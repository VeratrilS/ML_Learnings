"""
XP and Ippo-themed ranks, computed on the fly from existing data (no table of its own).

GET /api/xp -> {xp, rank, next_rank, progress, xp_to_next, breakdown, today_xp, ranks}

Every source is optional: a module or table that doesn't exist yet simply contributes 0,
so this endpoint never fails because some other feature isn't wired in.
"""
from datetime import timedelta, timezone

from flask import Blueprint, jsonify
from sqlalchemy import func

from api.core.config import now_ist
from api.core.db import SessionLocal
from api.domain.models import NotificationLog

# ---------------- tuning ----------------
LC_XP = {"Easy": 10, "Medium": 20, "Hard": 40}
LC_DEFAULT_XP = 10  # difficulty unknown
CF_BASE_XP = 15  # + rating // 100
REVISION_XP = 5
TOPIC_XP = 8
TODO_XP = 2
EPISODE_XP = 2
LESSON_XP = 6
FOCUS_MINUTES_PER_XP = 10

# A diligent day (2 mediums, an episode, a lesson, a few tasks/topics/reviews, ~2 focus hours)
# is ~80-100 XP, so a steady month lands in A-Class.
RANKS = [
    ("Rookie", 0),
    ("C-Class", 300),
    ("B-Class", 900),
    ("A-Class", 2000),
    ("Japanese Champion", 4000),
    ("OPBF Champion", 7000),
    ("World Champion", 12000),
]

xp_bp = Blueprint("xp", __name__, url_prefix="/api/xp")


def rank_for(xp):
    """Returns (rank_name, next_rank_name|None, progress 0..1, xp_to_next)."""
    idx = 0
    for i, (_, threshold) in enumerate(RANKS):
        if xp >= threshold:
            idx = i
    name, floor = RANKS[idx]
    if idx + 1 >= len(RANKS):
        return name, None, 1.0, 0
    nxt, ceiling = RANKS[idx + 1]
    progress = (xp - floor) / (ceiling - floor)
    return name, nxt, round(max(0.0, min(1.0, progress)), 4), max(0, ceiling - xp)


def _today_bounds_utc():
    """Naive-UTC [start, end) of the current IST calendar day."""
    start_ist = now_ist().replace(hour=0, minute=0, second=0, microsecond=0)
    start = start_ist.astimezone(timezone.utc).replace(tzinfo=None)
    return start, start + timedelta(days=1)


def _safe(db, fn, default):
    """Run one source; a missing table/module (or any DB error) contributes `default`."""
    try:
        return fn()
    except Exception as e:
        try:
            db.rollback()  # Postgres aborts the transaction after an error
        except Exception:
            pass
        print(f"xp source skipped: {e}")
        return default


# ---------------- sources: each returns (count, xp, count_today, xp_today) ----------------
def _completed_logs(db, task_type):
    return db.query(NotificationLog).filter(
        NotificationLog.task_type == task_type,
        NotificationLog.status == "success",
        NotificationLog.is_completed == True,  # noqa: E712
    )


def _in_today(dt, start, end):
    return dt is not None and start <= dt < end


def _leetcode(db, start, end):
    rows = _completed_logs(db, "leetcode").with_entities(NotificationLog.difficulty, NotificationLog.completed_at).all()
    count = xp = c_today = x_today = 0
    for difficulty, completed_at in rows:
        pts = LC_XP.get(difficulty or "", LC_DEFAULT_XP)
        count, xp = count + 1, xp + pts
        if _in_today(completed_at, start, end):
            c_today, x_today = c_today + 1, x_today + pts
    return count, xp, c_today, x_today


def _codeforces(db, start, end):
    rows = _completed_logs(db, "codeforces").with_entities(NotificationLog.difficulty, NotificationLog.completed_at).all()
    count = xp = c_today = x_today = 0
    for rating, completed_at in rows:
        try:
            bonus = int(rating) // 100 if rating else 0
        except (TypeError, ValueError):
            bonus = 0
        pts = CF_BASE_XP + bonus
        count, xp = count + 1, xp + pts
        if _in_today(completed_at, start, end):
            c_today, x_today = c_today + 1, x_today + pts
    return count, xp, c_today, x_today


def _revisions(db, start, end):
    # review_stage counts successful reviews; there is no per-review timestamp, so none count as "today".
    total = (_completed_logs(db, "leetcode")
             .with_entities(func.coalesce(func.sum(NotificationLog.review_stage), 0)).scalar()) or 0
    total = int(total)
    return total, total * REVISION_XP, 0, 0


def _episodes(db, start, end):
    rows = _completed_logs(db, "watch").with_entities(NotificationLog.completed_at).all()
    count = len(rows)
    today = sum(1 for (completed_at,) in rows if _in_today(completed_at, start, end))
    return count, count * EPISODE_XP, today, today * EPISODE_XP


def _done_flag_source(model, per_item, start, end, db):
    rows = db.query(model.done_at).filter(model.done == True).all()  # noqa: E712
    count = len(rows)
    today = sum(1 for (done_at,) in rows if _in_today(done_at, start, end))
    return count, count * per_item, today, today * per_item


def _todos(db, start, end):
    from api.domain.todos import Todo
    return _done_flag_source(Todo, TODO_XP, start, end, db)


def _syllabus(db, start, end):
    from api.domain.syllabus import SyllabusTopic
    return _done_flag_source(SyllabusTopic, TOPIC_XP, start, end, db)


def _lessons(db, start, end):
    from api.domain.learning import Lesson
    return _done_flag_source(Lesson, LESSON_XP, start, end, db)


_FOCUS_MINUTE_COLS = ("minutes", "duration_minutes")
_FOCUS_SECOND_COLS = ("seconds", "duration_seconds")
_FOCUS_TIME_COLS = ("ended_at", "completed_at", "started_at", "created_at")


def _focus_model():
    """Finds the focus-session model in api.domain.focus, whatever it ends up being called."""
    import api.domain.focus as focus
    for value in vars(focus).values():
        table = getattr(value, "__table__", None)
        if table is None:
            continue
        cols = set(table.columns.keys())
        if cols & set(_FOCUS_MINUTE_COLS + _FOCUS_SECOND_COLS):
            return value, cols
    raise LookupError("no focus session model")


def _focus(db, start, end):
    model, cols = _focus_model()
    minute_col = next((c for c in _FOCUS_MINUTE_COLS if c in cols), None)
    col = minute_col or next(c for c in _FOCUS_SECOND_COLS if c in cols)
    scale = 1 if minute_col else 60
    time_col = next((c for c in _FOCUS_TIME_COLS if c in cols), None)
    fields = [getattr(model, col)] + ([getattr(model, time_col)] if time_col else [])
    total = today = 0.0
    for row in db.query(*fields).all():
        amount = (row[0] or 0) / scale
        total += amount
        if time_col and _in_today(row[1], start, end):
            today += amount
    total, today = int(total), int(today)
    return total, total // FOCUS_MINUTES_PER_XP, today, today // FOCUS_MINUTES_PER_XP


def _speedruns(db, start, end):
    from api.domain.speedrun import SpeedrunSession
    rows = db.query(SpeedrunSession.xp_earned, SpeedrunSession.created_at).all()
    count = len(rows)
    xp = sum(r[0] or 0 for r in rows)
    today_rows = [r for r in rows if _in_today(r[1], start, end)]
    return count, xp, len(today_rows), sum(r[0] or 0 for r in today_rows)


def _duels(db, start, end):
    from api.domain.arena import DuelMatch
    rows = db.query(DuelMatch.xp_awarded, DuelMatch.created_at).all()
    count = len(rows)
    xp = sum(r[0] or 0 for r in rows)
    today_rows = [r for r in rows if _in_today(r[1], start, end)]
    return count, xp, len(today_rows), sum(r[0] or 0 for r in today_rows)


def _bounties(db, start, end):
    from api.domain.bounties import BountyClaim
    rows = db.query(BountyClaim.xp_awarded, BountyClaim.created_at).all()
    count = len(rows)
    xp = sum(r[0] or 0 for r in rows)
    today_rows = [r for r in rows if _in_today(r[1], start, end)]
    return count, xp, len(today_rows), sum(r[0] or 0 for r in today_rows)


def _hotseats(db, start, end):
    from api.domain.hotseat import HotSeatSession
    rows = db.query(HotSeatSession.xp_awarded, HotSeatSession.created_at).all()
    count = len(rows)
    xp = sum(r[0] or 0 for r in rows)
    today_rows = [r for r in rows if _in_today(r[1], start, end)]
    return count, xp, len(today_rows), sum(r[0] or 0 for r in today_rows)


SOURCES = [
    ("leetcode", "LeetCode solved", _leetcode),
    ("codeforces", "Codeforces solved", _codeforces),
    ("revisions", "Revisions done", _revisions),
    ("syllabus", "Syllabus topics", _syllabus),
    ("todos", "Plan tasks done", _todos),
    ("episodes", "Episodes watched", _episodes),
    ("lessons", "Lessons done", _lessons),
    ("focus", "Focus minutes", _focus),
    ("speedrun", "Focus speedruns", _speedruns),
    ("duels", "Arena duels", _duels),
    ("bounties", "Daily bounties", _bounties),
    ("hotseat", "Hot Seat defenses", _hotseats),
]


def compute_xp(db):
    start, end = _today_bounds_utc()
    breakdown, total, today_total = {}, 0, 0
    for key, label, fn in SOURCES:
        count, xp, c_today, x_today = _safe(db, lambda fn=fn: fn(db, start, end), (0, 0, 0, 0))
        breakdown[key] = {"label": label, "count": count, "xp": xp, "today": x_today, "count_today": c_today}
        total += xp
        today_total += x_today
    rank, next_rank, progress, to_next = rank_for(total)
    return {
        "xp": total,
        "rank": rank,
        "next_rank": next_rank,
        "progress": progress,
        "xp_to_next": to_next,
        "breakdown": breakdown,
        "today_xp": today_total,
        "ranks": [{"name": n, "xp": t} for n, t in RANKS],
    }


@xp_bp.route("", methods=["GET"], strict_slashes=False)
def get_xp():
    db = SessionLocal()
    try:
        return jsonify({"status": "success", "data": compute_xp(db)})
    finally:
        db.close()
