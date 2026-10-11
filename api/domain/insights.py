"""
Insights engine: small, explainable models over data the app already stores.

  /api/insights/study    exam readiness (forgetting curve), EDF hour allocator, Monte Carlo finish forecast
  /api/insights/skills   LeetCode per-topic Elo, anchored on the contest rating
  /api/insights/cf       Codeforces practice rating by MLE (logistic / Elo curve) with per-tag shrinkage
  /api/insights/summary  compact numbers for the dashboard card (no slow network calls)

Pure Python only (runs on Vercel serverless). All maths lives in small pure functions that take
plain values, so it is unit-testable without a database; the DB/HTTP glue sits at the bottom.
Randomness (Monte Carlo, Thompson sampling) is seeded with the date, so a page reload is stable.
"""
import math
import random
import time
from bisect import bisect_left
from datetime import date, datetime, timedelta, timezone
from itertools import accumulate

from flask import Blueprint, jsonify
from sqlalchemy.orm import selectinload

from api.core.config import now_ist, to_ist
from api.core.db import Base, SessionLocal, engine
from api.domain import integrations
from api.domain.models import NotificationLog
from api.domain.problem_bank import PROBLEMS
from api.domain.repositories import NotificationRepository
from api.domain.syllabus import Subject, SyllabusTopic, short_name

insights_bp = Blueprint("insights", __name__, url_prefix="/api/insights")

# ---------------- constants ----------------
STABILITY_DAYS = {1: 2.0, 2: 6.0, 3: 15.0}   # memory half-life-ish per confidence level
DONE_BOOST = 1.5                              # a finished topic is remembered longer
DONE_SHAKY_WORK = 0.3                         # hours of revision for a done-but-shaky topic
DEFAULT_STUDY_HOURS = 3.0
DSA_FLOOR_HOURS = 0.5
HISTORY_DAYS = 21
MIN_HISTORY_DAYS = 5
PRIOR_THROUGHPUT = 1.5                        # topics/day when there is no history yet
MC_SIMS = 2000
MC_HORIZON = 180

LC_DIFFICULTY = {"Easy": 1300, "Medium": 1650, "Hard": 2000}
LC_FALLBACK_RATING = 1500
LC_CONTEST_OFFSET = 50                        # practice rating ~ contest rating - 50
ELO_PRIOR_SIGMA = 150.0                       # topic offsets rarely exceed +-150 rating points
ELO_OBS_SIGMA = 200.0                         # rating noise of a single solve/fail
ELO_N0 = (ELO_OBS_SIGMA / ELO_PRIOR_SIGMA) ** 2  # pseudo-observations held by the prior
ELO_CLAMP = 450.0

CF_PRIOR_MU = 1200.0
CF_PRIOR_SIGMA = 300.0
CF_TAG_SIGMA = 150.0
LOGIT_C = math.log(10) / 400.0                # 10^(x/400) == e^(C*x)

LC_RATING_SETTING = "insights_lc_rating"      # last known LeetCode contest rating (internal)
CF_RATING_SETTING = "insights_cf_rating"      # last fitted CF practice rating (internal)
CACHE_TTL = 3600

_LC_CACHE = {}  # username -> (fetched_at, contest_rating | None)
_CF_CACHE = {}  # handle -> (fetched_at, result dict)

# Problem-bank topic sizes double as "how much interviews care" weights
_BANK_COUNTS = {}
for _p in PROBLEMS:
    _BANK_COUNTS[_p[3]] = _BANK_COUNTS.get(_p[3], 0) + 1
_BANK_MAX = max(_BANK_COUNTS.values()) if _BANK_COUNTS else 1


# =====================================================================
# Pure functions: forgetting curve + work model
# =====================================================================
def stability(confidence, done=False):
    """Memory stability S in days for a confidence level (1..3); None when unknown."""
    s = STABILITY_DAYS.get(confidence)
    if s is None:
        return None
    return s * (DONE_BOOST if done else 1.0)


def recall(dt_days, s):
    """FSRS-style power forgetting curve: R = (1 + dt / (9 S))^-1. Returns 0 when S is unknown."""
    if not s or s <= 0:
        return 0.0
    return 1.0 / (1.0 + max(0.0, float(dt_days)) / (9.0 * s))


def effective_confidence(confidence, done):
    """Unrated topics: a finished one counts as 'okay' (2), a studied-but-pending one as 'shaky' (1)."""
    if confidence in STABILITY_DAYS:
        return confidence
    return 2 if done else 1


def topic_recall(confidence, done, studied_on, on_day):
    """Recall probability of one topic on `on_day`. Never studied (no date) -> 0."""
    if studied_on is None or on_day is None:
        return 0.0
    return recall((on_day - studied_on).days, stability(effective_confidence(confidence, done), done))


def topic_work(confidence, done):
    """Hours of work left on a topic: (4 - conf) / 3 if pending, a short revision if done but shaky."""
    if done:
        return DONE_SHAKY_WORK if confidence == 1 else 0.0
    return (4 - (confidence or 1)) / 3.0


def avail_days(days_left):
    """Study days before an exam (the day before is kept as buffer); always at least one."""
    return max(1, (days_left or 0) - 1)


# =====================================================================
# Pure functions: allocator
# =====================================================================
def edf_feasibility(items, hours_per_day):
    """Earliest-deadline-first check. items: [(days_left, work_hours)].
    Feasible iff for every k: sum_{i<=k} W_i <= H * avail_days(d_k). Returns (feasible, shortfall_hours)."""
    cum, short = 0.0, 0.0
    for d, w in sorted(items, key=lambda x: x[0]):
        cum += w
        short = max(short, cum - hours_per_day * avail_days(d))
    short = round(short, 1)
    return short <= 0, max(0.0, short)


def dsa_hours(nearest_days, total_hours, floor=DSA_FLOOR_HOURS):
    """Daily DSA floor, tapered to zero as the nearest exam gets within 3 days."""
    base = min(floor, total_hours / 2.0)
    if nearest_days is None or nearest_days > 3:
        return round(base, 2)
    return round(base * max(0, nearest_days) / 4.0, 2)


def split_hours(items, total):
    """Water-filling split. items: [(key, rate, cap)]; hours proportional to rate, never above cap.
    Returns {key: hours}; whatever cannot be placed is simply left over."""
    out = {k: 0.0 for k, _, _ in items}
    active = [(k, r, c) for k, r, c in items if r > 0 and c > 0]
    left = float(total)
    while active and left > 1e-9:
        rsum = sum(r for _, r, _ in active)
        capped = [(k, r, c) for k, r, c in active if left * r / rsum >= c]
        if not capped:
            for k, r, _ in active:
                out[k] = left * r / rsum
            break
        for k, _, c in capped:
            out[k] = c
            left -= c
        keys = {k for k, _, _ in capped}
        active = [x for x in active if x[0] not in keys]
    return out


def round_minutes(m, step=5):
    return int(step * round(m / step))


def pick_study_next(candidates, minutes_budget=None, limit=5):
    """Greedy by marginal gain. candidates: [{topic_id, title, unit, gain, minutes, position}].
    With a budget, topics are added until it is used up (the last one may be trimmed)."""
    ordered = sorted(candidates, key=lambda c: (-c["gain"], c.get("position", 0), c["topic_id"]))
    out, used = [], 0
    for c in ordered:
        if len(out) >= limit:
            break
        m = c["minutes"]
        if minutes_budget is not None:
            room = minutes_budget - used
            if room < 10:
                break
            m = min(m, room)
        m = max(10, round_minutes(m))
        out.append({"topic_id": c["topic_id"], "title": c["title"], "unit": c.get("unit"), "minutes": m})
        used += m
    return out


# =====================================================================
# Pure functions: Monte Carlo burn-down
# =====================================================================
def poisson_sample(rng, lam):
    """Knuth's algorithm; fine for small lambda."""
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def throughput_samples(done_dates, today, start, days=HISTORY_DAYS):
    """Topics finished per day (zeros included) from max(start, today-days+1) to today."""
    first = max(today - timedelta(days=days - 1), start or today)
    n = (today - first).days + 1
    counts = [0] * max(0, n)
    for d in done_dates:
        if d is not None and first <= d <= today:
            counts[(d - first).days] += 1
    return counts


def monte_carlo_finish(remaining, samples, days_left, seed, sims=MC_SIMS, horizon=MC_HORIZON,
                       prior_lambda=PRIOR_THROUGHPUT):
    """Resample daily throughput until `remaining` topics are done.
    Day offset 0 = finished by the end of today. 'On time' = finished before exam day.
    Returns {p_finish, p50_days, p90_days, prior}. Days are None when beyond the horizon."""
    if remaining <= 0:
        return {"p_finish": 1.0 if days_left is not None else None, "p50_days": 0, "p90_days": 0, "prior": False}
    rng = random.Random(seed)
    prior = len(samples) < MIN_HISTORY_DAYS
    if prior:
        samples = [poisson_sample(rng, prior_lambda) for _ in range(500)]
    if not samples or max(samples) <= 0:
        return {"p_finish": 0.0 if days_left is not None else None, "p50_days": None, "p90_days": None,
                "prior": prior}
    # Speed: bootstrap whole weeks once (each a running total of 7 resampled days), then each
    # simulation strings random weeks together and only looks inside the week where it crosses.
    weeks = [list(accumulate(rng.choices(samples, k=7))) for _ in range(1500)]
    n_weeks = len(weeks)
    finishes = []
    for _ in range(sims):
        total, day, finish = 0, 0, None
        while day < horizon:
            cum = weeks[int(rng.random() * n_weeks)]
            if total + cum[-1] >= remaining:
                d = day + bisect_left(cum, remaining - total)
                finish = d if d < horizon else None
                break
            total += cum[-1]
            day += 7
        finishes.append(finish)
    on_time = None
    if days_left is not None:
        on_time = sum(1 for f in finishes if f is not None and f < days_left) / sims
    ranked = sorted(finishes, key=lambda f: math.inf if f is None else f)
    return {"p_finish": on_time, "p50_days": ranked[int(0.5 * sims)], "p90_days": ranked[min(sims - 1, int(0.9 * sims))],
            "prior": prior}


def burndown_series(total, done_dates, today, days=HISTORY_DAYS):
    """Remaining topics at the end of each of the last `days` days. Done with no date = done before."""
    out = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        done = sum(1 for x in done_dates if x is None or x <= d)
        out.append({"date": d.isoformat(), "remaining": total - done})
    return out


# =====================================================================
# Pure functions: Elo / logistic rating models
# =====================================================================
def p_solve(theta, b):
    """Elo expected score: P = 1 / (1 + 10^((b - theta) / 400))."""
    x = (b - theta) / 400.0
    if x > 30:
        return 0.0
    return 1.0 / (1.0 + 10.0 ** x)


def shrink(delta, n, n0=ELO_N0):
    """Shrink a topic offset toward 0: normal prior N(0, 150^2) vs per-solve noise -> n / (n + n0)."""
    return delta * n / (n + n0) if n > 0 else 0.0


def elo_step(theta, b, y, n):
    """One Elo update with a decaying K = 40 / sqrt(n + 1). Positive when you beat expectation."""
    return 40.0 / math.sqrt(n + 1) * (y - p_solve(theta, b))


def lc_outcome(sent_at, completed_at, is_completed, now, hard_review=False):
    """Score for one sent problem: 1 solved within 2 days, 0.5 solved later, 0 if unsolved after 3 days,
    0.3 if a later review was marked hard. None while it is still fresh and unsolved."""
    if is_completed:
        if hard_review:
            return 0.3
        if completed_at is None or sent_at is None or completed_at - sent_at <= timedelta(days=2):
            return 1.0
        return 0.5
    if sent_at is not None and now - sent_at > timedelta(days=3):
        return 0.0
    return None


def topic_elo(events, theta_global):
    """events: chronological [(topic, b, y)]. Returns {topic: {"delta", "delta_raw", "n"}}."""
    state = {}
    for topic, b, y in events:
        st = state.setdefault(topic, {"delta_raw": 0.0, "n": 0})
        theta = theta_global + shrink(st["delta_raw"], st["n"])
        st["delta_raw"] = max(-ELO_CLAMP, min(ELO_CLAMP, st["delta_raw"] + elo_step(theta, b, y, st["n"])))
        st["n"] += 1
    for st in state.values():
        st["delta"] = shrink(st["delta_raw"], st["n"])
    return state


def topic_freq_weight(topic):
    """sqrt of the topic's share of the problem bank (max = 1); unknown topics get 0.5."""
    c = _BANK_COUNTS.get(topic)
    return math.sqrt(c / _BANK_MAX) if c else 0.5


def fit_rating(obs, prior_mu=CF_PRIOR_MU, prior_sigma=CF_PRIOR_SIGMA, steps=10):
    """MAP rating from [(problem_rating, y in [0, 1])] under P = 1/(1+10^((r-theta)/400)) and a
    normal prior. ~10 Newton steps on a concave log-posterior; no data -> prior_mu."""
    theta = float(prior_mu)
    inv_var = 1.0 / (prior_sigma ** 2)
    for _ in range(steps):
        grad = -(theta - prior_mu) * inv_var
        hess = -inv_var
        for r, y in obs:
            p = p_solve(theta, r)
            grad += LOGIT_C * (y - p)
            hess -= LOGIT_C * LOGIT_C * p * (1.0 - p)
        step = max(-400.0, min(400.0, grad / hess))
        theta -= step
        if abs(step) < 1e-3:
            break
    return theta


def round100(x):
    return int(round(x / 100.0)) * 100


def cf_suggested_range(theta):
    lo = max(800, min(3500, round100(theta - 50)))
    hi = max(800, min(3500, round100(theta + 150)))
    if hi <= lo:
        hi = min(3500, lo + 100)
    return lo, hi


# =====================================================================
# DB glue
# =====================================================================
@insights_bp.record_once
def _ensure_tables(state):
    try:
        Base.metadata.create_all(bind=engine, tables=[Subject.__table__, SyllabusTopic.__table__])
    except Exception as e:  # e.g. a concurrent cold start created them first
        print(f"insights table check skipped: {e}")


def _today():
    return now_ist().date()


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ist_date(dt):
    return to_ist(dt).date() if dt else None


def _float_setting(repo, key, default, lo, hi):
    try:
        v = float(repo.get_setting(key, str(default)))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v)) if math.isfinite(v) else default


# ---------------- study ----------------
def _subject_order(s, today):
    d = (s.exam_date - today).days if s.exam_date else None
    bucket = 0 if d is not None and d >= 0 else 1 if d is None else 2
    return (bucket, s.exam_date or date.max, s.position or 0, s.id)


def compute_study(db, today=None):
    today = today or _today()
    repo = NotificationRepository(db)
    hours = _float_setting(repo, "daily_study_hours", DEFAULT_STUDY_HOURS, 0.5, 16.0)
    subjects = db.query(Subject).options(selectinload(Subject.topics)).all()
    theory = sorted([s for s in subjects if (s.kind or "theory") == "theory" and s.topics],
                    key=lambda s: _subject_order(s, today))
    plan = {"hours": hours, "dsa_hours": DSA_FLOOR_HOURS, "study_hours": 0.0, "free_hours": 0.0,
            "feasible": True, "shortfall_hours": 0.0}
    if not theory:
        return {"subjects": [], "plan": plan,
                "empty_reason": "Paste your syllabus into the Study page (and add exam dates) to get readiness and a daily plan."}

    rows = []
    for s in theory:
        d = (s.exam_date - today).days if s.exam_date else None
        topics = list(s.topics)
        r_now, r_exam, work, cands, done_dates = [], [], 0.0, [], []
        for t in topics:
            studied_on = max([x for x in (_ist_date(t.last_studied_at), _ist_date(t.done_at)) if x] or [None],
                             key=lambda x: x or date.min)
            r_now.append(topic_recall(t.confidence, t.done, studied_on, today))
            if s.exam_date:
                r_exam.append(topic_recall(t.confidence, t.done, studied_on, s.exam_date))
            w = topic_work(t.confidence, t.done)
            work += w
            if t.done:
                done_dates.append(_ist_date(t.done_at))
            if w > 0:
                forget = 1.0 - topic_recall(t.confidence, t.done, studied_on, s.exam_date or today) \
                    if studied_on else 1.0
                gain = (DONE_SHAKY_WORK * 3 if t.done else 4 - (t.confidence or 1)) * max(0.05, forget)
                cands.append({"topic_id": t.id, "title": t.title, "unit": t.unit, "gain": gain,
                              "minutes": w * 60, "position": t.position or 0})
        pending = sum(1 for t in topics if not t.done)
        rows.append({"s": s, "d": d, "work": work, "cands": cands, "pending": pending, "done_dates": done_dates,
                     "total": len(topics),
                     "readiness_now": sum(r_now) / len(r_now),
                     "readiness_exam": (sum(r_exam) / len(r_exam)) if s.exam_date else None})

    upcoming = [r for r in rows if r["d"] is not None and r["d"] >= 0]
    nearest = min((r["d"] for r in upcoming), default=None)
    dsa = dsa_hours(nearest, hours)
    study_h = max(0.0, hours - dsa)
    split = split_hours([(r["s"].id, r["work"] / avail_days(r["d"]), r["work"]) for r in upcoming], study_h)
    feasible, shortfall = edf_feasibility([(r["d"], r["work"]) for r in upcoming], study_h)
    used = sum(split.values())
    plan.update(dsa_hours=dsa, study_hours=round(used, 2), free_hours=round(max(0.0, study_h - used), 2),
                feasible=feasible, shortfall_hours=shortfall)

    out = []
    for r in rows:
        s, d = r["s"], r["d"]
        h = split.get(s.id, 0.0)
        is_up = d is not None and d >= 0
        created = _ist_date(s.created_at) or (today - timedelta(days=HISTORY_DAYS - 1))
        samples = throughput_samples(r["done_dates"], today, created)
        mc = monte_carlo_finish(r["pending"], samples, d if is_up else None, seed=f"{today.isoformat()}:{s.id}")
        study_next = pick_study_next(r["cands"], h * 60 if is_up else None, limit=5 if is_up else 3)
        out.append({
            "id": s.id, "name": s.name, "short": short_name(s.name), "code": s.code, "color": s.color,
            "exam_date": s.exam_date.isoformat() if s.exam_date else None, "days_left": d,
            "total": r["total"], "pending": r["pending"],
            "readiness_now": round(r["readiness_now"], 3),
            "readiness_exam": round(r["readiness_exam"], 3) if r["readiness_exam"] is not None else None,
            "remaining_work": round(r["work"], 2),
            "hours_today": round(h, 2),
            "study_next": study_next,
            "p_finish": round(mc["p_finish"], 3) if mc["p_finish"] is not None else None,
            "p50_date": (today + timedelta(days=mc["p50_days"])).isoformat() if mc["p50_days"] is not None else None,
            "p90_date": (today + timedelta(days=mc["p90_days"])).isoformat() if mc["p90_days"] is not None else None,
            "throughput_prior": mc["prior"],
            "burndown": burndown_series(r["total"], r["done_dates"], today),
        })
    result = {"subjects": out, "plan": plan, "today": today.isoformat()}
    if not upcoming:
        result["empty_reason"] = "Add upcoming exam dates on the Study page to get a daily split and finish forecast."
    return result


# ---------------- LeetCode skills ----------------
def _lc_theta(repo, allow_network):
    """(theta_global, contest_rating | None, source). Network only when allowed; cached for an hour."""
    username = repo.get_setting("leetcode_username", "Veratril") or ""
    rating = None
    hit = _LC_CACHE.get(username)
    if hit and time.time() - hit[0] < CACHE_TTL:
        rating, source = hit[1], "cache"
    elif allow_network and username:
        try:
            rating = integrations.leetcode_profile(username).get("contest_rating")
            _LC_CACHE[username] = (time.time(), rating)
            source = "live"
            if rating:
                repo.set_setting(LC_RATING_SETTING, str(int(rating)))
        except Exception as e:
            print(f"insights: leetcode profile failed: {e}")
            source = "error"
    else:
        source = "stored"
    if not rating:
        try:
            rating = int(float(repo.get_setting(LC_RATING_SETTING) or 0)) or None
        except ValueError:
            rating = None
    theta = (rating - LC_CONTEST_OFFSET) if rating else LC_FALLBACK_RATING
    return float(theta), rating, source if rating else "fallback"


def _lc_events(db, now):
    logs = db.query(NotificationLog).filter(NotificationLog.task_type == "leetcode",
                                            NotificationLog.status == "success").all()
    logs.sort(key=lambda l: (l.completed_at or l.timestamp or datetime.min) if l.is_completed
              else (l.timestamp or datetime.min))
    events = []
    for l in logs:
        hard = bool(l.is_completed and l.review_stage == 0 and l.next_review_at and l.completed_at
                    and l.next_review_at - l.completed_at > timedelta(days=1, hours=1))
        y = lc_outcome(l.timestamp, l.completed_at, bool(l.is_completed), now, hard)
        if y is None:
            continue
        b = LC_DIFFICULTY.get((l.difficulty or "").title(), LC_DIFFICULTY["Medium"])
        for topic in [x.strip() for x in (l.topic or "Mixed").split(",") if x.strip()][:2]:
            events.append((topic, b, y))
    return events


def compute_skills(db, allow_network=False, today=None):
    repo = NotificationRepository(db)
    theta_g, contest, source = _lc_theta(repo, allow_network)
    state = topic_elo(_lc_events(db, _utcnow()), theta_g)
    names = list(_BANK_COUNTS) + [t for t in state if t not in _BANK_COUNTS]
    topics = []
    for name in names:
        st = state.get(name, {"delta": 0.0, "n": 0})
        theta = theta_g + st["delta"]
        topics.append({"topic": name, "rating": round(theta), "delta": round(st["delta"], 1), "n": st["n"],
                       "p_solve_medium": round(p_solve(theta, LC_DIFFICULTY["Medium"]), 3),
                       "p_solve_hard": round(p_solve(theta, LC_DIFFICULTY["Hard"]), 3),
                       "freq": round(topic_freq_weight(name), 3)})
    topics.sort(key=lambda t: (t["rating"], -t["n"], t["topic"]))

    # Thompson-like pick: sample each offset from its posterior, score (1 - P(medium)) * frequency
    rng = random.Random(f"skills:{(today or _today()).isoformat()}")
    best, best_score = None, -1.0
    for t in topics:
        sd = ELO_PRIOR_SIGMA / math.sqrt(1.0 + t["n"] / ELO_N0)
        theta = theta_g + t["delta"] + rng.gauss(0.0, sd)
        score = (1.0 - p_solve(theta, LC_DIFFICULTY["Medium"])) * t["freq"]
        if score > best_score:
            best, best_score = t, score
    tracked = [t for t in topics if t["n"] > 0]
    return {"global_rating": round(theta_g), "contest_rating": contest, "rating_source": source,
            "n_events": sum(t["n"] for t in topics), "topics": topics,
            "weakest": (tracked or topics)[0]["topic"] if topics else None,
            "recommended_topic": best["topic"] if best else None,
            "recommended": {"topic": best["topic"], "p_solve_medium": best["p_solve_medium"],
                            "rating": best["rating"]} if best else None}


def topic_weights(db) -> dict:
    """{topic: weight} summing to 1 for the problem picker: (1 - P(solve medium)) * frequency,
    with a small floor so no topic disappears. No network calls."""
    skills = compute_skills(db, allow_network=False)
    raw = {t["topic"]: max(0.02, (1.0 - t["p_solve_medium"]) * t["freq"]) for t in skills["topics"]}
    total = sum(raw.values()) or 1.0
    return {k: v / total for k, v in raw.items()}


# ---------------- Codeforces ----------------
def fit_cf(solved, attempted, problems):
    """solved: {key: when}, attempted: set, problems: [{key, rating, tags}] -> rating model dict."""
    by_key = {p["key"]: p for p in problems}
    obs, tag_obs = [], {}
    for key in attempted | set(solved):
        p = by_key.get(key)
        if not p or not p.get("rating"):
            continue
        y = 1.0 if key in solved else 0.0
        obs.append((p["rating"], y))
        for tag in p.get("tags", []):
            tag_obs.setdefault(tag, []).append((p["rating"], y))
    theta = fit_rating(obs)
    tags = []
    for tag, o in tag_obs.items():
        tags.append({"tag": tag, "rating": round(fit_rating(o, prior_mu=theta, prior_sigma=CF_TAG_SIGMA)),
                     "n": len(o), "solved": int(sum(y for _, y in o))})
    tags.sort(key=lambda t: (t["rating"], -t["n"], t["tag"]))
    lo, hi = cf_suggested_range(theta)
    return {"rating": round(theta), "n_attempted": len(obs), "n_solved": int(sum(y for _, y in obs)),
            "suggested_min": lo, "suggested_max": hi, "tags": tags,
            "weakest_tags": [t["tag"] for t in tags if t["n"] >= 2][:5]}


def compute_cf(db, allow_network=True):
    repo = NotificationRepository(db)
    handle = repo.get_setting("cf_handle", "Veratril") or ""
    hit = _CF_CACHE.get(handle)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return {**hit[1], "cached": True}
    if not handle:
        lo, hi = cf_suggested_range(CF_PRIOR_MU)
        return {"handle": None, "rating": round(CF_PRIOR_MU), "n_attempted": 0, "n_solved": 0, "suggested_min": lo,
                "suggested_max": hi, "tags": [], "weakest_tags": [], "error": "Set your Codeforces handle in Settings."}
    if not allow_network:
        return None
    try:
        solved, attempted = integrations.cf_user_submissions(handle)
        problems = integrations.cf_problemset()
    except Exception as e:
        lo, hi = cf_suggested_range(CF_PRIOR_MU)
        stored = repo.get_setting(CF_RATING_SETTING)
        return {"handle": handle, "rating": int(stored) if stored and stored.isdigit() else None,
                "n_attempted": 0, "n_solved": 0, "suggested_min": lo, "suggested_max": hi, "tags": [],
                "weakest_tags": [], "error": f"Couldn't reach Codeforces: {e}"}
    result = {"handle": handle, **fit_cf(solved, attempted, problems)}
    _CF_CACHE[handle] = (time.time(), result)
    try:
        repo.set_setting(CF_RATING_SETTING, str(result["rating"]))
    except Exception as e:
        print(f"insights: could not store cf rating: {e}")
    return result


# ---------------- routes ----------------
def _ok(payload):
    return jsonify({"status": "success", **payload})


@insights_bp.route("/study", methods=["GET"])
def study():
    db = SessionLocal()
    try:
        return _ok(compute_study(db))
    finally:
        db.close()


@insights_bp.route("/skills", methods=["GET"])
def skills():
    db = SessionLocal()
    try:
        return _ok(compute_skills(db, allow_network=True))
    finally:
        db.close()


@insights_bp.route("/cf", methods=["GET"])
def cf():
    db = SessionLocal()
    try:
        return _ok(compute_cf(db, allow_network=True))
    finally:
        db.close()


@insights_bp.route("/summary", methods=["GET"])
def summary():
    db = SessionLocal()
    try:
        st = compute_study(db)
        upcoming = [s for s in st["subjects"] if s["days_left"] is not None and s["days_left"] >= 0]
        top = upcoming[0] if upcoming else None
        sk = compute_skills(db, allow_network=False)
        weakest = next((t for t in sk["topics"] if t["n"] > 0), None)
        cf_res = compute_cf(db, allow_network=False)
        cf_rating = cf_res.get("rating") if cf_res else None
        if cf_rating is None:
            stored = NotificationRepository(db).get_setting(CF_RATING_SETTING)
            cf_rating = int(stored) if stored and stored.isdigit() else None
        compact = [{k: s[k] for k in ("id", "name", "short", "color", "exam_date", "days_left", "readiness_now",
                                      "readiness_exam", "hours_today", "p_finish", "pending")} for s in upcoming]
        return _ok({
            "plan": st["plan"],
            "empty_reason": st.get("empty_reason"),
            "subjects": compact,
            "top_exam": {**{k: top[k] for k in ("id", "name", "short", "color", "exam_date", "days_left",
                                                "readiness_now", "readiness_exam", "p_finish", "hours_today")},
                         "study_next": top["study_next"][:3]} if top else None,
            "study_next": [{**t, "subject_id": s["id"], "short": s["short"] or s["name"], "color": s["color"]}
                           for s in upcoming for t in s["study_next"]][:3],
            "weakest_topic": {k: weakest[k] for k in ("topic", "rating", "p_solve_medium", "n")} if weakest else None,
            "recommended_topic": sk["recommended_topic"],
            "cf_rating": cf_rating,
        })
    finally:
        db.close()
