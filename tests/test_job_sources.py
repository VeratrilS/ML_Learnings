import json

import pytest

from api.domain import job_sources as js
from api.domain.job_sources import Posting, collect, is_candidate_role, is_india, score, years_required


class _Resp:
    def __init__(self, data, ok=True):
        self._data, self.ok = data, ok

    def json(self):
        return self._data

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("HTTP 500")


def _fake_get(url, timeout=None):
    if "missing-x" in url:
        return _Resp({}, ok=False)
    if "greenhouse" in url and url.endswith("/jobs"):
        return _Resp({"jobs": [
            {"id": 1, "title": "Software Engineer, New Grad 2027", "location": {"name": "Bengaluru, India"}, "absolute_url": "https://gh/1"},
            {"id": 2, "title": "Senior Software Engineer", "location": {"name": "Bengaluru, India"}, "absolute_url": "https://gh/2"},
            {"id": 3, "title": "Software Engineer", "location": {"name": "San Francisco"}, "absolute_url": "https://gh/3"},
            {"id": 4, "title": "Account Executive", "location": {"name": "Mumbai, India"}, "absolute_url": "https://gh/4"},
            {"id": 5, "title": "Backend Engineer", "location": {"name": "Pune, India"}, "absolute_url": "https://gh/5"},
        ]})
    if "greenhouse" in url and "/jobs/1" in url:
        return _Resp({"content": "&lt;p&gt;Build distributed systems in C++ and Python with Kafka and Redis.&lt;/p&gt;"})
    if "greenhouse" in url and "/jobs/5" in url:
        return _Resp({"content": "Requires 5+ years of experience with Java."})
    if "lever" in url:
        return _Resp([{"id": "lv1", "text": "SDE 1 - Backend", "hostedUrl": "https://lv/1",
                       "categories": {"location": "Gurugram"}, "descriptionPlain": "Node.js, MongoDB, REST APIs. 0-1 years."}])
    if "ashby" in url:
        return _Resp({"jobs": [{"id": "a1", "title": "Software Engineer Intern", "location": "Hyderabad, India",
                                "jobUrl": "https://ab/1", "descriptionPlain": "React and SQL", "isListed": True}]})
    return _Resp({}, ok=False)


COMPANIES = [("Acme", "greenhouse", "acme"), ("LevCo", "lever", "levco"), ("AshCo", "ashby", "ashco"), ("Broken", "greenhouse", "missing-x")]


def test_filters():
    p = lambda t, loc="Bengaluru, India": Posting("X", "greenhouse", "1", t, loc, "u")
    assert is_india(p("x")) and not is_india(p("x", "New York"))
    assert is_candidate_role(p("Software Engineer, New Grad"))
    assert not is_candidate_role(p("Senior Software Engineer"))
    assert not is_candidate_role(p("Staff Backend Engineer"))
    assert not is_candidate_role(p("UX Engineer"))
    assert not is_candidate_role(p("Account Executive"))
    assert years_required("needs 3+ years") == 3 and years_required("0-1 years") == 0 and years_required("none") is None


def test_score_rewards_skills_and_early_career():
    junior = Posting("X", "lever", "1", "Software Engineer, New Grad", "Bengaluru", "u", "C++ Python Kafka Redis distributed")
    plain = Posting("X", "lever", "2", "Software Engineer", "Bengaluru", "u", "Java")
    senior_req = Posting("X", "lever", "3", "Software Engineer", "Bengaluru", "u", "C++ Python, 4+ years")
    s1, m1, _ = score(junior)
    s2, _, _ = score(plain)
    s3, _, y3 = score(senior_req)
    assert s1 > s2 and {"C++", "Python", "Kafka", "Redis", "Distributed systems"} <= set(m1)
    assert y3 == 4 and s3 < s1
    assert 0 <= s1 <= 100


def test_collect_end_to_end_without_network():
    scored, errors = collect(get=_fake_get, companies=COMPANIES)
    titles = [p.title for p, *_ in scored]
    assert "Software Engineer, New Grad 2027" in titles and "SDE 1 - Backend" in titles and "Software Engineer Intern" in titles
    assert "Senior Software Engineer" not in titles and "Account Executive" not in titles
    assert "Backend Engineer" not in titles  # asks for 5+ years
    assert len(errors) == 1 and errors[0].startswith("Broken")
    assert [s for _, s, *_ in scored] == sorted([s for _, s, *_ in scored], reverse=True)
    gh = next(p for p, *_ in scored if p.job_id == "1")
    assert "distributed systems" in gh.text.lower() and gh.external_id == "greenhouse:acme:1"


def test_upsert_and_live_route(monkeypatch):
    pytest.importorskip("api.domain.job_radar")
    from flask import Flask
    from api.core.db import Base, SessionLocal, engine
    from api.domain.job_radar import JobOpportunity
    Base.metadata.create_all(bind=engine, tables=[JobOpportunity.__table__])
    scored, _ = collect(get=_fake_get, companies=COMPANIES)
    db = SessionLocal()
    db.query(JobOpportunity).filter(JobOpportunity.source.like("%(live)")).delete(synchronize_session=False)
    db.commit()
    new = js.upsert(db, scored)
    assert len(new) == len(scored)
    job = new[0]
    job.status = "manual_applied"  # Sai applied: a re-scan must not reset it
    db.commit()
    assert js.upsert(db, scored) == []
    db.refresh(job)
    assert job.status == "manual_applied" and job.shortlist_prob == 0.0 and json.loads(job.skills_required) is not None
    db.close()

    app = Flask(__name__)
    app.register_blueprint(js.job_sources_bp)
    data = app.test_client().get("/api/jobs/live?min_score=0").get_json()["data"]
    assert data and data[0]["match_score"] >= data[-1]["match_score"] and data[0]["url"].startswith("https://")


def test_scan_route_is_throttled(monkeypatch):
    pytest.importorskip("api.domain.job_radar")
    from flask import Flask
    from api.core.db import Base, engine
    from api.domain.job_radar import JobOpportunity
    Base.metadata.create_all(bind=engine, tables=[JobOpportunity.__table__])
    monkeypatch.setattr(js, "collect", lambda: collect(get=_fake_get, companies=COMPANIES))
    monkeypatch.setattr(js, "send_digest", lambda new: True)
    app = Flask(__name__)
    app.register_blueprint(js.job_sources_bp)
    c = app.test_client()
    first = c.post("/api/jobs/scan").get_json()
    assert first["status"] == "success" and first["data"]["found"] >= 3
    assert c.post("/api/jobs/scan").get_json()["status"] == "skipped"
