"""
SYSTEM DESIGN CONCEPT: Controller Layer (Model-View-Controller pattern)
This file handles HTTP routing only. It delegates the heavy lifting to the Domain/Service layers.
"""
import hashlib
import hmac
import json
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, request, Response
from flask_cors import CORS

from api.core.config import IST, now_ist, to_ist, RECEIVER_EMAIL, APP_URL
from api.core.db import init_db, SessionLocal
from api.domain.factory import NotifierFactory
from api.domain.repositories import NotificationRepository, normalize_title
from api.domain.models import WatchSeries
from api.domain import integrations
from api.domain.todos import todos_bp
from api.domain.contests import contests_bp
from api.domain.syllabus import syllabus_bp
from api.domain.learning import learning_bp
from api.domain.sheets import sheets_bp
from api.domain.weekly import weekly_bp
from api.domain.insights import insights_bp
from api.domain.focus import focus_bp
from api.domain.journal import journal_bp
from api.domain.xp import xp_bp
from api.domain.features import features_bp
from api.domain.pdf_extract import pdf_extract_bp
from api.domain.mistakes import mistakes_bp
from api.domain.placements import placements_bp
from api.domain.oa import oa_bp
from api.domain.interview import interview_bp
from api.domain.gym import gym_bp
from api.domain.brief import brief_bp
from api.domain.habits import habits_bp
from api.domain.capture import capture_bp
from api.domain.flashcards import flashcards_bp
from api.domain.tutor import tutor_bp

app = Flask(__name__)
# Enable CORS so our React frontend (running on different port) can talk to this API
CORS(app)
for bp in (todos_bp, contests_bp, syllabus_bp, learning_bp, sheets_bp, weekly_bp, insights_bp, focus_bp, journal_bp, xp_bp, features_bp,
           pdf_extract_bp, mistakes_bp, placements_bp, oa_bp, interview_bp, gym_bp, brief_bp, habits_bp, capture_bp, flashcards_bp, tutor_bp):
    app.register_blueprint(bp)

# ---------------- Passcode login ----------------
# When APP_PASSCODE is set, every API call needs X-App-Key = sha256("daily:" + passcode).
# Scheduler endpoints stay open: each is throttled server-side, so they can't be used to spam.
_OPEN_ENDPOINTS = {"/api/health", "/api/auth/status", "/api/auth/login",
                   "/api/cron", "/api/digest", "/api/syllabus/remind", "/api/weekly/cron"}


def _auth_token():
    passcode = os.getenv("APP_PASSCODE", "")
    return hashlib.sha256(f"daily:{passcode}".encode()).hexdigest() if passcode else None


def _authorized():
    expected = _auth_token()
    return expected is None or hmac.compare_digest(request.headers.get("X-App-Key", ""), expected)


@app.before_request
def _require_passcode():
    if request.method == "OPTIONS" or not request.path.startswith("/api/") or request.path.rstrip("/") in _OPEN_ENDPOINTS:
        return None
    if not _authorized():
        return jsonify({"status": "error", "message": "Locked. Enter your passcode.", "auth_required": True}), 401


@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    return jsonify({"status": "success", "required": _auth_token() is not None, "ok": _authorized()})


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    expected = _auth_token()
    if expected is None:
        return jsonify({"status": "success", "token": ""})
    passcode = str((request.json or {}).get("passcode", ""))
    if not hmac.compare_digest(passcode, os.getenv("APP_PASSCODE", "")):
        time.sleep(1)  # slow down guessing
        return _err("Wrong passcode", 401)
    return jsonify({"status": "success", "token": expected})

# Initialize the Database
init_db()

SETTING_DEFAULTS = {
    "leetcode_interval_minutes": "60",
    "leetcode_paused": "0",
    "quiet_start": "23",       # IST hour; no emails from 23:00 ...
    "quiet_end": "7",          # ... until 07:00
    "leetcode_difficulty": "mixed",
    "leetcode_username": "Veratril",
    "cf_handle": "Veratril",
    "daily_goal": "2",
    "daily_study_hours": "3",
}


NUMERIC_SETTINGS = {
    "leetcode_interval_minutes": (1, 10080),
    "quiet_start": (0, 23),
    "quiet_end": (0, 23),
    "daily_goal": (1, 50),
    "daily_study_hours": (1, 16),
}


class _Repo:
    """Context manager: `with _Repo() as repo:` gives a repository and always closes the session."""
    def __enter__(self):
        self.db = SessionLocal()
        return NotificationRepository(self.db)

    def __exit__(self, *exc):
        self.db.close()


def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


@app.errorhandler(Exception)
def _unhandled(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    return _err(str(e), 500)


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _serialize_log(l, full=False):
    data = {
        "id": l.id, "type": l.task_type, "title": l.title, "is_completed": bool(l.is_completed),
        "timestamp": _iso(l.timestamp), "completed_at": _iso(l.completed_at),
        "slug": l.slug, "difficulty": l.difficulty, "link": l.link, "topic": l.topic,
        "has_writeup": bool(l.content and l.content.lstrip().startswith("{")),
    }
    if not data["link"] and l.task_type == "leetcode":
        data["link"] = "https://leetcode.com/problemset/?search=" + l.title.replace(" ", "+")
    if full:
        writeup = None
        if l.content:
            try:
                writeup = json.loads(l.content)
            except ValueError:
                writeup = {"statement": l.content}  # legacy rows stored the question text only
        data["writeup"] = writeup
        if l.task_type == "leetcode" and l.slug:
            from api.domain.notifiers import problem_links
            data["links"] = problem_links(l.slug, l.title)
    return data


# ---------------- Notifications ----------------
@app.route('/api/trigger', methods=['POST'])
def trigger_notification():
    """
    Expects JSON: {"type": "incident" | "leetcode"}
    """
    data = request.json or {}
    notif_type = data.get("type", "incident")

    db = SessionLocal()
    try:
        notifier = NotifierFactory.get_notifier(notif_type, db)
        if notif_type == "leetcode":
            solved_keys = set()
            try:
                solved_keys = _sync_leetcode(NotificationRepository(db), NotificationRepository(db).get_setting(
                    "leetcode_username", SETTING_DEFAULTS["leetcode_username"]))[1]
            except Exception as e:
                print(f"LeetCode sync failed: {e}")
            result = notifier.run(skip=solved_keys)
        else:
            result = notifier.run()

        if result["status"] == "success":
            return jsonify({"status": "success", "data": result})
        else:
            return _err("Failed to send email. Check SENDER_EMAIL / SENDER_PASSWORD.")
    except Exception as e:
        return _err(str(e), 500)
    finally:
        db.close()


def _in_quiet_hours(start: int, end: int, hour: int) -> bool:
    if start == end:
        return False
    if start > end:
        return hour >= start or hour < end
    return start <= hour < end


@app.route('/api/cron', methods=['POST'])
def cron_trigger():
    db = SessionLocal()
    try:
        repo = NotificationRepository(db)
        if repo.get_setting("leetcode_paused", "0") == "1":
            return jsonify({"status": "skipped", "message": "Paused."})

        hour = now_ist().hour
        if _in_quiet_hours(int(repo.get_setting("quiet_start", "23")), int(repo.get_setting("quiet_end", "7")), hour):
            return jsonify({"status": "skipped", "message": f"Quiet hours ({hour}:00 IST)."})

        interval_minutes = int(repo.get_setting("leetcode_interval_minutes", "60"))

        # Only check successful sends, so a failed email doesn't reset the timer
        last_successful = repo.get_latest_successful_leetcode_log()
        if last_successful:
            elapsed = (datetime.now(timezone.utc) - last_successful.timestamp.replace(tzinfo=timezone.utc)).total_seconds() / 60.0
            if elapsed < interval_minutes:
                return jsonify({"status": "skipped", "message": f"Only {elapsed:.1f} mins elapsed."})

        # Best effort: auto-complete problems already solved on LeetCode so reminders stay accurate
        username = repo.get_setting("leetcode_username", SETTING_DEFAULTS["leetcode_username"])
        solved_keys = set()
        if username:
            try:
                solved_keys = _sync_leetcode(repo, username)[1]
            except Exception as e:
                print(f"LeetCode sync failed: {e}")

        notifier = NotifierFactory.get_notifier("leetcode", db)
        result = notifier.run(skip=solved_keys)
        return jsonify({"status": "success", "data": result})
    finally:
        db.close()


# ---------------- Logs ----------------
@app.route('/api/logs', methods=['GET'])
def get_logs():
    task_type = request.args.get("type", "leetcode")
    with _Repo() as repo:
        return jsonify({"status": "success", "data": [_serialize_log(l) for l in repo.get_logs(task_type)]})


@app.route('/api/logs/<int:log_id>', methods=['GET', 'PUT', 'DELETE'])
def log_detail(log_id):
    with _Repo() as repo:
        if request.method == 'DELETE':
            if not repo.hide_log(log_id):
                return _err("Not found", 404)
            return jsonify({"status": "success"})
        if request.method == 'PUT':
            data = request.json or {}
            log = repo.mark_task_completed(log_id, bool(data.get("is_completed", True)))
        else:
            log = repo.get_log(log_id)
        if not log:
            return _err("Not found", 404)
        return jsonify({"status": "success", "data": _serialize_log(log, full=True)})


@app.route('/api/logs/<int:log_id>/writeup', methods=['POST'])
def regenerate_writeup(log_id):
    from api.core.clients import LLMClient
    from api.domain.notifiers import generate_writeup
    with _Repo() as repo:
        log = repo.get_log(log_id)
        if not log or log.task_type != "leetcode":
            return _err("Not found", 404)
        slug = log.slug or normalize_title(log.title)
        writeup = generate_writeup(LLMClient(), log.title, slug, log.difficulty or "")
        log.content = json.dumps(writeup)
        if not log.difficulty and writeup.get("difficulty"):
            log.difficulty = writeup["difficulty"]
        repo.db.commit()
        return jsonify({"status": "success", "data": _serialize_log(log, full=True)})


# ---------------- Spaced repetition ----------------
def _serialize_review(repo, l, now=None):
    return {**_serialize_log(l), "review_stage": l.review_stage or 0, "lapses": l.lapses or 0,
            "recall": round(repo.recall_now(l, now), 3),
            "stability_days": round(l.stability, 2) if l.stability is not None else None,
            "difficulty_fsrs": round(l.difficulty_fsrs, 2) if l.difficulty_fsrs is not None else None,
            "next_review_at": _iso(l.next_review_at), "last_review_at": _iso(l.last_review_at)}


@app.route('/api/reviews', methods=['GET'])
def due_reviews():
    """Due problems, weakest memory first. `data` stays a list (the digest reads it)."""
    with _Repo() as repo:
        due = repo.get_due_reviews(limit=20)
        upcoming = repo.upcoming_reviews(days=7)
        return jsonify({"status": "success", "data": [_serialize_review(repo, l) for l in due],
                        "due_count": repo.count_due_reviews(), "upcoming": upcoming,
                        "week_count": sum(d["count"] for d in upcoming)})


@app.route('/api/reviews/<int:log_id>', methods=['POST'])
def record_review(log_id):
    """Body {grade: again|hard|good|easy}; legacy {result: easy|hard} maps to good|again."""
    from api.domain.repositories import GRADES, LEGACY_RESULTS
    body = request.get_json(silent=True) or {}
    if "grade" in body:
        grade = str(body.get("grade") or "").lower()
    else:
        result = str(body.get("result") or "easy").lower()
        if result not in LEGACY_RESULTS:
            return _err("result must be 'easy' or 'hard'")
        grade = LEGACY_RESULTS[result]
    if grade not in GRADES:
        return _err("grade must be one of: " + ", ".join(GRADES))
    with _Repo() as repo:
        log = repo.get_log(log_id)
        if not log or log.task_type != "leetcode" or not log.is_completed:
            return _err("Not found", 404)
        log = repo.record_review(log, grade)
        interval = (log.next_review_at - log.last_review_at).total_seconds() / 86400 if log.next_review_at else None
        return jsonify({"status": "success", "data": {
            **_serialize_review(repo, log), "grade": grade, "graduated": log.next_review_at is None,
            "stability": round(log.stability, 2), "recall": round(getattr(log, "recall_before", 1.0), 3),
            "interval_days": round(interval) if interval is not None else None}})


# ---------------- Settings ----------------
@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    with _Repo() as repo:
        if request.method == 'POST':
            for key, value in (request.json or {}).items():
                if key not in SETTING_DEFAULTS:
                    continue
                value = str(value).strip()[:100]
                if key in NUMERIC_SETTINGS:
                    lo, hi = NUMERIC_SETTINGS[key]
                    if not value.isdigit() or not lo <= int(value) <= hi:
                        return _err(f"{key} must be a number between {lo} and {hi}")
                repo.set_setting(key, value)
        settings = {k: repo.get_setting(k, v) for k, v in SETTING_DEFAULTS.items()}
        settings["receiver_email"] = RECEIVER_EMAIL
        settings["llm_configured"] = bool(os.getenv("GEMINI_API_KEY"))
        settings["email_configured"] = bool(os.getenv("SENDER_EMAIL") and os.getenv("SENDER_PASSWORD"))
        return jsonify({"status": "success", **settings})


# ---------------- LeetCode ----------------
def _sync_leetcode(repo, username):
    recent = integrations.leetcode_recent_accepted(username, limit=20)
    keys, when = set(), {}
    for r in recent:  # newest first; keep the most recent solve time
        for k in (r["slug"], normalize_title(r["title"])):
            keys.add(k)
            when.setdefault(k, r["solved_at"])
    return repo.mark_completed_by_keys("leetcode", keys, when), keys


@app.route('/api/leetcode/sync', methods=['POST'])
def leetcode_sync():
    with _Repo() as repo:
        username = repo.get_setting("leetcode_username", SETTING_DEFAULTS["leetcode_username"])
        if not username:
            return _err("Set your LeetCode username in Settings first.")
        updated, _ = _sync_leetcode(repo, username)
        return jsonify({"status": "success", "updated": [l.title for l in updated]})


@app.route('/api/leetcode/profile', methods=['GET'])
def leetcode_profile():
    with _Repo() as repo:
        username = repo.get_setting("leetcode_username", SETTING_DEFAULTS["leetcode_username"])
    if not username:
        return jsonify({"status": "success", "data": None})
    return jsonify({"status": "success", "data": {"username": username, **integrations.leetcode_profile(username)}})


# ---------------- Codeforces ----------------
def _cf_suggested_range(rating):
    if not rating:
        return 800, 1200
    base = max(800, int(round(rating / 100.0)) * 100)
    return base, min(3500, base + 300)


@app.route('/api/cf/meta', methods=['GET'])
def cf_meta():
    with _Repo() as repo:
        handle = repo.get_setting("cf_handle", SETTING_DEFAULTS["cf_handle"])
    user = None
    if handle:
        try:
            user = integrations.cf_user_info(handle)
        except Exception as e:
            user = {"handle": handle, "error": str(e)}
    lo, hi = _cf_suggested_range(user.get("rating") if user else None)
    return jsonify({"status": "success", "user": user, "tags": integrations.cf_all_tags(),
                    "suggested_min": lo, "suggested_max": hi})


@app.route('/api/cf/suggest', methods=['POST'])
def cf_suggest():
    data = request.json or {}
    count = max(1, min(int(data.get("count", 5)), 10))
    tags = [t for t in data.get("tags", []) if isinstance(t, str)]
    with _Repo() as repo:
        handle = repo.get_setting("cf_handle", SETTING_DEFAULTS["cf_handle"])
        exclude = repo.get_sent_keys("codeforces")
        rating = None
        if handle:
            try:
                solved, attempted = integrations.cf_user_submissions(handle)
                exclude |= attempted
                rating = integrations.cf_user_info(handle).get("rating")
            except Exception as e:
                print(f"CF user lookup failed: {e}")
        lo, hi = _cf_suggested_range(rating)
        min_rating = int(data.get("min_rating") or lo)
        max_rating = int(data.get("max_rating") or hi)
        if min_rating > max_rating:
            min_rating, max_rating = max_rating, min_rating

        picked = integrations.cf_pick(count, min_rating, max_rating, tags, exclude, data.get("tag_mode", "any"))
        if not picked:
            return _err("No unseen problems match those filters. Widen the rating range or remove tags.", 404)

        logs = [repo.log_notification(
            task_type="codeforces", title=f"{p['contest_id']}{p['index']} · {p['name']}", content=None,
            slug=p["key"], difficulty=str(p["rating"]), link=p["url"], topic=", ".join(p["tags"])) for p in picked]

        emailed = bool(data.get("email")) and _email_cf_set(logs)
        return jsonify({"status": "success", "emailed": emailed, "data": [_serialize_log(l) for l in logs]})


def _email_cf_set(logs):
    import html as h
    from api.core.clients import EmailClient
    sender, password = os.getenv("SENDER_EMAIL"), os.getenv("SENDER_PASSWORD")
    if not (sender and password):
        return False
    plain = "\n".join(f"[{l.difficulty}] {l.title}\n{l.link}\n" for l in logs)
    rows = "".join(
        f'<tr><td style="padding:12px 0;border-bottom:1px solid #eee;font:15px system-ui,sans-serif">'
        f'<span style="display:inline-block;min-width:48px;font-weight:700;color:#4338ca">{h.escape(l.difficulty)}</span>'
        f'<a href="{h.escape(l.link)}" style="color:#111827;text-decoration:none;font-weight:600">{h.escape(l.title)}</a>'
        f'<div style="color:#6b7280;font-size:12px;margin:4px 0 0 52px">{h.escape(l.topic or "")}</div></td></tr>' for l in logs)
    body = (f'<div style="max-width:600px;margin:0 auto;padding:24px;background:#fff;border-radius:16px;border:1px solid #e5e7eb">'
            f'<h2 style="font:700 20px system-ui,sans-serif;margin:0 0 12px">Codeforces practice set</h2>'
            f'<table width="100%" cellspacing="0" cellpadding="0">{rows}</table></div>')
    return EmailClient(sender, password).send_email(RECEIVER_EMAIL, f"Codeforces set · {len(logs)} problems", plain, html=body)


@app.route('/api/cf/sync', methods=['POST'])
def cf_sync():
    with _Repo() as repo:
        handle = repo.get_setting("cf_handle", SETTING_DEFAULTS["cf_handle"])
        if not handle:
            return _err("Set your Codeforces handle in Settings first.")
        solved, _ = integrations.cf_user_submissions(handle)
        updated = repo.mark_completed_by_keys("codeforces", set(solved), solved)
        return jsonify({"status": "success", "updated": [l.title for l in updated]})


# ---------------- Daily episode ----------------
DEFAULT_SERIES = {
    "title": "Hajime no Ippo: New Challenger",
    "url_template": "https://anikoto.cz/watch/fighting-spirit-new-challenger-v0hk2/ep-{ep}",
    "total_episodes": 26,
    "next_episode": 2,
}


def _today_bounds_utc():
    start_ist = now_ist().replace(hour=0, minute=0, second=0, microsecond=0)
    start = start_ist.astimezone(timezone.utc).replace(tzinfo=None)
    return start, start + timedelta(days=1)


def _serialize_series(repo, s):
    start, end = _today_bounds_utc()
    watched_today = [l for l in repo.get_logs("watch")
                     if l.slug and l.slug.startswith(f"{s.id}:") and l.completed_at and start <= l.completed_at < end]
    finished = s.next_episode > s.total_episodes
    return {
        "id": s.id, "title": s.title, "url_template": s.url_template, "total_episodes": s.total_episodes,
        "next_episode": s.next_episode, "is_active": bool(s.is_active), "finished": finished,
        "next_url": None if finished else s.url_template.replace("{ep}", str(s.next_episode)),
        "watched_today": [int(l.slug.split(":")[1]) for l in watched_today],
        "progress": round(100 * min(s.next_episode - 1, s.total_episodes) / max(s.total_episodes, 1)),
    }


def _ensure_seeded(repo):
    if not repo.get_series() and repo.get_setting("watch_seeded") != "1":
        repo.save(WatchSeries(**DEFAULT_SERIES, is_active=True))
        repo.set_setting("watch_seeded", "1")


@app.route('/api/watch', methods=['GET', 'POST'])
def watch_list():
    with _Repo() as repo:
        if request.method == 'POST':
            data = request.json or {}
            template = (data.get("url_template") or "").strip()
            if "{ep}" not in template:
                return _err("URL template must contain {ep}, e.g. https://site/watch/show/ep-{ep}")
            if data.get("is_active", True):
                for other in repo.get_series():
                    other.is_active = False
            repo.save(WatchSeries(title=(data.get("title") or "Untitled").strip()[:200], url_template=template[:500],
                                  total_episodes=max(1, int(data.get("total_episodes") or 12)),
                                  next_episode=max(1, int(data.get("next_episode") or 1)), is_active=True))
        _ensure_seeded(repo)
        return jsonify({"status": "success", "data": [_serialize_series(repo, s) for s in repo.get_series()]})


@app.route('/api/watch/<int:series_id>', methods=['PUT', 'DELETE'])
def watch_detail(series_id):
    with _Repo() as repo:
        s = repo.get_series_by_id(series_id)
        if not s:
            return _err("Not found", 404)
        if request.method == 'DELETE':
            repo.delete(s)
            return jsonify({"status": "success"})
        data = request.json or {}
        if "title" in data:
            s.title = str(data["title"]).strip()[:200] or s.title
        if "url_template" in data:
            if "{ep}" not in data["url_template"]:
                return _err("URL template must contain {ep}")
            s.url_template = data["url_template"].strip()[:500]
        if "total_episodes" in data:
            s.total_episodes = max(1, int(data["total_episodes"]))
        if "next_episode" in data:
            s.next_episode = max(1, int(data["next_episode"]))
        if data.get("is_active"):
            for other in repo.get_series():
                other.is_active = other.id == s.id
        repo.save(s)
        return jsonify({"status": "success", "data": _serialize_series(repo, s)})


@app.route('/api/watch/<int:series_id>/watched', methods=['POST', 'DELETE'])
def watch_mark(series_id):
    """POST marks the next episode watched; DELETE undoes the most recent one."""
    with _Repo() as repo:
        s = repo.get_series_by_id(series_id)
        if not s:
            return _err("Not found", 404)
        if request.method == 'POST':
            if s.next_episode > s.total_episodes:
                return _err("Series finished. Add the next season!")
            ep = s.next_episode
            log = repo.log_notification("watch", f"{s.title} · Ep {ep}", None, slug=f"{s.id}:{ep}",
                                        link=s.url_template.replace("{ep}", str(ep)), topic=s.title)
            repo.mark_task_completed(log.id, True)
            s.next_episode = ep + 1
        else:
            last = next((l for l in repo.get_logs("watch") if l.slug and l.slug.startswith(f"{s.id}:")), None)
            if last:
                s.next_episode = int(last.slug.split(":")[1])
                repo.delete_log(last.id)
        repo.save(s)
        return jsonify({"status": "success", "data": _serialize_series(repo, s)})


# ---------------- Stats ----------------
@app.route('/api/stats', methods=['GET'])
def stats():
    with _Repo() as repo:
        today = now_ist().date()
        solves_by_day, watch_by_day = Counter(), Counter()
        for l in repo.get_completed_logs():
            day = to_ist(l.completed_at or l.timestamp).date()
            (watch_by_day if l.task_type == "watch" else solves_by_day)[day] += 1

        def streak(counter):
            d = today if counter.get(today) else today - timedelta(days=1)
            n = 0
            while counter.get(d):
                n += 1
                d -= timedelta(days=1)
            return n

        # Solve streak with freezes (earned/spent deterministically from history) and exam rest days
        from api.domain.focus import compute_streak, focus_minutes_by_day, suggest_goal, theory_exam_days
        rest_days = theory_exam_days(repo.db)
        solve_streak = compute_streak({d for d, n in solves_by_day.items() if n}, rest_days, today)
        frozen = set(solve_streak["frozen_days"])
        goal = int(repo.get_setting("daily_goal", "2") or 2)
        focus_by_day = focus_minutes_by_day(repo.db, datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7 * 53 + 2))

        lc = repo.get_logs("leetcode")
        cf = repo.get_logs("codeforces")
        by_diff = defaultdict(lambda: {"sent": 0, "solved": 0})
        topics = defaultdict(lambda: {"sent": 0, "solved": 0})
        for l in lc:
            by_diff[l.difficulty or "Unknown"]["sent"] += 1
            by_diff[l.difficulty or "Unknown"]["solved"] += int(bool(l.is_completed))
            if l.topic:
                topics[l.topic]["sent"] += 1
                topics[l.topic]["solved"] += int(bool(l.is_completed))

        days = 7 * 53

        def cell(d):
            iso = d.isoformat()
            return {"date": iso, "count": solves_by_day.get(d, 0), "focus": focus_by_day.get(d, 0),
                    "frozen": iso in frozen, "rest": d in rest_days}

        heatmap = [cell(today - timedelta(days=i)) for i in range(days - 1, -1, -1)]
        week = [{"date": (today - timedelta(days=i)).isoformat(), "count": solves_by_day.get(today - timedelta(days=i), 0)}
                for i in range(6, -1, -1)]
        return jsonify({"status": "success", "data": {
            "today": {"solved": solves_by_day.get(today, 0), "watched": watch_by_day.get(today, 0),
                      "goal": goal, "date": today.isoformat(), "focus_minutes": focus_by_day.get(today, 0)},
            "streak": solve_streak["streak"], "best_streak": solve_streak["best_streak"],
            "freezes_available": solve_streak["freezes_available"], "frozen_days": solve_streak["frozen_days"],
            "rest_days": sorted(d.isoformat() for d in rest_days),
            "suggested_goal": suggest_goal(solves_by_day, today, goal, rest_days),
            "focus_minutes_today": focus_by_day.get(today, 0),
            "watch_streak": streak(watch_by_day),
            "totals": {"lc_sent": len(lc), "lc_solved": sum(1 for l in lc if l.is_completed),
                       "cf_sent": len(cf), "cf_solved": sum(1 for l in cf if l.is_completed),
                       "episodes": sum(watch_by_day.values())},
            "by_difficulty": by_diff, "topics": [{"topic": k, **v} for k, v in sorted(topics.items())],
            "heatmap": heatmap, "week": week,
        }})


# ---------------- PDF Studio ----------------
@app.route('/api/pdf/explain', methods=['POST'])
def explain_pdf():
    from api.domain.pdf_analyzer import PDFAnalyzer
    data = request.json or {}
    images = data.get("images") or []
    if not images and not data.get("text"):
        return _err("No pages provided")
    analyzer = PDFAnalyzer()
    stream = analyzer.explain_stream(str(data.get("label", "")), int(data.get("total_pages") or 0), images,
                                     data.get("text", ""), (data.get("focus") or "")[:500])
    return Response(stream, mimetype='text/event-stream', headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route('/api/pdf/quiz', methods=['POST'])
def generate_quiz():
    from api.domain.pdf_analyzer import PDFAnalyzer
    data = request.json or {}
    text = data.get("text")
    if not text:
        return _err("No text provided")
    result = PDFAnalyzer().generate_quiz(text)
    return jsonify(result) if result["status"] == "success" else (jsonify(result), 500)


# ---------------- Morning digest ----------------
def _internal_get(path):
    """Reuse our own endpoints so the digest always matches what the dashboard shows."""
    try:
        res = app.test_client().get(path)
        return res.get_json() if res.status_code == 200 else None
    except Exception as e:
        print(f"digest: {path} failed: {e}")
        return None


@app.route('/api/digest', methods=['POST'])
def morning_digest():
    import html as h
    from api.core.clients import EmailClient
    sender, password = os.getenv("SENDER_EMAIL"), os.getenv("SENDER_PASSWORD")
    if not (sender and password):
        return jsonify({"status": "skipped", "message": "Email not configured."})
    with _Repo() as repo:
        last = repo.get_setting("digest_last")
        if last and request.args.get("force") != "1" and                 datetime.now(timezone.utc) - datetime.fromisoformat(last) < timedelta(hours=20):
            return jsonify({"status": "skipped", "message": "Digest already sent today."})

    e = h.escape
    sections = []

    def section(title, items):
        if items:
            lis = "".join(f'<li style="margin:0 0 6px">{i}</li>' for i in items)
            sections.append(f'<h3 style="margin:22px 0 8px;font:600 12px system-ui,sans-serif;letter-spacing:.08em;'
                            f'text-transform:uppercase;color:#6b7280">{title}</h3>'
                            f'<ul style="margin:0;padding-left:18px;font:15px/1.5 system-ui,sans-serif;color:#111827">{lis}</ul>')

    def link(url, text):
        return f'<a href="{e(url or "")}" style="color:#c2410c;text-decoration:none;font-weight:600">{e(text)}</a>'

    watch = (_internal_get("/api/watch") or {}).get("data") or []
    active = next((x for x in watch if x.get("is_active")), None)
    if active and not active.get("finished"):
        section("Today's episode", [link(active["next_url"], f'{active["title"]} · Episode {active["next_episode"]}')])

    todos = (_internal_get("/api/todos") or {}).get("data") or []
    section("Today's plan", [e(t["text"]) + (' <span style="color:#9ca3af">(carried over)</span>' if t.get("carried") else "")
                             for t in todos if not t.get("done")])

    reviews = (_internal_get("/api/reviews") or {}).get("data") or []
    section(f"Revise ({len(reviews)} due)", [link(r["link"], r["title"]) for r in reviews[:5]])

    pending = [l for l in ((_internal_get("/api/logs?type=leetcode") or {}).get("data") or []) if not l["is_completed"]]
    section(f"Pending problems ({len(pending)})", [link(l["link"], l["title"]) + f' <span style="color:#9ca3af">· {e(l.get("difficulty") or "")}</span>'
                                                  for l in pending[:4]])

    soon = []
    for c in (_internal_get("/api/contests") or {}).get("data") or []:
        start = datetime.fromisoformat(c["start"].replace("Z", "+00:00"))
        if start - datetime.now(timezone.utc) < timedelta(hours=36):
            soon.append(link(c["url"], c["name"]) + f' <span style="color:#9ca3af">· {start.astimezone(IST).strftime("%a %I:%M %p")} IST</span>')
    section("Contests coming up", soon)

    syl = _internal_get("/api/syllabus") or {}
    nxt = syl.get("next_exam")
    if nxt:
        section("End-sem", [f'<b>{e(nxt["subject"])}</b> in {nxt["days_left"]} days'])

    stats = (_internal_get("/api/stats") or {}).get("data") or {}
    streak = stats.get("streak", 0)
    today = now_ist()
    body = (f'<!doctype html><html><body style="margin:0;background:#f5f5f7;padding:24px 12px">'
            f'<div style="max-width:620px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:18px;padding:28px">'
            f'<div style="font:600 12px system-ui,sans-serif;color:#6b7280">{today.strftime("%A, %d %B")}</div>'
            f'<h1 style="margin:8px 0 4px;font:700 24px system-ui,sans-serif;color:#111827">Good morning, Sai.</h1>'
            f'<p style="margin:0;font:15px system-ui,sans-serif;color:#4b5563">🔥 Streak: <b>{streak} day{"s" if streak != 1 else ""}</b>. '
            f'Goal today: <b>{stats.get("today", {}).get("goal", 2)}</b> problems.</p>'
            + "".join(sections) +
            f'<p style="margin:26px 0 0"><a href="{APP_URL}" style="display:inline-block;background:#111827;color:#fff;padding:11px 18px;'
            f'border-radius:10px;font:600 14px system-ui,sans-serif;text-decoration:none">Open dashboard</a></p></div></body></html>')
    plain = "Your daily dashboard: " + APP_URL
    ok = EmailClient(sender, password).send_email(RECEIVER_EMAIL, f"☀️ Today · streak {streak} · {len(reviews)} to revise", plain, html=body)
    if ok:
        with _Repo() as repo:
            repo.set_setting("digest_last", datetime.now(timezone.utc).isoformat())
    return jsonify({"status": "success" if ok else "error", "sections": len(sections)})


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
