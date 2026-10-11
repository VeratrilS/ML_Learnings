import sys
import types
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from api.core.config import IST
from api.core.db import Base, SessionLocal, engine
from api.domain import push as push_mod
from api.domain.models import NotificationLog
from api.domain.push import PushLog, PushSubscription, push_bp
from api.domain.repositories import NotificationRepository

SUB = {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "pk", "auth": "ak"}}


class FakeWebPushException(Exception):
    def __init__(self, msg, response=None):
        super().__init__(msg)
        self.response = response


class FakePush:
    """Stands in for the pywebpush module: records calls, never touches the network."""

    def __init__(self):
        self.calls, self.fail = [], {}  # endpoint -> HTTP status to fail with

    def webpush(self, subscription_info, data, **kw):
        self.calls.append({"endpoint": subscription_info["endpoint"], "data": data, **kw})
        code = self.fail.get(subscription_info["endpoint"])
        if code:
            raise FakeWebPushException("boom", response=types.SimpleNamespace(status_code=code))


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(push_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def fake(monkeypatch):
    f = FakePush()
    mod = types.ModuleType("pywebpush")
    mod.webpush, mod.WebPushException = f.webpush, FakeWebPushException
    monkeypatch.setitem(sys.modules, "pywebpush", mod)
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "BPUBLIC")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "private")
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:test@example.com")
    monkeypatch.delenv("CRON_KEY", raising=False)
    monkeypatch.setattr(push_mod, "_upcoming_contests", lambda now: [])
    return f


@pytest.fixture
def client(app, fake):
    yield app.test_client()
    db = SessionLocal()
    for model in (PushSubscription, PushLog, NotificationLog):
        db.query(model).delete()
    from api.domain.models import Settings
    db.query(Settings).delete()
    db.commit()
    db.close()


def _at(h, m=0):
    return datetime(2026, 10, 11, h, m, tzinfo=IST)


def _tick(client, monkeypatch, now, headers=None):
    monkeypatch.setattr(push_mod, "_now", lambda: now)
    res = client.post("/api/push/tick", headers=headers or {})
    return res, (res.get_json().get("data") or {})


def _kinds(data):
    return [f["kind"] for f in data.get("fired", [])]


def test_key_and_subscribe_lifecycle(client):
    assert client.get("/api/push/key").get_json()["data"] == {"public_key": "BPUBLIC", "configured": True}

    res = client.post("/api/push/subscribe", json={"subscription": SUB, "prefs": {"brief": False, "bogus": True}})
    data = res.get_json()["data"]
    assert data["prefs"] == {"brief": False, "streak": True, "contest": True, "revision": True}

    # Re-subscribing upserts and merges prefs instead of duplicating
    client.post("/api/push/subscribe", json={**SUB, "prefs": {"streak": False}})
    got = client.get("/api/push/subscribe", query_string={"endpoint": SUB["endpoint"]}).get_json()
    assert got["devices"] == 1 and got["data"]["prefs"]["brief"] is False and got["data"]["prefs"]["streak"] is False

    assert client.delete("/api/push/subscribe", json={"endpoint": SUB["endpoint"]}).get_json()["removed"] == 1
    assert client.get("/api/push/subscribe", query_string={"endpoint": SUB["endpoint"]}).get_json()["data"] is None


def test_subscribe_validation(client):
    assert client.post("/api/push/subscribe", json={"endpoint": "http://x", "keys": SUB["keys"]}).status_code == 400
    assert client.post("/api/push/subscribe", json={"endpoint": SUB["endpoint"], "keys": {}}).status_code == 400
    assert client.delete("/api/push/subscribe", json={}).status_code == 400


def test_send_test_and_gone_subscription_removed(client, fake):
    assert client.post("/api/push/test").status_code == 404
    client.post("/api/push/subscribe", json=SUB)
    res = client.post("/api/push/test", json={"endpoint": SUB["endpoint"]})
    assert res.status_code == 200 and res.get_json()["data"]["ok"] == 1
    assert fake.calls[-1]["vapid_claims"] == {"sub": "mailto:test@example.com"}

    fake.fail[SUB["endpoint"]] = 410
    assert client.post("/api/push/test").status_code == 502
    db = SessionLocal()
    assert db.query(PushSubscription).count() == 0
    db.close()


def test_transient_failure_counts_but_keeps_subscription(client, fake):
    client.post("/api/push/subscribe", json=SUB)
    fake.fail[SUB["endpoint"]] = 500
    client.post("/api/push/test")
    got = client.get("/api/push/subscribe", query_string={"endpoint": SUB["endpoint"]}).get_json()["data"]
    assert got["fail_count"] == 1


def test_test_requires_vapid(client, monkeypatch):
    monkeypatch.delenv("VAPID_PRIVATE_KEY")
    client.post("/api/push/subscribe", json=SUB)
    assert client.post("/api/push/test").status_code == 503


def test_tick_cron_key(client, monkeypatch):
    monkeypatch.setenv("CRON_KEY", "s3cret")
    assert _tick(client, monkeypatch, _at(12))[0].status_code == 401
    assert _tick(client, monkeypatch, _at(12), {"X-Cron-Key": "s3cret"})[0].status_code == 200


def test_tick_without_subscribers_is_noop(client, monkeypatch, fake):
    _, data = _tick(client, monkeypatch, _at(8, 30))
    assert data["fired"] == [] and fake.calls == []


def test_morning_brief_fires_once(client, monkeypatch, fake):
    client.post("/api/push/subscribe", json=SUB)
    _, data = _tick(client, monkeypatch, _at(8, 5))
    assert _kinds(data) == ["brief"] and len(fake.calls) == 1
    assert '"kind": "brief"' in fake.calls[0]["data"]
    _, data = _tick(client, monkeypatch, _at(8, 10))  # idempotent within the window
    assert data["fired"] == [] and len(fake.calls) == 1
    _, data = _tick(client, monkeypatch, _at(9, 30))  # window closed
    assert data["fired"] == []


def test_brief_respects_prefs_and_quiet_hours(client, monkeypatch, fake):
    client.post("/api/push/subscribe", json={**SUB, "prefs": {"brief": False}})
    assert _tick(client, monkeypatch, _at(8, 5))[1]["fired"] == []

    client.post("/api/push/subscribe", json={**SUB, "prefs": {"brief": True}})
    db = SessionLocal()
    NotificationRepository(db).set_setting("quiet_end", "10")  # quiet 23:00-10:00
    db.close()
    assert _tick(client, monkeypatch, _at(8, 5))[1]["fired"] == []
    assert fake.calls == []


def test_streak_at_risk_only_when_nothing_solved(client, monkeypatch, fake):
    client.post("/api/push/subscribe", json=SUB)
    _, data = _tick(client, monkeypatch, _at(21, 45))
    assert _kinds(data) == ["streak"]

    # Next day, a problem solved after IST midnight suppresses the nudge
    nxt = _at(21, 45) + timedelta(days=1)
    db = SessionLocal()
    solved_at = (nxt - timedelta(hours=3)).astimezone(timezone.utc).replace(tzinfo=None)
    db.add(NotificationLog(task_type="leetcode", title="Two Sum", is_completed=True, completed_at=solved_at))
    db.commit()
    db.close()
    assert _tick(client, monkeypatch, nxt)[1]["fired"] == []


def test_revision_needs_due_reviews(client, monkeypatch, fake):
    client.post("/api/push/subscribe", json=SUB)
    monkeypatch.setattr(push_mod, "_due_reviews", lambda repo: 0)
    assert _tick(client, monkeypatch, _at(18, 15))[1]["fired"] == []
    monkeypatch.setattr(push_mod, "_due_reviews", lambda repo: 3)
    _, data = _tick(client, monkeypatch, _at(18, 20))
    assert _kinds(data) == ["revision"] and "3 problems due" in fake.calls[-1]["data"]


def test_contest_reminder_ignores_quiet_hours(client, monkeypatch, fake):
    client.post("/api/push/subscribe", json=SUB)
    db = SessionLocal()
    NotificationRepository(db).set_setting("quiet_start", "0")
    NotificationRepository(db).set_setting("quiet_end", "23")
    db.close()
    now = _at(2, 0)

    def contests(start_in):
        start = (now + start_in).astimezone(timezone.utc).isoformat()
        return lambda _now: [{"platform": "codeforces", "name": "Round 1", "start": start,
                              "url": "https://codeforces.com/contest/2000", "running": False}]

    monkeypatch.setattr(push_mod, "_upcoming_contests", contests(timedelta(minutes=90)))
    assert _tick(client, monkeypatch, now)[1]["fired"] == []
    monkeypatch.setattr(push_mod, "_upcoming_contests", contests(timedelta(minutes=60)))
    _, data = _tick(client, monkeypatch, now)
    assert _kinds(data) == ["contest"] and "Codeforces contest in 60 min" in fake.calls[-1]["data"]
    assert fake.calls[-1]["ttl"] == 3600
    assert _tick(client, monkeypatch, now)[1]["fired"] == []  # deduped per contest


def test_tick_unconfigured(client, monkeypatch):
    monkeypatch.delenv("VAPID_PUBLIC_KEY")
    assert _tick(client, monkeypatch, _at(8, 5))[1]["configured"] is False
