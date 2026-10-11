"""
AI Interview Lab: mock DSA / behavioral / system-design rounds with a Gemini interviewer.

- Question selection is deterministic code (problem bank + curated lists), never the LLM,
  and avoids repeating what was asked in recent sessions of the same mode.
- The interviewer's turns stream over SSE ({type: delta|done|error}); the full reply is
  persisted only once the stream finishes, while the candidate's message is saved up front
  so it survives an LLM failure (the client can then retry with {"retry": true}).
- Ending a session grades the transcript into a rubric JSON. Grading is atomic: if the LLM
  fails the session stays active, so "End" can simply be retried.
"""
import json
import random
import re
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import Column, DateTime, Integer, String, Text

from api.core.clients import LLMClient
from api.core.db import Base, SessionLocal, engine
from api.domain.problem_bank import PROBLEMS

MODES = ("dsa", "behavioral", "system_design")
MAX_REPLY = 6000          # chars per candidate message
PROMPT_TURNS = 14         # recent messages sent to the model (plus the opening)
PROMPT_MSG_CHARS = 1500   # per-message cap inside prompts
REPLY_BUDGET = 75         # seconds; Vercel functions are capped at 300s
OPENING_BUDGET = 40
RUBRIC_BUDGET = 90
RECENT_AVOID = 12         # don't repeat questions from the last N sessions of a mode

VERDICTS = ("strong hire", "hire", "lean hire", "no hire")

# Rubric dimensions per mode: (key, label)
DIMENSIONS = {
    "dsa": [
        ("communication", "Communication"),
        ("problem_solving", "Problem solving"),
        ("correctness", "Correctness"),
        ("complexity_analysis", "Complexity analysis"),
        ("edge_cases", "Edge cases"),
    ],
    "behavioral": [
        ("communication", "Communication"),
        ("structure", "Structure (STAR)"),
        ("specificity", "Specificity"),
        ("impact", "Impact"),
        ("conciseness", "Conciseness"),
    ],
    "system_design": [
        ("communication", "Communication"),
        ("requirements", "Requirements"),
        ("high_level_design", "High-level design"),
        ("scalability", "Scalability"),
        ("trade_offs", "Trade-offs"),
    ],
}

BEHAVIORAL_QUESTIONS = [
    "Tell me about yourself.",
    "Walk me through the project on your resume you are most proud of.",
    "Tell me about a time you had a conflict with a teammate. How did you resolve it?",
    "Tell me about a time you failed. What did you learn?",
    "Describe a situation where you showed leadership without having formal authority.",
    "Why do you want to join our company?",
    "Why should we hire you over other candidates?",
    "Tell me about a time you had to meet a very tight deadline.",
    "Describe a time you received critical feedback. How did you respond?",
    "Tell me about a time you had to learn a new technology quickly.",
    "Describe the most difficult bug you have debugged.",
    "Tell me about a time you disagreed with a senior or a professor.",
    "Give an example of a time you went beyond what was expected of you.",
    "Tell me about a time you made a mistake that affected others.",
    "Describe a time you had to work with someone difficult.",
    "Tell me about a time you had to prioritise between multiple important tasks.",
    "Describe a situation where you took initiative to improve something.",
    "Tell me about a time you had to explain a technical concept to a non-technical person.",
    "Describe a time when a project's requirements changed midway.",
    "Tell me about a decision you made with incomplete information.",
    "Tell me about a time you helped a struggling teammate.",
    "Describe a time you convinced others to adopt your idea.",
    "Tell me about your internship. What was your biggest contribution?",
    "What is your greatest strength, with an example of using it?",
    "What is a real weakness of yours and what are you doing about it?",
    "Where do you see yourself in five years?",
    "Tell me about a time you handled a lot of pressure, e.g. exams and a project together.",
    "Describe a time you took a calculated risk.",
    "Tell me about a time you set a goal and achieved it.",
    "Tell me about a time a team you were part of did not succeed. What was your role?",
    "Why are you interested in a software engineering role rather than higher studies?",
]

SYSTEM_DESIGN_PROMPTS = [
    ("URL shortener", "Design a URL shortening service like bit.ly."),
    ("Rate limiter", "Design a rate limiter for a public API."),
    ("Chat application", "Design a one-to-one and group chat application like WhatsApp."),
    ("News feed", "Design the news feed for a social network like Instagram."),
    ("Notification service", "Design a notification service that sends push, SMS and email notifications."),
    ("Parking lot", "Design a parking lot system (classes, APIs and data model)."),
    ("Food delivery tracking", "Design live order tracking for a food delivery app like Swiggy or Zomato."),
    ("Ride matching", "Design the rider-driver matching service for a ride-hailing app like Ola or Uber."),
    ("Movie ticket booking", "Design a movie ticket booking system like BookMyShow, handling concurrent seat booking."),
    ("Pastebin", "Design a text sharing service like Pastebin."),
    ("Typeahead search", "Design search autocomplete (typeahead) for an e-commerce site."),
    ("Distributed cache", "Design a distributed key-value cache like Redis/Memcached."),
    ("Online judge", "Design an online coding judge like LeetCode that runs user submissions."),
    ("File storage", "Design a file storage and sync service like Google Drive."),
    ("Payment wallet", "Design a digital wallet like Paytm with peer-to-peer transfers."),
]

_INTERVIEWER_BASE = (
    "You are a realistic interviewer at a top Indian product company (think Flipkart, Amazon India, Google Bangalore) "
    "interviewing a final-year CS student during campus placements. Speak natural, polite Indian-English. "
    "Write ONLY your next turn as the interviewer: at most 90 words, one or two questions at a time, no headings, "
    "no praise inflation, no role labels. Markdown and `inline code` are fine. Never break character. "
)

SYSTEM_PROMPTS = {
    "dsa": _INTERVIEWER_BASE + (
        "This is a 45-minute DSA round on the problem: {title}. "
        "NEVER give the solution, the optimal idea, pseudo-code or code, even if asked directly; politely decline and nudge instead. "
        "Drive the round in order: clarifying questions -> brute force -> optimal approach -> time and space complexity "
        "-> edge cases -> dry run on a small example -> (if time) code walkthrough. "
        "Probe every claim: ask why it works and to justify complexities. If they jump to an answer, ask how they got there. "
        "Give a hint ONLY if the candidate explicitly asks for one or has been stuck for two consecutive turns; "
        "a hint is one small nudge (e.g. a question about a property of the input), never the approach. "
        "If they paste code, do not fix it; ask pointed questions that expose bugs. "
        "When they have covered everything, or past ~40 minutes, wrap up and tell them they can end the interview for feedback."
    ),
    "behavioral": _INTERVIEWER_BASE + (
        "This is a behavioral / HR round. The current question is: {title} "
        "Evaluate answers using STAR (Situation, Task, Action, Result). Ask ONE follow-up at a time that probes what is missing: "
        "their personal role ('I' vs 'we'), concrete actions, measurable results, what they learned or would do differently. "
        "Never answer for them. After 2-4 follow-ups on a question, move on to a different, related behavioral question. "
        "Past ~25 minutes, wrap up and tell them they can end the interview for feedback."
    ),
    "system_design": _INTERVIEWER_BASE + (
        "This is a fresher-level system design round: {title} "
        "Do NOT design it for them. Guide the flow: functional and non-functional requirements -> rough scale estimates "
        "-> APIs -> data model -> high-level components -> deep dive (database choice, caching, partitioning, queues, consistency) "
        "-> bottlenecks and trade-offs. Ask why for every choice and challenge weak spots with realistic scenarios. "
        "Give a hint only if they explicitly ask or are stuck twice. "
        "Past ~40 minutes, wrap up and tell them they can end the interview for feedback."
    ),
}

DSA_OPENING_SYSTEM = (
    "You are a DSA interviewer at an Indian product company. Present the given LeetCode problem to the candidate "
    "in your own words: a one-line greeting, the task, one small example (input -> output), and key constraints. "
    "Do not name the LeetCode problem or number and do not hint at the approach. End by asking them to think aloud "
    "and ask clarifying questions before solving. At most 140 words, Markdown, no headings."
)

RUBRIC_SYSTEM = (
    "You are a strict, fair hiring-committee reviewer for campus SDE placements in India. Grade ONLY what the candidate "
    "actually said in the transcript; missing steps score low. Scores are integers 1-5 "
    "(1 = absent/poor, 3 = acceptable, 5 = excellent). Output JSON only."
)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


class MockSession(Base):
    __tablename__ = "mock_sessions"

    id = Column(Integer, primary_key=True, index=True)
    mode = Column(String(20), nullable=False, index=True)  # dsa | behavioral | system_design
    title = Column(String(300), nullable=False)
    problem_slug = Column(String(200), nullable=True)
    transcript = Column(Text, nullable=False, default="[]")  # JSON list of {role, text, at}
    rubric = Column(Text, nullable=True)  # JSON, set when the session ends
    status = Column(String(10), nullable=False, default="active")  # active | done
    created_at = Column(DateTime, default=_utcnow)  # naive UTC
    ended_at = Column(DateTime, nullable=True)  # naive UTC

    def __repr__(self):
        return f"<MockSession(id={self.id}, mode={self.mode}, status={self.status}, title={self.title!r})>"


interview_bp = Blueprint("interview", __name__, url_prefix="/api/interview")


@interview_bp.record_once
def _ensure_table(state):
    """Create the table when the blueprint is registered, so wiring it in needs no extra step."""
    try:
        MockSession.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:  # e.g. a concurrent cold start created it first
        print(f"mock_sessions table check skipped: {e}")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _loads(raw, default):
    try:
        value = json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def _transcript(s):
    return _loads(s.transcript, [])


def _rubric(s):
    return _loads(s.rubric, {}) or None


def _msg(role, text):
    return {"role": role, "text": text, "at": _iso(_utcnow())}


def _problem(slug):
    return next((p for p in PROBLEMS if p[1] == slug), None)


def _elapsed_min(s):
    return max(0, int((_utcnow() - (s.created_at or _utcnow())).total_seconds() // 60))


def _summary(s):
    transcript = _transcript(s)
    rubric = _rubric(s)
    return {
        "id": s.id,
        "mode": s.mode,
        "title": s.title,
        "problem_slug": s.problem_slug,
        "status": s.status,
        "created_at": _iso(s.created_at),
        "ended_at": _iso(s.ended_at),
        "turns": sum(1 for m in transcript if m.get("role") == "candidate"),
        "verdict": rubric.get("verdict") if rubric else None,
        "overall": rubric.get("overall") if rubric else None,
    }


def _serialize(s):
    p = _problem(s.problem_slug) if s.problem_slug else None
    return {
        **_summary(s),
        "transcript": _transcript(s),
        "rubric": _rubric(s),
        "problem": {"title": p[0], "slug": p[1], "difficulty": p[2], "topic": p[3], "leetcode_id": p[4],
                    "link": f"https://leetcode.com/problems/{p[1]}/"} if p else None,
        "dimensions": [{"key": k, "label": label} for k, label in DIMENSIONS.get(s.mode, [])],
    }


def _recent_titles(db, mode):
    rows = (db.query(MockSession.title, MockSession.problem_slug)
            .filter(MockSession.mode == mode)
            .order_by(MockSession.id.desc()).limit(RECENT_AVOID).all())
    return {r[0] for r in rows}, {r[1] for r in rows if r[1]}


def _pick(pool, avoid):
    fresh = [x for x in pool if x not in avoid]
    return random.choice(fresh or list(pool))


def _clip(text, n=PROMPT_MSG_CHARS):
    text = (text or "").strip()
    return text if len(text) <= n else text[:n] + " …"


def _render_transcript(transcript):
    """Compact prompt view: the opening message plus the most recent turns."""
    msgs = transcript if len(transcript) <= PROMPT_TURNS + 1 else [transcript[0], None, *transcript[-PROMPT_TURNS:]]
    lines = []
    for m in msgs:
        if m is None:
            lines.append("[... earlier turns omitted ...]")
            continue
        who = "Interviewer" if m.get("role") == "interviewer" else "Candidate"
        lines.append(f"{who}: {_clip(m.get('text'))}")
    return "\n\n".join(lines)


def _sse(payload):
    return f"data: {json.dumps(payload)}\n\n"


_LLM_FRIENDLY = "The AI interviewer is busy right now (free tier). Please retry in a moment."


def _friendly(e):
    msg = str(e)
    if "No API key" in msg:
        return "AI is not configured (set GEMINI_API_KEY)."
    if re.search(r"429|quota|RESOURCE_EXHAUSTED|overloaded|503|UNAVAILABLE|timed? ?out|deadline", msg, re.I):
        return _LLM_FRIENDLY
    return f"Interviewer error: {msg[:300]}"


# ---------------- openings ----------------
def _dsa_opening(problem):
    title, slug, _difficulty, _topic, lc_id = problem
    fallback = (
        f"Hi! Let's get started. Today's problem is **{title}** "
        f"([read it here](https://leetcode.com/problems/{slug}/)). Take a minute to read it, then think aloud: "
        "ask me any clarifying questions first, and then walk me through your approach before writing any code."
    )
    try:
        text = LLMClient(budget=OPENING_BUDGET).generate(
            f"Problem: LeetCode #{lc_id} \"{title}\" (https://leetcode.com/problems/{slug}/).",
            temperature=0.5, system=DSA_OPENING_SYSTEM, thinking="low")
        text = (text or "").strip()
        return text if len(text) > 40 else fallback
    except Exception as e:
        print(f"interview opening fell back to template: {str(e)[:160]}")
        return fallback


def _behavioral_opening(question):
    return (
        "Hi, thanks for joining! This will be a short behavioral round. Please answer with a specific, real example, "
        f"and tell me what *you* did.\n\nLet's begin: **{question}**"
    )


def _system_design_opening(prompt):
    return (
        "Hi! For this round we'll do a system design discussion. Think aloud and treat me as your teammate.\n\n"
        f"**{prompt}**\n\nBefore jumping into components, what requirements would you like to clarify?"
    )


# ---------------- rubric ----------------
def _clamp_score(value):
    try:
        return max(1, min(5, int(round(float(value)))))
    except (TypeError, ValueError):
        return 1


def _verdict_for(overall):
    if overall >= 4.5:
        return "strong hire"
    if overall >= 3.75:
        return "hire"
    if overall >= 3:
        return "lean hire"
    return "no hire"


def _str_list(value, limit):
    if not isinstance(value, list):
        return []
    return [str(x).strip()[:400] for x in value if str(x).strip()][:limit]


def normalize_rubric(raw, mode):
    raw = raw if isinstance(raw, dict) else {}
    inner = raw.get("scores") if isinstance(raw.get("scores"), dict) else {}
    out, scores = {}, []
    for key, label in DIMENSIONS[mode]:
        score = _clamp_score(raw.get(key, inner.get(key)))
        out[key] = score
        scores.append({"key": key, "label": label, "score": score})
    overall = round(sum(s["score"] for s in scores) / len(scores), 2)
    verdict = str(raw.get("verdict") or "").strip().lower()
    out.update({
        "scores": scores,
        "overall": overall,
        "verdict": verdict if verdict in VERDICTS else _verdict_for(overall),
        "strengths": _str_list(raw.get("strengths"), 5),
        "top_fixes": _str_list(raw.get("top_fixes"), 3),
        "model_answer_outline": str(raw.get("model_answer_outline") or "").strip()[:4000],
    })
    return out


def _rubric_prompt(s, transcript):
    keys = ", ".join(f'"{k}": 1-5' for k, _ in DIMENSIONS[s.mode])
    focus = {
        "dsa": "Did they clarify, give brute force then optimal, justify complexity, cover edge cases, dry run? "
               "model_answer_outline: the ideal approach (brute force -> optimal, key insight, complexities, edge cases) as short Markdown bullets.",
        "behavioral": "Judge STAR structure, specificity (real details, 'I' not 'we'), measurable impact, conciseness. "
                      "model_answer_outline: how a strong STAR answer to these questions would be structured, as short Markdown bullets.",
        "system_design": "Judge requirement gathering, sensible high-level design, scaling, and trade-off reasoning. "
                         "model_answer_outline: a strong design (requirements, APIs, data model, components, scaling) as short Markdown bullets.",
    }[s.mode]
    return (
        f"Round: {s.mode.replace('_', ' ')} - {s.title}\n{focus}\n"
        f"Return JSON: {{{keys}, \"verdict\": one of {list(VERDICTS)}, \"strengths\": [2-4 short strings], "
        "\"top_fixes\": [exactly 3 concrete, actionable fixes], \"model_answer_outline\": string}\n\n"
        f"Transcript:\n{_render_transcript(transcript)}"
    )


# ---------------- routes ----------------
@interview_bp.route("", methods=["GET"])
def list_sessions():
    db = SessionLocal()
    try:
        rows = db.query(MockSession).order_by(MockSession.id.desc()).limit(60).all()
        items = [_summary(s) for s in rows]
        by_mode, verdicts = {}, {}
        for s in rows:
            rubric = _rubric(s)
            if s.status != "done" or not rubric:
                continue
            m = by_mode.setdefault(s.mode, {"count": 0, "overall": 0.0, "dims": {}})
            m["count"] += 1
            m["overall"] += float(rubric.get("overall") or 0)
            for key, _label in DIMENSIONS.get(s.mode, []):
                m["dims"][key] = m["dims"].get(key, 0) + _clamp_score(rubric.get(key))
            v = rubric.get("verdict")
            if v:
                verdicts[v] = verdicts.get(v, 0) + 1
        graded = sum(m["count"] for m in by_mode.values())
        total_overall = sum(m["overall"] for m in by_mode.values())
        averages = {
            "graded": graded,
            "overall": round(total_overall / graded, 2) if graded else None,
            "verdicts": verdicts,
            "by_mode": {
                mode: {
                    "count": m["count"],
                    "overall": round(m["overall"] / m["count"], 2),
                    "dims": {k: round(v / m["count"], 2) for k, v in m["dims"].items()},
                } for mode, m in by_mode.items()
            },
        }
        return jsonify({"status": "success", "data": items, "averages": averages})
    finally:
        db.close()


@interview_bp.route("/start", methods=["POST"])
def start_session():
    data = _body()
    mode = data.get("mode")
    if mode not in MODES:
        return _err(f"mode must be one of: {', '.join(MODES)}.")
    slug = data.get("problem_slug")
    if slug is not None and (mode != "dsa" or not isinstance(slug, str) or not _problem(slug.strip())):
        return _err("Unknown problem_slug." if mode == "dsa" else "problem_slug is only valid for DSA rounds.")

    db = SessionLocal()
    try:
        recent_titles, recent_slugs = _recent_titles(db, mode)
        if mode == "dsa":
            if slug:
                problem = _problem(slug.strip())
            else:
                mediums = [p for p in PROBLEMS if p[2] == "Medium"]
                problem = random.choice([p for p in mediums if p[1] not in recent_slugs] or mediums)
            title, problem_slug, opening = problem[0], problem[1], _dsa_opening(problem)
        elif mode == "behavioral":
            question = _pick(BEHAVIORAL_QUESTIONS, recent_titles)
            title, problem_slug, opening = question, None, _behavioral_opening(question)
        else:
            name, prompt = _pick(SYSTEM_DESIGN_PROMPTS, {p for p in SYSTEM_DESIGN_PROMPTS if p[0] in recent_titles})
            title, problem_slug, opening = name, None, _system_design_opening(prompt)

        s = MockSession(mode=mode, title=title[:300], problem_slug=problem_slug, status="active",
                        transcript=json.dumps([_msg("interviewer", opening)]))
        db.add(s)
        db.commit()
        db.refresh(s)
        return jsonify({"status": "success", "data": _serialize(s)})
    finally:
        db.close()


@interview_bp.route("/<int:session_id>", methods=["GET", "DELETE"])
def session_detail(session_id):
    db = SessionLocal()
    try:
        s = db.get(MockSession, session_id)
        if not s:
            return _err("Session not found.", 404)
        if request.method == "DELETE":
            db.delete(s)
            db.commit()
            return jsonify({"status": "success"})
        return jsonify({"status": "success", "data": _serialize(s)})
    finally:
        db.close()


def _system_prompt(s):
    title = s.title
    if s.mode == "system_design":
        title = next((p for n, p in SYSTEM_DESIGN_PROMPTS if n == s.title), s.title)
    return SYSTEM_PROMPTS[s.mode].format(title=title)


@interview_bp.route("/<int:session_id>/reply", methods=["POST"])
def reply(session_id):
    data = _body()
    retry = data.get("retry") is True
    text = data.get("text")
    text = text.strip() if isinstance(text, str) else ""
    if not retry and not text:
        return _err("Reply can't be empty.")
    if len(text) > MAX_REPLY:
        return _err(f"Reply must be at most {MAX_REPLY} characters.")

    db = SessionLocal()
    try:
        s = db.get(MockSession, session_id)
        if not s:
            return _err("Session not found.", 404)
        if s.status != "active":
            return _err("This interview has ended.", 409)
        transcript = _transcript(s)
        if retry:
            if not transcript or transcript[-1].get("role") != "candidate":
                return _err("Nothing to retry.", 409)
        else:
            transcript.append(_msg("candidate", text))
            s.transcript = json.dumps(transcript)
            db.commit()  # saved before the LLM call, so a failure never loses the answer
        system = _system_prompt(s)
        elapsed = _elapsed_min(s)
        prompt = (f"Elapsed: {elapsed} min.\n\nTranscript so far:\n{_render_transcript(transcript)}\n\n"
                  "Write the interviewer's next turn.")
    finally:
        db.close()

    def generate():
        parts = []
        try:
            for delta in LLMClient(budget=REPLY_BUDGET).stream(prompt, temperature=0.6, system=system, thinking="low"):
                if delta:
                    parts.append(delta)
                    yield _sse({"type": "delta", "text": delta})
            full = "".join(parts).strip()
            if not full:
                raise RuntimeError("Empty response from the model.")
        except Exception as e:
            yield _sse({"type": "error", "message": _friendly(e)})
            return

        msg = _msg("interviewer", full)
        db2 = SessionLocal()
        try:
            s2 = db2.get(MockSession, session_id)
            if s2 is not None:
                t2 = _transcript(s2)
                t2.append(msg)
                s2.transcript = json.dumps(t2)
                db2.commit()
        except Exception as e:
            db2.rollback()
            yield _sse({"type": "error", "message": f"Couldn't save the reply: {str(e)[:200]}"})
            return
        finally:
            db2.close()
        yield _sse({"type": "done", "message": msg})

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@interview_bp.route("/<int:session_id>/end", methods=["POST"])
def end_session(session_id):
    db = SessionLocal()
    try:
        s = db.get(MockSession, session_id)
        if not s:
            return _err("Session not found.", 404)
        if s.status == "done":
            return jsonify({"status": "success", "data": _serialize(s)})  # idempotent

        transcript = _transcript(s)
        if not any(m.get("role") == "candidate" for m in transcript):
            # Nothing to grade: close it without a rubric so it doesn't skew the averages
            s.status, s.ended_at = "done", _utcnow()
            db.commit()
            db.refresh(s)
            return jsonify({"status": "success", "data": _serialize(s)})

        try:
            raw = LLMClient(budget=RUBRIC_BUDGET).generate_json(
                _rubric_prompt(s, transcript), temperature=0.3, system=RUBRIC_SYSTEM, thinking="low")
        except Exception as e:
            return _err(_friendly(e) + " Your interview is saved; try ending it again.", 502)

        s.rubric = json.dumps(normalize_rubric(raw, s.mode))
        s.status, s.ended_at = "done", _utcnow()
        db.commit()
        db.refresh(s)
        return jsonify({"status": "success", "data": _serialize(s)})
    finally:
        db.close()
