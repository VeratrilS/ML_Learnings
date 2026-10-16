from api.app import app
from api.core.db import SessionLocal
from api.domain.job_runner_report import JobRunnerRun


def test_runner_report_post_and_get(monkeypatch):
    monkeypatch.setenv("APP_PASSCODE", "")
    c = app.test_client()

    report_payload = {
        "started_at": "2026-10-16T03:00:00Z",
        "finished_at": "2026-10-16T03:15:00Z",
        "submitted": [{"company": "Uber", "role": "SWE"}, {"company": "Google", "role": "SWE"}],
        "needs_you": [{"company": "Stripe", "reason": "CAPTCHA"}],
        "unconfirmed": [],
        "failed": [{"company": "Meta", "reason": "Timeout"}],
        "learned": ["Greenhouse requires phone country code"],
    }

    res = c.post("/api/jobs/runner-report", json=report_payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["data"]["submitted_count"] == 2
    assert data["data"]["needs_you_count"] == 1
    assert data["data"]["failed_count"] == 1

    get_res = c.get("/api/jobs/runner-report?limit=5")
    assert get_res.status_code == 200
    runs = get_res.get_json()["data"]
    assert len(runs) >= 1
    latest = runs[0]
    assert latest["submitted_count"] == 2
    assert latest["needs_you_count"] == 1
    assert latest["failed_count"] == 1
    assert "learned" in latest["summary"]


def test_runner_report_auth(monkeypatch):
    monkeypatch.setenv("APP_PASSCODE", "secretpass")
    c = app.test_client()
    assert c.post("/api/jobs/runner-report", json={}).status_code == 401
    assert c.get("/api/jobs/runner-report").status_code == 401
