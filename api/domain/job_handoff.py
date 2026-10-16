"""
Hand-off between the local apply runner and Sai, through the app database ("shared memory").

When the runner on Sai's laptop hits something it must not do alone (CAPTCHA, login, a question it can't
answer truthfully), it creates a hand-off here. The app emails Sai two buttons — "Complete it now" / "Later" —
and stores his choice; the runner polls for it and brings the window up (now) or moves on (later).

  POST /api/jobs/handoff              (passcode)  {job_id?, company, role, url, reason, missing[]} -> {id, choice}
  GET  /api/jobs/handoff/<id>         (passcode)  -> {id, choice: pending|now|later, decided_at}
  GET  /api/jobs/handoff/decide?t=…   (open, signed link from the email)  -> records the choice, small HTML page
"""
import base64
import hashlib
import hmac
import html
import json
import os
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, DateTime, Integer, String, Text

from api.core import config
from api.core.db import Base, SessionLocal, engine
from api.domain.job_approvals import _page

CHOICES = ("now", "later", "done")
LINK_TTL = 24 * 3600


class JobHandoff(Base):
    __tablename__ = "job_handoffs"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, nullable=True)
    company = Column(String(200), nullable=True)
    role = Column(String(300), nullable=True)
    url = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    missing = Column(Text, nullable=True)  # JSON list of questions/fields
    choice = Column(String(10), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False)
    decided_at = Column(DateTime, nullable=True)


job_handoff_bp = Blueprint("job_handoff", __name__, url_prefix="/api/jobs")


@job_handoff_bp.record_once
def _ensure_table(state):
    try:
        JobHandoff.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        print(f"job_handoffs check skipped: {e}")


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _secret():
    base = os.getenv("APP_PASSCODE") or os.getenv("STUDIO_SECRET") or "local-dev-secret"
    return hashlib.sha256(f"job-handoff:{base}".encode()).digest()


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def sign(handoff_id, choice, now=None):
    expiry = int((now if now is not None else time.time()) + LINK_TTL)
    payload = _b64(f"{int(handoff_id)}.{choice}.{expiry}".encode())
    sig = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify(token, now=None):
    try:
        payload, sig = (token or "").split(".")
        if not hmac.compare_digest(sig, _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())):
            return None
        hid, choice, expiry = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode().split(".")
        if choice not in CHOICES or int(expiry) < (now if now is not None else time.time()):
            return None
        return int(hid), choice
    except (ValueError, TypeError, UnicodeDecodeError):
        return None


def decide_url(handoff_id, choice):
    return f"{config.APP_URL.rstrip('/')}/api/jobs/handoff/decide?t={sign(handoff_id, choice)}"


def _serialize(h):
    return {"id": h.id, "job_id": h.job_id, "company": h.company, "role": h.role, "url": h.url, "choice": h.choice,
            "decided_at": h.decided_at.isoformat() + "Z" if h.decided_at else None}


def _email(h, missing):
    from api.core.clients import EmailClient
    sender, password = os.getenv("SENDER_EMAIL"), os.getenv("SENDER_PASSWORD")
    if not (sender and password):
        return False
    e = html.escape
    items = "".join(f"<li>{e(str(m))}</li>" for m in missing[:12])
    btn = ('<a href="{href}" style="display:inline-block;margin:6px 8px 0 0;padding:12px 18px;border-radius:10px;'
           'font-weight:600;text-decoration:none;background:{bg};color:{fg}">{label}</a>')
    body = (f'<!doctype html><html><body style="margin:0;background:#f5f5f7;padding:24px 12px">'
            f'<div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:24px;'
            f'font:15px/1.5 system-ui,sans-serif;color:#111827">'
            f'<div style="color:#6b7280;font-size:13px">Your apply runner needs you</div>'
            f'<h2 style="margin:6px 0 4px">{e(h.company or "")} — {e(h.role or "")}</h2>'
            f'<p style="margin:0 0 10px;color:#374151">{e(h.reason or "")}</p>'
            + (f'<ul style="margin:0 0 10px 18px;padding:0">{items}</ul>' if items else "")
            + btn.format(href=e(decide_url(h.id, "now")), bg="#111827", fg="#fff", label="Complete it now")
            + btn.format(href=e(decide_url(h.id, "later")), bg="#f3f4f6", fg="#111827", label="Later")
            + (f'<p style="margin:16px 0 0;font-size:13px;color:#6b7280">Job page: <a href="{e(h.url)}">{e(h.url)}</a></p>'
               if h.url else "")
            + '<p style="margin:8px 0 0;font-size:13px;color:#6b7280">"Complete it now" brings the filled application to the '
              'front on your laptop. "Later" saves it to your list and the runner moves on.</p></div></body></html>')
    subject = f"Need you: {h.company or 'Application'} — {h.role or ''}".strip(" —")
    return EmailClient(sender, password).send_email(config.RECEIVER_EMAIL, subject, f"Need you: {h.url or ''}", html=body)


@job_handoff_bp.route("/handoff", methods=["POST"])
def create():
    data = request.get_json(silent=True) or {}
    missing = [str(m)[:300] for m in (data.get("missing") or []) if str(m).strip()][:20]
    db = SessionLocal()
    try:
        h = JobHandoff(job_id=data.get("job_id") if isinstance(data.get("job_id"), int) else None,
                       company=str(data.get("company") or "")[:200], role=str(data.get("role") or "")[:300],
                       url=str(data.get("url") or "")[:2000], reason=str(data.get("reason") or "")[:1000],
                       missing=json.dumps(missing), choice="pending", created_at=_now())
        db.add(h)
        db.commit()
        try:
            emailed = bool(_email(h, missing))
        except Exception as e:
            print(f"handoff email failed: {e}")
            emailed = False
        return jsonify({"status": "success", "data": {**_serialize(h), "emailed": emailed}})
    finally:
        db.close()


@job_handoff_bp.route("/handoff/<int:handoff_id>", methods=["GET"])
def status(handoff_id):
    db = SessionLocal()
    try:
        h = db.get(JobHandoff, handoff_id)
        if not h:
            return jsonify({"status": "error", "message": "Not found"}), 404
        return jsonify({"status": "success", "data": _serialize(h)})
    finally:
        db.close()


@job_handoff_bp.route("/handoff/decide", methods=["GET"])
def decide():
    parsed = verify(request.args.get("t"))
    if not parsed:
        return _page("Link expired", "<h1>This link has expired or is invalid.</h1>", 400)
    hid, choice = parsed
    db = SessionLocal()
    try:
        h = db.get(JobHandoff, hid)
        if not h:
            return _page("Not found", "<h1>That application hand-off no longer exists.</h1>", 404)
        if h.choice == "pending":
            h.choice, h.decided_at = choice, _now()
            db.commit()
        e = html.escape
        if h.choice == "now":
            msg = ("<h1>Bringing it up on your laptop</h1><p>The filled application for "
                   f"<b>{e(h.company or '')} — {e(h.role or '')}</b> will come to the front in a few seconds. "
                   "Finish the highlighted part, then click <b>✅ I finished — continue</b> on the page.</p>")
        else:
            link = f'<p><a href="{e(h.url)}">Open the job page</a> when you\'re ready.</p>' if h.url else ""
            msg = (f"<h1>Saved for later</h1><p><b>{e(h.company or '')} — {e(h.role or '')}</b> is on your "
                   "\"needs you\" list. The runner has moved on to the next job.</p>" + link)
        return _page("Apply runner", msg)
    finally:
        db.close()


@job_handoff_bp.route("/handoffs", methods=["GET"])
def list_handoffs():
    choice = request.args.get("choice")
    db = SessionLocal()
    try:
        q = db.query(JobHandoff)
        if choice:
            q = q.filter(JobHandoff.choice == choice)
        rows = q.order_by(JobHandoff.created_at.desc()).limit(100).all()
        return jsonify({
            "status": "success",
            "data": [
                {
                    "id": h.id,
                    "job_id": h.job_id,
                    "company": h.company,
                    "role": h.role,
                    "url": h.url,
                    "reason": h.reason,
                    "missing": json.loads(h.missing) if h.missing else [],
                    "choice": h.choice,
                    "created_at": h.created_at.isoformat() + "Z" if h.created_at else None,
                    "decided_at": h.decided_at.isoformat() + "Z" if h.decided_at else None,
                }
                for h in rows
            ]
        })
    finally:
        db.close()


@job_handoff_bp.route("/handoff/<int:handoff_id>/done", methods=["POST"])
@job_handoff_bp.route("/handoff/<int:handoff_id>/choice", methods=["POST"])
def set_handoff_choice(handoff_id):
    data = request.get_json(silent=True) or {}
    choice = (data.get("choice") or "done").lower().strip()
    if choice not in CHOICES:
        return jsonify({"status": "error", "message": f"Invalid choice: {choice}"}), 400
    db = SessionLocal()
    try:
        h = db.get(JobHandoff, handoff_id)
        if not h:
            return jsonify({"status": "error", "message": "Not found"}), 404
        h.choice = choice
        h.decided_at = _now()
        db.commit()
        return jsonify({"status": "success", "data": _serialize(h)})
    finally:
        db.close()

