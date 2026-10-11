"""
SYSTEM DESIGN CONCEPT: Factory Pattern
The Factory is responsible for the complex instantiation logic of objects.
Instead of the Flask app knowing exactly how to construct an IncidentNotifier
(which requires LLMClient, EmailClient, DB Session, and Repository), the Flask app
just asks the Factory: "Give me an incident notifier".

This heavily decouples our application.
"""
import os
from api.core.config import RECEIVER_EMAIL
from api.core.clients import LLMClient, EmailClient
from api.domain.repositories import NotificationRepository
from api.domain.notifiers import IncidentNotifier, LeetcodeNotifier


class NotifierFactory:
    @staticmethod
    def get_notifier(notifier_type: str, db_session):
        sender_email = os.getenv("SENDER_EMAIL")
        sender_password = os.getenv("SENDER_PASSWORD")

        if not all([sender_email, sender_password]):
            raise ValueError("Missing SENDER_EMAIL / SENDER_PASSWORD environment variables.")

        # Instantiate our core clients
        llm = LLMClient(budget=150)
        email = EmailClient(sender_email=sender_email, sender_password=sender_password)
        repo = NotificationRepository(db_session=db_session)

        # POLYMORPHISM: Return the correct subclass based on the string type
        if notifier_type == "incident":
            return IncidentNotifier(llm, email, repo, RECEIVER_EMAIL)
        elif notifier_type == "leetcode":
            return LeetcodeNotifier(llm, email, repo, RECEIVER_EMAIL)
        else:
            raise ValueError(f"Unknown notifier type: {notifier_type}")
