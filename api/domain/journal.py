"""
Daily journal: the evening shutdown ritual.

One entry per IST "day". The day rolls over at 04:00 IST, not midnight, so closing the day
at 00:30 still lands on the day you actually lived. Each entry holds mood/energy (1-5),
one win, one blocker, and tomorrow's top 3, which the morning briefing shows the next day.

GET /api/journal/today  -> {data: entry|null, yesterday: entry|null, day}
PUT /api/journal/today  -> upsert today's entry (partial updates allowed)
GET /api/journal?days=30 -> {data: [entry...]} newest first
"""
import json
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Date, DateTime, Integer, Text

from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine

ROLLOVER_HOUR = 4  # IST hour at which a new journal day starts
MAX_TEXT = 500
MAX_ITEM = 300  # same cap as a todo, so top-3 items can become tasks unchanged
MAX_DAYS = 365


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    day = Column(Date, nullable=False, unique=True, index=True)  # IST journal day
    mood = Column(Integer, nullable=True)  # 1..5
    energy = Column(Integer, nullable=True)  # 1..5
    win = Column(Text, nullable=True)
    blocker = Column(Text, nullable=True)
    top3 = Column(Text, nullable=True)  # JSON list of strings
    created_at = Column(DateTime, default=_utcnow)  # naive UTC
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)  # naive UTC

    def __repr__(self):
        return f"<JournalEntry(day={self.day}, mood={self.mood}, energy={self.energy})>"


journal_bp = Blueprint("journal", __name__, url_prefix="/api/journal")


@journal_bp.record_once
def _ensure_table(state):
    """Create the table when the blueprint is registered, so wiring it in needs no extra step."""
    try:
        JournalEntry.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:  # e.g. a concurrent cold start created it first
        print(f"journal table check skipped: {e}")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def journal_day(now=None):
    """The IST journal day for `now` (defaults to the current time); rolls over at ROLLOVER_HOUR."""
    now = now or now_ist()
    return (now - timedelta(hours=ROLLOVER_HOUR)).date()


def _load_top3(raw):
    try:
        items = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return []
    return [str(x) for x in items if isinstance(x, str) and x.strip()][:3] if isinstance(items, list) else []


def serialize(e):
    if e is None:
        return None
    return {
        "id": e.id,
        "day": e.day.isoformat(),
        "mood": e.mood,
        "energy": e.energy,
        "win": e.win or "",
        "blocker": e.blocker or "",
        "top3": _load_top3(e.top3),
        "created_at": _iso(e.created_at),
        "updated_at": _iso(e.updated_at),
    }


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _scale(value, name):
    """Returns (int|None, error) for a 1-5 rating."""
    if value is None or value == "":
        return None, None
    if isinstance(value, bool):
        return None, f"{name} must be a number from 1 to 5."
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None, f"{name} must be a number from 1 to 5."
    if n != value and not (isinstance(value, str) and value.strip() == str(n)):
        return None, f"{name} must be a whole number from 1 to 5."
    if not 1 <= n <= 5:
        return None, f"{name} must be a number from 1 to 5."
    return n, None


def _text(value, name):
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, f"{name} must be text."
    value = value.strip()
    if len(value) > MAX_TEXT:
        return None, f"{name} must be at most {MAX_TEXT} characters."
    return value or None, None


def _top3(value):
    if value is None:
        return [], None
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        return None, "top3 must be a list of strings."
    items = [x.strip() for x in value if x.strip()]
    if len(items) > 3:
        return None, "top3 holds at most 3 items."
    if any(len(x) > MAX_ITEM for x in items):
        return None, f"Each top-3 item must be at most {MAX_ITEM} characters."
    return items, None


# ---------------- routes ----------------
@journal_bp.route("/today", methods=["GET"])
def get_today():
    db = SessionLocal()
    try:
        day = journal_day()
        entry = db.query(JournalEntry).filter(JournalEntry.day == day).first()
        yesterday = db.query(JournalEntry).filter(JournalEntry.day == day - timedelta(days=1)).first()
        return jsonify({"status": "success", "data": serialize(entry), "yesterday": serialize(yesterday),
                        "day": day.isoformat()})
    finally:
        db.close()


@journal_bp.route("/today", methods=["PUT"])
def put_today():
    data = _body()
    if data is None:
        return _err("Send a JSON object.")
    fields = {}
    for key, label in (("mood", "Mood"), ("energy", "Energy")):
        if key in data:
            fields[key], error = _scale(data[key], label)
            if error:
                return _err(error)
    for key, label in (("win", "Win"), ("blocker", "Blocker")):
        if key in data:
            fields[key], error = _text(data[key], label)
            if error:
                return _err(error)
    if "top3" in data:
        items, error = _top3(data["top3"])
        if error:
            return _err(error)
        fields["top3"] = json.dumps(items)

    db = SessionLocal()
    try:
        day = journal_day()
        entry = db.query(JournalEntry).filter(JournalEntry.day == day).first()
        if entry is None:
            entry = JournalEntry(day=day)
            db.add(entry)
        for k, v in fields.items():
            setattr(entry, k, v)
        entry.updated_at = _utcnow()
        db.commit()
        db.refresh(entry)
        return jsonify({"status": "success", "data": serialize(entry), "day": day.isoformat()})
    finally:
        db.close()


@journal_bp.route("", methods=["GET"], strict_slashes=False)
def list_entries():
    try:
        days = int(request.args.get("days", 30))
    except (TypeError, ValueError):
        return _err("days must be a number.")
    days = max(1, min(days, MAX_DAYS))
    db = SessionLocal()
    try:
        since = journal_day() - timedelta(days=days - 1)
        rows = (db.query(JournalEntry)
                .filter(JournalEntry.day >= since)
                .order_by(JournalEntry.day.desc())
                .all())
        return jsonify({"status": "success", "data": [serialize(e) for e in rows], "days": days})
    finally:
        db.close()
