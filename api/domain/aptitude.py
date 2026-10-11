"""
Aptitude Daily 5: placement-style quant / logical / verbal MCQs, five a day.

Today's five are picked deterministically per IST date from data as it stood *before* today, so the
set never shifts mid-day: types you are weak at weigh more, and questions you already got right are
skipped. Answers are recorded per question (daily or practice) with time taken, and /stats rolls them
up per type. /generate asks Gemini for new questions of a type, has a second Gemini call solve them
blind, and keeps only those where both agree.
"""
import hashlib
import json
import random
import re
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Date, Float, Text
from sqlalchemy.exc import IntegrityError

from api.core.clients import LLMClient
from api.core.config import IST, now_ist
from api.core.db import Base, SessionLocal, engine
from api.domain.aptitude_bank import BANK, KEEP_ORDER, TYPES

DAILY_N = 5
MAX_GENERATE = 5
PRACTICE_N = 5
MAX_SECONDS = 3600
GEN_BUDGET = 110    # seconds per LLM call (two calls); Vercel gives us 300
DIFFICULTY_WORDS = {"easy": 1, "medium": 2, "moderate": 2, "hard": 3, "difficult": 3}


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AptQuestion(Base):
    __tablename__ = "apt_questions"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(40), nullable=False, index=True)
    question = Column(Text, nullable=False)
    options = Column(Text, nullable=False)  # JSON list of 4 strings
    answer_index = Column(Integer, nullable=False)
    explanation = Column(Text, nullable=False, default="")
    difficulty = Column(Integer, nullable=False, default=2)  # 1 easy, 2 medium, 3 hard
    source = Column(String(10), nullable=False, default="seed")  # seed | ai
    fingerprint = Column(String(40), nullable=False, unique=True)
    created_at = Column(DateTime, default=_utcnow)  # naive UTC

    def __repr__(self):
        return f"<AptQuestion(id={self.id}, type={self.type}, source={self.source})>"


class AptAttempt(Base):
    __tablename__ = "apt_attempts"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, nullable=False, index=True)
    type = Column(String(40), nullable=False, index=True)  # denormalised for cheap stats
    chosen = Column(Integer, nullable=False)
    correct = Column(Boolean, nullable=False)
    seconds = Column(Float, nullable=True)
    mode = Column(String(10), nullable=False, default="daily")  # daily | practice
    day = Column(Date, nullable=False, index=True)  # IST date
    created_at = Column(DateTime, default=_utcnow)  # naive UTC

    def __repr__(self):
        return f"<AptAttempt(q={self.question_id}, day={self.day}, correct={self.correct})>"


aptitude_bp = Blueprint("aptitude", __name__, url_prefix="/api/aptitude")


@aptitude_bp.record_once
def _ensure_tables(state):
    """Create the tables when the blueprint is registered, so wiring it in needs no extra step."""
    for model in (AptQuestion, AptAttempt):
        try:
            model.__table__.create(bind=engine, checkfirst=True)
        except Exception as e:  # e.g. a concurrent cold start created it first
            print(f"{model.__tablename__} table check skipped: {e}")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _today():
    return now_ist().date()


def _day_start_utc(day):
    return datetime.combine(day, time.min, IST).astimezone(timezone.utc).replace(tzinfo=None)


def _fingerprint(type_, question):
    norm = re.sub(r"\s+", " ", (question or "").strip().lower())
    return hashlib.sha1(f"{type_}|{norm}".encode("utf-8")).hexdigest()


def _shuffled(type_, options, answer_index, fingerprint):
    """Deterministically shuffle options (LLMs and hand-written banks both favour some positions)."""
    if type_ in KEEP_ORDER:
        return list(options), answer_index
    order = list(range(len(options)))
    random.Random(fingerprint).shuffle(order)
    return [options[i] for i in order], order.index(answer_index)


def _make_question(item, source):
    fp = _fingerprint(item["type"], item["question"])
    options, answer = _shuffled(item["type"], item["options"], item["answer_index"], fp)
    return AptQuestion(type=item["type"], question=item["question"].strip(), options=json.dumps(options),
                       answer_index=answer, explanation=item.get("explanation") or "",
                       difficulty=int(item.get("difficulty") or 2), source=source, fingerprint=fp)


def _ensure_seeded(db):
    """Insert any bank questions not yet in the DB (cheap: one fingerprint query)."""
    have = {fp for (fp,) in db.query(AptQuestion.fingerprint).all()}
    missing = [q for q in BANK if _fingerprint(q["type"], q["question"]) not in have]
    if not missing:
        return
    db.add_all(_make_question(q, "seed") for q in missing)
    try:
        db.commit()
    except IntegrityError:  # a concurrent request seeded first
        db.rollback()


def _options(q):
    try:
        opts = json.loads(q.options)
    except (TypeError, ValueError):
        return []
    return opts if isinstance(opts, list) else []


def _serialize(q, reveal=False):
    label, section = TYPES.get(q.type, (q.type, "Other"))
    out = {
        "id": q.id, "type": q.type, "type_label": label, "section": section,
        "question": q.question, "options": _options(q), "difficulty": q.difficulty, "source": q.source,
    }
    if reveal:
        out["answer_index"] = q.answer_index
        out["explanation"] = q.explanation
    return out


def _with_attempt(q, attempt):
    out = _serialize(q, reveal=attempt is not None)
    out["attempt"] = None if attempt is None else {
        "chosen": attempt.chosen, "correct": bool(attempt.correct),
        "seconds": round(attempt.seconds, 1) if attempt.seconds is not None else None,
    }
    return out


WEAK_MIN_ATTEMPTS = 3
WEAK_ACCURACY = 0.6


def _smoothed_acc(attempts, correct):
    return (correct + 1) / (attempts + 2)  # Laplace: unseen types sit at 50%


def _type_weight(attempts, correct):
    """Weak types weigh more (1x for mastered up to 4x for always-wrong)."""
    return 1.0 + 3.0 * (1.0 - _smoothed_acc(attempts, correct))


def _is_weak(attempts, correct):
    return attempts >= WEAK_MIN_ATTEMPTS and _smoothed_acc(attempts, correct) < WEAK_ACCURACY


def _pick_daily(db, today):
    """Deterministic list of DAILY_N question ids for `today`, using only data from before today."""
    cutoff = _day_start_utc(today)
    questions = [q for q in db.query(AptQuestion).order_by(AptQuestion.id).all()
                 if q.source == "seed" or (q.created_at and q.created_at < cutoff)]
    past = db.query(AptAttempt).filter(AptAttempt.day < today).all()

    seen, right = set(), set()
    per_type = defaultdict(lambda: [0, 0])
    for a in past:
        seen.add(a.question_id)
        if a.correct:
            right.add(a.question_id)
        per_type[a.type][0] += 1
        per_type[a.type][1] += int(bool(a.correct))

    pool = [q for q in questions if q.id not in right]
    if len(pool) < DAILY_N:  # everything solved: recycle, oldest-solved first is not worth tracking
        pool = questions
    by_type = defaultdict(list)
    for q in pool:
        by_type[q.type].append(q)

    rng = random.Random(f"aptitude:{today.isoformat()}")
    picks, used = [], set()
    while len(picks) < DAILY_N:
        avail = sorted(t for t in by_type if by_type[t])
        if not avail:
            break
        fresh = [t for t in avail if t not in used] or avail  # spread across types first
        weak = [t for t in fresh if _is_weak(*per_type[t])]
        if not picks and weak:  # first slot is reserved for a clearly weak type
            t = rng.choices(weak, weights=[(1 - _smoothed_acc(*per_type[t])) ** 2 for t in weak])[0]
        else:
            t = rng.choices(fresh, weights=[_type_weight(*per_type[t]) for t in fresh])[0]
        cands = by_type[t]
        tier = [q for q in cands if q.id not in seen] or cands  # unseen before retries of misses
        q = rng.choice(tier)
        cands.remove(q)
        picks.append(q.id)
        used.add(t)
    return picks


def _today_set(db, today):
    """(ordered questions, {question_id: today's daily attempt})."""
    picks = _pick_daily(db, today)
    attempts = {}
    for a in (db.query(AptAttempt).filter(AptAttempt.day == today, AptAttempt.mode == "daily")
              .order_by(AptAttempt.id).all()):
        attempts.setdefault(a.question_id, a)
    # If the pool changed under us (e.g. a deploy added seed questions), keep what was already answered.
    for qid in attempts:
        if qid not in picks:
            for i in range(len(picks) - 1, -1, -1):
                if picks[i] not in attempts:
                    picks[i] = qid
                    break
    rows = {q.id: q for q in db.query(AptQuestion).filter(AptQuestion.id.in_(picks)).all()} if picks else {}
    return [rows[i] for i in picks if i in rows], attempts


def _streaks(db, today):
    """(current, best) streak of IST days with the full Daily 5 done."""
    counts = defaultdict(set)
    for qid, day in db.query(AptAttempt.question_id, AptAttempt.day).filter(AptAttempt.mode == "daily").all():
        counts[day].add(qid)
    full = {d for d, ids in counts.items() if len(ids) >= DAILY_N}
    d = today if today in full else today - timedelta(days=1)
    current = 0
    while d in full:
        current += 1
        d -= timedelta(days=1)
    best = run = 0
    prev = None
    for day in sorted(full):
        run = run + 1 if prev is not None and day - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = day
    return current, best


def _overall(db):
    rows = db.query(AptAttempt.correct, AptAttempt.seconds).all()
    n = len(rows)
    right = sum(1 for c, _ in rows if c)
    secs = [s for _, s in rows if s is not None and s > 0]
    return {
        "attempts": n, "correct": right,
        "accuracy": round(right / n, 3) if n else None,
        "avg_seconds": round(sum(secs) / len(secs), 1) if secs else None,
    }


def _types_payload():
    return [{"type": k, "label": v[0], "section": v[1]} for k, v in TYPES.items()]


# ---------------- routes ----------------
@aptitude_bp.route("/today", methods=["GET"])
def today_set():
    db = SessionLocal()
    try:
        _ensure_seeded(db)
        today = _today()
        questions, attempts = _today_set(db, today)
        items = [_with_attempt(q, attempts.get(q.id)) for q in questions]
        done = [i for i in items if i["attempt"]]
        current, best = _streaks(db, today)
        return jsonify({
            "status": "success",
            "day": today.isoformat(),
            "data": items,
            "total": len(items),
            "done": len(done),
            "correct": sum(1 for i in done if i["attempt"]["correct"]),
            "seconds": round(sum(i["attempt"]["seconds"] or 0 for i in done), 1),
            "streak": current,
            "best_streak": best,
            "overall": _overall(db),
        })
    finally:
        db.close()


@aptitude_bp.route("/practice", methods=["GET"])
def practice_set():
    type_ = request.args.get("type", "")
    if type_ not in TYPES:
        return _err("Unknown question type.")
    try:
        count = max(1, min(int(request.args.get("count", PRACTICE_N)), 10))
    except ValueError:
        count = PRACTICE_N
    db = SessionLocal()
    try:
        _ensure_seeded(db)
        questions = db.query(AptQuestion).filter(AptQuestion.type == type_).all()
        history = defaultdict(list)
        for qid, ok in (db.query(AptAttempt.question_id, AptAttempt.correct)
                        .filter(AptAttempt.type == type_).order_by(AptAttempt.id).all()):
            history[qid].append(bool(ok))
        rng = random.Random()
        rng.shuffle(questions)
        # Unseen first, then ones whose last attempt was wrong, then the rest.
        questions.sort(key=lambda q: 0 if q.id not in history else (1 if not history[q.id][-1] else 2))
        return jsonify({"status": "success", "type": type_, "label": TYPES[type_][0],
                        "data": [_serialize(q) for q in questions[:count]], "available": len(questions)})
    finally:
        db.close()


@aptitude_bp.route("/answer", methods=["POST"])
def answer():
    data = _body()
    qid, chosen = data.get("question_id"), data.get("chosen")
    if not isinstance(qid, int) or isinstance(qid, bool):
        return _err("question_id must be an integer.")
    if not isinstance(chosen, int) or isinstance(chosen, bool) or not 0 <= chosen <= 3:
        return _err("chosen must be an option index 0-3.")
    seconds = data.get("seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds < 0:
        seconds = None
    else:
        seconds = float(min(seconds, MAX_SECONDS))

    db = SessionLocal()
    try:
        q = db.get(AptQuestion, qid)
        if not q:
            return _err("Question not found.", 404)
        if chosen >= len(_options(q)):
            return _err("chosen is out of range for this question.")
        today = _today()
        mode = "practice" if data.get("mode") == "practice" else "daily"
        already = False
        attempt = None
        if mode == "daily":
            questions, attempts = _today_set(db, today)
            if qid not in {x.id for x in questions}:
                mode = "practice"  # not part of today's five: still counts toward stats
            elif qid in attempts:
                attempt, already = attempts[qid], True  # first answer stands
        if attempt is None:
            attempt = AptAttempt(question_id=q.id, type=q.type, chosen=chosen, correct=chosen == q.answer_index,
                                 seconds=seconds, mode=mode, day=today)
            db.add(attempt)
            db.commit()
            db.refresh(attempt)
        done = (db.query(AptAttempt.question_id)
                .filter(AptAttempt.day == today, AptAttempt.mode == "daily").distinct().count())
        return jsonify({
            "status": "success",
            "data": {
                "question_id": q.id, "chosen": attempt.chosen, "correct": bool(attempt.correct),
                "answer_index": q.answer_index, "explanation": q.explanation,
                "mode": attempt.mode, "already": already,
            },
            "done_today": done,
        })
    finally:
        db.close()


@aptitude_bp.route("/stats", methods=["GET"])
def stats():
    db = SessionLocal()
    try:
        _ensure_seeded(db)
        today = _today()
        per = {k: {"attempts": 0, "correct": 0, "secs": []} for k in TYPES}
        for type_, ok, secs in db.query(AptAttempt.type, AptAttempt.correct, AptAttempt.seconds).all():
            row = per.setdefault(type_, {"attempts": 0, "correct": 0, "secs": []})
            row["attempts"] += 1
            row["correct"] += int(bool(ok))
            if secs is not None and secs > 0:
                row["secs"].append(secs)
        counts = defaultdict(int)
        for (type_,) in db.query(AptQuestion.type).all():
            counts[type_] += 1
        types = []
        for k, row in per.items():
            label, section = TYPES.get(k, (k, "Other"))
            n = row["attempts"]
            types.append({
                "type": k, "label": label, "section": section, "attempts": n, "correct": row["correct"],
                "accuracy": round(row["correct"] / n, 3) if n else None,
                "avg_seconds": round(sum(row["secs"]) / len(row["secs"]), 1) if row["secs"] else None,
                "questions": counts.get(k, 0),
            })
        tried = [t for t in types if t["attempts"]]
        weakest = sorted(tried, key=lambda t: (t["accuracy"], -t["attempts"]))[:3]

        # Last 14 IST days of Daily 5 activity
        since = today - timedelta(days=13)
        days = defaultdict(lambda: {"done": set(), "correct": set()})
        for qid, ok, day in (db.query(AptAttempt.question_id, AptAttempt.correct, AptAttempt.day)
                             .filter(AptAttempt.mode == "daily", AptAttempt.day >= since).all()):
            days[day]["done"].add(qid)
            if ok:
                days[day]["correct"].add(qid)
        history = [{"day": (since + timedelta(days=i)).isoformat(),
                    "done": len(days[since + timedelta(days=i)]["done"]),
                    "correct": len(days[since + timedelta(days=i)]["correct"])} for i in range(14)]

        current, best = _streaks(db, today)
        return jsonify({
            "status": "success",
            "data": {
                "overall": _overall(db), "streak": current, "best_streak": best,
                "types": types, "weakest": [t["type"] for t in weakest],
                "history": history, "daily_n": DAILY_N,
            },
            "types": _types_payload(),
        })
    finally:
        db.close()


# ---------------- AI generation ----------------
_GEN_SYSTEM = (
    "You write multiple-choice aptitude questions for Indian campus placement online assessments "
    "(TCS NQT, Infosys, Accenture, Wipro, Capgemini, AMCAT). Every question must have exactly one correct "
    "option, four options, realistic numbers that work out cleanly, and a concise step-by-step explanation. "
    "Double-check every calculation before answering. Output JSON only."
)
_SOLVE_SYSTEM = (
    "You are an expert at quantitative aptitude and logical reasoning. Solve each multiple-choice question "
    "independently and carefully, working step by step internally, then report only the index (0-3) of the "
    "correct option. Output JSON only."
)


def _clean_generated(item, type_):
    """Validate one LLM question; returns a bank-shaped dict or None."""
    if not isinstance(item, dict):
        return None
    question = item.get("question")
    options = item.get("options")
    explanation = item.get("explanation")
    if not isinstance(question, str) or not 10 <= len(question.strip()) <= 1200:
        return None
    if not isinstance(options, list) or len(options) != 4:
        return None
    options = [re.sub(r"^\s*[A-Da-d][.)]\s+", "", o).strip() if isinstance(o, str) else "" for o in options]
    if any(not o or len(o) > 200 for o in options) or len({o.lower() for o in options}) != 4:
        return None
    ans = item.get("answer_index", item.get("answer"))
    if isinstance(ans, str):
        s = ans.strip().upper()
        ans = int(s) if s.isdigit() else ("ABCD".index(s) if len(s) == 1 and s in "ABCD" else None)
    if not isinstance(ans, int) or isinstance(ans, bool) or not 0 <= ans <= 3:
        return None
    if not isinstance(explanation, str) or not explanation.strip():
        return None
    diff = item.get("difficulty", 2)
    if isinstance(diff, str):
        diff = DIFFICULTY_WORDS.get(diff.strip().lower(), int(diff) if diff.strip().isdigit() else 2)
    if not isinstance(diff, int) or isinstance(diff, bool):
        diff = 2
    return {"type": type_, "question": question.strip(), "options": options, "answer_index": ans,
            "explanation": explanation.strip()[:2000], "difficulty": max(1, min(3, diff))}


def _as_list(raw, key):
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and isinstance(raw.get(key), list):
        return raw[key]
    return []


def _solver_answers(raw):
    """{question number: chosen index} from the solver's reply."""
    out = {}
    for i, a in enumerate(_as_list(raw, "answers")):
        if isinstance(a, dict):
            idx = a.get("i", a.get("index", i))
            ans = a.get("answer_index", a.get("answer"))
        else:
            idx, ans = i, a
        if isinstance(ans, str) and ans.strip().upper() in ("A", "B", "C", "D"):
            ans = "ABCD".index(ans.strip().upper())
        if isinstance(idx, int) and isinstance(ans, int) and not isinstance(ans, bool):
            out[idx] = ans
    return out


@aptitude_bp.route("/generate", methods=["POST"])
def generate():
    data = _body()
    type_ = data.get("type")
    if type_ not in TYPES:
        return _err("Unknown question type.")
    count = data.get("count", 3)
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_GENERATE:
        return _err(f"count must be between 1 and {MAX_GENERATE}.")
    label, section = TYPES[type_]

    db = SessionLocal()
    try:
        _ensure_seeded(db)
        existing = db.query(AptQuestion).filter(AptQuestion.type == type_).order_by(AptQuestion.id.desc()).all()
        examples = [{"question": q.question, "options": _options(q), "answer_index": q.answer_index,
                     "explanation": q.explanation, "difficulty": q.difficulty} for q in existing[:2]]
        avoid = [q.question[:140] for q in existing[:40]]
        prompt = (
            f"Write {count} new {section} aptitude MCQs of type \"{label}\" for placement tests.\n"
            "Mix difficulties (1 easy, 2 medium, 3 hard), lean medium. Do not repeat or lightly reword these "
            f"existing questions:\n{json.dumps(avoid, ensure_ascii=False)}\n\n"
            f"Style examples:\n{json.dumps(examples, ensure_ascii=False)}\n\n"
            'Return {"questions": [{"question": str, "options": [4 strings], "answer_index": 0-3, '
            '"explanation": str, "difficulty": 1-3}]}'
        )
        try:
            raw = LLMClient(budget=GEN_BUDGET).generate_json(prompt, temperature=0.8, system=_GEN_SYSTEM, thinking="medium")
        except Exception as e:
            return _err(f"Couldn't generate questions: {str(e)[:200]}", 502)

        have = {fp for (fp,) in db.query(AptQuestion.fingerprint).all()}
        cands, seen = [], set()
        for item in _as_list(raw, "questions")[:count]:
            q = _clean_generated(item, type_)
            if not q:
                continue
            fp = _fingerprint(type_, q["question"])
            if fp in have or fp in seen:
                continue
            seen.add(fp)
            cands.append(q)
        if not cands:
            return _err("The generator returned no usable questions. Try again.", 502)

        solve_prompt = (
            "Solve these questions. Return {\"answers\": [{\"i\": question number, \"answer_index\": 0-3}]}.\n\n"
            + json.dumps([{"i": i, "question": q["question"], "options": q["options"]} for i, q in enumerate(cands)],
                         ensure_ascii=False)
        )
        try:
            solved = _solver_answers(LLMClient(budget=GEN_BUDGET).generate_json(
                solve_prompt, temperature=0.0, system=_SOLVE_SYSTEM, thinking="high"))
        except Exception as e:
            return _err(f"Couldn't verify the generated questions: {str(e)[:200]}", 502)

        kept = [q for i, q in enumerate(cands) if solved.get(i) == q["answer_index"]]
        rows = [_make_question(q, "ai") for q in kept]
        db.add_all(rows)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return _err("Those questions were just added by another request. Try again.", 409)
        for r in rows:
            db.refresh(r)
        return jsonify({
            "status": "success",
            "data": [_serialize(r) for r in rows],
            "generated": len(cands), "kept": len(rows), "rejected": len(cands) - len(rows),
        })
    finally:
        db.close()
