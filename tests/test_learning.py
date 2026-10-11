from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from api.core.config import IST
from api.core.db import Base, engine, SessionLocal
from api.domain import learning as learning_mod
from api.domain.learning import (Course, Lesson, learning_bp, _add_course,
                                 SEEDED_KEY, SEED_COURSE_KEY, SEED_VERSION)
from api.domain.learning_data import CODER_ARMY_SYSTEM_DESIGN
from api.domain.models import Settings
from api.domain.repositories import NotificationRepository

FIXED_NOW = datetime(2026, 10, 11, 9, 30, tzinfo=IST)
PLAYLIST_ID = "PLQEaRBV9gAFvzp6XhcNFpk1WdOcyVo9qT"


class Clock:
    """Mutable frozen clock so a test can move across IST days."""
    def __init__(self):
        self.now = FIXED_NOW

    def __call__(self):
        return self.now


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(learning_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(learning_mod, "now_ist", c)
    return c


@pytest.fixture
def client(app, clock):
    yield app.test_client()
    db = SessionLocal()
    db.query(Lesson).delete()
    db.query(Course).delete()
    db.query(Settings).filter(Settings.key.in_([SEEDED_KEY, SEED_COURSE_KEY])).delete(synchronize_session=False)
    db.commit()
    db.close()


def _get(client):
    res = client.get("/api/learning")
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["status"] == "success"
    return body["data"]


def _done(client, lesson_id, done=True):
    res = client.put(f"/api/learning/lessons/{lesson_id}", json={"done": done})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _settings():
    db = SessionLocal()
    repo = NotificationRepository(db)
    out = repo.get_setting(SEEDED_KEY), repo.get_setting(SEED_COURSE_KEY)
    db.close()
    return out


# ---------------- seed data ----------------
def test_seed_data_is_the_40_video_system_design_playlist():
    c = CODER_ARMY_SYSTEM_DESIGN
    assert c["title"] == "System Design Full Course" and c["channel"] == "Coder Army"
    assert c["playlist_id"] == PLAYLIST_ID and c["playlist_url"].endswith(PLAYLIST_ID)
    assert len(c["videos"]) == 40
    assert [v[0] for v in c["videos"]] == list(range(1, 41))
    assert len({v[1] for v in c["videos"]}) == 40
    assert all(len(v[1]) == 11 and v[2] and v[3] for v in c["videos"])


# ---------------- seeding ----------------
def test_seed_on_first_get(client):
    data = _get(client)
    assert data["daily_min"] == 1 and data["done_today"] == 0 and data["streak"] == 0
    assert len(data["courses"]) == 1
    course = data["courses"][0]
    assert course["title"] == "System Design Full Course"
    assert course["total"] == 40 and course["done"] == 0 and course["progress"] == 0
    first = course["lessons"][0]
    assert first["position"] == 1 and first["video_id"] == CODER_ARMY_SYSTEM_DESIGN["videos"][0][1]
    assert first["url"] == f"https://www.youtube.com/watch?v={first['video_id']}&list={PLAYLIST_ID}&index=1"
    assert first["thumbnail"].endswith(f"/vi/{first['video_id']}/mqdefault.jpg")
    assert course["today"]["lesson"]["id"] == first["id"]
    assert course["total_seconds"] == course["remaining_seconds"] > 0
    assert _settings() == (SEED_VERSION, str(course["id"]))
    assert len(_get(client)["courses"]) == 1  # no duplicate seed


def test_no_reseed_after_delete(client):
    course = _get(client)["courses"][0]
    db = SessionLocal()
    db.query(Lesson).delete()
    db.query(Course).filter(Course.id == course["id"]).delete()
    db.commit()
    db.close()
    assert _get(client)["courses"] == []


def test_old_wrong_seed_is_repaired_and_progress_kept(client):
    """A v1 seed that stored the wrong playlist gets replaced; progress on shared videos survives."""
    good = CODER_ARMY_SYSTEM_DESIGN["videos"]
    wrong = [(i + 1, f"wrong{i:06d}", f"Uploads video {i}", "10:00") for i in range(447)]
    wrong[0] = good[0]
    db = SessionLocal()
    bad = _add_course(db, "System Design Full Course", "Coder Army",
                      "https://www.youtube.com/playlist?list=UUwrong", "UUwrong", wrong)
    other = _add_course(db, "Other", "Someone", None, "PLother", [(1, "other000001", "Other 1", "5:00")])
    db.commit()
    overlap = db.query(Lesson).filter(Lesson.course_id == bad.id, Lesson.video_id == good[0][1]).one()
    overlap.done, overlap.done_at = True, datetime(2026, 10, 10, 4)
    db.commit()
    NotificationRepository(db).set_setting(SEEDED_KEY, "1")  # legacy: seed course id never recorded
    other_id = other.id
    db.close()

    data = _get(client)
    assert [(c["title"], c["total"]) for c in data["courses"]] == [("System Design Full Course", 40), ("Other", 1)]
    seed = data["courses"][0]
    assert seed["playlist_id"] == PLAYLIST_ID
    assert [x["video_id"] for x in seed["lessons"]] == [v[1] for v in good]
    assert seed["lessons"][0]["done"] is True and seed["done"] == 1
    assert data["courses"][1]["id"] == other_id
    assert _settings() == (SEED_VERSION, str(seed["id"]))
    assert [c["total"] for c in _get(client)["courses"]] == [40, 1]  # idempotent


def test_old_correct_seed_is_kept(client):
    course = _get(client)["courses"][0]
    _done(client, course["lessons"][0]["id"])
    db = SessionLocal()
    NotificationRepository(db).set_setting(SEEDED_KEY, "1")
    db.close()
    again = _get(client)["courses"][0]
    assert again["id"] == course["id"] and again["done"] == 1


# ---------------- marking done ----------------
def test_mark_done_and_undo(client):
    lesson = _get(client)["courses"][0]["lessons"][0]
    out = _done(client, lesson["id"])
    assert out["done"] is True and out["done_at"] and out["done_day"] == "2026-10-11"

    data = _get(client)
    course = data["courses"][0]
    assert course["done"] == 1 and course["progress"] == round(100 / 40)
    assert [x["id"] for x in course["today"]["done_today"]] == [lesson["id"]]
    assert course["today"]["lesson"]["position"] == 2
    assert data["done_today"] == 1 and data["streak"] == 1

    out = _done(client, lesson["id"], False)
    assert out["done"] is False and out["done_at"] is None
    data = _get(client)
    assert data["courses"][0]["done"] == 0 and data["done_today"] == 0
    assert data["courses"][0]["today"]["lesson"]["position"] == 1


def test_done_twice_keeps_original_timestamp(client, clock):
    lesson = _get(client)["courses"][0]["lessons"][0]
    first = _done(client, lesson["id"])
    clock.now = FIXED_NOW + timedelta(hours=2)
    assert _done(client, lesson["id"])["done_at"] == first["done_at"]


def test_daily_minimum_is_not_a_cap(client, clock):
    lessons = _get(client)["courses"][0]["lessons"]
    for i in range(3):
        clock.now = FIXED_NOW + timedelta(minutes=10 * i)
        _done(client, lessons[i]["id"])
    data = _get(client)
    assert data["done_today"] == 3 and data["daily_min"] == 1
    assert [x["position"] for x in data["courses"][0]["today"]["done_today"]] == [1, 2, 3]
    assert data["courses"][0]["today"]["lesson"]["position"] == 4


def test_up_next_is_first_not_done(client):
    lessons = _get(client)["courses"][0]["lessons"]
    _done(client, lessons[1]["id"])  # watched #2 out of order
    assert _get(client)["courses"][0]["today"]["lesson"]["position"] == 1


def test_all_done_has_no_next(client):
    for lesson in _get(client)["courses"][0]["lessons"]:
        _done(client, lesson["id"])
    course = _get(client)["courses"][0]
    assert course["today"]["lesson"] is None and course["progress"] == 100 and course["remaining_seconds"] == 0


def test_today_uses_ist_boundary(client, clock):
    lesson = _get(client)["courses"][0]["lessons"][0]
    # 00:15 IST on Oct 11 is still Oct 10 in UTC; it must count as "today" in IST
    clock.now = datetime(2026, 10, 11, 0, 15, tzinfo=IST)
    _done(client, lesson["id"])
    assert _get(client)["done_today"] == 1
    clock.now = datetime(2026, 10, 12, 0, 5, tzinfo=IST)
    data = _get(client)
    assert data["done_today"] == 0 and data["streak"] == 1  # yesterday still keeps the streak alive


def test_streak(client, clock):
    lessons = _get(client)["courses"][0]["lessons"]
    for i, days_ago in enumerate([3, 2, 1]):
        clock.now = FIXED_NOW - timedelta(days=days_ago)
        _done(client, lessons[i]["id"])
    clock.now = FIXED_NOW
    data = _get(client)
    assert data["streak"] == 3 and data["courses"][0]["streak"] == 3
    _done(client, lessons[3]["id"])
    _done(client, lessons[4]["id"])  # two on one day still counts as one streak day
    assert _get(client)["streak"] == 4
    clock.now = FIXED_NOW + timedelta(days=2)  # missed a whole day
    assert _get(client)["streak"] == 0


def test_streak_gap(client, clock):
    lessons = _get(client)["courses"][0]["lessons"]
    clock.now = FIXED_NOW - timedelta(days=3)
    _done(client, lessons[0]["id"])
    clock.now = FIXED_NOW
    _done(client, lessons[1]["id"])
    assert _get(client)["streak"] == 1


def test_done_at_is_naive_utc(client):
    lesson = _get(client)["courses"][0]["lessons"][0]
    _done(client, lesson["id"])
    db = SessionLocal()
    row = db.get(Lesson, lesson["id"])
    assert row.done_at.tzinfo is None
    assert row.done_at == FIXED_NOW.astimezone(timezone.utc).replace(tzinfo=None)
    db.close()


def test_validation(client):
    lesson = _get(client)["courses"][0]["lessons"][0]
    assert client.put("/api/learning/lessons/999999", json={"done": True}).status_code == 404
    for bad in [{}, {"notes": "x"}]:
        res = client.put(f"/api/learning/lessons/{lesson['id']}", json=bad)
        assert res.status_code == 400 and res.get_json()["status"] == "error"
    assert client.put(f"/api/learning/lessons/{lesson['id']}", data="nope").status_code == 400
    assert client.post("/api/learning/courses", json={}).status_code in (404, 405)  # no import endpoint
