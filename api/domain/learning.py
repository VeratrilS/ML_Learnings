"""
Learn: a simple tracker for working through a YouTube playlist.

The course (Coder Army's "System Design Full Course", 40 videos) is seeded on first use from
`learning_data.py`; the user ticks videos off as they watch them.

Endpoints:
  GET /api/learning                  -> courses with lessons + progress, next lesson,
                                        done_today vs daily_min (a minimum, never a cap), streak
  PUT /api/learning/lessons/<id>     -> {done: bool}
"""
from datetime import timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, func

from api.core.config import now_ist, to_ist
from api.core.db import Base, SessionLocal, engine
from api.domain.learning_data import CODER_ARMY_SYSTEM_DESIGN

MAX_TITLE = 300
SEEDED_KEY = "learning_seeded"               # seed version applied
SEED_COURSE_KEY = "learning_seed_course_id"  # which course the seed created
SEED_VERSION = "2"
DAILY_MIN = 1  # a daily minimum to aim for, never a cap


def _utcnow():
    """Naive UTC 'now', derived from now_ist so tests can freeze time in one place."""
    return now_ist().astimezone(timezone.utc).replace(tzinfo=None)


class Course(Base):
    __tablename__ = "learning_courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(MAX_TITLE), nullable=False)
    channel = Column(String(200), nullable=True)
    playlist_url = Column(String(500), nullable=True)
    playlist_id = Column(String(100), nullable=True, index=True)
    position = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_utcnow)  # naive UTC

    def __repr__(self):
        return f"<Course(id={self.id}, title={self.title!r})>"


class Lesson(Base):
    __tablename__ = "learning_lessons"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("learning_courses.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False, default=0)
    title = Column(String(MAX_TITLE), nullable=False)
    video_id = Column(String(32), nullable=False)
    duration = Column(String(20), nullable=True)
    done = Column(Boolean, default=False, nullable=False)
    done_at = Column(DateTime, nullable=True)  # naive UTC
    notes = Column(Text, nullable=True)  # reserved; not exposed in the simple tracker
    starred = Column(Boolean, default=False, nullable=False)  # reserved

    def __repr__(self):
        return f"<Lesson(id={self.id}, pos={self.position}, done={self.done}, title={self.title!r})>"


learning_bp = Blueprint("learning", __name__, url_prefix="/api/learning")


@learning_bp.record_once
def _ensure_tables(state):
    """Create our tables when the blueprint is registered, so wiring it in needs no extra step."""
    from api.domain.models import Settings  # the seed flag lives in the shared settings table
    for table in (Settings.__table__, Course.__table__, Lesson.__table__):
        try:
            table.create(bind=engine, checkfirst=True)
        except Exception as e:  # e.g. a concurrent cold start created it first
            print(f"{table.name} table check skipped: {e}")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _seconds(duration):
    try:
        total = 0
        for part in (duration or "").split(":"):
            total = total * 60 + int(part)
        return total
    except ValueError:
        return 0


def _ist_day(dt):
    return to_ist(dt).date() if dt else None


def _streak(done_days, today):
    """Consecutive IST days with >=1 lesson done, ending today (or yesterday if today is still open)."""
    days = set(d for d in done_days if d)
    cur = today if today in days else today - timedelta(days=1)
    streak = 0
    while cur in days:
        streak += 1
        cur -= timedelta(days=1)
    return streak


def _serialize_lesson(lesson, playlist_id=None):
    watch = f"https://www.youtube.com/watch?v={lesson.video_id}"
    if playlist_id:
        watch += f"&list={playlist_id}&index={lesson.position}"
    return {
        "id": lesson.id,
        "course_id": lesson.course_id,
        "position": lesson.position,
        "title": lesson.title,
        "video_id": lesson.video_id,
        "duration": lesson.duration,
        "seconds": _seconds(lesson.duration),
        "done": bool(lesson.done),
        "done_at": _iso(lesson.done_at),
        "done_day": _ist_day(lesson.done_at).isoformat() if lesson.done_at else None,
        "url": watch,
        "thumbnail": f"https://i.ytimg.com/vi/{lesson.video_id}/mqdefault.jpg",
    }


def _serialize_course(course, lessons, today):
    items = [_serialize_lesson(lesson, course.playlist_id) for lesson in lessons]
    done = [x for x in items if x["done"]]
    total = len(items)
    return {
        "id": course.id,
        "title": course.title,
        "channel": course.channel,
        "playlist_url": course.playlist_url,
        "playlist_id": course.playlist_id,
        "is_active": bool(course.is_active),
        "lessons": items,
        "done": len(done),
        "total": total,
        "progress": round(100 * len(done) / total) if total else 0,
        "total_seconds": sum(x["seconds"] for x in items),
        "remaining_seconds": sum(x["seconds"] for x in items if not x["done"]),
        "today": {
            "lesson": next((x for x in items if not x["done"]), None),  # up next
            "done_today": sorted((x for x in done if x["done_day"] == today.isoformat()),
                                 key=lambda x: x["done_at"] or ""),
        },
        "streak": _streak((_ist_day(lesson.done_at) for lesson in lessons if lesson.done), today),
    }


# ---------------- seeding ----------------
def _add_course(db, title, channel, playlist_url, playlist_id, videos):
    pos = (db.query(func.max(Course.position)).scalar() or 0) + 1
    course = Course(title=title[:MAX_TITLE], channel=channel, playlist_url=playlist_url,
                    playlist_id=playlist_id, position=pos, is_active=True)
    db.add(course)
    db.flush()
    for position, video_id, vtitle, duration in videos:
        db.add(Lesson(course_id=course.id, position=position, video_id=video_id,
                      title=vtitle[:MAX_TITLE], duration=duration or None))
    return course


def _seed_is_correct(db, course):
    c = CODER_ARMY_SYSTEM_DESIGN
    if course.playlist_id != c["playlist_id"]:
        return False
    ids = [v for (v,) in db.query(Lesson.video_id).filter(Lesson.course_id == course.id)
           .order_by(Lesson.position, Lesson.id).all()]
    return ids == [v[1] for v in c["videos"]]


def _legacy_seeded_course(db):
    """Before the seed course id was recorded, the seeded course was the first one created."""
    first = db.query(Course).order_by(Course.id).first()
    if first and first.channel == CODER_ARMY_SYSTEM_DESIGN["channel"] and "system design" in (first.title or "").lower():
        return first
    return None


def seed_if_needed(db):
    """Seed the System Design course once (never again after it is deleted).

    Seeds are versioned: when SEED_VERSION changes, the previously seeded course is replaced if its
    playlist or videos don't match CODER_ARMY_SYSTEM_DESIGN. Progress on videos present in both
    carries over. Other courses are never touched.
    """
    from api.domain.repositories import NotificationRepository
    repo = NotificationRepository(db)
    version = repo.get_setting(SEEDED_KEY)
    if version == SEED_VERSION:
        return False
    c = CODER_ARMY_SYSTEM_DESIGN

    if not version:  # never seeded
        if db.query(Course.id).first() is not None:
            repo.set_setting(SEEDED_KEY, SEED_VERSION)
            return False
        course = _add_course(db, c["title"], c["channel"], c["playlist_url"], c["playlist_id"], c["videos"])
        db.commit()
        repo.set_setting(SEED_COURSE_KEY, str(course.id))
        repo.set_setting(SEEDED_KEY, SEED_VERSION)
        return True

    # Older seed version: repair the seeded course if it is wrong
    seed_id = repo.get_setting(SEED_COURSE_KEY)
    old = db.get(Course, int(seed_id)) if seed_id and seed_id.isdigit() else _legacy_seeded_course(db)
    changed = False
    if old is not None and not _seed_is_correct(db, old):
        kept = {lesson.video_id: lesson for lesson in db.query(Lesson).filter(Lesson.course_id == old.id).all()}
        position, active = old.position, old.is_active
        db.query(Lesson).filter(Lesson.course_id == old.id).delete(synchronize_session=False)
        db.delete(old)
        db.flush()
        course = _add_course(db, c["title"], c["channel"], c["playlist_url"], c["playlist_id"], c["videos"])
        course.position, course.is_active = position, active
        db.flush()
        for lesson in db.query(Lesson).filter(Lesson.course_id == course.id).all():
            prev = kept.get(lesson.video_id)
            if prev is not None:
                lesson.done, lesson.done_at = prev.done, prev.done_at
        db.commit()
        repo.set_setting(SEED_COURSE_KEY, str(course.id))
        changed = True
    elif old is not None:
        repo.set_setting(SEED_COURSE_KEY, str(old.id))
    repo.set_setting(SEEDED_KEY, SEED_VERSION)
    return changed


def _payload(db):
    today = now_ist().date()
    courses = db.query(Course).order_by(Course.position, Course.id).all()
    lessons = db.query(Lesson).order_by(Lesson.course_id, Lesson.position, Lesson.id).all()
    by_course = {}
    for lesson in lessons:
        by_course.setdefault(lesson.course_id, []).append(lesson)
    all_done_days = [_ist_day(lesson.done_at) for lesson in lessons if lesson.done]
    return {
        "courses": [_serialize_course(c, by_course.get(c.id, []), today) for c in courses],
        "day": today.isoformat(),
        "streak": _streak(all_done_days, today),
        "done_today": sum(1 for d in all_done_days if d == today),
        "daily_min": DAILY_MIN,
    }


# ---------------- routes ----------------
@learning_bp.route("", methods=["GET"])
def list_learning():
    db = SessionLocal()
    try:
        seed_if_needed(db)
        return jsonify({"status": "success", "data": _payload(db)})
    finally:
        db.close()


@learning_bp.route("/lessons/<int:lesson_id>", methods=["PUT"])
def update_lesson(lesson_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "done" not in data:
        return _err("Send {done: true|false}.")
    db = SessionLocal()
    try:
        lesson = db.get(Lesson, lesson_id)
        if not lesson:
            return _err("Lesson not found", 404)
        done = bool(data["done"])
        if done != bool(lesson.done):
            lesson.done = done
            lesson.done_at = _utcnow() if done else None
            db.commit()
        course = db.get(Course, lesson.course_id)
        return jsonify({"status": "success", "data": _serialize_lesson(lesson, course.playlist_id if course else None)})
    finally:
        db.close()
