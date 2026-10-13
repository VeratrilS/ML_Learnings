"""
Task Studio: who does the work.

SYSTEM DESIGN CONCEPT: Strategy + Adapter + Registry
TaskProvider is the interface the pipeline talks to. GeminiProvider adapts our LLMClient (Pro models
first, falling through the list on errors) to it. PROVIDERS maps a name to a factory, so adding
another backend (e.g. OpenRouter) is one class plus one registry entry; STUDIO_PROVIDER picks it.
"""
import json
import os
from abc import ABC, abstractmethod

from api.core.clients import LLMClient, _strip_fences

DEFAULT_STUDIO_MODELS = "gemini-3.8-pro,gemini-3.5-pro,gemini-2.5-pro,gemini-3.8-flash,gemini-2.5-flash"
LLM_BUDGET = 230      # seconds across the whole fallback chain (Vercel allows 300 per request)
TEMPERATURE = 0.3

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


def parse_json_object(text):
    """Parse the model's reply into a dict, tolerating fences or stray text around the object."""
    text = _strip_fences(text or "")
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ProviderError("The model did not return JSON.")
        try:
            data = json.loads(text[start:end + 1])
        except ValueError:
            raise ProviderError("The model returned malformed JSON (the answer may have been cut off). Try a smaller project or a narrower prompt.")
    if not isinstance(data, dict):
        raise ProviderError("The model returned JSON, but not an object.")
    return data


def build_user_message(prompt, project_context, title=None):
    head = f"TASK FROM THE USER:\n{prompt.strip()}\n"
    if title:
        head += f"\nREPORT TITLE CHOSEN BY THE USER: {title.strip()}\n"
    return head + "\n" + project_context + "\n\nReturn the JSON object now."


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

    def __init__(self, client: LLMClient = None, budget: float = LLM_BUDGET):
        self.client = client or LLMClient(models=",".join(studio_models()), budget=budget)

    def run(self, prompt, project_context, title=None):
        try:
            text = self.client.generate(build_user_message(prompt, project_context, title), json_mode=True,
                                        temperature=TEMPERATURE, system=SYSTEM_PROMPT)
        except Exception as e:
            raise ProviderError(f"The model could not complete the task: {str(e)[:400]}")
        data = parse_json_object(text)
        data["model"] = getattr(self.client, "last_model", None) or "gemini"
        return data


# Registry: name -> zero-argument factory. A new backend is one class + one line here.
PROVIDERS = {
    "gemini": GeminiProvider,
}


def get_provider(name: str = None) -> TaskProvider:
    name = (name or os.getenv("STUDIO_PROVIDER") or "gemini").strip().lower()
    if name not in PROVIDERS:
        raise ProviderError(f"Unknown studio provider '{name}'.")
    return PROVIDERS[name]()
