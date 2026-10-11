from datetime import datetime, timedelta

import pytest
from flask import Flask

from api.core.config import IST
from api.core.db import Base, engine, SessionLocal
from api.domain import todos as todos_mod
from api.domain.todos import Todo, todos_bp

FIXED_NOW = datetime(2026, 10, 11, 9, 30, tzinfo=IST)
TODAY = FIXED_NOW.date()
YESTERDAY = TODAY - timedelta(days=1)


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(todos_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setattr(todos_mod, "now_ist", lambda: FIXED_NOW)
    yield app.test_client()
    db = SessionLocal()
    db.query(Todo).delete()
    db.commit()
    db.close()


def _add(client, text):
    res = client.post("/api/todos", json={"text": text})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def test_create_and_list(client):
    a = _add(client, "  Solve two LeetCode problems  ")
    b = _add(client, "Watch episode")
    assert a["text"] == "Solve two LeetCode problems"
    assert a["done"] is False and a["carried"] is False
    assert a["day"] == TODAY.isoformat()
    assert b["position"] == a["position"] + 1

    body = client.get("/api/todos").get_json()
    assert body["status"] == "success"
    assert [t["id"] for t in body["data"]] == [a["id"], b["id"]]
    assert body["total"] == 2 and body["done_today"] == 0


def test_validation(client):
    for bad in ["", "   ", None, 42, "x" * 301]:
        res = client.post("/api/todos", json={"text": bad})
        assert res.status_code == 400
        assert res.get_json()["status"] == "error"
        assert res.get_json()["message"]
    assert client.post("/api/todos", data="not json").status_code == 400
    assert client.post("/api/todos", json={"text": "x" * 300}).status_code == 200

    t = _add(client, "ok")
    assert client.put(f"/api/todos/{t['id']}", json={"text": "  "}).status_code == 400
    assert client.put("/api/todos/999999", json={"done": True}).status_code == 404
    assert client.delete("/api/todos/999999").status_code == 404
    assert client.post("/api/todos/reorder", json={"ids": "nope"}).status_code == 400


def test_toggle_and_edit(client):
    a = _add(client, "First")
    b = _add(client, "Second")

    res = client.put(f"/api/todos/{a['id']}", json={"done": True}).get_json()["data"]
    assert res["done"] is True and res["done_at"]

    body = client.get("/api/todos").get_json()
    assert [t["id"] for t in body["data"]] == [b["id"], a["id"]]  # done items sink
    assert body["done_today"] == 1 and body["total"] == 2

    res = client.put(f"/api/todos/{a['id']}", json={"done": False, "text": "First, renamed"}).get_json()["data"]
    assert res["done"] is False and res["done_at"] is None
    assert res["text"] == "First, renamed"


def test_delete(client):
    a = _add(client, "Temp")
    assert client.delete(f"/api/todos/{a['id']}").get_json()["status"] == "success"
    assert client.get("/api/todos").get_json()["total"] == 0


def test_reorder(client):
    a, b, c = (_add(client, x) for x in ("a", "b", "c"))
    res = client.post("/api/todos/reorder", json={"ids": [c["id"], a["id"], b["id"]]})
    assert res.get_json()["status"] == "success"
    ids = [t["id"] for t in client.get("/api/todos").get_json()["data"]]
    assert ids == [c["id"], a["id"], b["id"]]


def test_carry_over(client):
    db = SessionLocal()
    old_open = Todo(text="Unfinished", done=False, day=YESTERDAY, position=1)
    old_done = Todo(text="Finished", done=True, day=YESTERDAY, position=2, done_at=datetime(2026, 10, 10, 6, 0))
    db.add_all([old_open, old_done])
    db.commit()
    open_id, done_id = old_open.id, old_done.id
    db.close()

    fresh = _add(client, "Fresh today")
    body = client.get("/api/todos").get_json()
    by_id = {t["id"]: t for t in body["data"]}

    assert done_id not in by_id
    assert open_id in by_id and fresh["id"] in by_id
    assert by_id[open_id]["carried"] is True
    assert by_id[open_id]["carried_from"] == YESTERDAY.isoformat()
    assert by_id[open_id]["day"] == TODAY.isoformat()
    assert by_id[fresh["id"]]["carried"] is False
    assert body["total"] == 2

    db = SessionLocal()
    assert db.get(Todo, done_id).day == YESTERDAY  # done task stays on its own day
    db.close()

    # Carrying again keeps the original day, and is idempotent.
    body = client.get("/api/todos").get_json()
    assert body["total"] == 2
    assert {t["id"]: t for t in body["data"]}[open_id]["carried_from"] == YESTERDAY.isoformat()
