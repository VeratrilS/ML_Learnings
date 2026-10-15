"""
Human-in-the-loop approval for Job Radar openings, by email.

Integrity: nothing here applies anywhere. Approving a job only marks it "approved" in Job Radar and prepares the
application pack (job_pack). Sai still opens the official portal, reviews and submits himself.

Flow:
  1. POST /api/jobs/approval-digest (open scheduler endpoint, throttled to once per 20 h) emails Sai the best new
     matches, each with signed one-click Approve / Skip links, plus the approved jobs he has not applied to yet.
  2. GET /api/jobs/decide?t=<token> (open endpoint; the signed token is the auth) applies the decision and returns a
     small mobile page. Approve shows the portal link and the pack's cover note + answers with copy buttons.
  3. GET /api/jobs/queue (passcode-protected) lists approved jobs for the UI.

Tokens: base64url("<job_id>.<action>.<expiry unix>") + "." + base64url(HMAC-SHA256(secret, payload)). The secret is
derived from APP_PASSCODE (fallback STUDIO_SECRET, then a constant that is only meant for tests / local dev).
"""
import base64
import hashlib
import hmac
import html
import json
import os
import time
from datetime import datetime, timedelta, timezone

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.exc import IntegrityError

from api.core import config
from api.core.db import Base, SessionLocal, engine
from api.domain import job_pack
from api.domain.job_radar import JobOpportunity

ACTIONS = ("approve", "skip")
TOKEN_TTL = timedelta(days=7)
DIGEST_GAP = timedelta(hours=20)
LAST_DIGEST_KEY = "job_approvals:last_digest"
DIGEST_MIN_CTC = 15.0
DIGEST_MIN_SCORE = 55
DIGEST_WINDOW = timedelta(hours=48)
DIGEST_MAX = 15
WAITING_MAX = 25
# Statuses a decision may change. Applied jobs (manual_applied / applied_confirmed) are never touched.
# "skipped" can be re-approved so an accidental Skip (or a mail scanner opening the link) is recoverable.
APPROVABLE = {"discovered", "approved", "skipped"}
SKIPPABLE = {"discovered", "approved", "skipped"}
_TEST_SECRET = "job-approvals-local-dev-secret"


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------- Model (audit trail of decisions) ----------------
class JobApprovalDecision(Base):
    __tablename__ = "job_approval_decisions"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, unique=True, index=True, nullable=False)
    action = Column(String(20), nullable=False)
    decided_at = Column(DateTime, default=_utcnow)


# ---------------- Signed tokens ----------------
def _secret():
    base = os.getenv("APP_PASSCODE") or os.getenv("STUDIO_SECRET") or _TEST_SECRET
    return hashlib.sha256(f"job-approvals:{base}".encode()).digest()


def _b64e(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign_token(job_id, action, now=None, ttl=TOKEN_TTL):
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    expiry = int((now if now is not None else time.time()) + ttl.total_seconds())
    payload = _b64e(f"{int(job_id)}.{action}.{expiry}".encode())
    sig = _b64e(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_token(token, now=None):
    """Returns (job_id, action) for a valid, unexpired token, else None."""
    try:
        payload, sig = (token or "").split(".")
        expected = _b64e(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        job_id, action, expiry = _b64d(payload).decode().split(".")
        if action not in ACTIONS or int(expiry) < (now if now is not None else time.time()):
            return None
        return int(job_id), action
    except (ValueError, TypeError, UnicodeDecodeError):
        return None


def decide_url(job_id, action):
    return f"{config.APP_URL.rstrip('/')}/api/jobs/decide?t={sign_token(job_id, action)}"


# ---------------- Pack (reuses job_pack's builder + cache) ----------------
def get_or_build_pack(db, job):
    """Cached pack payload for `job` (same cache and builder as GET /api/jobs/<id>/pack)."""
    JobPack = job_pack.JobPack
    row = db.query(JobPack).filter(JobPack.job_id == job.id).first()
    if row:
        try:
            payload = json.loads(row.payload)
        except ValueError:
            payload = None
        if isinstance(payload, dict) and payload.get("job_key") == job_pack._job_key(job):
            return payload
    payload, model = job_pack.generate_pack(job, job_pack._location_prefs(db))
    if row is None:
        row = JobPack(job_id=job.id)
        db.add(row)
    row.payload, row.model, row.created_at = json.dumps(payload), model, _utcnow()
    try:
        db.commit()
    except IntegrityError:  # a concurrent request cached it first: overwrite with ours
        db.rollback()
        row = db.query(JobPack).filter(JobPack.job_id == job.id).first()
        row.payload, row.model, row.created_at = json.dumps(payload), model, _utcnow()
        db.commit()
    return payload


# ---------------- HTML ----------------
_e = html.escape


def _safe_url(url):
    url = (url or "").strip()
    return url if url.lower().startswith(("https://", "http://")) else "#"


_PAGE_CSS = (
    "*{box-sizing:border-box}body{margin:0;background:#f5f5f7;color:#111827;font:16px/1.5 system-ui,-apple-system,"
    "'Segoe UI',Roboto,sans-serif;padding:16px}.card{max-width:640px;margin:0 auto;background:#fff;border:1px solid "
    "#e5e7eb;border-radius:16px;padding:20px}h1{font-size:20px;margin:0 0 4px}.muted{color:#6b7280;font-size:14px;"
    "margin:0}.btn{display:block;text-align:center;background:#111827;color:#fff;text-decoration:none;font-weight:600;"
    "padding:14px;border-radius:12px;margin:18px 0}.note{background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;"
    "padding:12px;font-size:14px;color:#9a3412}.qa{border-top:1px solid #eee;padding:14px 0 4px}.q{font-weight:600;"
    "font-size:14px;margin:0 0 6px;display:flex;justify-content:space-between;gap:10px;align-items:center}"
    ".a{white-space:pre-wrap;font-size:14px;color:#374151;margin:0}.copy{flex:none;border:1px solid #d1d5db;"
    "background:#fff;border-radius:8px;padding:5px 10px;font-size:13px;cursor:pointer}"
    "@media (prefers-color-scheme:dark){body{background:#0b0b0f;color:#e5e7eb}.card{background:#16161d;"
    "border-color:#2a2a33}.muted,.a{color:#c4c7cf}.qa{border-color:#2a2a33}.btn{background:#f9fafb;color:#111827}"
    ".copy{background:#1f1f27;color:#e5e7eb;border-color:#3a3a45}.note{background:#2a1a0e;border-color:#7c2d12;"
    "color:#fdba74}}"
)
_COPY_JS = (
    "<script>document.querySelectorAll('.copy').forEach(function(b){b.onclick=function(){var t=document."
    "getElementById(b.dataset.for).innerText;var done=function(){b.textContent='Copied';setTimeout(function(){"
    "b.textContent='Copy'},1500)};if(navigator.clipboard){navigator.clipboard.writeText(t).then(done,function(){})}"
    "else{var r=document.createRange();r.selectNodeContents(document.getElementById(b.dataset.for));var s=window."
    "getSelection();s.removeAllRanges();s.addRange(r);document.execCommand('copy');done()}}})</script>"
)


def _page(title, body, status=200):
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
           f'content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">'
           f'<title>{_e(title)}</title><style>{_PAGE_CSS}</style></head><body><div class="card">{body}</div>'
           f'{_COPY_JS}</body></html>')
    return Response(doc, status=status, mimetype="text/html")


def _job_header(job):
    meta = " · ".join(x for x in (job.company, job.location,
                                   f"{job.ctc_lpa:g} LPA" if job.ctc_lpa else None) if x)
    return f"<h1>{_e(job.role)}</h1><p class=\"muted\">{_e(meta)}</p>"


def _qa_block(idx, question, answer):
    return (f'<div class="qa"><p class="q"><span>{_e(question)}</span>'
            f'<button class="copy" type="button" data-for="a{idx}">Copy</button></p>'
            f'<p class="a" id="a{idx}">{_e(answer)}</p></div>')


def approved_page(job, pack):
    body = [_job_header(job),
            f'<a class="btn" href="{_e(_safe_url(job.portal_url))}" target="_blank" rel="noopener">'
            f'Open application ↗</a>',
            '<p class="note">Approved. Use ⚡ Autofill, attach your resume, review, then submit on the official '
            'portal. Nothing has been submitted for you.</p>']
    if pack:
        blocks = [("Cover note", pack.get("cover_note")), ("Why this company?", pack.get("why_company"))]
        blocks += [(a.get("question"), a.get("answer")) for a in pack.get("answers") or [] if isinstance(a, dict)]
        body += [_qa_block(i, q, a) for i, (q, a) in enumerate(blocks) if q and a]
    else:
        body.append('<p class="muted" style="margin-top:14px">The application pack could not be prepared right now. '
                    'Open it later from Job Radar.</p>')
    return _page(f"Approved: {job.company}", "".join(body))


def message_page(title, text, job=None, status=200):
    body = (_job_header(job) if job else "") + f'<h1 style="margin-top:12px">{_e(title)}</h1>' \
        + f'<p class="muted">{_e(text)}</p>'
    if job and job.portal_url:
        body += (f'<a class="btn" href="{_e(_safe_url(job.portal_url))}" target="_blank" rel="noopener">'
                 f'Open application ↗</a>')
    return _page(title, body, status=status)


# ---------------- Decisions ----------------
def _record(db, job_id, action):
    row = db.query(JobApprovalDecision).filter(JobApprovalDecision.job_id == job_id).first()
    if row is None:
        row = JobApprovalDecision(job_id=job_id)
        db.add(row)
    row.action, row.decided_at = action, _utcnow()


def apply_decision(db, job, action):
    """Returns True if the status changed (or was already the target), False if the job is not decidable."""
    allowed = APPROVABLE if action == "approve" else SKIPPABLE
    if (job.status or "discovered") not in allowed:
        return False
    job.status = "approved" if action == "approve" else "skipped"
    _record(db, job.id, action)
    db.commit()
    return True


# ---------------- Digest ----------------
def select_new_matches(db, now=None):
    now = now or _utcnow()
    q = db.query(JobOpportunity).filter(
        JobOpportunity.status == "discovered",
        JobOpportunity.match_score >= DIGEST_MIN_SCORE,
        JobOpportunity.discovered_at >= now - DIGEST_WINDOW,
        (JobOpportunity.ctc_lpa >= DIGEST_MIN_CTC) | (JobOpportunity.ctc_lpa == 0) | (JobOpportunity.ctc_lpa.is_(None)),
    )
    return q.order_by(JobOpportunity.match_score.desc(), JobOpportunity.ctc_lpa.desc(),
                      JobOpportunity.id.asc()).limit(DIGEST_MAX).all()


def select_waiting(db):
    return (db.query(JobOpportunity)
            .filter(JobOpportunity.status == "approved", JobOpportunity.applied_at.is_(None))
            .order_by(JobOpportunity.match_score.desc(), JobOpportunity.id.asc()).limit(WAITING_MAX).all())


def _btn(href, label, bg, fg="#ffffff", border=None):
    border = border or bg
    return (f'<a href="{_e(href)}" style="display:inline-block;background:{bg};color:{fg};border:1px solid {border};'
            f'padding:9px 16px;border-radius:9px;font-weight:600;font-size:14px;text-decoration:none;'
            f'margin:8px 8px 0 0">{_e(label)}</a>')


def _meta(job):
    parts = [job.company, job.location, f"{job.ctc_lpa:g} LPA" if job.ctc_lpa else "CTC not listed",
             f"match {job.match_score or 0}"]
    return " · ".join(_e(str(p)) for p in parts if p)


def digest_html(new_jobs, waiting):
    rows = "".join(
        f'<div style="border-top:1px solid #eee;padding:14px 0">'
        f'<a href="{_e(_safe_url(j.portal_url))}" style="color:#111827;font-weight:600;text-decoration:none">'
        f'{_e(j.role)}</a><div style="color:#6b7280;font-size:13px;margin-top:2px">{_meta(j)}</div>'
        f'{_btn(decide_url(j.id, "approve"), "Approve", "#15803d")}'
        f'{_btn(decide_url(j.id, "skip"), "Skip", "#ffffff", "#374151", "#d1d5db")}</div>'
        for j in new_jobs)
    new_section = (f'<h1 style="margin:0 0 6px;font-size:21px">{len(new_jobs)} new jobs to review</h1>'
                   f'<p style="margin:0 0 6px;color:#4b5563;font-size:14px">Approve to get the application link and a '
                   f'ready pack. You still submit on the official portal yourself. Links work for 7 days.</p>{rows}'
                   if new_jobs else "")
    wait_rows = "".join(
        f'<div style="border-top:1px solid #eee;padding:12px 0"><b>{_e(j.role)}</b>'
        f'<div style="color:#6b7280;font-size:13px;margin-top:2px">{_meta(j)}</div>'
        f'{_btn(_safe_url(j.portal_url), "Open application", "#111827")}'
        f'{_btn(decide_url(j.id, "approve"), "View pack", "#ffffff", "#374151", "#d1d5db")}</div>'
        for j in waiting)
    wait_section = (f'<h2 style="margin:{"26px" if new_jobs else "0"} 0 6px;font-size:18px">Approved, waiting for you'
                    f'</h2><p style="margin:0 0 6px;color:#4b5563;font-size:14px">Approved but not marked applied yet.'
                    f'</p>{wait_rows}' if waiting else "")
    return (f'<!doctype html><html><body style="margin:0;background:#f5f5f7;padding:16px 8px">'
            f'<div style="max-width:620px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:16px;'
            f'padding:20px;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#111827">'
            f'{new_section}{wait_section}'
            f'<p style="margin:22px 0 0;font-size:13px;color:#6b7280"><a href="{_e(config.APP_URL)}#/job-radar" '
            f'style="color:#6b7280">Open Job Radar</a></p></div></body></html>')


def digest_text(new_jobs, waiting):
    lines = [f"{len(new_jobs)} new jobs to review" if new_jobs else "No new jobs today"]
    for j in new_jobs:
        lines += ["", f"{j.role} - {j.company} ({j.location})", f"Approve: {decide_url(j.id, 'approve')}",
                  f"Skip: {decide_url(j.id, 'skip')}"]
    if waiting:
        lines += ["", "Approved, waiting for you:"]
        lines += [f"- {j.role} - {j.company}: {j.portal_url}" for j in waiting]
    return "\n".join(lines)


def digest_subject(new_jobs, waiting):
    if new_jobs:
        return f"{len(new_jobs)} new job{'s' if len(new_jobs) != 1 else ''} to review (≥15 LPA)"
    return f"{len(waiting)} approved job{'s' if len(waiting) != 1 else ''} waiting for you"


# ---------------- Routes ----------------
job_approvals_bp = Blueprint("job_approvals", __name__, url_prefix="/api/jobs")


@job_approvals_bp.record_once
def _ensure_tables(state):
    for model in (JobApprovalDecision, job_pack.JobPack):
        try:
            model.__table__.create(bind=engine, checkfirst=True)
        except Exception as e:
            print(f"{model.__tablename__} check skipped: {e}")


@job_approvals_bp.route("/decide", methods=["GET"])
def decide_route():
    parsed = verify_token(request.args.get("t", ""))
    if not parsed:
        return message_page("Link invalid or expired",
                            "This approval link is invalid or older than 7 days. Open Job Radar to decide.", status=400)
    job_id, action = parsed
    db = SessionLocal()
    try:
        job = db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
        if not job:
            return message_page("Job not found", "This opening is no longer in Job Radar.", status=404)
        if not apply_decision(db, job, action):
            return message_page("Already applied" if job.status in ("manual_applied", "applied_confirmed")
                                else "Nothing changed",
                                f"This job is marked '{job.status}', so the link did not change it.", job=job)
        if action == "skip":
            return message_page("Skipped", "This job is hidden from your review list. To change your mind, use the "
                                           "Approve link from the same email.", job=job)
        try:
            pack = get_or_build_pack(db, job)
        except Exception as e:  # the approval stands; the pack can be rebuilt from Job Radar
            db.rollback()
            print(f"job approval pack failed for job {job.id}: {str(e)[:200]}")
            pack = None
        return approved_page(job, pack)
    finally:
        db.close()


@job_approvals_bp.route("/approval-digest", methods=["POST"])
def approval_digest_route():
    from api.core.clients import EmailClient
    from api.domain.repositories import NotificationRepository
    db = SessionLocal()
    try:
        repo = NotificationRepository(db)
        last = repo.get_setting(LAST_DIGEST_KEY)
        if last:
            try:
                if datetime.now(timezone.utc) - datetime.fromisoformat(last) < DIGEST_GAP:
                    return jsonify({"status": "skipped", "message": "Approval digest sent recently."})
            except ValueError:
                pass
        new_jobs, waiting = select_new_matches(db), select_waiting(db)
        if not new_jobs and not waiting:
            return jsonify({"status": "success", "data": {"new": 0, "waiting": 0, "emailed": False}})
        sender, password = os.getenv("SENDER_EMAIL"), os.getenv("SENDER_PASSWORD")
        if not (sender and password):
            return jsonify({"status": "error", "message": "SMTP credentials not configured."}), 500
        ok = EmailClient(sender, password).send_email(
            config.RECEIVER_EMAIL, digest_subject(new_jobs, waiting), digest_text(new_jobs, waiting),
            html=digest_html(new_jobs, waiting))
        if ok:
            repo.set_setting(LAST_DIGEST_KEY, datetime.now(timezone.utc).isoformat())
        return jsonify({"status": "success" if ok else "error",
                        "data": {"new": len(new_jobs), "waiting": len(waiting), "emailed": bool(ok),
                                 "job_ids": [j.id for j in new_jobs]}}), (200 if ok else 502)
    finally:
        db.close()


@job_approvals_bp.route("/queue", methods=["GET"])
def queue_route():
    db = SessionLocal()
    try:
        jobs = (db.query(JobOpportunity).filter(JobOpportunity.status == "approved")
                .order_by(JobOpportunity.match_score.desc(), JobOpportunity.id.asc()).all())
        ids = [j.id for j in jobs]
        decided = {d.job_id: d.decided_at for d in
                   db.query(JobApprovalDecision).filter(JobApprovalDecision.job_id.in_(ids)).all()} if ids else {}
        packed = {r.job_id for r in
                  db.query(job_pack.JobPack.job_id).filter(job_pack.JobPack.job_id.in_(ids)).all()} if ids else set()
        data = [{"id": j.id, "company": j.company, "role": j.role, "location": j.location, "url": j.portal_url,
                 "match_score": j.match_score, "ctc_lpa": j.ctc_lpa or None, "status": j.status,
                 "approved_at": decided[j.id].isoformat() + "Z" if decided.get(j.id) else None,
                 "pack_ready": j.id in packed} for j in jobs]
        data.sort(key=lambda d: d["approved_at"] or "", reverse=True)
        return jsonify({"status": "success", "data": data})
    finally:
        db.close()
