"""
Placements pipeline: every company from wishlist to offer.

An Application moves through stages (wishlist -> applied -> oa -> interview -> hr -> offer, or is
closed as rejected/withdrawn). Each stage change, note or interview round is kept as an
ApplicationEvent so the card has a timeline. GET returns everything plus a `summary` the
dashboard uses (counts per stage, upcoming rounds, near deadlines, offers).
"""
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Integer, String, DateTime, Date, Float, Text, ForeignKey

from api.core.config import IST, now_ist
from api.core.db import Base, SessionLocal, engine

STAGES = ["wishlist", "applied", "oa", "interview", "hr", "offer", "rejected", "withdrawn"]
STAGE_LABELS = {
    "wishlist": "Wishlist", "applied": "Applied", "oa": "OA", "interview": "Interview",
    "hr": "HR", "offer": "Offer", "rejected": "Rejected", "withdrawn": "Withdrawn",
}
ACTIVE_STAGES = {"applied", "oa", "interview", "hr"}
CLOSED_STAGES = {"rejected", "withdrawn"}
SOURCES = ["on-campus", "off-campus", "referral"]
EVENT_KINDS = {"stage", "note", "round"}

UPCOMING_DAYS = 14
DEADLINE_DAYS = 7
MAX_NOTES = 5000
MAX_EVENT_TEXT = 1000


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Application(Base):
    __tablename__ = "placement_applications"

    id = Column(Integer, primary_key=True, index=True)
    company = Column(String(120), nullable=False)
    role = Column(String(160), nullable=False, default="")
    source = Column(String(30), nullable=False, default="on-campus")
    stage = Column(String(30), nullable=False, default="wishlist", index=True)
    ctc_lpa = Column(Float, nullable=True)
    location = Column(String(120), nullable=True)
    link = Column(String(500), nullable=True)
    deadline = Column(Date, nullable=True)  # IST calendar date
    next_event_at = Column(DateTime, nullable=True)  # naive UTC
    next_event_label = Column(String(160), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)  # naive UTC
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    stage_changed_at = Column(DateTime, default=_utcnow)

    def __repr__(self):
        return f"<Application(id={self.id}, company={self.company!r}, stage={self.stage})>"


class ApplicationEvent(Base):
    __tablename__ = "placement_events"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("placement_applications.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    kind = Column(String(30), nullable=False, default="note")  # stage | note | round
    text = Column(Text, nullable=False)
    at = Column(DateTime, default=_utcnow)  # naive UTC


placements_bp = Blueprint("placements", __name__, url_prefix="/api/placements")


@placements_bp.record_once
def _ensure_tables(state):
    """Create the tables when the blueprint is registered, so wiring it in needs no extra step."""
    for model in (Application, ApplicationEvent):
        try:
            model.__table__.create(bind=engine, checkfirst=True)
        except Exception as e:  # e.g. a concurrent cold start created it first
            print(f"{model.__tablename__} table check skipped: {e}")


# ---------------- helpers ----------------
class _Invalid(ValueError):
    pass


def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _str(value, field, max_len, required=False):
    if value is None:
        if required:
            raise _Invalid(f"{field} is required.")
        return None
    if not isinstance(value, str):
        raise _Invalid(f"{field} must be text.")
    value = value.strip()
    if not value:
        if required:
            raise _Invalid(f"{field} is required.")
        return None
    if len(value) > max_len:
        raise _Invalid(f"{field} must be at most {max_len} characters.")
    return value


def _stage(value):
    s = value.strip().lower() if isinstance(value, str) else ""
    if s not in STAGES:
        raise _Invalid(f"Stage must be one of: {', '.join(STAGES)}.")
    return s


def _source(value):
    s = value.strip().lower() if isinstance(value, str) else ""
    if s not in SOURCES:
        raise _Invalid(f"Source must be one of: {', '.join(SOURCES)}.")
    return s


def _ctc(value):
    if value is None or value == "":
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise _Invalid("CTC must be a number (LPA).")
    if isinstance(value, bool) or v != v or v < 0 or v > 1000:
        raise _Invalid("CTC must be between 0 and 1000 LPA.")
    return round(v, 2)


def _link(value):
    link = _str(value, "Link", 500)
    if link and not link.lower().startswith(("http://", "https://")):
        link = f"https://{link}"
        if len(link) > 500:
            raise _Invalid("Link must be at most 500 characters.")
    return link


def _date(value, field="Deadline"):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise _Invalid(f"{field} must be a date (YYYY-MM-DD).")
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        raise _Invalid(f"{field} must be a date (YYYY-MM-DD).")


def _datetime(value, field="Event time"):
    """ISO string -> naive UTC. A string without an offset is read as IST."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise _Invalid(f"{field} must be an ISO date-time.")
    raw = value.strip()
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        raise _Invalid(f"{field} must be an ISO date-time.")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _serialize_event(e):
    return {"id": e.id, "application_id": e.application_id, "kind": e.kind, "text": e.text, "at": _iso(e.at)}


def _serialize(a, events=None):
    data = {
        "id": a.id,
        "company": a.company,
        "role": a.role or "",
        "source": a.source,
        "stage": a.stage,
        "ctc_lpa": a.ctc_lpa,
        "location": a.location,
        "link": a.link,
        "deadline": a.deadline.isoformat() if a.deadline else None,
        "next_event_at": _iso(a.next_event_at),
        "next_event_label": a.next_event_label,
        "notes": a.notes or "",
        "created_at": _iso(a.created_at),
        "updated_at": _iso(a.updated_at),
        "stage_changed_at": _iso(a.stage_changed_at),
    }
    if events is not None:
        data["events"] = [_serialize_event(e) for e in events]
    return data


def _add_event(db, app_id, kind, text, at=None):
    ev = ApplicationEvent(application_id=app_id, kind=kind, text=text, at=at or _utcnow())
    db.add(ev)
    return ev


def _events_for(db, app_ids):
    grouped = {i: [] for i in app_ids}
    if not app_ids:
        return grouped
    rows = (db.query(ApplicationEvent)
            .filter(ApplicationEvent.application_id.in_(app_ids))
            .order_by(ApplicationEvent.at.desc(), ApplicationEvent.id.desc())
            .all())
    for e in rows:
        grouped.setdefault(e.application_id, []).append(e)
    return grouped


def _apply(a, data, creating=False):
    """Validate and copy fields from the request body onto `a`. Returns the old stage if it changed."""
    if creating or "company" in data:
        a.company = _str(data.get("company"), "Company", 120, required=True)
    if creating or "role" in data:
        a.role = _str(data.get("role"), "Role", 160) or ""
    if "source" in data:
        a.source = _source(data["source"])
    elif creating:
        a.source = "on-campus"
    if "ctc_lpa" in data:
        a.ctc_lpa = _ctc(data["ctc_lpa"])
    if "location" in data:
        a.location = _str(data["location"], "Location", 120)
    if "link" in data:
        a.link = _link(data["link"])
    if "deadline" in data:
        a.deadline = _date(data["deadline"])
    if "next_event_at" in data:
        a.next_event_at = _datetime(data["next_event_at"])
    if "next_event_label" in data:
        a.next_event_label = _str(data["next_event_label"], "Event label", 160)
    if "notes" in data:
        notes = data["notes"]
        if notes is not None and not isinstance(notes, str):
            raise _Invalid("Notes must be text.")
        notes = (notes or "").strip()
        if len(notes) > MAX_NOTES:
            raise _Invalid(f"Notes must be at most {MAX_NOTES} characters.")
        a.notes = notes
    old_stage = None
    if creating:
        a.stage = _stage(data["stage"]) if "stage" in data else "wishlist"
    elif "stage" in data:
        new_stage = _stage(data["stage"])
        if new_stage != a.stage:
            old_stage = a.stage
            a.stage = new_stage
    return old_stage


def _summary(apps):
    now = _utcnow()
    today = now_ist().date()
    counts = {s: 0 for s in STAGES}
    for a in apps:
        counts[a.stage] = counts.get(a.stage, 0) + 1

    horizon = now + timedelta(days=UPCOMING_DAYS)
    grace = now - timedelta(hours=2)  # keep a round that just started on the list
    upcoming = [
        {"id": a.id, "company": a.company, "role": a.role or "", "stage": a.stage,
         "label": a.next_event_label or "Next round", "at": _iso(a.next_event_at)}
        for a in sorted((a for a in apps
                         if a.next_event_at and a.stage not in CLOSED_STAGES
                         and grace <= a.next_event_at <= horizon),
                        key=lambda a: (a.next_event_at, a.id))
    ]

    last_day = today + timedelta(days=DEADLINE_DAYS)
    deadlines = [
        {"id": a.id, "company": a.company, "role": a.role or "", "stage": a.stage,
         "deadline": a.deadline.isoformat(), "days_left": (a.deadline - today).days}
        for a in sorted((a for a in apps
                         if a.deadline and a.stage not in CLOSED_STAGES and a.stage != "offer"
                         and today <= a.deadline <= last_day),
                        key=lambda a: (a.deadline, a.id))
    ]

    offers = sorted(
        ({"id": a.id, "company": a.company, "role": a.role or "", "ctc_lpa": a.ctc_lpa}
         for a in apps if a.stage == "offer"),
        key=lambda o: (-(o["ctc_lpa"] or 0), o["company"].lower()),
    )
    ctcs = [o["ctc_lpa"] for o in offers if o["ctc_lpa"] is not None]
    return {
        "counts": counts,
        "total": len(apps),
        "active": sum(counts[s] for s in ACTIVE_STAGES),
        "oa_pending": counts["oa"],
        "interviews": counts["interview"] + counts["hr"],
        "offers_count": len(offers),
        "offers": offers,
        "best_ctc": max(ctcs) if ctcs else None,
        "upcoming": upcoming,
        "deadlines": deadlines,
    }


# ---------------- routes ----------------
@placements_bp.route("", methods=["GET"])
def list_applications():
    db = SessionLocal()
    try:
        apps = db.query(Application).order_by(Application.updated_at.desc(), Application.id.desc()).all()
        events = _events_for(db, [a.id for a in apps])
        return jsonify({
            "status": "success",
            "data": [_serialize(a, events.get(a.id, [])) for a in apps],
            "summary": _summary(apps),
            "stages": STAGES,
            "sources": SOURCES,
        })
    finally:
        db.close()


@placements_bp.route("", methods=["POST"])
def create_application():
    data = _body()
    a = Application()
    try:
        _apply(a, data, creating=True)
    except _Invalid as e:
        return _err(str(e))
    db = SessionLocal()
    try:
        now = _utcnow()
        a.created_at = a.updated_at = a.stage_changed_at = now
        db.add(a)
        db.flush()
        _add_event(db, a.id, "stage", f"Added to {STAGE_LABELS[a.stage]}", now)
        db.commit()
        db.refresh(a)
        return jsonify({"status": "success", "data": _serialize(a, _events_for(db, [a.id])[a.id])})
    finally:
        db.close()


@placements_bp.route("/<int:app_id>", methods=["PUT", "DELETE"])
def application_detail(app_id):
    db = SessionLocal()
    try:
        a = db.get(Application, app_id)
        if not a:
            return _err("Application not found.", 404)
        if request.method == "DELETE":
            db.query(ApplicationEvent).filter(ApplicationEvent.application_id == app_id).delete()
            db.delete(a)
            db.commit()
            return jsonify({"status": "success"})

        try:
            old_stage = _apply(a, _body())
        except _Invalid as e:
            db.rollback()
            return _err(str(e))
        now = _utcnow()
        a.updated_at = now
        if old_stage:
            a.stage_changed_at = now
            _add_event(db, a.id, "stage", f"{STAGE_LABELS[old_stage]} → {STAGE_LABELS[a.stage]}", now)
        db.commit()
        db.refresh(a)
        return jsonify({"status": "success", "data": _serialize(a, _events_for(db, [a.id])[a.id])})
    finally:
        db.close()


@placements_bp.route("/<int:app_id>/events", methods=["POST"])
def add_event(app_id):
    data = _body()
    kind = data.get("kind", "note")
    kind = kind.strip().lower() if isinstance(kind, str) else ""
    if kind not in ("note", "round"):
        return _err("Kind must be 'note' or 'round'.")
    try:
        text = _str(data.get("text"), "Text", MAX_EVENT_TEXT, required=True)
        at = _datetime(data.get("at"), "Time")
    except _Invalid as e:
        return _err(str(e))
    db = SessionLocal()
    try:
        a = db.get(Application, app_id)
        if not a:
            return _err("Application not found.", 404)
        ev = _add_event(db, a.id, kind, text, at)
        a.updated_at = _utcnow()
        db.commit()
        db.refresh(ev)
        db.refresh(a)
        return jsonify({
            "status": "success",
            "data": _serialize_event(ev),
            "application": _serialize(a, _events_for(db, [a.id])[a.id]),
        })
    finally:
        db.close()
