import json

import pytest
from flask import Flask

from api.core.db import Base, SessionLocal, engine
from api.domain import tutor as tu
from api.domain.models import NotificationLog
from api.domain.tutor import TutorCache, tutor_bp

WRITEUP = {
    "statement": "Given nums and target, return indices of two numbers adding to target.",
    "pattern": "Hash map",
    "hints": ["Think about complements.", "Store what you've seen.", "Look up target - x."],
    "intuition": "Each x needs target - x.",
    "approach": ["Scan once", "Check the map", "Insert x"],
    "time_complexity": "O(n)", "space_complexity": "O(n)",
    "edge_cases": ["duplicates"],
    "cpp_code": "SECRET_SOLUTION_CODE();",
}


class FakeLLM:
    instances = []
    chunks = ["Good. ", "What do you ", "store?"]
    stream_error = None
    json_result = None
    json_error = None

    def __init__(self, budget=240, **_kw):
        self.budget = budget
        self.calls = []
        FakeLLM.instances.append(self)

    def generate_json(self, contents, temperature=0.7, system=None, thinking=None):
        self.calls.append(("generate_json", contents, system))
        if FakeLLM.json_error:
            raise FakeLLM.json_error
        return FakeLLM.json_result

    def stream(self, contents, temperature=0.5, system=None, thinking=None):
        self.calls.append(("stream", contents, system))
        if FakeLLM.stream_error:
            raise FakeLLM.stream_error
        yield from FakeLLM.chunks


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(tutor_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def client(app, monkeypatch):
    FakeLLM.instances = []
    FakeLLM.chunks = ["Good. ", "What do you ", "store?"]
    FakeLLM.stream_error = None
    FakeLLM.json_result = None
    FakeLLM.json_error = None
    monkeypatch.setattr(tu, "LLMClient", FakeLLM)
    yield app.test_client()
    db = SessionLocal()
    db.query(TutorCache).delete()
    db.query(NotificationLog).delete()
    db.commit()
    db.close()


@pytest.fixture
def log_id():
    db = SessionLocal()
    log = NotificationLog(task_type="leetcode", title="Two Sum", slug="two-sum", difficulty="Easy",
                          content=json.dumps(WRITEUP))
    db.add(log)
    db.commit()
    lid = log.id
    db.close()
    return lid


def _events(res):
    body = res.get_data(as_text=True)
    return [json.loads(c[6:]) for c in body.split("\n\n") if c.startswith("data: ")]


def _prompt_text(call):
    return f"{call[1]}\n{call[2] or ''}"


# ---------------- chat ----------------
def test_chat_streams_and_redacts_code(client, log_id):
    msgs = [{"role": "user" if i % 2 == 0 else "tutor", "text": f"msg{i}"} for i in range(9)]
    res = client.post(f"/api/tutor/{log_id}/chat", json={"messages": msgs})
    assert res.status_code == 200
    assert res.mimetype == "text/event-stream"
    ev = _events(res)
    assert [e["type"] for e in ev][-1] == "done"
    assert "".join(e["text"] for e in ev if e["type"] == "delta") == "Good. What do you store?"
    assert ev[-1]["text"] == "Good. What do you store?"
    call = FakeLLM.instances[0].calls[0]
    text = _prompt_text(call)
    assert "SECRET_SOLUTION_CODE" not in text
    assert "redacted" in text.lower()
    assert "Hash map" in call[2] and "Socratic" in call[2]
    # only the last 6 turns reach the model
    assert "msg2" not in call[1] and "msg3" in call[1] and "msg8" in call[1]


def test_chat_strips_code_fences(client, log_id):
    FakeLLM.chunks = ["Try this: ``", "`cpp\nint x;\n", "```", " ok?"]
    ev = _events(client.post(f"/api/tutor/{log_id}/chat", json={"messages": [{"role": "user", "text": "code pls"}]}))
    streamed = "".join(e["text"] for e in ev if e["type"] == "delta")
    assert "int x" not in streamed and "```" not in streamed
    assert streamed == ev[-1]["text"] or streamed.strip() == ev[-1]["text"]
    assert "code omitted" in ev[-1]["text"]


def test_chat_validation_and_errors(client, log_id):
    assert client.post(f"/api/tutor/{log_id}/chat", json={"messages": []}).status_code == 400
    assert client.post(f"/api/tutor/{log_id}/chat",
                       json={"messages": [{"role": "tutor", "text": "hi"}]}).status_code == 400
    assert client.post("/api/tutor/99999/chat", json={"messages": [{"role": "user", "text": "hi"}]}).status_code == 404
    FakeLLM.stream_error = RuntimeError("429 RESOURCE_EXHAUSTED")
    ev = _events(client.post(f"/api/tutor/{log_id}/chat", json={"messages": [{"role": "user", "text": "hi"}]}))
    assert ev[-1]["type"] == "error" and "busy" in ev[-1]["message"]


# ---------------- assess ----------------
def test_assess_normalizes(client, log_id):
    FakeLLM.json_result = {"idea_correct": "yes", "missing_insight": "Duplicates?", "complexity_ok": False,
                           "next_question": "What if nums has the same value twice?", "hint_level": 7}
    res = client.post(f"/api/tutor/{log_id}/assess", json={"approach": "Sort and two pointers"})
    assert res.status_code == 200
    d = res.get_json()["data"]
    assert d == {"idea_correct": True, "missing_insight": "Duplicates?", "complexity_ok": False,
                 "next_question": "What if nums has the same value twice?", "hint_level": 3}
    assert "SECRET_SOLUTION_CODE" not in _prompt_text(FakeLLM.instances[0].calls[0])


def test_assess_validation_and_llm_error(client, log_id):
    assert client.post(f"/api/tutor/{log_id}/assess", json={"approach": "  "}).status_code == 400
    FakeLLM.json_error = RuntimeError("503 UNAVAILABLE")
    res = client.post(f"/api/tutor/{log_id}/assess", json={"approach": "hash map"})
    assert res.status_code == 502 and "busy" in res.get_json()["message"]


# ---------------- review ----------------
REVIEW = {"verdict": "Buggy", "summary": "Off by one.", "time": "O(n^2)", "space": "O(1)", "matches_optimal": "false",
          "bugs": [{"line": "3", "issue": "j starts at i"}, "unused var"],
          "failing_cases": [{"input": "[3,3], 6", "expected": "[0,1]", "why": "uses same index twice"}],
          "cleanups": ["Use a hash map"], "suggested_grade": "weird"}


def test_review_normalizes_and_caches(client, log_id):
    FakeLLM.json_result = REVIEW
    code = "for i\n  for j=i\n    check\n"
    res = client.post(f"/api/tutor/{log_id}/review", json={"code": code, "language": "C++"})
    assert res.status_code == 200
    d = res.get_json()["data"]
    assert d["verdict"] == "buggy" and d["suggested_grade"] == "hard" and d["matches_optimal"] is False
    assert d["bugs"] == [{"line": 3, "issue": "j starts at i"}, {"line": None, "issue": "unused var"}]
    assert d["failing_cases"][0]["expected"] == "[0,1]" and d["cached"] is False
    # reviewer sees the reference solution and numbered lines
    assert "SECRET_SOLUTION_CODE" in FakeLLM.instances[0].calls[0][1]
    assert "  2 |   for j=i" in FakeLLM.instances[0].calls[0][1]

    again = client.post(f"/api/tutor/{log_id}/review", json={"code": code, "language": "cpp"}).get_json()["data"]
    assert again["cached"] is True and again["verdict"] == "buggy"
    assert len(FakeLLM.instances) == 1  # served from cache, no LLM call

    # different language or code -> new review
    client.post(f"/api/tutor/{log_id}/review", json={"code": code, "language": "python"})
    assert len(FakeLLM.instances) == 2
    # fresh bypasses cache
    client.post(f"/api/tutor/{log_id}/review", json={"code": code, "language": "cpp", "fresh": True})
    assert len(FakeLLM.instances) == 3


def test_review_validation(client, log_id):
    assert client.post(f"/api/tutor/{log_id}/review", json={"code": ""}).status_code == 400
    assert client.post(f"/api/tutor/{log_id}/review", json={"code": "x", "language": "rust"}).status_code == 400
    assert client.post(f"/api/tutor/{log_id}/review", json={"code": "x" * (tu.MAX_CODE + 1)}).status_code == 400
    FakeLLM.json_error = ValueError("bad json")
    res = client.post(f"/api/tutor/{log_id}/review", json={"code": "int main(){}"})
    assert res.status_code == 502
    db = SessionLocal()
    assert db.query(TutorCache).count() == 0  # failures are never cached
    db.close()


def test_normalize_review_defaults():
    r = tu.normalize_review({"verdict": "wrong_approach"})
    assert r["verdict"] == "wrong approach" and r["suggested_grade"] == "again"
    assert r["bugs"] == [] and r["failing_cases"] == [] and r["cleanups"] == []
    assert tu.normalize_review(None)["verdict"] == "likely correct"


def test_problem_context_legacy_and_codeforces():
    ctx = tu.problem_context({"title": "A", "task_type": "codeforces", "slug": "1850/C",
                              "link": "https://codeforces.com/problemset/problem/1850/C", "writeup": {}})
    assert "codeforces.com" in ctx and "leetcode.com" not in ctx and "No stored write-up" in ctx
