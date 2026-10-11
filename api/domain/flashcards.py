"""
CS-fundamentals flashcards (OS / DBMS / CN / OOP / SQL) with FSRS-lite spaced repetition.

Memory model per card:
- stability S (days): the interval after which recall probability R falls to 90%.
  R(t) = (1 + t / (9 S))^-1, so R(S) = 0.9 and a card is due S days after its last review.
- difficulty_fsrs D (1..10): how hard the card is for *you*; it scales how fast S grows.

The curated starter deck (api/domain/flashcard_deck.py) is seeded on the first GET.
"""
import math
import re
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, func

from api.core.clients import LLMClient
from api.core.config import IST, now_ist
from api.core.db import Base, SessionLocal, engine
from api.domain.flashcard_deck import DECK
from api.domain.repositories import NotificationRepository

SUBJECTS = ("OS", "DBMS", "CN", "OOP", "SQL")
GRADES = ("again", "hard", "good", "easy")
SOURCES = ("seed", "ai", "user")
MAX_Q, MAX_A, MAX_TAGS, MAX_SUBJECT = 500, 4000, 200, 40
S_MIN, S_MAX = 0.2, 365.0
D_MIN, D_MAX = 1.0, 10.0
MASTERED_S = 21.0
INITIAL_S = {"again": 0.2, "hard": 1.0, "good": 2.5, "easy": 5.0}
INITIAL_D = {"again": 7.0, "hard": 6.0, "good": 5.0, "easy": 3.5}
D_DELTA = {"again": 1.2, "hard": 0.5, "good": -0.1, "easy": -0.8}
GROWTH = 1.6          # an on-time 'good' at D=5, S=2.5 multiplies S by ~2.4
HARD_SHARE = 0.35     # 'hard' gets 35% of the growth 'good' would
EASY_BONUS = 1.8      # 'easy' gets 180%
LAPSE_KEEP = 0.25     # 'again' keeps a quarter of the stability
DEFAULT_NEW_PER_DAY = 10


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Flashcard(Base):
    __tablename__ = "flashcards"

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String(MAX_SUBJECT), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    tags = Column(String(MAX_TAGS), default="", nullable=False)  # comma-separated
    difficulty = Column(Integer, default=2, nullable=False)  # content difficulty 1-3
    source = Column(String(10), default="user", nullable=False)  # seed | ai | user
    stability = Column(Float, nullable=True)  # None until first review
    difficulty_fsrs = Column(Float, nullable=True)
    due_at = Column(DateTime, nullable=True, index=True)  # naive UTC; None = new
    reps = Column(Integer, default=0, nullable=False)
    lapses = Column(Integer, default=0, nullable=False)
    last_review_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    def __repr__(self):
        return f"<Flashcard(id={self.id}, subject={self.subject}, reps={self.reps})>"


class CardReview(Base):
    __tablename__ = "card_reviews"

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, nullable=False, index=True)
    grade = Column(String(10), nullable=False)
    at = Column(DateTime, default=_utcnow, nullable=False, index=True)  # naive UTC


flashcards_bp = Blueprint("flashcards", __name__, url_prefix="/api/cards")


@flashcards_bp.record_once
def _ensure_tables(state):
    """Create the tables when the blueprint is registered, so wiring it in needs no extra step."""
    for model in (Flashcard, CardReview):
        try:
            model.__table__.create(bind=engine, checkfirst=True)
        except Exception as e:  # e.g. a concurrent cold start created it first
            print(f"{model.__tablename__} table check skipped: {e}")


# ---------------- FSRS-lite ----------------
def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def recall_probability(stability, elapsed_days):
    if not stability:
        return 0.0
    return (1.0 + max(0.0, elapsed_days) / (9.0 * stability)) ** -1


def next_state(stability, difficulty, elapsed_days, grade):
    """Returns (new_stability, new_difficulty). `stability=None` means a brand-new card.

    For one prior state, the resulting stability is strictly monotone: again < hard < good < easy
    (until the S_MAX cap).
    """
    if grade not in GRADES:
        raise ValueError(f"grade must be one of {GRADES}")
    if not stability:
        return INITIAL_S[grade], INITIAL_D[grade]
    d0 = difficulty if difficulty is not None else 5.0
    d = d0 + D_DELTA[grade]
    d = _clamp(0.9 * d + 0.1 * 5.0, D_MIN, D_MAX)  # gentle mean reversion so D never gets stuck
    if grade == "again":
        return _clamp(stability * LAPSE_KEEP, S_MIN, min(stability, S_MAX)), d
    r = recall_probability(stability, elapsed_days)
    spacing = _clamp((1.0 - r) / 0.1, 0.3, 2.0)  # 1.0 on time; early reviews grow less, late ones more
    gain = GROWTH * ((11.0 - d) / 6.0) * stability ** -0.15 * spacing
    factor = {"hard": HARD_SHARE, "good": 1.0, "easy": EASY_BONUS}[grade]
    return _clamp(stability * (1.0 + factor * gain), S_MIN, S_MAX), d


def _elapsed_days(card, now):
    if card.last_review_at is None:
        return 0.0
    return max(0.0, (now - card.last_review_at).total_seconds() / 86400.0)


def preview(card, now):
    """Interval in days each grade would schedule next."""
    t = _elapsed_days(card, now)
    return {g: round(next_state(card.stability, card.difficulty_fsrs, t, g)[0], 3) for g in GRADES}


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _words(text):
    return set(_norm(text).split())


def _is_dupe(question, seen_norms, seen_words):
    n = _norm(question)
    if not n or n in seen_norms:
        return True
    w = _words(question)
    if len(w) >= 4:
        for other in seen_words:
            if other and len(w & other) / len(w | other) >= 0.85:
                return True
    return False


def _state(card):
    if not card.reps:
        return "new"
    if (card.stability or 0) >= MASTERED_S:
        return "mastered"
    if (card.stability or 0) < 1.0:
        return "learning"
    return "review"


def _serialize(c, now=None):
    now = now or _utcnow()
    return {
        "id": c.id,
        "subject": c.subject,
        "question": c.question,
        "answer": c.answer,
        "tags": [t for t in (c.tags or "").split(",") if t],
        "difficulty": c.difficulty,
        "source": c.source,
        "stability": round(c.stability, 3) if c.stability else None,
        "difficulty_fsrs": round(c.difficulty_fsrs, 2) if c.difficulty_fsrs is not None else None,
        "due_at": _iso(c.due_at),
        "reps": c.reps or 0,
        "lapses": c.lapses or 0,
        "last_review_at": _iso(c.last_review_at),
        "created_at": _iso(c.created_at),
        "state": _state(c),
        "retrievability": round(recall_probability(c.stability, _elapsed_days(c, now)), 3) if c.reps else None,
        "preview": preview(c, now),
    }


def _canon_subject(value):
    s = value.strip() if isinstance(value, str) else ""
    for known in SUBJECTS:
        if s.lower() == known.lower():
            return known, None
    if not s:
        return None, "Subject is required."
    if len(s) > MAX_SUBJECT:
        return None, f"Subject must be at most {MAX_SUBJECT} characters."
    return s, None


def _clean_tags(value):
    if isinstance(value, list):
        parts = [str(v) for v in value]
    elif isinstance(value, str):
        parts = value.split(",")
    else:
        parts = []
    tags = []
    for p in parts:
        t = re.sub(r"\s+", "-", p.strip().lower())[:30]
        if t and t not in tags:
            tags.append(t)
    return ",".join(tags)[:MAX_TAGS]


def _clean_difficulty(value, default=2):
    try:
        return int(_clamp(int(value), 1, 3))
    except (TypeError, ValueError):
        return default


def _clean_text(value, name, limit):
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        return None, f"{name} can't be empty."
    if len(text) > limit:
        return None, f"{name} must be at most {limit} characters."
    return text, None


def _ist_day_start_utc(now_local):
    start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


def _ensure_seeded(db):
    repo = NotificationRepository(db)
    if repo.get_setting("cards_seeded") == "1":
        return
    existing = {_norm(q) for (q,) in db.query(Flashcard.question).all()}
    for row in DECK:
        if _norm(row["question"]) in existing:
            continue
        db.add(Flashcard(subject=row["subject"], question=row["question"], answer=row["answer"],
                         tags=_clean_tags(row["tags"]), difficulty=row["difficulty"], source="seed"))
    db.commit()
    repo.set_setting("cards_seeded", "1")


def _new_per_day(db):
    raw = NotificationRepository(db).get_setting("cards_new_per_day")
    try:
        return int(_clamp(int(raw), 0, 100)) if raw is not None else DEFAULT_NEW_PER_DAY
    except (TypeError, ValueError):
        return DEFAULT_NEW_PER_DAY


def _interleave(cards):
    """Round-robin across subjects, keeping each subject's own order."""
    buckets = {}
    for c in cards:
        buckets.setdefault(c.subject, []).append(c)
    out, queues = [], list(buckets.values())
    while queues:
        for q in queues:
            out.append(q.pop(0))
        queues = [q for q in queues if q]
    return out


def _streak(db, now_local):
    since = _ist_day_start_utc(now_local) - timedelta(days=400)
    days = {
        at.replace(tzinfo=timezone.utc).astimezone(IST).date()
        for (at,) in db.query(CardReview.at).filter(CardReview.at >= since).all()
    }
    day = now_local.date()
    if day not in days:
        day -= timedelta(days=1)  # today not done yet: the streak is still alive from yesterday
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def _counts(db, now, now_local):
    day_start = _ist_day_start_utc(now_local)
    done_today = db.query(func.count(CardReview.id)).filter(CardReview.at >= day_start).scalar() or 0
    firsts = (db.query(CardReview.card_id)
              .group_by(CardReview.card_id)
              .having(func.min(CardReview.at) >= day_start)
              .all())
    new_today = len(firsts)
    unseen = db.query(func.count(Flashcard.id)).filter(Flashcard.reps == 0).scalar() or 0
    due = (db.query(func.count(Flashcard.id))
           .filter(Flashcard.reps > 0, Flashcard.due_at <= now).scalar() or 0)
    per_day = _new_per_day(db)
    return {
        "due": due,
        "new": min(unseen, max(0, per_day - new_today)),
        "new_per_day": per_day,
        "new_today": new_today,
        "done_today": done_today,
        "streak": _streak(db, now_local),
        "total": db.query(func.count(Flashcard.id)).scalar() or 0,
    }


def _subject_stats(db, now):
    stats = {}
    for c in db.query(Flashcard).all():
        s = stats.setdefault(c.subject, {"subject": c.subject, "total": 0, "mastered": 0, "due": 0, "new": 0})
        s["total"] += 1
        if not c.reps:
            s["new"] += 1
        else:
            if (c.stability or 0) >= MASTERED_S:
                s["mastered"] += 1
            if c.due_at and c.due_at <= now:
                s["due"] += 1
    order = {s: i for i, s in enumerate(SUBJECTS)}
    out = sorted(stats.values(), key=lambda s: (order.get(s["subject"], len(order)), s["subject"]))
    for s in out:
        s["mastery"] = round(100 * s["mastered"] / s["total"]) if s["total"] else 0
    return out


# ---------------- routes ----------------
@flashcards_bp.route("/today", methods=["GET"])
def today_queue():
    try:
        limit = int(_clamp(int(request.args.get("limit", 20)), 1, 100))
    except (TypeError, ValueError):
        limit = 20
    subject = (request.args.get("subject") or "").strip()
    db = SessionLocal()
    try:
        _ensure_seeded(db)
        now, now_local = _utcnow(), now_ist()
        counts = _counts(db, now, now_local)
        due_q = db.query(Flashcard).filter(Flashcard.reps > 0, Flashcard.due_at <= now)
        new_q = db.query(Flashcard).filter(Flashcard.reps == 0)
        if subject:
            due_q = due_q.filter(Flashcard.subject == subject)
            new_q = new_q.filter(Flashcard.subject == subject)
        due = due_q.order_by(Flashcard.due_at, Flashcard.id).limit(limit).all()
        room = min(counts["new"], limit - len(due))
        fresh = []
        if room > 0:
            # Take a balanced slice per subject (seed order within each) so new cards span subjects.
            subjects = [s for (s,) in new_q.with_entities(Flashcard.subject).distinct().all()]
            pool = []
            for s in subjects:
                pool += new_q.filter(Flashcard.subject == s).order_by(Flashcard.id).limit(room).all()
            fresh = _interleave(sorted(pool, key=lambda c: c.id))[:room]
        queue = _interleave(due + fresh)
        return jsonify({
            "status": "success",
            "data": [_serialize(c, now) for c in queue],
            "counts": counts,
            "subjects": _subject_stats(db, now),
        })
    finally:
        db.close()


@flashcards_bp.route("/<int:card_id>/review", methods=["POST"])
def review_card(card_id):
    grade = _body().get("grade")
    if grade not in GRADES:
        return _err(f"grade must be one of: {', '.join(GRADES)}.")
    db = SessionLocal()
    try:
        c = db.get(Flashcard, card_id)
        if not c:
            return _err("Not found", 404)
        now = _utcnow()
        s, d = next_state(c.stability, c.difficulty_fsrs, _elapsed_days(c, now), grade)
        if grade == "again" and c.reps:
            c.lapses = (c.lapses or 0) + 1
        c.stability, c.difficulty_fsrs = s, d
        c.reps = (c.reps or 0) + 1
        c.last_review_at = now
        c.due_at = now + timedelta(days=s)
        db.add(CardReview(card_id=c.id, grade=grade, at=now))
        db.commit()
        db.refresh(c)
        return jsonify({"status": "success", "data": _serialize(c, now), "interval_days": round(s, 3)})
    finally:
        db.close()


@flashcards_bp.route("", methods=["GET"])
def list_cards():
    subject = (request.args.get("subject") or "").strip()
    q = _norm(request.args.get("q"))
    db = SessionLocal()
    try:
        _ensure_seeded(db)
        now = _utcnow()
        query = db.query(Flashcard)
        if subject:
            query = query.filter(Flashcard.subject == subject)
        cards = query.order_by(Flashcard.subject, Flashcard.id).all()
        if q:
            cards = [c for c in cards if q in _norm(f"{c.question} {c.answer} {c.tags}")]
        return jsonify({
            "status": "success",
            "data": [_serialize(c, now) for c in cards],
            "subjects": _subject_stats(db, now),
            "counts": _counts(db, now, now_ist()),
        })
    finally:
        db.close()


@flashcards_bp.route("", methods=["POST"])
def create_card():
    data = _body()
    subject, error = _canon_subject(data.get("subject"))
    if error:
        return _err(error)
    question, error = _clean_text(data.get("question"), "Question", MAX_Q)
    if error:
        return _err(error)
    answer, error = _clean_text(data.get("answer"), "Answer", MAX_A)
    if error:
        return _err(error)
    db = SessionLocal()
    try:
        c = Flashcard(subject=subject, question=question, answer=answer, tags=_clean_tags(data.get("tags")),
                      difficulty=_clean_difficulty(data.get("difficulty")), source="user")
        db.add(c)
        db.commit()
        db.refresh(c)
        return jsonify({"status": "success", "data": _serialize(c)})
    finally:
        db.close()


@flashcards_bp.route("/<int:card_id>", methods=["PUT", "DELETE"])
def card_detail(card_id):
    db = SessionLocal()
    try:
        c = db.get(Flashcard, card_id)
        if not c:
            return _err("Not found", 404)
        if request.method == "DELETE":
            db.query(CardReview).filter(CardReview.card_id == c.id).delete()
            db.delete(c)
            db.commit()
            return jsonify({"status": "success"})
        data = _body()
        if "subject" in data:
            c.subject, error = _canon_subject(data["subject"])
            if error:
                return _err(error)
        if "question" in data:
            c.question, error = _clean_text(data["question"], "Question", MAX_Q)
            if error:
                return _err(error)
        if "answer" in data:
            c.answer, error = _clean_text(data["answer"], "Answer", MAX_A)
            if error:
                return _err(error)
        if "tags" in data:
            c.tags = _clean_tags(data["tags"])
        if "difficulty" in data:
            c.difficulty = _clean_difficulty(data["difficulty"], c.difficulty)
        if data.get("reset"):
            c.stability = c.difficulty_fsrs = c.due_at = c.last_review_at = None
            c.reps = c.lapses = 0
        db.commit()
        db.refresh(c)
        return jsonify({"status": "success", "data": _serialize(c)})
    finally:
        db.rollback()
        db.close()


GEN_SYSTEM = (
    "You write flashcards for Indian SDE campus-placement interviews (CS fundamentals). "
    "Each card tests ONE concept. The question is self-contained and specific. The answer is accurate, "
    "interview-ready and short (2-6 lines): a crisp definition or comparison, key facts, and an example "
    "when useful. Lines starting with '- ' are bullets. No markdown headings, no fluff. Never invent facts."
)


def _gen_prompt(subject, topic, count, avoid):
    avoid_txt = "\n".join(f"- {q}" for q in avoid[:40])
    return (
        f"Subject: {subject}\nTopic: {topic or 'core interview concepts'}\n"
        f"Write {count} distinct flashcards.\n"
        + (f"Do NOT repeat these existing questions:\n{avoid_txt}\n" if avoid_txt else "")
        + 'Return JSON: {"cards": [{"question": str, "answer": str, "tags": [str], "difficulty": 1|2|3}]}'
    )


@flashcards_bp.route("/generate", methods=["POST"])
def generate_cards():
    data = _body()
    subject, error = _canon_subject(data.get("subject"))
    if error:
        return _err(error)
    topic = (data.get("topic") or "").strip()[:200] if isinstance(data.get("topic"), str) else ""
    try:
        count = int(_clamp(int(data.get("count", 5)), 1, 10))
    except (TypeError, ValueError):
        count = 5
    db = SessionLocal()
    try:
        existing = [q for (q,) in db.query(Flashcard.question).all()]
        same_subject = [q for (q,) in db.query(Flashcard.question).filter(Flashcard.subject == subject).all()]
        if topic:
            tw = _words(topic)
            related = [q for q in same_subject if _words(q) & tw]
            same_subject = related + [q for q in same_subject if q not in related]
        try:
            raw = LLMClient(budget=60).generate_json(_gen_prompt(subject, topic, count, same_subject),
                                                     temperature=0.6, system=GEN_SYSTEM)
        except Exception as e:
            print(f"flashcard generation failed: {e}")
            return _err("The AI couldn't generate cards right now. Try again in a minute.", 502)
        items = raw.get("cards") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return _err("The AI returned an unexpected format. Try again.", 502)

        seen_norms = {_norm(q) for q in existing}
        seen_words = [_words(q) for q in existing]
        created, skipped = [], 0
        for item in items:
            if len(created) >= count:
                break
            if not isinstance(item, dict):
                skipped += 1
                continue
            question, e1 = _clean_text(item.get("question") or item.get("q"), "Question", MAX_Q)
            answer, e2 = _clean_text(item.get("answer") or item.get("a"), "Answer", MAX_A)
            if e1 or e2 or _is_dupe(question, seen_norms, seen_words):
                skipped += 1
                continue
            seen_norms.add(_norm(question))
            seen_words.append(_words(question))
            tags = _clean_tags(item.get("tags")) or _clean_tags(topic)
            c = Flashcard(subject=subject, question=question, answer=answer, tags=tags,
                          difficulty=_clean_difficulty(item.get("difficulty")), source="ai")
            db.add(c)
            created.append(c)
        db.commit()
        now = _utcnow()
        for c in created:
            db.refresh(c)
        return jsonify({"status": "success", "data": [_serialize(c, now) for c in created], "skipped": skipped})
    finally:
        db.close()
