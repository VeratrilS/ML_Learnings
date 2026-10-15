"""
Live job discovery for Job Radar: public company job boards -> India early-career software roles.

Only public, documented job-board feeds are read (Greenhouse, Lever, Ashby). Nothing is ever submitted to a
company: the scan finds and scores openings; Sai applies on the official portal and confirms in Job Radar.

Design:
  - Strategy: one BoardSource per job-board type (fetch + normalize to a common Posting).
  - COMPANIES: verified (board, token) pairs (checked live on 2026-10-16 to have India openings).
  - Filters + deterministic match score against the resume's skills (no ML guesses).
  - scan(): parallel fetch -> filter -> score -> upsert into job_radar.JobOpportunity.

Endpoints (blueprint job_sources_bp, prefix /api/jobs):
  POST /api/jobs/scan   -> scheduler entry (open endpoint, throttled to once per 20 h); emails a digest of new matches
  GET  /api/jobs/live   -> live-discovered openings, best match first (passcode-protected)
"""
import html
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, jsonify, request

from api.core.config import APP_URL, RECEIVER_EMAIL
from api.core.db import SessionLocal

TIMEOUT = 12
WORKERS = 12
SCAN_GAP = timedelta(hours=20)
LAST_SCAN_KEY = "jobs_last_scan"
DIGEST_MIN_SCORE = 60

# (display name, board type, board token) — each verified to return India openings.
COMPANIES = [
    ("Databricks", "greenhouse", "databricks"), ("Stripe", "greenhouse", "stripe"),
    ("MongoDB", "greenhouse", "mongodb"), ("Okta", "greenhouse", "okta"),
    ("Zscaler", "greenhouse", "zscaler"), ("GitLab", "greenhouse", "gitlab"),
    ("Rubrik", "greenhouse", "rubrik"), ("Datadog", "greenhouse", "datadog"),
    ("Coinbase", "greenhouse", "coinbase"), ("Elastic", "greenhouse", "elastic"),
    ("Twilio", "greenhouse", "twilio"), ("Druva", "greenhouse", "druva"),
    ("HighRadius", "greenhouse", "highradius"), ("InMobi", "greenhouse", "inmobi"),
    ("HackerRank", "greenhouse", "hackerrank"), ("Groww", "greenhouse", "groww"),
    ("Razorpay", "greenhouse", "razorpaysoftwareprivatelimited"), ("Airbnb", "greenhouse", "airbnb"),
    ("Samsara", "greenhouse", "samsara"), ("Anthropic", "greenhouse", "anthropic"),
    ("Figma", "greenhouse", "figma"), ("Scale AI", "greenhouse", "scaleai"), ("Duolingo", "greenhouse", "duolingo"),
    ("Paytm", "lever", "paytm"), ("Meesho", "lever", "meesho"), ("Zeta", "lever", "zeta"),
    ("FamPay", "lever", "fampay"), ("CRED", "lever", "cred"), ("Spotify", "lever", "spotify"),
    ("OpenAI", "ashby", "openai"), ("Notion", "ashby", "notion"),
]

INDIA = ("india", "bengaluru", "bangalore", "hyderabad", "pune", "gurugram", "gurgaon", "mumbai", "chennai",
         "noida", "delhi", "kolkata", "ahmedabad", "remote - in", "remote, in")
ROLE = re.compile(r"\b(software|sde|developer|engineer|backend|back-end|full[ -]?stack|frontend|front-end|platform|"
                  r"infrastructure|machine learning|ml|data engineer|site reliability|sre|security engineer)\b", re.I)
SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|manager|director|head|architect|vp|distinguished|"
                    r"ii|iii|iv|2|3|4|l[4-9]|sde[- ]?(2|3|ii|iii))\b", re.I)
EARLY = re.compile(r"\b(new grad|graduate|university|campus|entry[- ]level|junior|associate|early career|fresher|"
                   r"2026|2027|engineer i\b|sde[- ]?(1|i)\b|software engineer 1|intern)", re.I)
NOT_SWE = re.compile(r"\b(sales|account executive|recruit|marketing|legal|counsel|finance|accountant|support "
                     r"engineer|solutions engineer|customer|designer|product manager|program manager|ux|ui/ux|"
                     r"people|hr|talent|workplace|it support|helpdesk|technical writer|analyst|consultant)\b", re.I)
YEARS = re.compile(r"(\d+)\s*\+?\s*(?:-\s*\d+\s*)?years?", re.I)

# Skills from the resume (word-boundary regex, label shown in the UI).
SKILLS = [
    ("C++", r"c\+\+"), ("Python", r"python"), ("JavaScript", r"javascript|\bjs\b"), ("SQL", r"\bsql\b"),
    ("React", r"\breact"), ("Node.js", r"node\.?js|\bnode\b"), ("Express", r"express\.?js"), ("Kafka", r"kafka"),
    ("Redis", r"\bredis"), ("Elasticsearch", r"elastic ?search"), ("PostgreSQL", r"postgres"),
    ("MongoDB", r"mongo"), ("Microservices", r"micro-?services?"), ("Distributed systems", r"distributed"),
    ("REST APIs", r"\brest\b|restful"), ("Git", r"\bgit\b"), ("Data structures & algorithms", r"data structures|algorithm"),
    ("LLMs", r"\bllms?\b|large language"), ("Linux", r"linux"), ("Multithreading", r"multi-?thread|concurren"),
]


@dataclass
class Posting:
    company: str
    board: str
    job_id: str
    title: str
    location: str
    url: str
    text: str = ""
    updated: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def external_id(self):
        return f"{self.board}:{self.company.lower().replace(' ', '')}:{self.job_id}"[:80]


def _plain(s):
    s = html.unescape(s or "")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


# ---------------- Strategy: board sources ----------------
class BoardSource:
    name = "base"

    def list_postings(self, company, token, get=requests.get):  # pragma: no cover - interface
        raise NotImplementedError

    def details(self, posting, get=requests.get):
        """Fill posting.text when the list endpoint didn't include a description."""
        return posting


class GreenhouseSource(BoardSource):
    name = "greenhouse"

    def list_postings(self, company, token, get=requests.get):
        r = get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", timeout=TIMEOUT)
        r.raise_for_status()
        return [Posting(company, self.name, str(j["id"]), j.get("title", ""), (j.get("location") or {}).get("name", ""),
                        j.get("absolute_url", ""), updated=j.get("updated_at", ""), meta={"token": token})
                for j in r.json().get("jobs", [])]

    def details(self, posting, get=requests.get):
        try:
            r = get(f"https://boards-api.greenhouse.io/v1/boards/{posting.meta['token']}/jobs/{posting.job_id}", timeout=TIMEOUT)
            if r.ok:
                posting.text = _plain(r.json().get("content", ""))
        except Exception:
            pass
        return posting


class LeverSource(BoardSource):
    name = "lever"

    def list_postings(self, company, token, get=requests.get):
        r = get(f"https://api.lever.co/v0/postings/{token}?mode=json", timeout=TIMEOUT)
        r.raise_for_status()
        out = []
        for j in r.json():
            cats = j.get("categories") or {}
            text = " ".join([j.get("descriptionPlain") or ""] + [l.get("content", "") for l in j.get("lists") or []])
            out.append(Posting(company, self.name, j.get("id", ""), j.get("text", ""), cats.get("location") or "",
                               j.get("hostedUrl", ""), _plain(text), str(j.get("createdAt", ""))))
        return out


class AshbySource(BoardSource):
    name = "ashby"

    def list_postings(self, company, token, get=requests.get):
        r = get(f"https://api.ashbyhq.com/posting-api/job-board/{token}", timeout=TIMEOUT)
        r.raise_for_status()
        return [Posting(company, self.name, j.get("id", ""), j.get("title", ""), j.get("location") or "",
                        j.get("jobUrl", ""), _plain(j.get("descriptionPlain") or j.get("descriptionHtml") or ""),
                        j.get("publishedAt", ""))
                for j in r.json().get("jobs", []) if j.get("isListed", True)]


SOURCES = {s.name: s for s in (GreenhouseSource(), LeverSource(), AshbySource())}


# ---------------- filtering & scoring ----------------
def is_india(posting):
    loc = posting.location.lower()
    return any(k in loc for k in INDIA)


def is_candidate_role(posting):
    """Software role that isn't explicitly senior and isn't a non-engineering job."""
    t = posting.title
    return bool(ROLE.search(t)) and not SENIOR.search(t) and not NOT_SWE.search(t)


def years_required(text):
    nums = [int(m.group(1)) for m in YEARS.finditer(text or "") if int(m.group(1)) < 20]
    return min(nums) if nums else None


def score(posting):
    """Deterministic 0-100 match against the resume. Returns (score, matched skill labels, years required)."""
    hay = f"{posting.title} {posting.text}".lower()
    matched = [label for label, pattern in SKILLS if re.search(pattern, hay)]
    years = years_required(posting.text)
    s = 35 + min(40, 5 * len(matched))
    if EARLY.search(posting.title) or EARLY.search(posting.text[:2000]):
        s += 20
    if years is not None:
        s -= 0 if years <= 1 else 15 if years <= 2 else 35
    return max(0, min(100, s)), matched, years


def collect(get=requests.get, companies=None):
    """Fetch every board in parallel, keep India early-career-compatible software roles, fetch details, score."""
    companies = companies or COMPANIES
    errors, picked = [], []

    def one(entry):
        company, board, token = entry
        try:
            postings = SOURCES[board].list_postings(company, token, get=get)
            return [p for p in postings if is_india(p) and is_candidate_role(p)], None
        except Exception as e:
            return [], f"{company}: {str(e)[:80]}"

    with ThreadPoolExecutor(WORKERS) as ex:
        for found, err in ex.map(one, companies):
            picked.extend(found)
            if err:
                errors.append(err)
    with ThreadPoolExecutor(WORKERS) as ex:
        picked = list(ex.map(lambda p: p if p.text else SOURCES[p.board].details(p, get=get), picked))
    scored = []
    for p in picked:
        s, matched, years = score(p)
        if years is not None and years >= 3:
            continue  # clearly not an early-career opening
        scored.append((p, s, matched, years))
    scored.sort(key=lambda x: -x[1])
    return scored, errors


# ---------------- persistence (Job Radar's table) ----------------
def upsert(db, scored):
    """Insert new openings, refresh existing ones. Never touches status/applied fields Sai set."""
    from api.domain.job_radar import JobOpportunity
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    seen = {}
    for p, s, matched, years in scored:
        seen[p.external_id] = (p, s, matched, years)
    existing = {j.external_id: j for j in db.query(JobOpportunity).filter(JobOpportunity.external_id.in_(list(seen))).all()} if seen else {}
    new = []
    for ext, (p, s, matched, years) in seen.items():
        job = existing.get(ext)
        note = f"Live from {p.board.title()}" + (f"; asks for {years}+ years" if years else "")
        if job is None:
            job = JobOpportunity(external_id=ext, company=p.company[:120], role=p.title[:180], ctc_lpa=0.0,
                                 location=(p.location or "India")[:160], source=f"{p.board.title()} (live)"[:120],
                                 portal_url=p.url, skills_required=json.dumps(matched), match_score=s,
                                 shortlist_prob=0.0, status="discovered", notes=note, discovered_at=now,
                                 last_checked_at=now)
            db.add(job)
            new.append(job)
        else:
            job.role, job.portal_url, job.match_score = p.title[:180], p.url, s
            job.skills_required, job.last_checked_at = json.dumps(matched), now
            if not job.notes or job.notes.startswith("Live from"):
                job.notes = note
    db.commit()
    return new


def digest_html(new_jobs):
    e = html.escape
    rows = "".join(
        f'<tr><td style="padding:8px 0;border-top:1px solid #eee"><a href="{e(j.portal_url)}" style="color:#c2410c;font-weight:600;'
        f'text-decoration:none">{e(j.role)}</a><br><span style="color:#6b7280;font-size:13px">{e(j.company)} · {e(j.location)} · '
        f'match {j.match_score}</span></td></tr>' for j in new_jobs[:25])
    return (f'<!doctype html><html><body style="margin:0;background:#f5f5f7;padding:24px 12px">'
            f'<div style="max-width:620px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:18px;padding:28px;'
            f'font:15px/1.5 system-ui,sans-serif;color:#111827"><h1 style="margin:0 0 6px;font-size:22px">{len(new_jobs)} new openings</h1>'
            f'<p style="margin:0 0 14px;color:#4b5563">Early-career software roles in India from company career pages. '
            f'Apply on the official portal, then tap "I applied" in Job Radar.</p><table width="100%">{rows}</table>'
            f'<p style="margin:22px 0 0"><a href="{APP_URL}#/jobradar" style="display:inline-block;background:#111827;color:#fff;'
            f'padding:11px 18px;border-radius:10px;font-weight:600;text-decoration:none">Open Job Radar</a></p></div></body></html>')


def send_digest(new_jobs):
    good = [j for j in new_jobs if (j.match_score or 0) >= DIGEST_MIN_SCORE]
    sender, password = os.getenv("SENDER_EMAIL"), os.getenv("SENDER_PASSWORD")
    if not good or not (sender and password):
        return False
    from api.core.clients import EmailClient
    good.sort(key=lambda j: -(j.match_score or 0))
    return EmailClient(sender, password).send_email(
        RECEIVER_EMAIL, f"💼 {len(good)} new job openings for you", "New openings: " + APP_URL, html=digest_html(good))


# ---------------- routes ----------------
job_sources_bp = Blueprint("job_sources", __name__, url_prefix="/api/jobs")


def _serialize(j):
    try:
        skills = json.loads(j.skills_required or "[]")
    except ValueError:
        skills = []
    return {"id": j.id, "company": j.company, "role": j.role, "location": j.location, "source": j.source,
            "url": j.portal_url, "match_score": j.match_score, "skills": skills, "status": j.status, "notes": j.notes,
            "discovered_at": j.discovered_at.isoformat() + "Z" if j.discovered_at else None}


@job_sources_bp.route("/scan", methods=["POST"])
def scan_route():
    from api.domain.repositories import NotificationRepository
    db = SessionLocal()
    try:
        repo = NotificationRepository(db)
        last = repo.get_setting(LAST_SCAN_KEY)
        if last and datetime.now(timezone.utc) - datetime.fromisoformat(last) < SCAN_GAP:
            return jsonify({"status": "skipped", "message": "Scanned recently."})
        scored, errors = collect()
        new = upsert(db, scored)
        emailed = send_digest(new)
        repo.set_setting(LAST_SCAN_KEY, datetime.now(timezone.utc).isoformat())
        return jsonify({"status": "success", "data": {"found": len(scored), "new": len(new), "emailed": bool(emailed),
                                                      "errors": errors}})
    finally:
        db.close()


@job_sources_bp.route("/live", methods=["GET"])
def live_route():
    from api.domain.job_radar import JobOpportunity
    try:
        min_score = int(request.args.get("min_score", 0))
    except ValueError:
        min_score = 0
    db = SessionLocal()
    try:
        rows = (db.query(JobOpportunity).filter(JobOpportunity.source.like("%(live)"), JobOpportunity.match_score >= min_score)
                .order_by(JobOpportunity.match_score.desc(), JobOpportunity.discovered_at.desc()).limit(300).all())
        return jsonify({"status": "success", "data": [_serialize(j) for j in rows]})
    finally:
        db.close()
