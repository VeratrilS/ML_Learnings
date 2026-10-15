import io

from api.app import app
from api.domain import job_resume_file as rf


def test_upload_info_download_and_key(monkeypatch):
    monkeypatch.setenv("APP_PASSCODE", "")
    c = app.test_client()
    pdf = b"%PDF-1.4 test resume"
    r = c.post("/api/jobs/resume-upload", data={"file": (io.BytesIO(pdf), "My Resume.pdf")}, content_type="multipart/form-data")
    assert r.status_code == 200 and r.get_json()["data"]["size"] == len(pdf)
    info = c.get("/api/jobs/resume-file/info").get_json()["data"]
    assert info["uploaded"] and info["url"].endswith(rf.resume_key())
    ok = c.get(f"/api/jobs/resume-file?k={rf.resume_key()}")
    assert ok.status_code == 200 and ok.data == pdf and ok.headers["Access-Control-Allow-Origin"] == "*"
    assert c.get("/api/jobs/resume-file?k=wrong").status_code == 404


def test_rejects_non_pdf_and_upload_needs_passcode(monkeypatch):
    monkeypatch.setenv("APP_PASSCODE", "")
    c = app.test_client()
    bad = c.post("/api/jobs/resume-upload", data={"file": (io.BytesIO(b"hello"), "x.pdf")}, content_type="multipart/form-data")
    assert bad.status_code == 400
    monkeypatch.setenv("APP_PASSCODE", "1234")
    locked = c.post("/api/jobs/resume-upload", data={"file": (io.BytesIO(b"%PDF-1"), "x.pdf")}, content_type="multipart/form-data")
    assert locked.status_code == 401  # upload stays behind the passcode
