"""
Task Studio: who does the work.

SYSTEM DESIGN CONCEPT: Strategy + Adapter + Registry
TaskProvider is the interface the pipeline talks to. GeminiProvider adapts our LLMClient (Pro models
first, falling through the list on errors) to it. PROVIDERS maps a name to a factory, so adding
another backend (e.g. OpenRouter) is one class plus one registry entry; STUDIO_PROVIDER picks it.
"""
import json
import os
import re
import time
from abc import ABC, abstractmethod

from api.core.clients import LLMClient, _strip_fences

# Pro first, then Flash. LLMClient moves to the next model as soon as one fails; 404 (unknown / retired)
# and 429 (no quota) come back in about a second. As of Oct 2026 a free key gets 429 for both Pro models
# (no Pro quota on the free tier) and 404 for gemini-2.5-*, so in practice a Flash model answers.
DEFAULT_STUDIO_MODELS = "gemini-3.1-pro-preview,gemini-pro-latest,gemini-3.8-flash,gemini-3.7-flash,gemini-3.5-flash"
LLM_BUDGET = 150      # seconds across the whole fallback chain, so a run finishes well inside 2.5 minutes
TEMPERATURE = 0.3
THINKING = "low"      # Gemini 3 thinking level: "low" keeps Flash fast enough to write whole files in time
MAX_PASSES = 3        # re-run the chain only when a model was busy (503) or the JSON came back broken ...
RETRY_PAUSE = 5       # ... after this many seconds
MIN_PASS_SECONDS = 25
_BUSY = re.compile(r"\b503\b|UNAVAILABLE|high demand", re.I)  # 404 / 429 are not worth a retry

BANNED_PHRASES = ("delve", "leverage", "seamless", "robust", "cutting-edge", "comprehensive", "tapestry",
                  "in today's world", "it's important to note")

SYSTEM_PROMPT = f"""You are a careful senior software engineer. You receive a user's project (its file listing and file contents) and a task. Do the task by editing the project, then document what you did.

Respond with ONLY one JSON object (no markdown fences, no text before or after it) with exactly these keys:
{{
  "title": "short title for the work, 3-10 words",
  "summary": "2-4 plain sentences: what was asked and what was done",
  "steps": ["each step you took, one short sentence each, in order"],
  "changes": [
    {{"path": "relative/path/as/listed.ext", "action": "create" | "update" | "delete", "why": "one sentence", "content": "the FULL new file content"}}
  ],
  "readme_md": "README in Markdown",
  "report": {{
    "objective": "...",
    "approach": "...",
    "implementation_details": "...",
    "how_to_run": "...",
    "results_and_testing": "...",
    "limitations_next_steps": "..."
  }},
  "notes": ["anything the user must know: assumptions, things you could not do, files you could not see"]
}}

Rules for "changes":
- Paths are relative to the project root, use forward slashes, and match the listing exactly for existing files. Never use absolute paths or "..".
- "content" is the complete new file (not a diff, not an excerpt, no placeholders such as "rest unchanged"). Omit "content" for "delete".
- Only include files that actually change. Do not include unchanged files. Do not include README.md unless the task is about the README; put the README in "readme_md" instead.
- Never rewrite a file marked PREVIEW ONLY, and never touch binary files.
- Keep the existing code style, language version and dependencies unless the task needs otherwise. The code must be complete and runnable.

Rules for "readme_md" (simple and beginner-friendly), in this order: what the project is (one short paragraph), setup (exact commands), how to run (exact commands), project structure (the real files, one line each), what changed in this update.

Rules for "report": each value is plain paragraphs; short "- " bullet lines are allowed. A short code snippet is allowed inside ``` fences in implementation_details only (at most 15 lines). Sections:
- objective: what the task asked for and why it matters for this project.
- approach: how you went about it and the main decisions.
- implementation_details: the specific files, functions and classes added or changed, and how they work.
- how_to_run: exact commands to install, run and test.
- results_and_testing: which tests or checks are in the output and what they cover. You did not run anything, so say what to run and what it checks; never report pass counts, timings or numbers you did not measure.
- limitations_next_steps: honest gaps and concrete next steps.

Writing style for summary, steps, readme_md, report and notes (the user will submit this as their own work, so it must read like a careful engineer wrote it):
- Plain, specific, factual sentences grounded in the actual files. Name real files, functions and commands.
- Past tense for what was done.
- No hype, filler or marketing tone. Never use these words or phrases: {", ".join(BANNED_PHRASES)}.
- No emojis. No chains of em dashes. No rhetorical questions. No closing pleasantries.
- Do not claim tests were run or passed. Do not invent results, numbers, datasets or files.
- If the task cannot be done fully with the files provided, do what is possible and say exactly what is missing in "notes".
"""


class ProviderError(RuntimeError):
    """The model failed or returned unusable output. Maps to HTTP 502."""


_ESCAPE = re.compile(r"\\(.)", re.S)


def _fix_escapes(text):
    """Double every backslash whose escape JSON doesn't know (pairs are consumed, so "\\\\d" stays valid)."""
    return _ESCAPE.sub(lambda m: m.group(0) if m.group(1) in '"\\/bfnrtu' else "\\\\" + m.group(1), text)


def parse_json_object(text):
    """Parse the model's reply into a dict, tolerating fences or stray text around the object."""
    text = _strip_fences(text or "")
    try:
        data = json.loads(text, strict=False)  # tolerate raw newlines/tabs inside strings
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ProviderError("The model did not return JSON.")
        candidate = text[start:end + 1]
        try:
            data = json.loads(candidate, strict=False)
        except ValueError:
            data = None
        if data is None:  # code in file contents often carries invalid escapes such as \d or \' -> keep them literal
            try:
                data = json.loads(_fix_escapes(candidate), strict=False)
            except ValueError:
                data = None
        if data is None:
            raise ProviderError("The model returned malformed JSON (the answer may have been cut off). Try a smaller project or a narrower prompt.")
    if not isinstance(data, dict):
        raise ProviderError("The model returned JSON, but not an object.")
    return data


def build_user_message(prompt, project_context, title=None):
    head = f"TASK FROM THE USER:\n{prompt.strip()}\n"
    if title:
        head += f"\nREPORT TITLE CHOSEN BY THE USER: {title.strip()}\n"
    return head + "\n" + project_context + "\n\nReturn the JSON object now."


def condense_errors(message):
    """'All LLM providers failed. m1: 404 NOT_FOUND. {...} | m2: ...' -> 'm1: 404 NOT_FOUND; m2: ...'."""
    parts = []
    for segment in str(message).split("All LLM providers failed.", 1)[-1].split(" | "):
        model, _, rest = segment.strip().partition(":")
        if not model:
            continue
        code = re.search(r"\b(\d{3})\s+([A-Z_]{4,})", rest)
        parts.append(f"{model.strip()}: {code.group(1)} {code.group(2)}" if code else segment.strip()[:100])
    return "; ".join(parts)[:600] or str(message)[:300]


class TaskProvider(ABC):
    """Strategy interface: do the task and return the raw (unvalidated) result dict, plus "model"."""
    name = "base"

    @abstractmethod
    def run(self, prompt: str, project_context: str, title: str = None) -> dict:
        ...


def studio_models():
    return [m.strip() for m in (os.getenv("STUDIO_MODELS") or DEFAULT_STUDIO_MODELS).split(",") if m.strip()]


class GeminiProvider(TaskProvider):
    name = "gemini"

    def __init__(self, client: LLMClient = None, budget: float = LLM_BUDGET, sleep=time.sleep):
        # openrouter_key="" turns off LLMClient's OpenRouter fallback: it ignores the time budget (a run could
        # pass Vercel's 300 s limit) and its free model can't take a 600k-char project. OpenRouter would be
        # its own provider in PROVIDERS instead.
        self.client = client or LLMClient(openrouter_key="", models=",".join(studio_models()), budget=budget)
        self.budget = budget
        self.sleep = sleep

    def run(self, prompt, project_context, title=None):
        message = build_user_message(prompt, project_context, title)
        deadline = time.monotonic() + self.budget
        error = "No model was tried."
        for _ in range(MAX_PASSES):
            remaining = deadline - time.monotonic()
            if remaining < MIN_PASS_SECONDS:
                break
            self.client.budget = remaining
            try:
                text = self.client.generate(message, json_mode=True, temperature=TEMPERATURE, system=SYSTEM_PROMPT,
                                            thinking=THINKING)
            except Exception as e:
                error = str(e)
                if not _BUSY.search(error):
                    break
                self.sleep(min(RETRY_PAUSE, max(0.0, deadline - time.monotonic() - MIN_PASS_SECONDS)))
                continue
            try:
                data = parse_json_object(text)
            except ProviderError as e:  # one broken answer: ask again while there is time
                error = f"{getattr(self.client, 'last_model', None) or 'model'}: {e}"
                continue
            data["model"] = getattr(self.client, "last_model", None) or "gemini"
            return data
        if "JSON" in error:
            raise ProviderError(error.split(": ", 1)[-1])
        raise ProviderError(f"No model could complete the task ({condense_errors(error)}). "
                            "503 means the model is busy and 429 means its quota is used up; try again in a few minutes.")


# Registry: name -> zero-argument factory. A new backend is one class + one line here.
OPENROUTER_MODEL = os.getenv("STUDIO_OPENROUTER_MODEL", "openrouter/free")
OPENROUTER_TIMEOUT = 100      # seconds; with Gemini's 150 s the worst case stays under Vercel's 300 s
OPENROUTER_MAX_CONTEXT = 120_000  # chars; free OpenRouter models have far smaller windows than Gemini
TRUNCATION_NOTE = "\n\n[... project truncated for the backup model ...]"
JSON_ONLY_NOTE = "\nOutput only valid JSON, no markdown fences."


class OpenRouterProvider(TaskProvider):
    """Adapter for OpenRouter's OpenAI-compatible API (used as the backup when Gemini can't answer)."""
    name = "openrouter"

    def __init__(self, api_key: str = None, model: str = None, timeout: float = OPENROUTER_TIMEOUT):
        self.api_key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY", "")
        self.model = model or OPENROUTER_MODEL
        self.timeout = timeout

    def run(self, prompt, project_context, title=None):
        if not self.api_key:
            raise ProviderError("OpenRouter backup is not configured (set OPENROUTER_API_KEY).")
        context = project_context
        if len(context) > OPENROUTER_MAX_CONTEXT:
            context = context[:OPENROUTER_MAX_CONTEXT] + TRUNCATION_NOTE
        import openai
        client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=self.api_key, timeout=self.timeout, max_retries=0)
        try:
            resp = client.chat.completions.create(
                model=self.model, temperature=TEMPERATURE,
                messages=[{"role": "system", "content": SYSTEM_PROMPT + JSON_ONLY_NOTE},
                          {"role": "user", "content": build_user_message(prompt, context, title)}])
            text = resp.choices[0].message.content or ""
        except Exception as e:
            raise ProviderError(f"OpenRouter backup failed: {str(e)[:160]}")
        data = parse_json_object(text)
        data["model"] = f"openrouter:{getattr(resp, 'model', None) or self.model}"
        return data


class FallbackProvider(TaskProvider):
    """Chain of responsibility: try each provider in order and return the first answer."""
    name = "fallback"

    def __init__(self, providers):
        self.providers = providers

    def run(self, prompt, project_context, title=None):
        errors = []
        for provider in self.providers:
            try:
                return provider.run(prompt, project_context, title)
            except ProviderError as e:
                errors.append(f"{provider.name}: {e}")
        raise ProviderError(" | ".join(errors) or "No provider configured.")


PROVIDERS = {
    "gemini": GeminiProvider,
    "openrouter": OpenRouterProvider,
    # Default: Gemini first (Pro, then Flash), OpenRouter as the backup.
    "auto": lambda: FallbackProvider([PROVIDERS["gemini"](), PROVIDERS["openrouter"]()]),
}


def get_provider(name: str = None) -> TaskProvider:
    name = (name or os.getenv("STUDIO_PROVIDER") or "auto").strip().lower()
    if name not in PROVIDERS:
        raise ProviderError(f"Unknown studio provider '{name}'.")
    return PROVIDERS[name]()
