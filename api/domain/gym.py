"""
Gym: healthy-habit mechanics, Hajime no Ippo themed. Everything is derived from data the app already
stores (solves, focus sessions, syllabus, System Design lessons, reviews); the only state of its own is
the weekly boss and today's quest.

  GET  /api/gym/rings                 today's three rings (Solve / Study / Learn)
  GET  /api/gym/rings/history?days=   rings closed per IST day (0-3) + perfect weeks
  GET  /api/gym/boss                  this week's boss fight (weakest topic), damage log, past bosses
  GET  /api/gym/quest                 today's daily quest (auto-completes from data)
  POST /api/gym/quest/skip            reroll today's quest (once a day)
  GET  /api/gym/records               personal records

Every other module is imported lazily and every source is guarded: a table or module that doesn't
exist yet simply contributes nothing, so these endpoints never fail because a feature isn't wired in.
"""
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from math import ceil

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Date, DateTime, Integer, String
from sqlalchemy.exc import IntegrityError

from api.core.config import IST, now_ist, to_ist
from api.core.db import Base, SessionLocal, engine
from api.domain.models import NotificationLog, Settings

# ---------------- tuning ----------------
DEFAULT_SOLVE_GOAL = 2
STUDY_MINUTES = 60
EXAM_STUDY_MINUTES = 120
STUDY_TOPICS = 1
LESSON_GOAL = 1
REVISION_GOAL = 3
HISTORY_DAYS = 126
MAX_HISTORY_DAYS = 371
RECORD_SPAN_DAYS = 1100       # how far back personal records look
PERFECT_WEEK_DAYS = 5         # days (of 7) with all rings closed

BOSS_HP = 100
DAMAGE = {"Easy": 20, "Medium": 35, "Hard": 60}
DEFAULT_DAMAGE = 20           # difficulty unknown
REVIEW_DAMAGE = 10
BOSS_HISTORY = 20

QUEST_XP = 25
QUEST_SETTING = "gym_quest"   # "YYYY-MM-DD|key|param|skips"
MAX_SKIPS = 1
MORNING_HOUR = 10             # IST
MORNING_MINUTES = 25

# Problem-bank topic -> (rival, one-line flavour). Ippo's opponents (and Takamura's, for Greedy).
RIVALS = {
    "Graphs": ("Mashiba Ryo", "The Grim Reaper's flicker jab. Map every path before he maps yours."),
    "Dynamic Programming": ("Sendo Takeshi", "The Naniwa Tiger. Overlapping subproblems, overwhelming power."),
    "Binary Trees": ("Volg Zangief", "The white fang. Recursion that never loses its form."),
    "Binary Search Trees": ("Volg Zangief", "The white fang. Every node in its place, every punch on line."),
    "Sliding Window & Two Pointers": ("Miyata Ichiro", "Counter-puncher. Keep the window tight, strike on the shift."),
    "Stack & Queue": ("Hayami Ryuichi", "Shotgun jabs. Push, pop, never lose the order."),
    "Binary Search": ("Sawamura Ryuhei", "Bloody Hawk. Halve the distance, then strike."),
    "Heaps": ("Ozuma Geronimo", "Climbs to the top every round. Keep the priority straight."),
    "Recursion & Backtracking": ("Sanada Kazuki", "The doctor's Hien. Explore, prune, return."),
    "Greedy": ("Bryan Hawk", "Pure instinct. Prove the local choice is the right one."),
    "Arrays": ("Okita Keigo", "Rival of the rookie days. Fundamentals win fights."),
    "Strings": ("Karasawa Takuya", "Flashy footwork. Read the pattern, not the noise."),
    "Linked List": ("Kobashi Kenta", "The clincher. Don't lose the chain."),
    "Bit Manipulation": ("Iwao Shimabukuro", "Dense, compact, explosive."),
    "Maths": ("Saeki Takuma", "Speed star. Find the formula faster than he moves."),
    "Tries": ("Alfredo Gonzales", "World-class technique, one prefix at a time."),
}
FALLBACK_RIVAL = ("Date Eiji", "The Heartbreak Shot. The champion waits for you.")


def _bank_topics():
    try:
        from api.domain.problem_bank import PROBLEMS
        seen = []
        for p in PROBLEMS:
            if p[3] not in seen:
                seen.append(p[3])
        return seen or list(RIVALS)
    except Exception:
        return list(RIVALS)


BANK_TOPICS = _bank_topics()


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BossWeek(Base):
    __tablename__ = "gym_boss_weeks"

    id = Column(Integer, primary_key=True, index=True)
    week_start = Column(Date, nullable=False, unique=True, index=True)  # Monday, IST
    boss = Column(String(80), nullable=False)
    topic = Column(String(80), nullable=False)
    hp_max = Column(Integer, nullable=False, default=BOSS_HP)
    started_at = Column(DateTime, default=_utcnow)    # naive UTC
    defeated_at = Column(DateTime, nullable=True)     # naive UTC, the KO punch

    def __repr__(self):
        return f"<BossWeek(week={self.week_start}, boss={self.boss}, topic={self.topic})>"


gym_bp = Blueprint("gym", __name__, url_prefix="/api/gym")


@gym_bp.record_once
def _ensure_table(state):
    """Create the table when the blueprint is registered, so wiring it in needs no extra step."""
    for table in (Settings.__table__, BossWeek.__table__):
        try:
            table.create(bind=engine, checkfirst=True)
        except Exception as e:  # e.g. a concurrent cold start created it first
            print(f"{table.name} table check skipped: {e}")


# ---------------- helpers ----------------
def _ok(data):
    return jsonify({"status": "success", "data": data})


def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _day(dt):
    """naive UTC -> IST date"""
    return to_ist(dt).date() if dt else None


def _to_utc(now):
    return now.astimezone(timezone.utc).replace(tzinfo=None)


def _monday(d):
    return d - timedelta(days=d.weekday())


def _guard(db, fn, default, what):
    try:
        return fn()
    except Exception as e:
        try:
            db.rollback()  # Postgres aborts the transaction after an error
        except Exception:
            pass
        print(f"gym: {what} unavailable: {e}")
        return default


def _topics_of(raw):
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def _base_goal(db):
    def read():
        row = db.query(Settings).filter(Settings.key == "daily_goal").first()
        return max(1, min(50, int(row.value))) if row else DEFAULT_SOLVE_GOAL
    return _guard(db, read, DEFAULT_SOLVE_GOAL, "daily goal")


# ---------------- activity (everything bucketed per IST day) ----------------
class Activity:
    """All-time activity of the single user, bucketed by IST date. Small enough to load at once."""

    def __init__(self):
        self.solves = Counter()          # LeetCode + Codeforces completed
        self.mediums = Counter()         # LeetCode mediums completed
        self.lc_events = []              # (at, day, title, difficulty, [topics]) completed LeetCode
        self.review_events = []          # (at, day, title, [topics]) last review per problem
        self.reviews = Counter()
        self.focus = Counter()           # minutes
        self.morning_focus = Counter()   # minutes from sessions started before MORNING_HOUR IST
        self.topics = Counter()          # syllabus topics studied/done
        self.lessons = Counter()         # System Design lessons done
        self.rest = set()                # theory exam days
        self.frozen = set()              # days a streak freeze was spent
        self.reviews_ok = False
        self._first_active = None

    def recovery(self, d):
        """Yesterday broke the solve streak: no solve, not a rest day, no freeze spent (and not brand new)."""
        p = d - timedelta(days=1)
        if self.solves.get(p) or p in self.rest or p in self.frozen:
            return False
        return self._first_active is not None and self._first_active < p

    def first_day(self):
        days = [d for c in (self.solves, self.focus, self.topics, self.lessons, self.reviews) for d, n in c.items() if n]
        return min(days) if days else None


def load_activity(db, today):
    act = Activity()

    def solves():
        rows = (db.query(NotificationLog)
                .filter(NotificationLog.task_type.in_(("leetcode", "codeforces")),
                        NotificationLog.status == "success",
                        NotificationLog.is_completed == True)  # noqa: E712
                .all())
        for l in rows:
            at = l.completed_at or l.timestamp
            d = _day(at)
            if d is None:
                continue
            act.solves[d] += 1
            if l.task_type == "leetcode":
                if l.difficulty == "Medium":
                    act.mediums[d] += 1
                act.lc_events.append((at, d, l.title, l.difficulty, _topics_of(l.topic)))
        return True

    def reviews():
        rows = (db.query(NotificationLog.last_review_at, NotificationLog.title, NotificationLog.topic)
                .filter(NotificationLog.task_type == "leetcode", NotificationLog.status == "success",
                        NotificationLog.last_review_at != None)  # noqa: E711
                .all())
        for at, title, topic in rows:
            d = _day(at)
            act.reviews[d] += 1
            act.review_events.append((at, d, title, _topics_of(topic)))
        return True

    def focus():
        from api.domain.focus import FocusSession
        for started_at, minutes in db.query(FocusSession.started_at, FocusSession.minutes).all():
            local = to_ist(started_at)
            act.focus[local.date()] += minutes or 0
            if local.hour < MORNING_HOUR:
                act.morning_focus[local.date()] += minutes or 0
        return True

    def syllabus():
        from api.domain.syllabus import SyllabusTopic
        rows = db.query(SyllabusTopic.done, SyllabusTopic.done_at, SyllabusTopic.last_studied_at).all()
        for done, done_at, studied_at in rows:
            for d in {_day(done_at) if done else None, _day(studied_at)} - {None}:
                act.topics[d] += 1
        return True

    def lessons():
        from api.domain.learning import Lesson
        for (done_at,) in db.query(Lesson.done_at).filter(Lesson.done == True, Lesson.done_at != None).all():  # noqa: E712,E711
            act.lessons[_day(done_at)] += 1
        return True

    def rest():
        from api.domain.focus import theory_exam_days
        return set(theory_exam_days(db))

    _guard(db, solves, False, "solves")
    act.reviews_ok = _guard(db, reviews, False, "reviews")
    _guard(db, focus, False, "focus sessions")
    _guard(db, syllabus, False, "syllabus")
    _guard(db, lessons, False, "lessons")
    act.rest = _guard(db, rest, set(), "exam days")

    active = {d for d, n in act.solves.items() if n}
    act._first_active = min(active) if active else None

    def frozen():
        from api.domain.focus import compute_streak
        res = compute_streak(active, act.rest, today)
        return {datetime.strptime(x, "%Y-%m-%d").date() for x in res["frozen_days"]}

    act.frozen = _guard(db, frozen, set(), "streak freezes")
    return act


# ---------------- rings (pure) ----------------
def ring_goals(base_goal, exam_day=False, recovery=False):
    """Targets for one day. Exam day: Solve 1, Study 120 min. Recovery round: everything halved."""
    goals = {
        "solve": 1 if exam_day else max(1, int(base_goal)),
        "study_minutes": EXAM_STUDY_MINUTES if exam_day else STUDY_MINUTES,
        "study_topics": STUDY_TOPICS,
        "lessons": LESSON_GOAL,
        "revisions": REVISION_GOAL,
    }
    if recovery:
        goals = {k: max(1, ceil(v / 2)) for k, v in goals.items()}
    return goals


def _frac(value, goal):
    return min(1.0, value / goal) if goal else 1.0


def compute_rings(stats, goals, reviews_ok=True):
    """stats: {solves, focus, topics, lessons, reviews}. Returns the three ring dicts."""
    solves = stats.get("solves", 0)
    focus, topics = stats.get("focus", 0), stats.get("topics", 0)
    lessons, reviews = stats.get("lessons", 0), stats.get("reviews", 0)

    p_focus, p_topics = _frac(focus, goals["study_minutes"]), _frac(topics, goals["study_topics"])
    study_detail = f"{topics} syllabus topic{'s' if topics != 1 else ''} studied" if topics else "or study 1 syllabus topic"

    p_lessons = _frac(lessons, goals["lessons"])
    p_reviews = _frac(reviews, goals["revisions"]) if reviews_ok else 0.0
    if reviews_ok and p_reviews > p_lessons:
        learn_value, learn_goal, learn_unit = reviews, goals["revisions"], "reviews"
        learn_detail = f"{lessons} lesson{'s' if lessons != 1 else ''} today"
    else:
        learn_value, learn_goal, learn_unit = lessons, goals["lessons"], "lesson" if goals["lessons"] == 1 else "lessons"
        learn_detail = f"or {goals['revisions']} revisions ({reviews} today)" if reviews_ok else "System Design"

    def ring(key, label, value, goal, progress, unit, detail):
        progress = round(max(0.0, min(1.0, progress)), 4)
        return {"key": key, "label": label, "value": value, "goal": goal, "progress": progress,
                "closed": progress >= 1.0, "unit": unit, "detail": detail}

    return [
        ring("solve", "Solve", solves, goals["solve"], _frac(solves, goals["solve"]),
             "problem" if goals["solve"] == 1 else "problems", "LeetCode + Codeforces"),
        ring("study", "Study", focus, goals["study_minutes"], max(p_focus, p_topics), "min", study_detail),
        ring("learn", "Learn", learn_value, learn_goal, max(p_lessons, p_reviews), learn_unit, learn_detail),
    ]


def day_rings(act, d, base_goal):
    exam, rec = d in act.rest, act.recovery(d)
    stats = {"solves": act.solves.get(d, 0), "focus": act.focus.get(d, 0), "topics": act.topics.get(d, 0),
             "lessons": act.lessons.get(d, 0), "reviews": act.reviews.get(d, 0)}
    return compute_rings(stats, ring_goals(base_goal, exam, rec), act.reviews_ok), exam, rec


def rings_payload(act, today, base_goal):
    rings, exam, rec = day_rings(act, today, base_goal)
    solve_closed = rings[0]["closed"]
    closed = sum(r["closed"] for r in rings)
    return {"date": today.isoformat(), "rings": rings, "closed": closed, "all_closed": closed == 3,
            "recovery": rec, "exam_day": exam, "earned_episode": bool(solve_closed or exam)}


def history_payload(act, today, base_goal, days):
    first = today - timedelta(days=days - 1)
    cells = []
    for i in range(days):
        d = first + timedelta(days=i)
        rings, exam, rec = day_rings(act, d, base_goal)
        n = sum(r["closed"] for r in rings)
        cells.append({"date": d.isoformat(), "closed": n, "all_closed": n == 3, "rest": exam, "recovery": rec,
                      "perfect_week": False})

    # Perfect weeks: Monday-aligned, >= PERFECT_WEEK_DAYS days with all rings closed (rest days count)
    weeks = {}
    for c in cells:
        d = datetime.strptime(c["date"], "%Y-%m-%d").date()
        weeks.setdefault(_monday(d), []).append(c)
    perfect = []
    for ws, group in sorted(weeks.items()):
        if sum(1 for c in group if c["all_closed"] or c["rest"]) >= PERFECT_WEEK_DAYS:
            perfect.append(ws.isoformat())
            for c in group:
                c["perfect_week"] = True

    # Current all-rings streak: today still pending, rest days neutral
    streak, d = 0, today
    by_date = {c["date"]: c for c in cells}
    while True:
        c = by_date.get(d.isoformat())
        if c is None:
            break
        if c["all_closed"]:
            streak += 1
        elif not (c["rest"] or d == today):
            break
        d -= timedelta(days=1)

    return {"days": cells, "perfect_weeks": len(perfect), "perfect_week_starts": perfect,
            "all_closed_days": sum(1 for c in cells if c["all_closed"]), "streak": streak}


# ---------------- boss fight ----------------
def rival_for(topic):
    return RIVALS.get(topic, FALLBACK_RIVAL)


def _elo_ratings(db):
    """{topic: rating} from the insights topic Elo, {} when unavailable. No network."""
    def run():
        from api.domain.insights import compute_skills
        skills = compute_skills(db, allow_network=False)
        return {t["topic"]: t["rating"] for t in skills.get("topics", [])}
    return _guard(db, run, {}, "topic elo") or {}


def weakest_topic(db, act, seed):
    """Lowest topic Elo among the bank topics; ties (or no Elo) go to the least-solved topic,
    then a seeded coin flip so a fresh account doesn't always fight the same rival."""
    ratings = _elo_ratings(db)
    solved = Counter()
    for _, _, _, _, topics in act.lc_events:
        for t in topics:
            solved[t] += 1
    rng = random.Random(f"gym-boss:{seed}")
    tiebreak = {t: rng.random() for t in BANK_TOPICS}
    return min(BANK_TOPICS, key=lambda t: (round(ratings.get(t, 0)), solved[t], tiebreak[t]))


def boss_damage(act, bw):
    """Damage dealt to `bw` during its week. Returns (log oldest-first, total, ko_at|None)."""
    start = bw.week_start
    end = start + timedelta(days=7)
    events = []
    for at, d, title, diff, topics in act.lc_events:
        if start <= d < end and bw.topic in topics:
            events.append((at, title, DAMAGE.get(diff, DEFAULT_DAMAGE), "solve", diff))
    for at, d, title, topics in act.review_events:
        if start <= d < end and bw.topic in topics:
            events.append((at, title, REVIEW_DAMAGE, "review", None))
    events.sort(key=lambda e: (e[0], e[1]))
    total, ko_at, log = 0, None, []
    hp_max = bw.hp_max or BOSS_HP
    for at, title, dmg, kind, diff in events:
        total += dmg
        if ko_at is None and total >= hp_max:
            ko_at = at
        log.append({"title": title, "dmg": dmg, "at": _iso(at), "kind": kind, "difficulty": diff})
    return log, total, ko_at


def _sync_defeat(bw, ko_at):
    if bw.defeated_at != ko_at:
        bw.defeated_at = ko_at
        return True
    return False


def _ko_days(bw):
    return (_day(bw.defeated_at) - bw.week_start).days + 1 if bw.defeated_at else None


def ensure_week(db, act, today):
    monday = _monday(today)
    bw = db.query(BossWeek).filter(BossWeek.week_start == monday).first()
    if bw:
        return bw
    topic = weakest_topic(db, act, monday.isoformat())
    bw = BossWeek(week_start=monday, boss=rival_for(topic)[0], topic=topic, hp_max=BOSS_HP)
    db.add(bw)
    try:
        db.commit()
    except IntegrityError:  # a concurrent request created it first
        db.rollback()
        bw = db.query(BossWeek).filter(BossWeek.week_start == monday).first()
    return bw


def boss_payload(db, act, today):
    bw = ensure_week(db, act, today)
    log, total, ko_at = boss_damage(act, bw)
    changed = _sync_defeat(bw, ko_at)

    history = []
    past = (db.query(BossWeek).filter(BossWeek.week_start < bw.week_start)
            .order_by(BossWeek.week_start.desc()).limit(BOSS_HISTORY).all())
    for p in past:
        p_log, p_total, p_ko = boss_damage(act, p)
        changed = _sync_defeat(p, p_ko) or changed
        history.append({"week_start": p.week_start.isoformat(), "boss": p.boss, "topic": p.topic,
                        "hp_max": p.hp_max, "damage": p_total, "hits": len(p_log),
                        "defeated": p.defeated_at is not None, "defeated_at": _iso(p.defeated_at),
                        "ko_days": _ko_days(p), "result": "defeated" if p.defeated_at else "retreated"})
    if changed:
        db.commit()

    hp_max = bw.hp_max or BOSS_HP
    week_end = bw.week_start + timedelta(days=6)
    return {
        "boss": bw.boss, "topic": bw.topic, "tagline": rival_for(bw.topic)[1],
        "hp": max(0, hp_max - total), "hp_max": hp_max, "damage_total": total,
        "damage_log": list(reversed(log)),
        "days_left": max(0, (week_end - today).days + 1),
        "week_start": bw.week_start.isoformat(), "week_end": week_end.isoformat(),
        "defeated": bw.defeated_at is not None, "defeated_at": _iso(bw.defeated_at), "ko_days": _ko_days(bw),
        "damage_table": {**DAMAGE, "review": REVIEW_DAMAGE},
        "history": history,
    }


# ---------------- daily quest ----------------
QUEST_ORDER = ("medium_weak", "clear_revisions", "morning_focus", "sd_lessons", "syllabus_3", "oldest_pending")


def _count_due(db, now_utc):
    def run():
        from api.domain.repositories import NotificationRepository
        return NotificationRepository(db).count_due_reviews(now=now_utc)
    return _guard(db, run, 0, "due reviews")


def _oldest_pending(db):
    def run():
        return (db.query(NotificationLog)
                .filter(NotificationLog.task_type == "leetcode", NotificationLog.status == "success",
                        NotificationLog.is_completed == False)  # noqa: E712
                .order_by(NotificationLog.timestamp.asc(), NotificationLog.id.asc()).first())
    return _guard(db, run, None, "pending problems")


def _undone_count(db, what):
    def run():
        if what == "lessons":
            from api.domain.learning import Lesson
            return db.query(Lesson).filter(Lesson.done == False).count()  # noqa: E712
        from api.domain.syllabus import SyllabusTopic
        return db.query(SyllabusTopic).filter(SyllabusTopic.done == False).count()  # noqa: E712
    return _guard(db, run, 0, f"undone {what}")


def eligible_quests(db, act, day, now, allow_morning=True):
    """[(key, param)] in QUEST_ORDER. Only quests the data says are doable are offered."""
    out = [("medium_weak", weakest_topic(db, act, f"quest:{day.isoformat()}"))]
    due = _count_due(db, _to_utc(now))
    if due:
        out.append(("clear_revisions", str(due)))
    if allow_morning:
        out.append(("morning_focus", ""))
    if _undone_count(db, "lessons") >= 2:
        out.append(("sd_lessons", ""))
    if _undone_count(db, "topics") >= 3:
        out.append(("syllabus_3", ""))
    pending = _oldest_pending(db)
    if pending is not None:
        out.append(("oldest_pending", str(pending.id)))
    return out


def pick_quest(day, eligible, skips=0, exclude=()):
    """Deterministic per IST date (and skip count): seeded RNG over the eligible templates."""
    pool = [q for q in eligible if q[0] not in exclude] or list(eligible)
    rng = random.Random(f"gym-quest:{day.isoformat()}:{skips}")
    return rng.choice(pool)


def _quest_text(db, key, param):
    if key == "medium_weak":
        return f"Solve a Medium in {param}", "Any Medium LeetCode problem in your weakest topic"
    if key == "clear_revisions":
        return "Clear your revision queue", f"{param} review{'s' if param != '1' else ''} due this morning"
    if key == "morning_focus":
        return f"{MORNING_MINUTES} focus minutes before {MORNING_HOUR} AM", "Start a focus session early"
    if key == "sd_lessons":
        return "Watch 2 System Design lessons", "Coder Army System Design"
    if key == "syllabus_3":
        return "Mark 3 syllabus topics studied", "End-sem prep"
    if key == "oldest_pending":
        log = _guard(db, lambda: db.get(NotificationLog, int(param)), None, "pending problem") if param else None
        return "Solve a problem you skipped", (log.title if log else "Your oldest pending problem")
    return "Show up today", ""


def quest_progress(db, act, key, param, day, now):
    """(progress, goal) for a quest on `day`, straight from data."""
    if key == "medium_weak":
        n = sum(1 for _, d, _, diff, topics in act.lc_events if d == day and diff == "Medium" and param in topics)
        return min(n, 1), 1
    if key == "clear_revisions":
        goal = max(1, int(param or 1))
        due_now = _count_due(db, _to_utc(now))
        return min(goal, max(act.reviews.get(day, 0), goal - due_now)), goal
    if key == "morning_focus":
        return min(MORNING_MINUTES, act.morning_focus.get(day, 0)), MORNING_MINUTES
    if key == "sd_lessons":
        return min(2, act.lessons.get(day, 0)), 2
    if key == "syllabus_3":
        return min(3, act.topics.get(day, 0)), 3
    if key == "oldest_pending":
        log = _guard(db, lambda: db.get(NotificationLog, int(param)), None, "pending problem") if param else None
        return (1 if log is not None and log.is_completed else 0), 1
    return 0, 1


def _read_state(db, day):
    row = _guard(db, lambda: db.query(Settings).filter(Settings.key == QUEST_SETTING).first(), None, "quest state")
    if row and row.value:
        parts = row.value.split("|")
        if len(parts) == 4 and parts[0] == day.isoformat() and parts[1] in QUEST_ORDER:
            try:
                return parts[1], parts[2], int(parts[3])
            except ValueError:
                pass
    return None


def _write_state(db, day, key, param, skips):
    value = f"{day.isoformat()}|{key}|{param}|{skips}"[:100]
    row = db.query(Settings).filter(Settings.key == QUEST_SETTING).first()
    if row:
        row.value = value
    else:
        db.add(Settings(key=QUEST_SETTING, value=value))
    db.commit()


def quest_state(db, act, day, now):
    """Today's (key, param, skips). Stored on first sight so the quest can't drift during the day."""
    state = _read_state(db, day)
    if state:
        return state
    key, param = pick_quest(day, eligible_quests(db, act, day, now, allow_morning=now.hour < MORNING_HOUR))
    _guard(db, lambda: _write_state(db, day, key, param, 0), None, "quest save")
    return key, param, 0


def quest_payload(db, act, day, now, state=None):
    key, param, skips = state or quest_state(db, act, day, now)
    progress, goal = quest_progress(db, act, key, param, day, now)
    text, detail = _quest_text(db, key, param)
    tomorrow = day + timedelta(days=1)
    t_key, t_param = pick_quest(tomorrow, eligible_quests(db, act, tomorrow, now))
    t_text, _ = _quest_text(db, t_key, t_param)
    return {"date": day.isoformat(), "key": key, "text": text, "detail": detail,
            "progress": progress, "goal": goal, "done": progress >= goal, "xp": QUEST_XP,
            "skips_left": max(0, MAX_SKIPS - skips),
            "tomorrow_preview": {"key": t_key, "text": t_text}}


# ---------------- personal records ----------------
def records_payload(db, act, today, base_goal):
    def best(counter):
        items = [(n, d) for d, n in counter.items() if n and d <= today]
        if not items:
            return 0, None
        n, d = max(items, key=lambda x: (x[0], -x[1].toordinal()))  # first day the record was set
        return n, d.isoformat()

    solves_n, solves_d = best(act.solves)
    focus_n, focus_d = best(act.focus)

    weekly = Counter()
    for d, n in act.mediums.items():
        weekly[_monday(d)] += n
    med_n, med_d = best(weekly)

    # Longest all-rings streak (rest days neutral)
    first = act.first_day()
    best_streak, best_end, run = 0, None, 0
    if first:
        d = max(first, today - timedelta(days=RECORD_SPAN_DAYS))
        while d <= today:
            rings, exam, _ = day_rings(act, d, base_goal)
            if all(r["closed"] for r in rings):
                run += 1
                if run > best_streak:
                    best_streak, best_end = run, d.isoformat()
            elif not (exam or d == today):
                run = 0
            d += timedelta(days=1)

    def fastest():
        rows = db.query(BossWeek).filter(BossWeek.defeated_at != None).all()  # noqa: E711
        rows = [r for r in rows if _ko_days(r)]
        if not rows:
            return None
        return min(rows, key=lambda r: (_ko_days(r), r.week_start))

    ko = _guard(db, fastest, None, "boss records")

    return [
        {"key": "most_solves", "label": "Most solves in a day", "value": solves_n, "unit": "problems", "date": solves_d},
        {"key": "best_focus", "label": "Best focus day", "value": focus_n, "unit": "min", "date": focus_d},
        {"key": "rings_streak", "label": "Longest all-rings streak", "value": best_streak, "unit": "days", "date": best_end},
        {"key": "most_mediums", "label": "Most mediums in a week", "value": med_n, "unit": "mediums", "date": med_d},
        {"key": "fastest_ko", "label": "Fastest boss K.O.", "value": _ko_days(ko) if ko else None, "unit": "days",
         "date": _day(ko.defeated_at).isoformat() if ko else None,
         "detail": f"{ko.boss} · {ko.topic}" if ko else None},
    ]


# ---------------- routes ----------------
def _context(db):
    now = now_ist()
    today = now.date()
    return now, today, load_activity(db, today)


@gym_bp.route("/rings", methods=["GET"])
def rings():
    db = SessionLocal()
    try:
        _, today, act = _context(db)
        return _ok(rings_payload(act, today, _base_goal(db)))
    finally:
        db.close()


@gym_bp.route("/rings/history", methods=["GET"])
def rings_history():
    try:
        days = int(request.args.get("days", HISTORY_DAYS))
    except ValueError:
        return _err("days must be a whole number.")
    days = max(7, min(MAX_HISTORY_DAYS, days))
    db = SessionLocal()
    try:
        _, today, act = _context(db)
        return _ok(history_payload(act, today, _base_goal(db), days))
    finally:
        db.close()


@gym_bp.route("/boss", methods=["GET"])
def boss():
    db = SessionLocal()
    try:
        _, today, act = _context(db)
        return _ok(boss_payload(db, act, today))
    finally:
        db.close()


@gym_bp.route("/quest", methods=["GET"])
def quest():
    db = SessionLocal()
    try:
        now, today, act = _context(db)
        return _ok(quest_payload(db, act, today, now))
    finally:
        db.close()


@gym_bp.route("/quest/skip", methods=["POST"])
def skip_quest():
    db = SessionLocal()
    try:
        now, today, act = _context(db)
        key, param, skips = quest_state(db, act, today, now)
        if skips >= MAX_SKIPS:
            return _err("You already skipped today's quest. This one's yours.")
        progress, goal = quest_progress(db, act, key, param, today, now)
        if progress >= goal:
            return _err("Quest already complete.")
        eligible = eligible_quests(db, act, today, now, allow_morning=now.hour < MORNING_HOUR)
        new_key, new_param = pick_quest(today, eligible, skips + 1, exclude=(key,))
        _write_state(db, today, new_key, new_param, skips + 1)
        return _ok(quest_payload(db, act, today, now, state=(new_key, new_param, skips + 1)))
    finally:
        db.close()


@gym_bp.route("/records", methods=["GET"])
def records():
    db = SessionLocal()
    try:
        _, today, act = _context(db)
        return _ok({"records": records_payload(db, act, today, _base_goal(db))})
    finally:
        db.close()
