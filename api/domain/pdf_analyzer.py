import fitz  # PyMuPDF
import base64
import json
from google import genai
import os

class PDFAnalyzer:
    def __init__(self, chunk_size=10):
        self.chunk_size = chunk_size
        self.client = genai.Client()

    def parse_pdf_chunks(self, filepath):
        """
        Parses a PDF file, splits it into chunks, and extracts raw text.
        Returns a list of dictionaries with chunk boundaries and text.
        """
        doc = fitz.open(filepath)
        total_pages = len(doc)
        
        chunks = []
        for chunk_start in range(0, total_pages, self.chunk_size):
            chunk_end = min(chunk_start + self.chunk_size, total_pages)
            
            # Extract raw text for this chunk (for the "Go to ChatGPT" clipboard feature)
            text = ""
            for page_num in range(chunk_start, chunk_end):
                page = doc.load_page(page_num)
                text += page.get_text("text") + "\n\n"
                
            chunks.append({
                "chunk": f"{chunk_start + 1}-{chunk_end}",
                "chunk_start": chunk_start,
                "chunk_end": chunk_end,
                "text": text.strip()
            })
            
        doc.close()
        return chunks

    def analyze_specific_chunk(self, filepath, chunk_start, chunk_end):
        """
        Reads a specific chunk from the saved PDF, extracts images, and yields explanations using Gemini.
        Yields JSON strings (SSE format).
        """
        try:
            doc = fitz.open(filepath)
            total_pages = len(doc)
        except Exception as e:
            result = {
                "status": "error",
                "chunk": f"{chunk_start + 1}-{chunk_end}",
                "message": f"Failed to open PDF: {str(e)}"
            }
            yield f"data: {json.dumps(result)}\n\n"
            return
            
        # Extract images for the chunk
        images_data = []
        for page_num in range(chunk_start, min(chunk_end, total_pages)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            img_bytes = pix.tobytes("jpeg")
            img_base64 = base64.b64encode(img_bytes).decode("utf-8")
            images_data.append({
                "type": "image",
                "data": img_base64,
                "mime_type": "image/jpeg"
            })

        doc.close()

        # Prepare message for Interactions API
        prompt_text = (
            f"You are an expert document analyzer. Here are pages {chunk_start + 1} to {chunk_end} "
            f"of a {total_pages}-page document. Please provide a detailed, easy-to-understand "
            "explanation of the content present in these pages. Make sure to describe and explain "
            "any charts, diagrams, or images you see on these pages."
        )
        
        inputs = [{"type": "text", "text": prompt_text}]
        inputs.extend(images_data)
        
        try:
            interaction = self.client.interactions.create(
                model="gemini-3.8-flash",
                input=inputs
            )
            result = {
                "status": "success",
                "chunk": f"{chunk_start + 1}-{chunk_end}",
                "explanation": interaction.output_text
            }
        except Exception as e:
            result = {
                "status": "error",
                "chunk": f"{chunk_start + 1}-{chunk_end}",
                "message": str(e)
            }
            
        yield f"data: {json.dumps(result)}\n\n"

    def generate_quiz(self, explanation_text):
        """
        Generates 3-5 multiple choice questions based on the explanation text.
        Returns a JSON object with a list of questions.
        """
        prompt_text = (
            "You are an expert tutor. Based on the following summary of a document, "
            "generate exactly 3 multiple choice questions to test the user's understanding. "
            "Return ONLY a valid JSON object in this exact format, with no markdown formatting or backticks around it:\n"
            "{\n"
            '  "questions": [\n'
            '    {\n'
            '      "question": "Question text here?",\n'
            '      "options": ["Option A", "Option B", "Option C", "Option D"],\n'
            '      "correct_answer": 0,\n'
            '      "explanation": "Why this is correct"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            f"Summary text:\n{explanation_text}"
        )
        
        try:
            interaction = self.client.interactions.create(
                model="gemini-3.8-flash",
                input=prompt_text
            )
            content = interaction.output_text.strip()
            # clean up markdown if present
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
            
            quiz_data = json.loads(content)
            return {"status": "success", "data": quiz_data}
        except Exception as e:
            return {"status": "error", "message": str(e)}
