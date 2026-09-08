"""
OOP CONCEPTS: Abstraction, Inheritance, Polymorphism
SYSTEM DESIGN: Strategy Pattern & Dependency Injection
"""
from abc import ABC, abstractmethod
import random
from backend.core.clients import LLMClient, EmailClient
from backend.domain.repositories import NotificationRepository

class BaseNotifier(ABC):
    """
    ABSTRACTION: This is an Abstract Base Class (ABC). 
    We cannot instantiate BaseNotifier directly. It forces child classes to implement `run()`.
    """
    def __init__(self, llm_client: LLMClient, email_client: EmailClient, repo: NotificationRepository, receiver_email: str):
        # DEPENDENCY INJECTION: We inject the complex clients into the notifier.
        self.llm = llm_client
        self.email = email_client
        self.repo = repo
        self.receiver_email = receiver_email

    @abstractmethod
    def run(self) -> dict:
        """
        Forces all child classes to define their own specific `run` behavior.
        """
        pass

# INHERITANCE: IncidentNotifier inherits from BaseNotifier
class IncidentNotifier(BaseNotifier):
    CATEGORIES = {
        "Women Safety": ["Molestation", "Harassment", "Domestic Violence", "Others"],
        "Traffic": ["Road Accident", "Abnormal Traffic", "Road Rage", "Others"],
        "Others": ["Others"]
    }

    def run(self) -> dict:
        # 1. Generate content specific to Incidents
        category = random.choice(list(self.CATEGORIES.keys()))
        incident_type = random.choice(self.CATEGORIES[category])
        
        prompt = f"""
        Generate a highly realistic fictional incident report for a sampling dataset.
        Category: '{category}', Type: '{incident_type}'.
        Provide a JSON response with keys: "title" and "description".
        """
        try:
            data = self.llm.generate_json(prompt)
            title = data.get("title", f"{incident_type} Incident")
            desc = data.get("description", "No description provided.")
        except Exception:
            title = f"{incident_type} Incident"
            desc = "Fallback template used due to LLM error."

        # 2. Format Email
        subject = f"Daily Incident Report: {title}"
        body = f"Category: {category}\nType: {incident_type}\n\nTitle: {title}\n\nDescription:\n{desc}\n\n--- To stop, reply STOP."

        # 3. Send Email
        success = self.email.send_email(self.receiver_email, subject, body)
        
        # 4. Log to Database via Repository Pattern
        status = "success" if success else "failed"
        self.repo.log_notification(task_type="incident", title=title, content=desc, status=status)

        return {"status": status, "title": title, "category": category, "type": incident_type}

# POLYMORPHISM: LeetcodeNotifier provides a completely different implementation of `run()`
class LeetcodeNotifier(BaseNotifier):
    def run(self) -> dict:
        prompt = """
        Pick a random, highly requested Data Structures and Algorithms problem from Striver's SDE/A2Z Sheet.
        Provide a JSON response with keys: 
        "title": the problem name (e.g. 'Two Sum'), 
        "difficulty": (Easy/Medium/Hard),
        "question": brief problem statement,
        "solution": the optimal approach in Python or C++.
        """
        try:
            data = self.llm.generate_json(prompt)
            title = data.get("title", "Random DSA Problem")
            difficulty = data.get("difficulty", "Medium")
            question = data.get("question", "Question missing")
            solution = data.get("solution", "Solution missing")
        except Exception:
            title = "Two Sum (Fallback)"
            difficulty = "Easy"
            question = "Given an array of integers, return indices of the two numbers such that they add up to a specific target."
            solution = "Use a hash map to store seen values."

        subject = f"Hourly LeetCode Challenge: {title} ({difficulty})"
        body = f"🔥 Striver's Sheet Problem\n\nTitle: {title}\nDifficulty: {difficulty}\n\nQuestion:\n{question}\n\nOptimal Solution:\n{solution}\n\n--- Keep Grinding!"

        success = self.email.send_email(self.receiver_email, subject, body)
        
        status = "success" if success else "failed"
        self.repo.log_notification(task_type="leetcode", title=title, content=question, status=status)

        return {"status": status, "title": title, "difficulty": difficulty}
