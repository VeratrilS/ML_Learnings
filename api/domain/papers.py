"""
Past-paper predictor for end-sem exams.

Old question papers (PDF pages rendered to images in the browser, or photos) are read by Gemini,
which pulls out every question with its marks and maps it onto the subject's syllabus topics.
A deterministic ranking then surfaces "high-yield & weak" topics:

    priority = Σ (marks or 5) × year_weight  ×  (1 − recall)

where year_weight is 1.5 for the two most recent exam years on file, and recall is the
forgetting-curve estimate from the topic's confidence and when it was last studied
(conf 1/2/3 → stability 2/6/15 days, R = (1 + t / 9S)^-1, never studied → 0).
"""
import base64
import binascii
import difflib
import hashlib
import json
import re
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import relationship, selectinload

from api.core.clients import LLMClient
from api.core.db import Base, SessionLocal, engine
from api.domain.syllabus import Subject, SyllabusTopic

MAX_IMAGES = 12
MAX_TEXT = 30000
MAX_QUESTIONS = 80
MAX_Q_TEXT = 2000
MAX_LABEL = 120
MAX_YEAR = 20
MAX_UNIT = 120
DEFAULT_MARKS = 5.0
RECENT_WEIGHT = 1.5
RECENT_YEARS = 2          # the N most recent exam years on file count as "recent"
TOP_N = 8
STABILITY_DAYS = {1: 2.0, 2: 6.0, 3: 15.0}

EXTRACT_SYSTEM = (
    "You digitise university exam question papers. Extract every question a student must answer, "
    "including sub-parts as separate questions when they carry their own marks (e.g. 1(a), 1(b)). "
    "Skip instructions, headers, roll-number boxes and page furniture. Keep each question's wording "
    "faithful but concise (no 'Q1.' prefixes). Never invent questions."
)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------- models ----------------
class PastPaper(Base):
    __tablename__ = "past_papers"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    year = Column(String(MAX_YEAR), nullable=False)
    label = Column(String(MAX_LABEL), nullable=True)
    hash = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=_utcnow)  # naive UTC

    questions = relationship("PaperQuestion", back_populates="paper", cascade="all, delete-orphan",
                             passive_deletes=True, order_by="PaperQuestion.id")

    def __repr__(self):
        return f"<PastPaper(id={self.id}, subject_id={self.subject_id}, year={self.year!r})>"


class PaperQuestion(Base):
    __tablename__ = "paper_questions"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("past_papers.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    marks = Column(Float, nullable=True)
    topic_id = Column(Integer, ForeignKey("syllabus_topics.id", ondelete="SET NULL"), nullable=True, index=True)
    unit = Column(String(MAX_UNIT), nullable=True)

    paper = relationship("PastPaper", back_populates="questions")

    def __repr__(self):
        return f"<PaperQuestion(id={self.id}, paper_id={self.paper_id}, topic_id={self.topic_id})>"


papers_bp = Blueprint("papers", __name__, url_prefix="/api/papers")


@papers_bp.record_once
def _ensure_tables(state):
    """Create the tables when the blueprint is registered, so wiring it in needs no extra step."""
    try:
        Base.metadata.create_all(bind=engine, tables=[Subject.__table__, SyllabusTopic.__table__,
                                                      PastPaper.__table__, PaperQuestion.__table__])
    except Exception as e:  # e.g. a concurrent cold start created them first
        print(f"papers table check skipped: {e}")


# ---------------- pure helpers (tested directly) ----------------
def stability(confidence, done=False):
    """Stability S in days. Unrated topics count as 'okay' when done, 'shaky' otherwise."""
    if confidence not in STABILITY_DAYS:
        confidence = 2 if done else 1
    return STABILITY_DAYS[confidence]


def recall(confidence, done, last_studied_at, now=None):
    """R = (1 + t / (9 S))^-1 with t in days since last studied; never studied -> 0."""
    if last_studied_at is None:
        return 0.0
    t = max(0.0, ((now or _utcnow()) - last_studied_at).total_seconds() / 86400.0)
    return 1.0 / (1.0 + t / (9.0 * stability(confidence, done)))


def year_number(year):
    """'2023', 'Nov 2022', '2021-22' -> first 4-digit year as int, else None."""
    m = re.search(r"(?<!\d)(19|20)\d{2}(?!\d)", year or "")
    return int(m.group(0)) if m else None


def year_weights(years):
    """{year string: weight}. The RECENT_YEARS most recent distinct numeric years get RECENT_WEIGHT."""
    nums = sorted({n for n in (year_number(y) for y in years) if n is not None}, reverse=True)
    recent = set(nums[:RECENT_YEARS])
    return {y: (RECENT_WEIGHT if year_number(y) in recent else 1.0) for y in years}


def rank_topics(topics, questions, now=None):
    """topics: SyllabusTopic-like objects; questions: [(topic_id, marks, year, paper_id)].
    Returns (ranked topic dicts, unmapped question count). Deterministic."""
    by_id = {t.id: t for t in topics}
    weights = year_weights({q[2] for q in questions})
    acc, unmapped = {}, 0
    for topic_id, marks, year, paper_id in questions:
        if topic_id not in by_id:
            unmapped += 1
            continue
        a = acc.setdefault(topic_id, {"appearances": 0, "total_marks": 0.0, "weighted": 0.0,
                                      "papers": set(), "years": set()})
        m = marks if marks and marks > 0 else DEFAULT_MARKS
        a["appearances"] += 1
        a["total_marks"] += m
        a["weighted"] += m * weights.get(year, 1.0)
        a["papers"].add(paper_id)
        a["years"].add(year)

    ranked = []
    for topic_id, a in acc.items():
        t = by_id[topic_id]
        r = recall(t.confidence, bool(t.done), t.last_studied_at, now)
        ranked.append({
            "topic_id": t.id, "title": t.title, "unit": t.unit,
            "appearances": a["appearances"], "paper_count": len(a["papers"]),
            "years": sorted(a["years"], key=lambda y: (year_number(y) or 0, y), reverse=True),
            "total_marks": round(a["total_marks"], 1),
            "recall": round(r, 3),
            "priority": round(a["weighted"] * (1.0 - r), 2),
            "confidence": t.confidence, "done": bool(t.done),
            "last_studied_at": _iso(t.last_studied_at),
            "_pos": (t.position or 0, t.id),
        })
    ranked.sort(key=lambda x: (-x["priority"], -x["total_marks"], -x["appearances"], x["_pos"]))
    for x in ranked:
        del x["_pos"]
    return ranked, unmapped


def parse_marks(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        m = float(value)
    else:
        found = re.search(r"\d+(?:\.\d+)?", str(value))
        if not found:
            return None
        m = float(found.group(0))
    return m if 0 < m <= 100 else None


def match_topic(topic_id, guess, topics):
    """Validates the LLM's topic_id against the subject; falls back to fuzzy-matching its title guess."""
    by_id = {t.id: t for t in topics}
    try:
        tid = int(topic_id) if topic_id is not None and not isinstance(topic_id, bool) else None
    except (TypeError, ValueError):
        tid = None
    if tid in by_id:
        return by_id[tid]
    guess = re.sub(r"\s+", " ", str(guess or "")).strip().lower()
    if not guess or not topics:
        return None
    titles = {t.title.strip().lower(): t for t in topics}
    if guess in titles:
        return titles[guess]
    close = difflib.get_close_matches(guess, list(titles), n=1, cutoff=0.82)
    return titles[close[0]] if close else None


def content_hash(subject_id, images, text):
    h = hashlib.sha256(f"paper:{subject_id}\n".encode())
    for img in images:
        h.update(img.encode() if isinstance(img, str) else img)
        h.update(b"\x00")
    h.update(re.sub(r"\s+", " ", text or "").strip().encode())
    return h.hexdigest()


def _decode_image(img):
    """Returns (bytes, mime). Raises ValueError on bad input."""
    if not isinstance(img, str) or not img:
        raise ValueError("bad image")
    mime = "image/jpeg"
    if img.startswith("data:"):
        head, _, img = img.partition(",")
        m = re.match(r"data:(image/[a-z0-9.+-]+)", head, re.IGNORECASE)
        if m:
            mime = m.group(1).lower()
    try:
        return base64.b64decode(img, validate=False), mime
    except (binascii.Error, ValueError) as e:
        raise ValueError("bad image") from e


# ---------------- request helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _int_arg(name):
    raw = request.args.get(name)
    try:
        return int(raw) if raw not in (None, "") else None
    except ValueError:
        return False


def _serialize_question(q, topics_by_id):
    t = topics_by_id.get(q.topic_id)
    return {"id": q.id, "paper_id": q.paper_id, "text": q.text, "marks": q.marks,
            "topic_id": t.id if t else None, "topic_title": t.title if t else None,
            "unit": (t.unit if t else None) or q.unit}


def _serialize_paper(p, topics_by_id):
    qs = list(p.questions)
    return {
        "id": p.id, "subject_id": p.subject_id, "year": p.year, "label": p.label,
        "created_at": _iso(p.created_at), "question_count": len(qs),
        "mapped_count": sum(1 for q in qs if q.topic_id in topics_by_id),
        "total_marks": round(sum(q.marks or 0 for q in qs), 1),
        "questions": [_serialize_question(q, topics_by_id) for q in qs],
    }


def _subject_topics(db, subject_id):
    return (db.query(SyllabusTopic).filter(SyllabusTopic.subject_id == subject_id)
            .order_by(SyllabusTopic.position, SyllabusTopic.id).all())


def _papers_for(db, subject_id):
    q = db.query(PastPaper).options(selectinload(PastPaper.questions))
    if subject_id is not None:
        q = q.filter(PastPaper.subject_id == subject_id)
    papers = q.all()
    papers.sort(key=lambda p: (year_number(p.year) or 0, p.created_at or datetime.min, p.id), reverse=True)
    return papers


def _topics_by_id_for(db, papers):
    ids = {q.topic_id for p in papers for q in p.questions if q.topic_id is not None}
    if not ids:
        return {}
    return {t.id: t for t in db.query(SyllabusTopic).filter(SyllabusTopic.id.in_(ids)).all()}


# ---------------- LLM extraction ----------------
def _build_prompt(subject, topics, year, label, text):
    topic_list = [{"id": t.id, "title": t.title, "unit": t.unit} for t in topics]
    return (
        f"Subject: {subject.name}" + (f" ({subject.code})" if subject.code else "") + "\n"
        f"Paper: {label or 'End-sem'} {year}\n\n"
        "Syllabus topics (map each question to the single best-matching topic id from THIS list, "
        "or null if none fits):\n"
        f"{json.dumps(topic_list, ensure_ascii=False)}\n\n"
        "Return JSON exactly like: {\"questions\": [{\"text\": str, \"marks\": number or null, "
        "\"topic_id\": int or null, \"topic_title_guess\": str, \"unit\": str or null}]}. "
        "marks = marks printed for that question/sub-part (null if not shown). "
        "topic_title_guess = the syllabus topic title you matched (or a short topic name if none fits). "
        f"At most {MAX_QUESTIONS} questions, in paper order."
        + (f"\n\nText extracted from the paper (may be imperfect; trust the images when they disagree):\n{text[:MAX_TEXT]}"
           if text.strip() else "")
    )


def extract_questions(llm, subject, topics, year, label, images, text):
    """Calls the LLM and returns cleaned [{text, marks, topic, unit}]. Raises RuntimeError on LLM failure."""
    contents = [_build_prompt(subject, topics, year, label, text)]
    for data, mime in images:
        contents.append(llm.image_part(data, mime))
    raw = llm.generate_json(contents if images else contents[0], temperature=0.1,
                            system=EXTRACT_SYSTEM, thinking="low")
    items = raw.get("questions") if isinstance(raw, dict) else raw if isinstance(raw, list) else None
    if not isinstance(items, list):
        return []
    out = []
    for it in items[:MAX_QUESTIONS]:
        if not isinstance(it, dict):
            continue
        q_text = re.sub(r"[ \t]+", " ", str(it.get("text") or "")).strip()
        if len(q_text) < 3:
            continue
        topic = match_topic(it.get("topic_id"), it.get("topic_title_guess"), topics)
        unit = topic.unit if topic else (str(it.get("unit")).strip()[:MAX_UNIT] or None if it.get("unit") else None)
        out.append({"text": q_text[:MAX_Q_TEXT], "marks": parse_marks(it.get("marks")), "topic": topic, "unit": unit})
    return out


# ---------------- routes ----------------
@papers_bp.route("", methods=["GET"])
def list_papers():
    subject_id = _int_arg("subject_id")
    if subject_id is False:
        return _err("subject_id must be an integer.")
    db = SessionLocal()
    try:
        papers = _papers_for(db, subject_id)
        topics_by_id = _topics_by_id_for(db, papers)
        return jsonify({"status": "success", "data": [_serialize_paper(p, topics_by_id) for p in papers]})
    finally:
        db.close()


@papers_bp.route("/extract", methods=["POST"])
def extract_paper():
    data = _body()
    subject_id = data.get("subject_id")
    if isinstance(subject_id, bool) or not isinstance(subject_id, int):
        return _err("subject_id is required.")
    year = re.sub(r"\s+", " ", str(data.get("year") or "")).strip()
    if not year:
        return _err("Which year is this paper from?")
    if len(year) > MAX_YEAR:
        return _err(f"year must be at most {MAX_YEAR} characters.")
    label = re.sub(r"\s+", " ", str(data.get("label") or "")).strip()[:MAX_LABEL] or None
    raw_images = data.get("images") or []
    if not isinstance(raw_images, list):
        return _err("images must be a list of base64 images.")
    if len(raw_images) > MAX_IMAGES:
        return _err(f"At most {MAX_IMAGES} pages per paper.")
    text = data.get("text") if isinstance(data.get("text"), str) else ""
    text = text[:MAX_TEXT]
    meaningful = re.sub(r"---\s*Page \d+\s*---|\(no extractable text\)|\s+", "", text)
    if not raw_images and not meaningful:
        return _err("Upload the paper's pages (PDF or photos) or paste its text.")
    try:
        images = [_decode_image(i) for i in raw_images]
    except ValueError:
        return _err("One of the pages isn't a valid base64 image.")

    db = SessionLocal()
    try:
        subject = db.get(Subject, subject_id)
        if not subject:
            return _err("Subject not found", 404)
        digest = content_hash(subject_id, raw_images, text)
        existing = db.query(PastPaper).filter(PastPaper.hash == digest).first()
        if existing:
            topics_by_id = _topics_by_id_for(db, [existing])
            return jsonify({"status": "success", "cached": True, "data": _serialize_paper(existing, topics_by_id)})

        topics = _subject_topics(db, subject_id)
        try:
            questions = extract_questions(LLMClient(), subject, topics, year, label, images, text)
        except Exception as e:
            print(f"paper extraction failed: {e}")
            return _err("Gemini couldn't read this paper right now (it may be busy on the free tier). "
                        "Try again in a minute.", 502)
        if not questions:
            return _err("No questions found in that upload. Check the pages are the question paper and readable.", 422)

        paper = PastPaper(subject_id=subject_id, year=year, label=label, hash=digest)
        db.add(paper)
        db.flush()
        for q in questions:
            db.add(PaperQuestion(paper_id=paper.id, text=q["text"], marks=q["marks"],
                                 topic_id=q["topic"].id if q["topic"] else None, unit=q["unit"]))
        try:
            db.commit()
        except IntegrityError:  # the same paper finished uploading in a parallel request
            db.rollback()
            paper = db.query(PastPaper).filter(PastPaper.hash == digest).first()
            if not paper:
                raise
            return jsonify({"status": "success", "cached": True,
                            "data": _serialize_paper(paper, _topics_by_id_for(db, [paper]))})
        db.refresh(paper)
        topics_by_id = {t.id: t for t in topics}
        return jsonify({"status": "success", "cached": False, "data": _serialize_paper(paper, topics_by_id)}), 201
    finally:
        db.close()


@papers_bp.route("/<int:paper_id>", methods=["DELETE"])
def delete_paper(paper_id):
    db = SessionLocal()
    try:
        p = db.get(PastPaper, paper_id)
        if not p:
            return _err("Paper not found", 404)
        db.delete(p)  # ORM cascade removes its questions
        db.commit()
        return jsonify({"status": "success"})
    finally:
        db.close()


@papers_bp.route("/questions/<int:question_id>", methods=["PUT"])
def update_question(question_id):
    data = _body()
    db = SessionLocal()
    try:
        q = db.get(PaperQuestion, question_id)
        if not q:
            return _err("Question not found", 404)
        if "topic_id" in data:
            tid = data["topic_id"]
            if tid is None:
                q.topic_id = None
            else:
                if isinstance(tid, bool) or not isinstance(tid, int):
                    return _err("topic_id must be a topic id or null.")
                t = db.get(SyllabusTopic, tid)
                if not t or t.subject_id != q.paper.subject_id:
                    return _err("That topic isn't in this paper's subject.")
                q.topic_id = t.id
                q.unit = t.unit
        if "marks" in data:
            if data["marks"] is None:
                q.marks = None
            else:
                m = parse_marks(data["marks"])
                if m is None:
                    return _err("marks must be a number between 0 and 100, or null.")
                q.marks = m
        db.commit()
        db.refresh(q)
        topics_by_id = {q.topic_id: db.get(SyllabusTopic, q.topic_id)} if q.topic_id else {}
        return jsonify({"status": "success", "data": _serialize_question(q, topics_by_id)})
    finally:
        db.close()


@papers_bp.route("/predict", methods=["GET"])
def predict():
    subject_id = _int_arg("subject_id")
    if not subject_id:
        return _err("subject_id is required.")
    db = SessionLocal()
    try:
        subject = db.get(Subject, subject_id)
        if not subject:
            return _err("Subject not found", 404)
        topics = _subject_topics(db, subject_id)
        papers = _papers_for(db, subject_id)
        rows = [(q.topic_id, q.marks, p.year, p.id) for p in papers for q in p.questions]
        ranked, unmapped = rank_topics(topics, rows)
        weights = year_weights({p.year for p in papers})
        return jsonify({
            "status": "success",
            "data": {
                "subject_id": subject_id,
                "papers": len(papers),
                "questions": len(rows),
                "unmapped": unmapped,
                "recent_years": sorted([y for y, w in weights.items() if w > 1.0],
                                       key=lambda y: (year_number(y) or 0, y), reverse=True),
                "topics": ranked,
                "high_yield_weak": [t for t in ranked if t["priority"] > 0][:TOP_N],
            },
        })
    finally:
        db.close()
