import fitz  # PyMuPDF
import base64
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import os

class PDFAnalyzer:
    def __init__(self, chunk_size=10):
        self.chunk_size = chunk_size
        self.llm = ChatOpenAI(model="gpt-4o", max_tokens=2048)

    def analyze_pdf_stream(self, file_stream):
        """
        Reads a PDF file stream, extracts pages, chunks them, and yields explanations.
        Yields JSON strings.
        """
        # Read the PDF into PyMuPDF
        pdf_bytes = file_stream.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        total_pages = len(doc)
        
        for chunk_start in range(0, total_pages, self.chunk_size):
            chunk_end = min(chunk_start + self.chunk_size, total_pages)
            
            # Extract images for the chunk
            images_data = []
            for page_num in range(chunk_start, chunk_end):
                page = doc.load_page(page_num)
                # Render page to an image (pixmap)
                # Matrix scales the image up or down, we'll keep it standard
                pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                # Convert to jpeg bytes
                img_bytes = pix.tobytes("jpeg")
                # Base64 encode
                img_base64 = base64.b64encode(img_bytes).decode("utf-8")
                images_data.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{img_base64}",
                        "detail": "auto"
                    }
                })

            # Prepare message for LangChain
            prompt_text = (
                f"You are an expert document analyzer. Here are pages {chunk_start + 1} to {chunk_end} "
                f"of a {total_pages}-page document. Please provide a detailed, easy-to-understand "
                "explanation of the content present in these pages. Make sure to describe and explain "
                "any charts, diagrams, or images you see on these pages."
            )
            
            content = [{"type": "text", "text": prompt_text}]
            content.extend(images_data)
            
            message = HumanMessage(content=content)
            
            try:
                response = self.llm.invoke([message])
                result = {
                    "status": "success",
                    "chunk": f"{chunk_start + 1}-{chunk_end}",
                    "explanation": response.content
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
            # We can use a smaller/faster model for the quiz if we wanted, but we'll stick to gpt-4o for quality
            response = self.llm.invoke([HumanMessage(content=prompt_text)])
            content = response.content.strip()
            # clean up markdown if present
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
            
            quiz_data = json.loads(content)
            return {"status": "success", "data": quiz_data}
        except Exception as e:
            return {"status": "error", "message": str(e)}
