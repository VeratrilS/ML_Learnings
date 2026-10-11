from datetime import datetime, timedelta

import pytest
from flask import Flask

from api.core.config import IST
from api.core.db import Base, engine, SessionLocal
from api.domain import sheets as sheets_mod
from api.domain.sheets import SheetProblem, sheets_bp, seed_if_needed, _seeded_key, SEED_VERSION
from api.domain.sheet_data import APPLE_SHEET
from api.domain.models import Settings
from api.domain.repositories import NotificationRepository

FIXED_NOW = datetime(2026, 10, 12, 9, 30, tzinfo=IST)


class Clock:
    """Mutable frozen clock so a test can move across IST days."""
    def __init__(self):
        self.now = FIXED_NOW

    def __call__(self):
        return self.now


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(sheets_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(sheets_mod, "now_ist", c)
    return c


@pytest.fixture
def client(app, clock):
    yield app.test_client()
    db = SessionLocal()
    db.query(SheetProblem).delete()
    db.query(Settings).filter(Settings.key == _seeded_key("apple")).delete(synchronize_session=False)
    db.commit()
    db.close()


def _get(client):
    res = client.get("/api/sheets/apple")
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["status"] == "success"
    return body["data"]


def _done(client, problem_id, done=True):
    res = client.put(f"/api/sheets/problems/{problem_id}", json={"done": done})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


# ---------------- seed data ----------------
def test_seed_data_is_apple_medium_and_hard_only():
    problems = APPLE_SHEET["problems"]
    assert len(problems) == 130
    assert [p[0] for p in problems] == list(range(1, 131))
    assert {p[4] for p in problems} == {"Medium", "Hard"}
    assert sum(p[4] == "Hard" for p in problems) == 24
    assert len({p[3] for p in problems}) == 130  # slugs unique
    assert all(p[1] > 0 and p[2] and p[3] == p[3].lower() and 0 < p[5] < 100 for p in problems)
    assert problems[0][2] == "LRU Cache"


# ---------------- seeding ----------------
def test_seed_on_first_get(client):
    data = _get(client)
    assert data["title"] == "Apple Interview Sheet" and data["company"] == "Apple"
    assert data["total"] == 130 and data["done"] == 0 and data["progress"] == 0
    assert data["by_difficulty"] == {"Medium": {"done": 0, "total": 106}, "Hard": {"done": 0, "total": 24}}
    assert data["daily_min"] == 1 and data["done_today"] == 0 and data["streak"] == 0
    first = data["problems"][0]
    assert first["position"] == 1 and first["leetcode_id"] == 146 and first["difficulty"] == "Medium"
    assert first["url"] == "https://leetcode.com/problems/lru-cache/"
    assert first["topics"][:2] == ["Hash Table", "Linked List"]
    assert data["next"]["id"] == first["id"]
    assert len(_get(client)["problems"]) == 130  # no duplicate seed


def test_premium_problems_link_to_leetcode(client):
    by_slug = {p["slug"]: p for p in _get(client)["problems"]}
    for slug in ("design-hit-counter", "design-tic-tac-toe", "meeting-rooms-ii"):
        assert by_slug[slug]["url"] == f"https://leetcode.com/problems/{slug}/"


def test_reseed_on_new_version_keeps_progress(client, monkeypatch):
    first = _get(client)["problems"][0]
    _done(client, first["id"])
    monkeypatch.setattr(sheets_mod, "SEED_VERSION", "test-next")
    data = _get(client)
    assert data["total"] == 130
    assert data["problems"][0]["id"] == first["id"] and data["problems"][0]["done"] is True
    db = SessionLocal()
    assert NotificationRepository(db).get_setting(_seeded_key("apple")) == "test-next"
    db.close()


def test_seed_is_noop_when_current(client):
    _get(client)
    db = SessionLocal()
    try:
        assert NotificationRepository(db).get_setting(_seeded_key("apple")) == SEED_VERSION
        assert seed_if_needed(db, "apple") is False
    finally:
        db.close()


# ---------------- marking ----------------
def test_mark_done_and_undo(client):
    data = _get(client)
    hard = next(p for p in data["problems"] if p["difficulty"] == "Hard")
    out = _done(client, hard["id"])
    assert out["done"] is True and out["done_day"] == "2026-10-12"
    data = _get(client)
    assert data["done"] == 1 and data["done_today"] == 1 and data["streak"] == 1
    assert data["by_difficulty"]["Hard"]["done"] == 1 and data["by_difficulty"]["Medium"]["done"] == 0
    assert data["progress"] == round(100 / 130)

    out = _done(client, hard["id"], False)
    assert out["done"] is False and out["done_at"] is None
    data = _get(client)
    assert data["done"] == 0 and data["done_today"] == 0 and data["streak"] == 0


def test_next_skips_solved(client):
    problems = _get(client)["problems"]
    _done(client, problems[0]["id"])
    assert _get(client)["next"]["id"] == problems[1]["id"]


def test_streak_across_days(client, clock):
    problems = _get(client)["problems"]
    clock.now = FIXED_NOW - timedelta(days=2)
    _done(client, problems[0]["id"])
    clock.now = FIXED_NOW - timedelta(days=1)
    _done(client, problems[1]["id"])
    clock.now = FIXED_NOW
    data = _get(client)
    assert data["streak"] == 2 and data["done_today"] == 0  # today still open
    _done(client, problems[2]["id"])
    assert _get(client)["streak"] == 3


# ---------------- errors ----------------
def test_unknown_sheet_404(client):
    assert client.get("/api/sheets/google").status_code == 404


def test_update_validation(client):
    pid = _get(client)["problems"][0]["id"]
    assert client.put(f"/api/sheets/problems/{pid}", json={}).status_code == 400
    assert client.put(f"/api/sheets/problems/{pid}", data="x").status_code == 400
    assert client.put("/api/sheets/problems/999999", json={"done": True}).status_code == 404
