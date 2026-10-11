"""
Web push notifications (VAPID) for the installed PWA.

Devices subscribe via the service worker; the 5-minute cron pings POST /api/push/tick, which fires
at most one notification per rule per day (or per contest) thanks to unique PushLog dedupe keys:

  brief     08:00-09:30 IST  "brief:{date}"     pending tasks, reviews due, next exam
  streak    21:30-22:30 IST  "streak:{date}"    no LeetCode/Codeforces problem completed today
  revision  18:00-19:00 IST  "revision:{date}"  spaced-repetition reviews due
  contest   40-75 min before start  "contest:{id}"  (ignores quiet hours)

Env: VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY (raw base64url or PEM/DER), VAPID_SUBJECT (mailto:...),
optional CRON_KEY (then /tick needs header X-Cron-Key).
"""
import hmac
import json
import os
from datetime import datetime, time as dtime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.exc import IntegrityError

from api.core.config import IST, now_ist
from api.core.db import Base, SessionLocal, engine

KINDS = ("brief", "streak", "contest", "revision")
DEFAULT_PREFS = {k: True for k in KINDS}
MAX_FAILS = 10  # transient failures in a row before a subscription is dropped

# kind -> (ttl seconds, urgency)
DELIVERY = {
    "brief": (2 * 3600, "normal"),
    "streak": (3600, "high"),
    "contest": (45 * 60, "high"),
    "revision": (2 * 3600, "normal"),
    "test": (120, "high"),
}

WINDOWS = {  # IST [start, end)
    "brief": (dtime(8, 0), dtime(9, 30)),
    "revision": (dtime(18, 0), dtime(19, 0)),
    "streak": (dtime(21, 30), dtime(22, 30)),
}
CONTEST_LEAD = (40 * 60, 75 * 60)  # seconds before start


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _now():
    """Current IST time (patched in tests)."""
    return now_ist()


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    endpoint = Column(String(1000), unique=True, nullable=False)
    p256dh = Column(String(255), nullable=False)
    auth = Column(String(255), nullable=False)
    ua = Column(String(300), nullable=True)
    prefs = Column(Text, nullable=True)  # JSON {kind: bool}
    fail_count = Column(Integer, default=0, nullable=False)
    last_ok_at = Column(DateTime, nullable=True)  # naive UTC
    created_at = Column(DateTime, default=_utcnow)  # naive UTC

    def __repr__(self):
        return f"<PushSubscription(id={self.id}, endpoint={self.endpoint[:40]!r})>"


class PushLog(Base):
    __tablename__ = "push_logs"

    id = Column(Integer, primary_key=True, index=True)
    dedupe_key = Column(String(200), unique=True, nullable=False)
    kind = Column(String(30), nullable=False)
    sent_at = Column(DateTime, default=_utcnow)  # naive UTC


push_bp = Blueprint("push", __name__, url_prefix="/api/push")


@push_bp.record_once
def _ensure_tables(state):
    for model in (PushSubscription, PushLog):
        try:
            model.__table__.create(bind=engine, checkfirst=True)
        except Exception as e:  # e.g. a concurrent cold start created it first
            print(f"{model.__tablename__} table check skipped: {e}")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _prefs(sub):
    prefs = dict(DEFAULT_PREFS)
    try:
        stored = json.loads(sub.prefs or "{}")
        if isinstance(stored, dict):
            prefs.update({k: bool(v) for k, v in stored.items() if k in KINDS})
    except ValueError:
        pass
    return prefs


def _clean_prefs(value, base=None):
    prefs = dict(base or DEFAULT_PREFS)
    if isinstance(value, dict):
        prefs.update({k: bool(v) for k, v in value.items() if k in KINDS})
    return prefs


def _serialize(sub):
    return {
        "id": sub.id,
        "endpoint": sub.endpoint,
        "ua": sub.ua,
        "prefs": _prefs(sub),
        "fail_count": sub.fail_count or 0,
        "last_ok_at": _iso(sub.last_ok_at),
        "created_at": _iso(sub.created_at),
    }


def vapid_public_key():
    return (os.getenv("VAPID_PUBLIC_KEY") or "").strip()


def _vapid_private_key():
    # .env/Vercel values may carry literal "\n" in a PEM
    return (os.getenv("VAPID_PRIVATE_KEY") or "").strip().replace("\\n", "\n")


def _vapid_subject():
    return (os.getenv("VAPID_SUBJECT") or "mailto:admin@example.com").strip()


def configured():
    return bool(vapid_public_key() and _vapid_private_key())


def _in_window(now, kind):
    start, end = WINDOWS[kind]
    return start <= now.time().replace(tzinfo=None) < end


def _in_quiet_hours(start: int, end: int, hour: int) -> bool:
    if start == end:
        return False
    if start > end:
        return hour >= start or hour < end
    return start <= hour < end


def _ist_midnight_utc(now):
    """IST midnight of `now`'s day as naive UTC (DB timestamps are naive UTC)."""
    midnight = datetime.combine(now.date(), dtime(0, 0), tzinfo=IST)
    return midnight.astimezone(timezone.utc).replace(tzinfo=None)


# ---------------- sending ----------------
def send(sub, payload, db=None, kind=None):
    """Deliver one push. Returns "ok", "gone" (subscription deleted) or "error".

    Subscriptions answering 404/410 are expired and removed. When `db` is given, bookkeeping
    (fail_count / last_ok_at / deletion) is committed on that session.
    """
    from pywebpush import WebPushException, webpush  # lazy: heavy crypto import, only when sending

    kind = kind or payload.get("kind") or "test"
    ttl, urgency = DELIVERY.get(kind, (3600, "normal"))
    ttl = int(payload.pop("_ttl", ttl))
    status = "error"
    try:
        webpush(
            subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            data=json.dumps(payload),
            vapid_private_key=_vapid_private_key(),
            vapid_claims={"sub": _vapid_subject()},  # fresh dict: pywebpush fills in aud/exp
            ttl=max(0, ttl),
            headers={"Urgency": urgency},
            timeout=10,
        )
        status = "ok"
    except WebPushException as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        status = "gone" if code in (404, 410) else "error"
        if status == "error":
            print(f"push failed ({code}): {e}")
    except Exception as e:  # network errors etc.
        print(f"push failed: {e}")

    if db is not None:
        if status == "ok":
            sub.fail_count = 0
            sub.last_ok_at = _utcnow()
        elif status == "gone":
            db.delete(sub)
        else:
            sub.fail_count = (sub.fail_count or 0) + 1
            if sub.fail_count >= MAX_FAILS:
                db.delete(sub)
                status = "gone"
        db.commit()
    return status


def _broadcast(db, subs, payload, kind):
    counts = {"ok": 0, "gone": 0, "error": 0}
    for sub in subs:
        counts[send(sub, {**payload, "kind": kind}, db=db, kind=kind)] += 1
    return counts


# ---------------- tick data (each guarded: a missing module must not break push) ----------------
def _pending_todos(db, today):
    try:
        from api.domain.todos import Todo
        return db.query(Todo).filter(Todo.done.is_(False), Todo.day <= today).count()
    except Exception as e:
        print(f"push: todo count skipped: {e}")
        db.rollback()
        return 0


def _due_reviews(repo):
    try:
        return repo.count_due_reviews()
    except Exception as e:
        print(f"push: review count skipped: {e}")
        repo.db.rollback()
        return 0


def _next_exam(db, today):
    try:
        from api.domain.syllabus import Subject, _next_exam as next_exam
        return next_exam(db.query(Subject).all(), today)
    except Exception as e:
        print(f"push: next exam skipped: {e}")
        db.rollback()
        return None


def _solved_today(db, now):
    try:
        from api.domain.models import NotificationLog
        return db.query(NotificationLog).filter(
            NotificationLog.task_type.in_(("leetcode", "codeforces")),
            NotificationLog.is_completed.is_(True),
            NotificationLog.completed_at >= _ist_midnight_utc(now),
        ).count()
    except Exception as e:
        print(f"push: solved count skipped: {e}")
        db.rollback()
        return 1  # unknown: don't nag


def _upcoming_contests(now):
    try:
        from api.domain import contests
        return contests.get_contests(now=now.timestamp()).get("data") or []
    except Exception as e:
        print(f"push: contests skipped: {e}")
        return []


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _contest_id(c):
    tail = (c.get("url") or "").rstrip("/").rsplit("/", 1)[-1] or c.get("name", "")
    return f"{c.get('platform', 'contest')}:{tail}"[:180]


# ---------------- tick ----------------
def _candidates(db, repo, now):
    """Yield (kind, dedupe_key, payload) for every rule whose condition holds right now."""
    today = now.date()
    quiet = _in_quiet_hours(int(repo.get_setting("quiet_start", "23") or 23),
                            int(repo.get_setting("quiet_end", "7") or 7), now.hour)
    cache = {}

    def counts():
        if not cache:
            cache["todos"] = _pending_todos(db, today)
            cache["reviews"] = _due_reviews(repo)
        return cache["todos"], cache["reviews"]

    if not quiet and _in_window(now, "brief"):
        todos, reviews = counts()
        parts = [_plural(todos, "task") + " pending" if todos else "No tasks yet: plan your day"]
        if reviews:
            parts.append(_plural(reviews, "review") + " due")
        exam = _next_exam(db, today)
        if exam:
            d = exam.get("days_left")
            when = "today" if d == 0 else "tomorrow" if d == 1 else f"in {d} days"
            parts.append(f"{exam.get('short') or exam.get('subject')} exam {when}")
        yield "brief", f"brief:{today.isoformat()}", {
            "title": "Good morning ☀️", "body": " · ".join(parts), "url": "/#/today",
            "tag": "brief", "badge_count": todos + reviews,
        }

    if not quiet and _in_window(now, "revision"):
        todos, reviews = counts()
        if reviews > 0:
            yield "revision", f"revision:{today.isoformat()}", {
                "title": "Revision time",
                "body": f"{_plural(reviews, 'problem')} due for review. A few minutes keeps them fresh.",
                "url": "/#/today", "tag": "revision", "badge_count": todos + reviews,
            }

    if not quiet and _in_window(now, "streak") and _solved_today(db, now) == 0:
        todos, reviews = counts()
        yield "streak", f"streak:{today.isoformat()}", {
            "title": "Streak at risk 🔥",
            "body": "No problem solved today yet. One quick LeetCode or Codeforces problem keeps it alive.",
            "url": "/#/problems", "tag": "streak", "badge_count": todos + reviews,
        }

    # Contests ignore quiet hours: you asked to be told before they start.
    lo, hi = CONTEST_LEAD
    for c in _upcoming_contests(now):
        try:
            start = datetime.fromisoformat(c["start"].replace("Z", "+00:00"))
        except (KeyError, ValueError, AttributeError):
            continue
        lead = (start - now).total_seconds()
        if c.get("running") or not (lo <= lead <= hi):
            continue
        mins = int(round(lead / 60))
        start_ist = start.astimezone(IST).strftime("%H:%M")
        platform = {"leetcode": "LeetCode", "codeforces": "Codeforces"}.get(c.get("platform"), c.get("platform", ""))
        yield "contest", f"contest:{_contest_id(c)}", {
            "title": f"{platform} contest in {mins} min",
            "body": f"{c.get('name', 'Contest')} starts at {start_ist} IST.",
            "url": "/#/today", "tag": f"contest-{_contest_id(c)}",
            "_ttl": max(60, int(lead)),
        }


def run_tick(now=None):
    """Evaluate every rule once. Idempotent: each dedupe key is claimed at most once."""
    now = now or _now()
    if not configured():
        return {"configured": False, "fired": [], "skipped": "VAPID keys not set"}
    from api.domain.repositories import NotificationRepository

    db = SessionLocal()
    fired = []
    try:
        if not db.query(PushSubscription.id).first():
            return {"configured": True, "fired": [], "skipped": "no subscribers"}
        repo = NotificationRepository(db)
        for kind, key, payload in list(_candidates(db, repo, now)):
            if db.query(PushLog.id).filter(PushLog.dedupe_key == key).first():
                continue
            subs = [s for s in db.query(PushSubscription).all() if _prefs(s).get(kind, True)]
            if not subs:
                continue
            # Claim the key first so concurrent ticks can't double-send.
            db.add(PushLog(dedupe_key=key, kind=kind))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                continue
            payload = {k: v for k, v in payload.items() if v is not None}
            fired.append({"kind": kind, "key": key, **_broadcast(db, subs, payload, kind)})
        return {"configured": True, "fired": fired, "at": now.isoformat()}
    finally:
        db.close()


# ---------------- routes ----------------
@push_bp.route("/key", methods=["GET"])
def get_key():
    return jsonify({"status": "success", "data": {"public_key": vapid_public_key() or None, "configured": configured()}})


def _parse_subscription(data):
    sub = data.get("subscription") if isinstance(data.get("subscription"), dict) else data
    endpoint = sub.get("endpoint")
    keys = sub.get("keys") if isinstance(sub.get("keys"), dict) else {}
    p256dh, auth = keys.get("p256dh"), keys.get("auth")
    if not isinstance(endpoint, str) or not endpoint.startswith("https://") or len(endpoint) > 1000:
        return None, "A valid https push endpoint is required."
    if not (isinstance(p256dh, str) and p256dh and isinstance(auth, str) and auth) or len(p256dh) > 255 or len(auth) > 255:
        return None, "Subscription keys (p256dh, auth) are required."
    return {"endpoint": endpoint, "p256dh": p256dh, "auth": auth}, None


@push_bp.route("/subscribe", methods=["GET"])
def get_subscription():
    endpoint = request.args.get("endpoint", "")
    db = SessionLocal()
    try:
        sub = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first() if endpoint else None
        return jsonify({"status": "success", "data": _serialize(sub) if sub else None,
                        "devices": db.query(PushSubscription).count()})
    finally:
        db.close()


@push_bp.route("/subscribe", methods=["POST"])
def subscribe():
    data = _body()
    parsed, error = _parse_subscription(data)
    if error:
        return _err(error)
    ua = (data.get("ua") or request.headers.get("User-Agent") or "")[:300]
    db = SessionLocal()
    try:
        sub = db.query(PushSubscription).filter(PushSubscription.endpoint == parsed["endpoint"]).first()
        if sub is None:
            sub = PushSubscription(endpoint=parsed["endpoint"], prefs=json.dumps(_clean_prefs(data.get("prefs"))))
            db.add(sub)
        elif "prefs" in data:
            sub.prefs = json.dumps(_clean_prefs(data.get("prefs"), _prefs(sub)))
        sub.p256dh, sub.auth, sub.ua, sub.fail_count = parsed["p256dh"], parsed["auth"], ua, 0
        try:
            db.commit()
        except IntegrityError:  # raced with another subscribe of the same endpoint
            db.rollback()
            return _err("Subscription changed concurrently; try again.", 409)
        db.refresh(sub)
        return jsonify({"status": "success", "data": _serialize(sub)})
    finally:
        db.close()


@push_bp.route("/subscribe", methods=["DELETE"])
def unsubscribe():
    endpoint = _body().get("endpoint") or request.args.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint:
        return _err("endpoint is required.")
    db = SessionLocal()
    try:
        removed = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).delete()
        db.commit()
        return jsonify({"status": "success", "removed": removed})
    finally:
        db.close()


@push_bp.route("/test", methods=["POST"])
def send_test():
    if not configured():
        return _err("Push isn't configured on the server (VAPID keys missing).", 503)
    endpoint = _body().get("endpoint")
    db = SessionLocal()
    try:
        q = db.query(PushSubscription)
        if isinstance(endpoint, str) and endpoint:
            q = q.filter(PushSubscription.endpoint == endpoint)
        subs = q.all()
        if not subs:
            return _err("No subscribed device found. Enable notifications first.", 404)
        payload = {"title": "Daily", "body": "Test notification: you're all set. 🎯", "url": "/#/today",
                   "tag": "test"}
        counts = _broadcast(db, subs, payload, "test")
        if not counts["ok"]:
            return _err("The push service rejected the notification. Try re-enabling notifications.", 502)
        return jsonify({"status": "success", "data": counts})
    finally:
        db.close()


@push_bp.route("/tick", methods=["POST", "GET"])
def tick():
    cron_key = os.getenv("CRON_KEY", "")
    if cron_key and not hmac.compare_digest(request.headers.get("X-Cron-Key", ""), cron_key):
        return _err("Bad cron key.", 401)
    return jsonify({"status": "success", "data": run_tick()})
