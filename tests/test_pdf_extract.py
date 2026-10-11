import base64
import json

import pytest
from flask import Flask

import api.domain.pdf_extract as pe
from api.domain.pdf_extract import MAX_CARDS, MAX_IMAGES, MAX_TOPICS, normalize, pdf_extract_bp

JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0fakejpeg").decode()


class FakeLLM:
    calls = []
    reply = {}
    raises = None

    def __init__(self, budget=240, **_):
        self.budget = budget

    @staticmethod
    def image_part(data, mime_type="image/jpeg"):
        return {"bytes": data, "mime": mime_type}

    def generate_json(self, contents, temperature=0.7, system=None, thinking=None):
        FakeLLM.calls.append({"contents": contents, "budget": self.budget, "system": system})
        if FakeLLM.raises:
            raise FakeLLM.raises
        return FakeLLM.reply


@pytest.fixture
def client(monkeypatch):
    FakeLLM.calls, FakeLLM.reply, FakeLLM.raises = [], {}, None
    monkeypatch.setattr(pe, "LLMClient", FakeLLM)
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(pdf_extract_bp)
    with app.test_client() as c:
        yield c


def test_extracts_and_normalizes(client):
    FakeLLM.reply = {
        "unit": "Black box testing",
        "topics": [
            {"title": "1. Equivalence partitioning", "summary": "Split inputs\ninto classes.", "likely_marks": "HIGH",
             "flashcards": [{"q": "What is EP?", "a": "Partitioning inputs."}, {"q": "", "a": "x"},
                            {"question": "Why EP?", "answer": "Fewer tests."}]},
            {"title": "equivalence partitioning", "likely_marks": "high"},  # duplicate
            {"title": "Boundary value analysis", "likely_marks": "whatever", "cards": "nope"},
            "Decision tables",
            {"title": "---"},
            42,
        ],
    }
    r = client.post("/api/pdf-extract/topics", json={
        "images": [JPEG, JPEG], "text": "  some text ", "subject_name": "Software Testing", "label": "1–10"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "success"
    data = body["data"]
    assert data["unit"] == "Black box testing" and data["label"] == "1–10"
    assert [t["title"] for t in data["topics"]] == ["Equivalence partitioning", "Boundary value analysis", "Decision tables"]
    first = data["topics"][0]
    assert first["likely_marks"] == "high" and first["summary"] == "Split inputs into classes."
    assert first["flashcards"] == [{"q": "What is EP?", "a": "Partitioning inputs."}, {"q": "Why EP?", "a": "Fewer tests."}]
    assert data["topics"][1]["likely_marks"] == "medium" and data["topics"][1]["flashcards"] == []

    call = FakeLLM.calls[0]
    assert call["budget"] == 90
    prompt, *parts = call["contents"]
    assert "Software Testing" in prompt and "pages 1–10" in prompt and "some text" in prompt
    assert len(parts) == 2 and parts[0]["mime"] == "image/jpeg" and parts[0]["bytes"].startswith(b"\xff\xd8")


def test_clamps_counts_and_lengths():
    raw = {"topics": [{"title": f"Topic {i} " + "x" * 300, "summary": "s" * 1000,
                       "flashcards": [{"q": f"q{j}", "a": "a"} for j in range(8)]} for i in range(40)]}
    out = normalize(raw, fallback_unit="Pages 3")
    assert out["unit"] == "Pages 3"
    assert len(out["topics"]) == MAX_TOPICS
    for t in out["topics"]:
        assert len(t["title"]) <= pe.MAX_TITLE and len(t["summary"]) <= pe.MAX_SUMMARY
        assert len(t["flashcards"]) == MAX_CARDS


def test_normalize_handles_garbage():
    assert normalize(None) == {"unit": "Imported from PDF", "topics": []}
    assert normalize(["A topic"])["topics"][0]["title"] == "A topic"
    assert normalize({"topics": "nope"})["topics"] == []


def test_text_only_and_fallback_unit(client):
    FakeLLM.reply = {"topics": [{"title": "TCP congestion control"}]}
    r = client.post("/api/pdf-extract/topics", json={"text": "slides", "label": "11–20"})
    assert r.status_code == 200
    assert r.get_json()["data"]["unit"] == "Pages 11–20"
    assert len(FakeLLM.calls[0]["contents"]) == 1


@pytest.mark.parametrize("payload, needle", [
    ({}, "No pages"),
    ({"images": "abc"}, "list"),
    ({"images": [JPEG] * (MAX_IMAGES + 1)}, "at most"),
    ({"images": ["data:image/gif;base64,R0lG"]}, "couldn't be read"),
    ({"images": ["!!!not base64!!!"]}, "couldn't be read"),
])
def test_validation(client, payload, needle):
    r = client.post("/api/pdf-extract/topics", json=payload)
    assert r.status_code == 400
    body = r.get_json()
    assert body["status"] == "error" and needle in body["message"]
    assert FakeLLM.calls == []


def test_llm_failures(client):
    FakeLLM.raises = json.JSONDecodeError("bad", "x", 0)
    r = client.post("/api/pdf-extract/topics", json={"text": "t"})
    assert r.status_code == 502 and "malformed" in r.get_json()["message"]

    FakeLLM.raises = RuntimeError("All LLM providers failed. No API key configured (set GEMINI_API_KEY).")
    r = client.post("/api/pdf-extract/topics", json={"text": "t"})
    assert r.status_code == 503

    FakeLLM.raises = RuntimeError("timeout")
    r = client.post("/api/pdf-extract/topics", json={"text": "t"})
    assert r.status_code == 502 and r.get_json()["status"] == "error"
