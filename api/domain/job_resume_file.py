"""
Sai's resume PDF for the Autofill bookmarklet.

The repo is public and the resume has a phone number, so the PDF lives in the database, never in git.
The bookmarklet runs on a company's application page, so it can't send the app passcode; instead it gets a
read-only URL carrying a key derived from the passcode that only unlocks this one file.

  POST /api/jobs/resume-upload      (passcode)  multipart "file": a PDF up to 2 MB; replaces the stored one
  GET  /api/jobs/resume-file/info   (passcode)  -> {uploaded, filename, size, uploaded_at, url}
  GET  /api/jobs/resume-file?k=KEY  (open, key-checked, CORS *)  -> the PDF bytes
"""
import hashlib
import hmac
import os
import re
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import Column, DateTime, Integer, LargeBinary, String

from api.core.config import APP_URL
from api.core.db import Base, SessionLocal, engine

MAX_BYTES = 2 * 1024 * 1024


class ResumeFile(Base):
    __tablename__ = "resume_files"
    id = Column(Integer, primary_key=True)  # single row, id = 1
    filename = Column(String(200), nullable=False)
    content = Column(LargeBinary, nullable=False)
    uploaded_at = Column(DateTime, nullable=False)


job_resume_file_bp = Blueprint("job_resume_file", __name__, url_prefix="/api/jobs")


@job_resume_file_bp.record_once
def _ensure_table(state):
    try:
        ResumeFile.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        print(f"resume_files check skipped: {e}")


def resume_key():
    secret = os.getenv("APP_PASSCODE") or os.getenv("STUDIO_SECRET") or "local-dev-secret"
    return hmac.new(secret.encode(), b"resume-file-v1", hashlib.sha256).hexdigest()[:32]


def resume_url():
    return f"{APP_URL.rstrip('/')}/api/jobs/resume-file?k={resume_key()}"


def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Cache-Control"] = "private, max-age=300"
    return resp


@job_resume_file_bp.route("/resume-upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"status": "error", "message": "Send the PDF as multipart field 'file'."}), 400
    data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return jsonify({"status": "error", "message": "Resume must be 2 MB or smaller."}), 413
    if not data.startswith(b"%PDF"):
        return jsonify({"status": "error", "message": "Resume must be a PDF."}), 400
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", f.filename or "Resume.pdf")[:120] or "Resume.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    db = SessionLocal()
    try:
        row = db.get(ResumeFile, 1) or ResumeFile(id=1)
        row.filename, row.content = name, data
        row.uploaded_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.merge(row)
        db.commit()
        return jsonify({"status": "success", "data": {"filename": name, "size": len(data), "url": resume_url()}})
    finally:
        db.close()


@job_resume_file_bp.route("/resume-file/info", methods=["GET"])
def info():
    db = SessionLocal()
    try:
        row = db.get(ResumeFile, 1)
        if not row:
            return jsonify({"status": "success", "data": {"uploaded": False, "url": None}})
        return jsonify({"status": "success", "data": {
            "uploaded": True, "filename": row.filename, "size": len(row.content),
            "uploaded_at": row.uploaded_at.isoformat() + "Z", "url": resume_url()}})
    finally:
        db.close()


@job_resume_file_bp.route("/resume-file", methods=["GET", "OPTIONS"])
def download():
    if request.method == "OPTIONS":
        return _cors(Response(status=204))
    if not hmac.compare_digest(request.args.get("k", ""), resume_key()):
        return _cors(Response("Not found", status=404))
    db = SessionLocal()
    try:
        row = db.get(ResumeFile, 1)
        if not row:
            return _cors(Response("No resume uploaded", status=404))
        resp = Response(row.content, mimetype="application/pdf")
        resp.headers["Content-Disposition"] = f'inline; filename="{row.filename}"'
        return _cors(resp)
    finally:
        db.close()
