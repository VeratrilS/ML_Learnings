"""Resume tailoring: the guard keeps rewrites factual, reordering is deterministic, the PDF stays one page."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "apply_assist"))
import tailor_resume as tr  # noqa: E402

TEXT = tr._resume_text(tr.RESUME)
REST = "Developed **13 React.js pages** integrated with **120+ REST APIs** (Node.js/Express.js) backed by MongoDB."
KAFKA = ("Architected a car rental and **shared-ride** platform of **8 microservices** communicating over "
         "**14 Kafka topics** with DLQs.")
BACKEND_POSTING = """Backend Engineer. Build scalable distributed systems in C++ and Node.js. Experience with Apache Kafka,
Redis caching, multithreading, PostgreSQL and RESTful services. Design event-driven microservices."""


def check(new, orig=REST, posting=BACKEND_POSTING):
    return tr.check_bullet(orig, new, TEXT, posting)


def test_resume_transcribed():
    assert tr.RESUME["name"] == "Nandam Venkata Sai Raghava"
    assert len(tr.RESUME["education"]) == 2 and len(tr.RESUME["experience"]) == 2
    assert [len(e["bullets"]) for e in tr.RESUME["experience"]] == [3, 3]
    assert [p["name"] for p in tr.RESUME["projects"]] == ["SR-CarRentals", "React-Comps",
                                                         "Cache Server"]
    assert len(tr.RESUME["skills"]) == 4
    assert len(tr.bullet_ids(tr.RESUME)) == 15


@pytest.mark.parametrize("new", [
    "Developed **13 React.js pages** integrated with **120+ RESTful services** (Node.js/Express.js) backed by MongoDB.",
    "Developed **13 React.js pages** consuming **120+ REST APIs** (Node.js/Express.js) backed by MongoDB.",
])
def test_accepts_terminology_rewrite(new):
    assert check(new) is None


def test_accepts_distributed_systems_wording():
    new = ("Architected a distributed car rental and **shared-ride** platform of **8 microservices** communicating "
           "over **14 Kafka topics** with DLQs.")
    assert len(new) <= 1.15 * len(KAFKA) or check(new, KAFKA) == "too long"
    short = "Architected a car rental and **shared-ride** platform of **8 event-driven microservices** over **14 Kafka topics** with DLQs."
    assert check(short, KAFKA) is None


@pytest.mark.parametrize("new", [
    "Developed **13 React.js pages** integrated with **120+ REST APIs** (Spring Boot) backed by MongoDB.",
    "Developed **13 React.js pages** integrated with **120+ REST APIs** (Node.js) backed by MongoDB on AWS.",
    "Developed **13 React.js pages** integrated with **120+ REST APIs** in Java backed by MongoDB.",
    "Developed **13 React.js pages** integrated with **120+ REST APIs** (Node.js/Express.js) on Kubernetes.",
    "Developed **13 React.js pages** at Amazon with **120+ REST APIs** (Node.js/Express.js) backed by MongoDB.",
])
def test_rejects_new_technology_or_employer(new):
    assert check(new).startswith("new term")


@pytest.mark.parametrize("new", [
    "Developed **15 React.js pages** integrated with **120+ REST APIs** (Node.js/Express.js) backed by MongoDB.",
    "Developed **13 React.js pages** integrated with **REST APIs** (Node.js/Express.js) backed by MongoDB.",
    "Developed **13 React.js pages** with **120+ REST APIs** (Node.js/Express.js) cutting latency by 40 ms.",
    "Developed **thirteen React.js pages** with **120+ REST APIs** (Node.js/Express.js) backed by MongoDB.",
])
def test_rejects_changed_numbers(new):
    assert check(new) in ("numbers changed", "number word: thirteen")


@pytest.mark.parametrize("new", [
    "Led development of **13 React.js pages** with **120+ REST APIs** (Node.js/Express.js) backed by MongoDB.",
    "Developed **13 React.js pages** with **120+ REST APIs** (Node.js/Express.js) serving users via MongoDB.",
    "Developed **13 React.js pages** with **120+ REST APIs** (Node.js/Express.js) in production on MongoDB.",
    "Mentored interns on **13 React.js pages** with **120+ REST APIs** (Node.js/Express.js) and MongoDB.",
])
def test_rejects_inflated_claims(new):
    assert check(new).startswith("inflated claim")


def test_rejects_too_long_first_person_emoji_and_bold():
    assert check(REST[:-1] + ", following clean architecture and thorough code review practices throughout.") == "too long"
    assert check("I developed **13 React.js pages** with **120+ REST APIs** (Node.js/Express.js) and MongoDB.") == "first person"
    assert check(REST.replace("MongoDB.", "MongoDB 🚀.")) == "emoji / unsupported character"
    assert check(REST.replace("**13", "13", 1)) == "unbalanced bold markers"


def test_reorders_projects_for_backend_posting():
    new = copy.deepcopy(tr.RESUME)
    changes = tr.reorder(new, BACKEND_POSTING)
    assert [p["name"] for p in new["projects"]] == ["SR-CarRentals", "Cache Server",
                                                   "React-Comps"]
    assert ("Projects order", "SR-CarRentals, React-Comps, Cache Server",
            "SR-CarRentals, Cache Server, React-Comps") in changes
    front = copy.deepcopy(tr.RESUME)
    tr.reorder(front, "Frontend engineer: React, Redux, Firebase, Tailwind, payments with Razorpay.")
    assert front["projects"][0]["name"] == "React-Comps"


def test_reorders_skills_without_adding():
    new = copy.deepcopy(tr.RESUME)
    tr.reorder(new, "We use Python, Kafka and Redis. Postgres experience is a plus. Java and Go welcome.")
    skills = {c["name"]: c["items"] for c in new["skills"]}
    assert skills["Languages"] == ["Python", "C++", "JavaScript", "SQL"]
    assert skills["Backend"][:2] == ["Apache Kafka", "Redis"]
    assert skills["Databases & Tools"][0] == "PostgreSQL"
    for old, cat in zip(tr.RESUME["skills"], new["skills"]):
        assert sorted(old["items"]) == sorted(cat["items"])
    assert [e["title"] for e in new["experience"]] == [e["title"] for e in tr.RESUME["experience"]]


def test_render_is_one_page():
    pdf = tr.render(tr.RESUME)
    assert pdf.startswith(b"%PDF") and tr.page_count(pdf) == 1


def test_tailor_applies_guarded_llm_rewrites():
    good = REST.replace("120+ REST APIs", "120+ RESTful services")
    bad = KAFKA.replace("with DLQs", "with DLQs on Kubernetes")

    def fake(prompt):
        assert "RESTful services" in prompt and "e1.2" in prompt
        return {"bullets": {"e1.2": good, "p1.1": bad, "zz.9": "ignored"}}
    rejected = []
    new, changes = tr.tailor(tr.RESUME, BACKEND_POSTING, "Backend Engineer", "Acme", generate=fake, rejected=rejected)
    assert new["experience"][0]["bullets"][1] == good
    assert KAFKA in new["projects"][0]["bullets"]
    assert ("Experience: Maruti Suzuki India Limited (MSIL)", REST, good) in changes
    assert [r[0] for r in rejected] == ["p1.1"] and rejected[0][3] == "new term: Kubernetes"
    assert tr.RESUME["experience"][0]["bullets"][1] == REST  # input untouched


def test_tailor_survives_llm_failure():
    def boom(prompt):
        raise RuntimeError("quota")
    new, changes = tr.tailor(tr.RESUME, "Sales associate, great communication.", generate=boom)
    assert changes == [] and new == tr.RESUME


def test_tailored_pdf_none_when_nothing_changes(tmp_path):
    pdf, changes = tr.tailored_pdf("Retail sales associate. Great communication skills.", "Sales", "Shop",
                                   generate=None, out_dir=tmp_path)
    assert pdf is None and changes == [] and not list(tmp_path.iterdir())


def test_tailored_pdf_writes_review_files(tmp_path):
    pdf, changes = tr.tailored_pdf(BACKEND_POSTING, "Backend Engineer", "Acme Corp", out_dir=tmp_path)
    assert pdf and tr.page_count(pdf) == 1 and changes
    assert (tmp_path / "Acme_Corp_Backend_Engineer.pdf").read_bytes() == pdf
    assert (tmp_path / "Acme_Corp_Backend_Engineer.json").exists()


def test_tailor_reverts_biggest_growth_on_overflow(monkeypatch):
    small = REST.replace("120+ REST APIs", "120+ RESTful APIs")
    big = REST.replace("120+ REST APIs", "120+ RESTful services")
    calls = iter([2, 1])
    monkeypatch.setattr(tr, "page_count", lambda pdf: next(calls))
    rejected = []
    new, changes = tr.tailor(tr.RESUME, BACKEND_POSTING, generate=lambda p: {"bullets": {"e1.2": big, "p1.1": KAFKA}},
                             rejected=rejected)
    assert new["experience"][0]["bullets"][1] == REST and rejected[-1][3] == "page overflow"
    assert small != big


def test_rejects_dropped_detail():
    orig = "Implemented **JWT authentication** and **role-based access control** (User, Manager, Admin); reviewed backend code."
    new = "Implemented **JWT authentication and authorization** (User, Manager, Admin); reviewed backend code."
    assert check(new, orig) == "drops detail"


def test_contact_comes_from_answers_not_the_repo():
    import tailor_resume as tr
    src = (Path(tr.__file__)).read_text(encoding="utf-8")
    import re
    assert not re.search(r"(?<!\d)[6-9]\d{9}(?!\d)", src) and "@gmail" not in src  # no phone / email in the public repo
    r = tr._with_contact(tr.RESUME, {"phone": "9000000000", "email": "a@b.co"})
    assert r["contact"][0]["text"] == "(+91) 9000000000" and r["contact"][1]["text"] == "a@b.co"
    assert all("key" not in c for c in tr._with_contact(tr.RESUME, {})["contact"])
