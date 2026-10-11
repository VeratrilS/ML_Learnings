"""
Weekly report (beta): a 7-day recap of everything tracked, compared with the week before.

Shown in the app as a page and emailed on Sundays (7:30 PM IST via the scheduler) -- but the
automatic email only goes out once the 'weekly' feature is approved in the Beta Lab.

Endpoints:
  GET  /api/weekly?weeks_ago=0   -> the report for the 7 IST days ending today (or N weeks back)
  POST /api/weekly/send          -> email this week's report now
  POST /api/weekly/cron          -> scheduler entry: sends only when approved, at most once per 6 days
"""
import html
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from api.core.config import APP_URL, RECEIVER_EMAIL, now_ist, to_ist
from api.core.db import SessionLocal
from api.domain.models import NotificationLog

FEATURE_KEY = "weekly"
LAST_SENT_KEY = "weekly_last"
MIN_GAP = timedelta(days=6)
MAX_WEEKS_AGO = 52

weekly_bp = Blueprint("weekly", __name__, url_prefix="/api/weekly")


def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _day(dt):
    return to_ist(dt).date() if dt else None


# ---------------- report ----------------
def _solves(db):
    """Completed LeetCode / Codeforces logs as (IST day, log)."""
    rows = db.query(NotificationLog).filter(
        NotificationLog.is_completed == True,  # noqa: E712
        NotificationLog.status == "success",
        NotificationLog.task_type.in_(["leetcode", "codeforces"]),
    ).all()
    return [(_day(l.completed_at or l.timestamp), l) for l in rows]


def _optional(db, fn, default):
    """Tables owned by other features may not exist yet; a missing one just leaves its section empty."""
    try:
        return fn()
    except Exception as e:
        db.rollback()  # Postgres aborts the transaction on a missing table
        print(f"weekly report: section skipped: {e}")
        return default


def _done_days(db, model):
    return [_day(dt) for (dt,) in db.query(model.done_at).filter(model.done == True).all()]  # noqa: E712


def build_report(db, weeks_ago=0):
    from api.domain.focus import compute_streak, focus_minutes_by_day, theory_exam_days
    from api.domain.learning import Course, Lesson
    from api.domain.repositories import NotificationRepository
    from api.domain.sheets import SheetProblem

    today = now_ist().date()
    end = today - timedelta(days=7 * weeks_ago)
    start = end - timedelta(days=6)
    prev_start, prev_end = start - timedelta(days=7), start - timedelta(days=1)
    days = [start + timedelta(days=i) for i in range(7)]

    def in_week(d):
        return d is not None and start <= d <= end

    def in_prev(d):
        return d is not None and prev_start <= d <= prev_end

    solves = _solves(db)
    week_solves = [l for d, l in solves if in_week(d)]
    per_day = Counter(d for d, _ in solves if in_week(d))
    raw_goal = NotificationRepository(db).get_setting("daily_goal", "2") or "2"
    goal = max(1, int(raw_goal)) if str(raw_goal).isdigit() else 2
    streak = compute_streak({d for d, _ in solves}, theory_exam_days(db), today)

    focus = focus_minutes_by_day(db, datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7 * weeks_ago + 16))
    lesson_days = _optional(db, lambda: _done_days(db, Lesson), [])
    sheet_days = _optional(db, lambda: [(_day(p.done_at), p.difficulty) for p in
                                        db.query(SheetProblem).filter(SheetProblem.done == True).all()], [])  # noqa: E712

    reviewed = [l for (l,) in db.query(NotificationLog.last_review_at).filter(NotificationLog.last_review_at != None).all()]  # noqa: E711
    episodes = [_day(dt) for (dt,) in db.query(NotificationLog.completed_at).filter(
        NotificationLog.task_type == "watch", NotificationLog.is_completed == True).all()]  # noqa: E712

    by_diff = Counter(l.difficulty or "Unknown" for l in week_solves)
    topics = Counter()
    for l in week_solves:
        for t in (l.topic or "").split(","):
            if t.strip():
                topics[t.strip()] += 1

    def count(dates, pred):
        return sum(1 for d in dates if pred(d))

    solved = len(week_solves)
    prev_solved = sum(1 for d, _ in solves if in_prev(d))
    focus_week = sum(focus.get(d, 0) for d in days)
    focus_prev = sum(m for d, m in focus.items() if in_prev(d))

    # Where to pick up next week
    next_lesson = _optional(db, lambda: db.query(Lesson).join(Course, Course.id == Lesson.course_id)
                            .filter(Course.is_active == True, Lesson.done == False)  # noqa: E712
                            .order_by(Course.position, Lesson.position).first(), None)
    next_sheet = _optional(db, lambda: db.query(SheetProblem).filter(SheetProblem.done == False)  # noqa: E712
                           .order_by(SheetProblem.sheet, SheetProblem.position).first(), None)
    sheet_total = _optional(db, lambda: db.query(SheetProblem).count(), 0)
    lesson_total = _optional(db, lambda: db.query(Lesson).count(), 0)

    best = max(days, key=lambda d: (per_day.get(d, 0), d))
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "weeks_ago": weeks_ago,
        "days": [{"date": d.isoformat(), "solved": per_day.get(d, 0), "focus": focus.get(d, 0),
                  "goal_met": per_day.get(d, 0) >= goal} for d in days],
        "goal": goal,
        "solved": solved,
        "solved_prev": prev_solved,
        "leetcode": sum(1 for l in week_solves if l.task_type == "leetcode"),
        "codeforces": sum(1 for l in week_solves if l.task_type == "codeforces"),
        "by_difficulty": dict(by_diff),
        "topics": [{"topic": t, "count": n} for t, n in topics.most_common(5)],
        "active_days": sum(1 for d in days if per_day.get(d, 0)),
        "goal_days": sum(1 for d in days if per_day.get(d, 0) >= goal),
        "best_day": {"date": best.isoformat(), "solved": per_day.get(best, 0)} if per_day else None,
        "focus_minutes": focus_week,
        "focus_minutes_prev": focus_prev,
        "videos": count(lesson_days, in_week),
        "videos_prev": count(lesson_days, in_prev),
        "videos_done": len(lesson_days),
        "videos_total": lesson_total,
        "sheet": count([d for d, _ in sheet_days], in_week),
        "sheet_prev": count([d for d, _ in sheet_days], in_prev),
        "sheet_by_difficulty": dict(Counter(diff for d, diff in sheet_days if in_week(d))),
        "sheet_done": len(sheet_days),
        "sheet_total": sheet_total,
        "revisions": count([_day(dt) for dt in reviewed], in_week),
        "episodes": count(episodes, in_week),
        "streak": streak["streak"],
        "best_streak": streak["best_streak"],
        "next": {
            "lesson": {"title": next_lesson.title, "position": next_lesson.position} if next_lesson else None,
            "sheet": {"title": next_sheet.title, "leetcode_id": next_sheet.leetcode_id, "difficulty": next_sheet.difficulty,
                      "url": f"https://leetcode.com/problems/{next_sheet.slug}/"} if next_sheet else None,
        },
    }


# ---------------- email ----------------
def _fmt_range(r):
    s, e = datetime.fromisoformat(r["start"]), datetime.fromisoformat(r["end"])
    return f"{s.strftime('%d %b')} – {e.strftime('%d %b')}"


def _delta(now, prev, unit=""):
    diff = now - prev
    if not diff:
        return '<span style="color:#9ca3af">same as last week</span>'
    color = "#16a34a" if diff > 0 else "#dc2626"
    return f'<span style="color:{color}">{"+" if diff > 0 else "−"}{abs(diff)}{unit} vs last week</span>'


def render_email(r):
    e = html.escape
    hours = f"{r['focus_minutes'] / 60:.1f}h"
    tiles = [
        ("Problems solved", str(r["solved"]), _delta(r["solved"], r["solved_prev"])),
        ("Apple sheet", str(r["sheet"]), f'{r["sheet_done"]}/{r["sheet_total"]} total'),
        ("System design videos", str(r["videos"]), f'{r["videos_done"]}/{r["videos_total"]} total'),
        ("Focus time", hours, _delta(r["focus_minutes"], r["focus_minutes_prev"], " min")),
    ]
    cells = [
        f'<td width="50%" style="padding:6px"><div style="border:1px solid #e5e7eb;border-radius:14px;padding:14px">'
        f'<div style="font:600 11px system-ui,sans-serif;letter-spacing:.06em;text-transform:uppercase;color:#6b7280">{e(label)}</div>'
        f'<div style="font:700 26px system-ui,sans-serif;color:#111827;margin-top:4px">{e(value)}</div>'
        f'<div style="font:12px system-ui,sans-serif;margin-top:2px;color:#6b7280">{sub}</div></div></td>'
        for label, value, sub in tiles]
    grid = ('<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:18px">'
            f'<tr>{cells[0]}{cells[1]}</tr><tr>{cells[2]}{cells[3]}</tr></table>')  # 2 x 2 tiles

    bars = "".join(
        f'<td align="center" valign="bottom" style="padding:0 3px">'
        f'<div style="font:600 11px system-ui,sans-serif;color:#111827">{d["solved"] or ""}</div>'
        f'<div style="height:{8 + min(d["solved"], 8) * 9}px;width:26px;border-radius:6px;'
        f'background:{"#ea580c" if d["goal_met"] else ("#fdba74" if d["solved"] else "#e5e7eb")}"></div>'
        f'<div style="font:11px system-ui,sans-serif;color:#6b7280;margin-top:4px">'
        f'{datetime.fromisoformat(d["date"]).strftime("%a")[:2]}</div></td>'
        for d in r["days"])

    lines = [f'Active on <b>{r["active_days"]}/7</b> days · goal of {r["goal"]} hit on <b>{r["goal_days"]}</b>',
             f'🔥 Streak <b>{r["streak"]}</b> days (best {r["best_streak"]})']
    if r["by_difficulty"]:
        lines.append("Difficulty: " + " · ".join(f"{e(k)} {v}" for k, v in sorted(r["by_difficulty"].items())))
    if r["topics"]:
        lines.append("Topics: " + ", ".join(f'{e(t["topic"])} ({t["count"]})' for t in r["topics"]))
    if r["revisions"]:
        lines.append(f'Revised <b>{r["revisions"]}</b> problems')
    if r["episodes"]:
        lines.append(f'Watched <b>{r["episodes"]}</b> episodes')
    stats = "".join(f'<li style="margin:0 0 6px">{x}</li>' for x in lines)

    nxt = []
    if r["next"]["sheet"]:
        s = r["next"]["sheet"]
        nxt.append(f'Apple sheet: <a href="{e(s["url"])}" style="color:#c2410c;font-weight:600;text-decoration:none">'
                   f'{s["leetcode_id"]}. {e(s["title"])}</a> <span style="color:#9ca3af">· {e(s["difficulty"])}</span>')
    if r["next"]["lesson"]:
        nxt.append(f'System design: #{r["next"]["lesson"]["position"]} {e(r["next"]["lesson"]["title"])}')
    up_next = ("<h3 style=\"margin:22px 0 8px;font:600 12px system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase;"
               "color:#6b7280\">Pick up next week</h3><ul style=\"margin:0;padding-left:18px;font:15px/1.5 system-ui,sans-serif;"
               f"color:#111827\">{''.join(f'<li style=\"margin:0 0 6px\">{x}</li>' for x in nxt)}</ul>") if nxt else ""

    return (f'<!doctype html><html><body style="margin:0;background:#f5f5f7;padding:24px 12px">'
            f'<div style="max-width:620px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:18px;padding:28px">'
            f'<div style="font:600 12px system-ui,sans-serif;color:#6b7280">Weekly report · {_fmt_range(r)}</div>'
            f'<h1 style="margin:8px 0 4px;font:700 24px system-ui,sans-serif;color:#111827">Your week, Sai.</h1>'
            f'<p style="margin:0;font:15px system-ui,sans-serif;color:#4b5563">{r["solved"]} problems solved '
            f'({r["leetcode"]} LeetCode, {r["codeforces"]} Codeforces).</p>'
            f'{grid}'
            f'<table cellspacing="0" cellpadding="0" style="margin:22px auto 0"><tr>{bars}</tr></table>'
            f'<ul style="margin:22px 0 0;padding-left:18px;font:15px/1.5 system-ui,sans-serif;color:#111827">{stats}</ul>'
            f'{up_next}'
            f'<p style="margin:26px 0 0"><a href="{APP_URL}#/weekly" style="display:inline-block;background:#111827;color:#fff;'
            f'padding:11px 18px;border-radius:10px;font:600 14px system-ui,sans-serif;text-decoration:none">Open full report</a></p>'
            f'</div></body></html>')


def send_report(db):
    from api.core.clients import EmailClient
    sender, password = os.getenv("SENDER_EMAIL"), os.getenv("SENDER_PASSWORD")
    if not (sender and password):
        return None
    r = build_report(db)
    subject = f"📊 Your week · {r['solved']} solved · {r['sheet']} Apple · {r['videos']} videos"
    plain = f"Weekly report {_fmt_range(r)}: {r['solved']} problems solved. Full report: {APP_URL}#/weekly"
    return EmailClient(sender, password).send_email(RECEIVER_EMAIL, subject, plain, html=render_email(r))


def _approved(db):
    from api.domain.features import FeatureFlag
    flag = _optional(db, lambda: db.query(FeatureFlag).filter(FeatureFlag.key == FEATURE_KEY).first(), None)
    return bool(flag and flag.status == "approved")


# ---------------- routes ----------------
@weekly_bp.route("", methods=["GET"])
def get_report():
    try:
        weeks_ago = int(request.args.get("weeks_ago", 0))
    except ValueError:
        return _err("weeks_ago must be a number")
    if not 0 <= weeks_ago <= MAX_WEEKS_AGO:
        return _err(f"weeks_ago must be between 0 and {MAX_WEEKS_AGO}")
    db = SessionLocal()
    try:
        return jsonify({"status": "success", "data": build_report(db, weeks_ago)})
    finally:
        db.close()


@weekly_bp.route("/send", methods=["POST"])
def send_now():
    db = SessionLocal()
    try:
        ok = send_report(db)
        if ok is None:
            return _err("Email not configured. Set SENDER_EMAIL / SENDER_PASSWORD.")
        return jsonify({"status": "success"}) if ok else _err("Failed to send the email.", 502)
    finally:
        db.close()


@weekly_bp.route("/cron", methods=["POST"])
def cron():
    from api.domain.repositories import NotificationRepository
    db = SessionLocal()
    try:
        if not _approved(db):
            return jsonify({"status": "skipped", "message": "Weekly report is in beta; approve it in the Beta Lab to get it on Sundays."})
        repo = NotificationRepository(db)
        last = repo.get_setting(LAST_SENT_KEY)
        if last and datetime.now(timezone.utc) - datetime.fromisoformat(last) < MIN_GAP:
            return jsonify({"status": "skipped", "message": "Already sent this week."})
        ok = send_report(db)
        if ok is None:
            return jsonify({"status": "skipped", "message": "Email not configured."})
        if ok:
            repo.set_setting(LAST_SENT_KEY, datetime.now(timezone.utc).isoformat())
        return jsonify({"status": "success"}) if ok else jsonify({"status": "error", "message": "Failed to send the email."})
    finally:
        db.close()
