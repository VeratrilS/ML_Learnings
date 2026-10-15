import json
import re

import pytest
from flask import Flask

from api.core.clients import LLMClient
from api.core.db import Base, SessionLocal, engine
from api.domain import job_pack as jp
from api.domain.job_pack import (BANNED_WORDS, COVER_MAX_WORDS, QUESTIONS, RESUME_FACTS, WHY_COMPANY_MAX_WORDS,
                                 JobPack, job_pack_bp, word_count)
from api.domain.job_radar import JobOpportunity

FACT_BULLETS = {h["bullet"] for h in RESUME_FACTS["highlights"]}

GOOD_LLM = {
    "cover_note": "I am a final-year B.Tech CSE student at NIT Rourkela with a CGPA of 8.99. I built a distributed "
                  "railway reservation system with 8 microservices and 13 Kafka topics.\n\nI want to do this work "
                  "as a Backend Engineer at Acme.",
    "why_company": "Acme is hiring a Backend Engineer, and my Kafka and Redis work lines up with the role.",
    "why_role": "The role is backend work with Kafka and Redis, which I used in my railway project.",
    "challenging_project": "My railway reservation system used Redis Lua locks with Postgres row locks and a Saga.",
    "strongest_skill": "C++. I wrote a Redis-compatible cache server with 30 commands and O(1) LRU/LFU eviction.",
}


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(job_pack_bp)
    Base.metadata.create_all(bind=engine, tables=[JobOpportunity.__table__, JobPack.__table__])
    yield app


@pytest.fixture
def client(app):
    yield app.test_client()
    db = SessionLocal()
    db.query(JobPack).delete()
    db.query(JobOpportunity).delete()
    db.commit()
    db.close()


@pytest.fixture
def llm(monkeypatch):
    """Fake LLMClient.generate_json: returns `llm.reply` (or raises it if it's an exception) and records calls."""
    class Fake:
        reply = dict(GOOD_LLM)
        calls = []

    def fake_generate_json(self, contents, temperature=0.7, system=None, thinking=None):
        Fake.calls.append({"contents": contents, "system": system})
        if isinstance(Fake.reply, Exception):
            raise Fake.reply
        self.last_model = "gemini-test"
        return Fake.reply

    Fake.calls = []
    monkeypatch.setattr(LLMClient, "generate_json", fake_generate_json)
    return Fake


def _job(company="Acme", role="Backend Engineer", skills=("C++", "Kafka", "Redis", "Java"), location="Bengaluru"):
    db = SessionLocal()
    job = JobOpportunity(external_id=f"t-{company}-{role}", company=company, role=role, ctc_lpa=0.0,
                         location=location, source="Greenhouse (live)", portal_url="https://example.com/apply/1",
                         skills_required=json.dumps(list(skills)), notes="Live from Greenhouse")
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()
    return job_id


def _pack(client, job_id, refresh=False):
    res = client.get(f"/api/jobs/{job_id}/pack" + ("?refresh=1" if refresh else ""))
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["status"] == "success"
    return body["data"]


def _all_text(data):
    return " ".join([data["cover_note"], data["why_company"]] + [a["answer"] for a in data["answers"]])


# ---------------- shape ----------------
def test_pack_shape(client, llm):
    job_id = _job()
    data = _pack(client, job_id)
    assert data["job_id"] == job_id and data["company"] == "Acme" and data["role"] == "Backend Engineer"
    assert data["url"] == "https://example.com/apply/1"
    assert data["model"] == "gemini-test" and data["cached"] is False
    assert data["cover_note"] == GOOD_LLM["cover_note"]
    assert word_count(data["cover_note"]) <= COVER_MAX_WORDS
    assert word_count(data["why_company"]) <= WHY_COMPANY_MAX_WORDS
    assert [a["question"] for a in data["answers"]] == [q for _, q in QUESTIONS]
    assert all(a["answer"] for a in data["answers"])
    answers = {a["question"]: a["answer"] for a in data["answers"]}
    assert "2027" in answers["What is your expected graduation date?"]
    assert "Bengaluru" in answers["Are you willing to relocate?"]
    assert 3 <= len(data["resume_highlights"]) <= 5
    assert set(data["resume_highlights"]) <= FACT_BULLETS
    assert data["matched_skills"] == ["C++", "Kafka", "Redis"]  # Java is not on the resume
    # One call, grounded prompt
    assert len(llm.calls) == 1
    prompt, system = llm.calls[0]["contents"], llm.calls[0]["system"]
    assert "Acme" in prompt and "Backend Engineer" in prompt and "NIT Rourkela" in prompt
    assert all(w in system for w in BANNED_WORDS)


def test_highlights_follow_job_skills(client, llm):
    backend = _pack(client, _job(role="Backend Engineer", skills=["Kafka", "PostgreSQL", "Microservices"]))
    assert backend["resume_highlights"][0].startswith("Distributed Railway Reservation")
    web = _pack(client, _job(company="Webco", role="Frontend Engineer", skills=["React", "JavaScript", "Node.js"]))
    assert web["resume_highlights"][0].startswith("Software Engineering Intern, Maruti Suzuki")
    cpp = _pack(client, _job(company="Sys", role="Software Engineer", skills=["C++", "Multithreading"]))
    assert cpp["resume_highlights"][0].startswith("Cache Server (C++)")
    bare = _pack(client, _job(company="Bare", role="Software Engineer", skills=[]))
    assert len(bare["resume_highlights"]) == 3


# ---------------- cache ----------------
def test_cache_hit_skips_llm(client, llm):
    job_id = _job()
    first = _pack(client, job_id)
    second = _pack(client, job_id)
    assert len(llm.calls) == 1
    assert second["cached"] is True and second["model"] == "gemini-test"
    assert {k: v for k, v in second.items() if k != "cached"} == {k: v for k, v in first.items() if k != "cached"}


def test_refresh_regenerates(client, llm):
    job_id = _job()
    _pack(client, job_id)
    llm.reply = {**GOOD_LLM, "cover_note": "I built a Redis-compatible cache server in C++ with 30 commands."}
    data = _pack(client, job_id, refresh=True)
    assert len(llm.calls) == 2 and data["cached"] is False
    assert data["cover_note"].startswith("I built a Redis-compatible cache server")
    again = _pack(client, job_id)
    assert again["cached"] is True and again["cover_note"] == data["cover_note"] and len(llm.calls) == 2
    db = SessionLocal()
    assert db.query(JobPack).filter(JobPack.job_id == job_id).count() == 1
    db.close()


def test_cache_invalidated_when_job_changes(client, llm):
    job_id = _job()
    _pack(client, job_id)
    db = SessionLocal()
    db.query(JobOpportunity).filter(JobOpportunity.id == job_id).update({"role": "Platform Engineer"})
    db.commit()
    db.close()
    data = _pack(client, job_id)
    assert data["cached"] is False and data["role"] == "Platform Engineer" and len(llm.calls) == 2


# ---------------- fallback ----------------
def test_llm_failure_falls_back_to_template(client, llm):
    llm.reply = RuntimeError("All LLM providers failed. 429 RESOURCE_EXHAUSTED")
    job_id = _job()
    data = _pack(client, job_id)
    assert data["model"] == "template" and data["cached"] is False
    assert "NIT Rourkela" in data["cover_note"] and "8.99" in data["cover_note"]
    assert "Acme" in data["cover_note"] and "Backend Engineer" in data["cover_note"]
    assert "C++, Kafka and Redis" in data["cover_note"] and "Java" not in data["cover_note"]
    assert word_count(data["cover_note"]) <= COVER_MAX_WORDS
    assert word_count(data["why_company"]) <= WHY_COMPANY_MAX_WORDS
    assert all(a["answer"] for a in data["answers"])
    assert set(data["resume_highlights"]) <= FACT_BULLETS
    assert _pack(client, job_id)["cached"] is True  # cached; ?refresh=1 retries the LLM


def test_garbage_llm_output_falls_back(client, llm):
    llm.reply = ["not", "an", "object"]
    data = _pack(client, _job())
    assert data["model"] == "template" and "NIT Rourkela" in data["cover_note"]


def test_partial_llm_output_fills_gaps_from_template(client, llm):
    llm.reply = {"cover_note": GOOD_LLM["cover_note"], "why_company": ""}
    data = _pack(client, _job())
    assert data["model"] == "gemini-test" and data["cover_note"] == GOOD_LLM["cover_note"]
    assert "Acme is hiring for Backend Engineer" in data["why_company"]
    assert all(a["answer"] for a in data["answers"])


def test_invented_numbers_and_placeholders_rejected(client, llm):
    llm.reply = {**GOOD_LLM,
                 "cover_note": "I cut API latency by 40% at Maruti Suzuki.",
                 "why_company": "I admire [Company] and its mission."}
    data = _pack(client, _job())
    assert "40%" not in data["cover_note"] and "NIT Rourkela" in data["cover_note"]
    assert "[Company]" not in data["why_company"]
    assert data["answers"][0]["answer"] == GOOD_LLM["why_role"]  # valid fields from the LLM are kept


# ---------------- hygiene ----------------
def test_banned_words_markdown_and_emojis_filtered(client, llm):
    long_tail = " ".join(["I built the railway reservation system with Kafka."] * 40)
    llm.reply = {**GOOD_LLM,
                 "cover_note": "**I am passionate about** backend work 🚀. I leverage Kafka to build seamless, "
                               "cutting-edge systems and delve into synergy.\n\n- " + long_tail,
                 "why_role": "## Why\n* I am leveraging my [railway project](https://x.y) to learn more."}
    data = _pack(client, _job())
    text = _all_text(data).lower()
    for w in BANNED_WORDS:
        assert not re.search(rf"\b{re.escape(w)}", text), w
    assert "**" not in text and "##" not in text and "🚀" not in text and "](" not in text
    assert data["cover_note"].startswith("I am interested in backend work")
    assert data["answers"][0]["answer"] == "I am using my railway project to learn more."
    assert word_count(data["cover_note"]) <= COVER_MAX_WORDS


@pytest.mark.parametrize("role,skills", [
    ("Backend Engineer", ["Kafka", "Redis"]), ("Frontend Engineer", ["React"]), ("ML Engineer", ["Python", "LLMs"]),
    ("Software Engineer Intern", []), ("SDE 1", ["C++", "Data structures & algorithms"]),
])
def test_template_is_clean_and_grounded(role, skills):
    job = JobOpportunity(id=1, company="Acme", role=role, location="Hyderabad", skills_required=json.dumps(skills))
    parts = jp.template_pack(job)
    answers = jp.fixed_answers(job)
    text = " ".join(list(parts.values()) + list(answers.values())).lower()
    for w in BANNED_WORDS:
        assert w not in text, w
    assert not jp._EMOJI.search(text) and "*" not in text and "#" not in text
    assert word_count(parts["cover_note"]) <= COVER_MAX_WORDS
    assert word_count(parts["why_company"]) <= WHY_COMPANY_MAX_WORDS
    allowed = jp._allowed_numbers(job)
    assert all(n in allowed for n in re.findall(r"\d+(?:\.\d+)?", text))


# ---------------- errors ----------------
def test_unknown_job_404(client, llm):
    res = client.get("/api/jobs/999999/pack")
    assert res.status_code == 404 and res.get_json()["status"] == "error"
    assert llm.calls == []
