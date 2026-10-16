import json
import re
from types import SimpleNamespace

import pytest
from flask import Flask

from api.core.db import Base, SessionLocal, engine
from api.domain import job_resume as jr
from api.domain.job_pack import RESUME_FACTS
from api.domain.job_radar import JobOpportunity, JobRadarProfile

FACT_BULLETS = {h["bullet"] for h in RESUME_FACTS["highlights"]}
ALL_IDS = {h["id"] for h in RESUME_FACTS["highlights"]}
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
FACT_NUMBERS = set(_NUMBER.findall(" ".join([RESUME_FACTS["education"], *FACT_BULLETS])))


def job(role="Software Engineer", skills=(), company="Acme"):
    return SimpleNamespace(id=1, company=company, role=role, skills_required=json.dumps(list(skills)), location="")


def section(content, heading):
    return next(s for s in content["sections"] if s["heading"] == heading)


def ids(content, heading):
    return [e["id"] for e in section(content, heading)["entries"]]


# ---------------- pure content ----------------
def test_section_headings_and_order():
    content = jr.resume_content(job())
    assert [s["heading"] for s in content["sections"]] == ["Education", "Experience", "Projects", "Achievements",
                                                           "Skills"]
    assert content["name"] == RESUME_FACTS["name"]


def test_backend_kafka_redis_job_puts_distributed_work_first():
    c = jr.resume_content(job("Backend Engineer", ["Kafka", "Redis", "Java"]))
    assert ids(c, "Projects")[:2] == ["railway", "cache"]
    assert c["skills"][:2] == ["Kafka", "Redis"]


def test_frontend_job_puts_react_work_first():
    c = jr.resume_content(job("Frontend Engineer", ["React", "JavaScript", "Node.js"]))
    assert ids(c, "Experience")[0] == "maruti"
    assert ids(c, "Projects")[0] == "react_comps"
    assert c["skills"][:3] == ["React", "JavaScript", "Node.js"]


def test_cpp_job_puts_cpp_work_first():
    c = jr.resume_content(job("Software Engineer", ["C++", "Multithreading"]))
    assert ids(c, "Experience")[0] == "dataannotation"
    assert ids(c, "Projects")[0] == "cache"
    assert c["skills"][0] == "C++"


def test_no_job_skills_keeps_fact_order():
    c = jr.resume_content(job("Software Engineer", []))
    assert ids(c, "Experience") == ["maruti", "dataannotation"]
    assert ids(c, "Projects") == ["railway", "cache", "react_comps"]
    assert c["skills"] == RESUME_FACTS["skills"]


@pytest.mark.parametrize("role,skills", [
    ("Backend Engineer", ["Kafka", "Redis", "Go", "Kubernetes", "AWS"]),
    ("Frontend Engineer", ["React", "TypeScript", "GraphQL"]),
    ("ML Engineer", ["Python", "PyTorch", "LLMs"]),
    ("SDE", []),
])
def test_every_line_comes_from_resume_facts(role, skills):
    c = jr.resume_content(job(role, skills))
    seen = []
    for s in c["sections"]:
        for e in s["entries"]:
            if s["heading"] == "Skills":
                continue
            if s["heading"] == "Education":
                assert e["bullets"] == [RESUME_FACTS["education"]]
                continue
            assert e["fact"] in FACT_BULLETS
            seen.append(e["id"])
            detail = e["bullets"][0]
            fact_title, _, fact_detail = e["fact"].partition(": ")
            assert e["title"] == fact_title and detail == fact_detail[:1].upper() + fact_detail[1:]
            assert set(_NUMBER.findall(e["title"] + " " + detail)) <= FACT_NUMBERS
    assert sorted(seen) == sorted(ALL_IDS)  # every highlight exactly once, nothing extra
    # Skills: exactly the listed RESUME_FACTS skills, nothing the job asks for that isn't listed.
    assert sorted(c["skills"]) == sorted(RESUME_FACTS["skills"])
    assert section(c, "Skills")["entries"][0]["bullets"] == [", ".join(c["skills"])]


def test_no_phone_when_absent():
    profile = jr.default_profile()
    assert profile.phone is None
    texts = [t for t, _ in jr.resume_content(job(), profile)["contact"]]
    assert texts[0] == "sairaghava1318@gmail.com"
    assert not any(re.fullmatch(r"[+\d][\d\s-]{6,}", t) for t in texts)
    assert "github.com/VeratrilS" in texts and "leetcode.com/u/Sairaghava1318" in texts


def test_phone_shown_only_when_set():
    profile = jr.default_profile()
    profile.phone = "+91 90000 00000"
    assert "+91 90000 00000" in [t for t, _ in jr.contact_items(profile)]
    profile.phone = "   "
    assert len(jr.contact_items(profile)) == 5  # email + 4 links


@pytest.mark.parametrize("company,expected", [
    ("Acme", "NandamVenkataSaiRaghava_Acme.pdf"),
    ("D. E. Shaw", "NandamVenkataSaiRaghava_DEShaw.pdf"),
    ("JP Morgan & Chase", "NandamVenkataSaiRaghava_JPMorganChase.pdf"),
    ('Evil"; rm -rf /\r\nX-Header: 1', "NandamVenkataSaiRaghava_EvilRmRfXHeader1.pdf"),
    ("Zoë Café", "NandamVenkataSaiRaghava_ZoeCafe.pdf"),
    ("", "NandamVenkataSaiRaghava_Company.pdf"),
    (None, "NandamVenkataSaiRaghava_Company.pdf"),
    ("你好", "NandamVenkataSaiRaghava_Company.pdf"),
])
def test_filename_sanitising(company, expected):
    assert jr.resume_filename(company) == expected


def test_filename_length_capped():
    name = jr.resume_filename("A" * 500)
    assert re.fullmatch(r"NandamVenkataSaiRaghava_A{60}\.pdf", name)


def test_render_pdf_one_page():
    pdf = jr.render_pdf(jr.resume_content(job("Backend Engineer", ["Kafka", "Redis"])))
    assert pdf.startswith(b"%PDF")
    assert b"/Count 1" in pdf


# ---------------- endpoint ----------------
@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(jr.job_resume_bp)
    Base.metadata.create_all(bind=engine, tables=[JobOpportunity.__table__, JobRadarProfile.__table__])
    yield app


@pytest.fixture
def client(app):
    yield app.test_client()
    db = SessionLocal()
    db.query(JobOpportunity).delete()
    db.query(JobRadarProfile).delete()
    db.commit()
    db.close()


def _make_job(company="Acme Corp", role="Backend Engineer", skills=("Kafka", "Redis")):
    db = SessionLocal()
    row = JobOpportunity(external_id=f"t-{company}-{role}", company=company, role=role, ctc_lpa=0.0,
                         location="Bengaluru", source="Greenhouse (live)", portal_url="https://example.com/apply/1",
                         skills_required=json.dumps(list(skills)))
    db.add(row)
    db.commit()
    job_id = row.id
    db.close()
    return job_id


def test_endpoint_returns_pdf_attachment(client):
    res = client.get(f"/api/jobs/{_make_job()}/resume.pdf")
    assert res.status_code == 200
    assert res.mimetype == "application/pdf"
    assert res.data.startswith(b"%PDF")
    assert res.headers["Content-Disposition"] == 'attachment; filename="NandamVenkataSaiRaghava_AcmeCorp.pdf"'


def test_endpoint_uses_profile_when_present(client, monkeypatch):
    db = SessionLocal()
    db.add(JobRadarProfile(id=1, phone="+91 98765 43210", skills="[]", achievements="[]", resume_summary=""))
    db.commit()
    db.close()
    captured = {}
    real = jr.resume_content
    monkeypatch.setattr(jr, "resume_content", lambda j, p: captured.setdefault("c", real(j, p)))
    res = client.get(f"/api/jobs/{_make_job()}/resume.pdf")
    assert res.status_code == 200
    assert "+91 98765 43210" in [t for t, _ in captured["c"]["contact"]]


def test_endpoint_without_profile_has_no_phone(client, monkeypatch):
    captured = {}
    real = jr.resume_content
    monkeypatch.setattr(jr, "resume_content", lambda j, p: captured.setdefault("c", real(j, p)))
    assert client.get(f"/api/jobs/{_make_job()}/resume.pdf").status_code == 200
    assert len(captured["c"]["contact"]) == 5


def test_unknown_job_404(client):
    res = client.get("/api/jobs/999999/resume.pdf")
    assert res.status_code == 404
    assert res.get_json()["status"] == "error"


def test_passcode_required_once_registered(monkeypatch):
    """The endpoint is not in _OPEN_ENDPOINTS, so the app-level passcode check applies."""
    from api.app import _OPEN_ENDPOINTS, app as real_app
    if "job_resume" not in real_app.blueprints:
        pytest.skip("job_resume_bp not registered in api/app.py yet")
    assert not any(p.endswith("resume.pdf") for p in _OPEN_ENDPOINTS)
    monkeypatch.setenv("APP_PASSCODE", "1234")
    res = real_app.test_client().get("/api/jobs/1/resume.pdf")
    assert res.status_code == 401
