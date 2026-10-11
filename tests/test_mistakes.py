from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from api.core.config import IST
from api.core.db import Base, engine, SessionLocal
from api.domain import mistakes as mod
from api.domain.mistakes import Mistake, mistakes_bp, heuristic_category, heuristic_pattern
from api.domain.models import NotificationLog

FIXED_NOW = datetime(2026, 10, 11, 21, 15, tzinfo=IST)
NOW_UTC = FIXED_NOW.astimezone(timezone.utc).replace(tzinfo=None)


class FakeLLM:
    calls = []
    reply = None  # dict to return, or an Exception to raise

    def __init__(self, *a, **kw):
        pass

    def generate_json(self, prompt, **kw):
        FakeLLM.calls.append(prompt)
        if isinstance(FakeLLM.reply, Exception):
            raise FakeLLM.reply
        return FakeLLM.reply


def _wipe():
    db = SessionLocal()
    db.query(Mistake).delete()
    db.query(NotificationLog).delete()
    db.commit()
    db.close()


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(mistakes_bp)
    Base.metadata.create_all(bind=engine)
    _wipe()
    yield app
    _wipe()


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setattr(mod, "now_ist", lambda: FIXED_NOW)
    monkeypatch.setattr(mod, "LLMClient", FakeLLM)
    FakeLLM.calls = []
    FakeLLM.reply = RuntimeError("no key")
    yield app.test_client()
    _wipe()


def _add(category, days_ago, pattern=None, resolved=False):
    db = SessionLocal()
    m = Mistake(what_happened="x", category=category, pattern=pattern, lesson="l",
                created_at=NOW_UTC - timedelta(days=days_ago), resolved=resolved)
    db.add(m)
    db.commit()
    db.close()


# ---------------- heuristics ----------------
def test_heuristic_category():
    assert heuristic_category("Got TLE, my solution was O(n^2)") == "tle_complexity"
    assert heuristic_category("loop bound was <= instead of <, off by one") == "off_by_one"
    assert heuristic_category("forgot the empty array edge case") == "missed_edge_case"
    assert heuristic_category("sum overflowed int32, needed long long") == "overflow"
    assert heuristic_category("I misread the statement, it's a subsequence") == "misread_problem"
    assert heuristic_category("feeling sad") == "other"


def test_heuristic_pattern():
    assert heuristic_pattern("used dp but wrong transition") == "dynamic programming"
    assert heuristic_pattern("binary search on answer") == "binary search"
    assert heuristic_pattern("nothing relevant") is None


# ---------------- create ----------------
def test_create_uses_llm_tags(client):
    FakeLLM.reply = {"category": "off_by_one", "pattern": "Binary Search",
                     "lesson": "Use lo < hi with hi = n when searching for the insertion point."}
    r = client.post("/api/mistakes", json={"what_happened": "infinite loop in my search",
                                           "problem_title": "Search Insert Position",
                                           "link": "https://leetcode.com/problems/search-insert-position/"})
    body = r.get_json()
    assert body["status"] == "success" and body["source"] == "ai"
    d = body["data"]
    assert d["category"] == "off_by_one" and d["category_label"] == "Off by one"
    assert d["pattern"] == "binary search"
    assert d["lesson"].startswith("Use lo < hi")
    assert d["resolved"] is False
    assert "Search Insert Position" in FakeLLM.calls[0]


def test_create_falls_back_to_heuristics(client):
    r = client.post("/api/mistakes", json={"what_happened": "TLE because the sliding window recomputed sums"})
    body = r.get_json()
    assert body["source"] == "heuristic"
    assert body["data"]["category"] == "tle_complexity"
    assert body["data"]["pattern"] == "sliding window"
    assert body["data"]["lesson"] == "TLE because the sliding window recomputed sums"


def test_invalid_llm_category_uses_heuristic(client):
    FakeLLM.reply = {"category": "bananas", "pattern": None, "lesson": "Check for integer overflow."}
    d = client.post("/api/mistakes", json={"what_happened": "answer overflowed int32"}).get_json()["data"]
    assert d["category"] == "overflow" and d["lesson"] == "Check for integer overflow."


def test_user_category_wins(client):
    FakeLLM.reply = {"category": "overflow", "pattern": None, "lesson": "Read carefully."}
    d = client.post("/api/mistakes", json={"what_happened": "hmm", "category": "misread_problem"}).get_json()["data"]
    assert d["category"] == "misread_problem"


def test_create_from_log(client):
    db = SessionLocal()
    log = NotificationLog(task_type="leetcode", title="Two Sum", link="https://leetcode.com/problems/two-sum/",
                          topic="Hash Table")
    db.add(log)
    db.commit()
    log_id = log.id
    db.close()
    d = client.post("/api/mistakes", json={"what_happened": "forgot duplicates", "log_id": log_id}).get_json()["data"]
    assert d["log_id"] == log_id and d["problem_title"] == "Two Sum"
    assert d["link"] == "https://leetcode.com/problems/two-sum/"
    assert d["pattern"] == "hashing" or d["pattern"] == "hash table"
    assert client.post("/api/mistakes", json={"what_happened": "x", "log_id": 99999}).status_code == 404


def test_create_validation(client):
    assert client.post("/api/mistakes", json={}).status_code == 400
    assert client.post("/api/mistakes", json={"what_happened": "   "}).status_code == 400
    assert client.post("/api/mistakes", json={"what_happened": "x", "link": "javascript:alert(1)"}).status_code == 400
    assert client.post("/api/mistakes", json={"what_happened": "x", "log_id": "1"}).status_code == 400
    assert client.post("/api/mistakes", json={"what_happened": "x", "category": "nope"}).status_code == 400


# ---------------- update / delete ----------------
def test_update_and_delete(client):
    mid = client.post("/api/mistakes", json={"what_happened": "off by one in loop"}).get_json()["data"]["id"]
    d = client.put(f"/api/mistakes/{mid}", json={"resolved": True, "lesson": "Check bounds.",
                                                 "category": "implementation_bug", "pattern": "  Two Pointers "}).get_json()["data"]
    assert d["resolved"] is True and d["lesson"] == "Check bounds."
    assert d["category"] == "implementation_bug" and d["pattern"] == "two pointers"
    assert client.put(f"/api/mistakes/{mid}", json={"category": "bad"}).status_code == 400
    assert client.put(f"/api/mistakes/{mid}", json={"what_happened": ""}).status_code == 400
    assert client.delete(f"/api/mistakes/{mid}").get_json()["status"] == "success"
    assert client.put(f"/api/mistakes/{mid}", json={"resolved": False}).status_code == 404


# ---------------- list / stats / checklist ----------------
def test_list_stats_and_filter(client):
    _add("off_by_one", 1, pattern="binary search")
    _add("off_by_one", 2, pattern="binary search")
    _add("off_by_one", 9)
    _add("tle_complexity", 3, pattern="dynamic programming", resolved=True)
    _add("tle_complexity", 10)
    _add("tle_complexity", 11)
    _add("other", 0)
    _add("other", 0)
    _add("other", 0)

    body = client.get("/api/mistakes").get_json()
    assert body["status"] == "success" and len(body["data"]) == 9
    s = body["stats"]
    assert s["total"] == 9 and s["resolved"] == 1 and s["open"] == 8
    assert s["this_week"] == 6 and s["last_week"] == 3
    per = {c["category"]: c for c in s["per_category"]}
    assert per["off_by_one"]["this_week"] == 2 and per["off_by_one"]["last_week"] == 1
    assert per["tle_complexity"]["this_week"] == 1 and per["tle_complexity"]["last_week"] == 2
    # 'other' is most frequent but never outranks a real category
    assert [t["category"] for t in s["top_categories"]] == ["off_by_one", "tle_complexity"]
    assert s["top_patterns"][0] == {"pattern": "binary search", "count": 2}
    assert len(body["categories"]) == 8

    filtered = client.get("/api/mistakes?category=tle_complexity").get_json()["data"]
    assert len(filtered) == 3 and all(m["category"] == "tle_complexity" for m in filtered)
    assert len(client.get("/api/mistakes?category=tle_complexity&status=open").get_json()["data"]) == 2
    assert client.get("/api/mistakes?category=nope").status_code == 400

    cl = client.get("/api/mistakes/checklist").get_json()["data"]
    texts = [i["text"] for i in cl["items"]]
    assert texts[0].startswith("Check loop bounds")
    assert any("worst-case complexity" in t for t in texts)
    assert cl["text"].startswith("Pre-submit checklist\n[ ] ")
    assert [b["category"] for b in cl["based_on"]][:2] == ["off_by_one", "tle_complexity"]


def test_checklist_without_history(client):
    cl = client.get("/api/mistakes/checklist").get_json()["data"]
    assert cl["based_on"] == []
    assert len(cl["items"]) >= 3
    assert cl["items"][-1]["label"] == "Always"
