"""
Achievements: Hajime no Ippo themed "fighter cards" unlocked by what the app already tracks.

GET  /api/achievements       -> evaluates every achievement (idempotent), returns all cards + new ones
POST /api/achievements/seen  -> {keys?: [...]} marks unlocked cards as seen (all unseen if no keys)

Only the unlock itself is stored (Achievement: key, unlocked_at, seen). Progress is computed on the fly
from other modules, each read lazily and guarded so a missing module or table just counts as 0.
Once unlocked, a card stays unlocked even if its metric later drops (e.g. a broken streak).
"""
import importlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.exc import IntegrityError

from api.core.config import now_ist, to_ist
from api.core.db import Base, SessionLocal, engine

TIERS = ("bronze", "silver", "gold")
IPPO_SEASON_EPISODES = 75  # Hajime no Ippo: The Fighting!, season 1
HIRE_VERDICTS = ("hire", "strong hire")


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(64), unique=True, nullable=False, index=True)
    unlocked_at = Column(DateTime, nullable=False, default=_utcnow)  # naive UTC
    seen = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<Achievement(key={self.key!r}, seen={self.seen})>"


# (key, name, description, lucide icon, tier, category, metric, target)
CATALOG = [
    ("jab", "Jab", "Solve your first problem.", "Footprints", "bronze", "Solving", "solved", 1),
    ("one_two", "One-Two", "Solve 10 problems.", "Zap", "bronze", "Solving", "solved", 10),
    ("rookie_king", "Rookie King", "Solve 100 problems.", "Medal", "silver", "Solving", "solved", 100),
    ("takamura_belt", "Takamura's Belt", "Solve 250 problems.", "Crown", "gold", "Solving", "solved", 250),
    ("gazelle_punch", "Gazelle Punch", "Solve your first LeetCode Hard.", "Rocket", "bronze", "Solving", "hards", 1),
    ("smash", "Sendo's Smash", "Solve 50 LeetCode Mediums.", "Target", "silver", "Solving", "mediums", 50),
    ("dempsey_roll", "Dempsey Roll", "Solve 5 Hards in a single week.", "RefreshCw", "gold", "Solving",
     "hards_week", 5),
    ("hawk", "Bryan Hawk's Instinct", "Solve 25 LeetCode Hards.", "Feather", "gold", "Solving", "hards", 25),
    ("counter", "Miyata's Counter", "Solve your first Codeforces problem.", "Swords", "bronze", "Solving",
     "cf", 1),
    ("jolt_counter", "Jolt Counter", "Solve 25 Codeforces problems.", "Crosshair", "silver", "Solving", "cf", 25),
    ("roadwork", "Roadwork", "Hit a 3-day solve streak.", "Sunrise", "bronze", "Streak", "streak", 3),
    ("peek_a_boo", "Peek-a-Boo", "Hit a 7-day solve streak.", "Shield", "silver", "Streak", "streak", 7),
    ("iron_chin", "Iron Chin", "Hit a 30-day solve streak.", "Flame", "silver", "Streak", "streak", 30),
    ("kamogawa_pride", "Kamogawa's Pride", "Hit a 100-day solve streak.", "Award", "gold", "Streak", "streak", 100),
    ("sparring", "Sparring Partner", "Complete 10 spaced revisions.", "RotateCcw", "bronze", "Revision",
     "revisions", 10),
    ("muscle_memory", "Muscle Memory", "Review 100 flashcards.", "Brain", "silver", "Revision", "flashcards", 100),
    ("ten_rounds", "Ten Rounds", "Log 10 hours of focus.", "Timer", "bronze", "Focus", "focus_min", 600),
    ("gym_regular", "Kamogawa Gym Regular", "Log 50 hours of focus.", "Hourglass", "silver", "Focus",
     "focus_min", 3000),
    ("mountain_camp", "Mountain Training Camp", "Log 150 hours of focus.", "Mountain", "gold", "Focus",
     "focus_min", 9000),
    ("fundamentals", "Fundamentals", "Finish your first System Design lesson.", "BookOpen", "bronze", "Learning",
     "lessons", 1),
    ("blueprint", "Blueprint of a Champion", "Finish the whole System Design course.", "Network", "gold",
     "Learning", "course", None),
    ("weigh_in", "Weigh-In", "Mark 25 syllabus topics done.", "ClipboardCheck", "bronze", "Learning",
     "topics", 25),
    ("fight_night", "Fight Night", "Watch your first episode.", "Tv", "bronze", "Ippo", "episodes", 1),
    ("the_fighting", "The Fighting!", "Finish a full season of Hajime no Ippo.", "Clapperboard", "gold", "Ippo",
     "season", None),
    ("liver_blow", "Liver Blow", "KO your first weekly boss.", "Dumbbell", "bronze", "Gym", "boss_kos", 1),
    ("champion_carnival", "Champion Carnival", "KO 5 weekly bosses.", "Trophy", "silver", "Gym", "boss_kos", 5),
    ("pro_test", "Pro Test", "Finish your first mock OA.", "ListChecks", "bronze", "Placements", "oas", 1),
    ("press_conference", "Press Conference", "Finish your first mock interview.", "Mic", "bronze", "Placements",
     "mocks", 1),
    ("hire_me", "Hire Me, Coach", "Get a \"hire\" verdict in a mock interview.", "BadgeCheck", "silver",
     "Placements", "mock_hires", 1),
    ("a_class", "A-Class", "Reach A-Class rank (2,000 XP).", "Star", "silver", "Rank", "xp", 2000),
]

achievements_bp = Blueprint("achievements", __name__, url_prefix="/api/achievements")


@achievements_bp.record_once
def _ensure_table(state):
    try:
        Achievement.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:  # e.g. a concurrent cold start created it first
        print(f"achievements table check skipped: {e}")


# ---------------- metrics (each guarded) ----------------
def _guard(db, fn, default):
    try:
        return fn()
    except Exception as e:
        db.rollback()
        print(f"achievements: source unavailable ({e})")
        return default


def _day(dt):
    return to_ist(dt).date() if dt else None


def _solves(db, m):
    from api.domain.models import NotificationLog
    rows = (db.query(NotificationLog.task_type, NotificationLog.difficulty, NotificationLog.completed_at,
                     NotificationLog.timestamp, NotificationLog.review_stage)
            .filter(NotificationLog.status == "success", NotificationLog.is_completed == True)  # noqa: E712
            .all())
    hard_weeks, days = Counter(), set()
    for kind, diff, done_at, ts, stage in rows:
        d = _day(done_at or ts)
        if kind == "watch":
            m["episodes"] += 1
            continue
        if kind not in ("leetcode", "codeforces"):
            continue
        m["solved"] += 1
        if d:
            days.add(d)
        if kind == "codeforces":
            m["cf"] += 1
            continue
        m["revisions"] += int(stage or 0)
        if diff == "Medium":
            m["mediums"] += 1
        elif diff == "Hard":
            m["hards"] += 1
            if d:
                hard_weeks[d - timedelta(days=d.weekday())] += 1
    m["hards_week"] = max(hard_weeks.values(), default=0)
    return days


def _streak(db, days, today):
    from api.domain.focus import compute_streak, theory_exam_days
    return compute_streak(days, theory_exam_days(db), today)["best_streak"]


def _focus(db):
    from sqlalchemy import func
    from api.domain.focus import FocusSession
    return int(db.query(func.coalesce(func.sum(FocusSession.minutes), 0)).scalar() or 0)


def _learning(db, m, targets):
    from api.domain.learning import Course, Lesson
    courses = db.query(Course).all()
    lessons = db.query(Lesson.course_id, Lesson.done).all()
    m["lessons"] = sum(1 for _, done in lessons if done)
    per = {c.id: [0, 0] for c in courses}
    for cid, done in lessons:
        if cid in per:
            per[cid][0] += 1 if done else 0
            per[cid][1] += 1
    design = [c for c in courses if "design" in (c.title or "").lower()] or courses
    best = max((per[c.id] for c in design if per[c.id][1]), key=lambda p: (p[0] >= p[1], p[0] / p[1]),
               default=None)
    if best:
        m["course"], targets["course"] = best


def _topics(db):
    from api.domain.syllabus import SyllabusTopic
    return db.query(SyllabusTopic).filter(SyllabusTopic.done == True).count()  # noqa: E712


def _season(db, m, targets):
    from api.domain.models import WatchSeries
    target = IPPO_SEASON_EPISODES
    series = [s for s in db.query(WatchSeries).all() if "ippo" in (s.title or "").lower()]
    if series:
        s = max(series, key=lambda x: x.next_episode or 0)
        target = max(1, int(s.total_episodes or target))
        m["season"] = min(target, max(m["episodes"], (s.next_episode or 1) - 1))
    else:
        m["season"] = min(target, m["episodes"])
    targets["season"] = target


def _boss_kos(db):
    from api.domain.gym import BossWeek
    return db.query(BossWeek).filter(BossWeek.defeated_at != None).count()  # noqa: E711


def _oas(db):
    from api.domain.oa import OAAttempt
    return db.query(OAAttempt).filter(OAAttempt.status == "finished").count()


def _mocks(db, m):
    from api.domain.interview import MockSession
    for (raw,) in db.query(MockSession.rubric).filter(MockSession.status == "done").all():
        m["mocks"] += 1
        try:
            verdict = str((json.loads(raw or "{}") or {}).get("verdict") or "").strip().lower()
        except (ValueError, AttributeError):
            verdict = ""
        if verdict in HIRE_VERDICTS:
            m["mock_hires"] += 1


def _xp(db):
    from api.domain.xp import compute_xp
    return int(compute_xp(db).get("xp") or 0)


def _flashcards(db):
    """Flashcards may not exist yet: count review rows, or sum a per-card repetition counter."""
    mod = importlib.import_module("api.domain.flashcards")
    for name in ("FlashcardReview", "CardReview", "Review"):
        model = getattr(mod, name, None)
        if model is not None and hasattr(model, "__table__"):
            return db.query(model).count()
    from sqlalchemy import func
    for name in ("Flashcard", "Card"):
        model = getattr(mod, name, None)
        for col in ("reps", "review_count", "reviews"):
            if model is not None and hasattr(model, col):
                return int(db.query(func.coalesce(func.sum(getattr(model, col)), 0)).scalar() or 0)
    return 0


def collect_metrics(db, today):
    """Returns (metrics, dynamic_targets). Every source is optional."""
    m = Counter()
    targets = {}
    days = _guard(db, lambda: _solves(db, m), set())
    m["streak"] = _guard(db, lambda: _streak(db, days, today), 0)
    m["focus_min"] = _guard(db, lambda: _focus(db), 0)
    _guard(db, lambda: _learning(db, m, targets), None)
    m["topics"] = _guard(db, lambda: _topics(db), 0)
    _guard(db, lambda: _season(db, m, targets), None)
    targets.setdefault("season", IPPO_SEASON_EPISODES)
    m.setdefault("season", min(m["episodes"], IPPO_SEASON_EPISODES))
    m["boss_kos"] = _guard(db, lambda: _boss_kos(db), 0)
    m["oas"] = _guard(db, lambda: _oas(db), 0)
    _guard(db, lambda: _mocks(db, m), None)
    m["xp"] = _guard(db, lambda: _xp(db), 0)
    m["flashcards"] = _guard(db, lambda: _flashcards(db), 0)
    return m, targets


# ---------------- evaluation ----------------
def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def evaluate(db, today=None):
    """Unlocks every achievement whose target is met (idempotent). Returns (cards, newly_unlocked_keys)."""
    today = today or now_ist().date()
    metrics, targets = collect_metrics(db, today)
    rows = {a.key: a for a in db.query(Achievement).all()}
    cards, new_keys = [], []
    for key, name, desc, icon, tier, category, metric, target in CATALOG:
        target = target or targets.get(metric) or 1
        current = int(metrics.get(metric, 0) or 0)
        row = rows.get(key)
        if row is None and current >= target:
            row = Achievement(key=key, unlocked_at=_utcnow(), seen=False)
            db.add(row)
            try:
                db.commit()
            except IntegrityError:  # unlocked by a concurrent request
                db.rollback()
                row = db.query(Achievement).filter(Achievement.key == key).first()
            else:
                new_keys.append(key)
            rows[key] = row
        unlocked = row is not None
        cards.append({
            "key": key, "name": name, "description": desc, "icon": icon, "tier": tier, "category": category,
            "current": min(current, target) if unlocked else current, "target": target,
            "progress": 1.0 if unlocked else round(min(1.0, current / target), 4),
            "unlocked": unlocked,
            "unlocked_at": _iso(row.unlocked_at) if row else None,
            "seen": bool(row.seen) if row else False,
        })
    return cards, new_keys


# ---------------- routes ----------------
@achievements_bp.route("", methods=["GET"], strict_slashes=False)
def list_achievements():
    db = SessionLocal()
    try:
        cards, new_keys = evaluate(db)
        unlocked = [c for c in cards if c["unlocked"]]
        return jsonify({
            "status": "success",
            "data": cards,
            "unlocked": len(unlocked),
            "total": len(cards),
            "by_tier": {t: {"unlocked": sum(1 for c in unlocked if c["tier"] == t),
                            "total": sum(1 for c in cards if c["tier"] == t)} for t in TIERS},
            "unseen": [c for c in unlocked if not c["seen"]],
            "new": new_keys,
        })
    finally:
        db.close()


@achievements_bp.route("/seen", methods=["POST"])
def mark_seen():
    data = request.get_json(silent=True)
    keys = data.get("keys") if isinstance(data, dict) else None
    if keys is not None and (not isinstance(keys, list) or not all(isinstance(k, str) for k in keys)):
        return jsonify({"status": "error", "message": "keys must be a list of achievement keys."}), 400
    db = SessionLocal()
    try:
        q = db.query(Achievement).filter(Achievement.seen == False)  # noqa: E712
        if keys is not None:
            q = q.filter(Achievement.key.in_(keys)) if keys else q.filter(False)
        rows = q.all()
        for a in rows:
            a.seen = True
        db.commit()
        return jsonify({"status": "success", "updated": len(rows)})
    finally:
        db.close()
