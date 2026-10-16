from api.app import app
from api.domain import job_handoff as jh


def test_create_poll_decide_flow(monkeypatch):
    monkeypatch.setenv("APP_PASSCODE", "")
    sent = []
    monkeypatch.setattr(jh, "_email", lambda h, missing: sent.append((h.company, missing)) or True)
    c = app.test_client()
    r = c.post("/api/jobs/handoff", json={"job_id": 7, "company": "Stripe", "role": "SWE", "url": "https://x/y",
                                          "reason": "CAPTCHA on the form", "missing": ["CAPTCHA"]}).get_json()["data"]
    assert r["choice"] == "pending" and r["emailed"] and sent == [("Stripe", ["CAPTCHA"])]
    hid = r["id"]
    assert c.get(f"/api/jobs/handoff/{hid}").get_json()["data"]["choice"] == "pending"
    page = c.get("/api/jobs/handoff/decide?t=" + jh.sign(hid, "now"))
    assert page.status_code == 200 and b"Bringing it up" in page.data
    assert c.get(f"/api/jobs/handoff/{hid}").get_json()["data"]["choice"] == "now"
    # first decision wins; a later click doesn't flip it
    c.get("/api/jobs/handoff/decide?t=" + jh.sign(hid, "later"))
    assert c.get(f"/api/jobs/handoff/{hid}").get_json()["data"]["choice"] == "now"


def test_bad_links_and_auth(monkeypatch):
    monkeypatch.setenv("APP_PASSCODE", "")
    c = app.test_client()
    assert c.get("/api/jobs/handoff/decide?t=garbage").status_code == 400
    assert jh.verify(jh.sign(1, "now", now=0)) is None  # expired
    monkeypatch.setenv("APP_PASSCODE", "1234")
    assert c.post("/api/jobs/handoff", json={"company": "X"}).status_code == 401  # creating needs the passcode
    assert c.get("/api/jobs/handoff/1").status_code == 401
