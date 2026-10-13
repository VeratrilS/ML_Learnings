import json
import pytest

from api.app import app
from api.core.db import Base, SessionLocal, engine
from api.domain.hotseat import HotSeatSession, PROFESSORS, CURATED_TOPICS


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.query(HotSeatSession).delete()
    db.commit()
    yield
    db.query(HotSeatSession).delete()
    db.commit()
    db.close()


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_list_topics(client):
    res = client.get("/api/hotseat/topics")
    assert res.status_code == 200
    data = res.get_json()
    assert "topics" in data
    assert "professors" in data
    assert len(data["topics"]) >= len(CURATED_TOPICS)
    assert len(data["professors"]) == 3


def test_start_session(client):
    res = client.post("/api/hotseat/session/start", json={
        "subject": "Raft Consensus & Split Brains",
        "difficulty": "undergraduate"
    })
    assert res.status_code == 201
    data = res.get_json()
    sess = data["session"]
    assert sess["status"] == "active"
    assert sess["composure"] == 100
    assert sess["current_turn"] == 1
    assert sess["questions_total"] == 3
    assert len(sess["turns"]) == 1
    assert sess["turns"][0]["question"] is not None


def test_answer_turn_advance(client):
    res = client.post("/api/hotseat/session/start", json={
        "subject": "Self-Attention & KV-Caching",
        "difficulty": "masters"
    })
    sess = res.get_json()["session"]
    sid = sess["id"]

    # Candidate provides a strong technical answer
    ans_res = client.post(f"/api/hotseat/session/{sid}/answer", json={
        "answer": "The self-attention mechanism operates in O(N^2) memory and compute due to the softmax denominator over the key-value sequence. FlashAttention resolves memory bandwidth bottlenecks by tiling query, key, and value blocks directly in GPU SRAM without materializing the full N by N attention matrix to HBM."
    })
    assert ans_res.status_code == 200
    updated = ans_res.get_json()["session"]
    assert updated["current_turn"] == 2
    assert updated["composure"] >= 95
    assert len(updated["turns"]) == 2
    # Turn 1 should now have feedback and score
    t1 = updated["turns"][0]
    assert t1["score"] is not None
    assert t1["feedback"] is not None


def test_roasted_when_composure_drops_to_zero(client):
    res = client.post("/api/hotseat/session/start", json={
        "subject": "TLB Shootdowns & Page Faults",
        "difficulty": "undergraduate"
    })
    sid = res.get_json()["session"]["id"]

    # Directly set composure low to test roasting condition
    db = SessionLocal()
    session = db.query(HotSeatSession).filter_by(id=sid).first()
    session.composure = 10
    db.commit()
    db.close()

    # Provide an awful trivial answer
    ans_res = client.post(f"/api/hotseat/session/{sid}/answer", json={
        "answer": "idk"
    })
    assert ans_res.status_code == 200
    roasted = ans_res.get_json()["session"]
    assert roasted["status"] == "roasted"
    assert roasted["composure"] == 0
    assert "Roasted" in roasted["final_verdict"]


def test_complete_defense_and_xp(client):
    res = client.post("/api/hotseat/session/start", json={
        "subject": "Raft Consensus & Split Brains",
        "difficulty": "undergraduate"  # 3 rounds
    })
    sid = res.get_json()["session"]["id"]

    # Answer all 3 rounds
    for i in range(3):
        ans_res = client.post(f"/api/hotseat/session/{sid}/answer", json={
            "answer": "In Raft, leader election requires a majority quorum of node votes in the current term. If network partitions occur, the minority partition cannot elect a leader or commit entries because it cannot assemble a quorum. Log indices ensure monotonically increasing terms prevent split-brain commit conflicts."
        })
        assert ans_res.status_code == 200
    
    final_sess = ans_res.get_json()["session"]
    assert final_sess["status"] == "completed"
    assert final_sess["xp_awarded"] >= 100
    assert final_sess["final_verdict"] in ["Summa Cum Laude", "Magna Cum Laude", "Defense Passed"]


def test_history_and_stats(client):
    # Run one session
    client.post("/api/hotseat/session/start", json={"subject": "MVCC & Repeatable Read Anomalies", "difficulty": "masters"})
    res = client.get("/api/hotseat/history")
    assert res.status_code == 200
    data = res.get_json()
    assert "sessions" in data
    assert "stats" in data
    assert data["stats"]["total_defenses"] >= 1
