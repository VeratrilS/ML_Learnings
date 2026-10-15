"""
External platform integrations (LeetCode public GraphQL, Codeforces public API).
Pure functions over HTTP; no DB access here.
"""
import random
import re
import time
from datetime import datetime, timezone

import requests

_HEADERS = {"User-Agent": "Mozilla/5.0 (productivity-automations)", "Referer": "https://leetcode.com"}


# ---------------- LeetCode ----------------
def leetcode_recent_accepted(username: str, limit: int = 20) -> list:
    """Returns [{slug, title, solved_at(naive UTC)}] for the user's recent accepted submissions."""
    query = """query recentAc($username: String!, $limit: Int!) {
      recentAcSubmissionList(username: $username, limit: $limit) { titleSlug title timestamp }
    }"""
    r = requests.post("https://leetcode.com/graphql", json={"query": query, "variables": {"username": username, "limit": limit}},
                      headers=_HEADERS, timeout=15)
    r.raise_for_status()
    items = (r.json().get("data") or {}).get("recentAcSubmissionList") or []
    return [{
        "slug": i["titleSlug"],
        "title": i["title"],
        "solved_at": datetime.fromtimestamp(int(i["timestamp"]), tz=timezone.utc).replace(tzinfo=None),
    } for i in items]


def leetcode_random_unsent(exclude: set, difficulties: list = None) -> dict:
    """Fallback once the curated bank is exhausted: a random free, popular LeetCode problem not in `exclude`."""
    query = """query q($limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
      questionList(categorySlug: "algorithms", limit: $limit, skip: $skip, filters: $filters) {
        data { acRate difficulty questionFrontendId isPaidOnly title titleSlug topicTags { name } }
      }
    }"""
    for _ in range(4):
        skip = random.randint(0, 2400)
        r = requests.post("https://leetcode.com/graphql", json={"query": query, "variables": {"limit": 100, "skip": skip, "filters": {}}},
                          headers=_HEADERS, timeout=20)
        r.raise_for_status()
        rows = ((r.json().get("data") or {}).get("questionList") or {}).get("data") or []
        rows = [q for q in rows if not q["isPaidOnly"] and q["acRate"] >= 40 and q["titleSlug"] not in exclude
                and re.sub(r"[^a-z0-9]", "", q["title"].lower()) not in exclude
                and (not difficulties or q["difficulty"] in difficulties)]
        if rows:
            q = random.choice(rows)
            topic = ", ".join(t["name"] for t in q["topicTags"][:2]) or "Mixed"
            return {"title": q["title"], "slug": q["titleSlug"], "difficulty": q["difficulty"], "topic": topic,
                    "id": int(q["questionFrontendId"])}
    return None


def leetcode_profile(username: str) -> dict:
    query = """query profile($username: String!) {
      matchedUser(username: $username) {
        submitStatsGlobal { acSubmissionNum { difficulty count } }
        profile { ranking }
        userCalendar { streak totalActiveDays }
      }
      userContestRanking(username: $username) { rating attendedContestsCount globalRanking topPercentage }
      allQuestionsCount { difficulty count }
    }"""
    r = requests.post("https://leetcode.com/graphql", json={"query": query, "variables": {"username": username}},
                      headers=_HEADERS, timeout=15)
    r.raise_for_status()
    user = (r.json().get("data") or {}).get("matchedUser")
    if not user:
        raise ValueError(f"LeetCode user '{username}' not found")
    data = r.json()["data"]
    counts = {x["difficulty"]: x["count"] for x in user["submitStatsGlobal"]["acSubmissionNum"]}
    totals = {x["difficulty"]: x["count"] for x in data.get("allQuestionsCount") or []}
    contest = data.get("userContestRanking") or {}
    calendar = user.get("userCalendar") or {}
    return {"total": counts.get("All", 0), "easy": counts.get("Easy", 0), "medium": counts.get("Medium", 0),
            "hard": counts.get("Hard", 0), "ranking": (user.get("profile") or {}).get("ranking"),
            "available": {"easy": totals.get("Easy"), "medium": totals.get("Medium"), "hard": totals.get("Hard")},
            "contest_rating": round(contest["rating"]) if contest.get("rating") else None,
            "contests_attended": contest.get("attendedContestsCount"),
            "top_percentage": contest.get("topPercentage"),
            "streak": calendar.get("streak"), "active_days": calendar.get("totalActiveDays")}


# ---------------- Codeforces ----------------
_CF_CACHE = {"at": 0, "problems": []}
_CF_TTL = 6 * 3600


def _cf_get(method: str, **params):
    r = requests.get(f"https://codeforces.com/api/{method}", params=params, headers=_HEADERS, timeout=25)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK":
        raise ValueError(data.get("comment") or "Codeforces API error")
    return data["result"]


def cf_problemset() -> list:
    if time.time() - _CF_CACHE["at"] > _CF_TTL or not _CF_CACHE["problems"]:
        result = _cf_get("problemset.problems")
        solved = {(s["contestId"], s["index"]): s.get("solvedCount", 0) for s in result["problemStatistics"]}
        problems = []
        for p in result["problems"]:
            if "rating" not in p or "contestId" not in p or "*special" in p.get("tags", []):
                continue
            if p.get("rating", 0) < 1400:
                continue
            problems.append({
                "key": f"{p['contestId']}/{p['index']}",
                "contest_id": p["contestId"],
                "index": p["index"],
                "name": p["name"],
                "rating": p["rating"],
                "tags": p.get("tags", []),
                "solved_count": solved.get((p["contestId"], p["index"]), 0),
                "url": f"https://codeforces.com/problemset/problem/{p['contestId']}/{p['index']}",
            })
        _CF_CACHE.update(at=time.time(), problems=problems)
    return _CF_CACHE["problems"]


def cf_all_tags() -> list:
    tags = set()
    for p in cf_problemset():
        tags.update(p["tags"])
    return sorted(tags)


def cf_user_info(handle: str) -> dict:
    u = _cf_get("user.info", handles=handle)[0]
    return {"handle": u["handle"], "rating": u.get("rating"), "max_rating": u.get("maxRating"), "rank": u.get("rank")}


def cf_user_submissions(handle: str) -> tuple:
    """Returns (solved_keys:{key: solved_at}, attempted_keys:set)."""
    subs = _cf_get("user.status", handle=handle, **{"from": 1, "count": 10000})
    solved, attempted = {}, set()
    for s in subs:
        p = s.get("problem", {})
        if "contestId" not in p:
            continue
        key = f"{p['contestId']}/{p['index']}"
        attempted.add(key)
        if s.get("verdict") == "OK":
            at = datetime.fromtimestamp(s["creationTimeSeconds"], tz=timezone.utc).replace(tzinfo=None)
            solved[key] = min(at, solved.get(key, at))
    return solved, attempted


def cf_pick(count: int, min_rating: int, max_rating: int, tags: list, exclude: set, tag_mode: str = "any") -> list:
    pool = [p for p in cf_problemset()
            if min_rating <= p["rating"] <= max_rating and p["key"] not in exclude]
    if tags:
        want = set(tags)
        if tag_mode == "all":
            pool = [p for p in pool if want.issubset(p["tags"])]
        else:
            pool = [p for p in pool if want.intersection(p["tags"])]
    # Prefer modern, well-tested problems: newer contests and solved by enough people.
    modern = [p for p in pool if p["contest_id"] >= 1200 and p["solved_count"] >= 300]
    source = modern if len(modern) >= count else pool
    picked = random.sample(source, min(count, len(source)))
    return sorted(picked, key=lambda p: p["rating"])
