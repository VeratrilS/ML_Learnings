import pytest
from api.app import app
from api.core.db import SessionLocal
from api.domain.job_radar import JobOpportunity
from api.domain.job_prep import build_striver_prep_plan


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def sample_job():
    db = SessionLocal()
    job = JobOpportunity(
        external_id="test:google:prep-1",
        company="Google",
        role="Software Engineer - Early Career",
        ctc_lpa=35.0,
        location="Bengaluru, India",
        portal_url="https://careers.google.com/jobs/results/123",
        skills_required='["C++", "Python", "DSA"]',
        match_score=90,
        source="direct",
        status="manual_applied",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id
    db.close()
    yield job_id

    # Cleanup
    db = SessionLocal()
    j = db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
    if j:
        db.delete(j)
        db.commit()
    db.close()


def test_build_striver_prep_plan_structure():
    plan = build_striver_prep_plan("Google")
    assert plan["plan_days"] == 7
    assert plan["problems_per_day"] == 4
    assert plan["total_plan_problems"] == 28
    assert len(plan["days"]) == 7
    assert plan["source"] == "Common patterns for SWE OAs (Striver A2Z)"

    for d in plan["days"]:
        assert len(d["problems"]) == 4
        assert "focus" in d
        assert "day" in d
        for prob in d["problems"]:
            assert prob["url"].startswith("https://leetcode.com/problems/")
            assert prob["difficulty"] in ("Easy", "Medium", "Hard")

    breakdown = plan["difficulty_breakdown"]
    # Verify Medium/Hard weighted
    assert breakdown["medium"] + breakdown["hard"] >= 20
    assert breakdown["medium"] >= 12
    assert breakdown["hard"] >= 4


def test_job_prep_endpoint(client, sample_job):
    res = client.get(f"/api/jobs/{sample_job}/prep")
    assert res.status_code == 200
    data = res.get_json()

    assert data["company"] == "Google"
    assert data["role"] == "Software Engineer - Early Career"
    assert data["plan_days"] == 7
    assert data["problems_per_day"] == 4
    assert data["total_plan_problems"] == 28
    assert len(data["days"]) == 7
    assert "Striver A2Z" in data["source"]


def test_job_prep_not_found(client):
    res = client.get("/api/jobs/999999/prep")
    assert res.status_code == 404
