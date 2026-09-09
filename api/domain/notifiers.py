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
    MAX_DEDUP_RETRIES = 3

    def _generate_new_problem(self, all_sent_titles: set) -> dict:
        """Generates a new problem from the LLM, with dedup retry logic."""
        avoid_list = ", ".join(sorted(all_sent_titles)) if all_sent_titles else "None"
        
        for attempt in range(self.MAX_DEDUP_RETRIES):
            prompt = f"""
            Pick a random, highly requested Data Structures and Algorithms problem from Striver's SDE/A2Z Sheet.
            IMPORTANT: Pick a completely DIFFERENT problem. Do NOT pick any of these previously sent problems: [{avoid_list}].
            {"CRITICAL: Your last suggestion was a duplicate. You MUST pick a DIFFERENT problem this time." if attempt > 0 else ""}
            Provide a JSON response with keys: 
            "title": the problem name (e.g. 'Two Sum'), 
            "difficulty": (Easy/Medium/Hard),
            "question": brief problem statement,
            "approach": Detailed step-by-step optimal approach and intuition,
            "cpp_code": The optimal solution written in C++,
            "leetcode_link": "A valid URL to this problem on LeetCode or GeeksForGeeks",
            "striver_link": "A valid URL to this topic on takeUforward/Striver"
            """
            
            data = self.llm.generate_json(prompt)
            title = data.get("title", "Random DSA Problem")
            
            # Programmatic dedup check: reject if already sent
            if title not in all_sent_titles:
                return data
            
            print(f"Dedup: LLM returned duplicate '{title}', retrying ({attempt + 1}/{self.MAX_DEDUP_RETRIES})...")
        
        # After all retries, accept whatever the LLM gives (better than nothing)
        print(f"Warning: Could not find unique problem after {self.MAX_DEDUP_RETRIES} retries. Using last result.")
        return data

    def _generate_retry_problem(self, task_title: str) -> dict:
        """Generates a detailed solution for a previously sent problem (spaced repetition)."""
        prompt = f"""
        Generate a detailed approach and C++ solution for the Data Structures and Algorithms problem: '{task_title}'.
        Provide a JSON response with keys: 
        "title": "{task_title}", 
        "difficulty": (Easy/Medium/Hard),
        "question": brief problem statement,
        "approach": Detailed step-by-step optimal approach and intuition,
        "cpp_code": The optimal solution written in C++,
        "leetcode_link": "A valid URL to this problem on LeetCode or GeeksForGeeks",
        "striver_link": "A valid URL to this topic on takeUforward/Striver"
        """
        return self.llm.generate_json(prompt)

    def run(self) -> dict:
        uncompleted_tasks = self.repo.get_uncompleted_leetcode_tasks()
        all_sent_titles = self.repo.get_all_sent_titles()
        is_retry = False

        try:
            if uncompleted_tasks and random.random() < 0.5:
                task = random.choice(uncompleted_tasks)
                is_retry = True
                data = self._generate_retry_problem(task.title)
            else:
                data = self._generate_new_problem(all_sent_titles)
            
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
            total_sent = len(all_sent_titles) + 1
            subject = f"Question #{total_sent} | LeetCode Challenge: {title} ({difficulty})"
            
        body = f"🔥 Striver's Sheet Problem\n\nTitle: {title}\nDifficulty: {difficulty}\n\nLinks:\n- Practice: {leetcode_link}\n- Learn: {striver_link}\n\nQuestion:\n{question}\n\nApproach:\n{approach}\n\nC++ Code:\n{cpp_code}\n\n--- Keep Grinding!"

        success = self.email.send_email(self.receiver_email, subject, body)
        
        status = "success" if success else "failed"
        
        # Only log new problems, don't duplicate logs for retries
        if not is_retry:
            self.repo.log_notification(task_type="leetcode", title=title, content=question, status=status)

        return {"status": status, "title": title, "difficulty": difficulty}
