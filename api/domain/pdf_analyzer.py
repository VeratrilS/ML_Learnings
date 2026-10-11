"""
PDF Studio service. Pages are rendered to images in the browser (pdf.js), so the server
stays stateless and never stores uploads — it only talks to the LLM.
"""
import base64
import json

from api.core.clients import LLMClient

EXPLAIN_SYSTEM = (
    "You are an outstanding university tutor. You explain documents so a student can revise for exams from your notes alone. "
    "Write in clean Markdown: short sections with ## headings, bullet points, **bold** key terms, and tables where useful. "
    "Explain every diagram, chart, table and formula you see. Never use LaTeX; write math inline in plain text. "
    "End with a '## Key takeaways' section of 3-6 bullets and a '## Likely exam questions' section of 3 questions."
)


class PDFAnalyzer:
    def __init__(self, llm: LLMClient = None):
        self.llm = llm or LLMClient()

    def explain_stream(self, label: str, total_pages: int, page_images: list, page_text: str = "", focus: str = ""):
        """Yields SSE events: {type: delta, text} ... {type: done} | {type: error, message}."""
        contents = [
            f"These are pages {label} of a {total_pages}-page document."
            + (f"\nThe student specifically wants: {focus}" if focus else "")
            + (f"\n\nExtracted text (may be imperfect):\n{page_text[:20000]}" if page_text else "")
        ]
        for img in page_images[:12]:
            data = img.split(",", 1)[1] if img.startswith("data:") else img
            contents.append(self.llm.image_part(base64.b64decode(data), "image/jpeg"))

        try:
            for delta in self.llm.stream(contents, temperature=0.4, system=EXPLAIN_SYSTEM, thinking="low"):
                yield f"data: {json.dumps({'type': 'delta', 'text': delta})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)[:500]})}\n\n"

    def generate_quiz(self, explanation_text, count: int = 5):
        """Generates multiple choice questions based on the explanation text."""
        prompt = (
            f"Based on the study notes below, write exactly {count} challenging multiple-choice questions that test real understanding "
            "(not trivia). Return JSON: {\"questions\": [{\"question\": str, \"options\": [4 strings], "
            "\"correct_answer\": index 0-3, \"explanation\": str}]}. Vary the position of the correct answer.\n\n"
            f"Notes:\n{explanation_text[:30000]}"
        )
        try:
            quiz_data = self.llm.generate_json(prompt, temperature=0.6)
            return {"status": "success", "data": quiz_data}
        except Exception as e:
            return {"status": "error", "message": str(e)}
