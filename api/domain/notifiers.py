"""
OOP CONCEPTS: Abstraction, Inheritance, Polymorphism
SYSTEM DESIGN: Strategy Pattern & Dependency Injection
"""
import html
import json
import random
from abc import ABC, abstractmethod
from urllib.parse import quote_plus

from api.core.clients import LLMClient, EmailClient
from api.core.config import APP_URL
from api.domain.repositories import NotificationRepository, normalize_title
from api.domain.problem_bank import PROBLEMS


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
            data = self.llm.generate_json(prompt, temperature=0.9)
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


DIFFICULTY_PREFS = {
    "mixed": ["Easy", "Medium", "Hard"],
    "easy": ["Easy"],
    "easy-medium": ["Easy", "Medium"],
    "medium": ["Medium"],
    "medium-hard": ["Medium", "Hard"],
    "hard": ["Hard"],
}

WRITEUP_SYSTEM = (
    "You are an elite competitive programmer and DSA mentor (Striver / takeUforward style). "
    "You write precise, correct, interview-ready explanations. Never use LaTeX; write complexities like O(n log n)."
)


def generate_writeup(llm: LLMClient, title: str, slug: str, difficulty: str) -> dict:
    """Asks the LLM for a structured write-up of ONE specific, already-chosen problem."""
    prompt = f"""Write a complete study write-up for LeetCode problem "{title}" (https://leetcode.com/problems/{slug}/, {difficulty}).

Return a JSON object with exactly these keys:
- "statement": concise problem statement (3-6 sentences) including one small example with input/output.
- "pattern": the core technique in a few words (e.g. "Monotonic stack", "Binary search on answer").
- "hints": array of 3 progressive hints, from a gentle nudge to almost the idea. Do not give away the code.
- "brute_force": 1-3 sentences on the naive approach and its complexity.
- "intuition": a paragraph on the key insight that leads to the optimal solution.
- "approach": array of clear step-by-step strings for the optimal algorithm.
- "time_complexity": e.g. "O(n)".
- "space_complexity": e.g. "O(1)".
- "edge_cases": array of edge cases to watch for.
- "cpp_code": complete, compilable, optimal C++ solution in LeetCode's class Solution format with brief comments.
- "related": array of 2-3 related LeetCode problem titles to practice next."""
    data = llm.generate_json(prompt, temperature=0.4, system=WRITEUP_SYSTEM)
    return sanitize_writeup(data)


def _as_text(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return " — ".join(str(x) for x in v.values() if x)
    return "" if v is None else str(v)


def sanitize_writeup(data: dict) -> dict:
    """LLMs occasionally return objects where we expect strings; the UI only renders strings."""
    if not isinstance(data, dict):
        raise ValueError("Write-up is not a JSON object")
    clean = {}
    for key, value in data.items():
        if key in ("hints", "approach", "edge_cases", "related"):
            items = value if isinstance(value, list) else [value]
            clean[key] = [t for t in (_as_text(i).strip() for i in items) if t]
        else:
            clean[key] = _as_text(value)
    if not clean.get("cpp_code"):
        raise ValueError("Write-up is missing code")
    return clean


def problem_links(slug: str, title: str) -> dict:
    return {
        "leetcode": f"https://leetcode.com/problems/{slug}/",
        "editorial": f"https://leetcode.com/problems/{slug}/editorial/",
        "video": f"https://www.youtube.com/results?search_query={quote_plus('take u forward ' + title)}",
    }


# POLYMORPHISM: LeetcodeNotifier provides a completely different implementation of `run()`
class LeetcodeNotifier(BaseNotifier):
    def pick_problem(self, difficulty_pref: str = "mixed", skip: set = frozenset()):
        """Deterministically picks the next never-sent problem from the curated bank.
        Topics rotate (never the same topic twice in a row) and each topic progresses easy -> hard."""
        sent = self.repo.get_sent_keys("leetcode") | set(skip)  # skip = already solved on LeetCode
        allowed = DIFFICULTY_PREFS.get(difficulty_pref, DIFFICULTY_PREFS["mixed"])
        unsent = [p for p in PROBLEMS if p[1] not in sent and normalize_title(p[0]) not in sent]
        candidates = [p for p in unsent if p[2] in allowed] or unsent

        if not candidates:
            from api.domain.integrations import leetcode_random_unsent
            q = leetcode_random_unsent(sent, allowed) or leetcode_random_unsent(sent)
            if not q:
                raise RuntimeError("No unsent problems left.")
            return q

        recent_topics = [l.topic for l in self.repo.get_recent_logs(limit=10) if l.task_type == "leetcode" and l.topic][:2]
        topics = sorted({p[3] for p in candidates})
        fresh_topics = [t for t in topics if t not in recent_topics] or topics
        topic = random.choice(fresh_topics)
        title, slug, difficulty, topic, lc_id = next(p for p in candidates if p[3] == topic)
        return {"title": title, "slug": slug, "difficulty": difficulty, "topic": topic, "id": lc_id}

    def run(self, skip: set = frozenset()) -> dict:
        problem = self.pick_problem(self.repo.get_setting("leetcode_difficulty", "mixed"), skip)
        title, slug, difficulty, topic = problem["title"], problem["slug"], problem["difficulty"], problem["topic"]
        links = problem_links(slug, title)
        number = len(self.repo.get_all_leetcode_logs()) + 1
        pending = self.repo.get_uncompleted_leetcode_tasks()[:3]

        # Claim the problem before the slow LLM call so an overlapping run can't pick it too
        log = self.repo.log_notification(task_type="leetcode", title=title, content=None, status="sending",
                                         slug=slug, difficulty=difficulty, link=links["leetcode"], topic=topic)

        try:
            writeup = generate_writeup(self.llm, title, slug, difficulty)
        except Exception as e:
            print(f"Write-up generation failed: {e}")
            writeup = {}

        subject = f"#{number} · {title} ({difficulty}) · {topic}"
        body = _leetcode_plain(title, difficulty, topic, links, writeup, pending)
        html_body = _leetcode_html(number, title, difficulty, topic, links, writeup, pending)

        success = self.email.send_email(self.receiver_email, subject, body, html=html_body)
        status = "success" if success else "failed"

        self.repo.update_log(log, status=status, content=json.dumps(writeup) if writeup else None)

        return {"status": status, "id": log.id, "title": title, "difficulty": difficulty, "topic": topic,
                "link": links["leetcode"], "has_writeup": bool(writeup)}


# ---------------- Email rendering ----------------
_DIFF_COLORS = {"Easy": "#00a86b", "Medium": "#d97706", "Hard": "#dc2626"}


def _leetcode_plain(title, difficulty, topic, links, w, pending):
    parts = [f"{title}  [{difficulty}]  ·  {topic}", "", f"Solve: {links['leetcode']}", f"Editorial: {links['editorial']}", ""]
    if w.get("statement"):
        parts += ["PROBLEM", w["statement"], ""]
    if w.get("hints"):
        parts += ["HINTS"] + [f"{i}. {h}" for i, h in enumerate(w["hints"], 1)] + [""]
    if w.get("intuition"):
        parts += ["INTUITION", w["intuition"], ""]
    if w.get("approach"):
        parts += ["APPROACH"] + [f"{i}. {s}" for i, s in enumerate(w["approach"], 1)] + [""]
    if w.get("time_complexity"):
        parts += [f"Time: {w['time_complexity']}   Space: {w.get('space_complexity', '?')}", ""]
    if w.get("cpp_code"):
        parts += ["C++", w["cpp_code"], ""]
    if not w:
        parts += ["(AI write-up unavailable right now — open the app and tap 'Generate write-up'.)", ""]
    if pending:
        parts += ["STILL PENDING"] + [f"- {p.title}: {p.link or ''}" for p in pending] + [""]
    parts.append(f"Open dashboard: {APP_URL}")
    return "\n".join(parts)


def _leetcode_html(number, title, difficulty, topic, links, w, pending):
    e = html.escape
    color = _DIFF_COLORS.get(difficulty, "#6366f1")

    def section(label, inner):
        return (f'<tr><td style="padding:18px 28px 0"><div style="font:600 11px/1 system-ui,-apple-system,Segoe UI,sans-serif;'
                f'letter-spacing:.08em;text-transform:uppercase;color:#6b7280;margin-bottom:8px">{label}</div>{inner}</td></tr>')

    def para(t):
        return f'<p style="margin:0;font:15px/1.6 system-ui,-apple-system,Segoe UI,sans-serif;color:#111827;white-space:pre-wrap">{e(t)}</p>'

    def olist(items):
        lis = "".join(f'<li style="margin:0 0 6px">{e(str(i))}</li>' for i in items)
        return f'<ol style="margin:0;padding-left:20px;font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;color:#111827">{lis}</ol>'

    def button(href, label, primary=False):
        style = ("background:#111827;color:#fff;" if primary else "background:#f3f4f6;color:#111827;")
        return (f'<a href="{e(href)}" style="{style}display:inline-block;padding:10px 16px;border-radius:10px;'
                f'font:600 14px/1 system-ui,-apple-system,Segoe UI,sans-serif;text-decoration:none;margin:0 8px 8px 0">{label}</a>')

    rows = [
        f'<tr><td style="padding:28px 28px 0"><div style="font:600 12px/1 system-ui,sans-serif;color:#6b7280">DAILY DSA · #{number}</div>'
        f'<h1 style="margin:10px 0 12px;font:700 24px/1.25 system-ui,-apple-system,Segoe UI,sans-serif;color:#111827">{e(title)}</h1>'
        f'<span style="display:inline-block;padding:4px 10px;border-radius:999px;background:{color}1a;color:{color};font:600 12px/1.4 system-ui,sans-serif">{e(difficulty)}</span> '
        f'<span style="display:inline-block;padding:4px 10px;border-radius:999px;background:#eef2ff;color:#4338ca;font:600 12px/1.4 system-ui,sans-serif">{e(topic)}</span>'
        f'{" " if w.get("pattern") else ""}'
        + (f'<span style="display:inline-block;padding:4px 10px;border-radius:999px;background:#f3f4f6;color:#374151;font:600 12px/1.4 system-ui,sans-serif">{e(w["pattern"])}</span>' if w.get("pattern") else "")
        + '</td></tr>',
        f'<tr><td style="padding:18px 28px 0">{button(links["leetcode"], "Solve on LeetCode →", True)}{button(links["editorial"], "Editorial")}{button(links["video"], "Video")}</td></tr>',
    ]
    if w.get("statement"):
        rows.append(section("Problem", para(w["statement"])))
    if w.get("hints"):
        rows.append(section("Hints — try before scrolling", olist(w["hints"])))
    if w.get("intuition"):
        rows.append(section("Intuition", para(w["intuition"])))
    if w.get("approach"):
        rows.append(section("Optimal approach", olist(w["approach"])))
    if w.get("time_complexity"):
        rows.append(section("Complexity", para(f"Time {w['time_complexity']}  ·  Space {w.get('space_complexity', '?')}")))
    if w.get("edge_cases"):
        rows.append(section("Edge cases", olist(w["edge_cases"])))
    if w.get("cpp_code"):
        rows.append(section("C++ solution", f'<pre style="margin:0;padding:16px;background:#0b1020;color:#e5e7eb;border-radius:12px;'
                                             f'font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;overflow-x:auto;white-space:pre">{e(w["cpp_code"])}</pre>'))
    if not w:
        rows.append(section("Write-up", para("AI write-up unavailable right now. Open the dashboard and tap 'Generate write-up'.")))
    if pending:
        items = "".join(f'<li style="margin:0 0 6px"><a href="{e(p.link or "")}" style="color:#4338ca;text-decoration:none">{e(p.title)}</a></li>' for p in pending)
        rows.append(section(f"Still pending", f'<ul style="margin:0;padding-left:18px;font:14px/1.5 system-ui,sans-serif">{items}</ul>'))
    rows.append(f'<tr><td style="padding:24px 28px 28px">{button(APP_URL, "Open dashboard")}</td></tr>')

    return ('<!doctype html><html><body style="margin:0;background:#f5f5f7;padding:24px 12px">'
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;margin:0 auto;background:#ffffff;'
            'border-radius:18px;border:1px solid #e5e7eb">' + "".join(rows) + '</table></body></html>')
