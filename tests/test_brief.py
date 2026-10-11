from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from api.core.config import IST
from api.core.db import Base, engine, SessionLocal
from api.domain import brief as brief_mod
from api.domain import todos as todos_mod
from api.domain.brief import DailyBrief, brief_bp, validate_brief, fallback_brief, gather_context, KINDS
from api.domain.todos import Todo, todos_bp

FIXED_NOW = datetime(2026, 10, 11, 9, 12, tzinfo=IST)

CTX = {
    "now_ist": "09:12", "date": "2026-10-11", "weekday": "Sunday", "plan_from": "09:15",
    "stats": {"streak": 12, "best_streak": 20, "solved_today": 0, "goal": 2, "rest_day": False},
    "exams": {"plan": {"hours": 6, "dsa_hours": 1, "study_hours": 5, "feasible": True, "shortfall_hours": 0},
              "subjects": [{"id": 3, "short": "CN", "days_left": 4, "readiness_now_pct": 42, "hours_today": 2.5,
                            "p_finish_pct": 80, "study_next": [{"topic_id": 31, "title": "TCP congestion", "minutes": 40}]},
                           {"id": 4, "short": "DBMS", "days_left": 9, "readiness_now_pct": 60, "hours_today": 1.0,
                            "study_next": []}]},
    "reviews": {"due_count": 3, "top": [{"id": 7, "title": "Two Sum", "difficulty": "Easy", "recall_pct": 55}]},
    "pending_problems": {"count": 4, "top": [{"id": 11, "title": "Koko Eating Bananas", "difficulty": "Medium"}]},
    "learning": {"done_today": 0, "daily_min": 1, "streak": 3, "lessons_left": 40,
                 "next_lesson": {"id": 21, "title": "Consistent Hashing", "minutes": 28}},
    "episode": {"series_id": 1, "title": "Hajime no Ippo", "episode": 54, "watched_today": False, "finished": False},
}

AI_BRIEF = {
    "headline": "CN in 4 days. Congestion control before anything else.",
    "summary": "CN is at 42% with 2.5h planned today. 3 reviews due and 4 problems pending.",
    "blocks": [
        {"start": "09:30", "minutes": 90, "kind": "exam", "title": "CN: TCP congestion", "why": "Exam in 4 days",
         "ref": {"type": "topic", "id": 31}},
        {"start": "11:10", "minutes": 45, "kind": "dsa", "title": "Koko Eating Bananas", "why": "Goal 2",
         "ref": {"type": "problem", "id": 11}},
        {"start": "12:00", "minutes": 15, "kind": "rest", "title": "Lunch", "why": "", "ref": None},
        {"start": "14:00", "minutes": 20, "kind": "review", "title": "Revise Two Sum", "why": "3 due",
         "ref": {"type": "review", "id": 7}},
        {"start": "15:00", "minutes": 40, "kind": "video", "title": "Consistent Hashing", "why": "1/day",
         "ref": {"type": "lesson", "id": 21}},
        {"start": "21:30", "minutes": 25, "kind": "episode", "title": "Ippo Ep 54", "why": "Reward",
         "ref": {"type": "episode", "id": 1}},
    ],
    "risk": None,
    "nudge": "Hard work betrays none.",
}


class FakeLLM:
    calls = 0
    response = AI_BRIEF
    error = None
    kwargs = None

    def __init__(self, *args, **kwargs):
        FakeLLM.init_kwargs = kwargs

    def generate_json(self, contents, temperature=0.7, system=None, thinking=None):
        FakeLLM.calls += 1
        FakeLLM.kwargs = {"contents": contents, "system": system, "thinking": thinking}
        if FakeLLM.error:
            raise FakeLLM.error
        return FakeLLM.response


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(todos_bp)
    app.register_blueprint(brief_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def clock(monkeypatch):
    state = {"now": FIXED_NOW}
    monkeypatch.setattr(brief_mod, "now_ist", lambda: state["now"])
    monkeypatch.setattr(todos_mod, "now_ist", lambda: state["now"])
    return state


@pytest.fixture
def client(app, clock, monkeypatch):
    FakeLLM.calls, FakeLLM.response, FakeLLM.error = 0, AI_BRIEF, None
    monkeypatch.setattr(brief_mod, "LLMClient", FakeLLM)
    monkeypatch.setattr(brief_mod, "gather_context", lambda fetch, now=None: dict(CTX))
    yield app.test_client()
    db = SessionLocal()
    db.query(DailyBrief).delete()
    db.query(Todo).delete()
    db.commit()
    db.close()


# ---------------- caching ----------------
def test_get_is_pending_until_generated(client):
    body = client.get("/api/brief").get_json()
    assert body == {"status": "success", "data": None, "pending": True}
    assert FakeLLM.calls == 0  # GET never calls the LLM


def test_post_generates_and_caches_per_day(client, clock):
    body = client.post("/api/brief").get_json()
    assert body["status"] == "success" and body["cached"] is False
    data = body["data"]
    assert data["ai"] is True and data["day"] == "2026-10-11"
    assert data["headline"] == AI_BRIEF["headline"]
    assert [b["kind"] for b in data["blocks"]] == ["exam", "dsa", "rest", "review", "video", "episode"]
    assert data["accepted"] == []
    assert FakeLLM.calls == 1
    assert FakeLLM.kwargs["thinking"] == "low" and FakeLLM.init_kwargs == {"budget": 60}
    assert "CONTEXT" in FakeLLM.kwargs["contents"] and '"short":"CN"' in FakeLLM.kwargs["contents"]

    # GET and a plain POST both reuse today's brief
    got = client.get("/api/brief").get_json()
    assert got["pending"] is False and got["data"]["headline"] == AI_BRIEF["headline"]
    again = client.post("/api/brief").get_json()
    assert again["cached"] is True and FakeLLM.calls == 1

    # force regenerates in place
    FakeLLM.response = {**AI_BRIEF, "headline": "Round two."}
    forced = client.post("/api/brief?force=1").get_json()
    assert forced["cached"] is False and forced["data"]["headline"] == "Round two." and FakeLLM.calls == 2
    db = SessionLocal()
    assert db.query(DailyBrief).count() == 1
    db.close()

    # a new IST day starts empty
    clock["now"] = FIXED_NOW + timedelta(days=1)
    assert client.get("/api/brief").get_json()["pending"] is True


# ---------------- validation ----------------
def test_validate_clamps_and_drops_invalid_blocks():
    raw = {
        "headline": "x" * 200, "summary": "  Two   sentences.  ", "risk": "null", "nudge": "Go.",
        "blocks": [
            {"start": "07:00", "minutes": 30, "kind": "dsa", "title": "Too early (before now)"},
            {"start": "09:30", "minutes": 5, "kind": "exam", "title": "Short", "ref": {"type": "topic", "id": 31}},
            {"start": "09:20", "minutes": 30, "kind": "dsa", "title": "Out of order"},
            {"start": "10:00", "minutes": 500, "kind": "DSA", "title": "Long", "why": "w" * 200,
             "ref": {"type": "problem", "id": "999"}},
            {"start": "11:00", "minutes": 30, "kind": "party", "title": "Bad kind"},
            {"start": "25:00", "minutes": 30, "kind": "rest", "title": "Bad time"},
            {"start": "12:00", "minutes": "abc", "kind": "rest", "title": "Bad minutes"},
            {"start": "12:30", "minutes": 20, "kind": "review", "title": ""},
            {"start": "23:50", "minutes": 60, "kind": "episode", "title": "Late episode",
             "ref": {"type": "episode", "id": 1}},
            "not a block",
        ],
    }
    out = validate_brief(raw, FIXED_NOW, CTX)
    assert len(out["headline"]) <= 90 and out["headline"].endswith("…")
    assert out["summary"] == "Two sentences."
    assert out["risk"] is None
    assert [b["title"] for b in out["blocks"]] == ["Short", "Long", "Late episode"]
    short, long_, late = out["blocks"]
    assert short["minutes"] == 10 and short["ref"] == {"type": "topic", "id": 31}
    assert long_["minutes"] == 180 and long_["kind"] == "dsa" and len(long_["why"]) <= 80
    assert long_["ref"] is None  # problem 999 is not in the context
    assert late["minutes"] == 10  # clipped at midnight
    assert all(b["kind"] in KINDS for b in out["blocks"])


def test_validate_caps_blocks_and_rejects_empty():
    many = {"headline": "h", "summary": "s", "nudge": "n",
            "blocks": [{"start": f"{10 + i}:00", "minutes": 30, "kind": "plan", "title": f"B{i}"} for i in range(12)]}
    assert len(validate_brief(many, FIXED_NOW)["blocks"]) == 8
    with pytest.raises(ValueError):
        validate_brief({"headline": "h", "summary": "s", "blocks": [{"start": "nope"}]}, FIXED_NOW)
    with pytest.raises(ValueError):
        validate_brief({"summary": "s", "blocks": many["blocks"]}, FIXED_NOW)
    with pytest.raises(ValueError):
        validate_brief(["not", "a", "dict"], FIXED_NOW)


# ---------------- fallback ----------------
def _assert_well_formed(blocks):
    starts = [int(b["start"][:2]) * 60 + int(b["start"][3:]) for b in blocks]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)
    assert all(b["kind"] in KINDS and 10 <= b["minutes"] <= 180 and b["title"] for b in blocks)


def test_fallback_when_llm_raises(client):
    FakeLLM.error = RuntimeError("All LLM providers failed.")
    data = client.post("/api/brief").get_json()["data"]
    assert data["ai"] is False and data["model"] == "fallback"
    blocks = data["blocks"]
    _assert_well_formed(blocks)
    assert blocks[0]["start"] >= "09:15"
    assert blocks[0]["kind"] == "exam" and blocks[0]["minutes"] == 120  # 2.5h clamped to one 120-min block
    assert blocks[0]["ref"] == {"type": "topic", "id": 31}
    assert blocks[-1]["kind"] == "episode" and blocks[-1]["ref"] == {"type": "episode", "id": 1}
    kinds = [b["kind"] for b in blocks]
    assert {"dsa", "review", "video", "rest"} <= set(kinds)
    assert "CN" in data["headline"] and "4 days" in data["headline"]
    assert "42%" in data["summary"] and "3 reviews due" in data["summary"]
    assert data["nudge"]


def test_fallback_when_llm_returns_garbage(client):
    FakeLLM.response = {"headline": "h", "summary": "s", "blocks": [{"start": "x", "kind": "y"}]}
    data = client.post("/api/brief").get_json()["data"]
    assert data["ai"] is False and data["blocks"]


def test_fallback_risks_and_empty_context():
    late = FIXED_NOW.replace(hour=19, minute=0)
    ctx = {"stats": {"streak": 5, "goal": 2, "solved_today": 1}}
    out = fallback_brief(ctx, late)
    assert "Streak of 5 at risk" in out["risk"]
    _assert_well_formed(out["blocks"])

    infeasible = {**CTX, "exams": {**CTX["exams"], "plan": {"feasible": False, "shortfall_hours": 3.5}}}
    assert "3.5h" in fallback_brief(infeasible, FIXED_NOW)["risk"]

    bare = fallback_brief({}, FIXED_NOW.replace(hour=23, minute=58))
    assert len(bare["blocks"]) == 1 and bare["blocks"][0]["kind"] == "rest"

    early = fallback_brief(CTX, FIXED_NOW.replace(hour=2, minute=0))
    assert early["blocks"][0]["start"] == "07:00"


# ---------------- context gathering ----------------
def test_gather_context_with_missing_sources():
    pages = {
        "/api/stats": {"status": "success", "data": {"streak": 3, "today": {"solved": 1, "goal": 2}, "rest_days": []}},
        "/api/reviews": {"status": "success", "data": [{"id": 1, "title": "A", "recall": 0.4}], "due_count": 1},
        "/api/logs?type=leetcode": {"status": "success", "data": [
            {"id": i, "title": f"P{i}", "is_completed": i % 2 == 0, "difficulty": "Easy"} for i in range(20)]},
        "/api/contests": {"status": "success", "data": [
            {"name": "Weekly", "platform": "leetcode", "start": (FIXED_NOW + timedelta(hours=10)).astimezone(timezone.utc).isoformat(),
             "duration_seconds": 5400},
            {"name": "Far", "platform": "codeforces", "start": (FIXED_NOW + timedelta(days=5)).isoformat(), "duration_seconds": 7200}]},
        "/api/watch": {"status": "success", "data": [{"id": 1, "title": "Ippo", "next_episode": 9, "is_active": True,
                                                     "watched_today": [], "finished": False}]},
    }

    def fetch(path):
        if path == "/api/todos":
            raise RuntimeError("boom")  # a broken source is skipped, not fatal
        return pages.get(path)

    ctx = gather_context(fetch, FIXED_NOW)
    assert ctx["plan_from"] == "09:15"
    assert ctx["stats"]["streak"] == 3
    assert ctx["reviews"]["top"][0]["recall_pct"] == 40
    assert ctx["pending_problems"]["count"] == 10 and len(ctx["pending_problems"]["top"]) == 5
    assert [c["name"] for c in ctx["contests"]] == ["Weekly"]
    assert ctx["episode"]["episode"] == 9 and ctx["episode"]["watched_today"] is False
    for missing in ("todos", "exams", "learning", "journal", "skills", "placements"):
        assert missing not in ctx


def test_gather_context_stays_compact():
    huge = {"status": "success", "data": [{"id": i, "text": "t" * 300, "done": False} for i in range(50)]}
    logs = {"status": "success", "data": [{"id": i, "title": "x" * 300, "is_completed": False} for i in range(500)]}
    ctx = gather_context(lambda p: huge if p == "/api/todos" else logs if p.startswith("/api/logs") else None, FIXED_NOW)
    assert len(ctx["todos"]["open"]) <= 8 and len(ctx["pending_problems"]["top"]) <= 5
    import json
    assert len(json.dumps(ctx)) < brief_mod.CONTEXT_CHAR_CAP


# ---------------- accept ----------------
def test_accept_creates_todos_once(client):
    assert client.post("/api/brief/accept", json={"indices": [0]}).status_code == 404
    client.post("/api/brief")

    res = client.post("/api/brief/accept", json={"indices": [0, 1, 1]})
    body = res.get_json()
    assert res.status_code == 200 and body["accepted"] == [0, 1]
    assert [t["text"] for t in body["data"]] == ["09:30 · CN: TCP congestion (90m)", "11:10 · Koko Eating Bananas (45m)"]

    # repeats are ignored; omitting indices adds every remaining non-rest block
    again = client.post("/api/brief/accept", json={}).get_json()
    assert [t["text"].split(" · ")[0] for t in again["data"]] == ["14:00", "15:00", "21:30"]
    assert again["accepted"] == [0, 1, 3, 4, 5]
    assert client.post("/api/brief/accept", json={"indices": [0, 1]}).get_json()["data"] == []

    todos = client.get("/api/todos").get_json()["data"]
    assert len(todos) == 5
    assert client.get("/api/brief").get_json()["data"]["accepted"] == [0, 1, 3, 4, 5]

    assert client.post("/api/brief/accept", json={"indices": [99]}).status_code == 400
    assert client.post("/api/brief/accept", json={"indices": "all"}).status_code == 400
    assert client.post("/api/brief/accept", json={"indices": [True]}).status_code == 400


# ---------------- cron ----------------
def test_cron_skips_when_ai_brief_exists(client):
    FakeLLM.error = RuntimeError("overloaded")
    first = client.post("/api/brief/cron").get_json()
    assert first == {"status": "success", "ai": False, "day": "2026-10-11"}  # fallback saved...

    FakeLLM.error = None
    second = client.post("/api/brief/cron").get_json()
    assert second["status"] == "success" and second["ai"] is True  # ...and retried with the LLM
    third = client.post("/api/brief/cron").get_json()
    assert third["status"] == "skipped"
    assert FakeLLM.calls == 2
