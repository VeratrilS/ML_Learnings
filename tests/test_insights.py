import random
import time
from datetime import date, datetime, timedelta

import pytest
from flask import Flask

from api.core.config import IST
from api.core.db import Base, SessionLocal, engine
from api.domain import insights as ins
from api.domain.models import NotificationLog, Settings
from api.domain.syllabus import Subject, SyllabusTopic

FIXED_NOW = datetime(2026, 10, 11, 9, 30, tzinfo=IST)
TODAY = FIXED_NOW.date()


# ---------------- forgetting curve ----------------
def test_recall_formula():
    assert ins.recall(0, 6) == 1.0
    assert ins.recall(54, 6) == pytest.approx(0.5)  # dt = 9S -> R = 1/2
    assert ins.recall(10, 2) < ins.recall(10, 6) < ins.recall(10, 15)
    assert ins.recall(5, None) == 0.0


def test_stability_and_topic_recall():
    assert ins.stability(1) == 2 and ins.stability(2) == 6 and ins.stability(3) == 15
    assert ins.stability(3, done=True) == pytest.approx(22.5)
    assert ins.stability(None) is None
    d0 = date(2026, 10, 1)
    assert ins.topic_recall(3, True, None, d0) == 0.0  # never studied
    later = ins.topic_recall(2, False, d0, d0 + timedelta(days=20))
    sooner = ins.topic_recall(2, False, d0, d0 + timedelta(days=2))
    assert 0 < later < sooner <= 1


def test_topic_work():
    assert ins.topic_work(None, False) == pytest.approx(1.0)
    assert ins.topic_work(3, False) == pytest.approx(1 / 3)
    assert ins.topic_work(1, True) == pytest.approx(0.3)
    assert ins.topic_work(3, True) == 0.0


# ---------------- allocator ----------------
def test_edf_feasible_and_shortfall():
    ok, short = ins.edf_feasibility([(10, 5.0), (20, 10.0)], 3)
    assert ok and short == 0
    # exam in 3 days -> 2 study days * 2h = 4h of capacity, 10h of work
    ok, short = ins.edf_feasibility([(3, 10.0)], 2)
    assert not ok and short == pytest.approx(6.0)
    # order matters: the late exam's work counts only against its own (larger) window
    ok, short = ins.edf_feasibility([(30, 20.0), (2, 1.0)], 1)
    assert ok


def test_split_hours_proportional_and_capped():
    out = ins.split_hours([("a", 2.0, 10.0), ("b", 1.0, 10.0)], 3.0)
    assert out["a"] == pytest.approx(2.0) and out["b"] == pytest.approx(1.0)
    out = ins.split_hours([("a", 5.0, 0.5), ("b", 1.0, 10.0)], 3.0)
    assert out["a"] == pytest.approx(0.5) and out["b"] == pytest.approx(2.5)
    assert sum(ins.split_hours([("a", 0.0, 0.0)], 3.0).values()) == 0


def test_dsa_floor_tapers():
    assert ins.dsa_hours(None, 3) == 0.5
    assert ins.dsa_hours(10, 3) == 0.5
    assert ins.dsa_hours(2, 3) < 0.5
    assert ins.dsa_hours(0, 3) == 0


def test_pick_study_next_greedy_budget():
    cands = [{"topic_id": i, "title": f"T{i}", "unit": None, "gain": g, "minutes": 60, "position": i}
             for i, g in enumerate([1.0, 3.0, 2.0])]
    out = ins.pick_study_next(cands, minutes_budget=90)
    assert [t["topic_id"] for t in out] == [1, 2]
    assert sum(t["minutes"] for t in out) == 90


# ---------------- Monte Carlo ----------------
def test_monte_carlo_deterministic_and_bounded():
    samples = [0, 1, 2, 3, 1, 0, 2]
    a = ins.monte_carlo_finish(20, samples, 15, seed="2026-10-11:1")
    b = ins.monte_carlo_finish(20, samples, 15, seed="2026-10-11:1")
    assert a == b
    assert 0.0 <= a["p_finish"] <= 1.0
    assert a["p50_days"] <= a["p90_days"]
    # more time -> at least as likely to finish
    c = ins.monte_carlo_finish(20, samples, 40, seed="2026-10-11:1")
    assert c["p_finish"] >= a["p_finish"]
    assert ins.monte_carlo_finish(0, samples, 5, seed="x")["p_finish"] == 1.0
    assert ins.monte_carlo_finish(5, [0] * 10, 5, seed="x")["p_finish"] == 0.0


def test_monte_carlo_prior_when_little_history():
    out = ins.monte_carlo_finish(15, [2, 1], 30, seed="s")
    assert out["prior"] is True
    assert out["p_finish"] > 0.9  # Poisson(1.5)/day finishes 15 topics well within 30 days


def test_monte_carlo_is_fast():
    start = time.perf_counter()
    ins.monte_carlo_finish(60, [0, 1, 2, 3, 0, 1, 4, 2, 0, 1], 30, seed="speed")
    ins.monte_carlo_finish(120, [0, 0, 0, 0, 0, 1], 30, seed="slow")  # runs to the horizon
    assert time.perf_counter() - start < 0.3


def test_throughput_and_burndown():
    d = [TODAY, TODAY, TODAY - timedelta(days=2), None]
    s = ins.throughput_samples(d, TODAY, TODAY - timedelta(days=40))
    assert len(s) == 21 and s[-1] == 2 and s[-3] == 1 and sum(s) == 3
    assert len(ins.throughput_samples(d, TODAY, TODAY - timedelta(days=2))) == 3
    bd = ins.burndown_series(10, d, TODAY)
    assert len(bd) == 21 and bd[-1]["remaining"] == 6 and bd[0]["remaining"] == 9
    assert bd[-1]["date"] == TODAY.isoformat()


# ---------------- Elo / MLE ----------------
def test_elo_update_direction():
    assert ins.elo_step(1600, 1650, 1.0, 0) > 0
    assert ins.elo_step(1600, 1650, 0.0, 0) < 0
    assert abs(ins.elo_step(1600, 1650, 1.0, 9)) < abs(ins.elo_step(1600, 1650, 1.0, 0))  # K decays
    st = ins.topic_elo([("Graphs", 1650, 0.0)] * 3 + [("Arrays", 1300, 1.0)] * 3, 1650)
    assert st["Graphs"]["delta"] < 0 < st["Arrays"]["delta"]
    assert st["Graphs"]["n"] == 3


def test_shrinkage():
    assert ins.shrink(100, 0) == 0
    assert ins.shrink(100, 1) < ins.shrink(100, 5) < ins.shrink(100, 50) < 100


def test_lc_outcome():
    t0 = datetime(2026, 10, 1)
    now = datetime(2026, 10, 11)
    assert ins.lc_outcome(t0, t0 + timedelta(hours=5), True, now) == 1.0
    assert ins.lc_outcome(t0, t0 + timedelta(days=5), True, now) == 0.5
    assert ins.lc_outcome(t0, t0 + timedelta(hours=5), True, now, hard_review=True) == 0.3
    assert ins.lc_outcome(t0, None, False, now) == 0.0
    assert ins.lc_outcome(now - timedelta(days=1), None, False, now) is None


def test_mle_recovers_known_theta():
    true = 1500
    rng = random.Random(7)
    obs = []
    for _ in range(3000):
        r = rng.randrange(800, 2400, 100)
        obs.append((r, 1.0 if rng.random() < ins.p_solve(true, r) else 0.0))
    assert ins.fit_rating(obs) == pytest.approx(true, abs=40)
    # expected-value data: essentially exact
    obs = [(r, ins.p_solve(1700, r)) for r in range(800, 2600, 50)] * 50
    assert ins.fit_rating(obs) == pytest.approx(1700, abs=5)


def test_mle_prior_and_tag_shrinkage():
    assert ins.fit_rating([]) == pytest.approx(1200)
    one_win = ins.fit_rating([(1600, 1.0)])
    assert 1200 < one_win < 1600
    # a tag with one failure is pulled less far from the global rating under the tighter prior
    loose = ins.fit_rating([(1000, 0.0)], prior_mu=1500, prior_sigma=300)
    tight = ins.fit_rating([(1000, 0.0)], prior_mu=1500, prior_sigma=150)
    assert loose < tight < 1500


def test_cf_suggested_range():
    assert ins.cf_suggested_range(1200) == (1200, 1400)
    assert ins.cf_suggested_range(1449) == (1400, 1600)
    lo, hi = ins.cf_suggested_range(500)
    assert lo == 800 and hi > lo


def test_fit_cf():
    problems = [{"key": "1/A", "rating": 800, "tags": ["math"]}, {"key": "1/B", "rating": 1400, "tags": ["dp"]},
                {"key": "1/C", "rating": 1900, "tags": ["dp", "graphs"]}, {"key": "2/A", "tags": []}]
    res = ins.fit_cf({"1/A": datetime(2026, 1, 1), "1/B": datetime(2026, 1, 2)}, {"1/A", "1/B", "1/C", "2/A"}, problems)
    assert res["n_attempted"] == 3 and res["n_solved"] == 2
    assert res["suggested_min"] < res["suggested_max"]
    assert {t["tag"] for t in res["tags"]} == {"math", "dp", "graphs"}


# ---------------- endpoints ----------------
@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(ins.insights_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setattr(ins, "now_ist", lambda: FIXED_NOW)
    ins._LC_CACHE.clear()
    ins._CF_CACHE.clear()

    def no_network(*a, **k):
        raise AssertionError("network call in tests")
    for name in ("leetcode_profile", "leetcode_recent_accepted", "cf_user_info", "cf_user_submissions", "cf_problemset"):
        monkeypatch.setattr(ins.integrations, name, no_network)
    yield app.test_client()
    db = SessionLocal()
    db.query(SyllabusTopic).delete()
    db.query(Subject).delete()
    db.query(NotificationLog).delete()
    db.query(Settings).delete()
    db.commit()
    db.close()


def _seed_subjects():
    db = SessionLocal()
    now_utc = datetime(2026, 10, 11, 3, 0)
    a = Subject(name="Next Generation Networking Systems", kind="theory", color="violet",
                exam_date=TODAY + timedelta(days=6), created_at=now_utc - timedelta(days=30))
    b = Subject(name="Deep Learning", kind="theory", color="rose", exam_date=TODAY + timedelta(days=14),
                created_at=now_utc - timedelta(days=30))
    lab = Subject(name="Deep Learning Laboratory", kind="lab", exam_date=TODAY + timedelta(days=2))
    db.add_all([a, b, lab])
    db.flush()
    for i in range(8):
        db.add(SyllabusTopic(subject_id=a.id, title=f"NGNS topic {i}", unit="Unit 1", position=i,
                             done=i < 3, done_at=now_utc - timedelta(days=i) if i < 3 else None,
                             confidence=(i % 3) + 1 if i < 5 else None,
                             last_studied_at=now_utc - timedelta(days=i + 1) if i < 5 else None))
    for i in range(5):
        db.add(SyllabusTopic(subject_id=b.id, title=f"DL topic {i}", position=i))
    db.add(SyllabusTopic(subject_id=lab.id, title="Lab exp 1", position=0))
    db.commit()
    ids = (a.id, b.id)
    db.close()
    return ids


def test_study_empty(client):
    body = client.get("/api/insights/study").get_json()
    assert body["status"] == "success"
    assert body["subjects"] == [] and body["empty_reason"]


def test_study_endpoint(client):
    a_id, b_id = _seed_subjects()
    body = client.get("/api/insights/study").get_json()
    assert body["status"] == "success"
    subs = body["subjects"]
    assert [s["id"] for s in subs] == [a_id, b_id]  # labs excluded, nearest exam first
    a = subs[0]
    assert a["short"] == "NGNS" and a["days_left"] == 6
    assert 0 < a["readiness_now"] <= 1 and a["readiness_exam"] <= a["readiness_now"]
    assert subs[1]["readiness_now"] == 0
    assert 0 <= a["p_finish"] <= 1 and a["p50_date"]
    assert len(a["burndown"]) == 21 and a["burndown"][-1]["remaining"] == 5
    assert a["study_next"] and all(t["minutes"] >= 10 for t in a["study_next"])
    plan = body["plan"]
    assert plan["hours"] == 3 and plan["dsa_hours"] == 0.5
    assert sum(s["hours_today"] for s in subs) == pytest.approx(plan["study_hours"], abs=0.02)
    assert sum(s["hours_today"] for s in subs) <= 2.5 + 1e-6
    # deterministic within a day
    assert client.get("/api/insights/study").get_json()["subjects"] == subs


def test_study_shortfall_with_few_hours(client):
    _seed_subjects()
    db = SessionLocal()
    db.add(Settings(key="daily_study_hours", value="1"))
    db.commit()
    db.close()
    plan = client.get("/api/insights/study").get_json()["plan"]
    assert plan["hours"] == 1 and plan["feasible"] is False and plan["shortfall_hours"] > 0


def test_skills_endpoint(client, monkeypatch):
    monkeypatch.setattr(ins.integrations, "leetcode_profile", lambda u: {"contest_rating": 1709})
    db = SessionLocal()
    t0 = datetime(2026, 9, 1)
    for i in range(4):  # graphs: never solved
        db.add(NotificationLog(task_type="leetcode", title=f"G{i}", status="success", difficulty="Medium",
                               topic="Graphs", timestamp=t0 + timedelta(days=i), is_completed=False))
    for i in range(4):  # arrays: solved fast
        db.add(NotificationLog(task_type="leetcode", title=f"A{i}", status="success", difficulty="Medium",
                               topic="Arrays", timestamp=t0 + timedelta(days=i), is_completed=True,
                               completed_at=t0 + timedelta(days=i, hours=3)))
    db.commit()
    db.close()
    body = client.get("/api/insights/skills").get_json()
    assert body["status"] == "success" and body["global_rating"] == 1659
    by = {t["topic"]: t for t in body["topics"]}
    assert by["Graphs"]["rating"] < 1659 < by["Arrays"]["rating"]
    assert body["topics"][0]["topic"] == "Graphs" and body["weakest"] == "Graphs"
    assert 0 < by["Graphs"]["p_solve_hard"] < by["Graphs"]["p_solve_medium"] < 1
    assert body["recommended_topic"] in by

    w = ins.topic_weights(SessionLocal())
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["Graphs"] > w["Arrays"]


def test_skills_fallback_without_profile(client):
    body = client.get("/api/insights/skills").get_json()  # profile call raises -> fallback 1500
    assert body["global_rating"] == 1500 and body["rating_source"] == "fallback"


def test_cf_endpoint(client, monkeypatch):
    problems = [{"key": f"{1800 + i}/A", "rating": 800 + 100 * (i % 10), "tags": ["greedy"] if i % 2 else ["dp"]}
                for i in range(20)]
    solved = {p["key"]: datetime(2026, 9, 1) for p in problems if p["rating"] <= 1100}
    monkeypatch.setattr(ins.integrations, "cf_user_submissions", lambda h: (solved, {p["key"] for p in problems}))
    monkeypatch.setattr(ins.integrations, "cf_problemset", lambda: problems)
    body = client.get("/api/insights/cf").get_json()
    assert body["status"] == "success" and "error" not in body
    assert body["n_attempted"] == 20 and body["n_solved"] == len(solved)
    assert 900 < body["rating"] < 1400
    assert body["suggested_min"] < body["suggested_max"]
    assert {t["tag"] for t in body["tags"]} == {"greedy", "dp"}


def test_cf_network_error(client):
    res = client.get("/api/insights/cf")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "success" and body["error"]


def test_summary(client):
    _seed_subjects()
    body = client.get("/api/insights/summary").get_json()  # must not touch the network
    assert body["status"] == "success"
    assert body["top_exam"]["short"] == "NGNS" and len(body["top_exam"]["study_next"]) <= 3
    assert len(body["subjects"]) == 2 and len(body["study_next"]) <= 3
    assert body["cf_rating"] is None and body["weakest_topic"] is None
    assert body["plan"]["hours"] == 3


def test_summary_empty(client):
    body = client.get("/api/insights/summary").get_json()
    assert body["status"] == "success" and body["top_exam"] is None and body["empty_reason"]
