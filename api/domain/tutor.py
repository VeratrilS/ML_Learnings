"""
Socratic DSA tutor + solution reviewer for a single problem (a leetcode NotificationLog).

- /chat streams a Socratic tutor turn over SSE ({type: delta|done|error}). The tutor sees the stored
  write-up with the reference code REDACTED, asks guiding questions, and only escalates hints when asked.
- /assess grades a free-text approach into a small JSON verdict (idea, missing insight, next question).
- /review reviews the student's code against the write-up; results are cached by sha256 in TutorCache,
  so re-reviewing identical code is instant and costs no quota.
"""
import hashlib
import json
import re
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import Column, DateTime, Integer, String, Text, Index

from api.core.clients import LLMClient
from api.core.db import Base, SessionLocal, engine
from api.domain.models import NotificationLog

CHAT_TURNS = 6            # most recent messages sent to the model
MAX_MSG = 2000            # chars per chat message
MAX_APPROACH = 4000
MAX_CODE = 20000
CHAT_BUDGET = 45          # seconds (free tier can be slow; Vercel caps at 300s)
ASSESS_BUDGET = 40
REVIEW_BUDGET = 60

LANGUAGES = {"cpp": "C++", "java": "Java", "python": "Python"}
_LANG_ALIASES = {"c++": "cpp", "cpp": "cpp", "cc": "cpp", "java": "java", "python": "python", "py": "python",
                 "python3": "python"}
VERDICTS = ("correct", "likely correct", "buggy", "wrong approach")
GRADES = ("again", "hard", "good", "easy")
_VERDICT_GRADE = {"correct": "good", "likely correct": "good", "buggy": "hard", "wrong approach": "again"}
_REDACTED_KEYS = ("cpp_code", "code", "java_code", "python_code", "solution")

_LLM_FRIENDLY = "The AI is busy right now (free-tier limits). Give it a few seconds and try again."


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TutorCache(Base):
    __tablename__ = "tutor_cache"

    id = Column(Integer, primary_key=True, index=True)
    feature = Column(String(20), nullable=False)   # 'review'
    key = Column(String(64), nullable=False)       # sha256 hex
    payload = Column(Text, nullable=False)         # JSON
    created_at = Column(DateTime, default=_utcnow)  # naive UTC

    __table_args__ = (Index("ix_tutor_cache_feature_key", "feature", "key"),)


tutor_bp = Blueprint("tutor", __name__, url_prefix="/api/tutor")


@tutor_bp.record_once
def _ensure_table(state):
    try:
        TutorCache.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:  # e.g. a concurrent cold start created it first
        print(f"tutor_cache table check skipped: {e}")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _sse(payload):
    return f"data: {json.dumps(payload)}\n\n"


def _friendly(e):
    msg = str(e)
    if "No API key" in msg:
        return "AI is not configured (set GEMINI_API_KEY)."
    if re.search(r"429|quota|RESOURCE_EXHAUSTED|overloaded|503|UNAVAILABLE|timed? ?out|deadline", msg, re.I):
        return _LLM_FRIENDLY
    if isinstance(e, (ValueError, json.JSONDecodeError)):
        return "The AI returned something unreadable. Please try again."
    return f"Tutor error: {msg[:300]}"


def _load_problem(log_id):
    """Returns (problem dict, error response). The problem carries title/meta and the parsed write-up."""
    db = SessionLocal()
    try:
        log = db.get(NotificationLog, log_id)
        if not log or log.task_type not in ("leetcode", "codeforces"):
            return None, _err("Problem not found.", 404)
        writeup = {}
        if log.content:
            try:
                parsed = json.loads(log.content)
                writeup = parsed if isinstance(parsed, dict) else {}
            except ValueError:
                writeup = {"statement": log.content}  # legacy rows stored the question text only
        return {"title": log.title, "difficulty": log.difficulty or "", "topic": log.topic or "",
                "slug": log.slug or "", "link": log.link or "", "task_type": log.task_type,
                "writeup": writeup}, None
    finally:
        db.close()


def _as_list(v):
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    return [str(v)] if v else []


def problem_context(problem, include_code=False):
    """Plain-text brief of the problem for prompts. Reference code is redacted unless include_code."""
    w = problem.get("writeup") or {}
    lines = [f"Problem: {problem['title']}"
             + (f" ({'Codeforces' if problem.get('task_type') == 'codeforces' else 'LeetCode'}, {problem['difficulty']})"
                if problem.get("difficulty") else "")
             + (f" — topic: {problem['topic']}" if problem.get("topic") else "")]
    link = problem.get("link") or (f"https://leetcode.com/problems/{problem['slug']}/"
                                   if problem.get("slug") and problem.get("task_type") != "codeforces" else "")
    if link:
        lines.append(f"Link: {link}")
    if w.get("statement"):
        lines.append(f"\nStatement:\n{w['statement']}")
    if w.get("pattern"):
        lines.append(f"\nCore pattern: {w['pattern']}")
    hints = _as_list(w.get("hints"))
    if hints:
        lines.append("\nGraded hints (level 1 = gentle nudge ... level 3 = almost the idea):")
        lines += [f"  Level {i + 1}: {h}" for i, h in enumerate(hints[:3])]
    if w.get("brute_force"):
        lines.append(f"\nBrute force: {w['brute_force']}")
    if w.get("intuition"):
        lines.append(f"\nKey insight: {w['intuition']}")
    steps = _as_list(w.get("approach"))
    if steps:
        lines.append("\nOptimal approach:")
        lines += [f"  {i + 1}. {s}" for i, s in enumerate(steps)]
    if w.get("time_complexity") or w.get("space_complexity"):
        lines.append(f"\nOptimal complexity: time {w.get('time_complexity') or '?'}, space {w.get('space_complexity') or '?'}")
    edges = _as_list(w.get("edge_cases"))
    if edges:
        lines.append("\nEdge cases: " + "; ".join(edges))
    if include_code and w.get("cpp_code"):
        lines.append(f"\nReference C++ solution:\n{w['cpp_code']}")
    elif any(w.get(k) for k in _REDACTED_KEYS):
        lines.append("\n[Reference code redacted.]")
    if len(lines) <= 2:
        lines.append("\n(No stored write-up: rely on your own knowledge of this well-known problem.)")
    return "\n".join(lines)


TUTOR_SYSTEM = """You are a Socratic DSA tutor helping one student work through a single coding problem.
Your goal is that THEY discover the solution. Rules:
- Ask one focused guiding question at a time; build on what the student said.
- When the student describes an approach, evaluate it honestly: say what is right, then point at the gap with a question (a counterexample, a small input to trace, a complexity concern).
- Give hints only when the student asks or is clearly stuck, and escalate gradually: level 1 nudge -> level 2 name the technique/observation -> level 3 almost the full idea. Never jump straight to the full solution.
- NEVER write code, pseudo-code blocks, or the full step-by-step algorithm. No code fences. Short inline names like `left`/`right` are fine.
- If asked directly for the answer or code, decline kindly and offer the next hint instead.
- Check complexity claims precisely (time AND space) and say whether they match the optimal.
- Be warm, concise and concrete. Use Markdown sparingly (bold, short lists). Max 120 words per reply.

The reference material below is for YOUR eyes only. Use it to guide; never paste it."""


ROLE_LABEL = {"user": "Student", "tutor": "Tutor"}


def _clean_messages(raw):
    msgs = []
    for m in raw if isinstance(raw, list) else []:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").lower()
        role = "user" if role in ("user", "student") else "tutor" if role in ("tutor", "assistant", "model") else None
        text = m.get("text") if isinstance(m.get("text"), str) else m.get("content")
        text = text.strip()[:MAX_MSG] if isinstance(text, str) else ""
        if role and text:
            msgs.append({"role": role, "text": text})
    return msgs[-CHAT_TURNS:]


def _strip_code_fences(text):
    """Belt and braces: drop any fenced code block the model emits despite the rules."""
    return re.sub(r"```.*?(```|$)", "_(code omitted — try writing it yourself!)_", text, flags=re.S)


# ---------------- chat (SSE) ----------------
@tutor_bp.route("/<int:log_id>/chat", methods=["POST"])
def chat(log_id):
    data = _body()
    messages = _clean_messages(data.get("messages"))
    if not messages or messages[-1]["role"] != "user":
        return _err("Send at least one student message (the last message must be yours).")
    problem, error = _load_problem(log_id)
    if error:
        return error
    try:
        hint_level = max(0, min(3, int(data.get("hint_level") or 0)))
    except (TypeError, ValueError):
        hint_level = 0

    system = f"{TUTOR_SYSTEM}\n\n---\n{problem_context(problem)}"
    transcript = "\n\n".join(f"{ROLE_LABEL[m['role']]}: {m['text']}" for m in messages)
    prompt = (f"Conversation so far (most recent last):\n\n{transcript}\n\n"
              + (f"The student has asked for hints {hint_level} time(s); if they want a hint now, give level "
                 f"{min(3, hint_level)} at most.\n" if hint_level else "")
              + "Write the tutor's next reply (max 120 words, no code).")

    def generate():
        buf, sent = "", 0
        try:
            for delta in LLMClient(budget=CHAT_BUDGET).stream(prompt, temperature=0.5, system=system, thinking="low"):
                if not delta:
                    continue
                buf += delta
                # Hold back an unfinished fence so we never leak half a code block
                if buf.count("```") % 2 == 1 or buf.endswith("`"):
                    continue
                clean = _strip_code_fences(buf)
                if len(clean) > sent:
                    yield _sse({"type": "delta", "text": clean[sent:]})
                    sent = len(clean)
            clean = _strip_code_fences(buf).strip()
            if not clean:
                raise RuntimeError("Empty response from the model.")
            if len(_strip_code_fences(buf)) > sent:
                yield _sse({"type": "delta", "text": _strip_code_fences(buf)[sent:]})
            yield _sse({"type": "done", "text": clean})
        except Exception as e:
            yield _sse({"type": "error", "message": _friendly(e)})

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------- assess ----------------
def _bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1", "correct")
    return bool(v)


def _str(v, limit=600):
    if v is None:
        return ""
    if isinstance(v, (list, dict)):
        v = json.dumps(v) if isinstance(v, dict) else "; ".join(str(x) for x in v)
    return str(v).strip()[:limit]


def normalize_assessment(raw):
    raw = raw if isinstance(raw, dict) else {}
    try:
        level = int(raw.get("hint_level") or 0)
    except (TypeError, ValueError):
        level = 0
    return {
        "idea_correct": _bool(raw.get("idea_correct")),
        "missing_insight": _str(raw.get("missing_insight")),
        "complexity_ok": _bool(raw.get("complexity_ok")),
        "next_question": _str(raw.get("next_question")),
        "hint_level": max(0, min(3, level)),
    }


@tutor_bp.route("/<int:log_id>/assess", methods=["POST"])
def assess(log_id):
    approach = _body().get("approach")
    approach = approach.strip() if isinstance(approach, str) else ""
    if not approach:
        return _err("Describe your approach first.")
    if len(approach) > MAX_APPROACH:
        return _err(f"Keep the approach under {MAX_APPROACH} characters.")
    problem, error = _load_problem(log_id)
    if error:
        return error
    prompt = f"""{problem_context(problem)}

---
The student's proposed approach:
\"\"\"{approach}\"\"\"

Assess it as a Socratic tutor. Return a JSON object with exactly these keys:
- "idea_correct": true if the core idea would solve the problem correctly (even if not optimal).
- "missing_insight": one sentence naming the gap or mistake WITHOUT giving away the solution ("" if none).
- "complexity_ok": true if their approach (or stated complexity) meets the optimal time and space.
- "next_question": one guiding question to move them forward (never code, never the full answer).
- "hint_level": integer 0-3 — how much help they need next (0 = on track, 3 = needs a near-complete hint)."""
    try:
        raw = LLMClient(budget=ASSESS_BUDGET).generate_json(prompt, temperature=0.3, system=TUTOR_SYSTEM, thinking="low")
    except Exception as e:
        return _err(_friendly(e), 502)
    return jsonify({"status": "success", "data": normalize_assessment(raw)})


# ---------------- review ----------------
def _norm_language(v):
    return _LANG_ALIASES.get(str(v or "cpp").strip().lower())


def review_key(log_id, language, code):
    return hashlib.sha256(f"{log_id}\n{language}\n{code}".encode("utf-8")).hexdigest()


def _int_or_none(v):
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        m = re.search(r"\d+", str(v))
        return int(m.group()) if m else None


def normalize_review(raw):
    raw = raw if isinstance(raw, dict) else {}
    verdict = _str(raw.get("verdict"), 40).lower().replace("_", " ")
    if verdict not in VERDICTS:
        verdict = next((v for v in VERDICTS if v in verdict), "likely correct")
    grade = _str(raw.get("suggested_grade"), 20).lower()
    if grade not in GRADES:
        grade = _VERDICT_GRADE[verdict]
    bugs = []
    for b in raw.get("bugs") if isinstance(raw.get("bugs"), list) else []:
        if isinstance(b, dict) and _str(b.get("issue")):
            bugs.append({"line": _int_or_none(b.get("line")), "issue": _str(b.get("issue"))})
        elif isinstance(b, str) and b.strip():
            bugs.append({"line": None, "issue": b.strip()[:600]})
    cases = []
    for c in raw.get("failing_cases") if isinstance(raw.get("failing_cases"), list) else []:
        if isinstance(c, dict) and (c.get("input") or c.get("why")):
            cases.append({"input": _str(c.get("input"), 400), "expected": _str(c.get("expected"), 300),
                          "why": _str(c.get("why"), 400)})
    cleanups = [_str(c, 400) for c in (raw.get("cleanups") if isinstance(raw.get("cleanups"), list) else []) if _str(c)]
    return {
        "verdict": verdict,
        "summary": _str(raw.get("summary"), 400),
        "time": _str(raw.get("time"), 60),
        "space": _str(raw.get("space"), 60),
        "matches_optimal": _bool(raw.get("matches_optimal")),
        "bugs": bugs[:10],
        "failing_cases": cases[:6],
        "cleanups": cleanups[:8],
        "suggested_grade": grade,
    }


REVIEW_SYSTEM = """You are a meticulous competitive-programming code reviewer. You mentally run the code on tricky inputs,
check bounds, overflow, off-by-one errors, empty inputs and complexity. Be precise and never invent bugs:
if the code is correct, say so. Line numbers refer to the numbered listing you are given."""


@tutor_bp.route("/<int:log_id>/review", methods=["POST"])
def review(log_id):
    data = _body()
    code = data.get("code")
    code = code.replace("\r\n", "\n").rstrip() if isinstance(code, str) else ""
    if not code.strip():
        return _err("Paste your code first.")
    if len(code) > MAX_CODE:
        return _err(f"Code is too long (max {MAX_CODE} characters).")
    language = _norm_language(data.get("language"))
    if not language:
        return _err("language must be one of: cpp, java, python.")
    problem, error = _load_problem(log_id)
    if error:
        return error

    key = review_key(log_id, language, code)
    db = SessionLocal()
    try:
        if not data.get("fresh"):
            hit = (db.query(TutorCache).filter(TutorCache.feature == "review", TutorCache.key == key)
                   .order_by(TutorCache.id.desc()).first())
            if hit:
                try:
                    return jsonify({"status": "success", "data": {**json.loads(hit.payload), "cached": True}})
                except ValueError:
                    pass
    finally:
        db.close()

    numbered = "\n".join(f"{i + 1:>3} | {line}" for i, line in enumerate(code.split("\n")))
    prompt = f"""{problem_context(problem, include_code=True)}

---
The student's {LANGUAGES[language]} solution (numbered lines):
{numbered}

Review it. Return a JSON object with exactly these keys:
- "verdict": one of "correct", "likely correct", "buggy", "wrong approach".
- "summary": one sentence overall assessment.
- "time": the student's code time complexity, e.g. "O(n log n)".
- "space": the student's code extra space complexity, e.g. "O(n)".
- "matches_optimal": true if both complexities match the optimal solution.
- "bugs": array of {{"line": int line number from the listing (or null), "issue": what is wrong and why}}. Empty if none.
- "failing_cases": array of {{"input": a small concrete input, "expected": the correct output, "why": what the code does wrong}}. Empty if none.
- "cleanups": array of short readability / idiom / performance suggestions (max 5).
- "suggested_grade": spaced-repetition grade for this attempt: "again" (wrong approach), "hard" (bugs), "good" (correct), "easy" (correct, optimal and clean on the first go)."""
    try:
        raw = LLMClient(budget=REVIEW_BUDGET).generate_json(prompt, temperature=0.2, system=REVIEW_SYSTEM, thinking="medium")
    except Exception as e:
        return _err(_friendly(e), 502)
    result = normalize_review(raw)

    db = SessionLocal()
    try:
        db.add(TutorCache(feature="review", key=key, payload=json.dumps(result)))
        db.commit()
    except Exception as e:  # caching is best effort
        db.rollback()
        print(f"tutor cache write failed: {e}")
    finally:
        db.close()
    return jsonify({"status": "success", "data": {**result, "cached": False}})
