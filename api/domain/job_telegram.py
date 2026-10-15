"""
Optional Telegram notifications + one-tap approvals for Job Radar openings.

Integrity: nothing here applies anywhere. Approve only marks the job "approved" in Job Radar; Sai still opens the
official portal, autofills, reviews and submits himself. Applied jobs (manual_applied / applied_confirmed) are never
touched.

Everything is a no-op unless BOTH env vars TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set: functions return
{"status": "not_configured", ...} and send nothing. Uses the Telegram Bot API over HTTPS with `requests`.

Endpoints (blueprint job_telegram_bp, prefix /api/jobs):
  POST /api/jobs/telegram/webhook  OPEN endpoint (add to app._OPEN_ENDPOINTS). Auth = Telegram's
                                   X-Telegram-Bot-Api-Secret-Token header, compared with hmac.compare_digest to env
                                   TELEGRAM_WEBHOOK_SECRET. Only updates from TELEGRAM_CHAT_ID are acted on.
                                   Handles button presses (callback_query "a:<id>" / "s:<id>").
  POST /api/jobs/telegram/push     Passcode-protected (by app.before_request). Sends cards for the top new matches:
                                   status discovered, match_score >= 55, ctc_lpa >= 15 or unknown (0), discovered in
                                   the last 48 h, best 10 by match score.

Setup (one time):
  1. Create the bot: in Telegram open @BotFather, send /newbot, pick a name and a username ending in "bot".
     BotFather replies with the bot token (looks like 123456789:AA...). Keep it secret.
  2. Get your chat id: open your new bot, press Start and send it any message, then visit
        https://api.telegram.org/bot<TOKEN>/getUpdates
     and read result[0].message.chat.id (a number, e.g. 987654321).
  3. Pick a webhook secret (1-256 chars of A-Z a-z 0-9 _ -), e.g.  python -c "import secrets; print(secrets.token_urlsafe(32))"
  4. Vercel -> Project -> Settings -> Environment Variables (Production), add:
        TELEGRAM_BOT_TOKEN=<token>   TELEGRAM_CHAT_ID=<chat id>   TELEGRAM_WEBHOOK_SECRET=<secret>
     then redeploy so the functions see them.
  5. Point Telegram at the webhook (secret_token makes Telegram send the X-Telegram-Bot-Api-Secret-Token header):
        curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \\
             -d "url=https://productivity-automations.vercel.app/api/jobs/telegram/webhook" \\
             -d "secret_token=<secret>" -d 'allowed_updates=["callback_query"]'
     or, with the three env vars set locally:
        python -c "from api.domain.job_telegram import set_webhook; print(set_webhook())"
     Check with https://api.telegram.org/bot<TOKEN>/getWebhookInfo .
  6. Test: POST /api/jobs/telegram/push (with the X-App-Key passcode header) -> cards arrive in the chat.
"""
import hmac
import html
import os
import re
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, jsonify, request

from api.core import config
from api.core.db import SessionLocal, engine
from api.domain.job_radar import JobOpportunity

API_BASE = "https://api.telegram.org"
HTTP_TIMEOUT = 10  # seconds per Bot API call (serverless budget)
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

PUSH_MIN_SCORE = 55
PUSH_MIN_CTC = 15.0
PUSH_WINDOW = timedelta(hours=48)
PUSH_MAX = 10

# Same rules as job_approvals: approve only from discovered/approved; applied jobs are never touched.
APPROVABLE = {"discovered", "approved"}
SKIPPABLE = {"discovered", "approved", "skipped"}

APPROVED_NOTE = "Approved ✓ — open the link, Autofill, submit"
SKIPPED_NOTE = "Skipped"
NOT_CONFIGURED = {"status": "not_configured",
                  "message": "Telegram not configured: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."}


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------- Config + Bot API ----------------
def _token():
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _chat_id():
    return os.getenv("TELEGRAM_CHAT_ID", "").strip()


def is_configured():
    return bool(_token() and _chat_id())


def _not_configured(**extra):
    return {**NOT_CONFIGURED, **extra}


def _api(method, payload):
    """Calls a Bot API method. Returns the decoded JSON ({"ok": bool, ...}); never raises."""
    try:
        res = requests.post(f"{API_BASE}/bot{_token()}/{method}", json=payload, timeout=HTTP_TIMEOUT)
        try:
            body = res.json()
        except ValueError:
            body = {"ok": False, "description": f"HTTP {res.status_code}"}
        if not body.get("ok"):
            print(f"telegram {method} failed: {body.get('description')}")
        return body
    except requests.RequestException as e:
        print(f"telegram {method} failed: {e}")
        return {"ok": False, "description": str(e)}


# ---------------- Cards ----------------
def _est_ctc(job):
    m = re.search(r"est\. CTC ([^;]+)", job.notes or "")
    if m:
        return m.group(1).strip()
    return f"{job.ctc_lpa:g} LPA" if job.ctc_lpa else None


def _valid_url(url):
    return bool(url) and str(url).startswith(("https://", "http://"))


def card_text(job, note=None):
    """HTML-formatted card body for one job (optionally with a status line appended)."""
    e = html.escape
    lines = [f"<b>{e(job.company)}</b> — {e(job.role)}",
             f"📍 {e(job.location or 'Location n/a')}"]
    ctc = _est_ctc(job)
    if ctc:
        lines.append(f"💰 Est. CTC: {e(ctc)}")
    lines.append(f"🎯 Match: {int(job.match_score or 0)}/100")
    if _valid_url(job.portal_url):
        lines.append(f'🔗 <a href="{e(job.portal_url, quote=True)}">Application link</a>')
    if note:
        lines.append("")
        lines.append(f"<b>{e(note)}</b>")
    return "\n".join(lines)


def card_keyboard(job, decided=False):
    """Inline keyboard: Approve / Skip (callback) + Open (URL). After a decision only Open remains."""
    rows = []
    if not decided:
        rows.append([{"text": "✅ Approve", "callback_data": f"a:{job.id}"},
                     {"text": "⏭ Skip", "callback_data": f"s:{job.id}"}])
    if _valid_url(job.portal_url):
        rows.append([{"text": "🔗 Open", "url": job.portal_url}])
    return {"inline_keyboard": rows}


def card_payload(job, chat_id=None):
    return {"chat_id": chat_id or _chat_id(), "text": card_text(job), "parse_mode": "HTML",
            "disable_web_page_preview": True, "reply_markup": card_keyboard(job)}


def send_job_cards(jobs):
    """Sends one message per job. No-op (status not_configured) unless the bot token and chat id are set."""
    jobs = list(jobs or [])
    if not is_configured():
        return _not_configured(sent=0)
    sent, failed = 0, []
    for job in jobs:
        if _api("sendMessage", card_payload(job)).get("ok"):
            sent += 1
        else:
            failed.append(job.id)
    return {"status": "success" if not failed else ("partial" if sent else "error"),
            "sent": sent, "failed": failed, "total": len(jobs)}


def set_webhook(url=None):
    """Registers the webhook with Telegram (see module docstring). Needs TELEGRAM_WEBHOOK_SECRET too."""
    if not is_configured():
        return _not_configured()
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if not secret:
        return {"status": "error", "message": "Set TELEGRAM_WEBHOOK_SECRET first."}
    url = url or f"{config.APP_URL.rstrip('/')}/api/jobs/telegram/webhook"
    body = _api("setWebhook", {"url": url, "secret_token": secret, "allowed_updates": ["callback_query"]})
    return {"status": "success" if body.get("ok") else "error", "url": url, "telegram": body}


# ---------------- Decisions ----------------
def apply_decision(db, job_id, action):
    """Changes the job's status. Returns (job or None, outcome) where outcome is approved|skipped|unchanged|missing."""
    job = db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
    if job is None:
        return None, "missing"
    allowed = APPROVABLE if action == "approve" else SKIPPABLE
    if job.status not in allowed:
        return job, "unchanged"
    job.status = "approved" if action == "approve" else "skipped"
    job.last_checked_at = _utcnow()
    db.commit()
    return job, job.status


def top_new_matches(db, now=None):
    now = now or _utcnow()
    rows = (db.query(JobOpportunity)
            .filter(JobOpportunity.status == "discovered",
                    JobOpportunity.match_score >= PUSH_MIN_SCORE,
                    JobOpportunity.discovered_at >= now - PUSH_WINDOW)
            .order_by(JobOpportunity.match_score.desc(), JobOpportunity.discovered_at.desc())
            .all())
    return [j for j in rows if not j.ctc_lpa or j.ctc_lpa >= PUSH_MIN_CTC][:PUSH_MAX]


# ---------------- Blueprint ----------------
job_telegram_bp = Blueprint("job_telegram", __name__, url_prefix="/api/jobs")


@job_telegram_bp.record_once
def _ensure_tables(state):
    try:
        JobOpportunity.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        print(f"{JobOpportunity.__tablename__} check skipped: {e}")


@job_telegram_bp.route("/telegram/push", methods=["POST"])
def push_cards():
    if not is_configured():
        return jsonify(_not_configured(sent=0))
    db = SessionLocal()
    try:
        jobs = top_new_matches(db)
        if not jobs:
            return jsonify({"status": "success", "sent": 0, "failed": [], "total": 0,
                            "message": "No new matches to send."})
        return jsonify(send_job_cards(jobs))
    finally:
        db.close()


@job_telegram_bp.route("/telegram/webhook", methods=["POST"])
def webhook():
    if not is_configured():
        return jsonify(_not_configured()), 503
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    given = request.headers.get(SECRET_HEADER, "")
    if not secret or not hmac.compare_digest(given.encode(), secret.encode()):
        return jsonify({"status": "error", "message": "Forbidden"}), 403

    update = request.get_json(silent=True) or {}
    cq = update.get("callback_query")
    # Anything we don't act on still gets 200 so Telegram doesn't retry it.
    if not isinstance(cq, dict):
        return jsonify({"status": "ignored"})
    message = cq.get("message") or {}
    chat = str((message.get("chat") or {}).get("id", ""))
    if not chat or chat != _chat_id():
        return jsonify({"status": "ignored", "reason": "chat"})

    m = re.fullmatch(r"([as]):(\d+)", str(cq.get("data", "")))
    if not m:
        _api("answerCallbackQuery", {"callback_query_id": cq.get("id"), "text": "Unknown action"})
        return jsonify({"status": "ignored", "reason": "data"})
    action = "approve" if m.group(1) == "a" else "skip"

    db = SessionLocal()
    try:
        job, outcome = apply_decision(db, int(m.group(2)), action)
        if outcome == "missing":
            _api("answerCallbackQuery", {"callback_query_id": cq.get("id"), "text": "Job not found"})
            return jsonify({"status": "ignored", "reason": "missing"})
        if outcome == "unchanged":
            _api("answerCallbackQuery", {"callback_query_id": cq.get("id"), "show_alert": True,
                                         "text": f"Not changed: this job is '{job.status}'."})
            return jsonify({"status": "unchanged", "job_id": job.id, "job_status": job.status})

        note = APPROVED_NOTE if outcome == "approved" else SKIPPED_NOTE
        _api("answerCallbackQuery", {"callback_query_id": cq.get("id"), "text": note})
        if message.get("message_id") is not None:
            _api("editMessageText", {"chat_id": message["chat"]["id"], "message_id": message["message_id"],
                                     "text": card_text(job, note), "parse_mode": "HTML",
                                     "disable_web_page_preview": True,
                                     "reply_markup": card_keyboard(job, decided=True)})
        return jsonify({"status": "success", "job_id": job.id, "job_status": job.status})
    finally:
        db.close()
