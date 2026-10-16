"""
Live job discovery for Job Radar: public company job boards -> India early-career software roles.

Only public, documented job-board feeds are read (Greenhouse, Lever, Ashby, SmartRecruiters, Workday career sites).
Nothing is ever submitted to a company: the scan finds and scores openings; Sai applies on the official portal and
confirms in Job Radar.

Design:
  - Strategy: one BoardSource per job-board type (fetch + normalize to a common Posting).
  - COMPANIES: verified (board, token) pairs (checked live on 2026-10-16 to have India openings), merged with the
    NextLeet list in job_companies.py (deduped by board:token).
  - Filters (India, early-career-compatible software role, posted within MAX_AGE_DAYS) + deterministic match score
    against the resume's skills (no ML guesses).
  - collect(): parallel fetch -> filter -> details for the best candidates -> score, inside a time budget.

Endpoints (blueprint job_sources_bp, prefix /api/jobs):
  POST /api/jobs/scan   -> scheduler entry (open endpoint, throttled to once per 5 h); digest email at most once per 20 h
  GET  /api/jobs/live   -> live-discovered openings, best match first
                           (?min_score=&min_ctc=&strict_ctc=1&role_type=fte,intern_6m)
  Each successful scan sends at most one "New role released" email (FTE / 6-month intern, match >= 60, CTC >= 15 or
  unknown) with signed Approve / Skip links from job_approvals.
"""
import html
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import requests
from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from api.core.config import APP_URL, RECEIVER_EMAIL
from api.core.db import SessionLocal
from api.domain.job_companies import EST_CTC, NEXTLEET_COMPANIES

TIMEOUT = 12            # per HTTP request (s)
WORKERS = 24
SCAN_BUDGET = 130       # whole collect() (s); list phase gets LIST_SHARE of it, details the rest
LIST_SHARE = 0.7
SOURCE_BUDGET = 40      # max time one board spends paginating (s)
DETAIL_CAP = 400        # detail fetches only for the best candidates by title (~350 needed on 2026-10-16)
MAX_AGE_DAYS = 45       # skip postings older than this when the board gives a date
WD_PAGE, WD_MAX_PAGES = 20, 5      # Workday caps a page at 20
SR_PAGE, SR_MAX = 100, 500
SCAN_GAP = timedelta(hours=5)       # the scheduler hits /scan ~4x a day
DIGEST_GAP = timedelta(hours=20)    # ...but at most one digest email a day
LAST_SCAN_KEY = "jobs_last_scan_v2"  # v2: the v1 slot was taken by a scan that failed on a NOT NULL column
LAST_DIGEST_KEY = "jobs_last_digest"
DIGEST_MIN_SCORE = 60
DIGEST_MIN_CTC = 15.0
JSON_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

# (display name, board type, board token) — each fetched live on 2026-10-16 with >= 1 India opening.
# Workday token = "tenant|wdN|site".  Counts in comments = India postings seen that day (Workday: India hits for
# "software engineer").
COMPANIES = [
    # Greenhouse
    ("Databricks", "greenhouse", "databricks"), ("Stripe", "greenhouse", "stripe"),            # 95, 47
    ("MongoDB", "greenhouse", "mongodb"), ("Okta", "greenhouse", "okta"),                       # 85, 110
    ("Zscaler", "greenhouse", "zscaler"), ("GitLab", "greenhouse", "gitlab"),                   # 68, 33
    ("Rubrik", "greenhouse", "rubrik"), ("Datadog", "greenhouse", "datadog"),                   # 33, 10
    ("Coinbase", "greenhouse", "coinbase"), ("Elastic", "greenhouse", "elastic"),               # 9, 18
    ("Twilio", "greenhouse", "twilio"), ("Druva", "greenhouse", "druva"),                       # 14, 12
    ("HighRadius", "greenhouse", "highradius"), ("InMobi", "greenhouse", "inmobi"),             # 50, 42
    ("HackerRank", "greenhouse", "hackerrank"), ("Groww", "greenhouse", "groww"),               # 20, 10
    ("Razorpay", "greenhouse", "razorpaysoftwareprivatelimited"), ("Airbnb", "greenhouse", "airbnb"),  # 22, 4
    ("Samsara", "greenhouse", "samsara"), ("Anthropic", "greenhouse", "anthropic"),             # 4, 3
    ("Figma", "greenhouse", "figma"), ("Scale AI", "greenhouse", "scaleai"), ("Duolingo", "greenhouse", "duolingo"),
    ("Harness", "greenhouse", "harnessinc"), ("Agoda", "greenhouse", "agoda"),                  # 7, 12
    ("Toast", "greenhouse", "toast"), ("Netskope", "greenhouse", "netskope"),                   # 19, 20
    ("Pure Storage", "greenhouse", "purestorage"), ("New Relic", "greenhouse", "newrelic"),     # 72, 8
    ("Fivetran", "greenhouse", "fivetran"), ("Sumo Logic", "greenhouse", "sumologic"),          # 23, 5
    ("Celonis", "greenhouse", "celonis"), ("Sigmoid", "greenhouse", "sigmoid"),                 # 28, 30
    ("Yugabyte", "greenhouse", "yugabyte"), ("Appian", "greenhouse", "appian"),                 # 5, 24
    ("ZoomInfo", "greenhouse", "zoominfo"), ("Observe.AI", "greenhouse", "observeai"),          # 18, 4
    ("Turing", "greenhouse", "turing"), ("Neo4j", "greenhouse", "neo4j"),                       # 5, 5
    ("SingleStore", "greenhouse", "singlestore"), ("Starburst", "greenhouse", "starburst"),     # 9, 5
    ("BitGo", "greenhouse", "bitgo"), ("Tower Research Capital", "greenhouse", "towerresearchcapital"),  # 7, 10
    ("IMC", "greenhouse", "imc"), ("Jump Trading", "greenhouse", "jumptrading"),                # 18, 4
    ("Squarepoint Capital", "greenhouse", "squarepointcapital"), ("Arcesium", "greenhouse", "arcesiumllc"),  # 23, 18
    ("Zeta Global", "greenhouse", "zetaglobal"),                                                # 40
    # Lever
    ("Paytm", "lever", "paytm"), ("Meesho", "lever", "meesho"), ("Zeta", "lever", "zeta"),      # 148, 54, 21
    ("FamPay", "lever", "fampay"), ("CRED", "lever", "cred"), ("Spotify", "lever", "spotify"),  # 17, 7, 1
    ("Mindtickle", "lever", "mindtickle"), ("Hevo Data", "lever", "hevodata"), ("Outreach", "lever", "outreach"),  # 18, 53, 6
    # Ashby
    ("OpenAI", "ashby", "openai"), ("Notion", "ashby", "notion"),                               # 7, 2
    ("Sarvam AI", "ashby", "sarvam"), ("Cursor", "ashby", "cursor"),                            # 42, 5
    ("ClickHouse", "ashby", "clickhouse"), ("Sardine", "ashby", "sardine"),                     # 10, 1
    ("Ema", "ashby", "ema"), ("Snowflake", "ashby", "snowflake"),                               # 14, 7
    # SmartRecruiters (country=in)
    ("Swiggy", "smartrecruiters", "swiggy"), ("ServiceNow", "smartrecruiters", "servicenow"),   # 195, 76
    ("Freshworks", "smartrecruiters", "freshworks"), ("Arista Networks", "smartrecruiters", "aristanetworks"),  # 37, 26
    ("Canva", "smartrecruiters", "canva"), ("Wise", "smartrecruiters", "wise"),                 # 5, 31
    # Workday
    ("NVIDIA", "workday", "nvidia|wd5|NVIDIAExternalCareerSite"),                               # 136
    ("Salesforce", "workday", "salesforce|wd12|External_Career_Site"),                          # 45
    ("Adobe", "workday", "adobe|wd5|external_experienced"),                                     # 29
    ("Intel", "workday", "intel|wd1|External"),                                                 # 28
    ("Target", "workday", "target|wd5|targetcareers"),                                          # 38
    ("PayPal", "workday", "paypal|wd1|jobs"),                                                   # 6
    ("Autodesk", "workday", "autodesk|wd1|Ext"),                                                # 22
    ("Mastercard", "workday", "mastercard|wd1|CorporateCareers"),                               # 132
    ("Broadcom", "workday", "broadcom|wd1|External_Career"),                                    # 22
    ("Motorola Solutions", "workday", "motorolasolutions|wd5|Careers"),                         # 37
    ("Micron", "workday", "micron|wd1|External"),                                               # 65
    ("Workday", "workday", "workday|wd5|Workday"),                                              # 9
    ("Analog Devices", "workday", "analogdevices|wd1|External"),                                # 97
    ("HP", "workday", "hp|wd5|ExternalCareerSite"),                                             # 26
    ("Red Hat", "workday", "redhat|wd5|jobs"),                                                  # 6
    ("Visa", "workday", "visa|wd5|Visa"),                                                       # 53
    ("Expedia", "workday", "expedia|wd108|search"),                                             # 8
    ("CrowdStrike", "workday", "crowdstrike|wd5|crowdstrikecareers"),                           # 15
    ("Cisco", "workday", "cisco|wd5|Cisco_Careers"),                                            # 207
    ("Sprinklr", "workday", "sprinklr|wd1|careers"),                                            # 14
    ("Equinix", "workday", "equinix|wd1|External"),                                             # 15
    ("eBay", "workday", "ebay|wd5|apply"),                                                      # 64
    ("KLA", "workday", "kla|wd1|Search"),                                                       # 36
    ("Citi", "workday", "citi|wd5|2"),                                                          # 239
    ("Deutsche Bank", "workday", "db|wd3|DBWebSite"),                                           # 63
    ("State Street", "workday", "statestreet|wd1|Global"),                                      # 74
    ("Fidelity", "workday", "fmr|wd1|FidelityCareers"),                                         # 8
    ("BlackRock", "workday", "blackrock|wd1|BlackRock_Professional"),                           # 16
    ("Morgan Stanley", "workday", "ms|wd5|External"),                                           # 16
    ("LSEG", "workday", "lseg|wd3|Careers"),                                                    # 97
    ("Nasdaq", "workday", "nasdaq|wd1|Global_External_Site"),                                   # 25
    ("Marvell", "workday", "marvell|wd1|MarvellCareers"),                                       # 31
    ("NXP", "workday", "nxp|wd3|careers"),                                                      # 63
    ("HPE", "workday", "hpe|wd5|Jobsathpe"),                                                    # 233
    ("Thomson Reuters", "workday", "thomsonreuters|wd5|External_Career_Site"),                  # 20
    ("Warner Bros. Discovery", "workday", "warnerbros|wd5|global"),                             # 17
    ("Disney", "workday", "disney|wd5|disneycareer"),                                           # 20
    ("Cadence", "workday", "cadence|wd1|External_Careers"),                                     # 129
    ("Barclays", "workday", "barclays|wd3|External_Career_Site_Barclays"),                      # 132
    ("S&P Global", "workday", "spgi|wd5|SPGI_Careers"),                                         # 18
    ("Lowe's", "workday", "lowes|wd5|LWS_External_CS"),                                         # 8
]


def _key(board, token):
    return f"{board}:{token.lower()}"


# NextLeet companies (fresher CTC >= 15 LPA est.) merged in; existing COMPANIES entries win on duplicates.
CTC_BAND = {_key(b, t): band for _n, b, t, band in NEXTLEET_COMPANIES}
_seen_keys = {_key(b, t) for _n, b, t in COMPANIES}
ALL_COMPANIES = COMPANIES + [(n, b, t) for n, b, t, _band in NEXTLEET_COMPANIES
                             if _key(b, t) not in _seen_keys and not _seen_keys.add(_key(b, t))]
CURATED_NAMES = {n for n, _b, _t in COMPANIES}

INDIA = re.compile(r"\b(india|bengaluru|bangalore|hyderabad|pune|gurugram|gurgaon|mumbai|chennai|noida|delhi|kolkata|"
                   r"ahmedabad|mysuru|mysore|kochi|trivandrum|thiruvananthapuram|coimbatore|jaipur|indore|chandigarh|"
                   r"mohali|hosur|karnataka|telangana|maharashtra|tamil nadu|haryana|remote - in|remote, in)\b", re.I)
ROLE = re.compile(r"\b(software|sde|developer|engineer|backend|back-end|full[ -]?stack|frontend|front-end|platform|"
                  r"infrastructure|machine learning|ml|data engineer|site reliability|sre|security engineer)\b", re.I)
SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|manager|director|head|architect|vp|vice president|avp|"
                    r"distinguished|smts|lmts|pmts|ii|iii|iv|2|3|4|l[4-9]|sde[- ]?(2|3|ii|iii))\b", re.I)
EARLY = re.compile(r"\b(new grad|graduate|university|campus|entry[- ]level|junior|associate|early career|fresher|"
                   r"2026|2027|engineer i\b|sde[- ]?(1|i)\b|software engineer 1|intern)", re.I)
NOT_SWE = re.compile(r"\b(sales|account executive|recruit|marketing|legal|counsel|finance|accountant|support "
                     r"engineer|solutions engineer|customer|designer|product manager|program manager|ux|ui/ux|"
                     r"people|hr|talent|workplace|it support|helpdesk|technical writer|analyst|consultant)\b", re.I)
YEARS = re.compile(r"(\d+)\s*\+?\s*(?:-\s*\d+\s*)?years?", re.I)
DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
INTERN = re.compile(r"\bintern(ship)?s?\b", re.I)
_TO = r"\s*(?:-|\u2013|\u2014|to)\s*"
SIX_MONTH = re.compile(r"\b(?:6|six)[- ]?months?\b|\b24[- ]?weeks?\b|"
                       r"\bjan(?:uary)?\.?(?:\s*'?\d{2,4})?" + _TO + r"jun(?:e)?\b|"
                       r"\bjul(?:y)?\.?(?:\s*'?\d{2,4})?" + _TO + r"dec(?:ember)?\b", re.I)
SHORT_INTERN = re.compile(r"\bsummer\b|\b(?:8|10|12|eight|ten|twelve)(?:" + _TO + r"\d+)?[- ]?weeks?\b|"
                          r"\b(?:2|3|two|three)(?:" + _TO + r"\d+)?[- ]?months?\b", re.I)
ROLE_LABELS = {"fte": "[FTE]", "intern_6m": "[6-month intern]", "intern": "[Intern, duration not stated]"}
ALERT_ROLE_TYPES = ("fte", "intern_6m")
ALERT_MIN_SCORE = 60

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
    posted: str = ""  # YYYY-MM-DD when the board gives a posting date, else ""
    role_type: str = ""  # "fte" | "intern_6m" | "intern" (set by collect via classify_role)
    meta: dict = field(default_factory=dict)

    @property
    def external_id(self):
        return f"{self.board}:{self.company.lower().replace(' ', '')}:{self.job_id}"[:80]


def _plain(s):
    s = html.unescape(s or "")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _to_date(value):
    """ISO string / epoch (s or ms) -> 'YYYY-MM-DD', or '' when unknown."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)) or str(value).isdigit():
        ts = float(value)
        ts = ts / 1000 if ts > 1e11 else ts
        return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
    m = DATE.search(str(value))
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _workday_posted_on(text, today=None):
    """'Posted Today' / 'Posted Yesterday' / 'Posted 5 Days Ago' -> date; '30+ Days Ago' is open-ended -> ''."""
    today = today or date.today()
    t = (text or "").lower()
    if "today" in t:
        return today.isoformat()
    if "yesterday" in t:
        return (today - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)(\+?)\s*days?", t)
    return (today - timedelta(days=int(m.group(1)))).isoformat() if m and not m.group(2) else ""


def is_fresh(posting, today=None):
    """True unless the board gave a posting date older than MAX_AGE_DAYS."""
    if not posting.posted:
        return True
    try:
        return ((today or date.today()) - date.fromisoformat(posting.posted)).days <= MAX_AGE_DAYS
    except ValueError:
        return True


def _india_label(loc):
    """Board already filtered to India (facet / country=in): make sure the label says so."""
    loc = (loc or "").strip()
    return loc if re.search(r"\bindia\b", loc, re.I) else (f"{loc}, India" if loc else "India")


# ---------------- Strategy: board sources ----------------
class BoardSource:
    name = "base"

    def list_postings(self, company, token, get=requests.get, post=requests.post):  # pragma: no cover - interface
        raise NotImplementedError

    def details(self, posting, get=requests.get):
        """Fill posting.text when the list endpoint didn't include a description."""
        return posting


class GreenhouseSource(BoardSource):
    name = "greenhouse"

    def list_postings(self, company, token, get=requests.get, post=requests.post):
        r = get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", timeout=TIMEOUT)
        r.raise_for_status()
        return [Posting(company, self.name, str(j["id"]), j.get("title", ""), (j.get("location") or {}).get("name", ""),
                        j.get("absolute_url", ""), updated=j.get("updated_at", ""),
                        posted=_to_date(j.get("first_published") or j.get("updated_at")), meta={"token": token})
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

    def list_postings(self, company, token, get=requests.get, post=requests.post):
        r = get(f"https://api.lever.co/v0/postings/{token}?mode=json", timeout=TIMEOUT)
        r.raise_for_status()
        out = []
        for j in r.json():
            cats = j.get("categories") or {}
            text = " ".join([j.get("descriptionPlain") or ""] + [l.get("content", "") for l in j.get("lists") or []])
            out.append(Posting(company, self.name, j.get("id", ""), j.get("text", ""), cats.get("location") or "",
                               j.get("hostedUrl", ""), _plain(text), str(j.get("createdAt", "")),
                               posted=_to_date(j.get("createdAt"))))
        return out


class AshbySource(BoardSource):
    name = "ashby"

    def list_postings(self, company, token, get=requests.get, post=requests.post):
        r = get(f"https://api.ashbyhq.com/posting-api/job-board/{token}", timeout=TIMEOUT)
        r.raise_for_status()
        return [Posting(company, self.name, j.get("id", ""), j.get("title", ""), j.get("location") or "",
                        j.get("jobUrl", ""), _plain(j.get("descriptionPlain") or j.get("descriptionHtml") or ""),
                        j.get("publishedAt", ""), posted=_to_date(j.get("publishedAt")))
                for j in r.json().get("jobs", []) if j.get("isListed", True)]


class SmartRecruitersSource(BoardSource):
    """Public Posting API: GET /v1/companies/{id}/postings?country=in (pages of 100); details at /postings/{id}."""
    name = "smartrecruiters"
    API = "https://api.smartrecruiters.com/v1/companies"
    SKIP_LEVELS = {"director", "executive"}

    def list_postings(self, company, token, get=requests.get, post=requests.post):
        out, offset, t0 = [], 0, time.monotonic()
        while offset < SR_MAX and time.monotonic() - t0 < SOURCE_BUDGET:
            r = get(f"{self.API}/{token}/postings?country=in&limit={SR_PAGE}&offset={offset}", timeout=TIMEOUT)
            r.raise_for_status()
            d = r.json()
            content = d.get("content") or []
            for j in content:
                level = j.get("experienceLevel") or {}
                if level.get("id") in self.SKIP_LEVELS:
                    continue
                loc = j.get("location") or {}
                label = loc.get("fullLocation") or ", ".join(x for x in (loc.get("city"), loc.get("region")) if x)
                if loc.get("remote"):
                    label = f"{label} (Remote)" if label else "Remote"
                out.append(Posting(company, self.name, str(j.get("id", "")), j.get("name", ""), _india_label(label),
                                   f"https://jobs.smartrecruiters.com/{token}/{j.get('id', '')}",
                                   updated=j.get("releasedDate", ""), posted=_to_date(j.get("releasedDate")),
                                   meta={"token": token, "level": level.get("label", "")}))
            offset += SR_PAGE
            if not content or offset >= (d.get("totalFound") or 0):
                break
        return out

    def details(self, posting, get=requests.get):
        try:
            r = get(f"{self.API}/{posting.meta['token']}/postings/{posting.job_id}", timeout=TIMEOUT)
            if r.ok:
                d = r.json()
                sections = ((d.get("jobAd") or {}).get("sections") or {})
                parts = [sections.get(k, {}).get("text", "") for k in ("jobDescription", "qualifications", "additionalInformation")]
                level = posting.meta.get("level")
                posting.text = _plain((f"Experience level: {level}. " if level else "") + " ".join(parts))
                posting.url = d.get("postingUrl") or posting.url
                posting.posted = _to_date(d.get("releasedDate")) or posting.posted
        except Exception:
            pass
        return posting


class WorkdaySource(BoardSource):
    """Public Workday career sites (CXS JSON API). token = 'tenant|wdN|site'.

    1st POST /jobs (no facets) returns the facet tree; we apply the country facet whose value is 'India' (or,
    failing that, every location value naming an Indian city) and page through matches for SEARCH_TEXT.
    """
    name = "workday"
    SEARCH_TEXT = "software engineer"

    @staticmethod
    def _base(token):
        tenant, wd, site = token.split("|")
        return f"https://{tenant}.{wd}.myworkdayjobs.com", tenant, site

    @staticmethod
    def india_facet(facets):
        """-> {facetParameter: [ids]} selecting India, or {} if the site exposes no usable location facet."""
        country, cities = {}, {}

        def walk(fs):
            for f in fs or []:
                param = f.get("facetParameter", "")
                for v in f.get("values") or []:
                    if "values" in v:
                        walk([v])
                        continue
                    d = (v.get("descriptor") or "").strip()
                    if d.lower() == "india":
                        country.setdefault(param, []).append(v.get("id"))
                    elif INDIA.search(d):
                        cities.setdefault(param, []).append(v.get("id"))
        walk(facets)
        for found in (country, cities):
            if found:
                param = max(found, key=lambda p: len(found[p]))
                return {param: found[param]}
        return {}

    def list_postings(self, company, token, get=requests.get, post=requests.post):
        host, tenant, site = self._base(token)
        api = f"{host}/wday/cxs/{tenant}/{site}"
        body = {"appliedFacets": {}, "limit": WD_PAGE, "offset": 0, "searchText": self.SEARCH_TEXT}
        r = post(f"{api}/jobs", json=body, headers=JSON_HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()
        facet = self.india_facet(d.get("facets"))
        out, t0 = [], time.monotonic()
        if facet:
            body["appliedFacets"] = facet
            for page in range(WD_MAX_PAGES):
                if time.monotonic() - t0 > SOURCE_BUDGET:
                    break
                body["offset"] = page * WD_PAGE
                r = post(f"{api}/jobs", json=body, headers=JSON_HEADERS, timeout=TIMEOUT)
                r.raise_for_status()
                d = r.json()
                jobs = d.get("jobPostings") or []
                out += [self._posting(company, j, host, api, site, india=True) for j in jobs]
                if len(jobs) < WD_PAGE or body["offset"] + WD_PAGE >= (d.get("total") or 0):
                    break
        else:  # no location facet: keep first page, India decided by is_india() on locationsText
            out = [self._posting(company, j, host, api, site, india=False) for j in d.get("jobPostings") or []]
        return [p for p in out if p.title]

    def _posting(self, company, j, host, api, site, india):
        path = j.get("externalPath") or ""
        bullets = j.get("bulletFields") or []
        job_id = bullets[0] if bullets else path.rsplit("/", 1)[-1]
        loc = j.get("locationsText") or ""
        return Posting(company, self.name, str(job_id), j.get("title", ""), _india_label(loc) if india else loc,
                       f"{host}/en-US/{site}{path}", updated=j.get("postedOn", ""),
                       posted=_workday_posted_on(j.get("postedOn")), meta={"api": api, "path": path})

    def details(self, posting, get=requests.get):
        try:
            r = get(f"{posting.meta['api']}{posting.meta['path']}", headers={"Accept": "application/json"}, timeout=TIMEOUT)
            if r.ok:
                info = r.json().get("jobPostingInfo") or {}
                posting.text = _plain(info.get("jobDescription", ""))
                posting.posted = _to_date(info.get("startDate")) or posting.posted
        except Exception:
            pass
        return posting


SOURCES = {s.name: s for s in (GreenhouseSource(), LeverSource(), AshbySource(), SmartRecruitersSource(), WorkdaySource())}

# Big companies' own career sites (Amazon, Microsoft, Apple, Goldman, ...): adapters live in job_bigtech.py,
# which imports BoardSource/Posting from this module, so the import has to come after they're defined.
from api.domain.job_bigtech import BIGTECH_COMPANIES, BIGTECH_SOURCES  # noqa: E402

SOURCES.update(BIGTECH_SOURCES)
for _n, _b, _t, _band in BIGTECH_COMPANIES:
    if _key(_b, _t) not in _seen_keys:
        _seen_keys.add(_key(_b, _t))
        ALL_COMPANIES.append((_n, _b, _t))
        CTC_BAND[_key(_b, _t)] = _band


# ---------------- filtering & scoring ----------------
def is_india(posting):
    return bool(INDIA.search(posting.location or ""))


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
    years = years_required(f"{posting.title} {posting.text}")  # titles like "... | 8-14 Years" count too
    s = 35 + min(40, 5 * len(matched))
    if EARLY.search(posting.title) or EARLY.search(posting.text[:2000]):
        s += 20
    if years is not None:
        s -= 0 if years <= 1 else 15 if years <= 2 else 35
    return max(0, min(100, s)), matched, years


def _title_priority(posting):
    """Cheap pre-rank used to pick which candidates get a detail fetch."""
    t = posting.title.lower()
    return (2 if EARLY.search(t) else 0) + (1 if re.search(r"software|sde|developer|backend|full[ -]?stack", t) else 0)


def _parallel(fn, items, deadline):
    """Run fn over items with WORKERS threads until `deadline` (monotonic). -> [(item, result, error)]."""
    if not items:
        return []
    ex = ThreadPoolExecutor(min(WORKERS, len(items)))
    futs = {ex.submit(fn, it): it for it in items}
    out, done = [], set()

    def take(f):
        done.add(f)
        try:
            out.append((futs[f], f.result(), None))
        except Exception as e:
            out.append((futs[f], None, e))
    try:
        for f in as_completed(futs, timeout=max(0.1, deadline - time.monotonic())):
            take(f)
    except FuturesTimeout:
        for f, it in futs.items():
            if f in done:
                continue
            if f.done():
                take(f)
            else:
                out.append((it, None, TimeoutError("scan time budget exceeded")))
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return out


def collect(get=requests.get, companies=None, post=requests.post, budget=SCAN_BUDGET):
    """Fetch every board in parallel, keep fresh India early-career-compatible software roles, fetch details, score.

    Returns (scored, errors): scored = [(Posting, score, matched skills, years required)] best first.
    """
    start = time.monotonic()
    companies = companies or ALL_COMPANIES
    errors, picked, seen = [], [], set()

    def one(entry):
        company, board, token = entry
        band = CTC_BAND.get(_key(board, token)) or EST_CTC.get(company)
        postings = SOURCES[board].list_postings(company, token, get=get, post=post)
        keep = [p for p in postings if is_india(p) and is_candidate_role(p) and is_fresh(p)]
        for p in keep:
            p.meta["ctc"] = band
        return keep

    for (company, _b, _t), found, err in _parallel(one, companies, start + budget * LIST_SHARE):
        if err is not None:
            errors.append(f"{company}: {str(err)[:80]}")
            continue
        for p in found:
            if p.external_id not in seen:
                seen.add(p.external_id)
                picked.append(p)

    need = sorted((p for p in picked if not p.text), key=_title_priority, reverse=True)[:DETAIL_CAP]
    # details() fills each Posting in place; a timed-out fetch just leaves it without text
    _parallel(lambda p: SOURCES[p.board].details(p, get=get), need, start + budget)
    scored = []
    for p in picked:
        if not is_fresh(p):  # detail pages can reveal an older posting date (Workday "30+ days")
            continue
        p.role_type = classify_role(p)
        if p.role_type is None:  # short / summer internship
            continue
        s, matched, years = score(p)
        if years is not None and years >= 3:
            continue  # clearly not an early-career opening
        scored.append((p, s, matched, years))
    scored.sort(key=lambda x: -x[1])
    return scored, errors


def classify_role(posting):
    """'fte' | 'intern_6m' | 'intern' (duration not stated) | None (8-12 week / summer / 2-3 month internship: drop)."""
    title, text = posting.title or "", posting.text or ""
    if not INTERN.search(title):
        return "fte"
    if SHORT_INTERN.search(title):
        return None
    if SIX_MONTH.search(f"{title} {text}"):
        return "intern_6m"
    if SHORT_INTERN.search(text):
        return None
    return "intern"


def role_type_of(job):
    """Read the role type back from the notes prefix written by upsert()."""
    notes = job.notes or ""
    return next((rt for rt, label in ROLE_LABELS.items() if notes.startswith(label)), None)


def ctc_floor(band):
    """'18-28 LPA' -> 18.0, '40+ LPA' -> 40.0, None/unknown -> 0.0."""
    m = re.search(r"(\d+(?:\.\d+)?)", band or "")
    return float(m.group(1)) if m else 0.0


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
        band = p.meta.get("ctc")
        label = ROLE_LABELS.get(p.role_type or classify_role(p) or "intern")
        note = (f"{label} Live from {p.board.title()}" + (f"; posted {p.posted}" if p.posted else "")
                + (f"; asks for {years}+ years" if years else "") + (f"; est. CTC {band}" if band else ""))
        if job is None:
            job = JobOpportunity(external_id=ext, company=p.company[:120], role=p.title[:180], ctc_lpa=ctc_floor(band),
                                 location=(p.location or "India")[:160], source=f"{p.board.title()} (live)"[:120],
                                 portal_url=p.url, skills_required=json.dumps(matched), match_score=s,
                                 shortlist_prob=0.0, status="discovered", notes=note, discovered_at=now,
                                 last_checked_at=now, board=p.board)
            db.add(job)
            new.append(job)
        else:
            job.role, job.portal_url, job.match_score = p.title[:180], p.url, s
            job.skills_required, job.last_checked_at, job.board = json.dumps(matched), now, p.board
            if band and not job.ctc_lpa:
                job.ctc_lpa = ctc_floor(band)
            if not job.notes or job.notes.startswith("Live from") or role_type_of(job):
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
            f'<p style="margin:22px 0 0"><a href="{APP_URL}#/job-radar" style="display:inline-block;background:#111827;color:#fff;'
            f'padding:11px 18px;border-radius:10px;font-weight:600;text-decoration:none">Open Job Radar</a></p></div></body></html>')


def digest_worthy(job):
    """Good match AND (est. fresher CTC >= 15 LPA, or CTC unknown but from the curated big-tech COMPANIES list)."""
    if (job.match_score or 0) < DIGEST_MIN_SCORE:
        return False
    return (job.ctc_lpa or 0) >= DIGEST_MIN_CTC or (not job.ctc_lpa and job.company in CURATED_NAMES)


def send_digest(new_jobs):
    good = [j for j in new_jobs if digest_worthy(j)]
    sender, password = os.getenv("SENDER_EMAIL"), os.getenv("SENDER_PASSWORD")
    if not good or not (sender and password):
        return False
    from api.core.clients import EmailClient
    good.sort(key=lambda j: -(j.match_score or 0))
    return EmailClient(sender, password).send_email(
        RECEIVER_EMAIL, f"💼 {len(good)} new job openings for you", "New openings: " + APP_URL, html=digest_html(good))


def select_alerts(new_jobs):
    """NEW jobs worth an instant email: FTE / 6-month intern, match >= 60, est. CTC >= 15 LPA or unknown."""
    return sorted((j for j in new_jobs if role_type_of(j) in ALERT_ROLE_TYPES and (j.match_score or 0) >= ALERT_MIN_SCORE
                   and (not j.ctc_lpa or j.ctc_lpa >= DIGEST_MIN_CTC)), key=lambda j: -(j.match_score or 0))


def alert_subject(jobs):
    first = jobs[0]
    more = f" (+{len(jobs) - 1} more)" if len(jobs) > 1 else ""
    return f"New role released: {first.company} \u2014 {first.role}{more}"


def alert_html(jobs):
    from api.domain.job_approvals import decide_url
    e = html.escape

    def btn(href, label, bg, fg, border):
        return (f'<a href="{e(href)}" style="display:inline-block;background:{bg};color:{fg};border:1px solid {border};'
                f'padding:9px 16px;border-radius:9px;font-weight:600;font-size:14px;text-decoration:none;margin:8px 8px 0 0">'
                f'{e(label)}</a>')

    def meta(j):
        ctc = f"est. {j.ctc_lpa:g}+ LPA" if j.ctc_lpa else "CTC not listed"
        parts = [j.company, j.location, ROLE_LABELS.get(role_type_of(j), ""), ctc, f"match {j.match_score}"]
        return " \u00b7 ".join(e(str(x)) for x in parts if x)
    rows = "".join(
        f'<div style="border-top:1px solid #eee;padding:14px 0"><a href="{e(j.portal_url)}" style="color:#111827;'
        f'font-weight:600;text-decoration:none">{e(j.role)}</a><div style="color:#6b7280;font-size:13px;margin-top:2px">'
        f'{meta(j)}</div>{btn(decide_url(j.id, "approve"), "Approve", "#15803d", "#ffffff", "#15803d")}'
        f'{btn(decide_url(j.id, "skip"), "Skip", "#ffffff", "#374151", "#d1d5db")}</div>' for j in jobs)
    plural = "s" if len(jobs) != 1 else ""
    return (f'<!doctype html><html><body style="margin:0;background:#f5f5f7;padding:16px 8px">'
            f'<div style="max-width:620px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:16px;'
            f'padding:20px;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#111827">'
            f'<h1 style="margin:0 0 6px;font-size:21px">{len(jobs)} new role{plural} just released</h1>'
            f'<p style="margin:0 0 6px;color:#4b5563;font-size:14px">Approve to get the application link and a ready pack. '
            f'You still submit on the official portal yourself.</p>{rows}'
            f'<p style="margin:22px 0 0;font-size:13px"><a href="{APP_URL}#/job-radar" style="color:#6b7280">Open Job Radar</a>'
            f'</p></div></body></html>')


def alert_text(jobs):
    from api.domain.job_approvals import decide_url
    lines = [f"{len(jobs)} new role(s) released"]
    for j in jobs:
        lines += ["", f"{j.role} - {j.company} ({j.location})", f"Approve: {decide_url(j.id, 'approve')}",
                  f"Skip: {decide_url(j.id, 'skip')}"]
    return "\n".join(lines)


def send_new_role_alert(jobs):
    """One email per scan listing every qualifying new role. Returns True when sent."""
    sender, password = os.getenv("SENDER_EMAIL"), os.getenv("SENDER_PASSWORD")
    if not jobs or not (sender and password):
        return False
    from api.core.clients import EmailClient
    return bool(EmailClient(sender, password).send_email(RECEIVER_EMAIL, alert_subject(jobs), alert_text(jobs),
                                                          html=alert_html(jobs)))


# ---------------- routes ----------------
job_sources_bp = Blueprint("job_sources", __name__, url_prefix="/api/jobs")


def _note_field(notes, pattern):
    m = re.search(pattern, notes or "")
    return m.group(1).strip() if m else None


def _serialize(j):
    try:
        skills = json.loads(j.skills_required or "[]")
    except ValueError:
        skills = []
    return {"id": j.id, "company": j.company, "role": j.role, "location": j.location, "source": j.source,
            "url": j.portal_url, "match_score": j.match_score, "skills": skills, "status": j.status, "notes": j.notes,
            "ctc_lpa": j.ctc_lpa or None, "est_ctc": _note_field(j.notes, r"est\. CTC ([^;]+)"),
            "posted": _note_field(j.notes, r"posted (\d{4}-\d{2}-\d{2})"), "board": getattr(j, "board", None),
            "role_type": role_type_of(j),
            "discovered_at": j.discovered_at.isoformat() + "Z" if j.discovered_at else None}


def _recent(stamp, gap, now):
    try:
        return bool(stamp) and now - datetime.fromisoformat(stamp) < gap
    except ValueError:
        return False


def _undigested(db, last_digest, new):
    """Live jobs discovered since the last digest (so scans skipped by DIGEST_GAP still get emailed later)."""
    if not last_digest:
        return new
    from api.domain.job_radar import JobOpportunity
    try:
        since = datetime.fromisoformat(last_digest).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return new
    return (db.query(JobOpportunity).filter(JobOpportunity.source.like("%(live)"), JobOpportunity.discovered_at > since,
                                            JobOpportunity.status == "discovered").all())


@job_sources_bp.route("/scan", methods=["POST"])
def scan_route():
    from api.domain.repositories import NotificationRepository
    db = SessionLocal()
    try:
        repo = NotificationRepository(db)
        now = datetime.now(timezone.utc)
        previous = repo.get_setting(LAST_SCAN_KEY)
        if _recent(previous, SCAN_GAP, now):
            return jsonify({"status": "skipped", "message": "Scanned recently."})
        repo.set_setting(LAST_SCAN_KEY, now.isoformat())  # claim the slot first so concurrent POSTs don't double-scan
        try:
            scored, errors = collect()
            new = upsert(db, scored)
        except Exception as e:
            # A failed scan must not use up the 5-hour slot: give it back so the next run retries.
            db.rollback()
            repo.set_setting(LAST_SCAN_KEY, previous or "2000-01-01T00:00:00+00:00")
            return jsonify({"status": "error", "message": f"Scan failed: {str(e)[:300]}"}), 500
        alerts = select_alerts(new)
        alerted = send_new_role_alert(alerts) if alerts else False
        emailed = False
        last_digest = repo.get_setting(LAST_DIGEST_KEY)
        if not _recent(last_digest, DIGEST_GAP, now):
            emailed = send_digest(_undigested(db, last_digest, new))
            if emailed:
                repo.set_setting(LAST_DIGEST_KEY, now.isoformat())
        return jsonify({"status": "success", "data": {"found": len(scored), "new": len(new), "emailed": bool(emailed),
                                                      "alerted": len(alerts) if alerted else 0, "errors": errors}})
    finally:
        db.close()


@job_sources_bp.route("/live", methods=["GET"])
def live_route():
    from api.domain.job_radar import JobOpportunity
    try:
        min_score = int(request.args.get("min_score", 0))
    except ValueError:
        min_score = 0
    try:
        min_ctc = float(request.args.get("min_ctc", 0))
    except ValueError:
        min_ctc = 0.0
    strict = request.args.get("strict_ctc", "0").lower() in ("1", "true", "yes")
    role_types = [r for r in (request.args.get("role_type") or "").replace(" ", "").split(",") if r in ROLE_LABELS]
    db = SessionLocal()
    try:
        q = db.query(JobOpportunity).filter(JobOpportunity.source.like("%(live)"), JobOpportunity.match_score >= min_score)
        if min_ctc > 0:  # unknown CTC (0/NULL) is kept unless strict_ctc=1
            known_ok = JobOpportunity.ctc_lpa >= min_ctc
            q = q.filter(known_ok if strict else or_(known_ok, JobOpportunity.ctc_lpa.is_(None), JobOpportunity.ctc_lpa == 0))
        if role_types:
            q = q.filter(or_(*[JobOpportunity.notes.like(ROLE_LABELS[r] + "%") for r in role_types]))
        rows = (q.order_by(JobOpportunity.match_score.desc(), JobOpportunity.discovered_at.desc())
                .limit(300).all())
        return jsonify({"status": "success", "data": [_serialize(j) for j in rows]})
    finally:
        db.close()
