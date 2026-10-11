"""
SYSTEM DESIGN CONCEPT: Single Responsibility Principle (SRP)
Each class here has ONE job.
- LLMClient: Only handles communication with the AI (Gemini first, OpenRouter as a backup).
- EmailClient: Only handles sending SMTP emails.
"""
import json
import os
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from api.core import config  # noqa: F401  (loads .env)

# Strongest models available on the free tier first; we fall through on quota / availability errors.
DEFAULT_GEMINI_MODELS = "gemini-3.8-flash,gemini-3.7-flash,gemini-3.5-flash,gemini-2.5-flash"


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


class LLMClient:
    def __init__(self, gemini_key: str = None, openrouter_key: str = None, models: str = None, budget: float = 240):
        """
        DEPENDENCY INJECTION: Keys are passed in (or read from env), never hardcoded.
        """
        self.gemini_key = gemini_key if gemini_key is not None else os.getenv("GEMINI_API_KEY", "")
        self.openrouter_key = openrouter_key if openrouter_key is not None else os.getenv("OPENROUTER_API_KEY", "")
        self.models = [m.strip() for m in (models or os.getenv("GEMINI_MODELS") or DEFAULT_GEMINI_MODELS).split(",") if m.strip()]
        self.budget = budget  # total seconds we may spend across the whole fallback chain
        self._gemini = None

    @property
    def gemini(self):
        if self._gemini is None and self.gemini_key:
            from google import genai
            from google.genai import types
            self._gemini = genai.Client(api_key=self.gemini_key)
        return self._gemini

    def _config(self, json_mode: bool, temperature: float, system: str, timeout_s: float, thinking: str = None):
        from google.genai import types
        return types.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json" if json_mode else None,
            system_instruction=system,
            thinking_config=types.ThinkingConfig(thinking_level=thinking) if thinking else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
        )

    def _attempts(self):
        """Yields (model, timeout_s) while time remains. The first models get a fair share, never the whole budget."""
        deadline = time.time() + self.budget
        for i, model in enumerate(self.models):
            remaining = deadline - time.time()
            if remaining < 8:
                return
            left = len(self.models) - i
            yield model, remaining if left == 1 else max(remaining * 0.6, min(remaining, 45))

    @staticmethod
    def image_part(data: bytes, mime_type: str = "image/jpeg"):
        from google.genai import types
        return types.Part.from_bytes(data=data, mime_type=mime_type)

    def generate(self, contents, json_mode: bool = False, temperature: float = 0.7, system: str = None, thinking: str = None) -> str:
        """Returns the model's text. `contents` is a prompt string or a list of str / image parts."""
        errors = []
        if self.gemini:
            for model, timeout_s in self._attempts():
                try:
                    resp = self.gemini.models.generate_content(
                        model=model, contents=contents, config=self._config(json_mode, temperature, system, timeout_s, thinking if "gemini-3" in model else None))
                    if resp.text:
                        return resp.text
                    errors.append(f"{model}: empty response")
                except Exception as e:
                    errors.append(f"{model}: {str(e)[:160]}")
        text_prompt = contents if isinstance(contents, str) else "\n\n".join(c for c in contents if isinstance(c, str))
        if self.openrouter_key and text_prompt:
            try:
                return self._openrouter(text_prompt, json_mode, temperature, system)
            except Exception as e:
                errors.append(f"openrouter: {str(e)[:160]}")
        raise RuntimeError("All LLM providers failed. " + " | ".join(errors or ["No API key configured (set GEMINI_API_KEY)."]))

    def generate_json(self, contents, temperature: float = 0.7, system: str = None, thinking: str = None) -> dict:
        return json.loads(_strip_fences(self.generate(contents, json_mode=True, temperature=temperature, system=system, thinking=thinking)))

    def stream(self, contents, temperature: float = 0.5, system: str = None, thinking: str = None):
        """Yields text deltas. Falls back to the next model only if nothing was streamed yet."""
        errors = []
        if self.gemini:
            for model, timeout_s in self._attempts():
                started = False
                try:
                    for chunk in self.gemini.models.generate_content_stream(
                            model=model, contents=contents, config=self._config(False, temperature, system, timeout_s, thinking if "gemini-3" in model else None)):
                        if chunk.text:
                            started = True
                            yield chunk.text
                    if started:
                        return
                except Exception as e:
                    if started:
                        raise
                    errors.append(f"{model}: {str(e)[:160]}")
        # Non-streaming fallback (OpenRouter, text only)
        text_prompt = contents if isinstance(contents, str) else "\n\n".join(c for c in contents if isinstance(c, str))
        if self.openrouter_key and text_prompt:
            yield self._openrouter(text_prompt, False, temperature, system)
            return
        raise RuntimeError("All LLM providers failed. " + " | ".join(errors or ["No API key configured (set GEMINI_API_KEY)."]))

    def _openrouter(self, prompt: str, json_mode: bool, temperature: float, system: str = None) -> str:
        import openai
        client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=self.openrouter_key, timeout=50)
        sys_msg = system or ""
        if json_mode:
            sys_msg += "\nOutput only valid JSON, no markdown fences."
        response = client.chat.completions.create(
            model="openrouter/free",
            temperature=temperature,
            messages=[{"role": "system", "content": sys_msg.strip() or "You are a helpful assistant."},
                      {"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content


class EmailClient:
    def __init__(self, sender_email: str, sender_password: str):
        self.sender_email = sender_email
        self.sender_password = sender_password

    def send_email(self, receiver_email: str, subject: str, body: str, html: str = None) -> bool:
        """Handles the complex logic of SMTP configuration and dispatching. Sends HTML + plain-text fallback."""
        msg = MIMEMultipart("alternative")
        msg['From'] = self.sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        if html:
            msg.attach(MIMEText(html, 'html', 'utf-8'))

        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=20) as server:
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, receiver_email, msg.as_string())
            print(f"Email sent successfully to {receiver_email}")
            return True
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False
