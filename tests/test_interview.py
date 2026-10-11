import json

import pytest
from flask import Flask

from api.core.db import Base, SessionLocal, engine
from api.domain import interview as iv
from api.domain.interview import MockSession, interview_bp


class FakeLLM:
    """Stands in for LLMClient: no network, configurable per test."""
    instances = []
    opening = "Hi! Given an array, find something interesting. Think aloud and ask clarifying questions."
    chunks = ["Good start. ", "What would the brute force be, ", "and its complexity?"]
    stream_error = None       # raise before streaming anything
    fail_after = None         # raise after this many chunks
    json_result = None
    json_error = None
    generate_error = None

    def __init__(self, budget=240, **_kw):
        self.budget = budget
        self.calls = []
        FakeLLM.instances.append(self)

    def generate(self, contents, json_mode=False, temperature=0.7, system=None, thinking=None):
        self.calls.append(("generate", contents, system))
        if FakeLLM.generate_error:
            raise FakeLLM.generate_error
        return FakeLLM.opening

    def generate_json(self, contents, temperature=0.7, system=None, thinking=None):
        self.calls.append(("generate_json", contents, system))
        if FakeLLM.json_error:
            raise FakeLLM.json_error
        return FakeLLM.json_result

    def stream(self, contents, temperature=0.5, system=None, thinking=None):
        self.calls.append(("stream", contents, system))
        if FakeLLM.stream_error:
            raise FakeLLM.stream_error
        for i, c in enumerate(FakeLLM.chunks):
            if FakeLLM.fail_after is not None and i >= FakeLLM.fail_after:
                raise RuntimeError("503 UNAVAILABLE: model overloaded")
            yield c


DSA_RUBRIC = {
    "communication": 4, "problem_solving": 5, "correctness": "4", "complexity_analysis": 3.6, "edge_cases": 9,
    "verdict": "Hire", "strengths": ["Clear brute force", "Good complexity reasoning"],
    "top_fixes": ["Dry run earlier", "State edge cases upfront", "Name variables clearly", "extra one"],
    "model_answer_outline": "- Brute force O(n^2)\n- Hash map O(n)",
}


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(interview_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def client(app, monkeypatch):
    FakeLLM.instances = []
    FakeLLM.stream_error = None
    FakeLLM.fail_after = None
    FakeLLM.json_result = dict(DSA_RUBRIC)
    FakeLLM.json_error = None
    FakeLLM.generate_error = None
    monkeypatch.setattr(iv, "LLMClient", FakeLLM)
    yield app.test_client()
    db = SessionLocal()
    db.query(MockSession).delete()
    db.commit()
    db.close()


def _events(res):
    body = res.get_data(as_text=True)
    return [json.loads(chunk[6:]) for chunk in body.split("\n\n") if chunk.startswith("data: ")]


def _start(client, mode, **extra):
    res = client.post("/api/interview/start", json={"mode": mode, **extra})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


# ---------------- start ----------------
def test_start_dsa_picks_medium_and_llm_opening(client):
    s = _start(client, "dsa")
    assert s["mode"] == "dsa" and s["status"] == "active"
    problem = iv._problem(s["problem_slug"])
    assert problem and problem[2] == "Medium" and s["title"] == problem[0]
    assert s["problem"]["link"].endswith(f"/{s['problem_slug']}/")
    assert len(s["transcript"]) == 1
    first = s["transcript"][0]
    assert first["role"] == "interviewer" and first["text"] == FakeLLM.opening and first["at"]
    assert [d["key"] for d in s["dimensions"]] == ["communication", "problem_solving", "correctness",
                                                   "complexity_analysis", "edge_cases"]


def test_start_dsa_with_slug_and_template_fallback(client):
    FakeLLM.generate_error = RuntimeError("429 quota")
    s = _start(client, "dsa", problem_slug="two-sum")
    assert s["problem_slug"] == "two-sum" and s["title"] == "Two Sum"
    text = s["transcript"][0]["text"]
    assert "Two Sum" in text and "clarifying" in text


def test_start_behavioral_and_system_design(client):
    b = _start(client, "behavioral")
    assert b["title"] in iv.BEHAVIORAL_QUESTIONS and b["problem_slug"] is None
    assert b["title"] in b["transcript"][0]["text"]

    sd = _start(client, "system_design")
    names = {n for n, _ in iv.SYSTEM_DESIGN_PROMPTS}
    assert sd["title"] in names
    assert "requirements" in sd["transcript"][0]["text"]
    # Non-DSA openings are templated: no LLM call needed
    assert not any(c for inst in FakeLLM.instances for c in inst.calls)


def test_start_avoids_recent_repeats(client):
    from api.core.db import SessionLocal
    db = SessionLocal(); db.query(iv.MockSession).delete(); db.commit(); db.close()  # earlier tests in this module also started sessions
    n = min(len(iv.SYSTEM_DESIGN_PROMPTS), iv.RECENT_AVOID + 1)  # only the last RECENT_AVOID are avoided
    seen = [_start(client, "system_design")["title"] for _ in range(n)]
    assert len(set(seen)) == n


def test_start_validation(client):
    assert client.post("/api/interview/start", json={"mode": "hr"}).status_code == 400
    assert client.post("/api/interview/start", data="nope").status_code == 400
    assert client.post("/api/interview/start", json={"mode": "dsa", "problem_slug": "not-a-problem"}).status_code == 400
    assert client.post("/api/interview/start", json={"mode": "behavioral", "problem_slug": "two-sum"}).status_code == 400


# ---------------- reply ----------------
def test_reply_streams_and_persists_transcript(client):
    s = _start(client, "dsa", problem_slug="3sum")
    res = client.post(f"/api/interview/{s['id']}/reply", json={"text": "  Can the array contain duplicates?  "})
    assert res.status_code == 200 and res.mimetype == "text/event-stream"
    events = _events(res)
    deltas = [e["text"] for e in events if e["type"] == "delta"]
    assert deltas == FakeLLM.chunks
    assert events[-1]["type"] == "done"
    assert events[-1]["message"]["text"] == "".join(FakeLLM.chunks).strip()

    # The prompt carries the transcript and the DSA rules
    _kind, prompt, system = FakeLLM.instances[-1].calls[-1]
    assert "Can the array contain duplicates?" in prompt and "3Sum" in system and "NEVER give the solution" in system

    t = client.get(f"/api/interview/{s['id']}").get_json()["data"]["transcript"]
    assert [m["role"] for m in t] == ["interviewer", "candidate", "interviewer"]
    assert t[1]["text"] == "Can the array contain duplicates?"
    assert t[2]["text"] == "".join(FakeLLM.chunks).strip()


def test_reply_llm_failure_sends_error_and_keeps_candidate_message(client):
    s = _start(client, "behavioral")
    FakeLLM.stream_error = RuntimeError("All LLM providers failed. 503 UNAVAILABLE")
    events = _events(client.post(f"/api/interview/{s['id']}/reply", json={"text": "I led a hackathon team."}))
    assert [e["type"] for e in events] == ["error"]
    assert "busy" in events[0]["message"]

    t = client.get(f"/api/interview/{s['id']}").get_json()["data"]["transcript"]
    assert [m["role"] for m in t] == ["interviewer", "candidate"]
    assert t[-1]["text"] == "I led a hackathon team."

    # Retry regenerates the interviewer turn without duplicating the candidate message
    FakeLLM.stream_error = None
    events = _events(client.post(f"/api/interview/{s['id']}/reply", json={"retry": True}))
    assert events[-1]["type"] == "done"
    t = client.get(f"/api/interview/{s['id']}").get_json()["data"]["transcript"]
    assert [m["role"] for m in t] == ["interviewer", "candidate", "interviewer"]
    # Nothing left to retry now
    assert client.post(f"/api/interview/{s['id']}/reply", json={"retry": True}).status_code == 409


def test_reply_mid_stream_failure_does_not_persist_partial(client):
    s = _start(client, "system_design")
    FakeLLM.fail_after = 1
    events = _events(client.post(f"/api/interview/{s['id']}/reply", json={"text": "Read heavy, 100M URLs/month."}))
    assert [e["type"] for e in events] == ["delta", "error"]
    t = client.get(f"/api/interview/{s['id']}").get_json()["data"]["transcript"]
    assert [m["role"] for m in t] == ["interviewer", "candidate"]


def test_reply_validation(client):
    s = _start(client, "behavioral")
    assert client.post(f"/api/interview/{s['id']}/reply", json={"text": "   "}).status_code == 400
    assert client.post(f"/api/interview/{s['id']}/reply", json={"text": "x" * (iv.MAX_REPLY + 1)}).status_code == 400
    assert client.post("/api/interview/99999/reply", json={"text": "hi"}).status_code == 404


# ---------------- end ----------------
def test_end_produces_normalized_rubric(client):
    s = _start(client, "dsa", problem_slug="two-sum")
    _events(client.post(f"/api/interview/{s['id']}/reply", json={"text": "Brute force is O(n^2) with two loops."}))
    res = client.post(f"/api/interview/{s['id']}/end")
    assert res.status_code == 200, res.get_json()
    d = res.get_json()["data"]
    assert d["status"] == "done" and d["ended_at"]
    r = d["rubric"]
    assert (r["communication"], r["problem_solving"], r["correctness"], r["complexity_analysis"], r["edge_cases"]) == (4, 5, 4, 4, 5)
    assert r["verdict"] == "hire"
    assert r["overall"] == 4.4
    assert len(r["top_fixes"]) == 3 and r["strengths"] and "Hash map" in r["model_answer_outline"]
    assert [x["key"] for x in r["scores"]][0] == "communication"
    _kind, prompt, _system = FakeLLM.instances[-1].calls[-1]
    assert "Brute force is O(n^2)" in prompt

    # Ended sessions refuse replies; ending again is idempotent
    assert client.post(f"/api/interview/{s['id']}/reply", json={"text": "more"}).status_code == 409
    calls_before = sum(len(i.calls) for i in FakeLLM.instances)
    assert client.post(f"/api/interview/{s['id']}/end").get_json()["data"]["rubric"] == r
    assert sum(len(i.calls) for i in FakeLLM.instances) == calls_before


def test_end_behavioral_dimensions_and_bad_verdict(client):
    FakeLLM.json_result = {"communication": 2, "structure": 2, "specificity": 1, "impact": 2, "conciseness": 3,
                           "verdict": "maybe", "strengths": "not a list", "top_fixes": ["a", "b", "c"]}
    s = _start(client, "behavioral")
    _events(client.post(f"/api/interview/{s['id']}/reply", json={"text": "We did a project."}))
    r = client.post(f"/api/interview/{s['id']}/end").get_json()["data"]["rubric"]
    assert set(k["key"] for k in r["scores"]) == {"communication", "structure", "specificity", "impact", "conciseness"}
    assert r["verdict"] == "no hire"  # derived from the 2.0 average
    assert r["strengths"] == [] and r["model_answer_outline"] == ""


def test_end_llm_failure_keeps_session_active(client):
    s = _start(client, "dsa", problem_slug="two-sum")
    _events(client.post(f"/api/interview/{s['id']}/reply", json={"text": "Use a hash map."}))
    FakeLLM.json_error = RuntimeError("429 RESOURCE_EXHAUSTED")
    res = client.post(f"/api/interview/{s['id']}/end")
    assert res.status_code == 502 and res.get_json()["status"] == "error"
    d = client.get(f"/api/interview/{s['id']}").get_json()["data"]
    assert d["status"] == "active" and d["rubric"] is None and len(d["transcript"]) == 3

    FakeLLM.json_error = None
    assert client.post(f"/api/interview/{s['id']}/end").get_json()["data"]["rubric"]["verdict"] == "hire"


def test_end_without_answers_has_no_rubric(client):
    s = _start(client, "behavioral")
    d = client.post(f"/api/interview/{s['id']}/end").get_json()["data"]
    assert d["status"] == "done" and d["rubric"] is None
    assert not any(c[0] == "generate_json" for i in FakeLLM.instances for c in i.calls)


# ---------------- list ----------------
def test_list_with_averages(client):
    a = _start(client, "dsa", problem_slug="two-sum")
    _events(client.post(f"/api/interview/{a['id']}/reply", json={"text": "Hash map, O(n)."}))
    client.post(f"/api/interview/{a['id']}/end")
    b = _start(client, "behavioral")  # still active, not graded

    body = client.get("/api/interview").get_json()
    assert body["status"] == "success"
    assert [x["id"] for x in body["data"]] == [b["id"], a["id"]]
    graded = body["data"][1]
    assert graded["verdict"] == "hire" and graded["overall"] == 4.4 and graded["turns"] == 1
    assert "transcript" not in graded
    avg = body["averages"]
    assert avg["graded"] == 1 and avg["overall"] == 4.4
    assert avg["by_mode"]["dsa"]["dims"]["problem_solving"] == 5
    assert avg["verdicts"] == {"hire": 1}

    assert client.delete(f"/api/interview/{b['id']}").status_code == 200
    assert client.get(f"/api/interview/{b['id']}").status_code == 404
