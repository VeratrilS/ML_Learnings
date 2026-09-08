"""
SYSTEM DESIGN CONCEPT: Factory Pattern
The Factory is responsible for the complex instantiation logic of objects.
Instead of the Flask app knowing exactly how to construct an IncidentNotifier 
(which requires LLMClient, EmailClient, DB Session, and Repository), the Flask app 
just asks the Factory: "Give me an incident notifier".

This heavily decouples our application.
"""
import os
from dotenv import load_dotenv
from api.core.clients import LLMClient, EmailClient
from api.domain.repositories import NotificationRepository
from api.domain.notifiers import IncidentNotifier, LeetcodeNotifier

class NotifierFactory:
    @staticmethod
    def get_notifier(notifier_type: str, db_session):
        # Load env vars safely
        load_dotenv()
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        sender_email = os.getenv("SENDER_EMAIL")
        sender_password = os.getenv("SENDER_PASSWORD")
        receiver_email = "sairaghava1318@gmail.com" # Hardcoded per original script

        if not all([openrouter_key, sender_email, sender_password]):
            raise ValueError("Missing environment variables in .env file.")

        # Instantiate our core clients
        llm = LLMClient(api_key=openrouter_key)
        email = EmailClient(sender_email=sender_email, sender_password=sender_password)
        repo = NotificationRepository(db_session=db_session)

        # POLYMORPHISM: Return the correct subclass based on the string type
        if notifier_type == "incident":
            return IncidentNotifier(llm, email, repo, receiver_email)
        elif notifier_type == "leetcode":
            return LeetcodeNotifier(llm, email, repo, receiver_email)
        else:
            raise ValueError(f"Unknown notifier type: {notifier_type}")
