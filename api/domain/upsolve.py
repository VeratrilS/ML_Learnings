"""
Contest upsolve coach.

Looks at your last few rated contests on Codeforces and LeetCode, works out which problems you
solved during the contest, which you upsolved later, and which are still open. The "queue" is the
handful of open problems just above what you managed: on Codeforces anything rated up to
(max solved + 400); on LeetCode the unsolved problems up to one past your in-contest count.

Network results are cached in-process for 30 minutes; skips and AI hints are persisted.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from flask import Blueprint, jsonify, request
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from api.core.clients import LLMClient
from api.core.db import Base, SessionLocal, engine
from api.domain.integrations import _HEADERS, _cf_get, cf_user_submissions, leetcode_recent_accepted
from api.domain.repositories import NotificationRepository

CACHE_TTL = 30 * 60
CF_CONTESTS = 5
LC_CONTESTS = 5
QUEUE_SIZE = 6
CF_STRETCH = 400
LC_DURATION = 90 * 60
LLM_BUDGET = 30
MAX_URL = 300
MAX_NAME = 200
ALLOWED_HOSTS = ("https://codeforces.com/", "https://leetcode.com/")

_CACHE = {}  # (cf_handle, lc_username) -> {"at": ts, "contests": [...], "errors": [...]}


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UpsolveItem(Base):
    """One problem we've remembered something about: a skip, or a generated hint."""
    __tablename__ = "upsolve_items"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(MAX_URL), nullable=False, unique=True, index=True)
    name = Column(String(MAX_NAME), nullable=True)
    skipped = Column(Boolean, default=False, nullable=False)
    hint = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


upsolve_bp = Blueprint("upsolve", __name__, url_prefix="/api/upsolve")


@upsolve_bp.record_once
def _ensure_table(state):
    try:
        UpsolveItem.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:  # e.g. a concurrent cold start created it first
        print(f"upsolve table check skipped: {e}")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _iso_ts(ts):
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat() if ts else None


def _lc_difficulty(credit):
    if not credit:
        return None
    return "Easy" if credit <= 3 else "Medium" if credit <= 5 else "Hard"


def _clean_url(value):
    url = value.strip() if isinstance(value, str) else ""
    if not url or len(url) > MAX_URL or not url.startswith(ALLOWED_HOSTS):
        return None
    return url


# ---------------- Codeforces ----------------
def _cf_call(method, **params):
    """_cf_get with one retry when Codeforces rate-limits us."""
    try:
        return _cf_get(method, **params)
    except ValueError as e:
        if "limit" not in str(e).lower():
            raise
        time.sleep(1.2)
        return _cf_get(method, **params)


def cf_contests(handle):
    """Breakdown of the handle's last CF_CONTESTS rated contests, newest first."""
    history = _cf_call("user.rating", handle=handle) or []
    recent = list(reversed(history[-CF_CONTESTS:]))
    if not recent:
        return [], []
    solved_at, _ = cf_user_submissions(handle)
    contests, errors = [], []
    for rc in recent:
        cid = rc["contestId"]
        try:
            st = _cf_call("contest.standings", contestId=cid, handles=handle, showUnofficial="true")
        except Exception as e:
            errors.append(f"Codeforces contest {cid}: {e}")
            continue
        problems = st.get("problems") or []
        in_contest = set()
        for row in st.get("rows") or []:
            if (row.get("party") or {}).get("participantType") not in ("CONTESTANT", "OUT_OF_COMPETITION"):
                continue
            for p, res in zip(problems, row.get("problemResults") or []):
                if (res.get("points") or 0) > 0:
                    in_contest.add(p["index"])

        items = []
        for p in problems:
            key = f"{cid}/{p['index']}"
            status = "contest" if p["index"] in in_contest else "upsolved" if key in solved_at else "unsolved"
            items.append({
                "index": p["index"], "name": p.get("name") or p["index"], "rating": p.get("rating"),
                "difficulty": None, "points": None, "status": status, "target": False,
                "url": f"https://codeforces.com/contest/{cid}/problem/{p['index']}",
            })
        solved = [i for i in items if i["status"] != "unsolved"]
        rated = [i["rating"] for i in solved if i["rating"]]
        ceiling = (max(rated) if rated else (rc.get("newRating") or 1200)) + CF_STRETCH
        n_solved = len(solved)
        for pos, i in enumerate(items, start=1):
            if i["status"] == "unsolved":
                i["target"] = i["rating"] <= ceiling if i["rating"] else pos <= n_solved + 1

        contest = st.get("contest") or {}
        contests.append({
            "platform": "codeforces", "id": str(cid),
            "name": contest.get("name") or rc.get("contestName") or f"Contest {cid}",
            "url": f"https://codeforces.com/contest/{cid}",
            "start": _iso_ts(contest.get("startTimeSeconds") or rc.get("ratingUpdateTimeSeconds")),
            "rank": rc.get("rank"), "rating_change": (rc.get("newRating") or 0) - (rc.get("oldRating") or 0),
            "max_solved_rating": max(rated) if rated else None, "note": None, "problems": items,
        })
    return contests, errors


# ---------------- LeetCode ----------------
def lc_contest_history(username):
    """[{title, slug, start(ts), solved, total}] for contests the user attended, newest first."""
    query = """query h($username: String!) {
      userContestRankingHistory(username: $username) {
        attended problemsSolved totalProblems contest { title titleSlug startTime }
      }
    }"""
    r = requests.post("https://leetcode.com/graphql", json={"query": query, "variables": {"username": username}},
                      headers=_HEADERS, timeout=15)
    r.raise_for_status()
    rows = (r.json().get("data") or {}).get("userContestRankingHistory") or []
    out = [{"title": h["contest"]["title"], "slug": h["contest"]["titleSlug"], "start": int(h["contest"]["startTime"] or 0),
            "solved": int(h.get("problemsSolved") or 0), "total": int(h.get("totalProblems") or 0)}
           for h in rows if h.get("attended") and h.get("contest")]
    return sorted(out, key=lambda c: c["start"], reverse=True)


def lc_contest_questions(slug):
    """[{title, slug, credit}] in contest order. LeetCode sometimes blocks this endpoint; callers handle errors."""
    r = requests.get(f"https://leetcode.com/contest/api/info/{slug}/", headers=_HEADERS, timeout=15)
    r.raise_for_status()
    qs = r.json().get("questions") or []
    return [{"title": q.get("title") or q.get("title_slug"), "slug": q.get("title_slug"), "credit": q.get("credit")}
            for q in qs if q.get("title_slug")]


def lc_contests(username):
    history = lc_contest_history(username)[:LC_CONTESTS]
    if not history:
        return [], []
    errors = []
    try:
        recent = leetcode_recent_accepted(username, limit=20)
    except Exception as e:
        recent = []
        errors.append(f"LeetCode recent AC: {e}")
    first_ac = {}
    for s in recent:
        at = s["solved_at"].replace(tzinfo=timezone.utc).timestamp()
        first_ac[s["slug"]] = min(at, first_ac.get(s["slug"], at))
    oldest_ac = min(first_ac.values()) if first_ac else None

    contests = []
    for h in history:
        note = None
        try:
            qs = lc_contest_questions(h["slug"])
        except Exception:
            qs, note = [], "Problem list unavailable right now (LeetCode blocked the request)."
        # Is our AC window old enough to tell what happened in this contest?
        covered = oldest_ac is not None and oldest_ac <= h["start"] + LC_DURATION
        end = h["start"] + LC_DURATION
        items = []
        for pos, q in enumerate(qs, start=1):
            at = first_ac.get(q["slug"])
            if at is not None:
                status = "contest" if at <= end else "upsolved"
            elif not covered and pos <= h["solved"]:
                status = "contest"  # older than our AC window: assume the easiest ones went in during the contest
            else:
                status = "unsolved"
            items.append({
                "index": f"Q{pos}", "name": q["title"], "rating": None, "points": q["credit"],
                "difficulty": _lc_difficulty(q["credit"]), "status": status,
                "target": status == "unsolved" and pos <= h["solved"] + 1,
                "url": f"https://leetcode.com/problems/{q['slug']}/",
            })
        contests.append({
            "platform": "leetcode", "id": h["slug"], "name": h["title"],
            "url": f"https://leetcode.com/contest/{h['slug']}/",
            "start": _iso_ts(h["start"]), "rank": None, "rating_change": None, "max_solved_rating": None,
            "solved_in_contest_reported": h["solved"], "note": note, "problems": items,
        })
    return contests, errors


# ---------------- assembly ----------------
def _handles(db):
    repo = NotificationRepository(db)
    return ((repo.get_setting("cf_handle", "Veratril") or "").strip(),
            (repo.get_setting("leetcode_username", "Veratril") or "").strip())


def _fetch(cf_handle, lc_user):
    jobs = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        if cf_handle:
            jobs["Codeforces"] = pool.submit(cf_contests, cf_handle)
        if lc_user:
            jobs["LeetCode"] = pool.submit(lc_contests, lc_user)
        contests, errors = [], []
        for label, fut in jobs.items():
            try:
                c, e = fut.result()
                contests += c
                errors += e
            except Exception as e:
                errors.append(f"{label}: {e}")
    contests.sort(key=lambda c: c["start"] or "", reverse=True)
    return contests, errors


def _snapshot(cf_handle, lc_user, refresh=False):
    key = (cf_handle, lc_user)
    hit = _CACHE.get(key)
    if hit and not refresh and time.time() - hit["at"] < CACHE_TTL:
        return hit
    contests, errors = _fetch(cf_handle, lc_user)
    snap = {"at": time.time(), "contests": contests, "errors": errors}
    if contests or not hit:  # keep the last good snapshot if everything failed this time
        _CACHE[key] = snap
        return snap
    return {**hit, "errors": errors}


def _decorate(contests, memory):
    """Fresh copies with skip/hint flags + per-contest progress, and the ranked queue."""
    out, queue = [], []
    for rank, c in enumerate(contests):
        probs = []
        for p in c["problems"]:
            m = memory.get(p["url"])
            probs.append({**p, "skipped": bool(m and m.skipped), "has_hint": bool(m and m.hint)})
        in_contest = sum(p["status"] == "contest" for p in probs)
        upsolved = sum(p["status"] == "upsolved" for p in probs)
        targets = [p for p in probs if p["target"]]
        out.append({**c, "problems": probs, "solved_in_contest": in_contest, "upsolved": upsolved,
                    "total": len(probs), "targets_left": sum(not p["skipped"] for p in targets)})
        for p in targets:
            if not p["skipped"]:
                queue.append((rank, p["rating"] or 0, p["index"], {
                    **p, "platform": c["platform"], "contest": c["name"], "contest_url": c["url"],
                    "contest_start": c["start"],
                }))
    queue.sort(key=lambda t: t[:3])
    return out, [t[3] for t in queue[:QUEUE_SIZE]]


def _memory(db, urls):
    if not urls:
        return {}
    return {m.url: m for m in db.query(UpsolveItem).filter(UpsolveItem.url.in_(list(urls))).all()}


def _get_item(db, url, name=None):
    item = db.query(UpsolveItem).filter(UpsolveItem.url == url).first()
    if not item:
        item = UpsolveItem(url=url, name=(name or None), skipped=False)
        db.add(item)
    elif name and not item.name:
        item.name = name
    return item


# ---------------- routes ----------------
@upsolve_bp.route("", methods=["GET"])
@upsolve_bp.route("/", methods=["GET"])
def get_upsolve():
    db = SessionLocal()
    try:
        cf_handle, lc_user = _handles(db)
        snap = _snapshot(cf_handle, lc_user, refresh=request.args.get("refresh") in ("1", "true"))
        urls = {p["url"] for c in snap["contests"] for p in c["problems"]}
        contests, queue = _decorate(snap["contests"], _memory(db, urls))
        return jsonify({
            "status": "success",
            "data": {"contests": contests, "queue": queue},
            "errors": snap["errors"],
            "handles": {"codeforces": cf_handle, "leetcode": lc_user},
            "fetched_at": _iso_ts(snap["at"]),
        })
    finally:
        db.close()


@upsolve_bp.route("/skip", methods=["POST"])
def skip_problem():
    data = _body()
    url = _clean_url(data.get("url"))
    if not url:
        return _err("A valid Codeforces or LeetCode problem url is required.")
    skipped = data.get("skipped", True) is not False
    db = SessionLocal()
    try:
        item = _get_item(db, url, (data.get("name") or "")[:MAX_NAME] if isinstance(data.get("name"), str) else None)
        item.skipped = skipped
        db.commit()
        return jsonify({"status": "success", "url": url, "skipped": skipped})
    finally:
        db.close()


HINT_SYSTEM = (
    "You are a competitive-programming coach helping a student upsolve a contest problem. "
    "Give ONE short, nudging hint (2-4 sentences): the key observation or the technique to consider. "
    "Never give code, pseudocode, or the full solution. Plain text, no headings."
)


@upsolve_bp.route("/hint", methods=["POST"])
def problem_hint():
    data = _body()
    url = _clean_url(data.get("url"))
    if not url:
        return _err("A valid Codeforces or LeetCode problem url is required.")
    name = data.get("name").strip()[:MAX_NAME] if isinstance(data.get("name"), str) else ""
    if not name:
        return _err("Problem name is required.")
    db = SessionLocal()
    try:
        item = db.query(UpsolveItem).filter(UpsolveItem.url == url).first()
        if item and item.hint:
            return jsonify({"status": "success", "url": url, "hint": item.hint, "cached": True})
        platform = "Codeforces" if "codeforces.com" in url else "LeetCode"
        prompt = f"Problem: {name}\nPlatform: {platform}\nLink: {url}\n\nGive one hint for this problem."
        try:
            hint = (LLMClient(budget=LLM_BUDGET).generate(prompt, temperature=0.4, system=HINT_SYSTEM, thinking="low") or "").strip()
        except Exception as e:
            return _err(f"Couldn't get a hint right now: {e}", 502)
        if not hint:
            return _err("The model returned an empty hint. Try again.", 502)
        item = _get_item(db, url, name)
        item.hint = hint[:4000]
        db.commit()
        return jsonify({"status": "success", "url": url, "hint": item.hint, "cached": False})
    finally:
        db.close()
