import json
from datetime import date, timedelta

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


def _fake_get(url, timeout=None, **kw):
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
    monkeypatch.setattr(js, "send_new_role_alert", lambda jobs: False)
    app = Flask(__name__)
    app.register_blueprint(js.job_sources_bp)
    c = app.test_client()
    first = c.post("/api/jobs/scan").get_json()
    assert first["status"] == "success" and first["data"]["found"] >= 3
    assert c.post("/api/jobs/scan").get_json()["status"] == "skipped"


# ---------------- SmartRecruiters / Workday / freshness / budget ----------------
TODAY = date.today()
RECENT = (TODAY - timedelta(days=3)).isoformat()
OLD = (TODAY - timedelta(days=90)).isoformat()


def _sr_get(url, timeout=None, **kw):
    if "/postings?" in url:
        assert "country=in" in url
        page = [
            {"id": "s1", "name": "Software Engineer I", "releasedDate": RECENT + "T06:00:00Z",
             "location": {"city": "Bengaluru", "region": "KA", "country": "in", "fullLocation": "Bengaluru, KA, India"},
             "experienceLevel": {"id": "entry_level", "label": "Entry Level"}},
            {"id": "s2", "name": "Backend Developer", "releasedDate": OLD + "T06:00:00Z",  # too old
             "location": {"city": "Pune", "country": "in"}},
            {"id": "s3", "name": "Director, Engineering", "releasedDate": RECENT,
             "location": {"city": "Pune", "country": "in"}, "experienceLevel": {"id": "director"}},
        ]
        return _Resp({"offset": 0, "limit": 100, "totalFound": 3, "content": page})
    if url.endswith("/postings/s1"):
        return _Resp({"postingUrl": "https://jobs.smartrecruiters.com/acme/s1-software-engineer", "releasedDate": RECENT,
                      "jobAd": {"sections": {"jobDescription": {"text": "<p>Build microservices in Python and Kafka.</p>"},
                                             "qualifications": {"text": "0-1 years. Data structures"}}}})
    return _Resp({}, ok=False)


WD_HOST = "https://acme.wd5.myworkdayjobs.com"
WD_API = WD_HOST + "/wday/cxs/acme/Careers"
WD_FACETS = [{"facetParameter": "locationMainGroup", "values": [
    {"facetParameter": "locationCountry", "descriptor": "Locations", "values": [
        {"descriptor": "United States of America", "id": "us1", "count": 50},
        {"descriptor": "India", "id": "in1", "count": 4}]}]}]
WD_DETAIL = {"/job/Bengaluru/Software-Engineer_R1": RECENT, "/job/Pune/ASE_R2": RECENT, "/job/Pune/SD_R3": OLD}


def _wd_post(url, json=None, headers=None, timeout=None):
    assert url == WD_API + "/jobs" and json["searchText"] == "software engineer" and json["limit"] <= 20
    if not json["appliedFacets"]:
        return _Resp({"total": 54, "facets": WD_FACETS, "jobPostings": []})
    assert json["appliedFacets"] == {"locationCountry": ["in1"]}
    return _Resp({"total": 4, "jobPostings": [
        {"title": "Software Engineer", "externalPath": "/job/Bengaluru/Software-Engineer_R1", "locationsText": "Bengaluru, India",
         "postedOn": "Posted 2 Days Ago", "bulletFields": ["R1"]},
        {"title": "Associate Software Engineer", "externalPath": "/job/Pune/ASE_R2", "locationsText": "2 Locations",
         "postedOn": "Posted 30+ Days Ago", "bulletFields": ["R2"]},
        {"title": "Software Developer", "externalPath": "/job/Pune/SD_R3", "locationsText": "PUNE 05",
         "postedOn": "Posted 30+ Days Ago", "bulletFields": ["R3"]},
        {"title": "Senior Software Engineer", "externalPath": "/job/Pune/SSE_R4", "locationsText": "Pune",
         "postedOn": "Posted Today", "bulletFields": ["R4"]},
    ]})


def _wd_get(url, timeout=None, headers=None, **kw):
    for path, started in WD_DETAIL.items():
        if url == WD_API + path:
            return _Resp({"jobPostingInfo": {"jobDescription": "<p>C++ and Linux, new grad welcome</p>", "startDate": started}})
    return _Resp({}, ok=False)


def test_smartrecruiters_source_lists_details_and_freshness():
    src = js.SmartRecruitersSource()
    posts = src.list_postings("Acme", "acme", get=_sr_get)
    assert [p.job_id for p in posts] == ["s1", "s2"]  # director-level skipped
    s1 = posts[0]
    assert s1.posted == RECENT and is_india(s1) and s1.url.startswith("https://jobs.smartrecruiters.com/acme/")
    assert is_india(posts[1]) and posts[1].location.endswith("India")  # country=in feed is labelled India
    assert js.is_fresh(s1) and not js.is_fresh(posts[1])
    src.details(s1, get=_sr_get)
    assert "microservices" in s1.text.lower() and "entry level" in s1.text.lower()
    assert s1.url.endswith("s1-software-engineer")


def test_workday_source_applies_india_facet_and_builds_urls():
    posts = js.WorkdaySource().list_postings("Acme", "acme|wd5|Careers", get=_wd_get, post=_wd_post)
    assert [p.job_id for p in posts] == ["R1", "R2", "R3", "R4"]
    r1, r2, r3 = posts[:3]
    assert r1.url == WD_HOST + "/en-US/Careers/job/Bengaluru/Software-Engineer_R1"
    assert r1.posted == (TODAY - timedelta(days=2)).isoformat()
    assert r2.posted == "" and r2.location == "2 Locations, India" and is_india(r3)  # facet => India
    js.WorkdaySource().details(r1, get=_wd_get)
    assert "c++" in r1.text.lower() and r1.posted == RECENT


def test_workday_facet_detection_falls_back_to_cities_and_ignores_indianapolis():
    facets = [{"facetParameter": "locations", "values": [
        {"descriptor": "Bangalore, India", "id": "b"}, {"descriptor": "IN-INDIANAPOLIS, 220 Virginia Ave", "id": "x"},
        {"descriptor": "Hyderabad", "id": "h"}]}]
    assert js.WorkdaySource.india_facet(facets) == {"locations": ["b", "h"]}
    assert js.WorkdaySource.india_facet([]) == {}
    assert not is_india(Posting("X", "workday", "1", "SWE", "Indianapolis, Indiana", "u"))


def test_freshness_helpers():
    assert js._workday_posted_on("Posted Today", TODAY) == TODAY.isoformat()
    assert js._workday_posted_on("Posted Yesterday", TODAY) == (TODAY - timedelta(days=1)).isoformat()
    assert js._workday_posted_on("Posted 30+ Days Ago", TODAY) == ""
    assert js._to_date(1760000000000) == js._to_date(1760000000) and js._to_date("2026-10-01T10:00:00Z") == "2026-10-01"
    p = Posting("X", "lever", "1", "SWE", "Pune", "u", posted=OLD)
    assert not js.is_fresh(p) and js.is_fresh(Posting("X", "lever", "2", "SWE", "Pune", "u"))


def _mixed_get(url, timeout=None, **kw):
    if "smartrecruiters" in url:
        return _sr_get(url, timeout)
    if "myworkdayjobs" in url:
        return _wd_get(url, timeout)
    if "boom" in url:
        raise ConnectionError("network down")
    return _fake_get(url, timeout)


def test_collect_with_new_boards_freshness_and_failing_source():
    companies = [("SRCo", "smartrecruiters", "acme"), ("WDCo", "workday", "acme|wd5|Careers"),
                 ("LevCo", "lever", "levco"), ("Boom", "greenhouse", "boom"), ("Broken", "greenhouse", "missing-x")]
    scored, errors = collect(get=_mixed_get, post=_wd_post, companies=companies)
    ids = {p.job_id for p, *_ in scored}
    assert "s1" in ids and "s2" not in ids            # old SmartRecruiters posting skipped
    assert {"R1", "R2"} <= ids and "R3" not in ids    # R3 revealed as 90 days old by its detail page
    assert "R4" not in ids                            # senior
    assert "lv1" in ids
    assert sorted(e.split(":")[0] for e in errors) == ["Boom", "Broken"]
    assert all(p.posted for p, *_ in scored if p.board in ("smartrecruiters", "workday"))


def test_collect_respects_time_budget():
    import time as _time

    def slow_get(url, timeout=None, **kw):
        if "slow" in url:
            _time.sleep(1.5)
        return _fake_get(url, timeout)
    t0 = _time.monotonic()
    scored, errors = collect(get=slow_get, companies=[("Slow", "greenhouse", "slow"), ("LevCo", "lever", "levco")], budget=1.0)
    assert _time.monotonic() - t0 < 1.4
    assert any(e.startswith("Slow") and "budget" in e for e in errors)
    assert [p.job_id for p, *_ in scored] == ["lv1"]


def test_company_merge_ctc_and_digest_filter():
    keys = [js._key(b, t) for _n, b, t in js.ALL_COMPANIES]
    assert len(keys) == len(set(keys))  # deduped by board:token
    assert js._key("smartrecruiters", "swiggy") in keys and len(js.ALL_COMPANIES) > len(js.COMPANIES)
    assert js.ctc_floor("18-28 LPA") == 18.0 and js.ctc_floor("40+ LPA") == 40.0 and js.ctc_floor(None) == 0.0

    class J:
        def __init__(self, company, ctc, score=80):
            self.company, self.ctc_lpa, self.match_score = company, ctc, score
    assert js.digest_worthy(J("Unknown Startup", 18.0))
    assert not js.digest_worthy(J("Unknown Startup", 0.0)) and not js.digest_worthy(J("Unknown Startup", 12.0))
    assert js.digest_worthy(J("NVIDIA", 0.0)) and not js.digest_worthy(J("NVIDIA", 0.0, score=40))


def test_upsert_sets_ctc_and_live_min_ctc_filter():
    pytest.importorskip("api.domain.job_radar")
    from flask import Flask
    from api.core.db import Base, SessionLocal, engine
    from api.domain.job_radar import JobOpportunity
    Base.metadata.create_all(bind=engine, tables=[JobOpportunity.__table__])
    companies = [("Swiggy", "smartrecruiters", "swiggy"), ("LevCo", "lever", "levco")]
    scored, _ = collect(get=_mixed_get, companies=companies)
    assert {p.company for p, *_ in scored} == {"Swiggy", "LevCo"}
    db = SessionLocal()
    db.query(JobOpportunity).filter(JobOpportunity.source.like("%(live)")).delete(synchronize_session=False)
    db.commit()
    js.upsert(db, scored)
    swiggy = db.query(JobOpportunity).filter(JobOpportunity.company == "Swiggy").one()
    band = js.CTC_BAND[js._key("smartrecruiters", "swiggy")]
    assert swiggy.ctc_lpa == js.ctc_floor(band) >= 15 and f"est. CTC {band}" in swiggy.notes
    assert f"posted {RECENT}" in swiggy.notes and swiggy.board == "smartrecruiters"
    lev = db.query(JobOpportunity).filter(JobOpportunity.company == "LevCo").one()
    assert lev.ctc_lpa == 0.0
    db.close()

    app = Flask(__name__)
    app.register_blueprint(js.job_sources_bp)
    c = app.test_client()
    companies_for = lambda q: {d["company"] for d in c.get("/api/jobs/live?" + q).get_json()["data"]}
    assert companies_for("min_ctc=15") == {"Swiggy", "LevCo"}            # unknown CTC (0) is kept
    assert companies_for("min_ctc=15&strict_ctc=1") == {"Swiggy"}        # ...unless strict
    assert companies_for("min_ctc=99") == {"LevCo"}                      # known but below the bar -> dropped
    row = next(d for d in c.get("/api/jobs/live?min_ctc=15&strict_ctc=1").get_json()["data"])
    assert row["est_ctc"] == band and row["posted"] == RECENT and row["ctc_lpa"] == js.ctc_floor(band)


def test_scan_claims_slot_first_and_digest_at_most_daily(monkeypatch):
    pytest.importorskip("api.domain.job_radar")
    from datetime import datetime, timezone
    from flask import Flask
    from api.core.db import Base, SessionLocal, engine
    from api.domain.job_radar import JobOpportunity
    from api.domain.repositories import NotificationRepository
    Base.metadata.create_all(bind=engine, tables=[JobOpportunity.__table__])
    db = SessionLocal()
    repo = NotificationRepository(db)
    for key in (js.LAST_SCAN_KEY, js.LAST_DIGEST_KEY):
        repo.set_setting(key, "")
    db.query(JobOpportunity).filter(JobOpportunity.source.like("%(live)")).delete(synchronize_session=False)
    db.commit()
    db.close()

    claimed, digests = [], []

    def fake_collect():
        s = SessionLocal()
        claimed.append(NotificationRepository(s).get_setting(js.LAST_SCAN_KEY))  # throttle written before scanning
        s.close()
        return collect(get=_fake_get, companies=COMPANIES)
    monkeypatch.setattr(js, "collect", fake_collect)
    monkeypatch.setattr(js, "send_digest", lambda jobs: digests.append(len(jobs)) or True)
    monkeypatch.setattr(js, "send_new_role_alert", lambda jobs: False)
    app = Flask(__name__)
    app.register_blueprint(js.job_sources_bp)
    c = app.test_client()

    first = c.post("/api/jobs/scan").get_json()
    assert first["status"] == "success" and first["data"]["emailed"] is True and claimed[0]
    assert c.post("/api/jobs/scan").get_json()["status"] == "skipped"          # within SCAN_GAP (5 h)

    db = SessionLocal()
    six_h_ago = (datetime.now(timezone.utc) - js.SCAN_GAP - timedelta(hours=1)).isoformat()
    NotificationRepository(db).set_setting(js.LAST_SCAN_KEY, six_h_ago)
    db.close()
    second = c.post("/api/jobs/scan").get_json()
    assert second["status"] == "success" and second["data"]["emailed"] is False  # scanned, but no 2nd email in 20 h
    assert len(digests) == 1 and len(claimed) == 2
    assert js.SCAN_GAP == timedelta(hours=5) and js.DIGEST_GAP == timedelta(hours=20)


def test_years_in_title_disqualify_and_digest_link():
    p = Posting("X", "workday", "9", "Software Engineer | Go | 8-14 Years", "Bangalore, India", "u", "Go and microservices")
    assert score(p)[2] == 8
    assert "#/job-radar" in js.digest_html([]) and "#/jobradar" not in js.digest_html([])


# ---------------- role type classification + instant new-role alert ----------------
@pytest.mark.parametrize("title,text,expected", [
    ("Software Engineer, New Grad 2027", "", "fte"),
    ("SDE 1 - Backend", "Full-time role", "fte"),
    ("Associate Software Engineer", "", "fte"),
    ("International Payments Engineer", "", "fte"),                  # 'intern' only as a whole word
    ("Software Engineer Intern", "This is a 6 month internship.", "intern_6m"),
    ("SWE Intern", "Six-month internship in Bengaluru", "intern_6m"),
    ("SWE Intern", "Duration: 24 weeks", "intern_6m"),
    ("SWE Intern (Jan - Jun 2027)", "", "intern_6m"),
    ("Engineering Intern", "January 2027 to June 2027", "intern_6m"),
    ("Engineering Intern", "Jul–Dec 2027", "intern_6m"),
    ("Software Engineering Internship", "Great team, React and SQL", "intern"),  # duration not stated
    ("Software Engineer Intern", "", "intern"),
    ("Summer Intern - Software", "", None),
    ("Software Engineer Intern", "A 10-12 weeks summer program", None),
    ("Software Engineer Intern", "8 weeks paid internship", None),
    ("Software Engineer Intern", "Internship duration: 2-3 months", None),
    ("Software Engineer Intern", "three months", None),
])
def test_classify_role(title, text, expected):
    assert js.classify_role(Posting("X", "lever", "1", title, "Pune", "u", text)) == expected


def test_collect_drops_short_internships_and_labels_notes():
    def get(url, timeout=None, **kw):
        if "lever" in url:
            return _Resp([
                {"id": "f1", "text": "SDE 1", "hostedUrl": "https://lv/f1", "categories": {"location": "Pune"},
                 "descriptionPlain": "Python, SQL. 0-1 years."},
                {"id": "i6", "text": "Software Engineer Intern", "hostedUrl": "https://lv/i6",
                 "categories": {"location": "Pune"}, "descriptionPlain": "6-month internship, Jan-Jun 2027. Python."},
                {"id": "iu", "text": "Software Engineer Intern", "hostedUrl": "https://lv/iu",
                 "categories": {"location": "Pune"}, "descriptionPlain": "React and SQL."},
                {"id": "is", "text": "Software Engineer Intern", "hostedUrl": "https://lv/is",
                 "categories": {"location": "Pune"}, "descriptionPlain": "12 weeks summer internship."},
            ])
        return _Resp({}, ok=False)
    scored, _ = collect(get=get, companies=[("LevCo", "lever", "levco")])
    kinds = {p.job_id: p.role_type for p, *_ in scored}
    assert kinds == {"f1": "fte", "i6": "intern_6m", "iu": "intern"}


class _Job:
    def __init__(self, id, notes, score=80, ctc=0.0, company="Acme", role="SDE 1"):
        self.id, self.notes, self.match_score, self.ctc_lpa = id, notes, score, ctc
        self.company, self.role, self.location, self.portal_url = company, role, "Pune, India", f"https://x/{id}"


def test_select_alerts_and_alert_email():
    jobs = [
        _Job(1, "[FTE] Live from Lever", score=90),
        _Job(2, "[6-month intern] Live from Lever", score=70, ctc=18.0),
        _Job(3, "[Intern, duration not stated] Live from Lever", score=95),   # unstated intern: no instant alert
        _Job(4, "[FTE] Live from Lever", score=55),                           # weak match
        _Job(5, "[FTE] Live from Lever", score=90, ctc=8.0),                  # known CTC below 15 LPA
        _Job(6, "Live from Lever", score=99),                                 # legacy row, no role type
    ]
    picked = js.select_alerts(jobs)
    assert [j.id for j in picked] == [1, 2]
    assert js.alert_subject(picked) == "New role released: Acme — SDE 1 (+1 more)"
    assert js.alert_subject(picked[:1]) == "New role released: Acme — SDE 1"
    body = js.alert_html(picked)
    assert body.count("/api/jobs/decide?t=") == 4 and "#/job-radar" in body and "[6-month intern]" in body
    from api.domain.job_approvals import verify_token
    token = js.alert_text(picked).split("Approve: ")[1].split("?t=")[1].split()[0]
    assert verify_token(token) == (1, "approve")
    assert js.select_alerts([]) == [] and js.send_new_role_alert([]) is False


def test_scan_sends_one_alert_and_live_role_type_filter(monkeypatch):
    pytest.importorskip("api.domain.job_radar")
    from flask import Flask
    from api.core.db import Base, SessionLocal, engine
    from api.domain.job_radar import JobOpportunity
    from api.domain.repositories import NotificationRepository
    Base.metadata.create_all(bind=engine, tables=[JobOpportunity.__table__])
    db = SessionLocal()
    NotificationRepository(db).set_setting(js.LAST_SCAN_KEY, "")
    db.query(JobOpportunity).filter(JobOpportunity.source.like("%(live)")).delete(synchronize_session=False)
    db.commit()
    db.close()
    sent = []
    monkeypatch.setattr(js, "collect", lambda: collect(get=_fake_get, companies=COMPANIES))
    monkeypatch.setattr(js, "send_digest", lambda jobs: False)
    monkeypatch.setattr(js, "send_new_role_alert", lambda jobs: sent.append([j.role for j in jobs]) or True)
    app = Flask(__name__)
    app.register_blueprint(js.job_sources_bp)
    c = app.test_client()
    res = c.post("/api/jobs/scan").get_json()
    assert res["status"] == "success" and len(sent) == 1                  # one alert email per scan
    assert "Software Engineer, New Grad 2027" in sent[0] and "Software Engineer Intern" not in sent[0]
    assert res["data"]["alerted"] == len(sent[0])

    rows = c.get("/api/jobs/live").get_json()["data"]
    assert {r["role_type"] for r in rows} == {"fte", "intern"}
    fte = c.get("/api/jobs/live?role_type=fte,intern_6m").get_json()["data"]
    assert fte and all(r["role_type"] == "fte" for r in fte) and len(fte) < len(rows)
    assert all(r["notes"].startswith("[") and r["board"] for r in rows)
