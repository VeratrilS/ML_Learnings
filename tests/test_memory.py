"""FSRS-lite revision, focus sessions, streak freezes / rest days and the adaptive goal."""
from datetime import date, datetime, time, timedelta, timezone

import pytest
from flask import Flask

import api.app as app_mod
from api.core.config import IST
from api.core.db import Base, SessionLocal, engine
from api.domain import focus as focus_mod
from api.domain.focus import FocusSession, compute_streak, focus_bp, suggest_goal
from api.domain.models import NotificationLog
from api.domain.repositories import (
    GRADUATE_AFTER, INITIAL_DIFFICULTY, INITIAL_STABILITY, NotificationRepository, S_MAX, S_MIN,
    next_memory_state, pick_interval_days, recall_probability,
)

TODAY = date(2026, 10, 11)
FIXED_NOW = datetime.combine(TODAY, time(9, 30), tzinfo=IST)
NOW_UTC = FIXED_NOW.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_noon(d):
    """Naive UTC timestamp for noon IST on day d."""
    return datetime.combine(d, time(12, 0), tzinfo=IST).astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def repo():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    yield NotificationRepository(db)
    db.query(NotificationLog).delete()
    db.commit()
    db.close()


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)
    app_mod.app.config["TESTING"] = True
    yield app_mod.app.test_client()
    db = SessionLocal()
    db.query(NotificationLog).delete()
    db.commit()
    db.close()


def _solved(repo, title="Two Sum", difficulty="Medium", stability=None, difficulty_fsrs=5.0,
            last_review_at=None, next_review_at=None, review_stage=0):
    log = repo.log_notification("leetcode", title, None, slug=title.lower().replace(" ", "-"), difficulty=difficulty)
    repo.mark_task_completed(log.id, True)
    if stability is not None:
        log.stability = stability
        log.difficulty_fsrs = difficulty_fsrs
        log.last_review_at = last_review_at
        log.next_review_at = next_review_at
        log.review_stage = review_stage
        repo.db.commit()
    return log


# ---------------- FSRS-lite ----------------
def test_recall_is_90_percent_at_stability():
    assert recall_probability(5, 5) == pytest.approx(0.9)
    assert recall_probability(5, 0) == 1.0
    assert recall_probability(5, 20) < recall_probability(5, 10) < 0.9


def test_initial_state_by_difficulty(repo):
    for diff in ("Easy", "Medium", "Hard"):
        log = _solved(repo, f"P {diff}", difficulty=diff)
        assert log.stability == INITIAL_STABILITY[diff]
        assert log.difficulty_fsrs == INITIAL_DIFFICULTY[diff]
        assert log.review_stage == 0 and log.lapses == 0
        assert log.next_review_at - log.completed_at == timedelta(days=INITIAL_STABILITY[diff])
    repo.mark_task_completed(log.id, False)
    assert log.stability is None and log.next_review_at is None and log.review_stage is None


def test_good_on_time_grows_about_2_5x():
    s, d, r = next_memory_state(1.5, 5, 1.5, "good")
    assert r == pytest.approx(0.9)
    assert 2.3 <= s / 1.5 <= 2.7 and d == 5


def test_grade_monotonicity():
    states = {g: next_memory_state(10, 5, 10, g) for g in ("again", "hard", "good", "easy")}
    s = {g: v[0] for g, v in states.items()}
    assert s["again"] < 10 < s["hard"] < s["good"] < s["easy"]
    assert s["easy"] == pytest.approx(s["good"] * 1.3)
    assert states["again"][1] == 6 and states["hard"][1] == 5.5 and states["easy"][1] == 4.5
    intervals = [pick_interval_days(s[g], {}, seed=7) for g in ("again", "hard", "good", "easy")]
    assert intervals == sorted(intervals) and len(set(intervals)) == 4


def test_grade_monotonicity_through_repository(repo):
    start = NOW_UTC - timedelta(days=10)
    gaps = {}
    for g in ("again", "hard", "good", "easy"):
        log = _solved(repo, f"Mono {g}", stability=10.0, difficulty_fsrs=5.0, last_review_at=start,
                      next_review_at=NOW_UTC, review_stage=1)
        repo.record_review(log, g, now=NOW_UTC)
        gaps[g] = log.next_review_at - NOW_UTC
        assert log.review_stage == 2
    assert gaps["again"] < gaps["hard"] < gaps["good"] < gaps["easy"]


def test_clamps():
    assert next_memory_state(0.3, 5, 1, "again")[0] == S_MIN
    assert next_memory_state(0.01, 5, 1, "again")[0] == S_MIN
    assert next_memory_state(300, 1, 3000, "easy")[0] == S_MAX
    assert next_memory_state(5, 9.8, 5, "again")[1] == 10
    assert next_memory_state(5, 1.2, 5, "easy")[1] == 1
    # Reviewing early never shrinks stability on a pass
    assert next_memory_state(5, 5, 0, "hard")[0] >= 5


def test_again_counts_a_lapse_and_comes_back_soon(repo):
    log = _solved(repo, stability=10.0, last_review_at=NOW_UTC - timedelta(days=10), next_review_at=NOW_UTC)
    repo.record_review(log, "again", now=NOW_UTC)
    assert log.lapses == 1 and log.stability < 2
    assert timedelta(days=1) <= log.next_review_at - NOW_UTC <= timedelta(days=2)


def test_graduation(repo):
    log = _solved(repo, stability=150.0, difficulty_fsrs=3.0, last_review_at=NOW_UTC - timedelta(days=150),
                  next_review_at=NOW_UTC)
    repo.record_review(log, "good", now=NOW_UTC)
    assert log.stability > GRADUATE_AFTER and log.next_review_at is None
    assert log not in repo.get_due_reviews(now=NOW_UTC + timedelta(days=400))


def test_load_levelling_picks_least_loaded_day():
    assert pick_interval_days(10, {9: 5, 10: 3, 11: 0}) == 11
    assert pick_interval_days(10, {9: 0, 10: 3, 11: 1}) == 9
    assert pick_interval_days(10, {}, seed=0) in (9, 10, 11)
    assert pick_interval_days(0.4, {}) == 1  # never sooner than tomorrow


def test_load_levelling_in_repository(repo):
    # S=4, D=5 reviewed on time with 'good' -> S' ~ 8.9 -> candidate days 8, 9, 10
    for i, offset in enumerate((8, 8, 9, 9)):
        _solved(repo, f"Busy {i}", stability=5.0, last_review_at=NOW_UTC,
                next_review_at=NOW_UTC + timedelta(days=offset))
    log = _solved(repo, "Target", stability=4.0, difficulty_fsrs=5.0, last_review_at=NOW_UTC - timedelta(days=4),
                  next_review_at=NOW_UTC)
    repo.record_review(log, "good", now=NOW_UTC)
    assert 8.5 < log.stability < 9.3
    assert log.next_review_at - NOW_UTC == timedelta(days=10)


def test_legacy_backfill(repo):
    log = repo.log_notification("leetcode", "Legacy", None, slug="legacy", difficulty="Hard")
    log.is_completed = True
    log.completed_at = NOW_UTC - timedelta(days=20)
    log.review_stage = 2  # old ladder: next interval was 7 days
    log.next_review_at = NOW_UTC - timedelta(days=1)
    repo.db.commit()
    assert log.stability is None
    due = repo.get_due_reviews(now=NOW_UTC)
    assert [l.id for l in due] == [log.id]
    assert log.stability == 7.0 and log.difficulty_fsrs == INITIAL_DIFFICULTY["Hard"] and log.lapses == 0
    assert log.last_review_at == log.next_review_at - timedelta(days=7)


def test_reviews_endpoint_sorted_by_recall_with_upcoming(client):
    db = SessionLocal()
    repo = NotificationRepository(db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fresh = _solved(repo, "Fresh", stability=10.0, last_review_at=now - timedelta(days=11),
                    next_review_at=now - timedelta(days=1))
    stale = _solved(repo, "Stale", stability=2.0, last_review_at=now - timedelta(days=12),
                    next_review_at=now - timedelta(days=10))
    _solved(repo, "Later", stability=5.0, last_review_at=now, next_review_at=now + timedelta(days=3))
    ids = (fresh.id, stale.id)
    db.close()

    body = client.get("/api/reviews").get_json()
    assert [r["id"] for r in body["data"]] == [ids[1], ids[0]]  # lowest recall first
    assert body["data"][0]["recall"] < body["data"][1]["recall"] < 0.9
    assert body["data"][0]["stability_days"] == 2.0
    assert body["due_count"] == 2
    assert len(body["upcoming"]) == 7 and body["week_count"] == 1


def test_review_endpoint_grades_and_legacy_mapping(client):
    db = SessionLocal()
    repo = NotificationRepository(db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    logs = [_solved(repo, f"G{i}", stability=10.0, last_review_at=now - timedelta(days=10),
                    next_review_at=now) for i in range(5)]
    ids = [l.id for l in logs]
    db.close()

    legacy_hard = client.post(f"/api/reviews/{ids[0]}", json={"result": "hard"}).get_json()["data"]
    assert legacy_hard["grade"] == "again" and legacy_hard["lapses"] == 1
    legacy_easy = client.post(f"/api/reviews/{ids[1]}", json={"result": "easy"}).get_json()["data"]
    assert legacy_easy["grade"] == "good"
    easy = client.post(f"/api/reviews/{ids[2]}", json={"grade": "easy"}).get_json()["data"]
    assert easy["grade"] == "easy" and easy["stability"] > legacy_easy["stability"]
    assert easy["recall"] == pytest.approx(0.9, abs=0.01) and easy["next_review_at"] and easy["interval_days"] >= 1
    assert client.post(f"/api/reviews/{ids[3]}", json={}).get_json()["data"]["grade"] == "good"
    assert client.post(f"/api/reviews/{ids[4]}", json={"grade": "meh"}).status_code == 400
    assert client.post(f"/api/reviews/{ids[4]}", json={"result": "meh"}).status_code == 400
    assert client.post("/api/reviews/999999", json={"grade": "good"}).status_code == 404


# ---------------- Focus sessions ----------------
@pytest.fixture
def focus_client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(focus_bp)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(focus_mod, "now_ist", lambda: FIXED_NOW)
    yield app.test_client()
    db = SessionLocal()
    db.query(FocusSession).delete()
    db.commit()
    db.close()


def test_focus_create_and_list(focus_client):
    started = datetime.combine(TODAY, time(8, 0), tzinfo=IST).isoformat()
    res = focus_client.post("/api/focus", json={"minutes": 25, "completed": True, "label": "  DP  ", "started_at": started})
    assert res.status_code == 200
    assert res.get_json()["data"]["label"] == "DP" and res.get_json()["data"]["date"] == TODAY.isoformat()
    yday = datetime.combine(TODAY - timedelta(days=1), time(20, 0), tzinfo=IST).isoformat()
    focus_client.post("/api/focus", json={"minutes": 12, "completed": False, "started_at": yday})
    focus_client.post("/api/focus", json={"minutes": 50, "started_at": started})

    body = focus_client.get("/api/focus?days=7").get_json()
    assert body["today_minutes"] == 75 and body["today_sessions"] == 2
    assert len(body["per_day"]) == 7 and body["per_day"][-1] == {"date": TODAY.isoformat(), "minutes": 75}
    assert body["per_day"][-2]["minutes"] == 12
    assert len(body["data"]) == 3 and body["total_minutes"] == 87
    assert focus_client.get("/api/focus?days=1").get_json()["total_minutes"] == 75


def test_focus_validation(focus_client):
    for bad in ({}, {"minutes": 0}, {"minutes": 601}, {"minutes": "abc"}):
        assert focus_client.post("/api/focus", json=bad).status_code == 400
    assert focus_client.get("/api/focus?days=x").status_code == 400


# ---------------- Streaks, freezes, rest days, goal ----------------
def _days(*offsets):
    return {TODAY - timedelta(days=o) for o in offsets}


def test_streak_plain():
    assert compute_streak(set(), set(), TODAY)["streak"] == 0
    r = compute_streak(_days(0, 1, 2), set(), TODAY)
    assert r["streak"] == 3 and r["best_streak"] == 3 and r["freezes_available"] == 0
    # Today not done yet: streak from yesterday is kept
    assert compute_streak(_days(1, 2), set(), TODAY)["streak"] == 2
    # A miss without a freeze breaks it
    r = compute_streak(_days(0, 2, 3), set(), TODAY)
    assert r["streak"] == 1 and r["best_streak"] == 2 and r["frozen_days"] == []


def test_freeze_earned_then_consumed():
    active = _days(*range(2, 9)) | _days(0)  # 7 active days, a miss yesterday... (offset 1), active today
    r = compute_streak(active, set(), TODAY)
    assert r["frozen_days"] == [(TODAY - timedelta(days=1)).isoformat()]
    assert r["streak"] == 8 and r["freezes_available"] == 0


def test_freezes_cap_at_two_and_run_out():
    active = _days(*range(3, 3 + 21))  # 21 active days -> 3 earned, capped at 2
    assert compute_streak(active | _days(2, 1, 0), set(), TODAY)["freezes_available"] == 2
    r = compute_streak(active, set(), TODAY)  # missed offsets 2 and 1, today pending
    assert r["freezes_available"] == 0 and r["streak"] == 21 and len(r["frozen_days"]) == 2
    r = compute_streak(_days(*range(4, 4 + 21)), set(), TODAY)  # three misses: third breaks it
    assert r["streak"] == 0 and r["best_streak"] == 21 and len(r["frozen_days"]) == 2


def test_rest_days_neither_break_nor_extend():
    rest = _days(1)
    r = compute_streak(_days(0, 2, 3), rest, TODAY)
    assert r["streak"] == 3 and r["frozen_days"] == []
    # Active on a rest day still counts
    assert compute_streak(_days(0, 1, 2), rest, TODAY)["streak"] == 3


def test_suggested_goal():
    steady = {TODAY - timedelta(days=i): 3 for i in range(1, 22)}
    assert suggest_goal(steady, TODAY, 2) == 3
    assert suggest_goal({d: 12 for d in steady}, TODAY, 2) == 6  # clamped
    assert suggest_goal({}, TODAY, 4) == 4  # no history -> current goal
    sparse = {TODAY - timedelta(days=i): (2 if i % 2 else 0) for i in range(1, 22)}
    assert suggest_goal(sparse, TODAY, 3) == 1  # many zero days -> lower floor of 1
    # Recent days dominate: last week 5/day, the two before it 1/day
    recent = {TODAY - timedelta(days=i): (5 if i <= 7 else 1) for i in range(1, 22)}
    assert suggest_goal(recent, TODAY, 2) in (1, 5)
    assert suggest_goal(recent, TODAY, 2) == suggest_goal(dict(recent), TODAY, 2)  # deterministic
    # Rest days are ignored
    with_exam = dict(steady)
    with_exam[TODAY - timedelta(days=1)] = 0
    assert suggest_goal(with_exam, TODAY, 2, rest_days={TODAY - timedelta(days=1)}) == 3


def test_stats_endpoint_freezes_focus_and_goal(client, monkeypatch):
    monkeypatch.setattr(app_mod, "now_ist", lambda: FIXED_NOW)
    monkeypatch.setattr(focus_mod, "theory_exam_days", lambda db: set())
    db = SessionLocal()
    repo = NotificationRepository(db)
    for off in list(range(2, 9)) + [0]:  # earns a freeze, misses yesterday, solved today
        log = repo.log_notification("leetcode", f"S{off}", None, slug=f"s{off}")
        log.is_completed = True
        log.completed_at = _utc_noon(TODAY - timedelta(days=off))
    db.add(FocusSession(started_at=_utc_noon(TODAY), minutes=25, completed=True))
    db.commit()
    db.close()
    try:
        data = client.get("/api/stats").get_json()["data"]
        yday = (TODAY - timedelta(days=1)).isoformat()
        assert data["streak"] == 8 and data["frozen_days"] == [yday] and data["freezes_available"] == 0
        assert data["best_streak"] == 8 and isinstance(data["rest_days"], list)
        assert data["today"]["focus_minutes"] == 25 and data["focus_minutes_today"] == 25
        assert 1 <= data["suggested_goal"] <= 6
        cells = {c["date"]: c for c in data["heatmap"]}
        assert cells[yday]["frozen"] is True and cells[TODAY.isoformat()]["focus"] == 25
        assert set(cells[yday]) >= {"date", "count", "focus", "frozen", "rest"}
    finally:
        db = SessionLocal()
        db.query(FocusSession).delete()
        db.commit()
        db.close()


def test_stats_exam_days_are_rest_days(client, monkeypatch):
    from api.domain.syllabus import Subject
    monkeypatch.setattr(app_mod, "now_ist", lambda: FIXED_NOW)
    db = SessionLocal()
    repo = NotificationRepository(db)
    for off in (0, 2, 3):
        log = repo.log_notification("leetcode", f"R{off}", None, slug=f"r{off}")
        log.is_completed = True
        log.completed_at = _utc_noon(TODAY - timedelta(days=off))
    exam = Subject(name="Deep Learning (test)", kind="theory", exam_date=TODAY - timedelta(days=1))
    lab = Subject(name="DL Lab (test)", kind="lab", exam_date=TODAY - timedelta(days=5))
    db.add_all([exam, lab])
    db.commit()
    ids = (exam.id, lab.id)
    db.close()
    try:
        data = client.get("/api/stats").get_json()["data"]
        yday = (TODAY - timedelta(days=1)).isoformat()
        assert yday in data["rest_days"] and (TODAY - timedelta(days=5)).isoformat() not in data["rest_days"]
        assert data["streak"] == 3 and data["frozen_days"] == []
        assert {c["date"]: c for c in data["heatmap"]}[yday]["rest"] is True
    finally:
        db = SessionLocal()
        db.query(Subject).filter(Subject.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        db.close()
