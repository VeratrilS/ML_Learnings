"""
Public stats: live competitive-programming numbers for the public portfolio page.

This is the one endpoint meant for anonymous visitors, so it never needs the passcode
(it is listed in app._OPEN_ENDPOINTS). Visitors can't make us hammer LeetCode/Codeforces:
results are cached in-process for 6 hours and there is no way to bust the cache from outside.

Endpoints:
  GET /api/public/stats   -> {leetcode: {<handle>: {...} | null}, codeforces: {...} | null, fetched_at}
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from flask import Blueprint, jsonify

from api.domain.integrations import _HEADERS

LEETCODE_HANDLES = ("Sairaghava1318", "Veratril")
CF_HANDLE = "Raghavan_CP"

CACHE_TTL = 6 * 3600      # serve cached numbers for 6 hours
RETRY_AFTER = 10 * 60     # when every source fails, don't retry upstream more often than this
TIMEOUT = 8               # per-request timeout (sources are fetched in parallel, so this bounds latency)
BROWSER_MAX_AGE = 3600

_CACHE = {"at": 0.0, "data": None, "failed_at": 0.0}
_LOCK = threading.Lock()


def _now():
    """Wall clock in seconds; tests monkeypatch this to move across the TTL."""
    return time.time()


# ---------------- fetchers ----------------
_LC_QUERY = """query publicProfile($username: String!) {
  matchedUser(username: $username) {
    submitStatsGlobal { acSubmissionNum { difficulty count } }
    badges { id }
  }
  userContestRanking(username: $username) { rating attendedContestsCount topPercentage }
}"""


def fetch_leetcode(username: str) -> dict:
    r = requests.post("https://leetcode.com/graphql", json={"query": _LC_QUERY, "variables": {"username": username}},
                      headers=_HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json().get("data") or {}
    user = data.get("matchedUser")
    if not user:
        raise ValueError(f"LeetCode user '{username}' not found")
    counts = {x["difficulty"]: x["count"] for x in (user.get("submitStatsGlobal") or {}).get("acSubmissionNum") or []}
    contest = data.get("userContestRanking") or {}
    badges = user.get("badges")
    return {"total": counts.get("All", 0), "easy": counts.get("Easy", 0), "medium": counts.get("Medium", 0),
            "hard": counts.get("Hard", 0),
            "contest_rating": round(contest["rating"]) if contest.get("rating") else None,
            "contests_attended": contest.get("attendedContestsCount"),
            "top_percentage": contest.get("topPercentage"),
            "badges": len(badges) if isinstance(badges, list) else None}


def fetch_codeforces(handle: str) -> dict:
    r = requests.get("https://codeforces.com/api/user.info", params={"handles": handle}, headers=_HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    body = r.json()
    if body.get("status") != "OK":
        raise ValueError(body.get("comment") or "Codeforces API error")
    u = body["result"][0]
    return {"handle": u["handle"], "rating": u.get("rating"), "max_rating": u.get("maxRating"),
            "rank": u.get("rank"), "max_rank": u.get("maxRank")}


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception as e:  # any one source failing just nulls that entry
        print(f"public stats: {fn.__name__}{args} failed: {e}")
        return None


def _fetch_all() -> dict:
    """Uncached: fetch every source in parallel; a failed source is None."""
    with ThreadPoolExecutor(max_workers=len(LEETCODE_HANDLES) + 1) as pool:
        lc = {h: pool.submit(_safe, fetch_leetcode, h) for h in LEETCODE_HANDLES}
        cf = pool.submit(_safe, fetch_codeforces, CF_HANDLE)
        return {"leetcode": {h: f.result() for h, f in lc.items()},
                "codeforces": cf.result(),
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")}


def _empty() -> dict:
    return {"leetcode": {h: None for h in LEETCODE_HANDLES}, "codeforces": None, "fetched_at": None}


def _all_failed(data) -> bool:
    return data["codeforces"] is None and all(v is None for v in data["leetcode"].values())


def get_stats() -> dict:
    """Cached stats. Within the TTL nothing is fetched; after it, a failed source keeps its last good value,
    and if every source fails the stale cache is served (and upstream isn't retried for RETRY_AFTER)."""
    with _LOCK:
        now = _now()
        cached = _CACHE["data"]
        if cached is not None and now - _CACHE["at"] < CACHE_TTL:
            return cached
        if now - _CACHE["failed_at"] < RETRY_AFTER:
            return cached if cached is not None else _empty()
        fresh = _fetch_all()
        if _all_failed(fresh):
            _CACHE["failed_at"] = now
            return cached if cached is not None else fresh
        if cached is not None:  # keep the last good value for any source that failed this time
            for h, v in fresh["leetcode"].items():
                if v is None:
                    fresh["leetcode"][h] = cached["leetcode"].get(h)
            if fresh["codeforces"] is None:
                fresh["codeforces"] = cached["codeforces"]
        _CACHE.update(at=now, data=fresh, failed_at=0.0)
        return fresh


public_stats_bp = Blueprint("public_stats", __name__, url_prefix="/api/public")


# ---------------- routes ----------------
@public_stats_bp.route("/stats", methods=["GET"])
def public_stats():
    # Deliberately ignores query params (e.g. ?refresh=1): public callers can't bust the cache.
    res = jsonify({"status": "success", "data": get_stats()})
    res.headers["Cache-Control"] = f"public, max-age={BROWSER_MAX_AGE}"
    return res
