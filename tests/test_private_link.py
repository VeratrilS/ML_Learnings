import hashlib

from api.app import app


def test_private_link_requires_passcode(monkeypatch):
    monkeypatch.setenv("APP_PASSCODE", "secret-code")
    client = app.test_client()
    assert client.get("/api/private/link/proof").status_code == 401
    token = hashlib.sha256(b"daily:secret-code").hexdigest()
    res = client.get("/api/private/link/proof", headers={"X-App-Key": token})
    assert res.status_code == 200 and res.get_json()["url"].startswith("https://")
    assert client.get("/api/private/link/nope", headers={"X-App-Key": token}).status_code == 404
