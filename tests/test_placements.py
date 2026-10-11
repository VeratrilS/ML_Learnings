from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from api.core.config import now_ist
from api.core.db import Base, engine, SessionLocal
from api.domain.placements import Application, ApplicationEvent, placements_bp


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(placements_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def client(app):
    yield app.test_client()
    db = SessionLocal()
    db.query(ApplicationEvent).delete()
    db.query(Application).delete()
    db.commit()
    db.close()


def _iso_in(**delta):
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def _add(client, **fields):
    body = {"company": "Acme", "role": "SDE 1", **fields}
    res = client.post("/api/placements", json=body)
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _list(client):
    res = client.get("/api/placements")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "success"
    return body


def test_create_defaults_and_list(client):
    a = _add(client, company="  Google  ", ctc_lpa="32.5", link="careers.google.com/x")
    assert a["company"] == "Google"
    assert a["stage"] == "wishlist" and a["source"] == "on-campus"
    assert a["ctc_lpa"] == 32.5
    assert a["link"] == "https://careers.google.com/x"
    assert [e["kind"] for e in a["events"]] == ["stage"]
    assert a["events"][0]["text"] == "Added to Wishlist"

    body = _list(client)
    assert [x["id"] for x in body["data"]] == [a["id"]]
    assert body["summary"]["total"] == 1


def test_update_and_delete(client):
    a = _add(client, stage="applied", source="referral")
    res = client.put(f"/api/placements/{a['id']}", json={
        "role": "SDE Intern", "location": "Bengaluru", "notes": "Ask about team",
        "deadline": "2026-12-01", "next_event_at": "2026-12-02T10:00:00+05:30", "next_event_label": "OA on HackerRank",
    })
    assert res.status_code == 200, res.get_json()
    d = res.get_json()["data"]
    assert d["role"] == "SDE Intern" and d["location"] == "Bengaluru" and d["notes"] == "Ask about team"
    assert d["deadline"] == "2026-12-01"
    assert d["next_event_at"].startswith("2026-12-02T04:30:00")  # stored as UTC
    assert d["next_event_label"] == "OA on HackerRank"
    assert len(d["events"]) == 1  # no stage change -> no new event

    # Clearing optional fields
    d = client.put(f"/api/placements/{a['id']}", json={"next_event_at": None, "ctc_lpa": ""}).get_json()["data"]
    assert d["next_event_at"] is None and d["ctc_lpa"] is None

    assert client.delete(f"/api/placements/{a['id']}").status_code == 200
    assert _list(client)["data"] == []
    db = SessionLocal()
    assert db.query(ApplicationEvent).count() == 0
    db.close()
    assert client.delete(f"/api/placements/{a['id']}").status_code == 404
    assert client.put("/api/placements/999999", json={"stage": "oa"}).status_code == 404


def test_stage_change_appends_event(client):
    a = _add(client, stage="applied")
    d = client.put(f"/api/placements/{a['id']}", json={"stage": "OA"}).get_json()["data"]
    assert d["stage"] == "oa"
    assert d["events"][0]["kind"] == "stage" and d["events"][0]["text"] == "Applied → OA"
    assert d["stage_changed_at"] >= a["stage_changed_at"]

    d = client.put(f"/api/placements/{a['id']}", json={"stage": "interview"}).get_json()["data"]
    assert [e["text"] for e in d["events"] if e["kind"] == "stage"][:2] == ["OA → Interview", "Applied → OA"]

    # Same stage again: nothing new
    d = client.put(f"/api/placements/{a['id']}", json={"stage": "interview"}).get_json()["data"]
    assert len(d["events"]) == 3


def test_add_note_and_round_events(client):
    a = _add(client)
    res = client.post(f"/api/placements/{a['id']}/events", json={"kind": "round", "text": "Round 1 - DSA: 2 mediums"})
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["data"]["kind"] == "round"
    assert body["application"]["events"][0]["text"] == "Round 1 - DSA: 2 mediums"

    res = client.post(f"/api/placements/{a['id']}/events", json={"text": "Recruiter said results by Friday"})
    assert res.get_json()["data"]["kind"] == "note"

    assert client.post(f"/api/placements/{a['id']}/events", json={"text": "  "}).status_code == 400
    assert client.post(f"/api/placements/{a['id']}/events", json={"kind": "stage", "text": "x"}).status_code == 400
    assert client.post("/api/placements/999999/events", json={"text": "x"}).status_code == 404
    events = _list(client)["data"][0]["events"]
    assert len(events) == 3


def test_summary_counts_upcoming_deadlines_offers(client):
    today = now_ist().date()
    _add(client, company="W", stage="wishlist", deadline=(today + timedelta(days=2)).isoformat())
    _add(client, company="Late", stage="applied", next_event_at=_iso_in(days=5), next_event_label="Round 2 - DSA")
    _add(client, company="Soon", stage="oa", next_event_at=_iso_in(days=1), next_event_label="OA on HackerRank")
    _add(client, company="Far", stage="interview", next_event_at=_iso_in(days=20))
    _add(client, company="Past", stage="hr", next_event_at=_iso_in(days=-2))
    _add(client, company="Closed", stage="rejected", next_event_at=_iso_in(days=2),
         deadline=(today + timedelta(days=1)).isoformat())
    _add(client, company="Old", stage="applied", deadline=(today - timedelta(days=1)).isoformat())
    _add(client, company="Later", stage="applied", deadline=(today + timedelta(days=9)).isoformat())
    _add(client, company="Today", stage="applied", deadline=today.isoformat())
    _add(client, company="Small", stage="offer", ctc_lpa=12)
    _add(client, company="Big", stage="offer", ctc_lpa=44)
    _add(client, company="NoCtc", stage="offer")

    s = _list(client)["summary"]
    assert s["total"] == 12
    assert s["counts"] == {"wishlist": 1, "applied": 4, "oa": 1, "interview": 1, "hr": 1,
                           "offer": 3, "rejected": 1, "withdrawn": 0}
    assert s["active"] == 7  # applied + oa + interview + hr
    assert s["oa_pending"] == 1 and s["interviews"] == 2
    assert [u["company"] for u in s["upcoming"]] == ["Soon", "Late"]
    assert s["upcoming"][0]["label"] == "OA on HackerRank"
    assert [d["company"] for d in s["deadlines"]] == ["Today", "W"]
    assert [d["days_left"] for d in s["deadlines"]] == [0, 2]
    assert s["offers_count"] == 3
    assert [o["company"] for o in s["offers"]] == ["Big", "Small", "NoCtc"]
    assert s["best_ctc"] == 44


def test_naive_event_time_is_ist(client):
    a = _add(client, next_event_at="2026-11-05T14:00")
    assert a["next_event_at"].startswith("2026-11-05T08:30:00")


@pytest.mark.parametrize("body, message", [
    ({"role": "SDE"}, "Company is required."),
    ({"company": "   "}, "Company is required."),
    ({"company": "X", "stage": "ghosted"}, "Stage must be one of"),
    ({"company": "X", "source": "linkedin"}, "Source must be one of"),
    ({"company": "X", "ctc_lpa": "lots"}, "CTC must be a number"),
    ({"company": "X", "ctc_lpa": -3}, "CTC must be between"),
    ({"company": "X", "deadline": "next week"}, "Deadline must be a date"),
    ({"company": "X", "next_event_at": "soon"}, "Event time must be"),
    ({"company": "X" * 121}, "at most 120"),
])
def test_create_validation(client, body, message):
    res = client.post("/api/placements", json=body)
    assert res.status_code == 400
    j = res.get_json()
    assert j["status"] == "error" and message in j["message"]


def test_update_validation_leaves_row_unchanged(client):
    a = _add(client, stage="applied")
    res = client.put(f"/api/placements/{a['id']}", json={"stage": "offer", "company": ""})
    assert res.status_code == 400
    row = _list(client)["data"][0]
    assert row["stage"] == "applied" and row["company"] == "Acme"
    assert client.put(f"/api/placements/{a['id']}", json={"stage": "nope"}).status_code == 400
