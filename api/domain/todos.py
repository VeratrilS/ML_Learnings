"""
Today's plan: a small daily to-do list.

Each task belongs to an IST day. Unfinished tasks from earlier days roll forward to today
automatically (we remember where they came from in `carried_from`).
"""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Date, func

from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine

MAX_TEXT = 300


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Todo(Base):
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(String(MAX_TEXT), nullable=False)
    done = Column(Boolean, default=False, nullable=False)
    day = Column(Date, nullable=False, index=True)  # IST date the task belongs to
    carried_from = Column(Date, nullable=True)  # original IST day if rolled forward
    created_at = Column(DateTime, default=_utcnow)  # naive UTC
    done_at = Column(DateTime, nullable=True)  # naive UTC
    position = Column(Integer, default=0, nullable=False)

    def __repr__(self):
        return f"<Todo(id={self.id}, day={self.day}, done={self.done}, text={self.text!r})>"


todos_bp = Blueprint("todos", __name__, url_prefix="/api/todos")


@todos_bp.record_once
def _ensure_table(state):
    """Create the table when the blueprint is registered, so wiring it in needs no extra step."""
    try:
        Todo.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:  # e.g. a concurrent cold start created it first
        print(f"todos table check skipped: {e}")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _today():
    return now_ist().date()


def _serialize(t):
    return {
        "id": t.id,
        "text": t.text,
        "done": bool(t.done),
        "day": t.day.isoformat() if t.day else None,
        "created_at": _iso(t.created_at),
        "done_at": _iso(t.done_at),
        "position": t.position or 0,
        "carried": t.carried_from is not None,
        "carried_from": t.carried_from.isoformat() if t.carried_from else None,
    }


def _clean_text(value):
    """Returns (text, error)."""
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        return None, "Task text can't be empty."
    if len(text) > MAX_TEXT:
        return None, f"Task text must be at most {MAX_TEXT} characters."
    return text, None


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _carry_over(db, today):
    """Move unfinished tasks from earlier days to today, after today's existing tasks."""
    stale = (db.query(Todo)
             .filter(Todo.done.is_(False), Todo.day < today)
             .order_by(Todo.day, Todo.position, Todo.id)
             .all())
    if not stale:
        return
    pos = (db.query(func.max(Todo.position)).filter(Todo.day == today).scalar() or 0)
    for t in stale:
        pos += 1
        if t.carried_from is None:
            t.carried_from = t.day
        t.day = today
        t.position = pos
    db.commit()


# ---------------- routes ----------------
@todos_bp.route("", methods=["GET"])
def list_todos():
    db = SessionLocal()
    try:
        today = _today()
        _carry_over(db, today)
        items = (db.query(Todo)
                 .filter(Todo.day == today)
                 .order_by(Todo.done, Todo.position, Todo.id)
                 .all())
        return jsonify({
            "status": "success",
            "data": [_serialize(t) for t in items],
            "done_today": sum(1 for t in items if t.done),
            "total": len(items),
            "day": today.isoformat(),
        })
    finally:
        db.close()


@todos_bp.route("", methods=["POST"])
def create_todo():
    text, error = _clean_text(_body().get("text"))
    if error:
        return _err(error)
    db = SessionLocal()
    try:
        today = _today()
        pos = (db.query(func.max(Todo.position)).filter(Todo.day == today).scalar() or 0) + 1
        t = Todo(text=text, done=False, day=today, position=pos)
        db.add(t)
        db.commit()
        db.refresh(t)
        return jsonify({"status": "success", "data": _serialize(t)})
    finally:
        db.close()


@todos_bp.route("/<int:todo_id>", methods=["PUT", "DELETE"])
def todo_detail(todo_id):
    db = SessionLocal()
    try:
        t = db.get(Todo, todo_id)
        if not t:
            return _err("Not found", 404)
        if request.method == "DELETE":
            db.delete(t)
            db.commit()
            return jsonify({"status": "success"})

        data = _body()
        if "text" in data:
            text, error = _clean_text(data["text"])
            if error:
                return _err(error)
            t.text = text
        if "done" in data:
            done = bool(data["done"])
            if done != bool(t.done):
                t.done = done
                t.done_at = _utcnow() if done else None
        db.commit()
        db.refresh(t)
        return jsonify({"status": "success", "data": _serialize(t)})
    finally:
        db.close()


@todos_bp.route("/reorder", methods=["POST"])
def reorder_todos():
    ids = _body().get("ids")
    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        return _err("ids must be a list of task ids.")
    db = SessionLocal()
    try:
        rows = {t.id: t for t in db.query(Todo).filter(Todo.id.in_(ids)).all()} if ids else {}
        for pos, todo_id in enumerate(ids):
            if todo_id in rows:
                rows[todo_id].position = pos
        db.commit()
        return jsonify({"status": "success", "updated": len(rows)})
    finally:
        db.close()
