from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from api.core.config import IST
from api.core.db import Base, engine, SessionLocal
from api.domain import journal as journal_mod
from api.domain import xp as xp_mod
from api.domain.journal import JournalEntry, journal_bp
from api.domain.models import NotificationLog
from api.domain.syllabus import Subject, SyllabusTopic
from api.domain.todos import Todo
from api.domain.xp import RANKS, rank_for, xp_bp

try:  # optional module owned by another feature
    from api.domain.learning import Course, Lesson
except ImportError:  # pragma: no cover
    Course = Lesson = None

FIXED_NOW = datetime(2026, 10, 11, 21, 15, tzinfo=IST)
TODAY = FIXED_NOW.date()
YESTERDAY = TODAY - timedelta(days=1)
# 21:15 IST == 15:45 UTC (naive UTC is how timestamps are stored)
NOW_UTC = FIXED_NOW.astimezone(timezone.utc).replace(tzinfo=None)
LAST_WEEK_UTC = NOW_UTC - timedelta(days=7)


def _wipe():
    db = SessionLocal()
    models = [JournalEntry, NotificationLog, Todo, SyllabusTopic, Subject] + ([Lesson, Course] if Lesson else [])
    for model in models:
        db.query(model).delete()
    db.commit()
    db.close()


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(journal_bp)
    app.register_blueprint(xp_bp)
    Base.metadata.create_all(bind=engine)
    _wipe()
    yield app
    _wipe()


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setattr(journal_mod, "now_ist", lambda: FIXED_NOW)
    monkeypatch.setattr(xp_mod, "now_ist", lambda: FIXED_NOW)
    yield app.test_client()
    _wipe()


# ---------------- journal ----------------
def test_journal_empty_day(client):
    body = client.get("/api/journal/today").get_json()
    assert body["status"] == "success"
    assert body["data"] is None and body["yesterday"] is None
    assert body["day"] == TODAY.isoformat()


def test_journal_upsert_and_read(client):
    res = client.put("/api/journal/today", json={
        "mood": 4, "energy": "3", "win": "  Solved a Hard  ", "blocker": "", "top3": ["Graphs", "  ", "DBMS unit 3"],
    })
    assert res.status_code == 200, res.get_json()
    e = res.get_json()["data"]
    assert e["day"] == TODAY.isoformat()
    assert (e["mood"], e["energy"]) == (4, 3)
    assert e["win"] == "Solved a Hard" and e["blocker"] == ""
    assert e["top3"] == ["Graphs", "DBMS unit 3"]

    # Partial update keeps the other fields, and doesn't create a second row
    e2 = client.put("/api/journal/today", json={"mood": 5}).get_json()["data"]
    assert e2["id"] == e["id"] and e2["mood"] == 5 and e2["energy"] == 3 and e2["top3"] == ["Graphs", "DBMS unit 3"]
    db = SessionLocal()
    assert db.query(JournalEntry).count() == 1
    db.close()

    body = client.get("/api/journal/today").get_json()
    assert body["data"]["mood"] == 5

    listing = client.get("/api/journal?days=7").get_json()
    assert [x["day"] for x in listing["data"]] == [TODAY.isoformat()]


def test_journal_yesterday_top3_and_list(client):
    db = SessionLocal()
    db.add(JournalEntry(day=YESTERDAY, mood=2, top3='["Mock interview", "Revise DP"]'))
    db.add(JournalEntry(day=TODAY - timedelta(days=40), mood=3))
    db.commit()
    db.close()

    body = client.get("/api/journal/today").get_json()
    assert body["data"] is None
    assert body["yesterday"]["top3"] == ["Mock interview", "Revise DP"]

    assert len(client.get("/api/journal?days=30").get_json()["data"]) == 1
    assert len(client.get("/api/journal?days=60").get_json()["data"]) == 2
    assert client.get("/api/journal?days=abc").status_code == 400


def test_journal_rollover_after_midnight(client, monkeypatch):
    client.put("/api/journal/today", json={"win": "Late night grind"})
    monkeypatch.setattr(journal_mod, "now_ist", lambda: FIXED_NOW + timedelta(hours=4))  # 01:15 next day
    body = client.get("/api/journal/today").get_json()
    assert body["day"] == TODAY.isoformat()
    assert body["data"]["win"] == "Late night grind"


@pytest.mark.parametrize("payload", [
    {"mood": 0}, {"mood": 6}, {"energy": "x"}, {"mood": True}, {"mood": 2.5},
    {"win": 5}, {"blocker": "x" * 501},
    {"top3": "nope"}, {"top3": ["a", "b", "c", "d"]}, {"top3": [1]}, {"top3": ["x" * 301]},
])
def test_journal_validation(client, payload):
    res = client.put("/api/journal/today", json=payload)
    assert res.status_code == 400
    assert res.get_json()["status"] == "error" and res.get_json()["message"]


def test_journal_requires_json(client):
    assert client.put("/api/journal/today", data="nope").status_code == 400


# ---------------- xp ----------------
def test_rank_thresholds():
    assert rank_for(0) == ("Rookie", "C-Class", 0.0, 300)
    assert rank_for(150)[2] == 0.5
    assert rank_for(299)[0] == "Rookie"
    assert rank_for(300) == ("C-Class", "B-Class", 0.0, 600)
    assert rank_for(2000)[0] == "A-Class"
    assert rank_for(3999)[:2] == ("A-Class", "Japanese Champion")
    assert rank_for(12000) == ("World Champion", None, 1.0, 0)
    assert rank_for(99999)[0] == "World Champion"
    thresholds = [t for _, t in RANKS]
    assert thresholds == sorted(thresholds) and thresholds[0] == 0


def _log(task_type, done=True, when=NOW_UTC, **kw):
    return NotificationLog(task_type=task_type, title=f"{task_type} {kw.get('slug', '')}", status=kw.pop("status", "success"),
                           is_completed=done, completed_at=when if done else None, **kw)


def test_xp_breakdown(client):
    db = SessionLocal()
    db.add_all([
        _log("leetcode", difficulty="Easy", review_stage=2, when=LAST_WEEK_UTC),  # 10, +2 reviews
        _log("leetcode", difficulty="Medium", review_stage=1),  # 20 today, +1 review
        _log("leetcode", difficulty="Hard"),  # 40 today
        _log("leetcode", difficulty=None, when=LAST_WEEK_UTC),  # 10 (unknown)
        _log("leetcode", done=False, difficulty="Hard"),  # not solved
        _log("leetcode", difficulty="Hard", status="hidden"),  # hidden: ignored
        _log("codeforces", difficulty="1500"),  # 15 + 15 today
        _log("codeforces", difficulty="800", when=LAST_WEEK_UTC),  # 15 + 8
        _log("watch", slug="1:1", when=LAST_WEEK_UTC),  # 2
        _log("watch", slug="1:2"),  # 2 today
        Todo(text="a", done=True, day=TODAY, done_at=NOW_UTC),  # 2 today
        Todo(text="b", done=True, day=YESTERDAY, done_at=LAST_WEEK_UTC),  # 2
        Todo(text="c", done=False, day=TODAY),
    ])
    subject = Subject(name="Software Testing")
    db.add(subject)
    db.flush()
    db.add_all([
        SyllabusTopic(subject_id=subject.id, title="Black box", done=True, done_at=NOW_UTC),  # 8 today
        SyllabusTopic(subject_id=subject.id, title="White box", done=False),
    ])
    if Lesson is not None:
        course = Course(title="System Design")
        db.add(course)
        db.flush()
        db.add_all([
            Lesson(course_id=course.id, position=1, title="L1", video_id="abcdefghijk", done=True, done_at=LAST_WEEK_UTC),
            Lesson(course_id=course.id, position=2, title="L2", video_id="bcdefghijkl", done=False),
        ])
    db.commit()
    db.close()

    body = client.get("/api/xp").get_json()
    assert body["status"] == "success"
    d = body["data"]
    b = d["breakdown"]
    assert (b["leetcode"]["count"], b["leetcode"]["xp"], b["leetcode"]["today"]) == (4, 80, 60)
    assert (b["codeforces"]["count"], b["codeforces"]["xp"], b["codeforces"]["today"]) == (2, 53, 30)
    assert (b["revisions"]["count"], b["revisions"]["xp"]) == (3, 15)
    assert (b["episodes"]["count"], b["episodes"]["xp"], b["episodes"]["today"]) == (2, 4, 2)
    assert (b["todos"]["count"], b["todos"]["xp"], b["todos"]["today"]) == (2, 4, 2)
    assert (b["syllabus"]["count"], b["syllabus"]["xp"], b["syllabus"]["today"]) == (1, 8, 8)
    lessons_xp = 6 if Lesson is not None else 0
    assert b["lessons"]["xp"] == lessons_xp
    assert b["focus"]["xp"] >= 0  # optional source; never breaks the endpoint

    expected = 80 + 53 + 15 + 4 + 4 + 8 + lessons_xp + b["focus"]["xp"]
    assert d["xp"] == expected
    assert d["today_xp"] == 60 + 30 + 2 + 2 + 8 + b["focus"]["today"]
    assert d["rank"] == "Rookie" and d["next_rank"] == "C-Class"
    assert d["xp_to_next"] == 300 - expected
    assert 0 < d["progress"] < 1


def test_xp_empty(client):
    d = client.get("/api/xp").get_json()["data"]
    assert d["rank"] == "Rookie" and d["progress"] == 0.0 and d["today_xp"] == 0
    assert d["xp"] == sum(v["xp"] for v in d["breakdown"].values())


def test_xp_rank_up(client):
    db = SessionLocal()
    db.add_all([_log("leetcode", difficulty="Hard", slug=str(i)) for i in range(25)])  # 1000 XP
    db.commit()
    db.close()
    d = client.get("/api/xp").get_json()["data"]
    assert d["breakdown"]["leetcode"]["xp"] == 1000
    assert d["rank"] == "B-Class" and d["next_rank"] == "A-Class"
