"""
Upcoming programming contests (LeetCode + Codeforces).

GET /api/contests -> {status, data: [contest...], errors: [str...]}
Each contest: {platform, name, start (ISO UTC), duration_seconds, url, register_url, running}
Only contests that haven't ended and start within the next 30 days, sorted by start.
Both platforms are fetched in parallel and cached in-process for 30 minutes.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from flask import Blueprint, jsonify, request

contests_bp = Blueprint("contests", __name__, url_prefix="/api/contests")

TIMEOUT = 10
CACHE_TTL = 30 * 60
PARTIAL_TTL = 2 * 60  # retry sooner when one platform failed
WINDOW_SECONDS = 30 * 86400

_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://leetcode.com", "Content-Type": "application/json"}
# upcomingContests sometimes lists only the next weekly; topTwoContests adds the biweekly. Merge both by slug.
_LC_QUERY = ("{ upcomingContests { title titleSlug startTime duration } "
             "topTwoContests { title titleSlug startTime duration } }")

_cache = {"at": 0.0, "ttl": CACHE_TTL, "payload": None}
_lock = threading.Lock()


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _contest(platform, name, start_ts, duration, url, register_url):
    return {"platform": platform, "name": name, "start_ts": int(start_ts), "duration_seconds": int(duration),
            "url": url, "register_url": register_url}


def fetch_codeforces() -> list:
    r = requests.get("https://codeforces.com/api/contest.list", params={"gym": "false"},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=TIMEOUT)
    r.raise_for_status()
    body = r.json()
    if body.get("status") != "OK":
        raise ValueError(body.get("comment") or "Codeforces API error")
    out = []
    for c in body.get("result") or []:
        if c.get("phase") not in ("BEFORE", "CODING") or c.get("startTimeSeconds") is None:
            continue
        cid = c["id"]
        out.append(_contest("codeforces", c["name"], c["startTimeSeconds"], c.get("durationSeconds") or 0,
                            f"https://codeforces.com/contests/{cid}",
                            f"https://codeforces.com/contestRegistration/{cid}"))
    return out


def fetch_leetcode() -> list:
    r = requests.post("https://leetcode.com/graphql", json={"query": _LC_QUERY}, headers=_HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json().get("data") or {}
    seen, out = set(), []
    for c in (data.get("upcomingContests") or []) + (data.get("topTwoContests") or []):
        slug = c.get("titleSlug")
        if not slug or slug in seen or c.get("startTime") is None:
            continue
        seen.add(slug)
        url = f"https://leetcode.com/contest/{slug}/"
        out.append(_contest("leetcode", c["title"], c["startTime"], c.get("duration") or 0, url, url))
    if not out and not data:
        raise ValueError("LeetCode returned no contest data")
    return out


_FETCHERS = {"leetcode": ("LeetCode", fetch_leetcode), "codeforces": ("Codeforces", fetch_codeforces)}


def _collect() -> dict:
    contests, errors = [], []
    with ThreadPoolExecutor(max_workers=len(_FETCHERS)) as pool:
        futures = {key: pool.submit(fn) for key, (_, fn) in _FETCHERS.items()}
        for key, fut in futures.items():
            label = _FETCHERS[key][0]
            try:
                contests.extend(fut.result())
            except Exception as e:  # one platform failing must not hide the other
                errors.append(f"{label} contests unavailable ({type(e).__name__})")
    return {"contests": contests, "errors": errors}


def _present(raw: dict, now: float) -> dict:
    """Filter (not ended, starts within window) + sort. Applied on every request so cached data never goes stale."""
    data = []
    for c in raw["contests"]:
        start, end = c["start_ts"], c["start_ts"] + c["duration_seconds"]
        if end <= now or start > now + WINDOW_SECONDS:
            continue
        item = {k: v for k, v in c.items() if k != "start_ts"}
        item["start"] = _iso(start)
        item["running"] = start <= now < end
        data.append((start, item))
    data.sort(key=lambda x: (x[0], x[1]["platform"], x[1]["name"]))
    return {"status": "success", "data": [d for _, d in data], "errors": list(raw["errors"])}


def get_contests(force: bool = False, now: float = None) -> dict:
    now = time.time() if now is None else now
    with _lock:
        fresh = _cache["payload"] is not None and now - _cache["at"] < _cache["ttl"]
        if force or not fresh:
            raw = _collect()
            if raw["contests"] or not raw["errors"]:
                _cache.update(at=now, ttl=PARTIAL_TTL if raw["errors"] else CACHE_TTL, payload=raw)
            else:  # everything failed: don't cache, retry on the next request
                _cache.update(at=0.0, ttl=CACHE_TTL, payload=None)
        else:
            raw = _cache["payload"]
    return _present(raw, now)


def clear_cache():
    with _lock:
        _cache.update(at=0.0, ttl=CACHE_TTL, payload=None)


@contests_bp.route("", methods=["GET"], strict_slashes=False)
def list_contests():
    force = request.args.get("refresh") in ("1", "true")
    return jsonify(get_contests(force=force))
