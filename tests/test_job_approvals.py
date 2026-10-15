import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from api.core import config
from api.core.clients import EmailClient
from api.core.db import Base, SessionLocal, engine
from api.domain import job_approvals as ja
from api.domain import job_pack
from api.domain.job_pack import JobPack
from api.domain.job_radar import JobOpportunity
from api.domain.models import Settings

PACK = {
    "cover_note": "I am a final-year CSE student at NIT Rourkela.",
    "why_company": "Acme is hiring a Backend Engineer.",
    "answers": [{"question": "Why are you interested in this role?", "answer": "It matches my Kafka work & <Redis>."},
                {"question": "Are you willing to relocate?", "answer": "Yes, I am willing to relocate."}],
    "resume_highlights": [], "matched_skills": [],
}


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(ja.job_approvals_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setattr(config, "APP_URL", "https://app.test")
    yield app.test_client()
    db = SessionLocal()
    for model in (ja.JobApprovalDecision, JobPack, JobOpportunity, Settings):
        db.query(model).delete()
    db.commit()
    db.close()


@pytest.fixture
def pack_builder(monkeypatch):
    calls = []

    def fake_generate_pack(job, location_prefs=job_pack.DEFAULT_LOCATIONS):
        calls.append(job.id)
        return {**PACK, "job_key": job_pack._job_key(job)}, "template"

    monkeypatch.setattr(job_pack, "generate_pack", fake_generate_pack)
    return calls


@pytest.fixture
def mailbox(monkeypatch):
    sent = []

    def fake_send(self, receiver, subject, body, html=None):
        sent.append({"to": receiver, "subject": subject, "body": body, "html": html})
        return True

    monkeypatch.setattr(EmailClient, "send_email", fake_send)
    monkeypatch.setenv("SENDER_EMAIL", "bot@test")
    monkeypatch.setenv("SENDER_PASSWORD", "pw")
    return sent


_counter = {"n": 0}


def make_job(status="discovered", ctc=20.0, score=80, age_hours=1, company="Acme", role="Backend Engineer",
             url="https://boards.example.com/acme/1", applied_at=None):
    _counter["n"] += 1
    db = SessionLocal()
    job = JobOpportunity(external_id=f"ext-{_counter['n']}", company=company, role=role, ctc_lpa=ctc,
                         portal_url=url, skills_required=json.dumps(["Kafka", "Redis"]), match_score=score,
                         status=status, location="Bengaluru", applied_at=applied_at,
                         discovered_at=_utcnow() - timedelta(hours=age_hours))
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()
    return job_id


def get_job(job_id):
    db = SessionLocal()
    try:
        return db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
    finally:
        db.close()


# ---------------- tokens ----------------
def test_token_roundtrip():
    tok = ja.sign_token(42, "approve")
    assert ja.verify_token(tok) == (42, "approve")
    assert ja.verify_token(ja.sign_token(7, "skip")) == (7, "skip")


def test_token_expiry():
    tok = ja.sign_token(42, "approve", now=time.time() - 8 * 86400)
    assert ja.verify_token(tok) is None
    fresh = ja.sign_token(42, "approve")
    assert ja.verify_token(fresh, now=time.time() + 6 * 86400) == (42, "approve")
    assert ja.verify_token(fresh, now=time.time() + 8 * 86400) is None


def test_token_tamper():
    tok = ja.sign_token(42, "skip")
    payload, sig = tok.split(".")
    forged_payload = ja._b64e(ja._b64d(payload).decode().replace("skip", "approve").encode())
    assert ja.verify_token(f"{forged_payload}.{sig}") is None
    assert ja.verify_token(payload + "." + sig[:-2] + ("AA" if sig[-2:] != "AA" else "BB")) is None
    for junk in ("", "abc", "a.b.c", None, "!!!.???"):
        assert ja.verify_token(junk) is None
    with pytest.raises(ValueError):
        ja.sign_token(1, "apply")


def test_token_depends_on_passcode(monkeypatch):
    monkeypatch.setenv("APP_PASSCODE", "one")
    tok = ja.sign_token(5, "approve")
    assert ja.verify_token(tok) == (5, "approve")
    monkeypatch.setenv("APP_PASSCODE", "two")
    assert ja.verify_token(tok) is None


# ---------------- decide ----------------
def test_approve_sets_status_and_shows_pack(client, pack_builder):
    job_id = make_job()
    res = client.get(f"/api/jobs/decide?t={ja.sign_token(job_id, 'approve')}")
    assert res.status_code == 200 and res.mimetype == "text/html"
    page = res.get_data(as_text=True)
    assert get_job(job_id).status == "approved"
    assert 'href="https://boards.example.com/acme/1"' in page
    assert "Open application" in page
    assert PACK["cover_note"] in page
    assert "It matches my Kafka work &amp; &lt;Redis&gt;." in page  # escaped
    assert "Yes, I am willing to relocate." in page
    assert "Autofill" in page and "attach your resume" in page
    assert page.count('class="copy"') == 4
    assert pack_builder == [job_id]
    db = SessionLocal()
    assert db.query(JobPack).filter(JobPack.job_id == job_id).count() == 1
    assert db.query(ja.JobApprovalDecision).filter_by(job_id=job_id).one().action == "approve"
    db.close()
    # Re-opening the link uses the cached pack
    assert client.get(f"/api/jobs/decide?t={ja.sign_token(job_id, 'approve')}").status_code == 200
    assert pack_builder == [job_id]


def test_skip_sets_status(client, pack_builder):
    job_id = make_job()
    res = client.get(f"/api/jobs/decide?t={ja.sign_token(job_id, 'skip')}")
    assert res.status_code == 200
    assert "Skipped" in res.get_data(as_text=True)
    assert get_job(job_id).status == "skipped"
    assert pack_builder == []
    # Changing your mind: approve after skip works
    client.get(f"/api/jobs/decide?t={ja.sign_token(job_id, 'approve')}")
    assert get_job(job_id).status == "approved"


@pytest.mark.parametrize("status", ["manual_applied", "applied_confirmed"])
@pytest.mark.parametrize("action", ["approve", "skip"])
def test_decision_never_overrides_applied(client, pack_builder, status, action):
    applied = _utcnow()
    job_id = make_job(status=status, applied_at=applied)
    res = client.get(f"/api/jobs/decide?t={ja.sign_token(job_id, action)}")
    assert res.status_code == 200
    assert "Already applied" in res.get_data(as_text=True)
    job = get_job(job_id)
    assert job.status == status and job.applied_at == applied
    assert pack_builder == []


def test_invalid_or_expired_token_is_400(client, pack_builder):
    job_id = make_job()
    assert client.get("/api/jobs/decide?t=garbage").status_code == 400
    assert client.get("/api/jobs/decide").status_code == 400
    old = ja.sign_token(job_id, "approve", now=time.time() - 8 * 86400)
    res = client.get(f"/api/jobs/decide?t={old}")
    assert res.status_code == 400 and "expired" in res.get_data(as_text=True)
    assert get_job(job_id).status == "discovered"


def test_unknown_job_is_404(client):
    assert client.get(f"/api/jobs/decide?t={ja.sign_token(999999, 'approve')}").status_code == 404


def test_approve_survives_pack_failure(client, monkeypatch):
    def boom(job, location_prefs=None):
        raise RuntimeError("llm down")

    monkeypatch.setattr(job_pack, "generate_pack", boom)
    job_id = make_job()
    res = client.get(f"/api/jobs/decide?t={ja.sign_token(job_id, 'approve')}")
    assert res.status_code == 200
    assert "https://boards.example.com/acme/1" in res.get_data(as_text=True)
    assert get_job(job_id).status == "approved"


def test_non_http_portal_url_not_linked(client, pack_builder):
    job_id = make_job(url="javascript:alert(1)")
    page = client.get(f"/api/jobs/decide?t={ja.sign_token(job_id, 'approve')}").get_data(as_text=True)
    assert "javascript:alert" not in page


# ---------------- digest ----------------
def test_digest_selects_right_jobs_with_signed_links(client, mailbox):
    good = make_job(score=90, ctc=30.0)
    unknown_ctc = make_job(score=70, ctc=0.0, company="Beta")
    edge = make_job(score=55, ctc=15.0, company="Gamma")
    low_ctc = make_job(score=90, ctc=12.0)
    low_score = make_job(score=54, ctc=40.0)
    old = make_job(score=90, ctc=30.0, age_hours=60)
    already = make_job(status="approved", score=95, ctc=30.0, company="Waiting Co",
                       url="https://boards.example.com/waiting")
    applied = make_job(status="manual_applied", score=95, applied_at=_utcnow())
    skipped = make_job(status="skipped", score=95)

    res = client.post("/api/jobs/approval-digest")
    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    assert data["job_ids"] == [good, unknown_ctc, edge]
    assert data["waiting"] == 1 and data["emailed"] is True

    assert len(mailbox) == 1
    mail = mailbox[0]
    assert mail["to"] == config.RECEIVER_EMAIL
    assert mail["subject"] == "3 new jobs to review (≥15 LPA)"
    html = mail["html"]
    for job_id in (good, unknown_ctc, edge):
        for action in ("approve", "skip"):
            assert ja.sign_token(job_id, action).split(".")[0] in html
    for job_id in (low_ctc, low_score, old, applied, skipped):
        assert ja.sign_token(job_id, "approve").split(".")[0] not in html.split("Approved, waiting for you")[0]
    assert "https://app.test/api/jobs/decide?t=" in html
    assert 'href="https://app.test#/job-radar"' in html
    assert "Approved, waiting for you" in html
    assert "https://boards.example.com/waiting" in html

    # Every link in the email verifies to the right job/action
    import re
    tokens = re.findall(r"/api/jobs/decide\?t=([A-Za-z0-9_\-.]+)", html)
    decoded = {ja.verify_token(t) for t in tokens}
    assert (good, "approve") in decoded and (good, "skip") in decoded and (already, "approve") in decoded
    assert None not in decoded


def test_digest_caps_at_15(client, mailbox):
    for i in range(20):
        make_job(score=60 + i)
    data = client.post("/api/jobs/approval-digest").get_json()["data"]
    assert data["new"] == 15
    assert mailbox[0]["subject"].startswith("15 new jobs")


def test_digest_is_throttled(client, mailbox):
    make_job()
    assert client.post("/api/jobs/approval-digest").get_json()["data"]["emailed"] is True
    make_job()
    second = client.post("/api/jobs/approval-digest").get_json()
    assert second["status"] == "skipped"
    assert len(mailbox) == 1
    # After the 20 h gap it sends again
    db = SessionLocal()
    row = db.query(Settings).filter(Settings.key == ja.LAST_DIGEST_KEY).one()
    row.value = (datetime.now(timezone.utc) - timedelta(hours=21)).isoformat()
    db.commit()
    db.close()
    assert client.post("/api/jobs/approval-digest").get_json()["data"]["emailed"] is True
    assert len(mailbox) == 2


def test_digest_with_nothing_sends_nothing(client, mailbox):
    make_job(score=10)
    data = client.post("/api/jobs/approval-digest").get_json()["data"]
    assert data == {"new": 0, "waiting": 0, "emailed": False}
    assert mailbox == []


def test_digest_only_waiting(client, mailbox):
    make_job(status="approved")
    data = client.post("/api/jobs/approval-digest").get_json()["data"]
    assert data["new"] == 0 and data["waiting"] == 1
    assert mailbox[0]["subject"] == "1 approved job waiting for you"


def test_digest_failed_send_does_not_throttle(client, monkeypatch, mailbox):
    monkeypatch.setattr(EmailClient, "send_email", lambda *a, **k: False)
    make_job()
    assert client.post("/api/jobs/approval-digest").status_code == 502
    db = SessionLocal()
    assert db.query(Settings).filter(Settings.key == ja.LAST_DIGEST_KEY).count() == 0
    db.close()


# ---------------- queue ----------------
def test_queue_lists_approved_jobs(client, pack_builder):
    a = make_job(score=70)
    b = make_job(score=90, company="Beta")
    make_job(status="discovered")
    make_job(status="manual_applied", applied_at=_utcnow())
    client.get(f"/api/jobs/decide?t={ja.sign_token(a, 'approve')}")
    client.get(f"/api/jobs/decide?t={ja.sign_token(b, 'approve')}")
    res = client.get("/api/jobs/queue")
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert {d["id"] for d in data} == {a, b}
    assert data[0]["id"] == b  # most recently approved first
    assert all(d["status"] == "approved" and d["pack_ready"] and d["approved_at"] for d in data)
    assert data[0]["url"] == "https://boards.example.com/acme/1"
