"""
Bug Hunt & Code Autopsy — Real-world Forensic Debugging & Vulnerability Triage.
Engineers inspect realistic production snippets with insidious concurrency bugs,
memory leaks, security vulnerabilities, and off-by-one errors under a triage timer.
"""
from datetime import datetime, timezone
import json

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, DateTime, Integer, String, Text

from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine

bughunt_bp = Blueprint("bughunt", __name__, url_prefix="/api/bughunt")


class BugHuntLog(Base):
    __tablename__ = "bughunt_logs"

    id = Column(Integer, primary_key=True)
    case_id = Column(String(80), nullable=False)
    solved = Column(Integer, nullable=False, default=0)       # 1 if correct patch, 0 otherwise
    points_awarded = Column(Integer, nullable=False, default=0)
    time_taken_sec = Column(Integer, nullable=False, default=0)
    selected_line = Column(Integer, nullable=True)
    selected_patch = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=lambda: now_ist())

    def to_dict(self):
        return {
            "id": self.id,
            "case_id": self.case_id,
            "solved": bool(self.solved),
            "points_awarded": self.points_awarded,
            "time_taken_sec": self.time_taken_sec,
            "selected_line": self.selected_line,
            "selected_patch": self.selected_patch,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


Base.metadata.create_all(bind=engine, tables=[BugHuntLog.__table__], checkfirst=True)


CASES = [
    {
        "id": "bh_01_int_overflow",
        "title": "The Binary Search Integer Overflow",
        "severity": "High",
        "category": "Algorithms & Systems",
        "bounty_xp": 80,
        "summary": "Classic binary search implementation crash in production when array size exceeds 1.5 billion elements.",
        "code": (
            "1: def binary_search(arr, target):\n"
            "2:     low = 0\n"
            "3:     high = len(arr) - 1\n"
            "4:     while low <= high:\n"
            "5:         mid = (low + high) // 2\n"
            "6:         if arr[mid] == target:\n"
            "7:             return mid\n"
            "8:         elif arr[mid] < target:\n"
            "9:             low = mid + 1\n"
            "10:        else:\n"
            "11:            high = mid - 1\n"
            "12:    return -1"
        ),
        "bug_line": 5,
        "bug_explanation": "In 32-bit signed environments (or C++/Java backends), `(low + high)` overflows when sum exceeds 2^31 - 1, producing negative indices.",
        "options": [
            {"id": "A", "code": "mid = low + ((high - low) >> 1)", "correct": True},
            {"id": "B", "code": "mid = (low + high) * 2 // 4", "correct": False},
            {"id": "C", "code": "mid = int((low + high) / 2.0)", "correct": False},
            {"id": "D", "code": "mid = (high - low) // 2", "correct": False},
        ],
        "post_mortem": "Famous bug discovered by Joshua Bloch that existed undetected in Java's java.util.Arrays.binarySearch for over 9 years."
    },
    {
        "id": "bh_02_mutable_default",
        "title": "The Mutable Default Parameter Leak",
        "severity": "Medium",
        "category": "Python Runtime",
        "bounty_xp": 70,
        "summary": "User sessions mysteriously receive cached shopping cart items from previous unconnected sessions.",
        "code": (
            "1: class ShoppingCart:\n"
            "2:     def __init__(self, user_id, items=[]):\n"
            "3:         self.user_id = user_id\n"
            "4:         self.items = items\n"
            "5: \n"
            "6:     def add_item(self, item_id):\n"
            "7:         self.items.append(item_id)\n"
            "8:         return len(self.items)"
        ),
        "bug_line": 2,
        "bug_explanation": "Default parameter `items=[]` is evaluated once when the function is defined, making the list a shared singleton across all instances that omit the argument.",
        "options": [
            {"id": "A", "code": "def __init__(self, user_id, items=()):", "correct": False},
            {"id": "B", "code": "def __init__(self, user_id, items=None):\n    self.items = list(items) if items is not None else []", "correct": True},
            {"id": "C", "code": "def __init__(self, user_id, items=[*[]]):", "correct": False},
            {"id": "D", "code": "def __init__(self, user_id, items=copy(list)):", "correct": False},
        ],
        "post_mortem": "Default arguments are bound at function definition time, not runtime. Mutable defaults act as persistent state."
    },
    {
        "id": "bh_03_deadlock_inversion",
        "title": "Transfer Deadlock Lock Inversion",
        "severity": "Critical",
        "category": "Concurrency & Databases",
        "bounty_xp": 120,
        "summary": "Simultaneous bidirectional transfers between Account A and Account B cause server worker threads to lock up entirely.",
        "code": (
            "1: def transfer(src_account, dst_account, amount):\n"
            "2:     with src_account.lock:\n"
            "3:         with dst_account.lock:\n"
            "4:             if src_account.balance >= amount:\n"
            "5:                 src_account.balance -= amount\n"
            "6:                 dst_account.balance += amount\n"
            "7:                 return True\n"
            "8:             return False"
        ),
        "bug_line": 2,
        "bug_explanation": "If thread 1 transfers from A to B (acquires A, waits for B) while thread 2 transfers from B to A (acquires B, waits for A), classic Coffman circular wait causes a permanent deadlock.",
        "options": [
            {"id": "A", "code": "first, second = sorted([src_account, dst_account], key=lambda a: a.id)\nwith first.lock:\n    with second.lock:", "correct": True},
            {"id": "B", "code": "with dst_account.lock:\n    with src_account.lock:", "correct": False},
            {"id": "C", "code": "src_account.lock.acquire(timeout=0)\ndst_account.lock.acquire(timeout=0)", "correct": False},
            {"id": "D", "code": "global_lock.release()", "correct": False},
        ],
        "post_mortem": "Enforcing a global canonical locking order (e.g. by resource ID) strictly breaks the circular wait condition."
    },
    {
        "id": "bh_04_sql_injection",
        "title": "The Unsanitized Search Form",
        "severity": "Critical",
        "category": "Security & SQL",
        "bounty_xp": 90,
        "summary": "Penetration testers dumped the entire employee database using the username search endpoint.",
        "code": (
            "1: def find_user(db_cursor, username_query):\n"
            "2:     sql = f\"SELECT id, name, role FROM users WHERE username = '{username_query}'\"\n"
            "3:     db_cursor.execute(sql)\n"
            "4:     return db_cursor.fetchall()"
        ),
        "bug_line": 2,
        "bug_explanation": "Direct f-string interpolation into SQL statement allows arbitrary SQL execution if the user provides `admin' OR '1'='1`.",
        "options": [
            {"id": "A", "code": "sql = \"SELECT id, name, role FROM users WHERE username = %s\"\ndb_cursor.execute(sql, (username_query,))", "correct": True},
            {"id": "B", "code": "sql = \"SELECT id, name, role FROM users WHERE username = '\" + escape(username_query)", "correct": False},
            {"id": "C", "code": "sql = f\"SELECT id, name, role FROM users WHERE username = '{str(username_query)}'\"", "correct": False},
            {"id": "D", "code": "sql = f\"SELECT id, name, role FROM users WHERE binary username = '{username_query}'\"", "correct": False},
        ],
        "post_mortem": "Parameterized queries separate SQL structure from raw data inputs, neutralizing injection vectors at driver level."
    },
    {
        "id": "bh_05_float_equality",
        "title": "Financial Ledger Precision Drift",
        "severity": "High",
        "category": "Numerical Systems",
        "bounty_xp": 85,
        "summary": "Ledger reconciliation engine claims accounts don't balance after exactly 3 micro-transactions totaling $1.00.",
        "code": (
            "1: def verify_balance(transactions, expected_total):\n"
            "2:     total = sum(transactions)\n"
            "3:     if total == expected_total:\n"
            "4:         return 'BALANCED'\n"
            "5:     return f'DISCREPANCY: {total} != {expected_total}'"
        ),
        "bug_line": 3,
        "bug_explanation": "IEEE 754 binary floating-point representation cannot exactly represent 0.1 or 0.2 (0.1 + 0.2 == 0.30000000000000004), causing exact `==` equality checks to fail.",
        "options": [
            {"id": "A", "code": "from decimal import Decimal\ntotal = sum(Decimal(str(t)) for t in transactions)\nif total == Decimal(str(expected_total)):", "correct": True},
            {"id": "B", "code": "if float(round(total, 16)) == expected_total:", "correct": False},
            {"id": "C", "code": "if str(total) == str(expected_total):", "correct": False},
            {"id": "D", "code": "if total is expected_total:", "correct": False},
        ],
        "post_mortem": "Never use binary floating-point types for currencies. Always use arbitrary-precision Decimal or fixed integer cents."
    }
]


@bughunt_bp.route("/cases", methods=["GET"])
def list_cases():
    db = SessionLocal()
    logs = db.query(BugHuntLog).all()
    solved_ids = {l.case_id for l in logs if l.solved}
    db.close()

    result = []
    for c in CASES:
        item = {
            "id": c["id"],
            "title": c["title"],
            "severity": c["severity"],
            "category": c["category"],
            "bounty_xp": c["bounty_xp"],
            "summary": c["summary"],
            "solved": c["id"] in solved_ids,
        }
        result.append(item)

    return jsonify({"cases": result})


@bughunt_bp.route("/case/<case_id>", methods=["GET"])
def get_case(case_id):
    case = next((c for c in CASES if c["id"] == case_id), None)
    if not case:
        return jsonify({"error": "Case not found"}), 404

    # Sanitize options so correct answer is not leaked to client
    client_options = [{"id": o["id"], "code": o["code"]} for o in case["options"]]

    return jsonify({
        "case": {
            "id": case["id"],
            "title": case["title"],
            "severity": case["severity"],
            "category": case["category"],
            "bounty_xp": case["bounty_xp"],
            "summary": case["summary"],
            "code": case["code"],
            "options": client_options
        }
    })


@bughunt_bp.route("/case/<case_id>/triage", methods=["POST"])
def triage_case(case_id):
    case = next((c for c in CASES if c["id"] == case_id), None)
    if not case:
        return jsonify({"error": "Case not found"}), 404

    data = request.get_json() or {}
    selected_line = int(data.get("line") or 0)
    selected_patch = str(data.get("patch") or "").upper().strip()
    time_taken = int(data.get("time_taken_sec") or 0)

    correct_line = case["bug_line"]
    correct_option = next((o for o in case["options"] if o["correct"]), None)

    line_match = (selected_line == correct_line)
    patch_match = (selected_patch == (correct_option["id"] if correct_option else ""))

    is_solved = line_match and patch_match
    xp = case["bounty_xp"] if is_solved else (case["bounty_xp"] // 4 if (line_match or patch_match) else 10)

    db = SessionLocal()
    log = BugHuntLog(
        case_id=case_id,
        solved=1 if is_solved else 0,
        points_awarded=xp,
        time_taken_sec=time_taken,
        selected_line=selected_line,
        selected_patch=selected_patch,
    )
    db.add(log)
    db.commit()
    db.close()

    return jsonify({
        "solved": is_solved,
        "line_correct": line_match,
        "patch_correct": patch_match,
        "actual_bug_line": correct_line,
        "actual_patch": correct_option["id"] if correct_option else "A",
        "bug_explanation": case["bug_explanation"],
        "post_mortem": case["post_mortem"],
        "xp_awarded": xp,
    })


@bughunt_bp.route("/stats", methods=["GET"])
def get_stats():
    db = SessionLocal()
    logs = db.query(BugHuntLog).all()
    total_attempts = len(logs)
    solved_count = len({l.case_id for l in logs if l.solved})
    total_xp = sum(l.points_awarded for l in logs)
    
    if solved_count >= len(CASES):
        rank = "Chief Forensic Coroner"
    elif solved_count >= 3:
        rank = "Senior Vulnerability Investigator"
    elif solved_count >= 1:
        rank = "Incident Responder"
    else:
        rank = "Trainee Detective"

    db.close()
    return jsonify({
        "stats": {
            "total_attempts": total_attempts,
            "solved_cases": solved_count,
            "total_cases": len(CASES),
            "total_xp": total_xp,
            "rank": rank,
        }
    })
