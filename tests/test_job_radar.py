import json
import pytest
from flask import Flask

from api.core.db import Base, SessionLocal, engine
from api.domain.job_radar import (
    JobApplicationReceipt,
    JobOpportunity,
    JobRadarProfile,
    JobRadarScanLog,
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


def test_job_radar_discovery_and_profile(client):
    """Verifies radar seed, candidate vectors, and 2027 CSE filtering >= 15 LPA."""
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
    assert summary["total_openings"] >= 100
    assert summary["eligible_2027_count"] >= 100
    assert summary["highest_ctc"] >= 40.0
    # Strict integrity: zero fake applied jobs
    assert summary["confirmed_applied_count"] == 0

    jobs = data["jobs"]
    assert len(jobs) >= 100
    for j in jobs[:20]:
        assert "2027" in j["eligible_batches"]
        assert j["ctc_lpa"] >= 15.0
        assert j["portal_url"].startswith("http")


def test_confirm_applied_and_unmark(client):
    """Verifies honest confirm-applied flow syncing to placements board and undo."""
    res = client.get("/api/jobs/radar")
    assert res.status_code == 200
    data = res.get_json()
    first_job = data["jobs"][0]
    job_id = first_job["id"]

    # Confirm genuine application submission
    ref_code = f"TEST-CONFIRM-{first_job['company'].upper()[:4]}-2027"
    conf_res = client.post("/api/jobs/confirm-applied", json={
        "job_id": job_id,
        "confirmation_ref": ref_code,
        "notes": "Verified portal submission test",
    })
    assert conf_res.status_code == 200
    conf_data = conf_res.get_json()
    assert conf_data["status"] == "success"
    assert conf_data["application_ref"] == ref_code

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
        app_entry = db.query(Application).filter(Application.company.ilike(first_job["company"])).first()
        assert app_entry is not None
        assert app_entry.stage == "applied"
        assert ref_code in app_entry.notes
    finally:
        db.close()

    # Unmark / undo
    unmark_res = client.post("/api/jobs/unmark-applied", json={"job_id": job_id})
    assert unmark_res.status_code == 200
    assert unmark_res.get_json()["status"] == "success"

    # Receipts should be 0 again
    rec_res2 = client.get("/api/jobs/receipts")
    assert len(rec_res2.get_json()["receipts"]) == 0


def test_blueprints_endpoint(client):
    """Verifies authentic technical blueprints for tier-1 companies."""
    client.get("/api/jobs/radar")
    res = client.get("/api/jobs/blueprints")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    blueprints = data["blueprints"]
    assert len(blueprints) > 10

    companies = {b["company"] for b in blueprints}
    assert any("Google" in c for c in companies)
    assert any("Uber" in c for c in companies)
    for b in blueprints[:10]:
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

