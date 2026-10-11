from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from api.core import clients as clients_mod
from api.core.config import IST
from api.core.db import Base, engine, SessionLocal
from api.domain import weekly as weekly_mod
from api.domain.features import FeatureFlag
from api.domain.focus import FocusSession
from api.domain.learning import Course, Lesson
from api.domain.models import NotificationLog, Settings
from api.domain.repositories import NotificationRepository
from api.domain.sheets import SheetProblem
from api.domain.weekly import weekly_bp, build_report, render_email, LAST_SENT_KEY

FIXED_NOW = datetime(2026, 10, 12, 9, 30, tzinfo=IST)  # a Monday
TODAY = FIXED_NOW.date()


class Clock:
    """Mutable frozen clock so a test can move across IST days."""
    def __init__(self):
        self.now = FIXED_NOW

    def __call__(self):
        return self.now


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(weekly_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(weekly_mod, "now_ist", c)

    # build_report (focus window) and the cron throttle read datetime.now(timezone.utc) directly;
    # drive them from the same frozen clock so the tests don't depend on the real date.
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return c.now.astimezone(tz) if tz else c.now.astimezone(timezone.utc).replace(tzinfo=None)

    monkeypatch.setattr(weekly_mod, "datetime", FrozenDatetime)
    return c


@pytest.fixture
def client(app, clock):
    yield app.test_client()
    db = SessionLocal()
    for model in (NotificationLog, SheetProblem, Lesson, Course, FocusSession, FeatureFlag):
        db.query(model).delete()
    db.query(Settings).filter(Settings.key.in_(["daily_goal", LAST_SENT_KEY])).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.fixture
def mailer(monkeypatch):
    """Configured email with send_email recorded instead of hitting SMTP."""
    calls = []
    state = {"ok": True}

    def fake_send(self, receiver_email, subject, body, html=None):
        calls.append({"to": receiver_email, "subject": subject, "body": body, "html": html})
        return state["ok"]

    monkeypatch.setenv("SENDER_EMAIL", "bot@example.com")
    monkeypatch.setenv("SENDER_PASSWORD", "secret")
    monkeypatch.setattr(clients_mod.EmailClient, "send_email", fake_send)
    return calls, state


# ---------------- helpers ----------------
def _utc(days_ago, hour=12, minute=0):
    """Naive UTC timestamp for `hour:minute` IST on the IST day `days_ago` before TODAY."""
    ist = datetime(TODAY.year, TODAY.month, TODAY.day, hour, minute, tzinfo=IST) - timedelta(days=days_ago)
    return ist.astimezone(timezone.utc).replace(tzinfo=None)


def _day(days_ago):
    return (TODAY - timedelta(days=days_ago)).isoformat()


def _add(*rows):
    db = SessionLocal()
    db.add_all(rows)
    db.commit()
    db.close()


def _solve(days_ago, task_type="leetcode", difficulty="Medium", topic=None, **kw):
    fields = dict(task_type=task_type, title=f"P{days_ago}", status="success", is_completed=True,
                  difficulty=difficulty, topic=topic, completed_at=_utc(days_ago))
    fields.update(kw)
    return NotificationLog(**fields)


def _set(key, value):
    db = SessionLocal()
    NotificationRepository(db).set_setting(key, value)
    db.close()


def _setting(key):
    db = SessionLocal()
    try:
        return NotificationRepository(db).get_setting(key)
    finally:
        db.close()


def _flag(status):
    _add(FeatureFlag(key="weekly", status=status))


def _get(client, weeks_ago=None):
    url = "/api/weekly" if weeks_ago is None else f"/api/weekly?weeks_ago={weeks_ago}"
    res = client.get(url)
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["status"] == "success"
    return body["data"]


def _cron(client):
    res = client.post("/api/weekly/cron")
    assert res.status_code == 200, res.get_json()
    return res.get_json()


# ---------------- report ----------------
def test_empty_report(client):
    r = _get(client)
    assert r["start"] == "2026-10-06" and r["end"] == "2026-10-12" and r["weeks_ago"] == 0
    assert [d["date"] for d in r["days"]] == [_day(i) for i in range(6, -1, -1)]
    assert all(d["solved"] == 0 and d["focus"] == 0 and d["goal_met"] is False for d in r["days"])
    assert r["goal"] == 2
    for key in ("solved", "solved_prev", "leetcode", "codeforces", "active_days", "goal_days",
                "focus_minutes", "focus_minutes_prev", "videos", "videos_prev", "videos_done", "videos_total",
                "sheet", "sheet_prev", "sheet_done", "sheet_total", "revisions", "episodes",
                "streak", "best_streak"):
        assert r[key] == 0, key
    assert r["by_difficulty"] == {} and r["topics"] == [] and r["sheet_by_difficulty"] == {}
    assert r["best_day"] is None
    assert r["next"] == {"lesson": None, "sheet": None}


def test_solve_counts_this_week_vs_previous(client):
    _set("daily_goal", "2")
    _add(
        # this week (IST days 0..6 ago)
        _solve(0, difficulty="Easy", topic="Array, Hash Table"),
        _solve(0, topic="Array"),
        _solve(2, task_type="codeforces", difficulty="1200", topic="greedy"),
        _solve(2, topic="Array,Two Pointers , "),
        _solve(3, completed_at=None, timestamp=_utc(3)),  # falls back to timestamp
        _solve(6, difficulty="Hard"),
        # previous week (7..13 ago)
        _solve(7), _solve(8, task_type="codeforces"), _solve(13),
        # neither
        _solve(14), _solve(15),
        # not solves
        _solve(0, status="failed"),
        _solve(0, is_completed=False),
        _solve(0, task_type="incident"),
    )
    r = _get(client)
    assert r["solved"] == 6 and r["solved_prev"] == 3
    assert r["leetcode"] == 5 and r["codeforces"] == 1
    assert r["by_difficulty"] == {"Easy": 1, "Medium": 3, "1200": 1, "Hard": 1}
    assert r["topics"][0] == {"topic": "Array", "count": 3}
    assert {t["topic"]: t["count"] for t in r["topics"]} == {"Array": 3, "Hash Table": 1, "greedy": 1, "Two Pointers": 1}
    per_day = {d["date"]: d["solved"] for d in r["days"]}
    assert per_day == {_day(0): 2, _day(1): 0, _day(2): 2, _day(3): 1, _day(4): 0, _day(5): 0, _day(6): 1}
    assert {d["date"] for d in r["days"] if d["goal_met"]} == {_day(0), _day(2)}
    assert r["active_days"] == 4 and r["goal_days"] == 2
    assert r["best_day"] == {"date": _day(0), "solved": 2}  # tie with 2 days ago -> latest day wins


def test_goal_setting_changes_goal_days(client):
    _set("daily_goal", "1")
    _add(_solve(0), _solve(1), _solve(1))
    r = _get(client)
    assert r["goal"] == 1 and r["goal_days"] == 2 and r["active_days"] == 2
    assert r["best_day"] == {"date": _day(1), "solved": 2}
    _set("daily_goal", "3")
    r = _get(client)
    assert r["goal"] == 3 and r["goal_days"] == 0


def test_ist_day_boundary(client):
    # Bucketing is by IST day, not UTC day: 00:30 IST is still the previous day in UTC.
    # 23:00 IST eight days ago and 00:30 IST seven days ago are prev week; 00:30 IST six days ago is this week.
    _add(_solve(8, completed_at=_utc(8, 23, 0)),
         _solve(7, completed_at=_utc(7, 0, 30)),
         _solve(6, completed_at=_utc(6, 0, 30)))
    r = _get(client)
    assert r["solved"] == 1 and r["days"][0] == {"date": _day(6), "solved": 1, "focus": 0, "goal_met": False}
    assert r["solved_prev"] == 2


def test_streak(client):
    _add(_solve(0), _solve(1), _solve(2), _solve(5))
    r = _get(client)
    assert r["streak"] == 3 and r["best_streak"] == 3


def test_revisions_and_episodes(client):
    _add(_solve(20, last_review_at=_utc(1)),
         _solve(20, last_review_at=_utc(10)),
         NotificationLog(task_type="watch", title="Ep 1", status="success", is_completed=True, completed_at=_utc(0)),
         NotificationLog(task_type="watch", title="Ep 0", status="success", is_completed=True, completed_at=_utc(9)))
    r = _get(client)
    assert r["revisions"] == 1 and r["episodes"] == 1


def test_apple_sheet_and_videos(client):
    _add(
        SheetProblem(sheet="apple", position=1, leetcode_id=146, title="LRU Cache", slug="lru-cache",
                     difficulty="Medium", done=True, done_at=_utc(1)),
        SheetProblem(sheet="apple", position=2, leetcode_id=42, title="Trapping Rain Water", slug="trapping-rain-water",
                     difficulty="Hard", done=True, done_at=_utc(9)),
        SheetProblem(sheet="apple", position=4, leetcode_id=1, title="Two Sum", slug="two-sum",
                     difficulty="Medium", done=False),
        SheetProblem(sheet="apple", position=3, leetcode_id=56, title="Merge Intervals", slug="merge-intervals",
                     difficulty="Medium", done=False),
        SheetProblem(sheet="apple", position=5, leetcode_id=200, title="Number of Islands", slug="number-of-islands",
                     difficulty="Medium", done=True, done_at=_utc(20)),
    )
    db = SessionLocal()
    archived = Course(title="Old course", position=0, is_active=False)
    active = Course(title="System Design", position=1, is_active=True)
    db.add_all([archived, active])
    db.flush()
    db.add_all([
        Lesson(course_id=archived.id, position=1, title="Archived lesson", video_id="a1", done=False),
        Lesson(course_id=active.id, position=1, title="Intro", video_id="v1", done=True, done_at=_utc(0)),
        Lesson(course_id=active.id, position=2, title="Scaling", video_id="v2", done=True, done_at=_utc(12)),
        Lesson(course_id=active.id, position=4, title="Caching", video_id="v4", done=False),
        Lesson(course_id=active.id, position=3, title="Load Balancers", video_id="v3", done=False),
    ])
    db.commit()
    db.close()

    r = _get(client)
    assert r["sheet"] == 1 and r["sheet_prev"] == 1 and r["sheet_done"] == 3 and r["sheet_total"] == 5
    assert r["sheet_by_difficulty"] == {"Medium": 1}
    assert r["videos"] == 1 and r["videos_prev"] == 1 and r["videos_done"] == 2 and r["videos_total"] == 5
    assert r["next"]["sheet"] == {"title": "Merge Intervals", "leetcode_id": 56, "difficulty": "Medium",
                                  "url": "https://leetcode.com/problems/merge-intervals/"}
    assert r["next"]["lesson"] == {"title": "Load Balancers", "position": 3}


def test_focus_minutes(client):
    _add(FocusSession(started_at=_utc(0, 8), minutes=25),
         FocusSession(started_at=_utc(4, 22), minutes=50, completed=False),
         FocusSession(started_at=_utc(10), minutes=30),
         FocusSession(started_at=_utc(20), minutes=99))
    r = _get(client)
    assert r["focus_minutes"] == 75 and r["focus_minutes_prev"] == 30
    focus = {d["date"]: d["focus"] for d in r["days"]}
    assert focus[_day(0)] == 25 and focus[_day(4)] == 50 and sum(focus.values()) == 75


def test_weeks_ago_shifts_window(client):
    _add(_solve(0), _solve(7), _solve(10), _solve(15),
         FocusSession(started_at=_utc(8), minutes=40), FocusSession(started_at=_utc(16), minutes=20))
    now = _get(client, 0)
    last = _get(client, 1)
    assert last["weeks_ago"] == 1
    assert last["start"] == (TODAY - timedelta(days=13)).isoformat() == _day(13)
    assert last["end"] == _day(7)
    assert [d["date"] for d in last["days"]] == [
        (datetime.fromisoformat(d["date"]) - timedelta(days=7)).date().isoformat() for d in now["days"]]
    assert last["solved"] == 2 and last["solved_prev"] == 1
    assert last["focus_minutes"] == 40 and last["focus_minutes_prev"] == 20
    assert now["solved"] == 1 and now["solved_prev"] == 2


@pytest.mark.parametrize("value", ["x", "-1", "53", "1.5"])
def test_weeks_ago_validation(client, value):
    res = client.get(f"/api/weekly?weeks_ago={value}")
    assert res.status_code == 400
    assert res.get_json()["status"] == "error"


def test_weeks_ago_max_is_allowed(client):
    assert _get(client, 52)["end"] == (TODAY - timedelta(days=7 * 52)).isoformat()


# ---------------- cron ----------------
def test_cron_skips_when_flag_missing_or_beta(client, mailer):
    calls, _ = mailer
    body = _cron(client)
    assert body["status"] == "skipped" and "beta" in body["message"]
    _flag("beta")
    body = _cron(client)
    assert body["status"] == "skipped" and "beta" in body["message"]
    assert calls == [] and _setting(LAST_SENT_KEY) is None


def test_cron_approved_without_email(client):
    _flag("approved")
    assert _cron(client) == {"status": "skipped", "message": "Email not configured."}
    assert _setting(LAST_SENT_KEY) is None


def test_cron_sends_once_per_week(client, clock, mailer):
    calls, _ = mailer
    _flag("approved")
    assert _cron(client) == {"status": "success"}
    assert len(calls) == 1
    last = datetime.fromisoformat(_setting(LAST_SENT_KEY))
    assert last == FIXED_NOW  # stored as aware UTC
    assert last.utcoffset() == timedelta(0)

    assert _cron(client) == {"status": "skipped", "message": "Already sent this week."}
    clock.now = FIXED_NOW + timedelta(days=5, hours=23)
    assert _cron(client) == {"status": "skipped", "message": "Already sent this week."}
    assert len(calls) == 1

    clock.now = FIXED_NOW + timedelta(days=7)
    assert _cron(client) == {"status": "success"}
    assert len(calls) == 2
    assert datetime.fromisoformat(_setting(LAST_SENT_KEY)) == clock.now


def test_cron_sends_when_last_sent_is_old(client, mailer):
    calls, _ = mailer
    _flag("approved")
    _set(LAST_SENT_KEY, (FIXED_NOW - timedelta(days=7)).astimezone(timezone.utc).isoformat())
    assert _cron(client) == {"status": "success"}
    assert len(calls) == 1


def test_cron_send_failure_does_not_record(client, mailer):
    calls, state = mailer
    state["ok"] = False
    _flag("approved")
    assert _cron(client) == {"status": "error", "message": "Failed to send the email."}
    assert len(calls) == 1 and _setting(LAST_SENT_KEY) is None


# ---------------- send now ----------------
def test_send_requires_email(client):
    res = client.post("/api/weekly/send")
    assert res.status_code == 400
    assert "Email not configured" in res.get_json()["message"]


def test_send_now(client, mailer):
    calls, _ = mailer
    _add(_solve(0), _solve(1, task_type="codeforces"), _solve(9))
    res = client.post("/api/weekly/send")
    assert res.status_code == 200 and res.get_json() == {"status": "success"}
    assert len(calls) == 1
    sent = calls[0]
    assert sent["to"] == weekly_mod.RECEIVER_EMAIL
    assert "2 solved" in sent["subject"] and "0 Apple" in sent["subject"] and "0 videos" in sent["subject"]
    assert "06 Oct – 12 Oct" in sent["body"] and "2 problems solved" in sent["body"]
    assert "06 Oct – 12 Oct" in sent["html"] and "Your week" in sent["html"]
    assert "(1 LeetCode, 1 Codeforces)" in sent["html"]
    assert "+1 vs last week" in sent["html"]
    assert _setting(LAST_SENT_KEY) is None  # manual send doesn't touch the cron throttle


def test_send_now_failure_is_502(client, mailer):
    _, state = mailer
    state["ok"] = False
    res = client.post("/api/weekly/send")
    assert res.status_code == 502 and res.get_json()["status"] == "error"


# ---------------- email rendering ----------------
def test_render_email_escapes_html(client):
    _add(_solve(0, topic="<script>alert(1)</script>, DP", difficulty="<b>"),
         SheetProblem(sheet="apple", position=1, leetcode_id=7, title="A<B & C", slug="a-b-c",
                      difficulty="Medium", done=False))
    db = SessionLocal()
    course = Course(title="SD", position=0, is_active=True)
    db.add(course)
    db.flush()
    db.add(Lesson(course_id=course.id, position=1, title="<img src=x onerror=alert(1)>", video_id="v", done=False))
    db.commit()
    try:
        out = render_email(build_report(db))
    finally:
        db.close()
    assert "<script>" not in out and "&lt;script&gt;alert(1)&lt;/script&gt; (1)" in out
    assert "Difficulty: &lt;b&gt; 1" in out
    assert "7. A&lt;B &amp; C" in out and "https://leetcode.com/problems/a-b-c/" in out
    assert "<img" not in out and "#1 &lt;img src=x onerror=alert(1)&gt;" in out
    assert "Pick up next week" in out


def test_render_email_deltas(client):
    _add(_solve(8), _solve(9), _solve(0), FocusSession(started_at=_utc(0), minutes=90))
    db = SessionLocal()
    try:
        out = render_email(build_report(db))
    finally:
        db.close()
    assert "−1 vs last week" in out  # 1 solved vs 2
    assert "+90 min vs last week" in out and "1.5h" in out
    assert "Pick up next week" not in out
