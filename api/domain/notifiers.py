"""
OOP CONCEPTS: Abstraction, Inheritance, Polymorphism
SYSTEM DESIGN: Strategy Pattern & Dependency Injection
"""
from abc import ABC, abstractmethod
import random
from api.core.clients import LLMClient, EmailClient
from api.domain.repositories import NotificationRepository

class BaseNotifier(ABC):
    """
    ABSTRACTION: This is an Abstract Base Class (ABC). 
    We cannot instantiate BaseNotifier directly. It forces child classes to implement `run()`.
    """
    def __init__(self, llm_client: LLMClient, email_client: EmailClient, repo: NotificationRepository, receiver_email: str):
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
        uncompleted_tasks = self.repo.get_uncompleted_leetcode_tasks()
        all_logs = self.repo.get_all_leetcode_logs()
        completed_titles = [log.title for log in all_logs if log.is_completed]
        
        unique_titles = set(log.title for log in all_logs)
        is_retry = False

        if uncompleted_tasks and random.random() < 0.5:
            task = random.choice(uncompleted_tasks)
            is_retry = True
            prompt = f"""
            Generate a detailed approach and C++ solution for the Data Structures and Algorithms problem: '{task.title}'.
            Provide a JSON response with keys: 
            "title": "{task.title}", 
            "difficulty": (Easy/Medium/Hard),
            "question": brief problem statement,
            "approach": Detailed step-by-step optimal approach and intuition,
            "cpp_code": The optimal solution written in C++,
            "leetcode_link": "A valid URL to this problem on LeetCode or GeeksForGeeks",
            "striver_link": "A valid URL to this topic on takeUforward/Striver"
            """
        else:
            avoid_list = ", ".join(completed_titles[-50:])
            prompt = f"""
            Pick a random, highly requested Data Structures and Algorithms problem from Striver's SDE/A2Z Sheet.
            IMPORTANT: Pick a completely DIFFERENT problem. Do NOT pick any of these: {avoid_list}.
            Provide a JSON response with keys: 
            "title": the problem name (e.g. 'Two Sum'), 
            "difficulty": (Easy/Medium/Hard),
            "question": brief problem statement,
            "approach": Detailed step-by-step optimal approach and intuition,
            "cpp_code": The optimal solution written in C++,
            "leetcode_link": "A valid URL to this problem on LeetCode or GeeksForGeeks",
            "striver_link": "A valid URL to this topic on takeUforward/Striver"
            """
        
        try:
            data = self.llm.generate_json(prompt)
            title = data.get("title", "Random DSA Problem")
            difficulty = data.get("difficulty", "Medium")
            question = data.get("question", "Question missing")
            approach = data.get("approach", "Approach missing")
            cpp_code = data.get("cpp_code", "Code missing")
            leetcode_link = data.get("leetcode_link", "https://leetcode.com/problemset/all/")
            striver_link = data.get("striver_link", "https://takeuforward.org/strivers-a2z-dsa-course/strivers-a2z-dsa-course-sheet-2/")
        except Exception:
            title = "Reverse Linked List (Fallback)"
            difficulty = "Easy"
            question = "Reverse a singly linked list."
            approach = "Iterate through the list and change next pointers to previous nodes."
            cpp_code = "class Solution {\npublic:\n    ListNode* reverseList(ListNode* head) {\n        ... \n    }\n};"
            leetcode_link = "https://leetcode.com/problems/reverse-linked-list/"
            striver_link = "https://takeuforward.org/data-structure/reverse-a-linked-list/"

        if is_retry:
            subject = f"Retry | LeetCode Challenge: {title} ({difficulty})"
        else:
            total_sent = len(unique_titles) + 1
            subject = f"Question #{total_sent} | LeetCode Challenge: {title} ({difficulty})"
            
        body = f"🔥 Striver's Sheet Problem\n\nTitle: {title}\nDifficulty: {difficulty}\n\nLinks:\n- Practice: {leetcode_link}\n- Learn: {striver_link}\n\nQuestion:\n{question}\n\nApproach:\n{approach}\n\nC++ Code:\n{cpp_code}\n\n--- Keep Grinding!"

        success = self.email.send_email(self.receiver_email, subject, body)
        
        status = "success" if success else "failed"
        
        # Only log new problems, don't duplicate logs for retries
        if not is_retry:
            self.repo.log_notification(task_type="leetcode", title=title, content=question, status=status)

        return {"status": status, "title": title, "difficulty": difficulty}
