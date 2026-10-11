"""
AI Daily Brief: one short, opinionated plan for today.

The app already computes every number that matters (exam readiness and hours, due reviews, streak,
weakest topic, next lesson, ...). Here we only *gather* those aggregates through our own endpoints,
hand them to the LLM to narrate and schedule, and validate what comes back. The LLM never recomputes
anything. If it fails (free tier overloaded, bad JSON, no key) we build a deterministic brief from the
same context, so the card always has something useful.

One brief per IST day, cached in `daily_briefs`.
"""
import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, has_request_context, jsonify, request
from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, Text
from sqlalchemy.exc import IntegrityError

from api.core.clients import LLMClient
from api.core.config import IST, now_ist
from api.core.db import Base, SessionLocal, engine

KINDS = ("exam", "dsa", "review", "video", "plan", "rest", "episode")
REF_TYPES = ("subject", "topic", "problem", "review", "lesson", "episode", "todo", "contest")
MIN_MINUTES, MAX_MINUTES = 10, 180
MIN_BLOCKS, MAX_BLOCKS = 5, 8
DAY_END = 24 * 60 - 1          # last minute of the day
EARLIEST_START = 7 * 60        # a brief made at night / before dawn plans from 07:00
PAST_GRACE = 30                # minutes an AI block may start before "now"
LLM_BUDGET = 60
CONTEXT_CHAR_CAP = 9000        # ~2.5k tokens
HEADLINE_MAX, WHY_MAX, TITLE_MAX = 90, 80, 120


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DailyBrief(Base):
    __tablename__ = "daily_briefs"

    id = Column(Integer, primary_key=True, index=True)
    day = Column(Date, nullable=False, unique=True, index=True)  # IST date
    payload = Column(Text, nullable=False)                         # JSON: headline, summary, blocks, ...
    model = Column(String(80), nullable=True)
    ai = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_utcnow)                 # naive UTC

    def __repr__(self):
        return f"<DailyBrief(day={self.day}, ai={self.ai})>"


brief_bp = Blueprint("brief", __name__, url_prefix="/api/brief")


@brief_bp.record_once
def _ensure_table(state):
    try:
        DailyBrief.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:  # a concurrent cold start created it first
        print(f"daily_briefs table check skipped: {e}")


# ---------------- small helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _clip(value, n):
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    if len(text) <= n:
        return text
    cut = text[:n - 1]
    if " " in cut[n // 2:]:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:-") + "…"


def _hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _parse_hhmm(value):
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return h * 60 + mi if 0 <= h < 24 and 0 <= mi < 60 else None


def _minute_of_day(now):
    return now.hour * 60 + now.minute


def plan_start(now):
    """First minute the plan may use: now rounded up to 5 min, never before 07:00."""
    m = _minute_of_day(now)
    m = int(math.ceil(m / 5.0) * 5)
    return min(max(m, EARLIEST_START), DAY_END)


def _pct(x):
    try:
        return None if x is None else round(float(x) * 100)
    except (TypeError, ValueError):
        return None


def _data(body):
    return body.get("data") if isinstance(body, dict) else None


# ---------------- context ----------------
def _internal_headers():
    key = request.headers.get("X-App-Key", "") if has_request_context() else ""
    if not key:  # cron calls arrive without a key: sign the internal calls ourselves
        passcode = os.getenv("APP_PASSCODE", "")
        key = hashlib.sha256(f"daily:{passcode}".encode()).hexdigest() if passcode else ""
    return {"X-App-Key": key} if key else {}


def make_fetcher(app=None):
    """GET our own endpoints in-process, so the brief always matches the dashboard. Never raises."""
    app = app or current_app._get_current_object()
    client = app.test_client()
    headers = _internal_headers()

    def fetch(path):
        try:
            res = client.get(path, headers=headers)
            if res.status_code != 200:
                return None
            body = res.get_json(silent=True)
            return body if isinstance(body, dict) and body.get("status") != "error" else None
        except Exception as e:
            print(f"brief: {path} failed: {e}")
            return None
    return fetch


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception as e:
        print(f"brief: context part {fn.__name__} skipped: {e}")
        return None


def _ctx_stats(fetch, now):
    st = _data(fetch("/api/stats"))
    if not isinstance(st, dict):
        return None
    t = st.get("today") or {}
    return {"streak": st.get("streak"), "best_streak": st.get("best_streak"),
            "freezes_available": st.get("freezes_available"),
            "solved_today": t.get("solved"), "goal": t.get("goal"),
            "focus_minutes_today": st.get("focus_minutes_today"), "watch_streak": st.get("watch_streak"),
            "rest_day": now.date().isoformat() in (st.get("rest_days") or [])}


def _ctx_todos(fetch, now):
    items = _data(fetch("/api/todos"))
    if not isinstance(items, list):
        return None
    open_ = [t for t in items if not t.get("done")]
    return {"open": [{"id": t.get("id"), "text": _clip(t.get("text"), 80), **({"carried": True} if t.get("carried") else {})}
                     for t in open_[:8]],
            "done": len(items) - len(open_), "total": len(items)}


def _ctx_reviews(fetch, now):
    body = fetch("/api/reviews")
    items = _data(body)
    if not isinstance(items, list):
        return None
    return {"due_count": body.get("due_count", len(items)), "week_count": body.get("week_count"),
            "top": [{"id": r.get("id"), "title": _clip(r.get("title"), 60), "difficulty": r.get("difficulty"),
                     "recall_pct": _pct(r.get("recall"))} for r in items[:3]]}


def _ctx_pending(fetch, now):
    items = _data(fetch("/api/logs?type=leetcode"))
    if not isinstance(items, list):
        return None
    pending = [p for p in items if not p.get("is_completed")]
    return {"count": len(pending),
            "top": [{"id": p.get("id"), "title": _clip(p.get("title"), 60), "difficulty": p.get("difficulty"),
                     **({"topic": _clip(p.get("topic"), 40)} if p.get("topic") else {})} for p in pending[:5]]}


def _ctx_contests(fetch, now):
    items = _data(fetch("/api/contests"))
    if not isinstance(items, list):
        return None
    out = []
    for c in items:
        try:
            start = datetime.fromisoformat(str(c["start"]).replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError):
            continue
        hours = (start - now).total_seconds() / 3600
        if hours <= 36:
            local = start.astimezone(IST)
            out.append({"id": c.get("id") or _clip(c.get("name"), 60), "name": _clip(c.get("name"), 60),
                        "platform": c.get("platform"), "start_ist": local.strftime("%a %H:%M"),
                        "today": local.date() == now.date(), "running": bool(c.get("running")),
                        "minutes": round((c.get("duration_seconds") or 0) / 60) or None})
    return out[:4]


def _ctx_exams(fetch, now):
    body = fetch("/api/insights/study")
    if isinstance(body, dict) and isinstance(body.get("subjects"), list):
        plan = body.get("plan") or {}
        subjects = []
        for s in body["subjects"]:
            d = s.get("days_left")
            if d is None or d < 0:
                continue
            subjects.append({"id": s.get("id"), "short": s.get("short") or _clip(s.get("name"), 30),
                             "days_left": d, "readiness_now_pct": _pct(s.get("readiness_now")),
                             "readiness_exam_pct": _pct(s.get("readiness_exam")),
                             "hours_today": s.get("hours_today"), "pending_topics": s.get("pending"),
                             "p_finish_pct": _pct(s.get("p_finish")),
                             "study_next": [{"topic_id": t.get("topic_id"), "title": _clip(t.get("title"), 60),
                                             "minutes": t.get("minutes")} for t in (s.get("study_next") or [])[:3]]})
        out = {"plan": {k: plan.get(k) for k in ("hours", "dsa_hours", "study_hours", "feasible", "shortfall_hours")},
               "subjects": subjects[:5]}
        if body.get("empty_reason"):
            out["empty_reason"] = body["empty_reason"]
        return out
    syl = fetch("/api/syllabus")  # older deploys: at least the next exam date
    nxt = syl.get("next_exam") if isinstance(syl, dict) else None
    if nxt:
        return {"subjects": [{"id": nxt.get("id"), "short": nxt.get("short") or nxt.get("subject"),
                              "days_left": nxt.get("days_left")}]}
    return None


def _ctx_skills(fetch, now):
    body = fetch("/api/insights/summary")  # no network calls, unlike /api/insights/skills
    if not isinstance(body, dict):
        return None
    out = {"weakest_topic": body.get("weakest_topic"), "recommended_topic": body.get("recommended_topic")}
    if body.get("cf_rating"):
        out["cf_rating"] = body["cf_rating"]
    return out if any(out.values()) else None


def _ctx_learning(fetch, now):
    data = _data(fetch("/api/learning"))
    if not isinstance(data, dict):
        return None
    courses = data.get("courses") or []
    course = next((c for c in courses if c.get("is_active") and (c.get("today") or {}).get("lesson")), None) \
        or next((c for c in courses if (c.get("today") or {}).get("lesson")), None)
    out = {"done_today": data.get("done_today"), "daily_min": data.get("daily_min"), "streak": data.get("streak")}
    if course:
        lesson = course["today"]["lesson"]
        out.update(course=_clip(course.get("title"), 60), progress_pct=course.get("progress"),
                   lessons_left=(course.get("total") or 0) - (course.get("done") or 0),
                   next_lesson={"id": lesson.get("id"), "title": _clip(lesson.get("title"), 70),
                                "duration": lesson.get("duration"),
                                "minutes": round((lesson.get("seconds") or 0) / 60) or None})
    return out


def _ctx_episode(fetch, now):
    items = _data(fetch("/api/watch"))
    if not isinstance(items, list):
        return None
    s = next((x for x in items if x.get("is_active")), None)
    if not s:
        return None
    return {"series_id": s.get("id"), "title": _clip(s.get("title"), 60), "episode": s.get("next_episode"),
            "total": s.get("total_episodes"), "watched_today": bool(s.get("watched_today")),
            "finished": bool(s.get("finished"))}


def _ctx_journal(fetch, now):
    body = fetch("/api/journal/today")
    if not isinstance(body, dict):
        return None

    def pick(e, keys):
        if not isinstance(e, dict):
            return None
        out = {k: (_clip(e.get(k), 100) if isinstance(e.get(k), str) else e.get(k)) for k in keys}
        if isinstance(e.get("top3"), list):
            out["top3"] = [_clip(x, 60) for x in e["top3"][:3]]
        out = {k: v for k, v in out.items() if v not in (None, "", [])}
        return out or None
    out = {"yesterday": pick(body.get("yesterday"), ("top3", "blocker", "energy", "mood", "win")),
           "today": pick(body.get("data"), ("top3", "energy", "mood"))}
    return out if any(out.values()) else None


def _ctx_placements(fetch, now):
    body = fetch("/api/placements")
    summary = body.get("summary") if isinstance(body, dict) else None
    if not isinstance(summary, dict):
        return None
    out = {}
    for key in ("upcoming", "deadlines"):
        rows = []
        for a in (summary.get(key) or [])[:3]:
            row = {"company": _clip(a.get("company"), 40), "stage": a.get("stage")}
            if a.get("label"):
                row["label"] = _clip(a.get("label"), 40)
            when = a.get("at") or a.get("deadline")
            if when:
                try:
                    row["when_ist"] = datetime.fromisoformat(str(when).replace("Z", "+00:00")).astimezone(IST).strftime("%a %d %b %H:%M")
                except ValueError:
                    row["when_ist"] = str(when)[:20]
            rows.append(row)
        if rows:
            out[key] = rows
    return out or None


# Order = priority. When the context is too large, the tail goes first.
_SECTIONS = [("stats", _ctx_stats), ("exams", _ctx_exams), ("todos", _ctx_todos), ("reviews", _ctx_reviews),
             ("pending_problems", _ctx_pending), ("contests", _ctx_contests), ("learning", _ctx_learning),
             ("episode", _ctx_episode), ("skills", _ctx_skills), ("journal", _ctx_journal),
             ("placements", _ctx_placements)]


def _size(ctx):
    return len(json.dumps(ctx, separators=(",", ":"), default=str))


def _fit(ctx, cap=CONTEXT_CHAR_CAP):
    """Keep the prompt small: shorten lists, then drop the lowest-priority sections."""
    if _size(ctx) <= cap:
        return ctx
    for path, n in ((("todos", "open"), 4), (("pending_problems", "top"), 3), (("exams", "subjects"), 3),
                    (("reviews", "top"), 2), (("contests",), 2)):
        node = ctx
        for k in path[:-1]:
            node = node.get(k) if isinstance(node, dict) else None
        if isinstance(node, dict) and isinstance(node.get(path[-1]), list):
            node[path[-1]] = node[path[-1]][:n]
        if _size(ctx) <= cap:
            return ctx
    for key, _ in reversed(_SECTIONS):
        if _size(ctx) <= cap:
            break
        ctx.pop(key, None)
    return ctx


def gather_context(fetch, now=None):
    """Compact aggregates for today. Every source is optional; missing endpoints are skipped."""
    now = now or now_ist()
    ctx = {"now_ist": now.strftime("%H:%M"), "date": now.date().isoformat(), "weekday": now.strftime("%A"),
           "plan_from": _hhmm(plan_start(now))}
    for key, fn in _SECTIONS:
        value = _safe(fn, fetch, now)
        if value not in (None, [], {}):
            ctx[key] = value
    return _fit(ctx)


def _ref_ids(ctx):
    """Ids the LLM may reference, per ref type."""
    ids = {t: set() for t in REF_TYPES}

    def add(t, v):
        if v is not None:
            ids[t].add(str(v))
    for t in (ctx.get("todos") or {}).get("open") or []:
        add("todo", t.get("id"))
    for r in (ctx.get("reviews") or {}).get("top") or []:
        add("review", r.get("id"))
        add("problem", r.get("id"))
    for p in (ctx.get("pending_problems") or {}).get("top") or []:
        add("problem", p.get("id"))
    for c in ctx.get("contests") or []:
        add("contest", c.get("id"))
    for s in (ctx.get("exams") or {}).get("subjects") or []:
        add("subject", s.get("id"))
        for t in s.get("study_next") or []:
            add("topic", t.get("topic_id"))
    add("lesson", ((ctx.get("learning") or {}).get("next_lesson") or {}).get("id"))
    add("episode", (ctx.get("episode") or {}).get("series_id"))
    return ids


# ---------------- validation ----------------
def _clean_ref(ref, allowed=None):
    if not isinstance(ref, dict):
        return None
    t = str(ref.get("type") or "").strip().lower()
    rid = ref.get("id")
    if t not in REF_TYPES or rid is None or isinstance(rid, bool) or isinstance(rid, (dict, list)):
        return None
    if isinstance(rid, float) and rid.is_integer():
        rid = int(rid)
    if isinstance(rid, str):
        rid = rid.strip()[:64]
        if rid.isdigit():
            rid = int(rid)
    if rid == "" or (allowed is not None and str(rid) not in allowed.get(t, set())):
        return None
    return {"type": t, "id": rid}


def validate_brief(raw, now=None, ctx=None):
    """Clamp an LLM answer into the schema. Raises ValueError when nothing usable is left."""
    now = now or now_ist()
    if not isinstance(raw, dict):
        raise ValueError("brief is not an object")
    headline = _clip(raw.get("headline"), HEADLINE_MAX)
    summary = _clip(raw.get("summary"), 600)
    if not headline or not summary:
        raise ValueError("headline/summary missing")
    risk = raw.get("risk")
    risk = _clip(risk, 240) if isinstance(risk, str) and risk.strip().lower() not in ("", "null", "none", "n/a") else None
    allowed = _ref_ids(ctx) if ctx is not None else None

    earliest = plan_start(now) - PAST_GRACE
    blocks, last = [], -1
    for b in raw.get("blocks") if isinstance(raw.get("blocks"), list) else []:
        if not isinstance(b, dict):
            continue
        kind = str(b.get("kind") or "").strip().lower()
        start = _parse_hhmm(b.get("start"))
        title = _clip(b.get("title"), TITLE_MAX)
        if kind not in KINDS or start is None or not title or start <= last or start < earliest:
            continue
        try:
            minutes = int(round(float(b.get("minutes"))))
        except (TypeError, ValueError):
            continue
        minutes = max(MIN_MINUTES, min(MAX_MINUTES, minutes))
        minutes = min(minutes, DAY_END + 1 - start)  # never past midnight
        if minutes < MIN_MINUTES:
            continue
        blocks.append({"start": _hhmm(start), "minutes": minutes, "kind": kind, "title": title,
                       "why": _clip(b.get("why"), WHY_MAX), "ref": _clean_ref(b.get("ref"), allowed)})
        last = start
        if len(blocks) == MAX_BLOCKS:
            break
    if not blocks:
        raise ValueError("no valid blocks")
    return {"headline": headline, "summary": summary, "blocks": blocks, "risk": risk,
            "nudge": _clip(raw.get("nudge"), 160)}


# ---------------- LLM ----------------
SYSTEM_PROMPT = """You are Sai's coach. Think Kamogawa from Hajime no Ippo: sharp, blunt, demanding, warm underneath, allergic to fluff. Never cheesy, no motivational-poster lines, no emoji (one at most, better none).
Sai is an Indian CS final-year student juggling: placements (LeetCode handle "Veratril"), end-sem exams, Coder Army System Design lessons (minimum one a day) and one Hajime no Ippo episode a day, which is his reward.

You write today's brief from CONTEXT. The app has already computed every number in it. Quote numbers verbatim; never recompute, estimate or invent numbers, problems, topics, lessons or contests.

Scheduling rules:
- 5 to 8 blocks, start times "HH:MM" (IST, 24h) strictly ascending, first block at or after plan_from, nothing past 23:30. minutes between 10 and 180, realistic gaps between blocks.
- An exam within ~7 days comes first: give each subject its hours_today (split into blocks of at most 120 min) and name the study_next topics.
- DSA: enough to reach the goal (goal minus solved_today) from pending_problems or the weakest topic; protect the streak. Fit contests at their real start time.
- Due reviews get a short "review" block. One System Design lesson ("video") if learning.done_today < daily_min.
- A short "rest" block after a long stretch. The "episode" block is the last block, as the reward (skip it if watched_today or finished).
- Open todos can become "plan" blocks.
- ref points at an id from CONTEXT: {"type": "subject"|"topic"|"problem"|"review"|"lesson"|"episode"|"todo"|"contest", "id": <id>} or null.

Writing rules: second person, plain English an Indian student uses. headline <= 90 chars and specific to today. summary: 2-3 sentences with concrete numbers from CONTEXT. why <= 80 chars. risk: one sentence only when something is genuinely at risk (exam plan infeasible or shortfall_hours > 0, low p_finish, streak at risk, a clash), else null. nudge: one line, Kamogawa energy.
Output JSON only."""

SCHEMA_HINT = """{"headline": str, "summary": str, "blocks": [{"start": "HH:MM", "minutes": int, "kind": "exam"|"dsa"|"review"|"video"|"plan"|"rest"|"episode", "title": str, "why": str, "ref": {"type": str, "id": int|str} | null}], "risk": str | null, "nudge": str}"""


def build_prompt(ctx, now):
    return (f"NOW (IST): {now.strftime('%A %d %B %Y, %H:%M')}. Plan from {ctx.get('plan_from') or _hhmm(plan_start(now))}.\n\n"
            f"CONTEXT:\n{json.dumps(ctx, separators=(',', ':'), ensure_ascii=False, default=str)}\n\n"
            f"Return JSON exactly in this shape:\n{SCHEMA_HINT}")


def generate_ai(ctx, now):
    client = LLMClient(budget=LLM_BUDGET)
    raw = client.generate_json(build_prompt(ctx, now), temperature=0.6, system=SYSTEM_PROMPT, thinking="low")
    return validate_brief(raw, now, ctx)


# ---------------- deterministic fallback ----------------
NUDGES = [
    "Hard work betrays none. Start the first block on time.",
    "Footwork first: open the first block before you open your phone.",
    "Jab, jab, straight. Small reps done daily become a weapon.",
    "Don't think about the whole fight. Win this round.",
    "Rest is training too. Sleep on time tonight.",
    "Nobody gets stronger watching. Get in the ring.",
    "Guard up, chin down. One block at a time.",
]


def _round5(m):
    return int(5 * round(m / 5.0))


def fallback_brief(ctx, now=None):
    now = now or now_ist()
    stats = ctx.get("stats") or {}
    exams = [s for s in (ctx.get("exams") or {}).get("subjects") or [] if (s.get("days_left") or 0) >= 0]
    plan = (ctx.get("exams") or {}).get("plan") or {}
    reviews = ctx.get("reviews") or {}
    pending = ctx.get("pending_problems") or {}
    learning = ctx.get("learning") or {}
    episode = ctx.get("episode") or {}
    skills = ctx.get("skills") or {}
    goal, solved, streak = stats.get("goal"), stats.get("solved_today") or 0, stats.get("streak") or 0

    work = []  # (kind, minutes, title, why, ref)
    study = [s for s in exams if (s.get("hours_today") or 0) > 0]

    def exam_block(s):
        topics = s.get("study_next") or []
        title = f"{s.get('short')}: {topics[0]['title']}" if topics else f"Study {s.get('short')}"
        bits = [f"Exam in {s.get('days_left')}d"]
        if s.get("readiness_now_pct") is not None:
            bits.append(f"readiness {s['readiness_now_pct']}%")
        ref = {"type": "topic", "id": topics[0]["topic_id"]} if topics and topics[0].get("topic_id") is not None \
            else {"type": "subject", "id": s.get("id")}
        return ("exam", max(30, min(120, _round5(s["hours_today"] * 60))), title, " · ".join(bits), ref)

    if study:
        work.append(exam_block(study[0]))
    top = (pending.get("top") or [None])[0]
    if top:
        mins = {"Easy": 30, "Medium": 45, "Hard": 60}.get(top.get("difficulty"), 45)
        why = f"{pending.get('count')} pending" + (f" · {solved}/{goal} solved today" if goal else "")
        work.append(("dsa", mins, f"Solve {top['title']}", why, {"type": "problem", "id": top.get("id")}))
    elif skills.get("weakest_topic") or skills.get("recommended_topic"):
        wt = skills.get("weakest_topic") or {}
        topic = skills.get("recommended_topic") or wt.get("topic")
        why = f"Weakest topic, rating {wt['rating']}" if wt.get("rating") and wt.get("topic") == topic else "Recommended topic"
        work.append(("dsa", 45, f"Practice {topic}", why, None))
    elif goal and solved < goal:
        work.append(("dsa", 45, f"Solve {goal - solved} LeetCode problem{'s' if goal - solved != 1 else ''}",
                     f"{solved}/{goal} solved today", None))
    for s in study[1:2]:
        work.append(exam_block(s))
    due = reviews.get("due_count") or 0
    if due and reviews.get("top"):
        r = reviews["top"][0]
        title = f"Revise {r['title']}" + (f" +{due - 1} more" if due > 1 else "")
        why = f"{due} due" + (f" · recall {r['recall_pct']}%" if r.get("recall_pct") is not None else "")
        work.append(("review", max(15, min(60, 10 * due)), title, why, {"type": "review", "id": r.get("id")}))
    lesson = learning.get("next_lesson")
    if lesson and (learning.get("done_today") or 0) < (learning.get("daily_min") or 1):
        mins = max(20, min(120, _round5((lesson.get("minutes") or 30) * 1.3)))
        why = f"{learning.get('lessons_left')} lessons left" if learning.get("lessons_left") else "One lesson a day, minimum"
        work.append(("video", mins, f"System Design: {lesson['title']}", why, {"type": "lesson", "id": lesson.get("id")}))
    reward = None
    if episode and not episode.get("watched_today") and not episode.get("finished"):
        reward = ("episode", 25, f"{episode.get('title')} · Ep {episode.get('episode')}", "The reward. Only after the work.",
                  {"type": "episode", "id": episode.get("series_id")})

    blocks, cursor, since_rest = [], plan_start(now), 0
    reserve = 35 if reward else 0
    for kind, mins, title, why, ref in work:
        if since_rest >= 100:
            if cursor + 15 + 10 + mins + reserve <= DAY_END - 29:
                blocks.append(("rest", 15, "Walk, water, no phone", "Recover before the next round", None, cursor))
                cursor += 25
                since_rest = 0
        if cursor + mins + reserve > DAY_END - 29:
            continue
        blocks.append((kind, mins, title, why, ref, cursor))
        cursor += mins + 10
        since_rest += mins
    if reward and cursor + 25 <= DAY_END:
        blocks.append((*reward, cursor))
    if not blocks:
        start = min(cursor, DAY_END - 15)
        blocks.append(("rest", 15, "Sleep. Tomorrow's round starts early", "Recovery is training too", None, start))

    # Words: only numbers that are already in the context
    sentences = []
    if exams:
        e = exams[0]
        s = f"{e.get('short')} exam in {e.get('days_left')} day{'s' if e.get('days_left') != 1 else ''}"
        if e.get("readiness_now_pct") is not None:
            s += f" at {e['readiness_now_pct']}% readiness"
        if e.get("hours_today"):
            s += f"; the plan gives it {e['hours_today']}h today"
        sentences.append(s + ".")
    counts = []
    if due:
        counts.append(f"{due} review{'s' if due != 1 else ''} due")
    if pending.get("count"):
        counts.append(f"{pending['count']} problem{'s' if pending['count'] != 1 else ''} pending")
    if goal:
        counts.append(f"{solved}/{goal} solved today")
    if counts:
        line = ", ".join(counts)
        sentences.append(line[0].upper() + line[1:] + ".")
    if lesson:
        sentences.append(f"Next System Design lesson: {lesson['title']}.")
    summary = _clip(" ".join(sentences[:3]) or "No data yet. Pick one problem, one lesson, one episode.", 600)

    if exams and exams[0].get("days_left") is not None and exams[0]["days_left"] <= 7:
        e = exams[0]
        headline = f"{e.get('short')} in {e['days_left']} day{'s' if e['days_left'] != 1 else ''}. Study first, then DSA."
    elif streak:
        headline = f"Streak at {streak}. " + (f"Hit {goal} problems and keep it alive." if goal else "Keep it alive today.")
    else:
        headline = "Fresh start: one problem, one lesson, one episode."

    risk = None
    if plan.get("feasible") is False:
        risk = f"Exam plan is short by {plan.get('shortfall_hours')}h. Cut scope or add study hours."
    elif exams and exams[0].get("p_finish_pct") is not None and exams[0]["p_finish_pct"] < 50:
        risk = f"{exams[0].get('short')}: only {exams[0]['p_finish_pct']}% chance to finish the syllabus at this pace."
    elif streak and goal and solved < goal and now.hour >= 18:
        risk = f"Streak of {streak} at risk: {solved}/{goal} solved today."

    return {
        "headline": _clip(headline, HEADLINE_MAX), "summary": summary, "risk": risk,
        "nudge": NUDGES[now.date().toordinal() % len(NUDGES)],
        "blocks": [{"start": _hhmm(start), "minutes": max(MIN_MINUTES, min(MAX_MINUTES, mins)), "kind": kind,
                    "title": _clip(title, TITLE_MAX), "why": _clip(why, WHY_MAX), "ref": _clean_ref(ref)}
                   for kind, mins, title, why, ref, start in blocks[:MAX_BLOCKS]],
    }


# ---------------- build + persist ----------------
def build_brief(fetch, now=None):
    """Returns (payload, ai, model). Never raises."""
    now = now or now_ist()
    try:
        ctx = gather_context(fetch, now)
    except Exception as e:
        print(f"brief: context failed: {e}")
        ctx = {"now_ist": now.strftime("%H:%M"), "date": now.date().isoformat(), "plan_from": _hhmm(plan_start(now))}
    sources = sorted(k for k in ctx if k not in ("now_ist", "date", "weekday", "plan_from"))
    try:
        payload, ai, model = generate_ai(ctx, now), True, "gemini"
    except Exception as e:
        print(f"brief: LLM failed, using fallback: {str(e)[:200]}")
        payload, ai, model = fallback_brief(ctx, now), False, "fallback"
    payload.update(sources=sources, generated_at=now.strftime("%H:%M"), accepted=[])
    return payload, ai, model


def _today():
    return now_ist().date()


def _get(db, day):
    return db.query(DailyBrief).filter(DailyBrief.day == day).first()


def _save(db, day, payload, ai, model):
    text = json.dumps(payload, ensure_ascii=False)
    row = _get(db, day)
    if row is None:
        row = DailyBrief(day=day, payload=text, ai=ai, model=model, created_at=_utcnow())
        db.add(row)
        try:
            db.commit()
        except IntegrityError:  # a concurrent request saved today's brief first: overwrite it
            db.rollback()
            row = _get(db, day)
    if row.payload != text or row.ai != ai or row.model != model:
        row.payload, row.ai, row.model, row.created_at = text, ai, model, _utcnow()
        db.commit()
    db.refresh(row)
    return row


def _load(row):
    try:
        payload = json.loads(row.payload)
        return payload if isinstance(payload, dict) else {}
    except (TypeError, ValueError):
        return {}


def serialize(row):
    payload = _load(row)
    return {**payload, "day": row.day.isoformat(), "ai": bool(row.ai), "model": row.model,
            "created_at": _iso(row.created_at), "accepted": payload.get("accepted") or []}


def generate_today(db, fetch=None, force=False):
    """Returns (row, cached)."""
    day = _today()
    row = _get(db, day)
    if row and not force:
        return row, True
    payload, ai, model = build_brief(fetch or make_fetcher())
    return _save(db, day, payload, ai, model), False


def generate_brief_for_cron(fetch=None):
    """Make today's brief unless an AI brief already exists (a fallback brief gets retried)."""
    db = SessionLocal()
    try:
        row = _get(db, _today())
        if row and row.ai:
            return {"status": "skipped", "message": "Today's brief already exists."}
        row, _ = generate_today(db, fetch, force=True)
        return {"status": "success", "ai": bool(row.ai), "day": row.day.isoformat()}
    finally:
        db.close()


# ---------------- routes ----------------
@brief_bp.route("", methods=["GET"], strict_slashes=False)
def get_brief():
    """Cached brief only; never blocks on the LLM. The client POSTs when `pending`."""
    db = SessionLocal()
    try:
        row = _get(db, _today())
        if row is None:
            return jsonify({"status": "success", "data": None, "pending": True})
        return jsonify({"status": "success", "data": serialize(row), "pending": False})
    finally:
        db.close()


@brief_bp.route("", methods=["POST"], strict_slashes=False)
def post_brief():
    force = request.args.get("force") in ("1", "true")
    db = SessionLocal()
    try:
        row, cached = generate_today(db, force=force)
        return jsonify({"status": "success", "data": serialize(row), "cached": cached, "pending": False})
    finally:
        db.close()


@brief_bp.route("/cron", methods=["POST"])
def cron_brief():
    return jsonify(generate_brief_for_cron())


def _todo_text(b):
    return _clip(f"{b['start']} · {b['title']} ({b['minutes']}m)", 300)


@brief_bp.route("/accept", methods=["POST"])
def accept_blocks():
    """Body {indices: [...]} (omit for every non-rest block). Adds each block to today's plan once."""
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    indices = body.get("indices")
    if indices is not None and (not isinstance(indices, list)
                                or not all(isinstance(i, int) and not isinstance(i, bool) for i in indices)):
        return _err("indices must be a list of block numbers.")
    db = SessionLocal()
    try:
        row = _get(db, _today())
        if row is None:
            return _err("No brief for today yet.", 404)
        payload = _load(row)
        blocks = payload.get("blocks") or []
        if indices is None:
            indices = [i for i, b in enumerate(blocks) if b.get("kind") != "rest"]
        if any(i < 0 or i >= len(blocks) for i in indices):
            return _err("Unknown block.")
        accepted = set(payload.get("accepted") or [])
        todo = sorted(i for i in set(indices) if i not in accepted)
        client = current_app.test_client()
        headers = _internal_headers()
        created, failed = [], 0
        for i in todo:
            res = client.post("/api/todos", json={"text": _todo_text(blocks[i])}, headers=headers)
            data = res.get_json(silent=True) if res.status_code == 200 else None
            if data and data.get("data"):
                created.append(data["data"])
                accepted.add(i)
            else:
                failed += 1
        if todo and not created:
            return _err("Couldn't add these to your plan.", 502)
        payload["accepted"] = sorted(accepted)
        row.payload = json.dumps(payload, ensure_ascii=False)
        db.commit()
        return jsonify({"status": "success", "data": created, "accepted": payload["accepted"], "failed": failed})
    finally:
        db.close()
