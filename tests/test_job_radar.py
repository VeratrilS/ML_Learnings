import json
import pytest
from flask import Flask

from api.core.db import Base, SessionLocal, engine
from api.domain.job_radar import (
    JobApplicationReceipt,
    JobOpportunity,
    JobRadarProfile,
    JobRadarScanLog,
    SkillMatcher,
    job_radar_bp,
)
from api.domain.placements import Application, ApplicationEvent


@pytest.fixture(scope="module")
def app():
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.register_blueprint(job_radar_bp)
    Base.metadata.create_all(bind=engine)
    yield flask_app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c
    db = SessionLocal()
    try:
        db.query(JobOpportunity).delete()
        db.query(JobRadarScanLog).delete()
        db.query(JobRadarProfile).delete()
        db.query(JobApplicationReceipt).delete()
        db.query(Application).delete()
        db.query(ApplicationEvent).delete()
        db.commit()
    finally:
        db.close()


def _make_fixture_job(company="Google", role="Software Engineer Intern", ctc=45.0, batch="2027", external_id="google-swe-1"):
    db = SessionLocal()
    try:
        job = JobOpportunity(
            external_id=external_id,
            company=company,
            role=role,
            eligible_batches=batch,
            eligible_branches="CSE, IT",
            min_cgpa=7.5,
            ctc_lpa=ctc,
            location="Bengaluru",
            source="Direct Careers Portal",
            portal_url=f"https://careers.{company.lower().replace(' ', '')}.com/jobs/1",
            skills_required=json.dumps(["C++", "Algorithms", "Kafka"]),
            match_score=92,
            status="discovered",
        )
        db.add(job)
        db.commit()
        return job.id
    finally:
        db.close()


def test_job_radar_discovery_and_profile(client):
    """Verifies radar profile, candidate vectors, and live/fixture openings."""
    _make_fixture_job("Google", "Software Engineer Intern", 45.0, "2027", "ext-g-1")
    _make_fixture_job("Uber", "Backend Engineer", 38.0, "2027", "ext-u-1")

    res = client.get("/api/jobs/radar")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"

    profile = data["profile"]
    assert profile["full_name"] == "Nandam Venkata Sai Raghava"
    assert profile["grad_year"] == 2027
    assert profile["cgpa"] == 8.99
    assert profile["email"] == "sairaghava1318@gmail.com"
    assert profile["min_ctc_lpa"] >= 15.0

    summary = data["summary"]
    assert summary["total_openings"] == 2
    assert summary["eligible_2027_count"] == 2
    assert summary["highest_ctc"] >= 40.0
    # Strict integrity: zero fake applied jobs
    assert summary["confirmed_applied_count"] == 0

    jobs = data["jobs"]
    assert len(jobs) == 2
    for j in jobs:
        assert "2027" in j["eligible_batches"]
        assert j["ctc_lpa"] >= 15.0
        assert j["portal_url"].startswith("http")


def test_confirm_applied_and_unmark(client):
    """Verifies honest confirm-applied flow syncing to placements board, 409 conflict, and safe undo."""
    job_id = _make_fixture_job("Google", "SWE", 45.0, "2027", "ext-conf-1")

    # Also add an existing manual Application for another company to ensure unmark does not delete it
    db = SessionLocal()
    existing_manual_app = Application(
        company="Microsoft",
        role="Prior Manual Application",
        stage="wishlist",
        source="manual",
    )
    db.add(existing_manual_app)
    db.commit()
    manual_app_id = existing_manual_app.id
    db.close()

    res = client.get("/api/jobs/radar")
    assert res.status_code == 200
    data = res.get_json()
    first_job = data["jobs"][0]

    # Confirm genuine application submission
    ref_code = "USER-REF-9988"
    conf_res = client.post("/api/jobs/confirm-applied", json={
        "job_id": job_id,
        "confirmation_ref": ref_code,
        "notes": "Verified portal submission test",
    })
    assert conf_res.status_code == 200
    conf_data = conf_res.get_json()
    assert conf_data["status"] == "success"
    assert conf_data["application_ref"] == ref_code

    # Attempt duplicate confirm -> must return 409 Conflict
    dup_res = client.post("/api/jobs/confirm-applied", json={
        "job_id": job_id,
        "confirmation_ref": "ANOTHER-REF",
    })
    assert dup_res.status_code == 409
    assert dup_res.get_json()["status"] == "conflict"

    # Check verified receipts
    rec_res = client.get("/api/jobs/receipts")
    assert rec_res.status_code == 200
    rec_data = rec_res.get_json()
    assert rec_data["status"] == "success"
    assert len(rec_data["receipts"]) == 1
    assert rec_data["receipts"][0]["application_ref"] == ref_code

    # Check database sync into Application
    db = SessionLocal()
    try:
        app_entry = db.query(Application).filter(Application.role == "SWE").first()
        assert app_entry is not None
        assert app_entry.stage == "applied"
        assert ref_code in app_entry.notes
        # Ensure the prior manual application still exists
        assert db.query(Application).filter(Application.id == manual_app_id).first() is not None
    finally:
        db.close()

    # Unmark / undo
    unmark_res = client.post("/api/jobs/unmark-applied", json={"job_id": job_id})
    assert unmark_res.status_code == 200
    assert unmark_res.get_json()["status"] == "success"

    # Receipts should be 0 again
    rec_res2 = client.get("/api/jobs/receipts")
    assert len(rec_res2.get_json()["receipts"]) == 0

    # Ensure the prior manual application was NOT deleted by safe unmark
    db = SessionLocal()
    try:
        assert db.query(Application).filter(Application.id == manual_app_id).first() is not None
    finally:
        db.close()


def test_blueprints_endpoint(client):
    """Verifies authentic technical blueprints for live/fixture companies."""
    _make_fixture_job("Google", "Software Engineer", 45.0, "2027", "ext-bp-1")
    _make_fixture_job("Uber", "Backend Engineer", 38.0, "2027", "ext-bp-2")

    res = client.get("/api/jobs/blueprints")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    blueprints = data["blueprints"]
    assert len(blueprints) == 2

    companies = {b["company"] for b in blueprints}
    assert "Google" in companies
    assert "Uber" in companies
    for b in blueprints:
        assert "oa_platform" in b
        assert "core_topics" in b



def test_toggle_auto_apply_and_settings(client):
    """Verifies toggling hourly scanner and updating preferences."""
    client.get("/api/jobs/radar")

    t_res = client.post("/api/jobs/toggle-auto-apply", json={"enabled": False})
    assert t_res.status_code == 200
    assert t_res.get_json()["auto_apply_enabled"] is False

    s_res = client.post("/api/jobs/settings", json={"min_ctc_lpa": 18.0, "location_pref": "Bengaluru"})
    assert s_res.status_code == 200
    assert s_res.get_json()["status"] == "success"

    db = SessionLocal()
    try:
        prof = db.query(JobRadarProfile).filter(JobRadarProfile.id == 1).first()
        assert prof.min_ctc_lpa == 18.0
        assert prof.location_pref == "Bengaluru"
    finally:
        db.close()


def test_followups_endpoint(client):
    """Verifies followups scheduler endpoint."""
    res = client.post("/api/jobs/followups")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] in ("success", "skipped")


def test_skill_matcher():
    """Verifies deterministic skill overlap matching and zero fake shortlist probability."""
    score, prob = SkillMatcher.compute_match(["C++", "Kafka", "Redis"], ctc_lpa=25.0, min_cgpa=8.0)
    assert score >= 50
    assert prob == 0.0  # strictly zero fake probability


def test_job_outcome_endpoint(client):
    """Verifies recording outcome (oa, interview, offer, rejected) and funnel stats."""
    job_id = _make_fixture_job("Palantir", "Forward Deployed SWE", 50.0, "2027", "ext-pal-1")

    # Record outcome without prior application -> still saves
    out_res = client.post(f"/api/jobs/{job_id}/outcome", json={"outcome": "oa", "notes": "HackerRank link received"})
    assert out_res.status_code == 200
    out_data = out_res.get_json()
    assert out_data["status"] == "success"
    assert out_data["data"]["outcome"] == "oa"

    # Invalid outcome returns 400
    bad_res = client.post(f"/api/jobs/{job_id}/outcome", json={"outcome": "invalid_val"})
    assert bad_res.status_code == 400

    # Verify summary funnel
    radar_res = client.get("/api/jobs/radar")
    summary = radar_res.get_json()["summary"]
    assert summary["oa_total"] >= 1
    assert summary["days_since_last_callback"] is not None


def test_job_referral_endpoint(client):
    """Verifies referral search URLs and template generation."""
    job_id = _make_fixture_job("Stripe", "Software Engineer", 45.0, "2027", "ext-stripe-ref-1")

    res = client.get(f"/api/jobs/{job_id}/referral")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    ref = data["data"]
    assert ref["company"] == "Stripe"
    assert "NIT%20Rourkela" in ref["alumni_url"]
    assert "software%20engineer" in ref["engineers_url"]
    assert "NIT Rourkela" in ref["template"]
    assert "8.99 CGPA" in ref["template"]
    assert "Kafka" in ref["template"]


def test_job_followup_draft_endpoint(client):
    """Verifies 7-day and 14-day polite recruiter follow-up note generation."""
    job_id = _make_fixture_job("Databricks", "Distributed Systems Engineer", 48.0, "2027", "ext-dbx-ref-1")

    # Mark applied
    app_res = client.post("/api/jobs/manual-applied", json={"job_id": job_id, "confirmation_ref": "DBX-994"})
    assert app_res.status_code == 200

    # Get follow-up drafts
    res = client.get(f"/api/jobs/{job_id}/followup-draft")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    drafts = data["data"]
    assert drafts["company"] == "Databricks"
    assert "DBX-994" in drafts["draft_7d"]
    assert "DBX-994" in drafts["draft_14d"]
    assert "NIT Rourkela" in drafts["draft_7d"]
    assert "Kafka microservices" in drafts["draft_14d"]

    # Verify 60-90 word bounds
    words_7d = len(drafts["draft_7d"].split())
    words_14d = len(drafts["draft_14d"].split())
    assert 55 <= words_7d <= 95
    assert 55 <= words_14d <= 95





