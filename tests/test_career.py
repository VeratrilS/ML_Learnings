from datetime import timedelta

import pytest
from flask import Flask

from api.core.db import Base, SessionLocal, engine
from api.domain import career as cr
from api.domain.career import CareerMeta, Contact, ResumeVersion, Story, career_bp, keyword_overlap


class FakeLLM:
    calls = []
    result = None
    error = None

    def __init__(self, budget=240, **_kw):
        self.budget = budget

    def generate_json(self, contents, temperature=0.7, system=None, thinking=None):
        FakeLLM.calls.append((contents, system))
        if FakeLLM.error:
            raise FakeLLM.error
        return FakeLLM.result


RESUME = """Sai Raghava - B.Tech CSE
Skills: Python, React, Flask, PostgreSQL, Docker, Git
- Built a placement dashboard with Flask and React deployed on Vercel
- Worked on a team project for college fest website
"""
JD = """We are hiring an SDE intern. Required: Python, Java, React, Kubernetes, AWS and strong data structures.
You will build REST APIs, write unit tests and work with PostgreSQL. Kubernetes experience is a plus."""


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(career_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def client(app, monkeypatch):
    FakeLLM.calls = []
    FakeLLM.result = None
    FakeLLM.error = None
    monkeypatch.setattr(cr, "LLMClient", FakeLLM)
    yield app.test_client()
    db = SessionLocal()
    for m in (ResumeVersion, Story, Contact, CareerMeta):
        db.query(m).delete()
    db.commit()
    db.close()


# ---------------- keyword overlap ----------------
def test_keyword_overlap_is_deterministic():
    k = keyword_overlap(RESUME, JD)
    assert {"python", "react", "postgresql"} <= set(k["tech_matched"])
    assert {"java", "kubernetes", "aws"} <= set(k["tech_missing"])
    assert "flask" not in k["tech_missing"]  # only JD terms count
    assert 0 < k["score"] < 100
    assert keyword_overlap(RESUME, JD) == k
    assert keyword_overlap("", "")["score"] == 0


def test_react_native_does_not_count_as_react():
    k = keyword_overlap("I know React Native", "Need React and React Native")
    assert "react native" in k["tech_matched"]
    assert "react" in k["tech_missing"]


# ---------------- resumes + match ----------------
def test_resume_crud(client):
    assert client.post("/api/career/resume", json={"label": "x"}).status_code == 400
    r = client.post("/api/career/resume", json={"label": "SDE v1", "text": RESUME}).get_json()["data"]
    assert r["label"] == "SDE v1" and r["text"] == RESUME.strip()
    auto = client.post("/api/career/resume", json={"text": "hello"}).get_json()["data"]
    assert auto["label"].startswith("Resume")
    rows = client.get("/api/career/resume").get_json()["data"]
    assert len(rows) == 2
    assert client.get(f"/api/career/resume/{r['id']}").get_json()["data"]["label"] == "SDE v1"
    assert client.delete(f"/api/career/resume/{r['id']}").status_code == 200
    assert client.get(f"/api/career/resume/{r['id']}").status_code == 404


def test_match_with_saved_resume_and_ai(client):
    rid = client.post("/api/career/resume", json={"text": RESUME}).get_json()["data"]["id"]
    FakeLLM.result = {
        "score": "72.4", "missing_keywords": ["Java", "AWS", "java"], "matched_keywords": "Python, React",
        "weak_bullets": [{"original": "Worked on a team project", "rewrite": "Led [N]-person team", "why": "verb"},
                         {"original": "", "rewrite": "dropped"}, "junk"],
        "summary": "Decent fit.",
    }
    res = client.post("/api/career/match", json={"resume_id": rid, "jd_text": JD})
    assert res.status_code == 200
    d = res.get_json()["data"]
    assert d["ai_error"] is None
    assert d["ai"]["score"] == 72
    assert d["ai"]["missing_keywords"] == ["Java", "AWS"]
    assert d["ai"]["matched_keywords"] == ["Python", "React"]
    assert len(d["ai"]["weak_bullets"]) == 1
    assert "kubernetes" in d["keywords"]["missing"]
    prompt, system = FakeLLM.calls[0]
    assert "NEVER invent metrics" in system and "[X%]" in system
    assert RESUME.strip() in prompt


def test_match_falls_back_when_ai_fails(client):
    FakeLLM.error = RuntimeError("429 RESOURCE_EXHAUSTED")
    d = client.post("/api/career/match", json={"resume_text": RESUME, "jd_text": JD}).get_json()["data"]
    assert d["ai"] is None
    assert "busy" in d["ai_error"]
    assert d["keywords"]["score"] > 0


def test_match_validation(client):
    assert client.post("/api/career/match", json={"resume_text": RESUME}).status_code == 400
    assert client.post("/api/career/match", json={"jd_text": JD}).status_code == 400
    assert client.post("/api/career/match", json={"resume_id": "abc", "jd_text": JD}).status_code == 400
    assert client.post("/api/career/match", json={"resume_id": 999, "jd_text": JD}).status_code == 404
    assert client.post("/api/career/match", json={"resume_text": RESUME, "jd_text": "too short"}).status_code == 400
    assert not FakeLLM.calls


# ---------------- stories ----------------
def test_example_story_seeded_once(client):
    data = client.get("/api/career/stories").get_json()
    assert len(data["data"]) == 1
    s = data["data"][0]
    assert s["draft"] is True and "Daily" in s["title"]
    assert set(s["tags"]) == {"ownership", "tech-depth"}
    assert "leadership" in data["tags"]
    client.delete(f"/api/career/stories/{s['id']}")
    assert client.get("/api/career/stories").get_json()["data"] == []


def test_story_crud_and_polish(client):
    client.get("/api/career/stories")  # seed
    assert client.post("/api/career/stories", json={"situation": "x"}).status_code == 400
    assert client.post("/api/career/stories", json={"title": "T", "tags": ["nope"]}).status_code == 400
    s = client.post("/api/career/stories", json={"title": "Fixed prod outage", "situation": "Site down",
                                                 "action": "Rolled back", "tags": "failure, ownership"}).get_json()["data"]
    assert s["tags"] == ["failure", "ownership"] and s["draft"] is False
    upd = client.put(f"/api/career/stories/{s['id']}", json={"result": "Back in [N] minutes", "draft": True}).get_json()["data"]
    assert upd["result"] == "Back in [N] minutes" and upd["draft"] and upd["situation"] == "Site down"

    FakeLLM.result = {"answer": "word " * 200, "follow_ups": ["a?", "b?", "c?", "d?"], "tip": "Slow down."}
    p = client.post(f"/api/career/stories/{s['id']}/polish").get_json()["data"]["polished"]
    assert p["words"] == 200 and len(p["follow_ups"]) == 3 and 60 <= p["seconds"] <= 120
    assert "NEVER invent" in FakeLLM.calls[0][1]
    assert client.get(f"/api/career/stories/{s['id']}").get_json()["data"]["polished"]["tip"] == "Slow down."

    FakeLLM.error = RuntimeError("503 UNAVAILABLE")
    assert client.post(f"/api/career/stories/{s['id']}/polish").status_code == 502

    empty = client.post("/api/career/stories", json={"title": "Empty"}).get_json()["data"]
    assert client.post(f"/api/career/stories/{empty['id']}/polish").status_code == 400
    assert client.post("/api/career/stories/9999/polish").status_code == 404
    assert client.delete(f"/api/career/stories/{s['id']}").status_code == 200


# ---------------- contacts ----------------
def test_contacts_crud_and_due(client):
    today = cr._today()
    assert client.post("/api/career/contacts", json={"company": "X"}).status_code == 400
    assert client.post("/api/career/contacts", json={"name": "A", "status": "maybe"}).status_code == 400
    assert client.post("/api/career/contacts", json={"name": "A", "follow_up": "soon"}).status_code == 400
    a = client.post("/api/career/contacts", json={"name": "Asha", "company": "Google", "link": "linkedin.com/in/asha",
                                                  "follow_up": (today - timedelta(days=1)).isoformat()}).get_json()["data"]
    assert a["status"] == "to-ask" and a["due"] and a["link"].startswith("https://")
    b = client.post("/api/career/contacts", json={"name": "Bala", "status": "referred",
                                                  "follow_up": today.isoformat()}).get_json()["data"]
    assert not b["due"]
    client.post("/api/career/contacts", json={"name": "Chitra", "follow_up": (today + timedelta(days=3)).isoformat()})

    lst = client.get("/api/career/contacts").get_json()
    assert [c["name"] for c in lst["data"]] == ["Asha", "Chitra", "Bala"]
    assert lst["due_count"] == 1 and lst["counts"]["referred"] == 1

    due = client.get("/api/career/contacts/due").get_json()
    assert due["total"] == 1 and due["data"][0]["name"] == "Asha"

    upd = client.put(f"/api/career/contacts/{a['id']}", json={"status": "asked", "follow_up": None}).get_json()["data"]
    assert upd["status"] == "asked" and upd["follow_up"] is None and not upd["due"] and upd["company"] == "Google"
    assert client.get("/api/career/contacts/due").get_json()["total"] == 0
    assert client.delete(f"/api/career/contacts/{a['id']}").status_code == 200
    assert client.get(f"/api/career/contacts/{a['id']}").status_code == 404


def test_contact_draft(client):
    c = client.post("/api/career/contacts", json={"name": "Asha", "company": "Google", "how_known": "college senior",
                                                  "status": "asked"}).get_json()["data"]
    FakeLLM.result = {"subject": "Referral for SDE", "message": "Hi Asha, hope work is going well at Google."}
    d = client.post(f"/api/career/contacts/{c['id']}/draft", json={"jd_text": "SDE role"}).get_json()["data"]
    assert d["message"].startswith("Hi Asha") and d["subject"] == "Referral for SDE"
    prompt, system = FakeLLM.calls[0]
    assert "college senior" in prompt and "SDE role" in prompt and "Status: asked" in prompt
    assert "NEVER invent" in system

    FakeLLM.result = {"message": ""}
    assert client.post(f"/api/career/contacts/{c['id']}/draft").status_code == 502
    assert client.post("/api/career/contacts/999/draft").status_code == 404
