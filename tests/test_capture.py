from datetime import datetime, timedelta

import pytest
from flask import Flask

from api.core.config import IST
from api.core.db import Base, engine, SessionLocal
from api.domain import capture as cap
from api.domain.capture import capture_bp
from api.domain.todos import Todo

FIXED_NOW = datetime(2026, 10, 11, 9, 30, tzinfo=IST)
TODAY = FIXED_NOW.date()
TOMORROW = TODAY + timedelta(days=1)


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(capture_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setattr(cap, "now_ist", lambda: FIXED_NOW)
    monkeypatch.setattr(cap, "_youtube_title", lambda url: "Segment Trees Explained")

    def no_network(*a, **k):
        raise AssertionError("network call in test")
    monkeypatch.setattr(cap.requests, "get", no_network)
    yield app.test_client()
    db = SessionLocal()
    db.query(Todo).delete()
    db.commit()
    db.close()


def _parse(client, **body):
    res = client.post("/api/capture/parse", json=body)
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


# ---------------- pure parsing ----------------
def test_leetcode_url():
    it = cap.parse_rules("https://leetcode.com/problems/two-sum/description/")[0]
    assert it["kind"] == "leetcode" and it["slug"] == "two-sum" and it["title"] == "Two Sum"
    assert it["url"] == "https://leetcode.com/problems/two-sum/"


def test_leetcode_bare_domain_and_roman():
    it = cap.parse_rules("leetcode.com/problems/jump-game-ii tomorrow #dp")[0]
    assert it["title"] == "Jump Game II" and it["day"] == "tomorrow" and it["tags"] == ["dp"]


@pytest.mark.parametrize("url,key", [
    ("https://codeforces.com/contest/1900/problem/c", "1900C"),
    ("https://codeforces.com/problemset/problem/4/A", "4A"),
])
def test_codeforces_url(url, key):
    it = cap.parse_rules(url)[0]
    assert it["kind"] == "codeforces" and it["key"] == key and it["title"] == f"CF {key}"


def test_youtube_uses_hint_when_no_title(monkeypatch):
    monkeypatch.setattr(cap, "_youtube_title", lambda url: None)
    it = cap.parse_rules("Graph basics - YouTube https://youtu.be/abc123")[0]
    assert it["kind"] == "video" and it["title"] == "Graph basics"


def test_todo_tomorrow_and_tags():
    it = cap.parse_todo("Revise DBMS tomorrow #exam #Exam #os")
    assert it == {"kind": "todo", "text": "Revise DBMS", "day": "tomorrow", "tags": ["exam", "os"]}


def test_possessive_tomorrow_is_not_a_day():
    it = cap.parse_todo("Prep for tomorrow's quiz")
    assert it["day"] == "today" and "tomorrow's" in it["text"]


def test_multiline_and_bullets():
    items = cap.parse_rules("- buy milk\n2) call mom tmrw; ")
    assert [i["text"] for i in items] == ["buy milk", "call mom"]
    assert [i["day"] for i in items] == ["today", "tomorrow"]


def test_looks_multi():
    assert cap.looks_multi("solve 2 DP problems, revise OS and email the professor")
    assert not cap.looks_multi("revise OS")


# ---------------- routes ----------------
def test_parse_route_adds_dates(client):
    data = _parse(client, text="Revise DBMS tomorrow")
    assert data["source"] == "rules" and not data["ambiguous"]
    assert data["items"][0]["date"] == TOMORROW.isoformat()


def test_parse_shared_url_param(client):
    data = _parse(client, text="Check this out", url="https://www.youtube.com/watch?v=xyz")
    it = data["items"][0]
    assert it["kind"] == "video" and it["title"] == "Segment Trees Explained"


def test_parse_empty_rejected(client):
    assert client.post("/api/capture/parse", json={"text": "   "}).status_code == 400


def test_parse_ambiguous_without_ai(client):
    data = _parse(client, text="solve 2 DP problems, revise OS and email the professor")
    assert data["ambiguous"] is True and len(data["items"]) == 1


def test_parse_ai_split(client, monkeypatch):
    monkeypatch.setattr(cap, "_llm_split", lambda text: [
        {"kind": "todo", "text": "Solve 2 DP problems", "day": "today", "tags": []},
        {"kind": "todo", "text": "Email the professor", "day": "tomorrow", "tags": []},
    ])
    data = _parse(client, text="solve 2 DP problems, revise OS and email the professor", ai=True)
    assert data["source"] == "ai" and len(data["items"]) == 2
    assert data["items"][1]["date"] == TOMORROW.isoformat()


def test_llm_split_without_key_returns_none():
    assert cap._llm_split("a, b and c then d") is None  # conftest blanks GEMINI_API_KEY


def test_commit_creates_todos(client):
    items = _parse(client, text="https://leetcode.com/problems/two-sum/\nRevise DBMS tomorrow #exam")["items"]
    res = client.post("/api/capture/commit", json={"items": items})
    assert res.status_code == 200, res.get_json()
    out = res.get_json()["data"]
    assert out[0]["text"] == "Solve: Two Sum https://leetcode.com/problems/two-sum/"
    assert out[0]["day"] == TODAY.isoformat()
    assert out[1]["text"] == "Revise DBMS #exam" and out[1]["day"] == TOMORROW.isoformat()


def test_commit_codeforces_and_dedupe(client):
    items = [{"kind": "codeforces", "key": "1900C", "title": "CF 1900C",
              "url": "https://codeforces.com/contest/1900/problem/C", "day": "today"}]
    first = client.post("/api/capture/commit", json={"items": items}).get_json()
    assert first["data"][0]["text"] == "Solve: CF 1900C https://codeforces.com/contest/1900/problem/C"
    again = client.post("/api/capture/commit", json={"items": items}).get_json()
    assert again["data"] == [] and again["skipped"] == 1


def test_commit_positions_append(client):
    client.post("/api/capture/commit", json={"items": [{"kind": "todo", "text": "a"}, {"kind": "todo", "text": "b"}]})
    db = SessionLocal()
    try:
        rows = db.query(Todo).order_by(Todo.position).all()
        assert [r.text for r in rows] == ["a", "b"] and rows[0].position < rows[1].position
    finally:
        db.close()


def test_commit_long_text_truncated(client):
    res = client.post("/api/capture/commit", json={"items": [{"kind": "leetcode", "title": "x" * 400,
                                                              "url": "https://leetcode.com/problems/x/"}]})
    text = res.get_json()["data"][0]["text"]
    assert len(text) <= 300 and text.endswith("https://leetcode.com/problems/x/")


@pytest.mark.parametrize("body", [{}, {"items": []}, {"items": ["x"]}, {"items": [{"text": "a", "day": "monday"}]},
                                  {"items": [{"kind": "todo", "text": "  "}]}])
def test_commit_validation(client, body):
    assert client.post("/api/capture/commit", json=body).status_code == 400
