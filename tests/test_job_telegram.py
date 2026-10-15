import json
from datetime import timedelta

import pytest
from flask import Flask

from api.core.db import Base, SessionLocal, engine
from api.domain import job_telegram as jt
from api.domain.job_radar import JobOpportunity

TOKEN = "123:TEST"
CHAT = "987654321"
SECRET = "hook-secret_1"


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(jt.job_telegram_bp)
    Base.metadata.create_all(bind=engine, tables=[JobOpportunity.__table__])
    yield app


@pytest.fixture
def client(app):
    yield app.test_client()
    db = SessionLocal()
    db.query(JobOpportunity).delete()
    db.commit()
    db.close()


@pytest.fixture
def calls(monkeypatch):
    """Fake requests.post: records (method, json) and replies ok. Fails the test on any real network use."""
    recorded = []

    class Resp:
        status_code = 200

        def json(self):
            return {"ok": True, "result": {}}

    def fake_post(url, json=None, timeout=None):
        assert url.startswith(f"https://api.telegram.org/bot{TOKEN}/")
        assert timeout
        recorded.append((url.rsplit("/", 1)[1], json))
        return Resp()

    monkeypatch.setattr(jt.requests, "post", fake_post)
    return recorded


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)


@pytest.fixture
def unconfigured(monkeypatch):
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_WEBHOOK_SECRET"):
        monkeypatch.delenv(k, raising=False)


_n = [0]


def _job(company="Acme", role="SDE 1", status="discovered", score=70, ctc=0.0, age_hours=1,
         notes="Live from Greenhouse; posted 2026-10-15; est. CTC 18-28 LPA", url="https://example.com/apply/1"):
    _n[0] += 1
    db = SessionLocal()
    job = JobOpportunity(external_id=f"tg-{_n[0]}", company=company, role=role, ctc_lpa=ctc, location="Bengaluru",
                         portal_url=url, skills_required=json.dumps(["C++"]), match_score=score, status=status,
                         notes=notes, discovered_at=jt._utcnow() - timedelta(hours=age_hours))
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()
    return job_id


def _get(job_id):
    db = SessionLocal()
    try:
        return db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
    finally:
        db.close()


def _update(data, chat=CHAT, message_id=55):
    return {"update_id": 1, "callback_query": {"id": "cb1", "from": {"id": int(chat)}, "data": data,
                                               "message": {"message_id": message_id, "chat": {"id": int(chat)}}}}


def _hook(client, update, secret=SECRET):
    headers = {jt.SECRET_HEADER: secret} if secret is not None else {}
    return client.post("/api/jobs/telegram/webhook", json=update, headers=headers)


# ---------------- Not configured ----------------
def test_not_configured_is_noop(client, unconfigured, calls):
    job_id = _job()
    assert jt.is_configured() is False
    res = jt.send_job_cards([_get(job_id)])
    assert res["status"] == "not_configured" and res["sent"] == 0
    assert "TELEGRAM_BOT_TOKEN" in res["message"]
    assert jt.set_webhook()["status"] == "not_configured"

    push = client.post("/api/jobs/telegram/push")
    assert push.status_code == 200 and push.get_json()["status"] == "not_configured"
    hook = _hook(client, _update(f"a:{job_id}"))
    assert hook.get_json()["status"] == "not_configured"
    assert calls == []
    assert _get(job_id).status == "discovered"


def test_only_token_set_is_still_not_configured(client, unconfigured, monkeypatch, calls):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    assert jt.send_job_cards([])["status"] == "not_configured"
    assert calls == []


# ---------------- Cards ----------------
def test_card_payload_and_buttons(client, configured, calls):
    job_id = _job(company="Stripe & Co", role="Backend <Engineer>", score=81)
    res = jt.send_job_cards([_get(job_id)])
    assert res == {"status": "success", "sent": 1, "failed": [], "total": 1}
    assert len(calls) == 1
    method, payload = calls[0]
    assert method == "sendMessage"
    assert payload["chat_id"] == CHAT and payload["parse_mode"] == "HTML"
    text = payload["text"]
    assert "Stripe &amp; Co" in text and "Backend &lt;Engineer&gt;" in text   # HTML-escaped
    assert "Bengaluru" in text and "18-28 LPA" in text and "81/100" in text
    assert "https://example.com/apply/1" in text
    rows = payload["reply_markup"]["inline_keyboard"]
    assert rows[0] == [{"text": "✅ Approve", "callback_data": f"a:{job_id}"},
                       {"text": "⏭ Skip", "callback_data": f"s:{job_id}"}]
    assert rows[1] == [{"text": "🔗 Open", "url": "https://example.com/apply/1"}]
    assert all(len(b["callback_data"].encode()) <= 64 for b in rows[0])


def test_card_without_note_ctc_uses_ctc_column_and_no_url_button_when_missing(client, configured, calls):
    job_id = _job(notes="Live from Lever", ctc=22.0, url="")
    jt.send_job_cards([_get(job_id)])
    payload = calls[0][1]
    assert "22 LPA" in payload["text"]
    assert len(payload["reply_markup"]["inline_keyboard"]) == 1   # no Open button for a missing URL


def test_send_reports_failures(client, configured, monkeypatch):
    class Bad:
        status_code = 400

        def json(self):
            return {"ok": False, "description": "chat not found"}

    monkeypatch.setattr(jt.requests, "post", lambda *a, **k: Bad())
    job_id = _job()
    res = jt.send_job_cards([_get(job_id)])
    assert res["status"] == "error" and res["failed"] == [job_id]


# ---------------- Push selection ----------------
def test_push_sends_top_new_matches_only(client, configured, calls):
    good = _job(score=90, ctc=0.0)
    good2 = _job(score=60, ctc=18.0)
    _job(score=50)                          # score too low
    _job(score=95, ctc=10.0)                # CTC known and < 15
    _job(score=95, age_hours=60)            # older than 48 h
    _job(score=95, status="manual_applied")
    _job(score=95, status="approved")
    res = client.post("/api/jobs/telegram/push")
    body = res.get_json()
    assert body["status"] == "success" and body["sent"] == 2
    sent_ids = [p["reply_markup"]["inline_keyboard"][0][0]["callback_data"] for _, p in calls]
    assert sent_ids == [f"a:{good}", f"a:{good2}"]   # best match first


def test_push_caps_at_ten(client, configured, calls):
    for i in range(13):
        _job(score=60 + i)
    assert client.post("/api/jobs/telegram/push").get_json()["sent"] == jt.PUSH_MAX == 10


# ---------------- Webhook auth ----------------
@pytest.mark.parametrize("secret", [None, "", "wrong", SECRET + "x"])
def test_webhook_rejects_bad_secret(client, configured, calls, secret):
    job_id = _job()
    res = _hook(client, _update(f"a:{job_id}"), secret=secret)
    assert res.status_code == 403
    assert calls == []
    assert _get(job_id).status == "discovered"


def test_webhook_rejects_when_secret_env_missing(client, configured, monkeypatch, calls):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET")
    job_id = _job()
    assert _hook(client, _update(f"a:{job_id}"), secret="").status_code == 403
    assert _get(job_id).status == "discovered"


def test_webhook_ignores_other_chat(client, configured, calls):
    job_id = _job()
    res = _hook(client, _update(f"a:{job_id}", chat="111"))
    assert res.status_code == 200 and res.get_json()["status"] == "ignored"
    assert calls == []
    assert _get(job_id).status == "discovered"


def test_webhook_ignores_non_callback_updates(client, configured, calls):
    res = _hook(client, {"update_id": 2, "message": {"chat": {"id": int(CHAT)}, "text": "/start"}})
    assert res.status_code == 200 and res.get_json()["status"] == "ignored"
    assert calls == []


# ---------------- Transitions ----------------
def test_approve_changes_status_answers_and_edits(client, configured, calls):
    job_id = _job()
    res = _hook(client, _update(f"a:{job_id}"))
    assert res.get_json() == {"status": "success", "job_id": job_id, "job_status": "approved"}
    assert _get(job_id).status == "approved"
    methods = [m for m, _ in calls]
    assert methods == ["answerCallbackQuery", "editMessageText"]
    assert calls[0][1]["callback_query_id"] == "cb1"
    edit = calls[1][1]
    assert edit["chat_id"] == int(CHAT) and edit["message_id"] == 55
    assert "Approved ✓ — open the link, Autofill, submit" in edit["text"]
    assert edit["reply_markup"]["inline_keyboard"] == [[{"text": "🔗 Open", "url": "https://example.com/apply/1"}]]


def test_skip_changes_status_and_edits(client, configured, calls):
    job_id = _job()
    res = _hook(client, _update(f"s:{job_id}"))
    assert res.get_json()["job_status"] == "skipped"
    assert _get(job_id).status == "skipped"
    assert "Skipped" in calls[1][1]["text"]


def test_approve_is_idempotent_and_skip_after_approve_allowed(client, configured, calls):
    job_id = _job()
    _hook(client, _update(f"a:{job_id}"))
    assert _hook(client, _update(f"a:{job_id}")).get_json()["job_status"] == "approved"
    assert _hook(client, _update(f"s:{job_id}")).get_json()["job_status"] == "skipped"


def test_cannot_approve_from_skipped(client, configured, calls):
    job_id = _job(status="skipped")
    res = _hook(client, _update(f"a:{job_id}"))
    assert res.get_json()["status"] == "unchanged"
    assert _get(job_id).status == "skipped"


@pytest.mark.parametrize("applied", ["manual_applied", "applied_confirmed"])
@pytest.mark.parametrize("data", ["a", "s"])
def test_never_overrides_applied(client, configured, calls, applied, data):
    job_id = _job(status=applied)
    res = _hook(client, _update(f"{data}:{job_id}"))
    assert res.status_code == 200 and res.get_json()["status"] == "unchanged"
    assert _get(job_id).status == applied
    assert [m for m, _ in calls] == ["answerCallbackQuery"]   # alert only, message not edited
    assert calls[0][1]["show_alert"] is True


def test_apply_decision_direct_never_touches_manual_applied():
    job_id = _job(status="manual_applied")
    db = SessionLocal()
    try:
        for action in ("approve", "skip"):
            job, outcome = jt.apply_decision(db, job_id, action)
            assert outcome == "unchanged" and job.status == "manual_applied"
        assert jt.apply_decision(db, 999999, "approve") == (None, "missing")
    finally:
        db.query(JobOpportunity).delete()
        db.commit()
        db.close()


def test_unknown_job_and_bad_data(client, configured, calls):
    assert _hook(client, _update("a:999999")).get_json()["reason"] == "missing"
    assert _hook(client, _update("x:1")).get_json()["reason"] == "data"
    assert _hook(client, _update("a:1; DROP")).get_json()["reason"] == "data"


def test_set_webhook_sends_secret(configured, calls):
    res = jt.set_webhook("https://example.com/api/jobs/telegram/webhook")
    assert res["status"] == "success"
    method, payload = calls[0]
    assert method == "setWebhook" and payload["secret_token"] == SECRET
    assert payload["url"] == "https://example.com/api/jobs/telegram/webhook"
