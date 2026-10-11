"""
End-sem syllabus tracker.

Subjects (with an optional exam date) own syllabus topics grouped by unit. Topics are ticked off,
rated for confidence (1 = shaky, 3 = solid) and stamped when last studied. A reminder email
summarises coverage per subject and suggests what to study next.
"""
import html as h
import os
import re
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, func, inspect, text
from sqlalchemy.orm import relationship, selectinload

from api.core.clients import EmailClient
from api.core.config import APP_URL, RECEIVER_EMAIL, now_ist
from api.core.db import Base, SessionLocal, engine
from api.domain.repositories import NotificationRepository

MAX_NAME = 120
MAX_CODE = 30
MAX_UNIT = 120
MAX_TITLE = 300
MAX_TOPICS_PER_PASTE = 400
REMIND_COOLDOWN = timedelta(hours=36)
REMIND_SETTING = "study_reminder_last"
SEEDED_SETTING = "syllabus_seeded"
KINDS = ("theory", "lab", "other")
# (code, name, faculty, kind, color) in display order. Only theory subjects drive reminders / next exam.
SEED_SUBJECTS = (
    ("CS6319", "Next Generation Networking Systems", "Judhistir Mahapatro", "theory", "violet"),
    ("CS6404", "Software Testing", "S. Asha", "theory", "teal"),
    ("CS6510", "Deep Learning", "Panthadeep Bhattacharjee", "theory", "rose"),
    ("CS6172", "Network Simulation Laboratory", "Judhistir Mahapatro", "lab", "violet"),
    ("CS6511", "Deep Learning Laboratory", "Panthadeep Bhattacharjee", "lab", "rose"),
    ("CS6474", "Software Testing Laboratory", "S. Asha", "lab", "teal"),
    ("CS6060", "Product Innovation Laboratory", "Tapas Kumar Mishra", "lab", "amber"),
    ("CS4095", "Capstone Project - I", "Sibarama Panigrahi", "other", "blue"),
    ("CS4907", "Summer Industrial Research Experience", "Sujata Mohanty", "other", "green"),
    ("CS4555", "Special Topics by Industry Experts", "Tapas Kumar Mishra", "other", "pink"),
    ("CS4901", "Seminar and Technical Writing", "Pankaj Kumar Sa", "other", "orange"),
)
_SMALL_WORDS = {"and", "of", "the", "for", "by", "in", "on", "to", "a", "an", "with"}


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------- models ----------------
class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(MAX_NAME), nullable=False)
    code = Column(String(MAX_CODE), nullable=True)
    faculty = Column(String(MAX_NAME), nullable=True)
    kind = Column(String(20), default="theory", nullable=False)  # 'theory' | 'lab' | 'other'
    exam_date = Column(Date, nullable=True)
    color = Column(String(20), nullable=True)
    position = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=_utcnow)  # naive UTC

    topics = relationship("SyllabusTopic", back_populates="subject", cascade="all, delete-orphan",
                          order_by="(SyllabusTopic.position, SyllabusTopic.id)")

    def __repr__(self):
        return f"<Subject(id={self.id}, name={self.name!r}, exam_date={self.exam_date})>"


class SyllabusTopic(Base):
    __tablename__ = "syllabus_topics"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    unit = Column(String(MAX_UNIT), nullable=True)  # e.g. "Unit 3 · Black box testing"
    title = Column(String(MAX_TITLE), nullable=False)
    done = Column(Boolean, default=False, nullable=False)
    done_at = Column(DateTime, nullable=True)  # naive UTC
    confidence = Column(Integer, nullable=True)  # 1 (shaky) .. 3 (solid)
    position = Column(Integer, default=0, nullable=False)
    last_studied_at = Column(DateTime, nullable=True)  # naive UTC

    subject = relationship("Subject", back_populates="topics")

    def __repr__(self):
        return f"<SyllabusTopic(id={self.id}, unit={self.unit!r}, title={self.title!r}, done={self.done})>"


syllabus_bp = Blueprint("syllabus", __name__, url_prefix="/api/syllabus")


@syllabus_bp.record_once
def _ensure_tables(state):
    """Create the tables when the blueprint is registered, so wiring it in needs no extra step."""
    try:
        Base.metadata.create_all(bind=engine, tables=[Subject.__table__, SyllabusTopic.__table__])
    except Exception as e:  # e.g. a concurrent cold start created them first
        print(f"syllabus table check skipped: {e}")
    # Columns added after the first version of this table (create_all never alters tables)
    try:
        existing = {c["name"] for c in inspect(engine).get_columns("subjects")}
        for name, ddl in (("faculty", "VARCHAR(120)"), ("kind", "VARCHAR(20) DEFAULT 'theory' NOT NULL")):
            if name not in existing:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE subjects ADD COLUMN {name} {ddl}"))
    except Exception as e:
        print(f"syllabus column migration skipped: {e}")


# ---------------- bulk syllabus parser ----------------
_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50}
_UNIT_RE = re.compile(
    r"^(?:[#*>\-•\s]*)"                                   # optional markdown / bullet noise
    r"(unit|module|chapter|part|week)\s*[-–—:.#]?\s*"      # the keyword
    r"(\d{1,2}|[ivxl]{1,6})(?![\w])"                       # its number (arabic or roman)
    r"\s*[:\-–—.)|]*\s*(.*)$",                             # separator + optional title
    re.IGNORECASE,
)
_STOP_RE = re.compile(
    r"^(?:text\s*-?\s*books?|reference\s*books?|references|course\s*outcomes?|suggested\s*readings?|"
    r"e-?\s*resources|web\s*resources|lab\s*experiments)\b",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(
    r"^(?:[\-*•·▪◦‣●○■□–—>✓✔#]+\s*"      # symbol bullets / markdown headings
    r"|\(?\d+(?:\.\d+)+[.)]?\s+"           # 1.2 / 1.2.3
    r"|\(?\d{1,3}[.)](?!\d)\s*"             # 1. / 1) / (1)  (not 2.5G)
    r"|\(?[a-zA-Z][.)]\s+"                  # a. / a) / (b)
    r"|\(?(?:i{1,3}|iv|vi{0,3}|ix|x)[.)]\s+"  # i. ii) (iv)
    r")+"
)
_GENERIC_HEADING_RE = re.compile(
    r"^(?:topics?|syllabus|contents?|course\s*contents?|detailed\s*syllabus|sub\s*topics?)\s*:?$", re.IGNORECASE)
_HOURS_RE = re.compile(
    r"[\s\-–—,:]*[(\[]?\s*\d{1,3}\s*(?:hrs?|hours?|lectures?|periods?|sessions?|l)\.?\s*[)\]]?\s*$",
    re.IGNORECASE,
)


def _roman_to_int(s):
    total, prev = 0, 0
    for ch in reversed(s.lower()):
        v = _ROMAN.get(ch)
        if v is None:
            return None
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total if 0 < total <= 40 else None


def _clean(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    text = _HOURS_RE.sub("", text).strip()
    return text.strip(" .:;,-–—|*").strip()


def _parse_unit_header(line):
    """'UNIT-II Testing techniques (9 Hrs)' -> 'Unit 2 · Testing techniques'. None if not a header."""
    m = _UNIT_RE.match(line)
    if not m:
        return None
    kind, num, rest = m.group(1).capitalize(), m.group(2), m.group(3)
    n = int(num) if num.isdigit() else _roman_to_int(num)
    if n is None:
        return None
    title = _clean(rest)
    label = f"{kind} {n}" + (f" · {title}" if title else "")
    return label[:MAX_UNIT].rstrip()


def _split_top_level(text):
    """Split on commas/semicolons that are not inside brackets and not between digits (1,000)."""
    parts, buf, depth = [], [], 0
    for i, ch in enumerate(text):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        if ch in ",;" and depth == 0:
            prev_digit = i > 0 and text[i - 1].isdigit()
            next_digit = i + 1 < len(text) and text[i + 1].isdigit()
            if not (prev_digit and next_digit):
                parts.append("".join(buf))
                buf = []
                continue
        buf.append(ch)
    parts.append("".join(buf))
    return parts


def _topics_from_line(line):
    line = _BULLET_RE.sub("", line.strip())
    line = _clean(line)
    if not line or not re.search(r"[A-Za-z]", line) or _GENERIC_HEADING_RE.match(line):
        return []
    pieces = _split_top_level(line)
    if len(pieces) == 1:
        return [line[:MAX_TITLE]]
    out = []
    # "Black box testing: equivalence partitioning, boundary values" -> heading + each item
    head, sep, first = pieces[0].partition(":")
    if sep and head.strip() and len(head) <= 80 and first.strip():
        out.append(_clean(head)[:MAX_TITLE])
        pieces[0] = first
    for p in pieces:
        p = _clean(_BULLET_RE.sub("", p.strip()))
        p = re.sub(r"^(?:and|&)\s+", "", p, flags=re.IGNORECASE)
        if len(p) >= 2 and re.search(r"[A-Za-z]", p):
            out.append(p[:MAX_TITLE])
    return out


def parse_syllabus(text, default_unit=None):
    """Turns a pasted syllabus into [(unit, title), ...] in reading order.

    Lines like 'Unit 1: Introduction', 'UNIT-II Testing techniques' or 'Module 3 - xyz' start a unit.
    Every other non-empty line is a topic in the current unit (bullets and numbering are stripped,
    comma/semicolon-separated lists become separate topics). Parsing stops at 'Text books' / 'References'.
    """
    unit = (default_unit or "").strip()[:MAX_UNIT] or None
    out = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if _STOP_RE.match(_BULLET_RE.sub("", line)):
            break
        header = _parse_unit_header(line)
        if header:
            unit = header
            continue
        for title in _topics_from_line(line):
            out.append((unit, title))
            if len(out) >= MAX_TOPICS_PER_PASTE:
                return out
    return out


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _today():
    return now_ist().date()


def _days_left(subject, today=None):
    if not subject.exam_date:
        return None
    return (subject.exam_date - (today or _today())).days


def _serialize_topic(t):
    return {
        "id": t.id, "subject_id": t.subject_id, "unit": t.unit, "title": t.title, "done": bool(t.done),
        "done_at": _iso(t.done_at), "confidence": t.confidence, "position": t.position or 0,
        "last_studied_at": _iso(t.last_studied_at),
    }


def _group_units(topics):
    units, index = [], {}
    for t in topics:
        if t.unit not in index:
            index[t.unit] = len(units)
            units.append({"unit": t.unit, "topics": []})
        units[index[t.unit]]["topics"].append(_serialize_topic(t))
    return units


def short_name(name):
    """'Next Generation Networking Systems' -> 'NGNS'. None for short names that need no alias."""
    words = [w for w in re.findall(r"[A-Za-z]+", name or "") if w.lower() not in _SMALL_WORDS]
    return "".join(w[0].upper() for w in words) if len(words) >= 3 else None


def _is_theory(s):
    return (s.kind or "theory") == "theory"


def _serialize_subject(s, today=None):
    topics = list(s.topics)
    total = len(topics)
    done = sum(1 for t in topics if t.done)
    return {
        "id": s.id, "name": s.name, "short": short_name(s.name), "code": s.code, "faculty": s.faculty,
        "kind": s.kind or "theory", "color": s.color, "position": s.position or 0,
        "exam_date": s.exam_date.isoformat() if s.exam_date else None,
        "days_left": _days_left(s, today),
        "progress": round(100 * done / total) if total else 0,
        "total": total, "done": done,
        "units": _group_units(topics),
    }


def _sort_key(s, today):
    """Upcoming exams first (nearest first), then subjects without a date, then finished exams."""
    d = _days_left(s, today)
    bucket = 0 if d is not None and d >= 0 else 1 if d is None else 2
    return (bucket, s.exam_date or date.max, s.position or 0, s.id)


def _all_subjects(db):
    today = _today()
    subjects = db.query(Subject).options(selectinload(Subject.topics)).all()
    return sorted(subjects, key=lambda s: _sort_key(s, today)), today


def _next_exam(subjects, today):
    upcoming = [s for s in subjects if _is_theory(s) and s.exam_date and s.exam_date >= today]
    if not upcoming:
        return None
    s = min(upcoming, key=lambda x: (x.exam_date, x.position or 0, x.id))
    return {"id": s.id, "subject": s.name, "short": short_name(s.name), "code": s.code,
            "date": s.exam_date.isoformat(), "days_left": _days_left(s, today)}


def _ensure_seeded(db):
    repo = NotificationRepository(db)
    if db.query(Subject.id).first() is None and repo.get_setting(SEEDED_SETTING) != "1":
        for i, (code, name, faculty, kind, color) in enumerate(SEED_SUBJECTS):
            db.add(Subject(name=name, code=code, faculty=faculty, kind=kind, color=color, position=i))
        db.commit()
        repo.set_setting(SEEDED_SETTING, "1")


def _parse_date(value):
    """Returns (date|None, error)."""
    if value in (None, ""):
        return None, None
    if not isinstance(value, str):
        return None, "exam_date must be a YYYY-MM-DD string."
    try:
        return date.fromisoformat(value.strip()[:10]), None
    except ValueError:
        return None, "exam_date must be a valid date (YYYY-MM-DD)."


def _opt_str(value, limit):
    if value is None:
        return None
    value = str(value).strip()
    return value[:limit] or None


def _apply_subject_fields(s, data, creating=False):
    """Validates and copies fields from `data` onto subject `s`. Returns an error message or None."""
    if creating or "name" in data:
        name = data.get("name")
        name = name.strip() if isinstance(name, str) else ""
        if not name:
            return "Subject name can't be empty."
        if len(name) > MAX_NAME:
            return f"Subject name must be at most {MAX_NAME} characters."
        s.name = name
    if "code" in data:
        s.code = _opt_str(data.get("code"), MAX_CODE)
    if "faculty" in data:
        s.faculty = _opt_str(data.get("faculty"), MAX_NAME)
    if creating or "kind" in data:
        kind = str(data.get("kind") or "theory").strip().lower()
        if kind not in KINDS:
            return "kind must be one of: theory, lab, other."
        s.kind = kind
    if "exam_date" in data:
        d, error = _parse_date(data.get("exam_date"))
        if error:
            return error
        s.exam_date = d
    if "color" in data:
        color = _opt_str(data.get("color"), 20)
        if color and not re.fullmatch(r"#?[A-Za-z0-9\-]{1,19}", color):
            return "color must be a colour name or hex code."
        s.color = color
    if "position" in data:
        try:
            s.position = int(data["position"])
        except (TypeError, ValueError):
            return "position must be an integer."
    return None


def _subject_response(db, s, code=200):
    db.refresh(s)
    return jsonify({"status": "success", "data": _serialize_subject(s)}), code


# ---------------- routes: subjects ----------------
@syllabus_bp.route("", methods=["GET"])
def list_subjects():
    db = SessionLocal()
    try:
        _ensure_seeded(db)
        subjects, today = _all_subjects(db)
        return jsonify({"status": "success", "data": [_serialize_subject(s, today) for s in subjects],
                        "next_exam": _next_exam(subjects, today)})
    finally:
        db.close()


@syllabus_bp.route("/subjects", methods=["POST"])
def create_subject():
    data = _body()
    db = SessionLocal()
    try:
        s = Subject()
        error = _apply_subject_fields(s, data, creating=True)
        if error:
            return _err(error)
        if "position" not in data:
            s.position = (db.query(func.max(Subject.position)).scalar() or 0) + 1
        db.add(s)
        db.commit()
        return _subject_response(db, s, 201)
    finally:
        db.close()


@syllabus_bp.route("/subjects/<int:subject_id>", methods=["PUT", "DELETE"])
def subject_detail(subject_id):
    db = SessionLocal()
    try:
        s = db.get(Subject, subject_id)
        if not s:
            return _err("Subject not found", 404)
        if request.method == "DELETE":
            db.delete(s)  # ORM cascade removes its topics
            db.commit()
            return jsonify({"status": "success"})
        error = _apply_subject_fields(s, _body())
        if error:
            return _err(error)
        db.commit()
        return _subject_response(db, s)
    finally:
        db.close()


# ---------------- routes: topics ----------------
@syllabus_bp.route("/subjects/<int:subject_id>/topics", methods=["POST"])
def add_topics(subject_id):
    data = _body()
    db = SessionLocal()
    try:
        s = db.get(Subject, subject_id)
        if not s:
            return _err("Subject not found", 404)
        unit = data.get("unit") if isinstance(data.get("unit"), str) else None
        if isinstance(data.get("text"), str) and data["text"].strip():
            items = parse_syllabus(data["text"], default_unit=unit)
            if not items:
                return _err("Couldn't find any topics in that text.")
        else:
            title = data.get("title")
            title = re.sub(r"\s+", " ", title).strip() if isinstance(title, str) else ""
            if not title:
                return _err("Topic title can't be empty.")
            if len(title) > MAX_TITLE:
                return _err(f"Topic title must be at most {MAX_TITLE} characters.")
            items = [((unit or "").strip()[:MAX_UNIT] or None, title)]

        pos = db.query(func.max(SyllabusTopic.position)).filter(SyllabusTopic.subject_id == s.id).scalar() or 0
        for u, title in items:
            pos += 1
            db.add(SyllabusTopic(subject_id=s.id, unit=u, title=title, position=pos))
        db.commit()
        resp, code = _subject_response(db, s, 201)
        body = resp.get_json()
        body["added"] = len(items)
        return jsonify(body), code
    finally:
        db.close()


@syllabus_bp.route("/topics/<int:topic_id>", methods=["PUT", "DELETE"])
def topic_detail(topic_id):
    db = SessionLocal()
    try:
        t = db.get(SyllabusTopic, topic_id)
        if not t:
            return _err("Topic not found", 404)
        if request.method == "DELETE":
            db.delete(t)
            db.commit()
            return jsonify({"status": "success"})

        data = _body()
        if "title" in data:
            title = data["title"]
            title = re.sub(r"\s+", " ", title).strip() if isinstance(title, str) else ""
            if not title:
                return _err("Topic title can't be empty.")
            if len(title) > MAX_TITLE:
                return _err(f"Topic title must be at most {MAX_TITLE} characters.")
            t.title = title
        if "unit" in data:
            t.unit = _opt_str(data["unit"], MAX_UNIT)
        if "confidence" in data:
            c = data["confidence"]
            if c is not None and (isinstance(c, bool) or not isinstance(c, int) or not 1 <= c <= 3):
                return _err("confidence must be 1, 2, 3 or null.")
            t.confidence = c
        if "done" in data:
            done = bool(data["done"])
            if done != bool(t.done):
                t.done = done
                t.done_at = _utcnow() if done else None
        if "studied" in data:
            t.last_studied_at = _utcnow() if data["studied"] else None
        db.commit()
        db.refresh(t)
        return jsonify({"status": "success", "data": _serialize_topic(t)})
    finally:
        db.close()


# ---------------- study reminder ----------------
def _study_next(topics, limit=3):
    """Not-done topics: shaky/unrated first, then never studied, then least recently studied, then unit order."""
    pending = [t for t in topics if not t.done]
    pending.sort(key=lambda t: (t.confidence or 1, t.last_studied_at is not None,
                                t.last_studied_at or datetime.min, t.position or 0, t.id))
    return pending[:limit]


def _days_phrase(d):
    if d is None:
        return "no exam date"
    if d < 0:
        return "exam done"
    if d == 0:
        return "exam today"
    if d == 1:
        return "exam tomorrow"
    return f"exam in {d} days"


def _bar_html(pct):
    pct = max(0, min(100, int(pct)))
    color = "#16a34a" if pct >= 100 else "#e8590c"
    cells = ""
    if pct > 0:
        cells += f'<td width="{pct}%" bgcolor="{color}" style="background:{color};height:8px;line-height:8px;font-size:0">&nbsp;</td>'
    if pct < 100:
        cells += f'<td bgcolor="#ececf0" style="background:#ececf0;height:8px;line-height:8px;font-size:0">&nbsp;</td>'
    return (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            f'style="border-collapse:separate;border-radius:4px;overflow:hidden"><tr>{cells}</tr></table>')


def build_reminder(subjects, today):
    """Returns (subject_line, plain_text, html) or None when nothing is left to study.
    Only theory subjects are considered (labs / projects have no end-sem written exam)."""
    with_topics = [s for s in subjects if _is_theory(s) and s.topics]
    total = sum(len(s.topics) for s in with_topics)
    done = sum(1 for s in with_topics for t in s.topics if t.done)
    if not total or done >= total:
        return None
    overall = round(100 * done / total)
    left = total - done

    upcoming = [s for s in with_topics if s.exam_date and s.exam_date >= today and any(not t.done for t in s.topics)]
    nearest = min(upcoming, key=lambda s: s.exam_date) if upcoming else None
    if nearest:
        subject_line = f"📚 Study reminder · {short_name(nearest.name) or nearest.name} {_days_phrase(_days_left(nearest, today))} · {overall}% covered"
    else:
        subject_line = f"📚 Study reminder · {overall}% covered · {left} topic{'s' if left != 1 else ''} left"

    font = "font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    plain = [f"End-sem prep: {overall}% of the syllabus covered ({done}/{total} topics).", ""]
    blocks = []
    for s in with_topics:
        d = _days_left(s, today)
        s_done = sum(1 for t in s.topics if t.done)
        pct = round(100 * s_done / len(s.topics))
        nxt = _study_next(s.topics)
        urgent = d is not None and 0 <= d <= 7
        badge_bg, badge_fg = ("#fde8e8", "#b91c1c") if urgent else ("#fff1e8", "#c2410c") if d is not None and 0 <= d <= 14 else ("#f1f1f3", "#52525b")
        name = h.escape(s.name) + (f' <span style="color:#8a8a94;font-weight:500">{h.escape(s.code)}</span>' if s.code else "")
        date_txt = f" · {s.exam_date.strftime('%a, %d %b')}" if s.exam_date else ""

        plain.append(f"{s.name} ({_days_phrase(d)}{date_txt}) - {pct}% ({s_done}/{len(s.topics)})")
        items = ""
        for t in nxt:
            plain.append(f"  - {t.title}" + (f" [{t.unit}]" if t.unit else ""))
            unit = f'<div style="color:#8a8a94;font-size:12px;margin-top:2px">{h.escape(t.unit)}</div>' if t.unit else ""
            items += (f'<tr><td valign="top" style="padding:6px 8px 6px 0;color:#e8590c;font-size:14px;width:14px">&#9679;</td>'
                      f'<td style="padding:6px 0;{font};font-size:14px;color:#0c0c0f">{h.escape(t.title)}{unit}</td></tr>')
        plain.append("")
        study_next = (f'<div style="{font};font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;'
                      f'color:#8a8a94;margin:14px 0 2px">Study next</div>'
                      f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">{items}</table>') if items else (
                      f'<div style="{font};font-size:13px;color:#16a34a;margin-top:12px;font-weight:600">All topics covered. Revise!</div>')
        blocks.append(
            f'<tr><td style="padding:0 0 14px">'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            f'style="border:1px solid #e4e4e8;border-radius:14px;background:#ffffff"><tr><td style="padding:16px 18px">'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr>'
            f'<td style="{font};font-size:16px;font-weight:700;color:#0c0c0f">{name}</td>'
            f'<td align="right" style="white-space:nowrap"><span style="{font};display:inline-block;padding:3px 8px;border-radius:6px;'
            f'background:{badge_bg};color:{badge_fg};font-size:12px;font-weight:700">{h.escape(_days_phrase(d))}</span></td></tr></table>'
            f'<div style="{font};font-size:12px;color:#8a8a94;margin:4px 0 10px">{pct}% covered · {s_done}/{len(s.topics)} topics{h.escape(date_txt)}</div>'
            f'{_bar_html(pct)}{study_next}</td></tr></table></td></tr>')

    url = f"{APP_URL.rstrip('/')}/#/study"
    plain.append(f"Open your study plan: {url}")
    html_body = (
        f'<div style="background:#f6f6f7;padding:24px 12px">'
        f'<table role="presentation" align="center" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;margin:0 auto">'
        f'<tr><td style="padding:0 4px 16px">'
        f'<div style="{font};font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#e8590c">End-sem prep</div>'
        f'<div style="{font};font-size:24px;font-weight:800;color:#0c0c0f;margin-top:4px">{overall}% of your syllabus covered</div>'
        f'<div style="{font};font-size:14px;color:#52525b;margin:4px 0 12px">{done} of {total} topics done · {left} to go'
        + (f' · next up: <b>{h.escape(nearest.name)}</b> ({h.escape(_days_phrase(_days_left(nearest, today)))})' if nearest else "")
        + f'</div>{_bar_html(overall)}</td></tr>'
        + "".join(blocks)
        + f'<tr><td align="center" style="padding:8px 0 4px">'
        f'<a href="{h.escape(url)}" style="{font};display:inline-block;background:#e8590c;color:#ffffff;text-decoration:none;'
        f'font-weight:700;font-size:15px;padding:12px 22px;border-radius:12px">Open study plan</a></td></tr>'
        f'<tr><td align="center" style="{font};font-size:12px;color:#8a8a94;padding-top:12px">One topic at a time. You\'ve got this.</td></tr>'
        f'</table></div>')
    return subject_line, "\n".join(plain), html_body


def send_study_reminder(db, force=False):
    """Sends the reminder email. Returns {"status": "success"|"skipped"|"error", "message": ...}.
    Usable from a cron job as well as the HTTP route."""
    repo = NotificationRepository(db)
    sender, password = os.getenv("SENDER_EMAIL"), os.getenv("SENDER_PASSWORD")
    if not (sender and password):
        return {"status": "skipped", "message": "Email isn't configured (set SENDER_EMAIL / SENDER_PASSWORD)."}

    subjects, today = _all_subjects(db)
    built = build_reminder(subjects, today)
    if not built:
        return {"status": "skipped", "message": "Nothing left to study. Add topics or enjoy the break."}

    if not force:
        last = repo.get_setting(REMIND_SETTING)
        if last:
            try:
                elapsed = _utcnow() - datetime.fromisoformat(last)
            except ValueError:
                elapsed = REMIND_COOLDOWN
            if elapsed < REMIND_COOLDOWN:
                hours = elapsed.total_seconds() / 3600
                return {"status": "skipped", "message": f"Last reminder went out {hours:.0f}h ago (limit: one per 36h)."}

    subject_line, plain, html_body = built
    if not EmailClient(sender, password).send_email(RECEIVER_EMAIL, subject_line, plain, html=html_body):
        return {"status": "error", "message": "Failed to send email. Check SENDER_EMAIL / SENDER_PASSWORD."}
    repo.set_setting(REMIND_SETTING, _utcnow().isoformat(timespec="seconds"))
    return {"status": "success", "message": f"Reminder sent to {RECEIVER_EMAIL}", "subject": subject_line}


@syllabus_bp.route("/remind", methods=["POST"])
def remind():
    force = request.args.get("force", "").lower() in ("1", "true", "yes")
    db = SessionLocal()
    try:
        result = send_study_reminder(db, force=force)
        if result["status"] == "error":
            return _err(result["message"], 502)
        return jsonify(result)
    finally:
        db.close()
