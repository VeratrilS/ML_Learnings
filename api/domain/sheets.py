"""
Sheets: a checklist for working through a company's LeetCode question list, like Learn's playlist.

The Apple sheet (Medium + Hard only, 130 problems) is seeded on first use from `sheet_data.py`;
the user ticks problems off as they solve them.

Endpoints:
  GET /api/sheets/<key>              -> problems + progress (overall and per difficulty), next problem,
                                        done_today vs daily_min (a minimum, never a cap), streak
  PUT /api/sheets/problems/<id>      -> {done: bool}
"""
from datetime import timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float

from api.core.config import now_ist, to_ist
from api.core.db import Base, SessionLocal, engine
from api.domain.learning import _err, _iso, _streak
from api.domain.sheet_data import APPLE_SHEET

SHEETS = {APPLE_SHEET["key"]: APPLE_SHEET}
SEED_VERSION = "1"
DAILY_MIN = 1  # a daily minimum to aim for, never a cap
DIFFICULTIES = ("Medium", "Hard")


def _seeded_key(sheet):
    return f"sheet_seeded:{sheet}"


def _utcnow():
    """Naive UTC 'now', derived from now_ist so tests can freeze time in one place."""
    return now_ist().astimezone(timezone.utc).replace(tzinfo=None)


def _ist_day(dt):
    return to_ist(dt).date() if dt else None


class SheetProblem(Base):
    __tablename__ = "sheet_problems"

    id = Column(Integer, primary_key=True, index=True)
    sheet = Column(String(40), nullable=False, index=True)
    position = Column(Integer, nullable=False, default=0)
    leetcode_id = Column(Integer, nullable=True)
    title = Column(String(300), nullable=False)
    slug = Column(String(200), nullable=False)
    difficulty = Column(String(10), nullable=False)
    acceptance = Column(Float, nullable=True)
    topics = Column(String(500), nullable=True)
    last_asked = Column(String(10), nullable=True)
    done = Column(Boolean, default=False, nullable=False)
    done_at = Column(DateTime, nullable=True)  # naive UTC

    def __repr__(self):
        return f"<SheetProblem(sheet={self.sheet!r}, pos={self.position}, done={self.done}, title={self.title!r})>"


sheets_bp = Blueprint("sheets", __name__, url_prefix="/api/sheets")


@sheets_bp.record_once
def _ensure_tables(state):
    """Create our table when the blueprint is registered, so wiring it in needs no extra step."""
    from api.domain.models import Settings  # the seed flag lives in the shared settings table
    for table in (Settings.__table__, SheetProblem.__table__):
        try:
            table.create(bind=engine, checkfirst=True)
        except Exception as e:  # e.g. a concurrent cold start created it first
            print(f"{table.name} table check skipped: {e}")


# ---------------- seeding ----------------
def seed_if_needed(db, key):
    """Seed a sheet once. When SEED_VERSION changes, problems are upserted by slug (progress kept, none removed)."""
    from api.domain.repositories import NotificationRepository
    repo = NotificationRepository(db)
    if repo.get_setting(_seeded_key(key)) == SEED_VERSION:
        return False
    existing = {p.slug: p for p in db.query(SheetProblem).filter(SheetProblem.sheet == key).all()}
    for position, lc_id, title, slug, difficulty, acceptance, topics, last_asked in SHEETS[key]["problems"]:
        p = existing.get(slug)
        if p is None:
            p = SheetProblem(sheet=key, slug=slug)
            db.add(p)
        p.position, p.leetcode_id, p.title, p.difficulty = position, lc_id, title[:300], difficulty
        p.acceptance, p.topics, p.last_asked = acceptance, topics[:500], last_asked
    db.commit()
    repo.set_setting(_seeded_key(key), SEED_VERSION)
    return True


# ---------------- serializing ----------------
def _serialize(p):
    return {
        "id": p.id,
        "sheet": p.sheet,
        "position": p.position,
        "leetcode_id": p.leetcode_id,
        "title": p.title,
        "slug": p.slug,
        "difficulty": p.difficulty,
        "acceptance": p.acceptance,
        "topics": [t.strip() for t in (p.topics or "").split(",") if t.strip()],
        "last_asked": p.last_asked,
        "done": bool(p.done),
        "done_at": _iso(p.done_at),
        "done_day": _ist_day(p.done_at).isoformat() if p.done_at else None,
        "url": f"https://leetcode.com/problems/{p.slug}/",
    }


def _payload(db, key):
    today = now_ist().date()
    sheet = SHEETS[key]
    rows = db.query(SheetProblem).filter(SheetProblem.sheet == key).order_by(SheetProblem.position, SheetProblem.id).all()
    items = [_serialize(p) for p in rows]
    done = [x for x in items if x["done"]]
    total = len(items)
    done_days = [_ist_day(p.done_at) for p in rows if p.done]
    return {
        "key": key,
        "title": sheet["title"],
        "company": sheet["company"],
        "problems": items,
        "done": len(done),
        "total": total,
        "progress": round(100 * len(done) / total) if total else 0,
        "by_difficulty": {
            d: {"done": sum(1 for x in done if x["difficulty"] == d),
                "total": sum(1 for x in items if x["difficulty"] == d)}
            for d in DIFFICULTIES
        },
        "next": next((x for x in items if not x["done"]), None),
        "day": today.isoformat(),
        "done_today": sum(1 for d in done_days if d == today),
        "daily_min": DAILY_MIN,
        "streak": _streak(done_days, today),
    }


# ---------------- routes ----------------
@sheets_bp.route("/<key>", methods=["GET"])
def get_sheet(key):
    if key not in SHEETS:
        return _err("Sheet not found", 404)
    db = SessionLocal()
    try:
        seed_if_needed(db, key)
        return jsonify({"status": "success", "data": _payload(db, key)})
    finally:
        db.close()


@sheets_bp.route("/problems/<int:problem_id>", methods=["PUT"])
def update_problem(problem_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "done" not in data:
        return _err("Send {done: true|false}.")
    db = SessionLocal()
    try:
        p = db.get(SheetProblem, problem_id)
        if not p:
            return _err("Problem not found", 404)
        done = bool(data["done"])
        if done != bool(p.done):
            p.done = done
            p.done_at = _utcnow() if done else None
            db.commit()
        return jsonify({"status": "success", "data": _serialize(p)})
    finally:
        db.close()
