from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from flask import Flask

import api.domain.models  # noqa: F401  (registers the settings table on Base)
from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine
from api.domain.models import Settings
from api.domain.repositories import NotificationRepository
from api.domain.syllabus import (CourseMaterial, REMIND_SETTING, SEED_SUBJECTS, Subject, SyllabusTopic, parse_syllabus,
                                 short_name, syllabus_bp)


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(syllabus_bp)
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db(client):
    def wipe():
        db = SessionLocal()
        try:
            db.query(CourseMaterial).delete()
            db.query(SyllabusTopic).delete()
            db.query(Subject).delete()
            db.query(Settings).filter(Settings.key.in_(["syllabus_seeded", REMIND_SETTING])).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()
    wipe()
    # Most tests want an empty tracker, not the seeded course list
    db = SessionLocal()
    NotificationRepository(db).set_setting("syllabus_seeded", "1")
    db.close()
    yield
    wipe()


@pytest.fixture
def email_env(monkeypatch):
    monkeypatch.setenv("SENDER_EMAIL", "me@example.com")
    monkeypatch.setenv("SENDER_PASSWORD", "secret")


def _subject(client, **body):
    body.setdefault("name", "Software Testing")
    r = client.post("/api/syllabus/subjects", json=body)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


def _paste(client, sid, text):
    r = client.post(f"/api/syllabus/subjects/{sid}/topics", json={"text": text})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


def _add_topic(client, sid, title, unit="Unit 1"):
    r = client.post(f"/api/syllabus/subjects/{sid}/topics", json={"unit": unit, "title": title})
    assert r.status_code == 201, r.get_json()
    subj = r.get_json()["data"]
    for u in subj["units"]:
        for t in u["topics"]:
            if t["title"] == title:
                return t
    raise ValueError(f"Topic {title} not found in response")


def _topic_ids(subject):
    return [t["id"] for u in subject["units"] for t in u["topics"]]


def _list(client):
    r = client.get("/api/syllabus")
    assert r.status_code == 200
    return r.get_json()


# ---------------- seeding ----------------
def test_seeds_real_courses_once(client):
    db = SessionLocal()
    db.query(Settings).filter(Settings.key == "syllabus_seeded").delete()
    db.commit()
    db.close()

    data = _list(client)["data"]
    assert len(data) == len(SEED_SUBJECTS)
    by_code = {s["code"]: s for s in data}
    ngns = by_code["CS6319"]
    assert ngns["name"] == "Next Generation Networking Systems"
    assert ngns["short"] == "NGNS"
    assert ngns["faculty"] == "Judhistir Mahapatro"
    assert ngns["kind"] == "theory"
    assert by_code["CS6172"]["kind"] == "lab"
    assert by_code["CS4901"]["kind"] == "other"
    theory_colors = {s["color"] for s in data if s["kind"] == "theory"}
    assert len(theory_colors) == 3  # each theory subject gets its own accent
    assert all(s["total"] == 0 and s["exam_date"] is None for s in data)

    # Deleting everything must not re-seed
    for s in data:
        client.delete(f"/api/syllabus/subjects/{s['id']}")
    assert _list(client)["data"] == []


# ---------------- subjects CRUD ----------------
def test_subject_crud(client):
    s = _subject(client, name="Deep Learning", code="CS6510", faculty="P. Bhattacharjee", exam_date="2030-05-02", color="rose")
    assert s["code"] == "CS6510" and s["faculty"] == "P. Bhattacharjee" and s["kind"] == "theory"
    assert s["exam_date"] == "2030-05-02" and s["progress"] == 0 and s["units"] == []

    r = client.put(f"/api/syllabus/subjects/{s['id']}", json={"name": "DL", "exam_date": "", "kind": "lab", "code": ""})
    d = r.get_json()["data"]
    assert d["name"] == "DL" and d["exam_date"] is None and d["kind"] == "lab" and d["code"] is None

    assert client.post("/api/syllabus/subjects", json={"name": "  "}).status_code == 400
    assert client.post("/api/syllabus/subjects", json={"name": "X", "exam_date": "31-12-2030"}).status_code == 400
    assert client.post("/api/syllabus/subjects", json={"name": "X", "kind": "elective"}).status_code == 400
    assert client.put("/api/syllabus/subjects/99999", json={"name": "x"}).status_code == 404

    _paste(client, s["id"], "Unit 1: Intro\nPerceptron\nBackprop")
    assert client.delete(f"/api/syllabus/subjects/{s['id']}").status_code == 200
    db = SessionLocal()
    try:
        assert db.query(SyllabusTopic).count() == 0  # topics cascade
    finally:
        db.close()
    assert client.delete(f"/api/syllabus/subjects/{s['id']}").status_code == 404


def test_ordering_and_days_left(client):
    today = now_ist().date()
    _subject(client, name="No date")
    _subject(client, name="Later", exam_date=(today + timedelta(days=20)).isoformat())
    _subject(client, name="Soon", exam_date=(today + timedelta(days=3)).isoformat())
    _subject(client, name="Lab soon", kind="lab", exam_date=(today + timedelta(days=1)).isoformat())
    _subject(client, name="Past", exam_date=(today - timedelta(days=2)).isoformat())

    body = _list(client)
    names = [s["name"] for s in body["data"]]
    assert names == ["Lab soon", "Soon", "Later", "No date", "Past"]
    by_name = {s["name"]: s for s in body["data"]}
    assert by_name["Soon"]["days_left"] == 3
    assert by_name["No date"]["days_left"] is None
    assert by_name["Past"]["days_left"] == -2
    # next_exam ignores labs and past exams
    assert body["next_exam"]["subject"] == "Soon"
    assert body["next_exam"]["days_left"] == 3


def test_next_exam_null_without_dates(client):
    _subject(client, name="A")
    assert _list(client)["next_exam"] is None


# ---------------- topics ----------------
def test_single_topic_and_updates(client):
    s = _subject(client)
    r = client.post(f"/api/syllabus/subjects/{s['id']}/topics", json={"unit": "Unit 1", "title": "  Test   oracles "})
    assert r.status_code == 201
    d = r.get_json()["data"]
    assert d["units"] == [{"unit": "Unit 1", "topics": [d["units"][0]["topics"][0]]}]
    t = d["units"][0]["topics"][0]
    assert t["title"] == "Test oracles" and t["done"] is False and t["confidence"] is None and t["last_studied_at"] is None

    assert client.post(f"/api/syllabus/subjects/{s['id']}/topics", json={"title": ""}).status_code == 400

    r = client.put(f"/api/syllabus/topics/{t['id']}", json={"done": True, "confidence": 2, "studied": True})
    u = r.get_json()["data"]
    assert u["done"] is True and u["done_at"] and u["confidence"] == 2 and u["last_studied_at"]

    assert client.put(f"/api/syllabus/topics/{t['id']}", json={"confidence": 4}).status_code == 400
    assert client.put(f"/api/syllabus/topics/{t['id']}", json={"confidence": True}).status_code == 400
    u = client.put(f"/api/syllabus/topics/{t['id']}", json={"confidence": None, "done": False, "title": "Oracles"}).get_json()["data"]
    assert u["confidence"] is None and u["done"] is False and u["done_at"] is None and u["title"] == "Oracles"

    assert client.delete(f"/api/syllabus/topics/{t['id']}").status_code == 200
    assert client.delete(f"/api/syllabus/topics/{t['id']}").status_code == 404
    assert client.put("/api/syllabus/topics/99999", json={"done": True}).status_code == 404


def test_progress(client):
    s = _subject(client)
    d = _paste(client, s["id"], "a1\na2\na3\na4\na5\na6\na7\na8")
    ids = _topic_ids(d)
    for tid in ids[:5]:
        client.put(f"/api/syllabus/topics/{tid}", json={"done": True})
    got = _list(client)["data"][0]
    assert got["total"] == 8 and got["done"] == 5 and got["progress"] == 62


# ---------------- bulk parsing ----------------
def test_parse_unit_colon_format():
    text = """
    Unit 1: Introduction
    Software testing fundamentals
    - Errors, faults and failures
    Unit 2: Black box testing
    1. Equivalence class partitioning
    2. Boundary value analysis
    """
    assert parse_syllabus(text) == [
        ("Unit 1 · Introduction", "Software testing fundamentals"),
        ("Unit 1 · Introduction", "Errors"),
        ("Unit 1 · Introduction", "faults and failures"),
        ("Unit 2 · Black box testing", "Equivalence class partitioning"),
        ("Unit 2 · Black box testing", "Boundary value analysis"),
    ]


def test_parse_roman_and_dash_headers_with_hours():
    text = """UNIT-II Testing techniques (9 Hrs)
    • Decision table based testing
    UNIT – III: White Box Testing [8 hours]
    a) Path testing
    b) Data flow testing
    Module 3 - Software Defined Networking
    * OpenFlow (v1.3), P4
    MODULE IV
    Network function virtualization."""
    got = parse_syllabus(text)
    assert got == [
        ("Unit 2 · Testing techniques", "Decision table based testing"),
        ("Unit 3 · White Box Testing", "Path testing"),
        ("Unit 3 · White Box Testing", "Data flow testing"),
        ("Module 3 · Software Defined Networking", "OpenFlow (v1.3)"),
        ("Module 3 · Software Defined Networking", "P4"),
        ("Module 4", "Network function virtualization"),
    ]


def test_parse_comma_paragraph_with_heading_and_parentheses():
    text = ("Unit 4: Deep networks\n"
            "Optimization: SGD, momentum, Adam; learning rate schedules\n"
            "Regularization (dropout, weight decay, batch norm)\n"
            "CNNs, RNNs and LSTMs, Transformers\n")
    titles = [t for _, t in parse_syllabus(text)]
    assert titles == ["Optimization", "SGD", "momentum", "Adam", "learning rate schedules",
                      "Regularization (dropout, weight decay, batch norm)",
                      "CNNs", "RNNs and LSTMs", "Transformers"]


def test_parse_topics_before_any_unit_and_default_unit():
    assert parse_syllabus("Test planning\nTest metrics") == [(None, "Test planning"), (None, "Test metrics")]
    assert parse_syllabus("Test planning", default_unit="Unit 5") == [("Unit 5", "Test planning")]


def test_parse_ignores_noise_and_stops_at_textbooks():
    text = """Unit 1 Introduction to networking
    1.1 Network architecture
    10
    Unit testing vs integration testing
    Text Books:
    1. Kurose & Ross, Computer Networking
    """
    got = parse_syllabus(text)
    # "Unit testing ..." is a topic, not a unit header; numbers-only lines are dropped; text books ignored
    assert got == [
        ("Unit 1 · Introduction to networking", "Network architecture"),
        ("Unit 1 · Introduction to networking", "Unit testing vs integration testing"),
    ]


def test_parse_markdown_paste():
    text = "## Chapter 2: Queueing\n### Topics\n- M/M/1 queue\n- 2.5G networks\n- Little's law\n"
    assert parse_syllabus(text) == [
        ("Chapter 2 · Queueing", "M/M/1 queue"),
        ("Chapter 2 · Queueing", "2.5G networks"),
        ("Chapter 2 · Queueing", "Little's law"),
    ]


def test_bulk_paste_endpoint_appends_in_order(client):
    s = _subject(client)
    _paste(client, s["id"], "Unit 1: Basics\nA\nB")
    d = _paste(client, s["id"], "Unit 2: More\nC")
    assert [u["unit"] for u in d["units"]] == ["Unit 1 · Basics", "Unit 2 · More"]
    assert [t["title"] for u in d["units"] for t in u["topics"]] == ["A", "B", "C"]
    r = client.post(f"/api/syllabus/subjects/{s['id']}/topics", json={"text": "\n  \n 12 \n"})
    assert r.status_code == 400


def test_short_name():
    assert short_name("Next Generation Networking Systems") == "NGNS"
    assert short_name("Software Testing") is None
    assert short_name("Seminar and Technical Writing") == "STW"


# ---------------- reminder ----------------
def _setup_reminder_data(client):
    today = now_ist().date()
    st = _subject(client, name="Software Testing", exam_date=(today + timedelta(days=9)).isoformat())
    d = _paste(client, st["id"], "Unit 1: Intro\nOracles\nMutation testing\nUnit 2: Black box\nBVA\nECP")
    ids = _topic_ids(d)
    client.put(f"/api/syllabus/topics/{ids[0]}", json={"done": True})
    client.put(f"/api/syllabus/topics/{ids[1]}", json={"confidence": 3, "studied": True})
    client.put(f"/api/syllabus/topics/{ids[3]}", json={"confidence": 1})
    lab = _subject(client, name="Software Testing Laboratory", kind="lab", exam_date=(today + timedelta(days=2)).isoformat())
    _paste(client, lab["id"], "Selenium basics")
    return ids


def test_remind_skips_without_email_config(client, monkeypatch):
    monkeypatch.delenv("SENDER_EMAIL", raising=False)
    monkeypatch.delenv("SENDER_PASSWORD", raising=False)
    _setup_reminder_data(client)
    with patch("api.domain.syllabus.EmailClient") as mock_cls:
        body = client.post("/api/syllabus/remind?force=1").get_json()
    assert body["status"] == "skipped"
    mock_cls.assert_not_called()


def test_remind_skips_when_nothing_left(client, email_env):
    s = _subject(client)
    d = _paste(client, s["id"], "Only topic")
    client.put(f"/api/syllabus/topics/{_topic_ids(d)[0]}", json={"done": True})
    lab = _subject(client, name="Lab", kind="lab")
    _paste(client, lab["id"], "Unfinished lab topic")  # labs don't count
    with patch("api.domain.syllabus.EmailClient") as mock_cls:
        body = client.post("/api/syllabus/remind?force=1").get_json()
    assert body["status"] == "skipped"
    mock_cls.assert_not_called()


def test_remind_content_and_36h_throttle(client, email_env):
    _setup_reminder_data(client)
    with patch("api.domain.syllabus.EmailClient") as mock_cls:
        mock_cls.return_value.send_email.return_value = True
        r = client.post("/api/syllabus/remind")
        assert r.get_json()["status"] == "success"
        to, subject_line, plain, = mock_cls.return_value.send_email.call_args.args[:3]
        html = mock_cls.return_value.send_email.call_args.kwargs["html"]
        assert subject_line == "📚 Study reminder · Software Testing exam in 9 days · 25% covered"
        assert "/#/study" in html and "Study next" in html
        assert "Laboratory" not in html and "Selenium" not in plain
        # Low confidence first, then never studied, then the confidently-studied one
        order = [line.strip("- ").strip() for line in plain.splitlines() if line.startswith("  - ")]
        assert [o.split(" [")[0] for o in order] == ["BVA", "ECP", "Mutation testing"]

        # Second call within 36h is throttled...
        body = client.post("/api/syllabus/remind").get_json()
        assert body["status"] == "skipped"
        assert mock_cls.return_value.send_email.call_count == 1
        # ...unless forced
        assert client.post("/api/syllabus/remind?force=1").get_json()["status"] == "success"
        assert mock_cls.return_value.send_email.call_count == 2

        # After 36h it goes out again
        db = SessionLocal()
        old = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=37)).isoformat(timespec="seconds")
        NotificationRepository(db).set_setting(REMIND_SETTING, old)
        db.close()
        assert client.post("/api/syllabus/remind").get_json()["status"] == "success"
        assert mock_cls.return_value.send_email.call_count == 3


def test_remind_failure_does_not_mark_sent(client, email_env):
    _setup_reminder_data(client)
    with patch("api.domain.syllabus.EmailClient") as mock_cls:
        mock_cls.return_value.send_email.return_value = False
        r = client.post("/api/syllabus/remind")
        assert r.status_code == 502
    db = SessionLocal()
    try:
        assert NotificationRepository(db).get_setting(REMIND_SETTING) is None
    finally:
        db.close()


def test_exam_date_round_trip(client):
    s = _subject(client, exam_date="2031-01-15")
    assert date.fromisoformat(s["exam_date"]) == date(2031, 1, 15)


def test_topic_generate_notes(client):
    s = _subject(client, name="Deep Learning")
    t = _add_topic(client, s["id"], title="Backpropagation and Gradient Descent", unit="Unit 2")
    assert t.get("notes") is None

    # Call AI generation endpoint
    r = client.post(f"/api/syllabus/topics/{t['id']}/generate")
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["notes"] is not None
    assert "Backpropagation" in data["notes"] or "Core Concept" in data["notes"]
    assert data["notes_generated_at"] is not None

    # Verify 404 for unknown topic
    assert client.post("/api/syllabus/topics/999999/generate").status_code == 404


def test_topic_update_notes(client):
    s = _subject(client, name="Operating Systems")
    t = _add_topic(client, s["id"], title="Semaphores", unit="Unit 1")
    r = client.put(f"/api/syllabus/topics/{t['id']}/notes", json={"notes": "Custom revision summary for semaphores."})
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["notes"] == "Custom revision summary for semaphores."
    assert data["notes_generated_at"] is not None


def test_course_materials_crud_and_cascade(client):
    s = _subject(client, name="Software Testing")

    # Add materials
    r1 = client.post(f"/api/syllabus/subjects/{s['id']}/materials", json={
        "title": "Unit 1 Lecture Slides",
        "category": "lecture_notes",
        "url": "https://example.com/slides1.pdf",
        "content": "Comprehensive slides covering black box testing and boundaries.",
    })
    assert r1.status_code == 201
    mat1 = r1.get_json()["data"]
    assert mat1["title"] == "Unit 1 Lecture Slides"
    assert mat1["category"] == "lecture_notes"
    assert mat1["url"] == "https://example.com/slides1.pdf"

    r2 = client.post(f"/api/syllabus/subjects/{s['id']}/materials", json={
        "title": "Boundary Value Analysis Cheatsheet",
        "category": "cheatsheet",
        "url": "",
        "content": "Formula: 4n + 1 test cases for robust testing.",
    })
    assert r2.status_code == 201
    mat2 = r2.get_json()["data"]

    # Validation: empty title
    assert client.post(f"/api/syllabus/subjects/{s['id']}/materials", json={"title": "  "}).status_code == 400

    # List materials
    r_list = client.get(f"/api/syllabus/subjects/{s['id']}/materials")
    assert r_list.status_code == 200
    items = r_list.get_json()["data"]
    assert len(items) == 2
    assert items[0]["id"] == mat2["id"]  # newest first

    # Subject summary includes materials
    subj_list = client.get("/api/syllabus").get_json()["data"]
    found_s = next(x for x in subj_list if x["id"] == s["id"])
    assert found_s["materials_count"] == 2
    assert len(found_s["materials"]) == 2

    # Update material
    r_edit = client.put(f"/api/syllabus/materials/{mat1['id']}", json={
        "title": "Unit 1 Updated Slides",
        "category": "lecture_notes",
    })
    assert r_edit.status_code == 200
    assert r_edit.get_json()["data"]["title"] == "Unit 1 Updated Slides"

    # Delete one material
    assert client.delete(f"/api/syllabus/materials/{mat1['id']}").status_code == 200
    assert client.delete(f"/api/syllabus/materials/{mat1['id']}").status_code == 404

    # Subject cascade delete removes remaining materials
    db = SessionLocal()
    try:
        assert db.query(CourseMaterial).count() == 1
    finally:
        db.close()
    client.delete(f"/api/syllabus/subjects/{s['id']}")
    db = SessionLocal()
    try:
        assert db.query(CourseMaterial).count() == 0
    finally:
        db.close()
