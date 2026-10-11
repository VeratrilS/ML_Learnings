import json
import random
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from api.core.db import Base, engine, SessionLocal
from api.domain import oa as oa_mod
from api.domain.models import NotificationLog, Settings
from api.domain.oa import OAAttempt, oa_bp
from api.domain.problem_bank import PROBLEMS


def _cf_problem(cid, index, rating, tags=("greedy",)):
    return {"key": f"{cid}/{index}", "contest_id": cid, "index": index, "name": f"P{cid}{index}",
            "rating": rating, "tags": list(tags), "solved_count": 5000,
            "url": f"https://codeforces.com/problemset/problem/{cid}/{index}"}


CF_SET = [_cf_problem(1500 + i, idx, r) for i, (idx, r) in enumerate(
    [(x, r) for r in range(800, 2100, 100) for x in ("A", "B", "C")])]


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(oa_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def state():
    """Mutable fake platform state the monkeypatched integrations read from."""
    return {"lc_ac": [], "cf_solved": {}, "cf_attempted": set(), "lc_calls": 0}


@pytest.fixture
def client(app, monkeypatch, state):
    def lc_recent(username, limit=20):
        state["lc_calls"] += 1
        return list(state["lc_ac"])

    monkeypatch.setattr(oa_mod.integrations, "leetcode_recent_accepted", lc_recent)
    monkeypatch.setattr(oa_mod.integrations, "cf_problemset", lambda: CF_SET)
    monkeypatch.setattr(oa_mod.integrations, "cf_user_submissions",
                        lambda handle: (dict(state["cf_solved"]), set(state["cf_attempted"])))
    monkeypatch.setattr(oa_mod, "_topic_weights", lambda db: {})
    monkeypatch.setattr(oa_mod, "_new_seed", lambda: 42)
    yield app.test_client()
    db = SessionLocal()
    db.query(OAAttempt).delete()
    db.query(NotificationLog).filter(NotificationLog.title.like("oa-test%")).delete(synchronize_session=False)
    db.query(Settings).filter(Settings.key.in_(["oa_cf_theta", "insights_cf_rating"])).delete(synchronize_session=False)
    db.commit()
    db.close()


def _start(client, **body):
    res = client.post("/api/oa/start", json=body)
    assert res.status_code == 200, res.get_json()
    return res.get_json()


def _shift_start(attempt_id, minutes_ago):
    """Pretend the attempt started `minutes_ago` minutes ago; returns the new started_at."""
    db = SessionLocal()
    a = db.get(OAAttempt, attempt_id)
    a.started_at = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0) - timedelta(minutes=minutes_ago)
    db.commit()
    started = a.started_at
    db.close()
    return started


def _mark_sent(slugs):
    db = SessionLocal()
    for s in slugs:
        db.add(NotificationLog(task_type="leetcode", title=f"oa-test {s}", slug=s, status="success"))
    db.commit()
    db.close()


# ---------------- presets ----------------
def test_lc_classic_composition(client):
    a = _start(client, preset="lc-classic")["data"]
    assert a["platform"] == "leetcode" and a["status"] == "active"
    assert [p["difficulty"] for p in a["problems"]] == ["Medium", "Medium", "Hard"]
    assert a["duration_min"] == 90
    assert len({p["slug"] for p in a["problems"]}) == 3
    assert len({p["topic"] for p in a["problems"]}) == 3  # topics are mixed
    for p in a["problems"]:
        assert p["url"] == f"https://leetcode.com/problems/{p['slug']}/"
        assert p["id"] == p["slug"]
    assert a["max_score"] == 700


def test_lc_classic_60_minutes_and_quick(client):
    a = _start(client, preset="lc-classic", duration_min=60)["data"]
    assert a["duration_min"] == 60
    client.post(f"/api/oa/{a['id']}/abandon")
    q = _start(client, preset="lc-quick")["data"]
    assert [p["difficulty"] for p in q["problems"]] == ["Easy", "Medium"]
    assert q["duration_min"] == 45


def test_cf_div2_targets_from_theta(client):
    db = SessionLocal()
    db.add(Settings(key="insights_cf_rating", value="1437"))
    db.commit()
    db.close()
    a = _start(client, preset="cf-div2")["data"]
    assert a["platform"] == "codeforces"
    assert [p["rating"] for p in a["problems"]] == [1400, 1600, 1800]
    assert a["duration_min"] == 90
    assert all(p["id"] == p["key"] for p in a["problems"])


def test_cf_default_theta_and_excludes_attempted(client, state):
    state["cf_attempted"] = {p["key"] for p in CF_SET if p["rating"] == 1200 and p["index"] != "C"}
    a = _start(client, preset="cf-div2")["data"]
    ratings = [p["rating"] for p in a["problems"]]
    assert ratings == [1200, 1400, 1600]
    assert a["problems"][0]["key"].endswith("/C")


def test_custom_validation(client):
    assert client.post("/api/oa/start", json={"preset": "nope"}).status_code == 400
    assert client.post("/api/oa/start", json={"preset": "custom", "platform": "leetcode",
                                              "difficulties": ["Insane"]}).status_code == 400
    assert client.post("/api/oa/start", json={"preset": "custom", "platform": "codeforces",
                                              "ratings": [100]}).status_code == 400
    assert client.post("/api/oa/start", json={"preset": "lc-quick", "duration_min": 1}).status_code == 400
    a = _start(client, preset="custom", platform="leetcode", difficulties=["Hard", "Hard"], duration_min=75)["data"]
    assert [p["difficulty"] for p in a["problems"]] == ["Hard", "Hard"]
    assert a["duration_min"] == 75


# ---------------- no repeats ----------------
def test_never_picks_sent_or_recently_solved(client, state):
    hards = [p for p in PROBLEMS if p[2] == "Hard"]
    keep = hards[-1]
    _mark_sent([p[1] for p in hards[:-2]])
    state["lc_ac"] = [{"slug": hards[-2][1], "title": hards[-2][0], "solved_at": datetime(2026, 1, 1)}]
    a = _start(client, preset="custom", platform="leetcode", difficulties=["Hard"])["data"]
    assert a["problems"][0]["slug"] == keep[1]
    assert a["problems"][0]["seen_before"] is False


def test_does_not_repeat_previous_oa_problems(client):
    seen = set()
    for _ in range(4):
        a = _start(client, preset="lc-classic")["data"]
        slugs = {p["slug"] for p in a["problems"]}
        assert not (slugs & seen)
        seen |= slugs
        client.post(f"/api/oa/{a['id']}/abandon")


def test_pick_is_seeded():
    one = oa_mod.pick_leetcode(["Medium", "Hard"], set(), random.Random(7))
    two = oa_mod.pick_leetcode(["Medium", "Hard"], set(), random.Random(7))
    assert one == two


def test_topic_weights_bias(client):
    weights = {"Graphs": 1.0}
    picks = [oa_mod.pick_leetcode(["Medium"], set(), random.Random(s), weights)[0]["topic"] for s in range(30)]
    assert picks.count("Graphs") >= 25


# ---------------- single active attempt ----------------
def test_single_active_attempt(client):
    first = _start(client, preset="lc-classic")
    assert first["resumed"] is False
    second = _start(client, preset="lc-quick")
    assert second["resumed"] is True
    assert second["data"]["id"] == first["data"]["id"]
    db = SessionLocal()
    assert db.query(OAAttempt).filter(OAAttempt.status == "active").count() == 1
    db.close()
    overview = client.get("/api/oa").get_json()["data"]
    assert overview["active"]["id"] == first["data"]["id"]


def test_abandon_frees_slot(client):
    a = _start(client, preset="lc-quick")["data"]
    res = client.post(f"/api/oa/{a['id']}/abandon").get_json()
    assert res["data"]["status"] == "abandoned"
    assert client.post(f"/api/oa/{a['id']}/abandon").status_code == 409
    assert client.post(f"/api/oa/{a['id']}/finish", json={}).status_code == 409
    b = _start(client, preset="lc-quick")
    assert b["resumed"] is False and b["data"]["id"] != a["id"]
    assert client.get("/api/oa").get_json()["data"]["stats"]["abandoned"] == 1


def test_missing_attempt_404(client):
    assert client.post("/api/oa/99999/finish", json={}).status_code == 404
    assert client.post("/api/oa/99999/abandon").status_code == 404


# ---------------- auto-verify ----------------
def test_verify_window_bounds():
    start = datetime(2026, 10, 11, 10, 0)
    lo, hi = oa_mod.verify_window(start, 90)
    assert lo == start and hi == start + timedelta(minutes=95)


def test_leetcode_auto_verify_window(client, state):
    a = _start(client, preset="lc-classic")["data"]
    started = _shift_start(a["id"], 100)
    m1, m2, h = [p["slug"] for p in a["problems"]]
    state["lc_ac"] = [
        {"slug": m1, "title": m1, "solved_at": started + timedelta(minutes=20)},   # inside
        {"slug": m2, "title": m2, "solved_at": started - timedelta(minutes=1)},    # before start: ignored
        {"slug": h, "title": h, "solved_at": started + timedelta(minutes=96)},     # after grace: ignored
        {"slug": "two-sum", "title": "Two Sum", "solved_at": started + timedelta(minutes=5)},  # not in set
    ]
    res = client.post(f"/api/oa/{a['id']}/finish", json={"results": {m1: "unsolved", m2: "partial"}}).get_json()
    d = res["data"]
    assert res["verified"] == [m1]
    assert d["results"] == {m1: "solved", m2: "partial", h: "unsolved"}  # verified beats self-report
    assert d["auto_verified"] is True and d["status"] == "finished"
    flags = {p["slug"]: p["verified"] for p in d["problems"]}
    assert flags == {m1: True, m2: False, h: False}
    assert next(p for p in d["problems"] if p["slug"] == m1)["solved_in_min"] == 20
    assert d["score"] == 200 + 80


def test_leetcode_grace_edge_counts(client, state):
    a = _start(client, preset="lc-quick")["data"]
    started = _shift_start(a["id"], 60)
    e = a["problems"][0]["slug"]
    state["lc_ac"] = [{"slug": e, "title": e, "solved_at": started + timedelta(minutes=50)}]  # 45 + 5 exactly
    d = client.post(f"/api/oa/{a['id']}/finish", json={}).get_json()["data"]
    assert d["results"][e] == "solved"


def test_codeforces_auto_verify(client, state):
    a = _start(client, preset="cf-div2")["data"]
    started = _shift_start(a["id"], 30)
    k1, k2, k3 = [p["key"] for p in a["problems"]]
    state["cf_solved"] = {k1: started + timedelta(minutes=10), k2: started - timedelta(days=3)}
    res = client.post(f"/api/oa/{a['id']}/finish", json={"results": {k3: "solved"}}).get_json()
    d = res["data"]
    assert res["verified"] == [k1]
    assert d["results"] == {k1: "solved", k2: "unsolved", k3: "solved"}
    r = {p["key"]: p["rating"] for p in d["problems"]}
    assert d["score"] == round(r[k1] / 5) + round(r[k3] / 5)


def test_verify_network_failure_falls_back_to_self_report(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")
    a = _start(client, preset="lc-quick")["data"]
    monkeypatch.setattr(oa_mod.integrations, "leetcode_recent_accepted", boom)
    e, m = [p["slug"] for p in a["problems"]]
    res = client.post(f"/api/oa/{a['id']}/finish", json={"results": {e: "solved", m: "bogus"}}).get_json()
    assert res["status"] == "success"
    assert "down" in res["verify_error"]
    assert res["data"]["results"] == {e: "solved", m: "unsolved"}
    assert res["data"]["auto_verified"] is False
    assert res["data"]["score"] == 100


# ---------------- scoring ----------------
def test_scoring():
    lc = [{"id": "a", "difficulty": "Easy"}, {"id": "b", "difficulty": "Medium"}, {"id": "c", "difficulty": "Hard"}]
    assert oa_mod.score_attempt(lc, {"a": "solved", "b": "solved", "c": "solved"}) == (600, 600)
    assert oa_mod.score_attempt(lc, {"a": "solved", "b": "partial", "c": "unsolved"}) == (180, 600)
    assert oa_mod.score_attempt(lc, {"c": "partial"}) == (120, 600)
    cf = [{"id": "1/A", "rating": 1200}, {"id": "1/B", "rating": 1600}]
    assert oa_mod.score_attempt(cf, {"1/A": "solved", "1/B": "partial"}) == (240 + 128, 560)


# ---------------- stats ----------------
def test_stats_and_history(client, state):
    a = _start(client, preset="lc-quick")["data"]
    e, m = [p["slug"] for p in a["problems"]]
    client.post(f"/api/oa/{a['id']}/finish", json={"results": {e: "solved", m: "partial"}})
    b = _start(client, preset="lc-quick")["data"]
    e2, m2 = [p["slug"] for p in b["problems"]]
    client.post(f"/api/oa/{b['id']}/finish", json={"results": {e2: "solved", m2: "solved"}})
    c = _start(client, preset="lc-classic")["data"]
    client.post(f"/api/oa/{c['id']}/abandon")

    data = client.get("/api/oa").get_json()["data"]
    assert data["active"] is None
    assert [h["id"] for h in data["history"]][:3] == [c["id"], b["id"], a["id"]] or \
        {h["id"] for h in data["history"]} == {a["id"], b["id"], c["id"]}
    s = data["stats"]
    assert s["attempts"] == 2 and s["abandoned"] == 1
    assert s["avg_score"] == round((180 + 300) / 2)
    assert s["problems"] == 4 and s["solved"] == 3
    assert s["solve_rate"] == 0.75
    assert s["avg_pct"] == round((60 + 100) / 2)
    assert s["by_difficulty"]["Medium"] == {"attempted": 2, "solved": 1}
    assert sum(t["attempted"] for t in s["by_topic"]) == 4
    keys = {p["key"] for p in data["presets"]}
    assert keys == {"lc-classic", "lc-quick", "cf-div2", "custom"}
    cf = next(p for p in data["presets"] if p["key"] == "cf-div2")
    assert cf["mix"] == [1200, 1400, 1600]
