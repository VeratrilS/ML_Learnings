"""
SYSTEM DESIGN CONCEPT: Single Responsibility Principle (SRP)
Each class here has ONE job. 
- LLMClient: Only handles communication with the AI.
- EmailClient: Only handles sending SMTP emails.
"""
import smtplib
import openai
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class LLMClient:
    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        """
        DEPENDENCY INJECTION: We pass the API key in, rather than hardcoding it.
        """
        self.client = openai.OpenAI(base_url=base_url, api_key=api_key)

    def generate_json(self, prompt: str) -> dict:
        """Sends a prompt to the LLM and returns the parsed JSON."""
        try:
            response = self.client.chat.completions.create(
                model="google/gemini-2.5-flash",
                max_tokens=800,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON. Do not include markdown formatting or backticks, just the raw JSON object."},
                    {"role": "user", "content": prompt}
                ]
            )
            import json
            text = response.choices[0].message.content.strip()
            if text.startswith("```json"):
                text = text[7:-3].strip()
            elif text.startswith("```"):
                text = text[3:-3].strip()
            return json.loads(text)
        except Exception as e:
            print(f"LLM API failed: {e}")
            raise e

class EmailClient:
    def __init__(self, sender_email: str, sender_password: str):
        self.sender_email = sender_email
        self.sender_password = sender_password

    def send_email(self, receiver_email: str, subject: str, body: str) -> bool:
        """Handles the complex logic of SMTP configuration and dispatching."""
        msg = MIMEMultipart()
        msg['From'] = self.sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        try:
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.login(self.sender_email, self.sender_password)
            text = msg.as_string()
            server.sendmail(self.sender_email, receiver_email, text)
            server.quit()
            print(f"Email sent successfully to {receiver_email}")
            return True
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False
