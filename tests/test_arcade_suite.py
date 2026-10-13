import json
import pytest

from api.app import app
from api.core.db import Base, SessionLocal, engine
from api.domain.bughunt import BugHuntLog, CASES
from api.domain.complexity import ComplexityPlayer, CHALLENGES
from api.domain.lofi import LofiSession, PRESETS


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.query(BugHuntLog).delete()
    db.query(ComplexityPlayer).delete()
    db.query(LofiSession).delete()
    db.commit()
    yield
    db.query(BugHuntLog).delete()
    db.query(ComplexityPlayer).delete()
    db.query(LofiSession).delete()
    db.commit()
    db.close()


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_bughunt_list_and_triage(client):
    # List cases
    res = client.get("/api/bughunt/cases")
    assert res.status_code == 200
    cases = res.get_json()["cases"]
    assert len(cases) == len(CASES)

    # Triage correct answer for integer overflow
    cid = "bh_01_int_overflow"
    triage_res = client.post(f"/api/bughunt/case/{cid}/triage", json={
        "line": 5,
        "patch": "A",
        "time_taken_sec": 12
    })
    assert triage_res.status_code == 200
    data = triage_res.get_json()
    assert data["solved"] is True
    assert data["xp_awarded"] >= 80

    # Check stats
    stats_res = client.get("/api/bughunt/stats")
    stats = stats_res.get_json()["stats"]
    assert stats["solved_cases"] == 1
    assert stats["total_xp"] >= 80


def test_complexity_challenges_and_guess(client):
    # List challenges
    res = client.get("/api/complexity/challenges")
    assert res.status_code == 200
    challenges = res.get_json()["challenges"]
    assert len(challenges) == len(CHALLENGES)

    # Make correct guess
    cid = "c_01_geometric_nested"
    guess_res = client.post("/api/complexity/guess", json={
        "challenge_id": cid,
        "guessed_time": "O(N log N)",
        "wager": 50
    })
    assert guess_res.status_code == 200
    data = guess_res.get_json()
    assert data["correct"] is True
    assert data["chips_delta"] > 0
    assert data["player"]["current_streak"] == 1


def test_lofi_presets_and_log(client):
    # List presets
    res = client.get("/api/lofi/presets")
    assert res.status_code == 200
    presets = res.get_json()["presets"]
    assert len(presets) == len(PRESETS)

    # Log 20 minutes focus session
    log_res = client.post("/api/lofi/session/log", json={
        "preset_id": "binaural_alpha",
        "duration_min": 20
    })
    assert log_res.status_code == 201
    assert log_res.get_json()["xp_awarded"] == 8

    # Check stats
    stats_res = client.get("/api/lofi/stats")
    assert stats_res.status_code == 200
    stats = stats_res.get_json()["stats"]
    assert stats["total_minutes"] == 20
    assert stats["total_xp"] == 8
