from datetime import datetime, timedelta

import pytest
from flask import Flask

from api.core.db import SessionLocal
from api.domain import flashcards as fc
from api.domain.flashcard_deck import DECK
from api.domain.flashcards import CardReview, Flashcard, flashcards_bp, next_state, recall_probability
from api.domain.models import Settings


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(flashcards_bp)
    yield app


@pytest.fixture
def client(app):
    yield app.test_client()
    db = SessionLocal()
    db.query(CardReview).delete()
    db.query(Flashcard).delete()
    db.query(Settings).filter(Settings.key.in_(["cards_seeded", "cards_new_per_day"])).delete()
    db.commit()
    db.close()


class FakeLLM:
    reply = {}
    calls = []

    def __init__(self, *a, **kw):
        FakeLLM.calls.append(kw)

    def generate_json(self, prompt, **kw):
        if isinstance(FakeLLM.reply, Exception):
            raise FakeLLM.reply
        return FakeLLM.reply


@pytest.fixture
def fake_llm(monkeypatch):
    FakeLLM.calls = []
    monkeypatch.setattr(fc, "LLMClient", FakeLLM)
    return FakeLLM


# ---------------- deck ----------------
def test_deck_is_complete_and_unique():
    assert len(DECK) >= 180
    subjects = {c["subject"] for c in DECK}
    assert subjects == {"OS", "DBMS", "CN", "OOP", "SQL"}
    qs = [c["question"].strip().lower() for c in DECK]
    assert len(qs) == len(set(qs))
    for c in DECK:
        assert c["question"].strip() and len(c["answer"]) > 40
        assert c["difficulty"] in (1, 2, 3)


# ---------------- memory model ----------------
def test_first_review_intervals():
    assert next_state(None, None, 0, "again")[0] == pytest.approx(0.2)
    assert next_state(None, None, 0, "hard")[0] == pytest.approx(1.0)
    assert next_state(None, None, 0, "good")[0] == pytest.approx(2.5)
    assert next_state(None, None, 0, "easy")[0] == pytest.approx(5.0)


def test_recall_is_90_percent_at_stability():
    assert recall_probability(10, 10) == pytest.approx(0.9)
    assert recall_probability(10, 0) == 1.0
    assert recall_probability(10, 30) < recall_probability(10, 5)


@pytest.mark.parametrize("s", [0.2, 1.0, 2.5, 7.0, 30.0, 120.0])
@pytest.mark.parametrize("d", [1.0, 5.0, 10.0])
@pytest.mark.parametrize("ratio", [0.2, 1.0, 3.0])
def test_growth_is_monotone_in_grade(s, d, ratio):
    out = [next_state(s, d, s * ratio, g)[0] for g in ("again", "hard", "good", "easy")]
    assert out[0] < out[1] < out[2]
    assert out[2] < out[3] or out[2] == out[3] == 365.0  # only ties at the cap
    assert out[0] <= s <= out[1]
    assert all(0.2 <= x <= 365 for x in out)


def test_stability_is_capped():
    s, d = 300.0, 1.0
    for _ in range(5):
        s, d = next_state(s, d, s, "easy")
    assert s == 365.0


def test_good_streak_reaches_mastery():
    s, d = next_state(None, None, 0, "good")
    for _ in range(4):
        s, d = next_state(s, d, s, "good")
    assert s >= 21


# ---------------- routes ----------------
def test_seed_on_first_get_and_only_once(client):
    body = client.get("/api/cards").get_json()
    assert body["status"] == "success"
    assert len(body["data"]) == len(DECK)
    assert {s["subject"] for s in body["subjects"]} == {"OS", "DBMS", "CN", "OOP", "SQL"}
    os_stats = next(s for s in body["subjects"] if s["subject"] == "OS")
    assert os_stats["total"] == sum(1 for c in DECK if c["subject"] == "OS")
    assert os_stats["mastered"] == 0 and os_stats["mastery"] == 0
    # delete one; a second GET must not re-seed
    cid = body["data"][0]["id"]
    assert client.delete(f"/api/cards/{cid}").get_json()["status"] == "success"
    assert len(client.get("/api/cards").get_json()["data"]) == len(DECK) - 1


def test_list_filters(client):
    only = client.get("/api/cards?subject=SQL").get_json()["data"]
    assert only and all(c["subject"] == "SQL" for c in only)
    found = client.get("/api/cards?q=belady").get_json()["data"]
    assert any("Belady" in c["question"] for c in found)


def test_today_respects_new_limit_and_interleaves(client):
    body = client.get("/api/cards/today?limit=20").get_json()
    cards = body["data"]
    assert len(cards) == 10  # default new per day
    assert body["counts"]["new"] == 10 and body["counts"]["due"] == 0
    assert body["counts"]["done_today"] == 0
    assert len({c["subject"] for c in cards[:5]}) == 5  # subjects interleaved
    assert set(cards[0]["preview"]) == {"again", "hard", "good", "easy"}


def test_new_per_day_setting(client):
    client.get("/api/cards")
    db = SessionLocal()
    db.add(Settings(key="cards_new_per_day", value="3"))
    db.commit()
    db.close()
    body = client.get("/api/cards/today").get_json()
    assert len(body["data"]) == 3


def test_review_schedules_and_counts(client):
    cards = client.get("/api/cards/today").get_json()["data"]
    a, b = cards[0], cards[1]
    r = client.post(f"/api/cards/{a['id']}/review", json={"grade": "good"}).get_json()
    assert r["status"] == "success"
    card = r["data"]
    assert card["reps"] == 1 and card["stability"] == pytest.approx(2.5)
    assert card["state"] == "review"
    client.post(f"/api/cards/{b['id']}/review", json={"grade": "again"})

    body = client.get("/api/cards/today").get_json()
    counts = body["counts"]
    assert counts["done_today"] == 2
    assert counts["new_today"] == 2
    assert counts["new"] == 8
    assert counts["streak"] == 1
    ids = {c["id"] for c in body["data"]}
    assert a["id"] not in ids  # not due for 2.5 days


def test_due_cards_come_back_and_lapses(client):
    card = client.get("/api/cards/today").get_json()["data"][0]
    client.post(f"/api/cards/{card['id']}/review", json={"grade": "good"})
    db = SessionLocal()
    c = db.get(Flashcard, card["id"])
    c.due_at = fc._utcnow() - timedelta(hours=1)
    c.last_review_at = fc._utcnow() - timedelta(days=3)
    db.commit()
    db.close()
    body = client.get("/api/cards/today").get_json()
    assert body["counts"]["due"] == 1
    assert body["data"][0]["id"] == card["id"] or card["id"] in {c["id"] for c in body["data"]}
    r = client.post(f"/api/cards/{card['id']}/review", json={"grade": "again"}).get_json()["data"]
    assert r["lapses"] == 1 and r["reps"] == 2
    assert r["stability"] < 2.5


def test_review_validation(client):
    client.get("/api/cards")
    cid = client.get("/api/cards").get_json()["data"][0]["id"]
    assert client.post(f"/api/cards/{cid}/review", json={"grade": "meh"}).status_code == 400
    assert client.post("/api/cards/999999/review", json={"grade": "good"}).status_code == 404


def test_streak_counts_consecutive_days(client):
    client.get("/api/cards")
    cid = client.get("/api/cards").get_json()["data"][0]["id"]
    db = SessionLocal()
    now = fc._utcnow()
    for days in (1, 2, 4):  # yesterday, day before; gap at day 3
        db.add(CardReview(card_id=cid, grade="good", at=now - timedelta(days=days)))
    db.commit()
    db.close()
    assert client.get("/api/cards/today").get_json()["counts"]["streak"] == 2


def test_create_update_delete(client):
    res = client.post("/api/cards", json={"subject": "os", "question": " What is a TLB shootdown? ",
                                          "answer": "Invalidating stale TLB entries on other cores via IPIs.",
                                          "tags": "tlb, Multi Core", "difficulty": 9})
    card = res.get_json()["data"]
    assert card["subject"] == "OS" and card["source"] == "user"
    assert card["question"] == "What is a TLB shootdown?"
    assert card["tags"] == ["tlb", "multi-core"] and card["difficulty"] == 3
    assert client.post("/api/cards", json={"subject": "OS", "question": "", "answer": "x"}).status_code == 400

    client.post(f"/api/cards/{card['id']}/review", json={"grade": "easy"})
    upd = client.put(f"/api/cards/{card['id']}", json={"answer": "IPIs flush other cores' TLBs.", "reset": True}).get_json()["data"]
    assert upd["answer"] == "IPIs flush other cores' TLBs." and upd["reps"] == 0 and upd["stability"] is None
    assert client.put(f"/api/cards/{card['id']}", json={"question": "  "}).status_code == 400
    assert client.delete(f"/api/cards/{card['id']}").get_json()["status"] == "success"
    assert client.put(f"/api/cards/{card['id']}", json={"answer": "x"}).status_code == 404


def test_generate_dedupes_and_caps(client, fake_llm):
    client.get("/api/cards")
    fake_llm.reply = {"cards": [
        {"question": "Process vs thread?", "answer": "Duplicate of a seed card, should be skipped."},
        {"question": "What is a TLB miss penalty?", "answer": "Extra memory access(es) to walk the page table.",
         "tags": ["tlb"], "difficulty": 2},
        {"question": "what is a TLB miss penalty", "answer": "Same question again in this batch."},
        {"question": "What is copy-on-write in fork()?", "answer": "Parent and child share pages until one writes."},
        {"question": "", "answer": "no question"},
        "garbage",
    ]}
    body = client.post("/api/cards/generate", json={"subject": "OS", "topic": "memory", "count": 50}).get_json()
    assert body["status"] == "success"
    qs = [c["question"] for c in body["data"]]
    assert qs == ["What is a TLB miss penalty?", "What is copy-on-write in fork()?"]
    assert all(c["source"] == "ai" and c["subject"] == "OS" for c in body["data"])
    assert body["skipped"] == 4
    assert fake_llm.calls[-1].get("budget") == 60

    fake_llm.reply = {"cards": [{"question": f"Distinct question number {i} about paging?", "answer": "An answer."}
                                for i in range(20)]}
    body = client.post("/api/cards/generate", json={"subject": "OS", "count": 50}).get_json()
    assert len(body["data"]) == 10


def test_generate_handles_llm_failure(client, fake_llm):
    fake_llm.reply = RuntimeError("quota")
    res = client.post("/api/cards/generate", json={"subject": "CN", "topic": "tcp"})
    assert res.status_code == 502 and res.get_json()["status"] == "error"
    assert client.post("/api/cards/generate", json={"subject": "", "topic": "tcp"}).status_code == 400
