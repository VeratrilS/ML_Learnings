"""
Runner run reporting and diagnostic summary for local apply runner.
Stores run metadata, submitted jobs, handoffs needed, failures, and learned rules.

Endpoints (blueprint job_runner_report_bp, prefix /api/jobs; passcode-protected):
  POST /api/jobs/runner-report        Stores the runner's run summary JSON
  GET  /api/jobs/runner-report?limit= Returns the last N runner runs
  POST /api/jobs/runner-email         {subject, text, html?} -> emails Sai (the laptop's network can block SMTP)
"""
from datetime import datetime, timezone
import json
import os
from flask import Blueprint, jsonify, request
from sqlalchemy import Column, DateTime, Integer, Text
from api.core.db import Base, SessionLocal, engine


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class JobRunnerRun(Base):
    __tablename__ = "job_runner_runs"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    submitted_count = Column(Integer, default=0)
    needs_you_count = Column(Integer, default=0)
    unconfirmed_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    payload = Column(Text, nullable=False)  # JSON
    created_at = Column(DateTime, default=_utcnow, nullable=False)


job_runner_report_bp = Blueprint("job_runner_report", __name__, url_prefix="/api/jobs")


@job_runner_report_bp.record_once
def _ensure_table(state):
    try:
        JobRunnerRun.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        print(f"job_runner_runs check skipped: {e}")


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        return None


@job_runner_report_bp.route("/runner-report", methods=["POST"])
def post_runner_report():
    data = request.get_json(silent=True) or {}
    submitted = data.get("submitted") or []
    needs_you = data.get("needs_you") or []
    unconfirmed = data.get("unconfirmed") or []
    failed = data.get("failed") or []

    started_at = _parse_iso(data.get("started_at"))
    finished_at = _parse_iso(data.get("finished_at"))

    db = SessionLocal()
    try:
        run = JobRunnerRun(
            started_at=started_at,
            finished_at=finished_at,
            submitted_count=len(submitted),
            needs_you_count=len(needs_you),
            unconfirmed_count=len(unconfirmed),
            failed_count=len(failed),
            payload=json.dumps(data),
            created_at=_utcnow(),
        )
        db.add(run)
        db.commit()
        return jsonify({
            "status": "success",
            "data": {
                "id": run.id,
                "submitted_count": run.submitted_count,
                "needs_you_count": run.needs_you_count,
                "unconfirmed_count": run.unconfirmed_count,
                "failed_count": run.failed_count,
                "created_at": run.created_at.isoformat() + "Z",
            }
        })
    finally:
        db.close()


@job_runner_report_bp.route("/runner-report", methods=["GET"])
def get_runner_report():
    try:
        limit = min(50, max(1, int(request.args.get("limit", 5))))
    except ValueError:
        limit = 5

    db = SessionLocal()
    try:
        rows = db.query(JobRunnerRun).order_by(JobRunnerRun.created_at.desc()).limit(limit).all()
        result = []
        for r in rows:
            try:
                body = json.loads(r.payload)
            except Exception:
                body = {}
            result.append({
                "id": r.id,
                "started_at": r.started_at.isoformat() + "Z" if r.started_at else None,
                "finished_at": r.finished_at.isoformat() + "Z" if r.finished_at else None,
                "submitted_count": r.submitted_count,
                "needs_you_count": r.needs_you_count,
                "unconfirmed_count": r.unconfirmed_count,
                "failed_count": r.failed_count,
                "created_at": r.created_at.isoformat() + "Z",
                "summary": body,
            })
        return jsonify({"status": "success", "data": result})
    finally:
        db.close()


@job_runner_report_bp.route("/runner-email", methods=["POST"])
def runner_email():
    """Sends the runner's end-of-run email from the server. Always to Sai (RECEIVER_EMAIL), never elsewhere."""
    from api.core.clients import EmailClient
    from api.core.config import RECEIVER_EMAIL
    data = request.get_json(silent=True) or {}
    subject, text = str(data.get("subject") or "").strip()[:200], str(data.get("text") or "")[:100000]
    if not subject or not text:
        return jsonify({"status": "error", "message": "subject and text are required"}), 400
    sender, password = os.getenv("SENDER_EMAIL"), os.getenv("SENDER_PASSWORD")
    if not (sender and password):
        return jsonify({"status": "error", "message": "Email not configured"}), 503
    html = str(data.get("html") or "")[:300000] or None
    ok = EmailClient(sender, password).send_email(RECEIVER_EMAIL, subject, text, html=html)
    return jsonify({"status": "success" if ok else "error", "data": {"sent": bool(ok)}}), (200 if ok else 502)
