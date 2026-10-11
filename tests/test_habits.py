from datetime import datetime, timedelta

import pytest
from flask import Flask

from api.core.config import IST
from api.core.db import Base, engine, SessionLocal
from api.domain import habits as habits_mod
from api.domain.habits import HabitDay, habits_bp
from api.domain.models import Settings

FIXED_NOW = datetime(2026, 10, 11, 8, 15, tzinfo=IST)
TODAY = FIXED_NOW.date()


def d(n):
    """The IST day n days before today, as an ISO string."""
    return (TODAY - timedelta(days=n)).isoformat()


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(habits_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setattr(habits_mod, "now_ist", lambda: FIXED_NOW)
    yield app.test_client()
    db = SessionLocal()
    db.query(HabitDay).delete()
    db.query(Settings).filter(Settings.key.like("habit_%")).delete(synchronize_session=False)
    db.commit()
    db.close()


def _put(client, body, day="today", code=200):
    res = client.put(f"/api/habits/{day}", json=body)
    assert res.status_code == code, res.get_json()
    return res.get_json()


def test_today_empty_has_defaults(client):
    body = client.get("/api/habits/today").get_json()
    assert body["status"] == "success"
    assert body["targets"] == {"sleep": 7.5, "water": 8, "exercise": 30}
    assert body["data"]["day"] == TODAY.isoformat()
    assert body["data"]["logged"] is False
    assert body["data"]["sleep_hours"] is None and body["data"]["water_glasses"] == 0
    assert body["data"]["score"] == 0
    assert len(body["history"]) == 7 and body["history"][-1]["day"] == TODAY.isoformat()
    assert body["history"][0]["day"] == d(6)
    assert body["streaks"] == {"sleep": 0, "water": 0, "exercise": 0, "screen_off": 0}


def test_upsert_creates_one_row_and_partial_update_keeps_fields(client):
    a = _put(client, {"water_glasses": 3})["data"]
    assert a["water_glasses"] == 3 and a["logged"] is True and a["sleep_hours"] is None
    b = _put(client, {"sleep_hours": 7.3, "notes": "  slept ok "})["data"]
    assert b["water_glasses"] == 3  # untouched
    assert b["sleep_hours"] == 7.25  # rounded to a quarter hour
    assert b["notes"] == "slept ok"
    c = _put(client, {"exercise_min": 20, "screen_off_on_time": True, "steps": 6400})["data"]
    assert (c["water_glasses"], c["sleep_hours"], c["exercise_min"], c["steps"]) == (3, 7.25, 20, 6400)

    db = SessionLocal()
    assert db.query(HabitDay).count() == 1
    db.close()
    assert client.get("/api/habits/today").get_json()["data"]["exercise_min"] == 20

    # null clears the nullable fields
    e = _put(client, {"sleep_hours": None, "screen_off_on_time": None})["data"]
    assert e["sleep_hours"] is None and e["screen_off_on_time"] is None and e["water_glasses"] == 3


def test_validation(client):
    _put(client, {}, code=400)
    _put(client, {"water_glasses": -1}, code=400)
    _put(client, {"water_glasses": "3"}, code=400)
    _put(client, {"sleep_hours": 25}, code=400)
    _put(client, {"exercise_min": True}, code=400)
    _put(client, {"screen_off_on_time": "yes"}, code=400)
    _put(client, {"notes": "x" * 2001}, code=400)
    _put(client, {"water_glasses": 1}, day="not-a-date", code=400)
    _put(client, {"water_glasses": 1}, day=(TODAY + timedelta(days=1)).isoformat(), code=400)
    _put(client, {"water_glasses": 1}, day=d(400), code=400)


def test_backfill_yesterday(client):
    y = _put(client, {"sleep_hours": 8}, day=d(1))["data"]
    assert y["day"] == d(1) and y["sleep_hours"] == 8.0
    body = client.get("/api/habits/today").get_json()
    assert body["yesterday"]["sleep_hours"] == 8.0
    assert body["data"]["logged"] is False


def test_targets(client):
    res = client.post("/api/habits/targets", json={"sleep": 8, "water": 10, "exercise": 45})
    assert res.status_code == 200
    assert res.get_json()["targets"] == {"sleep": 8.0, "water": 10, "exercise": 45}
    # the full settings key works too, and other targets are kept
    res = client.post("/api/habits/targets", json={"habit_water_target": 6})
    assert res.get_json()["targets"] == {"sleep": 8.0, "water": 6, "exercise": 45}
    assert client.get("/api/habits/today").get_json()["targets"]["water"] == 6

    assert client.post("/api/habits/targets", json={}).status_code == 400
    assert client.post("/api/habits/targets", json={"water": 0}).status_code == 400
    assert client.post("/api/habits/targets", json={"sleep": "8"}).status_code == 400


def test_body_score(client):
    # sleep 7.5/7.5 -> 40, water 4/8 -> 15, exercise 0 -> 0, screens no -> 0
    assert _put(client, {"sleep_hours": 7.5, "water_glasses": 4})["data"]["score"] == 55
    # overshooting a target is capped at 100% of its weight
    body = _put(client, {"water_glasses": 20, "exercise_min": 90, "screen_off_on_time": True})
    assert body["data"]["score"] == 100
    assert body["data"]["met"] == {"sleep": True, "water": True, "exercise": True, "screen_off": True}
    # a stricter target lowers the score: sleep 7.5/10 -> 30
    client.post("/api/habits/targets", json={"sleep": 10})
    assert client.get("/api/habits/today").get_json()["data"]["score"] == 90


def test_streaks(client):
    # water met for the 3 days before today, then a gap
    for n in (1, 2, 3):
        _put(client, {"water_glasses": 8, "exercise_min": 30 if n == 1 else 0}, day=d(n))
    _put(client, {"water_glasses": 2}, day=d(4))
    _put(client, {"water_glasses": 9}, day=d(5))  # before the gap: doesn't count

    s = client.get("/api/habits/today").get_json()["streaks"]
    # today not met yet: streak still counts from yesterday
    assert s["water"] == 3 and s["exercise"] == 1 and s["sleep"] == 0

    s = _put(client, {"water_glasses": 8})["streaks"]
    assert s["water"] == 4
    # yesterday missed -> exercise streak is only today
    _put(client, {"exercise_min": 0}, day=d(1))
    s = _put(client, {"exercise_min": 35})["streaks"]
    assert s["exercise"] == 1


def test_history_series_and_averages(client):
    _put(client, {"sleep_hours": 6, "water_glasses": 4, "exercise_min": 10, "screen_off_on_time": False}, day=d(2))
    _put(client, {"sleep_hours": 8, "water_glasses": 8, "exercise_min": 30, "screen_off_on_time": True})
    body = client.get("/api/habits?days=7").get_json()
    assert body["days"] == 7 and len(body["data"]) == 7
    assert body["data"][-1]["day"] == TODAY.isoformat()
    av = body["averages"]
    assert av["days_logged"] == 2
    assert av["sleep_hours"] == 7.0 and av["water_glasses"] == 6.0 and av["exercise_min"] == 20.0
    assert av["screen_off_rate"] == 0.5
    assert body["hit_rate"]["water"] == round(1 / 7, 2)

    assert len(client.get("/api/habits?days=9999").get_json()["data"]) == 365
    assert client.get("/api/habits?days=abc").status_code == 400
