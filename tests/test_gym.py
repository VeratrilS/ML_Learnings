from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from api.core.config import IST
from api.core.db import Base, SessionLocal, engine
from api.domain import gym as gym_mod
from api.domain.focus import FocusSession
from api.domain.gym import BossWeek, gym_bp, compute_rings, pick_quest, ring_goals
from api.domain.learning import Course, Lesson
from api.domain.models import NotificationLog, Settings
from api.domain.syllabus import Subject, SyllabusTopic

FIXED_NOW = datetime(2026, 10, 14, 15, 0, tzinfo=IST)  # a Wednesday
TODAY = FIXED_NOW.date()
MONDAY = TODAY - timedelta(days=TODAY.weekday())


def utc(day, hour=12, minute=0):
    """IST wall-clock on `day` -> naive UTC (how the DB stores timestamps)."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST).astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(gym_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def db():
    s = SessionLocal()
    for model in (NotificationLog, Settings, FocusSession, SyllabusTopic, Subject, Lesson, Course, BossWeek):
        s.query(model).delete()
    s.commit()
    yield s
    s.close()


@pytest.fixture
def client(app, db, monkeypatch):
    monkeypatch.setattr(gym_mod, "now_ist", lambda: FIXED_NOW)
    return app.test_client()


def solve(db, day, difficulty="Medium", topic="Arrays", task="leetcode", hour=12, title=None, review_on=None):
    at = utc(day, hour)
    log = NotificationLog(task_type=task, title=title or f"{topic} {difficulty} {day} {hour}", status="success",
                          is_completed=True, timestamp=at - timedelta(hours=1), completed_at=at,
                          difficulty=difficulty, topic=topic)
    if review_on:
        log.last_review_at = utc(review_on, 13)
    db.add(log)
    db.commit()
    return log


def focus(db, day, minutes, hour=12):
    db.add(FocusSession(started_at=utc(day, hour), minutes=minutes, completed=True))
    db.commit()


def lessons(db, day, n, undone=0):
    course = Course(title="System Design", is_active=True)
    db.add(course)
    db.commit()
    for i in range(n):
        db.add(Lesson(course_id=course.id, position=i, title=f"L{i}", video_id=f"v{i}", done=True, done_at=utc(day, 18)))
    for i in range(undone):
        db.add(Lesson(course_id=course.id, position=100 + i, title=f"U{i}", video_id=f"u{i}", done=False))
    db.commit()


def get(client, path):
    res = client.get(f"/api/gym{path}")
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def ring(data, key):
    return next(r for r in data["rings"] if r["key"] == key)


# ---------------- rings ----------------
def test_ring_goals_exam_and_recovery():
    assert ring_goals(2) == {"solve": 2, "study_minutes": 60, "study_topics": 1, "lessons": 1, "revisions": 3}
    exam = ring_goals(3, exam_day=True)
    assert exam["solve"] == 1 and exam["study_minutes"] == 120
    rec = ring_goals(4, recovery=True)
    assert rec["solve"] == 2 and rec["study_minutes"] == 30 and rec["revisions"] == 2 and rec["lessons"] == 1
    both = ring_goals(2, exam_day=True, recovery=True)
    assert both["solve"] == 1 and both["study_minutes"] == 60


def test_study_ring_takes_best_of_focus_or_topics():
    goals = ring_goals(2)
    half = compute_rings({"focus": 30}, goals)
    assert ring({"rings": half}, "study")["progress"] == 0.5
    topic = compute_rings({"focus": 30, "topics": 1}, goals)
    assert ring({"rings": topic}, "study")["closed"]


def test_rings_today(client, db):
    yesterday = TODAY - timedelta(days=1)
    solve(db, yesterday)
    solve(db, TODAY, "Easy")
    solve(db, TODAY, "1500", task="codeforces", topic=None)
    focus(db, TODAY, 45)
    lessons(db, TODAY, 1)
    data = get(client, "/rings")
    assert ring(data, "solve")["value"] == 2 and ring(data, "solve")["closed"]
    assert ring(data, "study")["value"] == 45 and ring(data, "study")["progress"] == 0.75
    assert ring(data, "learn")["closed"]
    assert data["closed"] == 2 and not data["all_closed"]
    assert data["earned_episode"] and not data["recovery"] and not data["exam_day"]


def test_learn_ring_from_revisions(client, db):
    for i in range(3):
        solve(db, TODAY - timedelta(days=10), title=f"old {i}", review_on=TODAY)
    data = get(client, "/rings")
    learn = ring(data, "learn")
    assert learn["closed"] and learn["unit"] == "reviews" and learn["value"] == 3


def test_recovery_round_halves_targets(client, db):
    solve(db, TODAY - timedelta(days=3))
    solve(db, TODAY - timedelta(days=2))  # nothing yesterday, no freeze banked
    solve(db, TODAY)
    data = get(client, "/rings")
    assert data["recovery"]
    assert ring(data, "solve")["goal"] == 1 and ring(data, "solve")["closed"]
    assert ring(data, "study")["goal"] == 30


def test_freeze_prevents_recovery(client, db):
    for i in range(2, 9):  # 7 consecutive days earn a freeze, spent on yesterday
        solve(db, TODAY - timedelta(days=i))
    data = get(client, "/rings")
    assert not data["recovery"]
    assert ring(data, "solve")["goal"] == 2


def test_exam_day(client, db):
    db.add(Subject(name="Software Testing", kind="theory", exam_date=TODAY))
    db.commit()
    data = get(client, "/rings")
    assert data["exam_day"]
    assert ring(data, "solve")["goal"] == 1 and ring(data, "study")["goal"] == 120
    assert data["earned_episode"]  # rest day: the episode is earned without a solve


def test_history_perfect_week(client, db):
    last_monday = MONDAY - timedelta(days=7)
    for i in range(5):
        d = last_monday + timedelta(days=i)
        solve(db, d, title=f"a{i}")
        solve(db, d, title=f"b{i}")
        focus(db, d, 60)
        lessons(db, d, 1)
    data = get(client, "/rings/history?days=21")
    assert len(data["days"]) == 21
    cells = {c["date"]: c for c in data["days"]}
    assert cells[last_monday.isoformat()]["closed"] == 3
    assert cells[last_monday.isoformat()]["perfect_week"]
    assert data["perfect_weeks"] == 1 and data["perfect_week_starts"] == [last_monday.isoformat()]
    assert data["all_closed_days"] == 5
    assert not cells[MONDAY.isoformat()]["perfect_week"]


# ---------------- boss ----------------
def test_boss_assigned_to_least_solved_topic(client, db, monkeypatch):
    monkeypatch.setattr(gym_mod, "_elo_ratings", lambda db: {})
    for t in gym_mod.BANK_TOPICS:
        if t != "Heaps":
            solve(db, TODAY - timedelta(days=40), topic=t)
    data = get(client, "/boss")
    assert data["topic"] == "Heaps" and data["boss"] == "Ozuma Geronimo"
    assert data["hp"] == data["hp_max"] == 100 and not data["defeated"]
    assert data["days_left"] == 5  # Wed..Sun
    # Stable for the rest of the week
    assert get(client, "/boss")["topic"] == "Heaps"


def test_boss_from_topic_elo(client, db):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for i in range(6):  # sent long ago, never solved -> Graphs Elo drops
        db.add(NotificationLog(task_type="leetcode", title=f"g{i}", status="success", is_completed=False,
                               timestamp=now - timedelta(days=20 + i), difficulty="Medium", topic="Graphs"))
    db.commit()
    data = get(client, "/boss")
    assert data["topic"] == "Graphs" and data["boss"] == "Mashiba Ryo"


def test_boss_damage_and_ko(client, db):
    db.add(BossWeek(week_start=MONDAY, boss="Mashiba Ryo", topic="Graphs", hp_max=100))
    db.commit()
    solve(db, MONDAY, "Medium", "Graphs")                              # 35
    solve(db, MONDAY + timedelta(days=1), "Hard", "Graphs")            # 60
    solve(db, MONDAY, "Hard", "Arrays")                                # other topic: no damage
    solve(db, MONDAY - timedelta(days=2), "Hard", "Graphs")            # last week: no damage
    data = get(client, "/boss")
    assert data["hp"] == 5 and not data["defeated"] and len(data["damage_log"]) == 2
    assert data["damage_log"][0]["dmg"] == 60  # newest first

    solve(db, MONDAY - timedelta(days=30), "Easy", "Graphs", title="BFS review", review_on=TODAY)  # +10 review
    data = get(client, "/boss")
    assert data["hp"] == 0 and data["defeated"] and data["ko_days"] == 3
    assert data["damage_log"][0]["kind"] == "review"


def test_boss_retreats_into_history(client, db):
    db.add(BossWeek(week_start=MONDAY - timedelta(days=7), boss="Sendo Takeshi", topic="Dynamic Programming"))
    db.add(BossWeek(week_start=MONDAY, boss="Mashiba Ryo", topic="Graphs"))
    db.commit()
    data = get(client, "/boss")
    assert data["history"][0]["boss"] == "Sendo Takeshi"
    assert data["history"][0]["result"] == "retreated" and not data["history"][0]["defeated"]


# ---------------- quest ----------------
def test_pick_quest_is_deterministic():
    eligible = [("medium_weak", "Graphs"), ("morning_focus", ""), ("sd_lessons", "")]
    assert pick_quest(TODAY, eligible) == pick_quest(TODAY, eligible)
    picks = {pick_quest(TODAY + timedelta(days=i), eligible)[0] for i in range(30)}
    assert len(picks) > 1
    assert pick_quest(TODAY, eligible, 1, exclude=("medium_weak", "morning_focus"))[0] == "sd_lessons"


def test_quest_stable_and_has_preview(client, db):
    first = get(client, "/quest")
    second = get(client, "/quest")
    assert first["text"] == second["text"] and first["xp"] == 25
    assert first["tomorrow_preview"]["text"]
    assert first["skips_left"] == 1


def test_quest_auto_progress(client, db):
    gym_mod._write_state(db, TODAY, "sd_lessons", "", 0)
    data = get(client, "/quest")
    assert data["text"] == "Watch 2 System Design lessons" and data["progress"] == 0 and not data["done"]
    lessons(db, TODAY, 2)
    data = get(client, "/quest")
    assert data["progress"] == 2 and data["done"]

    gym_mod._write_state(db, TODAY, "medium_weak", "Graphs", 0)
    assert not get(client, "/quest")["done"]
    solve(db, TODAY, "Medium", "Graphs")
    data = get(client, "/quest")
    assert data["text"] == "Solve a Medium in Graphs" and data["done"]


def test_quest_skip_once(client, db):
    gym_mod._write_state(db, TODAY, "morning_focus", "", 0)
    res = client.post("/api/gym/quest/skip")
    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    assert data["key"] != "morning_focus" and data["skips_left"] == 0
    assert get(client, "/quest")["key"] == data["key"]
    assert client.post("/api/gym/quest/skip").status_code == 400


# ---------------- records ----------------
def test_records(client, db):
    best_day = TODAY - timedelta(days=5)
    for i in range(3):
        solve(db, best_day, "Medium", title=f"r{i}")
    solve(db, TODAY - timedelta(days=2), "Easy")
    focus(db, TODAY - timedelta(days=4), 90)
    focus(db, TODAY - timedelta(days=3), 40)
    db.add(BossWeek(week_start=MONDAY - timedelta(days=14), boss="Volg Zangief", topic="Binary Trees",
                    defeated_at=utc(MONDAY - timedelta(days=13), 20)))
    db.commit()
    recs = {r["key"]: r for r in get(client, "/records")["records"]}
    assert recs["most_solves"]["value"] == 3 and recs["most_solves"]["date"] == best_day.isoformat()
    assert recs["best_focus"]["value"] == 90
    assert recs["most_mediums"]["value"] == 3
    assert recs["fastest_ko"]["value"] == 2 and "Volg" in recs["fastest_ko"]["detail"]
    assert recs["rings_streak"]["value"] == 0
