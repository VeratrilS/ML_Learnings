import pytest
from flask import Flask

from api.core.db import Base, engine, SessionLocal
from api.domain.notes import Note, notes_bp


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(notes_bp)
    Base.metadata.create_all(bind=engine)
    yield app


@pytest.fixture
def client(app):
    yield app.test_client()
    db = SessionLocal()
    db.query(Note).delete()
    db.commit()
    db.close()


def _add(client, **kw):
    res = client.post("/api/notes", json=kw)
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _list(client, qs=""):
    res = client.get(f"/api/notes{qs}")
    assert res.status_code == 200
    return res.get_json()["data"]


def test_create_get_and_list(client):
    n = _add(client, title="  Two pointers ", body="# Idea\nShrink the window.", tags="DSA, #arrays, dsa")
    assert n["title"] == "Two pointers"
    assert n["tags"] == ["dsa", "arrays"]
    assert n["pinned"] is False and n["color"] == ""
    assert n["created_at"] and n["updated_at"]
    got = client.get(f"/api/notes/{n['id']}").get_json()["data"]
    assert got["body"].startswith("# Idea")
    items = _list(client)
    assert len(items) == 1 and "body" not in items[0]
    assert items[0]["snippet"].startswith("# Idea")


def test_create_empty_note_allowed(client):
    n = _add(client)
    assert n["title"] == "" and n["body"] == "" and n["tags"] == []


def test_update_and_validation(client):
    n = _add(client, title="A")
    res = client.put(f"/api/notes/{n['id']}", json={"body": "new body", "tags": ["x", "Y"], "color": "ok"})
    d = res.get_json()["data"]
    assert d["body"] == "new body" and d["tags"] == ["x", "y"] and d["color"] == "ok"
    assert client.put(f"/api/notes/{n['id']}", json={"color": "purple"}).status_code == 400
    assert client.put(f"/api/notes/{n['id']}", json={"title": "x" * 201}).status_code == 400
    assert client.put(f"/api/notes/{n['id']}", json={"tags": 5}).status_code == 400
    assert client.post("/api/notes", json={"title": 3}).status_code == 400
    # failed update didn't persist anything
    assert client.get(f"/api/notes/{n['id']}").get_json()["data"]["color"] == "ok"


def test_delete_and_404(client):
    n = _add(client, title="gone")
    assert client.delete(f"/api/notes/{n['id']}").status_code == 200
    assert client.get(f"/api/notes/{n['id']}").status_code == 404
    assert client.put(f"/api/notes/{n['id']}", json={"title": "x"}).status_code == 404
    assert client.post(f"/api/notes/{n['id']}/pin").status_code == 404


def test_pin_toggle_and_order(client):
    a = _add(client, title="first")
    b = _add(client, title="second")
    res = client.post(f"/api/notes/{a['id']}/pin")
    assert res.get_json()["data"]["pinned"] is True
    ids = [n["id"] for n in _list(client)]
    assert ids[0] == a["id"]
    assert client.post(f"/api/notes/{a['id']}/pin").get_json()["data"]["pinned"] is False
    assert client.post(f"/api/notes/{b['id']}/pin", json={"pinned": True}).get_json()["data"]["pinned"] is True
    assert client.post(f"/api/notes/{b['id']}/pin", json={"pinned": True}).get_json()["data"]["pinned"] is True


def test_search_title_first_with_snippet(client):
    body_hit = _add(client, title="Misc", body="lots of text " * 30 + "about heaps here " + "tail " * 50)
    title_hit = _add(client, title="Heaps cheat sheet", body="priority queue")
    _add(client, title="Unrelated", body="graphs")
    tag_hit = _add(client, title="Other", tags="heaps")
    # make the body hit the most recently updated, so ordering must come from title-first
    client.put(f"/api/notes/{body_hit['id']}", json={"body": "lots of text " * 30 + "about heaps here " + "tail " * 50})
    items = _list(client, "?q=HEAPS")
    ids = [n["id"] for n in items]
    assert ids[0] == title_hit["id"]
    assert set(ids) == {body_hit["id"], title_hit["id"], tag_hit["id"]}
    snip = next(n for n in items if n["id"] == body_hit["id"])["snippet"]
    assert "heaps" in snip and snip.startswith("…") and snip.endswith("…")


def test_tag_filter_and_counts(client):
    _add(client, title="a", tags="dp,graphs")
    _add(client, title="b", tags="dp")
    _add(client, title="c", tags="dpx")
    assert {n["title"] for n in _list(client, "?tag=dp")} == {"a", "b"}
    assert {n["title"] for n in _list(client, "?tag=DP&q=a")} == {"a"}
    tags = client.get("/api/notes/tags").get_json()["data"]
    assert tags == [{"tag": "dp", "count": 2}, {"tag": "dpx", "count": 1}, {"tag": "graphs", "count": 1}]
