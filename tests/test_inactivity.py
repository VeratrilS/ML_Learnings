from datetime import datetime, timedelta, timezone

import api.app as app_mod
from api.core.db import SessionLocal
from api.domain.models import Settings
from api.domain.repositories import NotificationRepository


class _Fake:
    calls = 0

    def run(self, skip=frozenset()):
        _Fake.calls += 1
        return {"status": "success", "title": "Two Sum"}


def _set(key, value):
    db = SessionLocal()
    NotificationRepository(db).set_setting(key, value)
    db.close()


def _get(key):
    db = SessionLocal()
    v = NotificationRepository(db).get_setting(key)
    db.close()
    return v


def _setup(monkeypatch, idle_minutes):
    monkeypatch.setattr(app_mod.NotifierFactory, "get_notifier", staticmethod(lambda *a, **k: _Fake()))
    monkeypatch.setattr(app_mod, "_in_quiet_hours", lambda *a: False)
    monkeypatch.setattr(app_mod, "_sync_leetcode", lambda *a: ([], set()))
    monkeypatch.setattr(app_mod, "_touch_activity", lambda: None)
    monkeypatch.setenv("APP_PASSCODE", "")
    db = SessionLocal()
    db.query(Settings).filter(Settings.key.in_(["last_active", "inactivity_last_sent", "leetcode_interval_minutes"])).delete(synchronize_session=False)
    db.commit()
    db.close()
    _set("leetcode_interval_minutes", "10080")  # interval alone would never send
    _set("last_active", (datetime.now(timezone.utc) - timedelta(minutes=idle_minutes)).isoformat())
    _Fake.calls = 0


def test_inactive_sends_once(monkeypatch):
    _setup(monkeypatch, idle_minutes=200)
    client = app_mod.app.test_client()
    # a recent successful log keeps the normal interval from firing
    db = SessionLocal()
    NotificationRepository(db).log_notification("leetcode", "Recent", "q", slug="recent-x")
    db.close()
    r = client.post("/api/cron").get_json()
    assert r["status"] == "success" and r["reason"] == "inactivity" and _Fake.calls == 1
    assert _get("inactivity_last_sent")
    r = client.post("/api/cron").get_json()  # nudged recently -> no second email
    assert r["status"] == "skipped" and _Fake.calls == 1


def test_active_user_not_nudged(monkeypatch):
    _setup(monkeypatch, idle_minutes=30)
    db = SessionLocal()
    NotificationRepository(db).log_notification("leetcode", "Recent", "q", slug="recent-y")
    db.close()
    r = app_mod.app.test_client().post("/api/cron").get_json()
    assert r["status"] == "skipped" and _Fake.calls == 0
