"""
Body habits: sleep, water, exercise, steps and screens-off, one row per IST day.

`sleep_hours` on day D is the sleep that *ended* on the morning of D ("How long did you sleep?"),
so the morning prompt writes today's row and `PUT /api/habits/<YYYY-MM-DD>` lets you backfill.

Body score (0-100) = weighted completion of each target, each capped at 100%:
    sleep 40, water 30, exercise 20, screens-off-on-time 10.
"""
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Integer, DateTime, Boolean, Date, Float, Text
from sqlalchemy.exc import IntegrityError

from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine
from api.domain.models import Settings
from api.domain.repositories import NotificationRepository

MAX_NOTES = 2000
MAX_HISTORY_DAYS = 365
BACKFILL_DAYS = 366

# key -> (settings key, default, min, max, caster)
TARGETS = {
    "sleep": ("habit_sleep_target", 7.5, 3.0, 12.0, float),
    "water": ("habit_water_target", 8, 1, 30, int),
    "exercise": ("habit_exercise_target", 30, 5, 300, int),
}
WEIGHTS = {"sleep": 40, "water": 30, "exercise": 20, "screen_off": 10}
HABITS = ("sleep", "water", "exercise", "screen_off")

# field -> (min, max, caster)
FIELDS = {
    "sleep_hours": (0.0, 24.0, float),
    "water_glasses": (0, 40, int),
    "exercise_min": (0, 1440, int),
    "steps": (0, 200_000, int),
}


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class HabitDay(Base):
    __tablename__ = "habit_days"

    id = Column(Integer, primary_key=True, index=True)
    day = Column(Date, nullable=False, unique=True, index=True)  # IST date
    sleep_hours = Column(Float, nullable=True)  # null = not logged yet
    water_glasses = Column(Integer, default=0, nullable=False)
    exercise_min = Column(Integer, default=0, nullable=False)
    steps = Column(Integer, nullable=True)
    screen_off_on_time = Column(Boolean, nullable=True)  # null = not answered
    notes = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)  # naive UTC

    def __repr__(self):
        return f"<HabitDay(day={self.day}, sleep={self.sleep_hours}, water={self.water_glasses})>"


habits_bp = Blueprint("habits", __name__, url_prefix="/api/habits")


@habits_bp.record_once
def _ensure_table(state):
    """Create the tables when the blueprint is registered, so wiring it in needs no extra step."""
    for table in (Settings.__table__, HabitDay.__table__):
        try:
            table.create(bind=engine, checkfirst=True)
        except Exception as e:  # e.g. a concurrent cold start created it first
            print(f"{table.name} table check skipped: {e}")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _today():
    return now_ist().date()


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def get_targets(db):
    repo = NotificationRepository(db)
    out = {}
    for name, (key, default, lo, hi, cast) in TARGETS.items():
        raw = repo.get_setting(key)
        try:
            value = cast(float(raw)) if raw is not None else default
        except (TypeError, ValueError):
            value = default
        out[name] = min(max(value, lo), hi)
    return out


def _ratio(value, target):
    if not value or not target:
        return 0.0
    return min(float(value) / float(target), 1.0)


def met(row, targets):
    """Which habits hit their target on this row (None row = nothing met)."""
    if row is None:
        return {h: False for h in HABITS}
    return {
        "sleep": row.sleep_hours is not None and row.sleep_hours >= targets["sleep"],
        "water": (row.water_glasses or 0) >= targets["water"],
        "exercise": (row.exercise_min or 0) >= targets["exercise"],
        "screen_off": bool(row.screen_off_on_time),
    }


def body_score(row, targets):
    if row is None:
        return 0
    score = (WEIGHTS["sleep"] * _ratio(row.sleep_hours, targets["sleep"])
             + WEIGHTS["water"] * _ratio(row.water_glasses, targets["water"])
             + WEIGHTS["exercise"] * _ratio(row.exercise_min, targets["exercise"])
             + WEIGHTS["screen_off"] * (1.0 if row.screen_off_on_time else 0.0))
    return max(0, min(100, int(round(score))))


def _serialize(row, day, targets):
    return {
        "day": day.isoformat(),
        "logged": row is not None,
        "sleep_hours": row.sleep_hours if row else None,
        "water_glasses": (row.water_glasses or 0) if row else 0,
        "exercise_min": (row.exercise_min or 0) if row else 0,
        "steps": row.steps if row else None,
        "screen_off_on_time": row.screen_off_on_time if row else None,
        "notes": (row.notes or "") if row else "",
        "updated_at": _iso(row.updated_at) if row else None,
        "score": body_score(row, targets),
        "met": met(row, targets),
    }


def _rows_between(db, start, end):
    rows = db.query(HabitDay).filter(HabitDay.day >= start, HabitDay.day <= end).all()
    return {r.day: r for r in rows}


def streaks(db, today, targets):
    """Consecutive days each habit hit its target, ending today.
    Today not done yet doesn't break the streak (it counts from yesterday)."""
    by_day = _rows_between(db, today - timedelta(days=MAX_HISTORY_DAYS), today)
    out = {}
    for h in HABITS:
        d = today
        if not met(by_day.get(d), targets)[h]:
            d -= timedelta(days=1)
        n = 0
        while d in by_day and met(by_day[d], targets)[h]:
            n += 1
            d -= timedelta(days=1)
        out[h] = n
    return out


def _series(db, end, days, targets):
    start = end - timedelta(days=days - 1)
    by_day = _rows_between(db, start, end)
    return [_serialize(by_day.get(start + timedelta(days=i)), start + timedelta(days=i), targets)
            for i in range(days)]


def _clean(data):
    """Validate a partial update. Returns (changes, error)."""
    changes = {}
    for field, (lo, hi, cast) in FIELDS.items():
        if field not in data:
            continue
        v = data[field]
        if v is None and field in ("sleep_hours", "steps"):
            changes[field] = None
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None, f"{field} must be a number."
        if v != v or v < lo or v > hi:  # NaN or out of range
            return None, f"{field} must be between {lo} and {hi}."
        changes[field] = round(float(v) * 4) / 4 if cast is float else int(round(v))
    if "screen_off_on_time" in data:
        v = data["screen_off_on_time"]
        if v is not None and not isinstance(v, bool):
            return None, "screen_off_on_time must be true, false or null."
        changes["screen_off_on_time"] = v
    if "notes" in data:
        v = data["notes"]
        if v is not None and not isinstance(v, str):
            return None, "notes must be text."
        v = (v or "").strip()
        if len(v) > MAX_NOTES:
            return None, f"notes must be at most {MAX_NOTES} characters."
        changes["notes"] = v or None
    if not changes:
        return None, "Nothing to update."
    return changes, None


def upsert(db, day, changes):
    row = db.query(HabitDay).filter(HabitDay.day == day).first()
    if row is None:
        row = HabitDay(day=day, water_glasses=0, exercise_min=0)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:  # created concurrently: update that one instead
            db.rollback()
            row = db.query(HabitDay).filter(HabitDay.day == day).first()
    for k, v in changes.items():
        setattr(row, k, v)
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return row


def _update(day):
    changes, error = _clean(_body())
    if error:
        return _err(error)
    db = SessionLocal()
    try:
        today = _today()
        if day > today:
            return _err("Can't log habits for a future day.")
        if day < today - timedelta(days=BACKFILL_DAYS):
            return _err("That day is too far back.")
        row = upsert(db, day, changes)
        targets = get_targets(db)
        return jsonify({
            "status": "success",
            "data": _serialize(row, day, targets),
            "targets": targets,
            "streaks": streaks(db, today, targets),
        })
    finally:
        db.close()


# ---------------- routes ----------------
@habits_bp.route("/today", methods=["GET"])
def get_today():
    db = SessionLocal()
    try:
        today = _today()
        targets = get_targets(db)
        history = _series(db, today, 7, targets)
        return jsonify({
            "status": "success",
            "data": history[-1],
            "yesterday": history[-2],
            "targets": targets,
            "history": history,
            "streaks": streaks(db, today, targets),
            "weights": WEIGHTS,
            "day": today.isoformat(),
            "hour": now_ist().hour,
        })
    finally:
        db.close()


@habits_bp.route("/today", methods=["PUT"])
def put_today():
    return _update(_today())


@habits_bp.route("/<day_str>", methods=["PUT"])
def put_day(day_str):
    try:
        day = date.fromisoformat(day_str)
    except ValueError:
        return _err("Use a YYYY-MM-DD date.")
    return _update(day)


@habits_bp.route("", methods=["GET"])
def list_habits():
    try:
        days = int(request.args.get("days", 30))
    except (TypeError, ValueError):
        return _err("days must be a number.")
    days = max(1, min(days, MAX_HISTORY_DAYS))
    db = SessionLocal()
    try:
        today = _today()
        targets = get_targets(db)
        series = _series(db, today, days, targets)
        logged = [d for d in series if d["logged"]]
        slept = [d["sleep_hours"] for d in logged if d["sleep_hours"] is not None]
        stepped = [d["steps"] for d in logged if d["steps"] is not None]
        screen = [d["screen_off_on_time"] for d in logged if d["screen_off_on_time"] is not None]

        def avg(xs, nd=1):
            return round(sum(xs) / len(xs), nd) if xs else None

        averages = {
            "sleep_hours": avg(slept, 2),
            "water_glasses": avg([d["water_glasses"] for d in logged]),
            "exercise_min": avg([d["exercise_min"] for d in logged]),
            "steps": avg(stepped, 0),
            "screen_off_rate": avg([1.0 if s else 0.0 for s in screen], 2),
            "score": avg([d["score"] for d in series]),  # unlogged days count as 0
            "days_logged": len(logged),
        }
        hit_rate = {h: round(sum(1 for d in series if d["met"][h]) / len(series), 2) for h in HABITS}
        return jsonify({
            "status": "success",
            "data": series,
            "averages": averages,
            "hit_rate": hit_rate,
            "targets": targets,
            "streaks": streaks(db, today, targets),
            "days": days,
        })
    finally:
        db.close()


@habits_bp.route("/targets", methods=["POST"])
def set_targets():
    data = _body()
    updates = {}
    for name, (key, _default, lo, hi, cast) in TARGETS.items():
        v = data.get(name, data.get(key))
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
            return _err(f"{name} target must be a number.")
        if v < lo or v > hi:
            return _err(f"{name} target must be between {lo} and {hi}.")
        updates[key] = round(float(v) * 4) / 4 if cast is float else int(round(v))
    if not updates:
        return _err("Send at least one of sleep, water, exercise.")
    db = SessionLocal()
    try:
        repo = NotificationRepository(db)
        for key, v in updates.items():
            repo.set_setting(key, str(v))
        targets = get_targets(db)
        return jsonify({
            "status": "success",
            "targets": targets,
            "streaks": streaks(db, _today(), targets),
        })
    finally:
        db.close()
