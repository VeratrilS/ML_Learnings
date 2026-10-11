"""
OA Simulator: timed online-assessment practice sets.

A set is picked deterministically from a per-attempt seed: LeetCode sets come from the curated
problem bank (never something already sent or recently solved, topics mixed and biased toward weak
topics when insights are available); Codeforces sets climb from the user's practice rating.

Finishing an attempt auto-verifies against the platform (an accepted submission inside
[started_at, started_at + duration + grace]) and merges self-reported outcomes for the rest.
"""
import json
import random
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text

from api.core.db import Base, SessionLocal, engine
from api.domain import integrations
from api.domain.problem_bank import PROBLEMS
from api.domain.repositories import NotificationRepository, normalize_title

GRACE_MIN = 5                  # submissions up to 5 min after the buzzer still count
PARTIAL_FACTOR = 0.4           # a partial solve earns 40% of the problem's points
LC_POINTS = {"Easy": 100, "Medium": 200, "Hard": 300}
CF_DEFAULT_THETA = 1200
CF_MIN, CF_MAX = 800, 3500
OUTCOMES = ("solved", "partial", "unsolved")
HISTORY_LIMIT = 30
MIN_DURATION, MAX_DURATION = 10, 240

PRESETS = {
    "lc-classic": {"platform": "leetcode", "label": "LeetCode Classic", "slots": ["Medium", "Medium", "Hard"],
                   "duration": 90, "durations": [60, 90], "blurb": "The standard 3-question OA."},
    "lc-quick": {"platform": "leetcode", "label": "Quick Screen", "slots": ["Easy", "Medium"],
                 "duration": 45, "durations": [45], "blurb": "A short screening round."},
    "cf-div2": {"platform": "codeforces", "label": "Codeforces Div. 2", "offsets": [0, 200, 400],
                "duration": 90, "durations": [90, 120], "blurb": "Three problems climbing from your rating."},
    "custom": {"platform": None, "label": "Custom", "duration": 60, "durations": [],
               "blurb": "Pick the platform, problems and time."},
}


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class OAAttempt(Base):
    __tablename__ = "oa_attempts"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(20), nullable=False)  # 'leetcode' | 'codeforces'
    preset = Column(String(30), nullable=False)
    problems = Column(Text, nullable=False)  # JSON [{id, title, slug|key, url, difficulty|rating, topic, verified?}]
    duration_min = Column(Integer, nullable=False)
    started_at = Column(DateTime, nullable=False, default=_utcnow, index=True)  # naive UTC
    ended_at = Column(DateTime, nullable=True)  # naive UTC
    results = Column(Text, nullable=True)  # JSON {problem id: 'solved'|'partial'|'unsolved'}
    auto_verified = Column(Boolean, default=False, nullable=False)
    score = Column(Integer, nullable=True)
    status = Column(String(20), default="active", nullable=False, index=True)  # active | finished | abandoned

    def __repr__(self):
        return f"<OAAttempt(id={self.id}, preset={self.preset}, status={self.status}, score={self.score})>"


oa_bp = Blueprint("oa", __name__, url_prefix="/api/oa")


@oa_bp.record_once
def _ensure_table(state):
    """Create the table when the blueprint is registered, so wiring it in needs no extra step."""
    try:
        OAAttempt.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:  # e.g. a concurrent cold start created it first
        print(f"oa_attempts table check skipped: {e}")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _loads(text, default):
    try:
        value = json.loads(text) if text else default
    except (TypeError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def _new_seed():
    return random.SystemRandom().randrange(1, 2 ** 31)


def _topic_weights(db):
    """{topic: weight} from insights (weak topics weigh more); {} when unavailable."""
    try:
        from api.domain.insights import topic_weights
    except ImportError:
        return {}
    try:
        weights = topic_weights(db)
        return weights if isinstance(weights, dict) else {}
    except Exception as e:
        db.rollback()
        print(f"oa: topic weights unavailable: {e}")
        return {}


def lc_url(slug):
    return f"https://leetcode.com/problems/{slug}/"


def problem_points(p):
    if p.get("rating"):
        return max(100, int(round(int(p["rating"]) / 5.0)))  # 1200 -> 240, 1600 -> 320, 2000 -> 400
    return LC_POINTS.get(p.get("difficulty"), 200)


def score_attempt(problems, results):
    """Returns (score, max_score). Partial earns PARTIAL_FACTOR of the problem's points."""
    score = total = 0
    for p in problems:
        pts = problem_points(p)
        total += pts
        outcome = results.get(p["id"])
        if outcome == "solved":
            score += pts
        elif outcome == "partial":
            score += int(round(pts * PARTIAL_FACTOR))
    return score, total


def cf_theta(repo):
    """Practice rating for Codeforces sets: explicit OA setting, else the fitted insights rating, else 1200."""
    for key in ("oa_cf_theta", "insights_cf_rating"):
        raw = repo.get_setting(key)
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            continue
        if CF_MIN <= value <= CF_MAX:
            return int(round(value / 100.0)) * 100
    return CF_DEFAULT_THETA


def cf_targets(theta, offsets=(0, 200, 400)):
    return [max(CF_MIN, min(CF_MAX, theta + o)) for o in offsets]


# ---------------- picking ----------------
def pick_leetcode(slots, exclude, rng, weights=None):
    """slots: ['Medium', 'Hard', ...]. Picks unseen bank problems, preferring topics not yet in the set.
    Falls back to already-seen problems only when a difficulty is exhausted."""
    weights = weights or {}
    picked, used_topics, taken = [], set(), set()

    def unseen(p):
        return p[1] not in exclude and normalize_title(p[0]) not in exclude and normalize_title(p[1]) not in exclude

    for diff in slots:
        pool = [p for p in PROBLEMS if p[2] == diff and p[1] not in taken]
        fresh = [p for p in pool if unseen(p)]
        pool = fresh or pool
        if not pool:
            continue
        new_topic = [p for p in pool if p[3] not in used_topics]
        pool = new_topic or pool
        w = [max(1e-3, float(weights.get(p[3], 0.0))) if weights else 1.0 for p in pool]
        title, slug, difficulty, topic, _ = rng.choices(pool, weights=w, k=1)[0]
        taken.add(slug)
        used_topics.add(topic)
        picked.append({"id": slug, "title": title, "slug": slug, "url": lc_url(slug),
                       "difficulty": difficulty, "topic": topic, "seen_before": not fresh})
    return picked


def pick_codeforces(targets, problemset, exclude, rng):
    """One problem per target rating, unseen, modern if possible, no two from the same contest."""
    picked, contests = [], set()
    for target in targets:
        chosen = None
        for spread in (0, 100, 200):
            pool = [p for p in problemset
                    if abs(p["rating"] - target) <= spread and p["key"] not in exclude
                    and p["contest_id"] not in contests]
            modern = [p for p in pool if p.get("contest_id", 0) >= 1200 and p.get("solved_count", 0) >= 300]
            pool = modern or pool
            if pool:
                chosen = rng.choice(sorted(pool, key=lambda p: p["key"]))
                break
        if not chosen:
            continue
        contests.add(chosen["contest_id"])
        tags = chosen.get("tags") or []
        picked.append({"id": chosen["key"], "title": chosen["name"], "key": chosen["key"], "url": chosen["url"],
                       "rating": chosen["rating"], "topic": ", ".join(tags[:2]) or "Mixed",
                       "label": f"{chosen['contest_id']}{chosen['index']}"})
    return picked


def _lc_exclude(db, repo):
    exclude = set(repo.get_sent_keys("leetcode"))
    username = repo.get_setting("leetcode_username", "Veratril")
    if username:
        try:
            for s in integrations.leetcode_recent_accepted(username, 50):
                exclude.add(s["slug"])
                exclude.add(normalize_title(s["title"]))
        except Exception as e:
            print(f"oa: LeetCode recent AC lookup failed: {e}")
    for a in db.query(OAAttempt).filter(OAAttempt.platform == "leetcode").all():
        for p in _loads(a.problems, []):
            exclude.add(p.get("id"))
    return exclude


def _cf_exclude(db, repo):
    exclude = set(repo.get_sent_keys("codeforces"))
    handle = repo.get_setting("cf_handle", "Veratril")
    if handle:
        try:
            solved, attempted = integrations.cf_user_submissions(handle)
            exclude |= set(solved) | set(attempted)
        except Exception as e:
            print(f"oa: Codeforces submissions lookup failed: {e}")
    for a in db.query(OAAttempt).filter(OAAttempt.platform == "codeforces").all():
        for p in _loads(a.problems, []):
            exclude.add(p.get("id"))
    return exclude


def _plan(preset, data, repo):
    """Returns ({platform, slots|targets, duration}, error)."""
    spec = PRESETS[preset]
    duration = data.get("duration_min", spec["duration"])
    if not isinstance(duration, int) or isinstance(duration, bool) or not MIN_DURATION <= duration <= MAX_DURATION:
        return None, f"duration_min must be between {MIN_DURATION} and {MAX_DURATION}."
    if preset == "custom":
        platform = data.get("platform")
        if platform not in ("leetcode", "codeforces"):
            return None, "platform must be 'leetcode' or 'codeforces'."
        if platform == "leetcode":
            slots = data.get("difficulties")
            if not isinstance(slots, list) or not 1 <= len(slots) <= 5 or any(s not in LC_POINTS for s in slots):
                return None, "difficulties must be 1-5 of Easy/Medium/Hard."
            return {"platform": platform, "slots": slots, "duration": duration}, None
        ratings = data.get("ratings")
        if (not isinstance(ratings, list) or not 1 <= len(ratings) <= 6
                or any(not isinstance(r, int) or isinstance(r, bool) or not CF_MIN <= r <= CF_MAX for r in ratings)):
            return None, f"ratings must be 1-6 integers between {CF_MIN} and {CF_MAX}."
        return {"platform": platform, "targets": sorted(ratings), "duration": duration}, None
    if spec["platform"] == "leetcode":
        return {"platform": "leetcode", "slots": list(spec["slots"]), "duration": duration}, None
    return {"platform": "codeforces", "targets": cf_targets(cf_theta(repo), spec["offsets"]), "duration": duration}, None


# ---------------- serialization & stats ----------------
def _serialize(a):
    problems = _loads(a.problems, [])
    results = _loads(a.results, {})
    _, max_score = score_attempt(problems, {})
    return {
        "id": a.id,
        "platform": a.platform,
        "preset": a.preset,
        "label": PRESETS.get(a.preset, {}).get("label", a.preset),
        "problems": problems,
        "duration_min": a.duration_min,
        "started_at": _iso(a.started_at),
        "ends_at": _iso(a.started_at + timedelta(minutes=a.duration_min)) if a.started_at else None,
        "ended_at": _iso(a.ended_at),
        "status": a.status,
        "results": results,
        "auto_verified": bool(a.auto_verified),
        "score": a.score,
        "max_score": max_score,
    }


def compute_stats(attempts):
    """attempts: finished/abandoned OAAttempt rows."""
    finished = [a for a in attempts if a.status == "finished"]
    total_problems = solved = 0
    by_topic, by_difficulty, pct = {}, {}, []
    for a in finished:
        problems = _loads(a.problems, [])
        results = _loads(a.results, {})
        score, max_score = score_attempt(problems, results)
        if max_score:
            pct.append(100.0 * (a.score if a.score is not None else score) / max_score)
        for p in problems:
            ok = results.get(p["id"]) == "solved"
            total_problems += 1
            solved += ok
            for bucket, key in ((by_topic, p.get("topic") or "Mixed"),
                                (by_difficulty, p.get("difficulty") or (f"{p['rating']}" if p.get("rating") else "?"))):
                row = bucket.setdefault(key, {"attempted": 0, "solved": 0})
                row["attempted"] += 1
                row["solved"] += ok
    scores = [a.score or 0 for a in finished]
    topics = sorted(({"topic": t, **v, "rate": round(v["solved"] / v["attempted"], 3)} for t, v in by_topic.items()),
                    key=lambda r: (r["rate"], -r["attempted"], r["topic"]))
    return {
        "attempts": len(finished),
        "abandoned": sum(1 for a in attempts if a.status == "abandoned"),
        "avg_score": round(sum(scores) / len(scores)) if scores else 0,
        "best_score": max(scores) if scores else 0,
        "avg_pct": round(sum(pct) / len(pct)) if pct else 0,
        "problems": total_problems,
        "solved": solved,
        "solve_rate": round(solved / total_problems, 3) if total_problems else 0.0,
        "by_topic": topics,
        "by_difficulty": by_difficulty,
    }


def _presets_payload(repo):
    theta = cf_theta(repo)
    out = []
    for key, spec in PRESETS.items():
        item = {"key": key, "label": spec["label"], "platform": spec["platform"], "duration_min": spec["duration"],
                "durations": spec["durations"], "blurb": spec["blurb"]}
        if spec.get("slots"):
            item["mix"] = list(spec["slots"])
        if spec.get("offsets"):
            item["mix"] = cf_targets(theta, spec["offsets"])
            item["theta"] = theta
        out.append(item)
    return out


def _active(db):
    return db.query(OAAttempt).filter(OAAttempt.status == "active").order_by(OAAttempt.id.desc()).first()


# ---------------- verification ----------------
def verify_window(started_at, duration_min):
    return started_at, started_at + timedelta(minutes=duration_min + GRACE_MIN)


def auto_verify(attempt, repo):
    """Returns ({problem id: solved_at}, error). Only accepted submissions inside the window count."""
    problems = _loads(attempt.problems, [])
    ids = {p["id"] for p in problems}
    lo, hi = verify_window(attempt.started_at, attempt.duration_min)
    found = {}
    try:
        if attempt.platform == "leetcode":
            username = repo.get_setting("leetcode_username", "Veratril")
            if not username:
                return {}, "Set your LeetCode username in Settings to auto-verify."
            for s in integrations.leetcode_recent_accepted(username, 20):
                at = s.get("solved_at")
                if s.get("slug") in ids and at and lo <= at <= hi:
                    found[s["slug"]] = min(at, found.get(s["slug"], at))
        else:
            handle = repo.get_setting("cf_handle", "Veratril")
            if not handle:
                return {}, "Set your Codeforces handle in Settings to auto-verify."
            solved, _ = integrations.cf_user_submissions(handle)
            for key, at in solved.items():
                if key in ids and at and lo <= at <= hi:
                    found[key] = at
    except Exception as e:
        name = "LeetCode" if attempt.platform == "leetcode" else "Codeforces"
        return found, f"Couldn't reach {name} to verify: {e}"
    return found, None


# ---------------- routes ----------------
@oa_bp.route("", methods=["GET"])
def overview():
    db = SessionLocal()
    try:
        repo = NotificationRepository(db)
        active = _active(db)
        past = (db.query(OAAttempt).filter(OAAttempt.status != "active")
                .order_by(OAAttempt.started_at.desc(), OAAttempt.id.desc()).all())
        return jsonify({
            "status": "success",
            "data": {
                "active": _serialize(active) if active else None,
                "history": [_serialize(a) for a in past[:HISTORY_LIMIT]],
                "stats": compute_stats(past),
                "presets": _presets_payload(repo),
            },
            "now": _iso(_utcnow()),
        })
    finally:
        db.close()


@oa_bp.route("/start", methods=["POST"])
def start():
    data = _body()
    preset = data.get("preset")
    if preset not in PRESETS:
        return _err(f"preset must be one of: {', '.join(PRESETS)}.")
    db = SessionLocal()
    try:
        active = _active(db)
        if active:
            return jsonify({"status": "success", "data": _serialize(active), "resumed": True, "now": _iso(_utcnow())})
        repo = NotificationRepository(db)
        plan, error = _plan(preset, data, repo)
        if error:
            return _err(error)
        rng = random.Random(_new_seed())
        if plan["platform"] == "leetcode":
            problems = pick_leetcode(plan["slots"], _lc_exclude(db, repo), rng, _topic_weights(db))
            wanted = len(plan["slots"])
        else:
            try:
                problemset = integrations.cf_problemset()
            except Exception as e:
                return _err(f"Couldn't load the Codeforces problemset: {e}", 502)
            problems = pick_codeforces(plan["targets"], problemset, _cf_exclude(db, repo), rng)
            wanted = len(plan["targets"])
        if len(problems) < wanted:
            return _err("Not enough unseen problems for this set. Try another preset.", 404)
        a = OAAttempt(platform=plan["platform"], preset=preset, problems=json.dumps(problems),
                      duration_min=plan["duration"], started_at=_utcnow(), status="active", auto_verified=False)
        db.add(a)
        db.commit()
        db.refresh(a)
        return jsonify({"status": "success", "data": _serialize(a), "resumed": False, "now": _iso(_utcnow())})
    finally:
        db.close()


@oa_bp.route("/<int:attempt_id>/finish", methods=["POST"])
def finish(attempt_id):
    reported = _body().get("results") or {}
    if not isinstance(reported, dict):
        return _err("results must be an object of {problem id: solved|partial|unsolved}.")
    db = SessionLocal()
    try:
        a = db.get(OAAttempt, attempt_id)
        if not a:
            return _err("Not found", 404)
        if a.status != "active":
            return _err("This attempt is already over.", 409)
        repo = NotificationRepository(db)
        problems = _loads(a.problems, [])
        verified, verify_error = auto_verify(a, repo)
        results = {}
        for p in problems:
            pid = p["id"]
            if pid in verified:
                results[pid] = "solved"
                p["verified"] = True
                p["solved_in_min"] = max(0, int((verified[pid] - a.started_at).total_seconds() // 60))
            else:
                outcome = reported.get(pid)
                results[pid] = outcome if outcome in OUTCOMES else "unsolved"
                p["verified"] = False
        score, max_score = score_attempt(problems, results)
        a.problems = json.dumps(problems)
        a.results = json.dumps(results)
        a.auto_verified = bool(verified)
        a.score = score
        a.status = "finished"
        a.ended_at = _utcnow()
        db.commit()
        db.refresh(a)
        return jsonify({"status": "success", "data": _serialize(a), "verified": sorted(verified),
                        "verify_error": verify_error, "max_score": max_score})
    finally:
        db.close()


@oa_bp.route("/<int:attempt_id>/abandon", methods=["POST"])
def abandon(attempt_id):
    db = SessionLocal()
    try:
        a = db.get(OAAttempt, attempt_id)
        if not a:
            return _err("Not found", 404)
        if a.status != "active":
            return _err("This attempt is already over.", 409)
        a.status = "abandoned"
        a.ended_at = _utcnow()
        a.score = 0
        db.commit()
        db.refresh(a)
        return jsonify({"status": "success", "data": _serialize(a)})
    finally:
        db.close()
