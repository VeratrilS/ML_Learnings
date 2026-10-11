"""
Focus sessions + consistency maths.

- FocusSession: every Pomodoro the timer finishes (or abandons after >= 5 min) is stored server-side,
  so "minutes focused" survives across devices and shows up on the heatmap.
- compute_streak / suggest_goal: pure functions used by /api/stats. Streak freezes are derived
  deterministically from history (no cron): walk the days, earn a freeze per 7 consecutive active
  days (max 2 banked), and let a missed day spend one instead of breaking the streak.
"""
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Boolean, Column, DateTime, Integer, String

from api.core.config import now_ist, to_ist
from api.core.db import Base, SessionLocal, engine

MAX_LABEL = 200
MAX_MINUTES = 600
MAX_DAYS = 366
FREEZE_EVERY = 7   # consecutive active days per freeze earned
MAX_FREEZES = 2    # freezes that can be banked
GOAL_WINDOW = 21   # days of history behind the suggested goal
GOAL_DECAY = 0.9   # weight of a day = GOAL_DECAY ** age_in_days
GOAL_PERCENTILE = 0.3
GOAL_MIN, GOAL_MAX = 1, 6


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FocusSession(Base):
    __tablename__ = "focus_sessions"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, nullable=False, index=True)  # naive UTC
    minutes = Column(Integer, nullable=False)
    completed = Column(Boolean, default=True, nullable=False)
    label = Column(String(MAX_LABEL), nullable=True)
    created_at = Column(DateTime, default=_utcnow)  # naive UTC

    def __repr__(self):
        return f"<FocusSession(id={self.id}, minutes={self.minutes}, completed={self.completed})>"


focus_bp = Blueprint("focus", __name__, url_prefix="/api/focus")


@focus_bp.record_once
def _ensure_table(state):
    """Create the table when the blueprint is registered, so wiring it in needs no extra step."""
    try:
        FocusSession.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:  # e.g. a concurrent cold start created it first
        print(f"focus table check skipped: {e}")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _parse_started_at(value):
    """ISO string (any offset, 'Z' ok) -> naive UTC, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _serialize(s):
    return {"id": s.id, "started_at": _iso(s.started_at), "minutes": s.minutes, "completed": bool(s.completed),
            "label": s.label, "date": to_ist(s.started_at).date().isoformat()}


def focus_minutes_by_day(db, since_utc=None):
    """{IST date: minutes} across all focus sessions (completed or not). {} if the table is missing."""
    try:
        q = db.query(FocusSession.started_at, FocusSession.minutes)
        if since_utc is not None:
            q = q.filter(FocusSession.started_at >= since_utc)
        out = {}
        for started_at, minutes in q.all():
            day = to_ist(started_at).date()
            out[day] = out.get(day, 0) + (minutes or 0)
        return out
    except Exception as e:
        db.rollback()  # Postgres aborts the transaction on a missing table
        print(f"focus minutes unavailable: {e}")
        return {}


# ---------------- routes ----------------
@focus_bp.route("", methods=["POST"])
def create_session():
    data = request.get_json(silent=True)
    data = data if isinstance(data, dict) else {}
    try:
        minutes = int(data.get("minutes"))
    except (TypeError, ValueError):
        return _err("minutes must be a whole number.")
    if not 1 <= minutes <= MAX_MINUTES:
        return _err(f"minutes must be between 1 and {MAX_MINUTES}.")
    label = data.get("label")
    label = (label.strip()[:MAX_LABEL] or None) if isinstance(label, str) else None
    started_at = _parse_started_at(data.get("started_at")) or (_utcnow() - timedelta(minutes=minutes))
    db = SessionLocal()
    try:
        s = FocusSession(started_at=started_at, minutes=minutes, completed=bool(data.get("completed", True)), label=label)
        db.add(s)
        db.commit()
        db.refresh(s)
        today = now_ist().date()
        today_minutes = focus_minutes_by_day(db, _utcnow() - timedelta(days=2)).get(today, 0)
        return jsonify({"status": "success", "data": _serialize(s), "today_minutes": today_minutes})
    finally:
        db.close()


@focus_bp.route("", methods=["GET"])
def list_sessions():
    try:
        days = int(request.args.get("days", 30))
    except ValueError:
        return _err("days must be a whole number.")
    days = max(1, min(MAX_DAYS, days))
    today = now_ist().date()
    first = today - timedelta(days=days - 1)
    # Start of the first IST day, as naive UTC
    since = datetime(first.year, first.month, first.day, tzinfo=now_ist().tzinfo).astimezone(timezone.utc).replace(tzinfo=None)
    db = SessionLocal()
    try:
        rows = (db.query(FocusSession).filter(FocusSession.started_at >= since)
                .order_by(FocusSession.started_at.desc(), FocusSession.id.desc()).all())
        per_day = {}
        for s in rows:
            d = to_ist(s.started_at).date()
            per_day[d] = per_day.get(d, 0) + s.minutes
        today_rows = [s for s in rows if to_ist(s.started_at).date() == today]
        return jsonify({
            "status": "success",
            "data": [_serialize(s) for s in rows],
            "per_day": [{"date": (first + timedelta(days=i)).isoformat(), "minutes": per_day.get(first + timedelta(days=i), 0)}
                        for i in range(days)],
            "today_minutes": per_day.get(today, 0),
            "today_sessions": sum(1 for s in today_rows if s.completed),
            "total_minutes": sum(per_day.values()),
        })
    finally:
        db.close()


# ---------------- streaks & goals (pure) ----------------
def compute_streak(active_days, rest_days, today):
    """Walk every day from the first activity to `today`.

    - active day: streak +1; every FREEZE_EVERY consecutive active days bank a freeze (max MAX_FREEZES)
    - rest day (e.g. an exam) without activity: neither breaks nor extends the streak
    - missed day: spends a banked freeze if there's a streak to protect, else the streak resets
    - today without activity yet: pending, never breaks the streak
    Returns {streak, best_streak, freezes_available, frozen_days}.
    """
    active = set(active_days)
    rest = set(rest_days)
    past = [d for d in active if d <= today]
    result = {"streak": 0, "best_streak": 0, "freezes_available": 0, "frozen_days": []}
    if not past:
        return result
    streak = best = run = bank = 0
    frozen = []
    d = min(past)
    while d <= today:
        if d in active:
            streak += 1
            run += 1
            if run % FREEZE_EVERY == 0:
                bank = min(MAX_FREEZES, bank + 1)
            best = max(best, streak)
        elif d in rest or d == today:
            pass
        elif streak and bank:
            bank -= 1
            frozen.append(d)
            run = 0  # a frozen day isn't activity: earning starts over
        else:
            streak = run = 0
        d += timedelta(days=1)
    return {"streak": streak, "best_streak": best, "freezes_available": bank,
            "frozen_days": [x.isoformat() for x in frozen]}


def suggest_goal(counts_by_day, today, current_goal, rest_days=()):
    """Weighted 30th percentile of daily solve counts over the last GOAL_WINDOW days (today excluded,
    it isn't over), recent days weighted more. Clamped to [GOAL_MIN, GOAL_MAX]; falls back to the
    current goal when there's no activity in the window."""
    rest = set(rest_days)
    first_active = min((d for d, n in counts_by_day.items() if n), default=None)
    samples = []
    for age in range(1, GOAL_WINDOW + 1):
        d = today - timedelta(days=age)
        if d in rest or first_active is None or d < first_active:
            continue
        samples.append((counts_by_day.get(d, 0), GOAL_DECAY ** (age - 1)))
    if not samples or not any(n for n, _ in samples):
        return int(current_goal)
    samples.sort()
    total = sum(w for _, w in samples)
    acc = 0.0
    value = samples[-1][0]
    for n, w in samples:
        acc += w
        if acc >= GOAL_PERCENTILE * total:
            value = n
            break
    return max(GOAL_MIN, min(GOAL_MAX, int(round(value))))


def theory_exam_days(db):
    """IST exam dates of theory subjects (rest days). Empty if the syllabus table isn't there."""
    try:
        from api.domain.syllabus import Subject
        rows = db.query(Subject.exam_date).filter(Subject.kind == "theory", Subject.exam_date != None).all()  # noqa: E711
        return {r[0] for r in rows if isinstance(r[0], date)}
    except Exception as e:
        db.rollback()
        print(f"rest days unavailable: {e}")
        return set()
