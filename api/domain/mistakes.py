"""
Mistake journal: learn from every wrong submission.

Each entry records what went wrong on a DSA / CP problem. On create, one cheap LLM call tags it
with a category, the algorithmic pattern involved and a one-sentence actionable lesson. If the LLM
is unavailable (no key, quota, bad JSON) keyword heuristics pick the category and the lesson falls
back to the user's own words, so saving never fails because of the model.

Stats compare the last 7 days with the 7 before, and a deterministic pre-submit checklist is built
from the categories that recur most.
"""
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean

from api.core.clients import LLMClient
from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine
from api.domain.models import NotificationLog

MAX_WHAT = 2000
MAX_TITLE = 200
MAX_LINK = 500
MAX_PATTERN = 60
MAX_LESSON = 300
LLM_BUDGET = 20  # seconds; tagging is a nice-to-have, never worth a long wait
RECENT_DAYS = 30  # window for "recurring" categories

# key -> (label, keywords for the heuristic, pre-submit checklist lines)
CATEGORIES = {
    "off_by_one": (
        "Off by one",
        ["off by one", "off-by-one", "index", "bound", "<=", ">=", "n-1", "n+1", "last element",
         "first element", "inclusive", "exclusive", "fencepost", "out of range", "out of bounds", "loop"],
        ["Check loop bounds (< vs <=) and the first/last index", "Run the empty and single-element input"],
    ),
    "wrong_pattern": (
        "Wrong pattern",
        ["wrong approach", "wrong pattern", "wrong idea", "greedy fail", "greedy doesn't", "should have used",
         "should've used", "needed dp", "not greedy", "approach was wrong", "wrong algorithm", "misidentified"],
        ["Prove the approach on a counter-example before coding (greedy vs DP?)",
         "Name the pattern out loud and why it fits the constraints"],
    ),
    "missed_edge_case": (
        "Missed edge case",
        ["edge case", "corner case", "empty", "single", "n = 1", "n=1", "zero", "negative", "duplicate",
         "all same", "null", "none", "disconnected", "self loop", "special case"],
        ["Test n = 1, empty, all-equal, negatives and duplicates",
         "Ask: what if the graph is disconnected / the answer doesn't exist?"],
    ),
    "tle_complexity": (
        "TLE / complexity",
        ["tle", "time limit", "too slow", "timeout", "timed out", "complexity", "o(n^2)", "o(n2)", "n^2",
         "quadratic", "mle", "memory limit", "recursion depth", "stack overflow", "brute force"],
        ["Compute the worst-case complexity against the constraints before coding",
         "Watch for hidden O(n) work inside loops (string concat, list.pop(0), copies)"],
    ),
    "misread_problem": (
        "Misread problem",
        ["misread", "misunderstood", "didn't read", "did not read", "read the problem", "statement",
         "constraint", "thought it was", "missed that", "subsequence", "subarray", "1-indexed", "0-indexed",
         "output format", "modulo"],
        ["Re-read the statement and constraints; restate the task in one line",
         "Verify the output format, indexing and 'mod 1e9+7' on the samples"],
    ),
    "overflow": (
        "Overflow",
        ["overflow", "int32", "long long", "64-bit", "64 bit", "1e9+7", "integer limit", "too large",
         "big number", "multiplication overflow", "precision", "floating"],
        ["Use 64-bit ints for sums/products; take mod after every multiply",
         "Avoid floats for exact answers (compare with integers)"],
    ),
    "implementation_bug": (
        "Implementation bug",
        ["typo", "bug", "wrong variable", "forgot to", "forgot", "reset", "initialize", "initialise",
         "uninitialized", "copy paste", "copy-paste", "shadow", "swap", "wrong sign", "global", "visited",
         "didn't update", "mutated"],
        ["Re-initialise globals / visited arrays between test cases",
         "Dry-run the code on a sample by hand before submitting"],
    ),
    "other": (
        "Other",
        [],
        ["Write down the invariant your solution relies on and check it holds"],
    ),
}
CATEGORY_KEYS = list(CATEGORIES)
BASE_CHECKLIST = [
    "Run all samples plus one custom edge case",
    "Remove debug prints and check the I/O format",
]

# Pattern detection for the heuristic fallback (first match wins, so specific before generic).
PATTERNS = [
    ("sliding window", ["sliding window", "window"]),
    ("two pointers", ["two pointer", "two-pointer", "2 pointer"]),
    ("binary search", ["binary search", "lower_bound", "upper_bound", "bisect", "search on answer"]),
    ("prefix sums", ["prefix sum", "prefix", "difference array"]),
    ("monotonic stack", ["monotonic stack", "monotonic", "next greater"]),
    ("dynamic programming", ["dp", "dynamic programming", "memo", "knapsack", "tabulation"]),
    ("backtracking", ["backtrack", "permutation", "subsets"]),
    ("BFS", ["bfs", "breadth first", "shortest path in grid", "multi-source"]),
    ("DFS", ["dfs", "depth first"]),
    ("shortest paths", ["dijkstra", "bellman", "floyd", "shortest path"]),
    ("union find", ["union find", "dsu", "disjoint set"]),
    ("topological sort", ["topological", "topo sort", "kahn"]),
    ("trees", ["tree", "bst", "lca", "subtree"]),
    ("graphs", ["graph", "edge", "node", "cycle"]),
    ("heap", ["heap", "priority queue", "priority_queue", "heapq"]),
    ("hashing", ["hashmap", "hash map", "dictionary", "hash set", "counter"]),
    ("greedy", ["greedy"]),
    ("bit manipulation", ["bit", "xor", "bitmask"]),
    ("math", ["gcd", "prime", "sieve", "modular", "combinatorics", "ncr"]),
    ("strings", ["string", "substring", "palindrome", "kmp", "z-function"]),
    ("sorting", ["sort", "comparator"]),
    ("linked list", ["linked list"]),
    ("segment tree", ["segment tree", "fenwick", "bit tree"]),
]


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Mistake(Base):
    __tablename__ = "mistakes"

    id = Column(Integer, primary_key=True, index=True)
    log_id = Column(Integer, nullable=True, index=True)  # NotificationLog problem, if any (no FK: logs may be pruned)
    problem_title = Column(String(MAX_TITLE), nullable=True)
    link = Column(String(MAX_LINK), nullable=True)
    what_happened = Column(Text, nullable=False)
    category = Column(String(30), nullable=False, default="other", index=True)
    pattern = Column(String(MAX_PATTERN), nullable=True)
    lesson = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow, index=True)  # naive UTC
    resolved = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<Mistake(id={self.id}, category={self.category}, title={self.problem_title!r})>"


mistakes_bp = Blueprint("mistakes", __name__, url_prefix="/api/mistakes")


@mistakes_bp.record_once
def _ensure_table(state):
    """Create the table when the blueprint is registered, so wiring it in needs no extra step."""
    try:
        Mistake.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:  # e.g. a concurrent cold start created it first
        print(f"mistakes table check skipped: {e}")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _now_utc():
    """Naive UTC 'now' derived from now_ist() so tests can freeze time in one place."""
    return now_ist().astimezone(timezone.utc).replace(tzinfo=None)


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _label(key):
    return CATEGORIES.get(key, CATEGORIES["other"])[0]


def _serialize(m):
    return {
        "id": m.id,
        "log_id": m.log_id,
        "problem_title": m.problem_title,
        "link": m.link,
        "what_happened": m.what_happened,
        "category": m.category,
        "category_label": _label(m.category),
        "pattern": m.pattern,
        "lesson": m.lesson,
        "created_at": _iso(m.created_at),
        "resolved": bool(m.resolved),
    }


def _clean_str(value, limit, name, required=False):
    """Returns (value_or_None, error)."""
    if value is None:
        return (None, f"{name} can't be empty.") if required else (None, None)
    if not isinstance(value, str):
        return None, f"{name} must be text."
    value = value.strip()
    if not value:
        return (None, f"{name} can't be empty.") if required else (None, None)
    if len(value) > limit:
        return None, f"{name} must be at most {limit} characters."
    return value, None


def _clean_link(value):
    link, error = _clean_str(value, MAX_LINK, "Link")
    if error or link is None:
        return link, error
    if not re.match(r"^https?://\S+$", link, re.I):
        return None, "Link must be an http(s) URL."
    return link, None


def _clean_pattern(value):
    if not isinstance(value, str):
        return None
    value = re.sub(r"\s+", " ", value).strip().strip(".").lower()
    if not value or value in ("none", "null", "n/a", "unknown", "other"):
        return None
    return value[:MAX_PATTERN]


def _one_sentence(text, limit=MAX_LESSON):
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) > limit:
        text = text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return text


# ---------------- tagging ----------------
def heuristic_category(text):
    """Scores each category by keyword hits; ties go to the earlier (more specific) category."""
    t = (text or "").lower()
    best, best_score = "other", 0
    for key, (_, keywords, _) in CATEGORIES.items():
        score = sum(len(k) for k in keywords if k in t)  # longer phrases are stronger evidence
        if score > best_score:
            best, best_score = key, score
    return best


def heuristic_pattern(text):
    t = f" {(text or '').lower()} "
    for name, keywords in PATTERNS:
        for k in keywords:
            # word-boundary match for short tokens like "dp", "bit", "bfs"
            if (len(k) <= 4 and re.search(rf"\b{re.escape(k)}\b", t)) or (len(k) > 4 and k in t):
                return name
    return None


_SYSTEM = (
    "You tag competitive-programming mistakes. Reply with JSON only: "
    '{"category": one of ' + ", ".join(f'"{k}"' for k in CATEGORY_KEYS) + ", "
    '"pattern": the algorithmic pattern of the problem in 1-3 lowercase words (e.g. "binary search", '
    '"sliding window", "dynamic programming") or null, '
    '"lesson": ONE short actionable sentence (imperative, max 25 words) to avoid this next time}.'
)


def tag_mistake(what_happened, problem_title=None, topic=None):
    """Returns (category, pattern, lesson, source). source is 'ai' or 'heuristic'."""
    context = " ".join(x for x in (problem_title, topic, what_happened) if x)
    fallback_pattern = heuristic_pattern(context)
    if topic and not fallback_pattern:
        fallback_pattern = _clean_pattern(topic.split(",")[0])
    try:
        prompt = (f"Problem: {problem_title or 'unknown'}\n"
                  + (f"Topic: {topic}\n" if topic else "")
                  + f"What went wrong: {what_happened}")
        out = LLMClient(budget=LLM_BUDGET).generate_json(prompt, temperature=0.2, system=_SYSTEM, thinking="low")
        if not isinstance(out, dict):
            raise ValueError("not an object")
        category = str(out.get("category") or "").strip().lower()
        if category not in CATEGORIES:
            category = heuristic_category(what_happened)
        lesson = _one_sentence(out.get("lesson") if isinstance(out.get("lesson"), str) else "")
        pattern = _clean_pattern(out.get("pattern")) or fallback_pattern
        if lesson:
            return category, pattern, lesson, "ai"
    except Exception as e:  # no key, quota, timeout, bad JSON...
        print(f"mistake tagging fell back to heuristics: {str(e)[:160]}")
    return heuristic_category(what_happened), fallback_pattern, _one_sentence(what_happened), "heuristic"


# ---------------- stats / checklist ----------------
def _top_categories(rows, now, n=2):
    """Most frequent categories in the recent window (all time if that's empty); 'other' only as a last resort."""
    since = now - timedelta(days=RECENT_DAYS)
    recent = [m.category for m in rows if m.created_at and m.created_at >= since] or [m.category for m in rows]
    counts = Counter(recent)
    ranked = sorted(counts.items(), key=lambda kv: (kv[0] == "other", -kv[1], CATEGORY_KEYS.index(kv[0])
                                                    if kv[0] in CATEGORY_KEYS else 99))
    return [{"category": k, "label": _label(k), "count": c} for k, c in ranked[:n]]


def compute_stats(rows, now):
    this_start = now - timedelta(days=7)
    last_start = now - timedelta(days=14)
    this_week = Counter(m.category for m in rows if m.created_at and m.created_at >= this_start)
    last_week = Counter(m.category for m in rows if m.created_at and last_start <= m.created_at < this_start)
    per_category = [
        {"category": k, "label": _label(k), "this_week": this_week.get(k, 0), "last_week": last_week.get(k, 0),
         "total": sum(1 for m in rows if m.category == k)}
        for k in CATEGORY_KEYS
    ]
    patterns = Counter(m.pattern for m in rows if m.pattern)
    return {
        "total": len(rows),
        "open": sum(1 for m in rows if not m.resolved),
        "resolved": sum(1 for m in rows if m.resolved),
        "this_week": sum(this_week.values()),
        "last_week": sum(last_week.values()),
        "per_category": per_category,
        "top_categories": _top_categories(rows, now, 2),
        "top_patterns": [{"pattern": p, "count": c} for p, c in
                         sorted(patterns.items(), key=lambda kv: (-kv[1], kv[0]))[:5]],
    }


def build_checklist(rows, now):
    top = _top_categories(rows, now, 3)
    # No history yet: start from the two most common CP failure modes
    sources = top or [{"category": k, "label": _label(k), "count": 0} for k in ("missed_edge_case", "off_by_one")]
    items, seen = [], set()
    for t in sources:
        for line in CATEGORIES[t["category"]][2] if t["category"] in CATEGORIES else []:
            if line not in seen:
                seen.add(line)
                items.append({"text": line, "category": t["category"], "label": t["label"]})
    for line in BASE_CHECKLIST:
        items.append({"text": line, "category": None, "label": "Always"})
    text = "Pre-submit checklist\n" + "\n".join(f"[ ] {i['text']}" for i in items)
    return {"items": items, "based_on": top, "text": text}


# ---------------- routes ----------------
@mistakes_bp.route("", methods=["GET"])
def list_mistakes():
    category = (request.args.get("category") or "").strip().lower()
    if category and category not in CATEGORIES:
        return _err("Unknown category.")
    status = (request.args.get("status") or "").strip().lower()
    db = SessionLocal()
    try:
        rows = db.query(Mistake).order_by(Mistake.created_at.desc(), Mistake.id.desc()).all()
        items = [m for m in rows
                 if (not category or m.category == category)
                 and (status != "open" or not m.resolved)
                 and (status != "resolved" or m.resolved)]
        return jsonify({
            "status": "success",
            "data": [_serialize(m) for m in items],
            "stats": compute_stats(rows, _now_utc()),
            "categories": [{"key": k, "label": v[0]} for k, v in CATEGORIES.items()],
        })
    finally:
        db.close()


@mistakes_bp.route("/checklist", methods=["GET"])
def checklist():
    db = SessionLocal()
    try:
        rows = db.query(Mistake).all()
        return jsonify({"status": "success", "data": build_checklist(rows, _now_utc())})
    finally:
        db.close()


@mistakes_bp.route("", methods=["POST"])
def create_mistake():
    data = _body()
    what, error = _clean_str(data.get("what_happened"), MAX_WHAT, "What happened", required=True)
    if error:
        return _err(error)
    title, error = _clean_str(data.get("problem_title"), MAX_TITLE, "Problem title")
    if error:
        return _err(error)
    link, error = _clean_link(data.get("link"))
    if error:
        return _err(error)
    log_id = data.get("log_id")
    if log_id is not None and (not isinstance(log_id, int) or isinstance(log_id, bool)):
        return _err("log_id must be a number.")
    forced = data.get("category")  # the user picked a chip: respect it, still let the LLM write the lesson
    if forced is not None and forced not in CATEGORIES:
        return _err("Unknown category.")

    db = SessionLocal()
    try:
        topic = None
        if log_id is not None:
            log = db.get(NotificationLog, log_id)
            if not log:
                return _err("Problem not found.", 404)
            title = title or (log.title or "")[:MAX_TITLE] or None
            link = link or log.link
            topic = log.topic
        category, pattern, lesson, source = tag_mistake(what, title, topic)
        if forced:
            category = forced
        m = Mistake(log_id=log_id, problem_title=title, link=link, what_happened=what,
                    category=category, pattern=pattern, lesson=lesson, created_at=_now_utc(), resolved=False)
        db.add(m)
        db.commit()
        db.refresh(m)
        return jsonify({"status": "success", "data": _serialize(m), "source": source})
    finally:
        db.close()


@mistakes_bp.route("/<int:mistake_id>", methods=["PUT", "DELETE"])
def mistake_detail(mistake_id):
    db = SessionLocal()
    try:
        m = db.get(Mistake, mistake_id)
        if not m:
            return _err("Not found", 404)
        if request.method == "DELETE":
            db.delete(m)
            db.commit()
            return jsonify({"status": "success"})

        data = _body()
        if "what_happened" in data:
            what, error = _clean_str(data["what_happened"], MAX_WHAT, "What happened", required=True)
            if error:
                return _err(error)
            m.what_happened = what
        if "problem_title" in data:
            title, error = _clean_str(data["problem_title"], MAX_TITLE, "Problem title")
            if error:
                return _err(error)
            m.problem_title = title
        if "link" in data:
            link, error = _clean_link(data["link"])
            if error:
                return _err(error)
            m.link = link
        if "category" in data:
            if data["category"] not in CATEGORIES:
                return _err("Unknown category.")
            m.category = data["category"]
        if "pattern" in data:
            if data["pattern"] is not None and not isinstance(data["pattern"], str):
                return _err("Pattern must be text.")
            m.pattern = _clean_pattern(data["pattern"])
        if "lesson" in data:
            lesson, error = _clean_str(data["lesson"], MAX_LESSON, "Lesson")
            if error:
                return _err(error)
            m.lesson = lesson
        if "resolved" in data:
            m.resolved = bool(data["resolved"])
        db.commit()
        db.refresh(m)
        return jsonify({"status": "success", "data": _serialize(m)})
    finally:
        db.close()
