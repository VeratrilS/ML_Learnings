"""
Notes: a small markdown knowledge base.

Each note has a title, a markdown body, comma-separated tags, a pinned flag and an optional
colour label. Listing supports `?q=` (title/body/tags, title hits first, with a snippet) and `?tag=`.
"""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, or_

from api.core.db import Base, SessionLocal, engine

MAX_TITLE = 200
MAX_BODY = 100_000
MAX_TAGS = 20
MAX_TAG = 40
COLORS = {"", "accent", "ok", "danger", "easy", "medium", "hard"}
SNIPPET = 160


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(MAX_TITLE), nullable=False, default="")
    body = Column(Text, nullable=False, default="")
    tags = Column(String(1000), nullable=False, default="")  # normalized "a,b,c"
    pinned = Column(Boolean, default=False, nullable=False)
    color = Column(String(20), nullable=False, default="")
    created_at = Column(DateTime, default=_utcnow)  # naive UTC
    updated_at = Column(DateTime, default=_utcnow, index=True)  # naive UTC

    def __repr__(self):
        return f"<Note(id={self.id}, title={self.title!r})>"


notes_bp = Blueprint("notes", __name__, url_prefix="/api/notes")


@notes_bp.record_once
def _ensure_table(state):
    try:
        Note.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:  # e.g. a concurrent cold start created it first
        print(f"notes table check skipped: {e}")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _tag_list(raw):
    return [t for t in (raw or "").split(",") if t]


def _clean_tags(value):
    """Accepts a list or comma string. Returns (normalized_string, error)."""
    if value is None:
        return "", None
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, list) and all(isinstance(v, str) for v in value):
        parts = value
    else:
        return None, "tags must be a list or comma-separated string."
    out = []
    for p in parts:
        t = p.strip().lower().lstrip("#")
        if not t or t in out:
            continue
        if len(t) > MAX_TAG:
            return None, f"Tags must be at most {MAX_TAG} characters."
        out.append(t)
    if len(out) > MAX_TAGS:
        return None, f"At most {MAX_TAGS} tags."
    return ",".join(out), None


def _snippet(body, q):
    text = " ".join((body or "").split())
    if not text:
        return ""
    if q:
        i = text.lower().find(q.lower())
        if i >= 0:
            start = max(0, i - SNIPPET // 3)
            end = min(len(text), start + SNIPPET)
            return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")
    return text[:SNIPPET] + ("…" if len(text) > SNIPPET else "")


def _serialize(n, q=None, full=True):
    d = {
        "id": n.id,
        "title": n.title or "",
        "tags": _tag_list(n.tags),
        "pinned": bool(n.pinned),
        "color": n.color or "",
        "created_at": _iso(n.created_at),
        "updated_at": _iso(n.updated_at),
        "snippet": _snippet(n.body, q),
    }
    if full:
        d["body"] = n.body or ""
    return d


def _apply(n, data):
    """Apply editable fields from `data` onto note `n`. Returns an error string or None."""
    if "title" in data:
        if not isinstance(data["title"], str):
            return "title must be a string."
        title = data["title"].strip()
        if len(title) > MAX_TITLE:
            return f"Title must be at most {MAX_TITLE} characters."
        n.title = title
    if "body" in data:
        if not isinstance(data["body"], str):
            return "body must be a string."
        if len(data["body"]) > MAX_BODY:
            return f"Body must be at most {MAX_BODY} characters."
        n.body = data["body"]
    if "tags" in data:
        tags, error = _clean_tags(data["tags"])
        if error:
            return error
        n.tags = tags
    if "pinned" in data:
        n.pinned = bool(data["pinned"])
    if "color" in data:
        color = data["color"] if isinstance(data["color"], str) else None
        if color is None or color not in COLORS:
            return "Unknown color."
        n.color = color
    return None


# ---------------- routes ----------------
@notes_bp.route("", methods=["GET"])
def list_notes():
    q = (request.args.get("q") or "").strip()
    tag = (request.args.get("tag") or "").strip().lower().lstrip("#")
    db = SessionLocal()
    try:
        query = db.query(Note)
        if q:
            like = f"%{q}%"
            query = query.filter(or_(Note.title.ilike(like), Note.body.ilike(like), Note.tags.ilike(like)))
        if tag:
            # tags stored as "a,b,c": match exact element via padded comparison
            query = query.filter((("," + Note.tags + ",")).ilike(f"%,{tag},%"))
        items = query.order_by(Note.pinned.desc(), Note.updated_at.desc(), Note.id.desc()).all()
        if q:
            ql = q.lower()
            # stable sort keeps pinned/recency order within each group
            items.sort(key=lambda n: 0 if ql in (n.title or "").lower() else 1)
        return jsonify({
            "status": "success",
            "data": [_serialize(n, q, full=False) for n in items],
            "total": len(items),
        })
    finally:
        db.close()


@notes_bp.route("/tags", methods=["GET"])
def list_tags():
    db = SessionLocal()
    try:
        counts = {}
        for (raw,) in db.query(Note.tags).all():
            for t in _tag_list(raw):
                counts[t] = counts.get(t, 0) + 1
        data = [{"tag": t, "count": c} for t, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        return jsonify({"status": "success", "data": data})
    finally:
        db.close()


@notes_bp.route("", methods=["POST"])
def create_note():
    data = _body()
    n = Note(title="", body="", tags="", pinned=False, color="")
    error = _apply(n, data)
    if error:
        return _err(error)
    db = SessionLocal()
    try:
        now = _utcnow()
        n.created_at = now
        n.updated_at = now
        db.add(n)
        db.commit()
        db.refresh(n)
        return jsonify({"status": "success", "data": _serialize(n)})
    finally:
        db.close()


@notes_bp.route("/<int:note_id>", methods=["GET", "PUT", "PATCH", "DELETE"])
def note_detail(note_id):
    db = SessionLocal()
    try:
        n = db.get(Note, note_id)
        if not n:
            return _err("Not found", 404)
        if request.method == "GET":
            return jsonify({"status": "success", "data": _serialize(n)})
        if request.method == "DELETE":
            db.delete(n)
            db.commit()
            return jsonify({"status": "success"})
        error = _apply(n, _body())
        if error:
            db.rollback()
            return _err(error)
        n.updated_at = _utcnow()
        db.commit()
        db.refresh(n)
        return jsonify({"status": "success", "data": _serialize(n)})
    finally:
        db.close()


@notes_bp.route("/<int:note_id>/pin", methods=["POST"])
def pin_note(note_id):
    """Toggle pinned, or set it explicitly with {"pinned": bool}. Doesn't bump updated_at."""
    data = _body()
    db = SessionLocal()
    try:
        n = db.get(Note, note_id)
        if not n:
            return _err("Not found", 404)
        n.pinned = bool(data["pinned"]) if "pinned" in data else not n.pinned
        db.commit()
        db.refresh(n)
        return jsonify({"status": "success", "data": _serialize(n)})
    finally:
        db.close()
