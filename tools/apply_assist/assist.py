#!/usr/bin/env python
"""
Apply assist: opens a job application in Chrome on Sai's laptop and fills it from his own data.

Modes (see README.md):
  --setup [--pending]          one-time questionnaire -> answers.yaml (or only the pending questions)
  --pick | --job ID | --next   assist ONE job: fill it, bring the window up, Sai reviews and clicks Submit himself
  --harvest                    open the selected jobs' forms in the background, collect every unanswered required
                               question, write pending_questions.yaml and email Sai the batch (never submits)
  --auto                       dry run over many jobs: fill each, report what would block; never clicks Submit
  --auto --submit              Sai's explicit opt-in: click Submit only on forms filled completely from real data,
                               with no CAPTCHA / login wall; mark applied only after a confirmation page

Ground rules baked into the code:
  * Values come only from answers.yaml, the Job Radar profile, the job's pack and answers Sai typed before
    (learned_answers.yaml). Unknown required fields are left empty and outlined orange.
  * Every click goes through safe_click(), which refuses submit-like elements unless the caller is the explicit
    --submit path. No CAPTCHA solving, no stealth / fingerprint tricks: plain Playwright Chrome.
  * Chrome runs off-screen and minimized; the window only comes up when Sai is needed (or with --visible).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlparse, urlunparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DEFAULT_API = "http://localhost:5050"  # the local app (tools/local_server/serve.py), same database as production
PROD_API = "https://productivity-automations.vercel.app"
START_HINT =r"Start the app first: tools\local_server\start_local.bat"
PROFILE_DIR = HERE / ".profile"
RESUME_PATH = HERE / "resume.pdf"
ANSWERS_PATH = HERE / "answers.yaml"
LEARNED_PATH = HERE / "learned_answers.yaml"
PENDING_PATH = HERE / "pending_questions.yaml"
RUNS_DIR = HERE / "runs"
HOLD_PATH = HERE / "hold.txt"  # companies on hold (site broken etc.), one per line: never applied to until removed

MIN_SCORE, MIN_CTC, ROLE_TYPES = 55, 15.0, ("fte", "intern_6m")
DONE_STATUSES = {"manual_applied", "applied_confirmed", "skipped"}
APPLIED_STATUSES = {"manual_applied", "applied_confirmed"}
DEDUPE_DAYS = 30
GREEN, ORANGE = "#16a34a", "#f59e0b"


def _now():
    return datetime.now(timezone.utc)


def _iso(dt=None):
    return (dt or _now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _s(v):
    """YAML / JSON value -> form text. YAML turns Yes/No into booleans; forms want the words back."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    return str(v).strip()


def _words(s):
    return re.sub(r"[^a-z0-9+#]+", " ", str(s or "").lower()).split()


def _norm(s):
    return " ".join(_words(s))


# =====================================================================================================
# Job selection
# =====================================================================================================
def _ctc_floor(text):
    m = re.search(r"(\d+(?:\.\d+)?)", text or "")
    return float(m.group(1)) if m else 0.0


def ctc_ok(job, min_ctc=MIN_CTC):
    """Unknown CTC is allowed; there is no upper bound."""
    ctc = job.get("ctc_lpa") or _ctc_floor(job.get("est_ctc"))
    return not ctc or ctc >= min_ctc


SENIOR_TITLE = re.compile(r"(?<![a-z])(senior|mgr|avp|principle|officer|sr\.?|lead|staff|principal|manager|director|architect|head of|vp|vice president|ii|iii|iv|sde[- ]?(2|3|ii)|l[4-9]|phd)(?![a-z])", re.I)  # also "Developer_Director_..."


# Sai: "according to my quals only" (B.Tech CSE, software). Hardware / VLSI / non-software titles are skipped.
NOT_MY_FIELD = re.compile(
    r"\b(design verification|logic design|silicon|asic|rtl|physical design|analog|mixed[- ]signal|hardware|vlsi|"
    r"layout|pcb|eda tools?|cad engineer|timing|power analysis|dft|post[- ]silicon|soc|fpga|circuit|"
    r"mechanical|electrical|civil|chemical|manufacturing|process engineer|quality engineer(?!.*(software|automation))|"
    r"(?<!software )design (engineer|evaluation)|evaluation engineer|model[- ]based|transmission|drivetrain|powertrain|"
    r"thermal|hydraulics?|structural engineer|mechatronics|calibration|"
    r"sap|servicenow|salesforce admin|mainframe|cobol|oracle (ebs|apps)|"
    r"sales|marketing|finance|accountant|hr|recruiter|recruitment|talent acquisition|human resources|legal|procurement|buyer|"
    r"technician|field (service|engineer)|commissioning|site engineer|support engineer|help ?desk|"
    r"network (engineer|administrator)|system administrator|it support)\b", re.I)


def fresher_ok(job):
    """Sai is a 2027 fresher: skip roles asking for any experience, batches without 2027, and senior / PhD titles."""
    m = re.search(r"asks for (\d+)\+? years", job.get("notes") or "")
    if m and int(m.group(1)) >= 1:  # Sai: 0 experience is a must
        return False
    t = re.search(r"(\d{1,2})\s*(?:\+|to|-|–)?\s*\d{0,2}\s*(?:yrs?|years?)\b", job.get("role") or "", re.I)
    if t and int(t.group(1)) >= 1:  # "Software Engineer - Java |8 to 14yrs|"
        return False
    batches = _s(job.get("eligible_batches"))
    if batches and "2027" not in batches:
        return False
    if NOT_MY_FIELD.search(job.get("role") or ""):
        return False
    if other_campus(job.get("role")):
        return False
    return not SENIOR_TITLE.search(job.get("role") or "")


# Sai is at NIT Rourkela: "Campus Graduate Program - IIT BHU" style roles are another college's on-campus drive.
COLLEGE = re.compile(r"\b(IITs?|IIITs?|IISc|BITS|NITs?|DTU|NSUT|VIT|IIMs?|ISI|IIEST|campus)\b", re.I)
MY_COLLEGE = re.compile(r"rourkela|nitr\b", re.I)


def other_campus(role):
    """True when the title names a college drive that isn't NIT Rourkela (a bare "Campus Hire" is fine)."""
    role = role or ""
    names = [m.group(1).lower() for m in COLLEGE.finditer(role)]
    return any(n != "campus" for n in names) and not MY_COLLEGE.search(role)


# Sai: "give priority to top companies". Tier 1 first, then tier 2, then everyone else; inside a tier the best resume
# match first, then the newest posting.
TOP_TIER_1 = re.compile(r"\b(google|microsoft|apple|amazon|meta|nvidia|adobe|atlassian|uber|linkedin|salesforce|netflix|"
                        r"stripe|databricks|snowflake|rubrik|cohesity|nutanix|palo alto|zscaler|servicenow|intuit|"
                        r"goldman|morgan stanley|jp ?morgan|de shaw|d\. ?e\. ?shaw|tower research|graviton|quadeye|optiver|"
                        r"jane street|citadel|squarepoint|worldquant|imc|alphagrep|qualcomm|samsung|oracle|sap|vmware|"
                        r"broadcom|cisco|intel|amd|arista|texas instruments|visa|mastercard|american express|amex|"
                        r"walmart|flipkart|phonepe|razorpay|cred|zomato|swiggy|meesho|groww|zepto|sprinklr|"
                        r"rippling|postman|browserstack|media\.net|blackrock|arcesium|trexquant)\b", re.I)
TOP_TIER_2 = re.compile(r"\b(micron|kla|lseg|deutsche bank|barclays|citi|hsbc|ubs|nomura|bny|state street|wells fargo|"
                        r"paypal|expedia|booking|agoda|target|lowe'?s|honeywell|siemens|bosch|philips|caterpillar|"
                        r"hp|hpe|hewlett|dell|netapp|synopsys|cadence|marvell|nxp|analog devices|western digital|"
                        r"devrev|freshworks|zoho|chargebee|juspay|zeta|cars24|meesho|dream11|myntra|nykaa|"
                        r"godaddy|akamai|autodesk|workday|okta|twilio|mongodb|confluent|wolters kluwer|kyndryl)\b", re.I)


def company_tier(company):
    c = company or ""
    return 0 if TOP_TIER_1.search(c) else 1 if TOP_TIER_2.search(c) else 2


def select_jobs(jobs, min_score=MIN_SCORE, min_ctc=MIN_CTC, role_types=ROLE_TYPES):
    """Open jobs worth applying to: top companies first (company_tier), then best resume match, then newest."""
    keep = [j for j in jobs
            if (j.get("status") or "discovered") not in DONE_STATUSES and j.get("url")
            and j.get("role_type") in role_types and (j.get("match_score") or 0) >= min_score and ctc_ok(j, min_ctc)
            and fresher_ok(j)]
    keep.sort(key=lambda j: (j.get("posted") or (j.get("discovered_at") or "")[:10], j.get("discovered_at") or ""),
              reverse=True)  # newest first inside equal tier and match (stable sorts)
    keep.sort(key=lambda j: j.get("match_score") or 0, reverse=True)
    keep.sort(key=lambda j: company_tier(j.get("company")))
    return keep


def filter_boards(jobs, boards=None):
    """Keep only jobs on these ATS boards (comma-separated, e.g. 'greenhouse,lever,ashby'); None keeps all."""
    wanted = {b.strip().lower() for b in (boards or "").split(",") if b.strip()}
    return [j for j in jobs if (j.get("board") or "").lower() in wanted] if wanted else list(jobs)


def role_key(company, role):
    return f"{_norm(company)}|{_norm(role)}"


def _parse_ts(s):
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def recent_role_keys(history, now=None, days=DEDUPE_DAYS):
    """history: [{company, role, ts}] of submitted applications -> keys submitted within `days`."""
    now = now or _now()
    out = set()
    for h in history:
        ts = _parse_ts(h.get("ts"))
        if ts is None or now - ts <= timedelta(days=days):
            out.add(role_key(h.get("company"), h.get("role")))
    return out


def dedupe(jobs, done_keys=()):
    """Drop company+role pairs already applied to (recently) and repeats inside this list (first one wins)."""
    seen, out = set(done_keys), []
    for j in jobs:
        k = role_key(j.get("company"), j.get("role"))
        if k in seen:
            continue
        seen.add(k)
        out.append(j)
    return out


# Avature career sites (Siemens, Siemens Energy) send applicants to a sign-in / register page first.
AVATURE_LOGIN = re.compile(r"/(Login|Register)\?folderId(Pending)?=", re.I)

# Outcomes worth one more try at the end of a run: the page, not the form, was the problem.
TRANSIENT = re.compile(r"didn't finish loading|Timeout \d+ ?ms exceeded|has been closed|net::ERR_|"
                       r"Couldn't find Save and Continue|Workday sent you a verification email", re.I)


def plan_queue(jobs, max_jobs=25, per_company=1):
    """-> (jobs to work on this run, [(job, reason)] skipped). Keeps list order (newest first)."""
    work, skipped, counts = [], [], {}
    for j in jobs:
        ck = _norm(j.get("company"))
        if len(work) >= max_jobs:
            break
        if counts.get(ck, 0) >= per_company:
            skipped.append((j, f"per-company limit ({per_company}) this run"))
            continue
        counts[ck] = counts.get(ck, 0) + 1
        work.append(j)
    return work, skipped


def local_history(runs_dir=RUNS_DIR):
    out = []
    for log in sorted(Path(runs_dir).glob("*/log.jsonl")):
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("outcome") in ("submitted", "unconfirmed"):
                out.append({"company": e.get("company"), "role": e.get("role"), "ts": e.get("ts"), "id": e.get("job_id"),
                            "url": e.get("url")})
            elif e.get("outcome") == "unmarked":  # Sai said it wasn't really submitted: may be applied to again
                out = [h for h in out if h.get("id") != e.get("job_id")]
    return out


def expired_ids(runs_dir=RUNS_DIR):
    """Job Radar ids whose posting the runner found closed (never tried again)."""
    out = set()
    for log in sorted(Path(runs_dir).glob("*/log.jsonl")):
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("outcome") == "expired" and e.get("job_id") is not None:
                out.add(e["job_id"])
    return out


def server_history(radar_jobs):
    return [{"company": j.get("company"), "role": j.get("role"), "ts": j.get("applied_at"), "id": j.get("id"),
             "url": j.get("portal_url") or j.get("url")}
            for j in radar_jobs or [] if j.get("status") in APPLIED_STATUSES]


def applied_before(job, history, same_role=True):
    """The earlier application to this same posting (same board id, link, Job Radar id or company+role), or None.
    No time limit: a posting already sent (Rubrik Cloud: Azure went three times) is never resent."""
    key, rk = posting_key(job.get("url")), role_key(job.get("company"), job.get("role"))
    for h in history:
        if ((key and key == posting_key(h.get("url"))) or _same_url(job.get("url"), h.get("url"))
                or (job.get("id") is not None and job.get("id") == h.get("id"))
                or (same_role and job.get("role") and rk == role_key(h.get("company"), h.get("role")))):
            return h
    return None


# =====================================================================================================
# Where the application form lives
# =====================================================================================================
def greenhouse_tokens(repo=REPO):
    """Company name (lowercase) -> Greenhouse board token, read from Job Radar's company lists (no import)."""
    out = {}
    for name in ("job_sources.py", "job_companies.py"):
        try:
            text = (Path(repo) / "api" / "domain" / name).read_text(encoding="utf-8")
        except OSError:
            continue
        for company, token in re.findall(r'\(\s*"([^"]+)"\s*,\s*"greenhouse"\s*,\s*"([^"]+)"', text):
            out.setdefault(company.lower(), token)
    return out


ORACLE_CX = re.compile(r"oraclecloud\.com/hcmUI/CandidateExperience|/sites/CX[_\w]*/(job|requisitions)", re.I)  # + vanity domains (Honeywell)


def application_url(url, company=None, gh_tokens=None):
    """Job posting URL -> (URL of the application form, board kind)."""
    u = urlparse(url)
    host, path = u.netloc.lower(), u.path.rstrip("/")
    if host.endswith("lever.co"):
        return urlunparse(u._replace(path=path if path.endswith("/apply") else path + "/apply")), "lever"
    if host.endswith("ashbyhq.com"):
        return urlunparse(u._replace(path=path if path.endswith("/application") else path + "/application")), "ashby"
    if "greenhouse.io" in host:
        return url, "greenhouse"  # the form is on the job page itself
    gh_jid = parse_qs(u.query).get("gh_jid")
    if gh_jid:
        token = (gh_tokens or {}).get((company or "").lower())
        if token:
            return f"https://job-boards.greenhouse.io/embed/job_app?for={quote(token)}&token={quote(gh_jid[0])}", "greenhouse"
    return url, "other"



def posting_key(url):
    """The board's own id for a posting (Greenhouse number / gh_jid, Lever or Ashby UUID), or None."""
    u = urlparse(url or "")
    jid = parse_qs(u.query).get("gh_jid") or (parse_qs(u.query).get("token") if "job_app" in u.path else None)
    if jid:
        return jid[0]
    if "myworkday" in u.netloc.lower():  # .../job/Pune-India/Software-Engineer_R-290463 -> "r-290463"
        m = re.search(r"_([A-Za-z]*-?[0-9][\w-]*)$", u.path.rstrip("/"))
        if m:
            return m.group(1).lower()
    m = re.search(r"/(?:jobs?|jobdetails|job-details)/(\d+)|([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
                  u.path, re.I)  # Keka: /careers/jobdetails/92951
    return (m.group(1) or m.group(2)).lower() if m else None


def _same_url(a, b):
    norm = lambda x: re.sub(r"/+$", "", urlparse(x or "")._replace(query="", fragment="").geturl().lower())  # noqa: E731
    return bool(a and b) and norm(a) == norm(b)


def job_id_for_url(url, jobs):
    """Job Radar's id for a pasted posting link, so the Application desk can record it (None if not tracked)."""
    key = posting_key(url)
    for j in jobs if key else ():
        keys = {posting_key(j.get(f)) for f in ("url", "portal_url", "apply_url")} | {str(j.get("external_id") or "").lower()}
        if j.get("id") and (key in keys or _same_url(url, j.get("portal_url") or j.get("url"))):
            return j["id"]
    return None

# =====================================================================================================
# The click guard. Every click in this file goes through safe_click().
# =====================================================================================================
class SubmitBlocked(RuntimeError):
    pass


SUBMIT_WORDS = re.compile(r"\b(submit|apply|send|finish|complete|confirm)\b", re.I)
APPLY_ENTRY = (r"apply|apply now|apply for this (job|role|position)|apply here|apply online|apply to this job|"
               r"apply manually|start (your )?application|i.?m interested")
ACCOUNT_BUTTONS = r"create account|sign in|sign in with email|log ?in|create (?:a |your )?profile|register"  # Avature: Login / Create profile
WD_BUTTON_IDS = {"Create Account": "createAccountSubmitButton", "Sign In": "signInSubmitButton"}
NEXT_BUTTONS = r"save and continue|next|continue|verify"


def is_submit_like(info):
    t = (info.get("type") or "").lower()
    return t in ("submit", "image") or bool(SUBMIT_WORDS.search(info.get("text") or ""))


def check_click_allowed(info, purpose, submit_enabled=False):
    """Raises SubmitBlocked unless this click is safe. Only the explicit --submit path may press Submit."""
    t = (info.get("type") or "").lower()
    text = (info.get("text") or "").strip()
    if purpose == "submit":
        if submit_enabled:
            return True
        raise SubmitBlocked("Refusing to click Submit: only `--auto --submit` may do that.")
    if purpose == "toggle":
        if t in ("radio", "checkbox"):
            return True
        raise SubmitBlocked(f"Refusing to toggle a non-choice element ({t or info.get('tag')}).")
    if purpose == "open_application":
        # The job page's "Apply" link/button that opens the form: never a submit control, never inside a form.
        # A plain button outside any form (no type attribute: the browser only defaults it to "submit") can't submit.
        plain = t != "submit" or (info.get("tag") == "button" and info.get("typeattr", "submit") == "")
        if plain and not info.get("in_form") and re.fullmatch(rf"\s*({APPLY_ENTRY})\s*", text, re.I):
            return True
        raise SubmitBlocked(f"Refusing to click {text!r}: not a plain 'Apply' entry button.")
    if purpose == "pick_option" and info.get("tag") not in ("button", "input", "a") and (
            info.get("role") == "option" or info.get("wdid") in ("promptOption", "promptLeafNode")):
        return True  # a dropdown option ("Yes, I confirm") can't submit the form
    if purpose == "add_entry":
        # Workday "My Experience": the Add / Add Another button of a section (type=submit, but it only adds a row)
        if info.get("wdid") == "add-button" and re.fullmatch(r"\s*Add( Another)?\s*", text, re.I):
            return True
        raise SubmitBlocked(f"Refusing to click {text or t!r} as an Add button.")
    if purpose == "dismiss" and re.fullmatch(
            r"\s*(accept( all)?( cookies)?|i accept|i agree|agree|ok|okay|got it|close|decline|reject all)\s*", text, re.I):
        return True  # a cookie banner / privacy-notice dialog button (Oracle's ACCEPT is type=submit inside its dialog)
    if purpose == "toggle_label":
        # the visible <label> of a styled checkbox (Oracle's terms box): a label can't submit anything
        if (info.get("tag") or "").lower() == "label":
            return True
        raise SubmitBlocked(f"Refusing to click {text or t!r} as a checkbox label.")
    if purpose == "avature_register":
        # Avature's registration page ("Confirm" creates the candidate profile; the caller checks the /Register URL).
        if re.fullmatch(r"\s*confirm\s*", text, re.I) and info.get("tag") == "button":
            return True
        raise SubmitBlocked(f"Refusing to click {text or t!r} as the Avature registration button.")
    if purpose in ("account", "next_page"):
        # Workday: "Create Account" / "Sign In" and "Save and Continue" / "Next". The label may repeat (text + aria-label).
        words = ACCOUNT_BUTTONS if purpose == "account" else NEXT_BUTTONS
        if re.fullmatch(rf"\s*(?:{words})(?:\s+(?:{words}))*\s*", text, re.I) and not SUBMIT_WORDS.search(text):
            return True
        raise SubmitBlocked(f"Refusing to click {text or t!r} as a {purpose} button.")
    if purpose == "open_dropdown":
        if info.get("haspopup") == "listbox" and t != "submit" and not SUBMIT_WORDS.search(text):
            return True
        if info.get("uxi") == "selectinput" and info.get("tag") == "input" and t == "text":
            return True  # Workday search-select box ("How did you hear about us"): its list opens on a click
        raise SubmitBlocked(f"Refusing to click {text or t!r}: not a dropdown.")
    if is_submit_like(info):
        raise SubmitBlocked(f"Refusing to click {text or t!r}: looks like a submit/apply/send control.")
    return True


ELEMENT_INFO_JS = """(el) => ({
  tag: el.tagName.toLowerCase(), type: (el.type || el.getAttribute('type') || '').toLowerCase(), typeattr: el.getAttribute('type') || '',
  role: (el.getAttribute('role') || '').toLowerCase(), in_form: !!el.closest('form'), href: el.tagName === 'A' ? el.href : '',
  haspopup: (el.getAttribute('aria-haspopup') || '').toLowerCase(), wdid: el.getAttribute('data-automation-id') || '',
  uxi: el.getAttribute('data-uxi-widget-type') || '',
  text: ((el.innerText || '') + ' ' + (el.tagName === 'INPUT' ? (el.value || '') : '') + ' ' + (el.getAttribute('aria-label') || ''))
        .replace(/\\s+/g, ' ').trim().slice(0, 200)})"""


SEARCH_INPUT_JS = """(el) => ({uxi: (el.dataset && el.dataset.uxiWidgetType) || '', in_form: !!el.closest('form'),
  tag: el.tagName.toLowerCase()})"""


def check_enter_allowed(info):
    """Enter can submit a form, so it's only pressed inside a Workday search picker that isn't in a <form>."""
    if info.get("uxi") == "selectinput" and info.get("tag") == "input" and not info.get("in_form"):
        return True
    raise SubmitBlocked("Refusing to press Enter outside a Workday search picker.")


def search_enter(locator):
    """The only place in this file that presses Enter."""
    check_enter_allowed(locator.evaluate(SEARCH_INPUT_JS))
    locator.press("Enter")


def safe_click(locator, purpose, submit_enabled=False, info=None):
    info = info if info is not None else locator.evaluate(ELEMENT_INFO_JS)
    check_click_allowed(info, purpose, submit_enabled)
    if purpose == "toggle":
        try:
            locator.check(timeout=5000)
        except Exception:
            try:
                locator.check(timeout=5000, force=True)
            except Exception:
                pass
        try:
            ok = locator.is_checked(timeout=1000)
        except Exception:
            ok = False
        if not ok:  # Workday's styled radios ignore a programmatic check: click the visible label like a person
            locator.evaluate("""(el) => { const l = (el.labels && el.labels[0]) || el.closest('label') ||
                                 document.querySelector(`label[for="${el.id}"]`); (l || el).click(); }""")
    else:
        try:
            locator.click(timeout=10000)
        except Exception as e:
            if "intercepts pointer events" not in str(e):
                raise
            # Workday lays a transparent click layer over its buttons: click the same spot anyway (already guarded)
            locator.click(timeout=5000, force=True)
    return info


# =====================================================================================================
# Field model: what the page scan returns, and how each field maps to Sai's data
# =====================================================================================================
# field dict: {aid, frame, tag, type, role, label, optlabel, aria, placeholder, name, id, required, value,
#              checked, files, options, in_form}
RULES = [  # (pattern, key) in priority order; matched against label, aria-label, placeholder, name and id
    # Workday "My Experience" entries, by field id (workExperience-4--jobTitle, education-5--degree, ...)
    (r"workexperience-\d+--jobtitle", "we_title"),
    (r"workexperience-\d+--companyname", "we_company"),
    (r"workexperience-\d+--location", "we_location"),
    (r"workexperience-\d+--roledescription", "we_description"),
    (r"workexperience-\d+--startdate-datesectionmonth", "we_start_month"),
    (r"workexperience-\d+--startdate-datesectionyear", "we_start_year"),
    (r"workexperience-\d+--enddate-datesectionmonth", "we_end_month"),
    (r"workexperience-\d+--enddate-datesectionyear", "we_end_year"),
    (r"education-\d+--schoolname", "college"),
    (r"education-\d+--degree", "edu_degree"),
    (r"education-\d+--fieldofstudy", "edu_field"),
    (r"education-\d+--gradeaverage", "cgpa"),
    # "How would you like your personal data used for future recruitment": keep Sai in the talent pool
    (r"personal data to be used|how you would like your personal data|future recruitment (process|opportunit)", "data_use_future"),
    # Standard Workday screening questions (2026-10-19 run)
    (r"submit verification of (both )?your identity|proof of (your )?identity and|identity and (employment )?(eligibility|authori[sz]ation)|"
     r"verification check to validate|validate .{0,40}legal (right|authori[sz]ation)", "identity_docs"),
    (r"positive declaration|i understand that (a|my) (declaration|disclosure)", "accept_privacy_notice"),
    (r"ai-assisted screening|hiredscore|use of (ai|artificial intelligence).{0,40}(screen|assess|tool)", "accept_privacy_notice"),
    (r"citizen of any of the following countries|cuba, iran|north korea, (sudan|syria)", "embargoed_citizen"),
    (r"dual (citizenship|nationality)|(other|another|additional|second|any other|more than one) (citizenship|nationality)|"
     r"citizen(ship)? of (any|another) (other )?country|citizen of any country other than", "other_citizenship"),  # India only
    (r"citizenship|nationality|country of (citizenship|nationality)|citizen of which", "citizenship"),
    (r"employment status|current(ly)? (employment|working)|are you (currently )?(employed|working)", "currently_employed"),
    (r"(currently|previously) .{0,40}(directly )?employed", "previously_employed"),
    (r"issued a .{0,30}(employee id|email address)|employee id or .{0,30}email", "previously_employed"),
    (r"are you a referral|referred by (a|an) (current )?employee|employee referral|"
     r"do you (know|have) (anyone|someone|any (friends?|family|employees?|relatives?)).{0,40}(work|employ|at|from)",
     "is_referral"),  # Sai: "if they ask do you know anyone from the company keep no"
    (r"applying (for|to) (an |a )?(internship|co-?op|intern\b)", "applying_internship"),  # follows the role type
    (r"applying (for|to) (a |an )?full[- ]time", "applying_fulltime"),
    # Sai holds no offers (said many times): every wording of "other offers / offer deadline" is No / None
    (r"(any|other|existing|pending|competing|active|current|outstanding|holding|hold|have)\b.{0,30}\boffers?\b|offers? (in hand|deadline|from (any|other))|recruiting[- ]process deadline|deadline we should be aware", "other_offers"),
    # Before the college rule: "employed by ... government or public institution" is a No, not a school name
    (r"employed by (the )?(federal|any state|.{0,40}government)|government or public institution|public institution", "govt_official"),
    (r"education-\d+--firstyearattended", "edu_start_year"),
    (r"education-\d+--lastyearattended", "edu_end_year"),
    (r"language-\d+--language$", "language_primary"),
    (r"language-\d+--[0-9a-f]{32}$", "language_level"),
    (r"preferred\s*(first\s*)?name|nick\s*name", "preferred_name"),  # only from answers.yaml, never guessed
    (r"first\s*name|given\s*name|_systemfield_first|^first$", "first_name"),
    (r"last\s*name|surname|family\s*name|^last$", "last_name"),
    (r"^(full\s*)?name\s*\*?$|your (full )?name|_systemfield_name|legal name|candidate name|^full name", "full_name"),
    (r"e-?mail", "email"),
    (r"phone device type|device type", "phone_device_type"),
    (r"country phone code|phone (country )?code|dialing code|country code", "phone_country_code"),
    (r"phone extension|^extension\W*$|--extension$", "phone_extension"),  # never filled (Workday's optional box)
    (r"phone|mobile|contact number|whatsapp", "phone"),
    (r"linked\s*in", "linkedin"),
    (r"git\s*hub", "github"),
    (r"leet\s*code", "leetcode"),
    (r"codeforces", "codeforces"),
    (r"portfolio|personal (web)?site|^website|other (link|url)", "portfolio"),
    (r"10th|tenth|class x\b|\bssc\b|secondary school", "class_10"),
    (r"12th|twelfth|class xii|intermediate|higher secondary|\bhsc\b", "class_12"),
    (r"school|university|college|institution", "college"),
    (r"(do|does) (you|your profile) (meet|satisfy|fulfil+)|meet the (minimum|basic|required|stated)|"
     r"(minimum|basic) (qualification|requirement)s? .{0,40}\?", "meets_requirements"),  # P&G: a Yes, not the degree
    (r"degree|qualification|major|discipline|field of study", "degree"),
    (r"grad(uation)?\s*(year|date)|year of (graduation|passing)|class of|\bbatch\b|passing year", "grad_year"),
    (r"cgpa|\bgpa\b|grade point", "cgpa"),
    (r"start date month|start month|from month", "edu_start_month"),
    (r"start date year|start year|from year", "edu_start_year"),
    (r"end date month|end month|to month|graduation month", "edu_end_month"),
    (r"end date year|end year|to year", "edu_end_year"),
    (r"(fluent|spoken|written|speak|read)\b.{0,40}\blanguage|\blanguages?\b.{0,40}\b(fluent|spoken|written|speak)",
     "languages"),
    (r"backlog", "active_backlogs"),
    (r"(dateofbirth|birthdate).*datesectionmonth", "dob_month"),  # Workday splits the date into boxes
    (r"(dateofbirth|birthdate).*datesectionday", "dob_day"),
    (r"(dateofbirth|birthdate).*datesectionyear", "dob_year"),
    (r"date of birth|\bdob\b|birth\s*date", "date_of_birth"),
    (r"pin\s*code|postal code|\bzip\b", "pin_code"),
    (r"address line 1|street address|^street", "address_line1"),
    (r"address line [23]", "address_line2"),  # never filled
    (r"^city\W*$|^town\W*$|addresssection_city|--city$", "address_city"),  # the bare "City" of an address block
    (r"address", "address"),
    (r"expected (ctc|salary|compensation|pay)|salary expectation|desired (salary|compensation)", "expected_ctc"),
    (r"current (ctc|salary|compensation)|present (ctc|salary)", "current_ctc"),
    (r"notice period", "notice_period"),
    # Sai is a student: he can't join before January 2027, so "join immediately / within N days" is always No.
    (r"join (us )?(immediately|right away|asap|now)|immediate(ly)? (join|joining|start)|join within \d+", "join_immediately"),
    (r"^(are|is|will|would|can|could|do) you\b.{0,25}\b(available|able|willing|open|ready) to", "available"),  # yes/no
    (r"earliest (start|joining)|(when|how soon) can you (start|join)|start date|joining date|available to (start|join|commence)|"
     r"expect you to (start|join)|commence work",
     "start_date"),
    (r"relocation (assistance|support|package|benefit)|(require|need) relocation", "relocation_assistance"),
    (r"relocat", "willing_to_relocate"),
    (r"preferred (location|cities|city)|location preference", "preferred_cities"),
    (r"\b(require|need)\b.{0,40}\b(visa|work permit|right to work support)", "needs_sponsorship"),
    (r"(authori[sz]ed|eligible|legally (allowed|permitted)|right|permission) to work|work (permit|authori[sz]ation)",
     "work_authorized_india"),
    (r"sponsor", "needs_sponsorship"),
    (r"how did you (hear|find|learn)|where did you (hear|find|learn)|referral source|source of (application|hire)",
     "how_did_you_hear"),
    (r"pronoun", "pronouns"),
    (r"\bgender\b|\bsex\b", "gender"),
    (r"veteran|disabilit|\brace\b|ethnic|sexual orientation|transgender", "diversity"),
    (r"(work|working) (from|in|at) .{0,30}office|hybrid|on-?site|in-?office", "office_or_hybrid"),
    # Standard screening questions a student applicant answers the same way every time (see AUTO_DEFAULTS).
    (r"(currently|previously|ever|in the past|before)\b.{0,40}\b(work(ed)?|employed|contracted)\b.{0,40}\b(for|by|at|with)\b|"
     r"\b(worked|employed)\b (for|by|at|with)\b.{0,40}\b(previously|before|in the past)\b|"  # "worked for Edwards previously"
     r"former employee|contracted to provide services|employed by .{0,60} in the past", "previously_employed"),
    (r"family members?|relatives?\b|related to (any|an) (current )?employee|personal relationships?", "relatives_at_company"),
    (r"outside (business|employment|activit)|side business|conflicts? of interest", "outside_business"),
    (r"procurement|contract award|government (employee|official)|public official", "govt_official"),
    (r"(at least|over|above) (the age of )?18|18 years (of age|or older)|legal (working )?age", "is_adult"),
    (r"current (employer|company|organi[sz]ation)|name of your current employer|most recent (employer|company)",
     "current_company"),
    (r"current (job )?(title|role|position|designation)", "current_title"),
    (r"\backnowledge|privacy (policy|notice)|\bi (agree|accept|certify|confirm|consent)\b|consent to|agree to", "accept_privacy_notice"),
    (r"\b(available|able|willing|open|ready) to (intern|join|start|work|commit|attend|take)|availability (to|for)", "available"),
    (r"^state\b|state of residence|^province", "state"),
    (r"current (location|city)|^location|\bcity\b|where are you (based|located)|city of residence", "current_city"),
    (r"^country|country of residence|current country", "country"),
    (r"^skills|key skills|technical skills", "skills"),
]
_RULES = [(re.compile(p, re.I), k) for p, k in RULES]
# Work-authorisation answers are about India; a question about another country must stay for Sai.
FOREIGN = re.compile(r"united states|\bu\.s\.|\busa\b|america|united kingdom|\buk\b|britain|canada|europe|\beu\b|"
                     r"singapore|australia|germany|ireland|netherlands|poland|japan|\buae\b|dubai|israel|mexico|brazil", re.I)
DECLINE = ["Prefer not to say", "Decline to self identify", "I don't wish to answer", "Prefer not to answer",
           "I do not want to answer", "Decline to answer"]
CONSENT = re.compile(r"privacy|consent|data protection|gdpr|processing of (my )?(personal )?data|acknowledge|"
                     r"\bi (agree|accept|certify|confirm)\b|agree to|terms (and|&) conditions|confidential", re.I)
# Extra option texts tried after the saved answer, per rule key (dropdowns word these differently on every site).
EXTRA_TARGETS = {
    "other_offers": ["No", "None", "Not applicable", "N/A", "No offers"],
    "citizenship": ["India", "Indian"],
    "currently_employed": ["No", "Student", "Full-time student", "Not employed", "Unemployed"],
    "data_use_future": ["future opportunities", "future recruitment", "future roles", "talent pool", "talent community",
                        "all recruitment", "other positions", "other roles", "keep my data", "Yes", "I agree"],
    "edu_degree": ["Bachelor of Technology", "B.Tech", "BTech", "B. Tech", "Bachelor of Engineering", "B.E.", "BE",
                   "Bachelor's Degree", "Bachelors Degree", "Bachelors", "Bachelor's", "Bachelor", "Undergraduate"],
    "edu_field": ["Computer Science and Engineering", "Computer Science", "Computer Engineering",
                  "Computer and Information Science", "Information Technology"],
    "language_primary": ["English"],
    "language_level": ["Fluent", "Advanced", "Native", "Proficient", "Full Professional", "Expert", "Excellent"],
    "accept_privacy_notice": ["I agree", "I acknowledge", "I accept", "I consent", "Agree", "Acknowledge",
                              "Acknowledged", "Accept", "I have read", "Yes"],  # "Yes" last: Yes/No acknowledgements
    "how_did_you_hear": ["Company website", "Company careers page", "Careers page", "Careers site", "Career site",
                         "Website", "Job board", "Online job board", "LinkedIn", "Other"],
    "notice_period": ["Not applicable", "N/A", "None", "No notice period", "0 days", "Less than 15 days"],  # never "Immediate"
    "current_ctc": ["Not applicable", "N/A", "0"],
    "phone_country_code": ["India (+91)", "India", "+91"],
    "current_company": ["Student", "None", "Not applicable", "N/A", "Not currently employed", "Other"],
    "current_title": ["Student", "Not applicable", "N/A", "Other"],
    "degree": ["Bachelor of Technology", "B.Tech", "Bachelor's Degree", "Bachelor's", "Bachelors", "Bachelor of Engineering",
               "Bachelor"],
    "college": ["National Institute of Technology Rourkela", "NIT Rourkela", "National Institute of Technology", "Other"],
    "languages": ["Hindi", "Telugu"],
    "phone_device_type": ["Mobile", "Mobile Phone", "Personal Mobile", "Pers Mobile", "Mobile (Personal)", "Cell", "Cell Phone"],
}
DECLINE_KEYS = ("gender", "pronouns", "diversity")  # unanswered -> pick a decline option if the field offers one
RESUME_FIELD = re.compile(r"resume|\bcv\b|curriculum", re.I)
COVER_FIELD = re.compile(r"cover", re.I)
# "Import your profile from resume" (Oracle): re-reads the resume and overwrites the saved profile - never use it
IMPORT_FIELD = re.compile(r"import (your )?profile|^apply with$|autofill (with|from) (your )?resume", re.I)
PLACEHOLDER_OPT = re.compile(r"^(|select\b.*|choose\b.*|please select.*|-+.*|none selected|\.\.\.)$", re.I)

PACK_RULES = [
    (re.compile(r"cover letter|cover note|additional information|anything else|message to the (hiring|recruit)", re.I), "cover_note"),
    (re.compile(r"why .*(join|work (at|for|with)|company|\bus\b|interested in (joining|working))", re.I), "why_company"),
    (re.compile(r"why .*(role|position|job|opportunity)|interest(ed)? in this (role|position)", re.I),
     "Why are you interested in this role?"),
    (re.compile(r"challenging|difficult (project|problem)|project you (worked|are proud)", re.I),
     "Describe a challenging project you worked on."),
    (re.compile(r"strongest|technical skill", re.I), "What is your strongest technical skill?"),
]


def field_bits(f):
    return [b for b in (f.get("label"), f.get("aria"), f.get("placeholder"), f.get("name"), f.get("id")) if b]


def question_text(f):
    for b in (f.get("label"), f.get("aria"), f.get("placeholder"), f.get("name")):
        if b and b.strip():
            return re.sub(r"\s+", " ", b).strip()
    return f.get("type") or "field"


def rule_key(f):
    bits = field_bits(f)
    whole = " ".join(bits)
    for rx, key in _RULES:
        if any(rx.search(b.strip()) for b in bits):
            if key in ("work_authorized_india", "needs_sponsorship") and FOREIGN.search(whole) and not re.search(r"india", whole, re.I):
                return None
            return key
    return {"email": "email", "tel": "phone"}.get(f.get("type"))


def is_required(f):
    label = f.get("label") or ""
    return bool(f.get("required")) or "*" in label or "(required)" in label.lower()


def has_value(f):
    t = f.get("type")
    if t == "file":
        return (f.get("files") or 0) > 0
    if t in ("radio", "checkbox"):
        return bool(f.get("checked"))
    return bool(_s(f.get("value")))


def pick_form_fields(fields):
    """When the page has a real <form>, ignore stray inputs outside it (site search boxes, filters)."""
    in_form = [f for f in fields if f.get("in_form")]
    return in_form if len(in_form) >= 3 else list(fields)


def _groups(fields):
    groups = {}
    for f in fields:
        if f.get("type") in ("radio", "checkbox"):
            groups.setdefault((f.get("frame", 0), f.get("name") or f.get("aid")), []).append(f)
    return groups


def missing_required(fields):
    """Labels of required fields that are still empty (radio/checkbox groups count once)."""
    out = []
    for f in fields:
        if f.get("type") not in ("radio", "checkbox") and is_required(f) and not has_value(f):
            out.append(question_text(f))
    for g in _groups(fields).values():
        if any(is_required(x) for x in g) and not any(x.get("checked") for x in g):
            out.append(question_text(g[0]))
    return list(dict.fromkeys(out))


def _sub(small, big):
    n = len(small)
    return any(big[i:i + n] == small for i in range(len(big) - n + 1))


def choice_targets(value):
    v = _s(value)
    if not v:
        return []
    if _norm(v) in {_norm(d) for d in DECLINE}:
        return [v] + [d for d in DECLINE if _norm(d) != _norm(v)]
    return [v]


def option_match(options, wanted, strict=False):
    """Index of the option that matches the answer, or None. strict=True: exact text only (learned answers).
    With several targets, an earlier target beats a later one of the same match quality."""
    targets = [t for t in ([wanted] if isinstance(wanted, str) else list(wanted or [])) if _s(t)]
    best, best_s = None, (0, 0)
    for i, opt in enumerate(options):
        if PLACEHOLDER_OPT.match((opt or "").strip()):
            continue
        o = _words(opt)
        if not o:
            continue
        for ti, t in enumerate(targets):
            w = _words(t)
            if not w:
                continue
            if o == w:
                s = 1000
            elif strict:
                continue
            elif o[:len(w)] == w:
                s = 500 + len(w)  # "Yes, I am authorised" for "Yes"
            elif len(o) >= 2 and _sub(o, w):
                s = 100 + len(o)  # "Bachelor of Technology" inside the saved degree
            else:
                continue
            if (s, -ti) > best_s:
                best, best_s = i, (s, -ti)
    return best


def targets_for(key, value, strict=False):
    """Option texts to look for: the answer itself, then the rule key's usual wordings (not for Sai's exact answers)."""
    out = choice_targets(value)
    if strict:
        return out
    if key in DECLINE_KEYS and not out:
        return list(DECLINE)
    if key == "accept_privacy_notice" and _norm(value) != "yes":
        return out  # Sai opted out: never tick or pick "I agree"
    if key == "start_date":  # Stripe offers quarters: "May 2027" -> "Q2 2027 (April - June)"
        m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(20\d\d)", _s(value), re.I)
        if m:
            q = "Q%d %s" % ((["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
                             .index(m.group(1).lower()) // 3) + 1, m.group(2))
            out = out + [q] if q not in out else out
    return out + [t for t in EXTRA_TARGETS.get(key, []) if t not in out] if out else out


def combo_terms(value):
    """What to type into a search-as-you-type dropdown, most specific first."""
    v = _s(value)
    stripped = re.sub(r"\s*\([^)]*\)", "", v).strip()
    inner = re.findall(r"\(([^)]+)\)", v)
    words = [w for w in re.findall(r"[A-Za-z]{4,}", stripped)]
    return list(dict.fromkeys([t for t in [v, stripped, *inner, words[-1] if words else ""] if t]))


# =====================================================================================================
# Question bank (answers.yaml `questions`, learned_answers.yaml, pending_questions.yaml share it)
# =====================================================================================================
SENSITIVE_LABEL = re.compile(r"password|passcode|\botp\b|one[- ]time|verification|\bcode\b|captcha|\bcard\b|cvv|\bpin\b", re.I)
SENSITIVE_TYPES = {"password", "file", "hidden"}
PERSONAL = re.compile(r"phone|mobile|whatsapp|address|street|pin\s*code|postal|\bzip\b|birth|\bdob\b|ctc|salary|"
                      r"compensation|stipend|\bpay\b", re.I)
MAX_LEARN_CHARS = 1000


def norm_question(q):
    q = (q or "").lower().replace("(required)", " ").replace("*", " ")
    return " ".join(re.sub(r"[^a-z0-9+#]+", " ", q).split())


def jaccard(a, b):
    A, B = set(a.split()), set(b.split())
    return len(A & B) / len(A | B) if A | B else 0.0


def is_company_specific(question, company):
    c = norm_question(company)
    return bool(c) and f" {c} " in f" {norm_question(question)} "


def learnable(label, ftype, answer):
    a = _s(answer)
    return bool(a) and len(a) <= MAX_LEARN_CHARS and (ftype or "") not in SENSITIVE_TYPES \
        and not SENSITIVE_LABEL.search(label or "")


class QuestionBank:
    """normalized question -> {question, answer, type, options_seen, company, role, company_specific,
    learned_at, times_used}. Matches exactly or by token overlap (Jaccard >= 0.8)."""

    THRESHOLD = 0.8

    def __init__(self, entries=None):
        self.entries = {k: v for k, v in (entries or {}).items() if isinstance(v, dict)}

    def find(self, question, company=None):
        k = norm_question(question)
        if not k:
            return None, None
        cands = []
        for key, e in self.entries.items():
            if not _s(e.get("answer")):
                continue
            if e.get("company_specific") and norm_question(e.get("company")) != norm_question(company):
                continue  # "Why <company>?" is only reused for that company
            score = 1.0 if key == k else jaccard(key, k)
            if score >= self.THRESHOLD:
                cands.append((key == k, str(e.get("learned_at") or ""), key))
        if not cands:
            return None, None
        cands.sort(reverse=True)  # exact key first, then the most recent answer
        key = cands[0][2]
        return key, self.entries[key]

    def learn(self, question, answer, ftype=None, options=None, company=None, role=None, now=None):
        if not learnable(question, ftype, answer):
            return None
        key = norm_question(question)
        if not key:
            return None
        old = self.entries.get(key) or {}
        entry = {"question": question.strip(), "answer": _s(answer), "type": ftype or "text",
                 "options_seen": list(options or [])[:30], "company": company, "role": role,
                 "company_specific": is_company_specific(question, company),
                 "learned_at": _iso(now), "times_used": int(old.get("times_used") or 0)}
        self.entries[key] = entry
        return key

    def mark_used(self, key):
        if key in self.entries:
            self.entries[key]["times_used"] = int(self.entries[key].get("times_used") or 0) + 1


def load_yaml(path):
    import yaml
    p = Path(path)
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def save_yaml(path, data, header=""):
    import yaml
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=110)
    Path(path).write_text((header + "\n" if header else "") + text, encoding="utf-8")


# =====================================================================================================
# Planning: which value goes into which field (pure, testable)
# =====================================================================================================
@dataclass
class FillContext:
    values: dict
    company: str = ""
    custom: list = field(default_factory=list)
    questions: QuestionBank = field(default_factory=QuestionBank)
    learned: QuestionBank = field(default_factory=QuestionBank)
    pack: dict = field(default_factory=dict)
    resume: bool = False
    used_learned: set = field(default_factory=set)
    ai: object = None  # ai(question, ftype, options, company) -> answer or None; last resort for required fields
    role: str = ""
    ai_used: list = field(default_factory=list)


@dataclass
class Action:
    f: dict
    kind: str  # text | select | combo | toggle | file
    value: object
    source: str
    label: str = ""
    targets: list = field(default_factory=list)  # combo: option texts to accept, best first


@dataclass
class Todo:
    f: dict | None
    label: str
    reason: str
    ftype: str = ""
    options: list = field(default_factory=list)


@dataclass
class Plan:
    actions: list
    todo: list


# What a final-year student applying in India answers on every form. Used only where answers.yaml is blank;
# put a different value (or "No") in answers.yaml to override any of them.
AUTO_DEFAULTS = {
    "country": "India",
    "work_authorized_india": "Yes",
    "needs_sponsorship": "No",
    "willing_to_relocate": "Yes",
    "relocation_assistance": "Yes",  # Sai: "yes require relocation assistance if possible" (2026-10-19)
    "office_or_hybrid": "Yes",
    "available": "Yes",
    "join_immediately": "No",
    "accept_privacy_notice": "Yes",
    "how_did_you_hear": "Company careers website",
    "diversity": "Prefer not to say",
    "current_company": "Student, NIT Rourkela",
    "current_title": "B.Tech student (final year)",
    "previously_employed": "No",
    "relatives_at_company": "No",
    "outside_business": "No",
    "govt_official": "No",
    "is_adult": "Yes",
    "identity_docs": "Yes",
    "embargoed_citizen": "No",
    "other_offers": "None (no offers)",
    "is_referral": "No",
    "citizenship": "India",
    "other_citizenship": "No",
    "meets_requirements": "Yes",
    "currently_employed": "No (full-time student)",
    "active_backlogs": "No",
    "notice_period": "Not applicable (final-year student: internship from January 2027, full-time from May 2027)",
    "data_use_future": "Use my data for future recruitment opportunities too",
    "current_ctc": "0 / Not applicable",
    "expected_ctc": "As per company norms",
    "start_date_fte": "May 2027 (after graduation)",
    "start_date_internship": "January 2027",
    "start_date_winter": "December 2026",
    "address": "NIT Rourkela, Sector 1, Rourkela, Odisha 769008, India",
    "pin_code": "769008",
    "state": "Odisha",
    "phone_device_type": "Mobile",
    "phone_country_code": "India (+91)",
}
ADDRESS_DEFAULT_KEYS = ("pin_code", "state")


def build_values(profile, answers, role_type=None, role=""):
    """Profile (Job Radar) + answers.yaml + AUTO_DEFAULTS -> the values the rules use. answers.yaml wins; phone only
    from answers."""
    p, a = profile or {}, answers or {}
    full = _s(a.get("full_name")) or _s(p.get("full_name"))
    parts = full.split()
    defaults = dict(AUTO_DEFAULTS)
    if _s(a.get("address")):  # Sai's own address: the campus PIN / state no longer belong with it
        for k in ADDRESS_DEFAULT_KEYS:
            defaults.pop(k, None)
    a = {**{k: d for k, d in defaults.items() if not _s(a.get(k))}, **{k: x for k, x in a.items() if _s(x)}}
    v = {k: _s(val) for k, val in a.items() if not isinstance(val, (list, dict))}
    v.update({
        "full_name": full,
        "first_name": _s(a.get("first_name")) or " ".join(parts[:-1]) or full,
        "last_name": _s(a.get("last_name")) or (parts[-1] if len(parts) > 1 else ""),
        "phone": _s(a.get("phone")),
    })
    for key in ("email", "linkedin", "github", "leetcode", "codeforces", "college", "degree", "grad_year", "cgpa"):
        v[key] = _s(a.get(key)) or _s(p.get(key))
    v["current_city"] = _s(a.get("current_city")) or _s(p.get("location")) or _s(p.get("location_pref")).split(",")[0].strip()
    v["preferred_cities"] = _s(a.get("preferred_cities")) or _s(p.get("location_pref"))
    # Sai: winter internships from December 2026, 6-month internships from January 2027, full-time from May 2027
    intern = (role_type or "").startswith("intern") or bool(re.search(r"\bintern(ship)?s?\b", role or "", re.I))
    winter = intern and bool(re.search(r"\bwinter\b", role or "", re.I))
    which = "start_date_winter" if winter else "start_date_internship" if intern else "start_date_fte"
    v["start_date"] = _s(a.get(which)) or _s(AUTO_DEFAULTS.get(which)) or _s(a.get("start_date"))
    v["applying_internship"], v["applying_fulltime"] = ("Yes", "No") if intern else ("No", "Yes")
    # Address blocks split into line 1 / city: default to the whole address and the current city.
    v["address_line1"] = _s(a.get("address_line1")) or _s(v.get("address"))
    v["address_city"] = _s(a.get("address_city")) or v["current_city"]
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", _s(a.get("date_of_birth")))
    if m:  # for forms that split the date into month / day / year boxes
        v["dob_year"], v["dob_month"], v["dob_day"] = m.groups()
    v.pop("workday_password", None)  # passed to the Workday sign-in only, never to a form field or the AI
    v.pop("avature_password", None)
    return {k: val for k, val in v.items() if val}


def national_number(phone):
    """'+91 91103 07856' -> '9110307856' (for forms with a separate country-code dropdown)."""
    digits = re.sub(r"\D", "", phone or "")
    # only a real country code comes off: "9110307856" is already the 10-digit number (it just starts with 91)
    return digits[2:] if len(digits) == 12 and digits.startswith("91") else digits


def pack_answer(text, pack, company=""):
    if not pack:
        return None
    if company and re.search(rf"why\b.*\b{re.escape(company)}\b", text, re.I) and pack.get("why_company"):
        return pack["why_company"]
    qa = {a.get("question"): a.get("answer") for a in pack.get("answers") or [] if isinstance(a, dict)}
    for rx, key in PACK_RULES:
        if rx.search(text):
            val = pack.get(key) or qa.get(key)
            if val:
                return val
    return None


def resolve(f, fc, choice=False):
    """(value, source) for one field: answers.yaml custom/questions -> rules (answers.yaml over profile) ->
    learned answers -> the job's pack (free-text fields only). (None, None) = leave it for Sai."""
    text = question_text(f)
    for c in fc.custom or []:
        try:
            if isinstance(c, dict) and _s(c.get("answer")) and re.search(str(c.get("match")), text, re.I):
                return _s(c["answer"]), "custom"
        except re.error:
            continue
    _key, e = fc.questions.find(text, fc.company)
    if e:
        return _s(e["answer"]), "question"
    key = rule_key(f)
    if key and fc.values.get(key):
        return fc.values[key], "profile"
    lkey, e = fc.learned.find(text, fc.company)
    if e:
        fc.used_learned.add(lkey)
        return _s(e["answer"]), "learned"
    long_text = f.get("type") == "textarea" or (f.get("type") == "text" and len(text.split()) >= 4 and "?" in text)
    if not choice and long_text:
        val = pack_answer(text, fc.pack, fc.company)
        if val:
            return val, "pack"
    return None, None


def _ask_ai(fc, label, ftype, options):
    """Last resort for a required field nothing else answers. Returns the answer or None."""
    if not fc.ai or SENSITIVE_LABEL.search(label):
        return None
    try:
        ans = _s(fc.ai(label, ftype, [o for o in options or [] if not PLACEHOLDER_OPT.match((o or "").strip())],
                       fc.company, fc.role))
    except Exception as e:
        print(f"  (AI could not answer {label[:50]!r}: {str(e)[:80]})")
        return None
    if ans:
        fc.ai_used.append({"question": label, "answer": ans})
    return ans or None


def stale_contact_fix(f, fc, has_code=False):
    """For Sai's own contact boxes only: the value to replace a wrong saved one with ("" clears it), else None.
    Workday keeps drafts, so an earlier wrong fill (whole address in City, phone in Extension) would stick."""
    key, cur = rule_key(f), _s(f.get("value"))
    if key == "phone_extension":
        return "" if cur else None
    if key not in ("address_city", "address_line1", "pin_code", "phone"):
        return None
    want = _s(fc.values.get(key))
    if not want:
        return None
    if key == "phone":
        if has_code:
            want = national_number(want)
        digits = re.sub(r"\D", "", cur)
        return None if digits.lstrip("0").endswith(re.sub(r"\D", "", want).lstrip("0")[-10:]) else want
    return None if _norm(cur) == _norm(want) else want


# Last resort for required Yes/No-style questions when no rule, saved answer or AI fits (Sai: "make it take rational
# decisions"). A final-year student with no work history: never employed/contracted/related/sanctioned -> No;
# agreements, consents, certifications and eligibility -> Yes.
HEUR_NO = re.compile(r"\b(ever|previously|formerly|currently)\b.{0,60}\b(employ|work|contract|intern|consult)|related to|relative|family member|"
                     r"government (official|employee)|public official|sanction|debar|convicted|non-?compet|non-?solicit|"
                     r"conflict of interest|intellectual property|economic interest|own,? control|export control|citizen of any of|"
                     r"require (visa|sponsorship)|sponsorship", re.I)
HEUR_YES = re.compile(r"\bi (agree|acknowledge|understand|certify|confirm|consent|accept)\b|do you (agree|consent|acknowledge|accept)|"
                      r"agree to|consent to|certify that|true and complete|at least 18", re.I)
# (work authorisation is NOT guessed here: "authorized to work in the United States" is No for Sai - its own rule decides)


def heuristic_answer(question):
    q = question or ""
    if HEUR_NO.search(q):
        return "No"
    if HEUR_YES.search(q):
        return "Yes"
    return None


YEARS_REQ = re.compile(r"(?:minimum|min\.?|at least)?\s*(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*\d{1,2}\s*\+?)?\s*(?:years?|yrs?)\b"
                       r"[^.\n]{0,40}?(?:experience|\bexp\b|industry|professional|relevant|working)", re.I)
HIGHER_DEGREE_REQ = re.compile(r"(master'?s|\bm\.?tech\b|\bm\.?s\.?\b|ph\.?d)[^.\n]{0,60}\b(required|mandatory|must)", re.I)
# "6 months of experience", "at least 3 months work experience" (not "6-month internship")
MONTHS_REQ = re.compile(r"(?:minimum|min.?|at least)?\s*(\d{1,2})\s*\+?\s*months?\s+(?:of\s+)?(?:(?:professional|work|industry|relevant|hands-on)\s+)?(?:work\s+)?experience", re.I)
OTHER_BATCH = re.compile(r"\b(202[3-6])\s*(?:batch|graduates?|pass(?:ed)?[- ]?outs?)\b", re.I)
FORM_QUESTION = re.compile(r"[^.?!\n]*\?", re.I)  # any sentence ending in "?"


def min_quals_problem(text):
    """Why a 2027 B.Tech fresher should not apply, from the posting text; None when nothing rules him out."""
    # Form questions on the same page ("Do you have over 2 years of industry experience?") aren't requirements
    t = FORM_QUESTION.sub(" ", text or "")
    def ceiling(m):  # "no more than 18 months of experience" is a maximum (Stripe new grad), not a requirement
        return re.search(r"(?:no|not) more than|less than|fewer than|up to|at most|maximum(?: of)?|max\.?\s*$",
                         t[max(0, m.start(1) - 25):m.start(1)].strip(), re.I) is not None
    years = [int(m.group(1)) for m in YEARS_REQ.finditer(t) if 0 <= int(m.group(1)) <= 15 and not ceiling(m)]
    if years and min(years) >= 1:  # Sai: 0 experience is a must ("0-1 years" / "0 to 2 years" still pass)
        return f"asks for {min(years)}+ years of experience"
    months = [int(m.group(1)) for m in MONTHS_REQ.finditer(t) if 3 <= int(m.group(1)) <= 36 and not ceiling(m)
              and not re.search(r"\d\s*(?:-|–|to)\s*$", t[max(0, m.start(1) - 6):m.start(1)])]  # "0-6 months"
    if months:
        return f"asks for {min(months)}+ months of work experience"
    m = HIGHER_DEGREE_REQ.search(t)
    if m and not re.search(r"bachelor|b\.?tech|b\.?e\b", m.group(0), re.I):
        return "requires a higher degree (" + m.group(1) + ")"
    if OTHER_BATCH.search(t) and "2027" not in t:
        return "only for the " + OTHER_BATCH.search(t).group(1) + " batch"
    m = ONLY_CAMPUS.search(t)
    if m and not MY_COLLEGE.search(m.group(0)):
        return "on-campus drive for another college (" + m.group(1) + ")"
    return None


# "open only to students of IIT Kanpur", "eligible: candidates from IIT BHU only"
ONLY_CAMPUS = re.compile(r"only (?:open )?(?:to|for) (?:current )?(?:students|candidates|graduates)[^.\n]{0,20}?"
                         r"\b(?:of|from|at) ((?:IITs?|IIITs?|IISc|BITS|NITs?)\b[^.,;\n]{0,30})", re.I)


def plan_fields(fields, fc):
    actions, todo = [], []
    files = [f for f in fields if f.get("type") == "file"]
    has_code = any(rule_key(x) == "phone_country_code" for x in fields)
    for f in fields:
        t, label = f.get("type"), question_text(f)
        if t in ("radio", "checkbox"):
            continue
        if t == "file":
            desc = " ".join(field_bits(f))
            if any(IMPORT_FIELD.search(b.strip()) for b in field_bits(f)):
                continue
            is_resume = RESUME_FIELD.search(desc) or (len(files) == 1 and not COVER_FIELD.search(desc))
            if has_value(f):
                continue
            if is_resume and fc.resume:
                actions.append(Action(f, "file", None, "resume", label))
            elif is_required(f):
                todo.append(Todo(f, label, "upload" if not is_resume else "resume not available", "file"))
            continue
        is_combo = f.get("role") in ("combobox", "listbox")
        if has_value(f):
            fix = None if is_combo or t == "select" else stale_contact_fix(f, fc, has_code)
            if fix is not None:  # a saved Workday draft with an old/wrong contact value: correct it
                actions.append(Action(f, "text", fix, "profile", label))
            continue  # otherwise never overwrite what's already there
        val, src = resolve(f, fc, choice=t == "select" or is_combo)
        if val and t == "number":  # number-only boxes: "0 / Not applicable" -> "0"; no leading number -> leave it
            m = re.match(r"\s*(\d+(?:\.\d+)?)", str(val))
            val = m.group(1) if m else None
        if val and src == "profile" and has_code and rule_key(f) == "phone":
            val = national_number(val)
        strict = src in ("question", "learned")
        targets = targets_for(rule_key(f), val, strict=strict)
        src = src or ("default" if targets else None)  # e.g. "Decline to self-identify"
        for attempt in (1, 2):
            if t == "select":
                idx = option_match(f.get("options") or [], targets, strict=strict) if targets else None
                if idx is not None:
                    actions.append(Action(f, "select", idx, src, label))
                    break
            elif is_combo:
                if targets:
                    actions.append(Action(f, "combo", val or targets[0], src, label, targets))
                    break
            elif val:
                actions.append(Action(f, "text", val, src, label))
                break
            if attempt == 1 and is_required(f) and not val:
                val = _ask_ai(fc, label, "select" if is_combo else t, f.get("options") or [])
                src = "ai"
                if not val and (is_combo or t == "select"):  # AI unavailable: the sensible answer for a student
                    val, src = heuristic_answer(label), "rule-of-thumb"
                targets, strict = choice_targets(val), False
                if val:
                    continue
            if is_required(f):
                todo.append(Todo(f, label, "no saved answer" if not val else f"no option matches {val!r}", t,
                                 list(f.get("options") or [])))
            break
    for g in _groups(fields).values():
        if any(x.get("checked") for x in g):
            continue
        q = question_text(g[0])
        required = any(is_required(x) for x in g)
        opts = [x.get("optlabel") or _s(x.get("value")) for x in g]
        if g[0].get("type") == "checkbox" and len(g) == 1:
            if CONSENT.search(q + " " + opts[0]) and fc.values.get("accept_privacy_notice") == "Yes":
                actions.append(Action(g[0], "toggle", True, "consent", q))
            elif required:
                todo.append(Todo(g[0], q, "needs your tick", "checkbox", opts))
            continue
        val, src = resolve(g[0], fc, choice=True)
        strict = src in ("question", "learned")
        idx = option_match(opts, targets_for(rule_key(g[0]), val, strict=strict), strict=strict)
        if idx is None and required and not val:
            val, src = _ask_ai(fc, q, g[0].get("type"), opts), "ai"
            if not val:  # AI unavailable: the sensible answer for a student
                val, src = heuristic_answer(q), "rule-of-thumb"
            idx = option_match(opts, choice_targets(val)) if val else None
        if idx is not None:
            actions.append(Action(g[idx], "toggle", True, src or "default", q))
        elif required:
            todo.append(Todo(g[0], q, "no saved answer" if not val else f"no option matches {val!r}",
                             g[0].get("type"), opts))
    return Plan(actions, todo)


def tracked_from_todo(todo):
    """The unanswered questions we read back after Sai fills them (for learning)."""
    out = []
    for t in todo:
        if t.f is None or not learnable(t.label, t.ftype, "x"):
            continue
        out.append({"key": norm_question(t.label), "question": t.label, "type": t.ftype, "options": t.options,
                    "name": (t.f or {}).get("name")})
    return out


def read_answers(fields, tracked):
    """What Sai entered for the tracked questions: {key: {question, answer, type, options}}."""
    out = {}
    groups = _groups(fields)
    for tr in tracked:
        answer = ""
        if tr["type"] in ("radio", "checkbox"):
            for g in groups.values():
                if norm_question(question_text(g[0])) == tr["key"] or (tr.get("name") and g[0].get("name") == tr["name"]):
                    answer = ", ".join(x.get("optlabel") or _s(x.get("value")) for x in g if x.get("checked"))
                    break
        else:
            for f in fields:
                if f.get("type") not in ("radio", "checkbox") and norm_question(question_text(f)) == tr["key"]:
                    answer = _s(f.get("value"))
                    break
        if answer and learnable(tr["question"], tr["type"], answer):
            out[tr["key"]] = {"question": tr["question"], "answer": answer, "type": tr["type"], "options": tr["options"]}
    return out


# =====================================================================================================
# Page states: blockers and confirmation
# =====================================================================================================
CONFIRM_TEXT = re.compile(
    r"thank(s| you) for (applying|your application|submitting)|application (has been|was) (successfully )?"
    r"(submitted|received)|we('ve| have) received your application|application received|successfully (submitted|applied)|"
    r"your application is (complete|submitted)|application submitted|you('ve| have) (successfully )?applied", re.I)
CONFIRM_URL = re.compile(r"/(thanks|thank-you|thank_you|thankyou|confirmation|confirmed|success|submitted|applied)\b", re.I)
SECURITY_CODE = re.compile(r"security code|verification code|enter the (\d+[- ]character )?code|"
                           r"code (was|has been) sent|sent a code", re.I)
REF = re.compile(r"(?:application|reference|confirmation|candidate)\s*(?:id|number|no\.?|#|code)\s*[:#]?\s*([A-Z0-9][A-Z0-9-]{3,})", re.I)


def detect_confirmation(text, url, start_url=None):
    """(confirmed?, reference or None). Needs a thank-you message, or a URL change to a thanks/confirmation page."""
    ok = bool(CONFIRM_TEXT.search(text or ""))
    if not ok and url and start_url and url != start_url:
        ok = bool(CONFIRM_URL.search(urlparse(url).path or ""))
    m = REF.search(text or "") if ok else None
    return ok, (m.group(1) if m else None)


EXPIRED = re.compile(r"this job (has expired|is no longer (available|accepting))|job (posting )?(has expired|is closed|"
                     r"no longer available)|position (has been filled|is no longer available)|no longer accepting "
                     r"applications|this (position|role|requisition) (has been )?closed|the job you are looking for "
                     r"(is no longer|does not exist)|page you requested was not found|job (posting )?(was )?not found|"
                     r"page you are looking for (doesn't|does not) exist", re.I)


def blockers(state, fields):
    reasons = []
    if state.get("captcha"):
        reasons.append("CAPTCHA on the page")
    if state.get("login"):
        reasons.append("Login or account needed")
    if EXPIRED.search((state.get("text") or "")[:3000]):
        return ["Posting closed (expired or no longer accepting applications)"]
    if "maintenance-page" in (state.get("url") or "") or re.search(
            r"workday is currently unavailable|experiencing a service interruption", state.get("text") or "", re.I):
        reasons.append("Workday is down for maintenance right now: run this job again later")
    elif re.match(r"\s*(access denied|403 forbidden|request blocked)", state.get("text") or "", re.I):
        reasons.append("The site blocked this browser (Access Denied): open the link yourself")
    elif len(fields) < 2 and not state.get("login"):
        reasons.append("No application form found (unknown flow)")
    return reasons


# =====================================================================================================
# One-time setup + pending questions
# =====================================================================================================
KNOWN = {
    "full_name": "Nandam Venkata Sai Raghava",
    "first_name": "Nandam Venkata Sai",
    "last_name": "Raghava",
    "email": "sairaghava1318@gmail.com",
    "college": "National Institute of Technology, Rourkela",
    "degree": "B.Tech, Computer Science and Engineering",
    "grad_year": 2027,
    "cgpa": 8.99,
    "class_12": "97.1% (AP Board of Intermediate Education, 2023)",
    "linkedin": "https://www.linkedin.com/in/nandam-venkata-sai-raghava-946b3735b/",
    "github": "https://github.com/VeratrilS",
    "leetcode": "https://leetcode.com/u/Sairaghava1318/",
    "codeforces": "https://codeforces.com/profile/Raghavan_CP",
    # same list as RESUME_FACTS["skills"] in api/domain/job_pack.py (a test keeps them in sync)
    "skills": "C++, Python, JavaScript, SQL, React, Node.js, Express, Kafka, Redis, Elasticsearch, PostgreSQL, MongoDB",
}
SUGGESTED = {
    "country": "India",
    "current_ctc": "0 / Not applicable",
    "preferred_cities": "Bengaluru, Hyderabad, Gurugram, Remote",
    "how_did_you_hear": "Company careers website",
    "diversity": "Prefer not to say",
}
SETUP_QUESTIONS = [  # (key, prompt, kind) kind: text | yn
    ("full_name", "Full name", "text"),
    ("first_name", "First name as forms should show it", "text"),
    ("last_name", "Last name as forms should show it", "text"),
    ("email", "Email", "text"),
    ("phone", "Phone (10 digits, no +91)", "text"),
    ("college", "College", "text"),
    ("degree", "Degree", "text"),
    ("grad_year", "Graduation year", "text"),
    ("cgpa", "CGPA", "text"),
    ("class_12", "12th: % (board, year)", "text"),
    ("class_10", "10th: % (board, year)", "text"),
    ("active_backlogs", "Any active backlogs?", "yn"),
    ("linkedin", "LinkedIn", "text"),
    ("github", "GitHub", "text"),
    ("leetcode", "LeetCode", "text"),
    ("codeforces", "Codeforces", "text"),
    ("portfolio", "Portfolio / personal website", "text"),
    ("skills", "Skills (comma-separated)", "text"),
    ("current_city", "Current city", "text"),
    ("country", "Country", "text"),
    ("address", "Full address", "text"),
    ("pin_code", "PIN code", "text"),
    ("date_of_birth", "Date of birth (YYYY-MM-DD)", "text"),
    ("gender", "Gender (Male / Female / Non-binary / Prefer not to say)", "text"),
    ("pronouns", "Pronouns (optional)", "text"),
    ("expected_ctc", "Expected CTC", "text"),
    ("current_ctc", "Current CTC", "text"),
    ("notice_period", "Notice period", "text"),
    ("start_date_fte", "Earliest start date for a full-time role", "text"),
    ("start_date_internship", "Earliest start date for an internship", "text"),
    ("willing_to_relocate", "Willing to relocate?", "yn"),
    ("preferred_cities", "Preferred cities", "text"),
    ("work_authorized_india", "Authorised to work in India?", "yn"),
    ("needs_sponsorship", "Need visa sponsorship?", "yn"),
    ("office_or_hybrid", "Willing to work from office / hybrid?", "yn"),
    ("how_did_you_hear", "'How did you hear about us' answer", "text"),
    ("diversity", "Diversity questions (veteran / disability / race / ethnicity)", "text"),
    ("accept_privacy_notice", "Tick required privacy-policy / data-consent checkboxes for you?", "yn"),
]
ANSWERS_HEADER = ("# Sai's application answers (written by `assist.py --setup`; edit freely, never committed).\n"
                  "# Blank = leave that field for me on the form.  `custom`: [{match: <regex>, answer: ...}].\n"
                  "# `questions`: answers from `--setup --pending`, keyed by the normalized question.")


def setup_defaults(existing):
    """Current value per setup question: answers.yaml first, then the known facts, then a suggestion."""
    out = {}
    for key, _prompt, _kind in SETUP_QUESTIONS:
        if key in existing and existing[key] is not None:
            out[key] = existing[key]
        else:
            out[key] = KNOWN.get(key, SUGGESTED.get(key, ""))
    return out


def setup_answer(kind, current, raw):
    """Enter keeps, '-' clears, y/n questions store Yes/No. Returns (value, ok)."""
    raw = (raw or "").strip()
    if raw == "":
        return current, True
    if raw == "-":
        return "", True
    if kind == "yn":
        low = raw.lower()
        if low in ("y", "yes"):
            return "Yes", True
        if low in ("n", "no"):
            return "No", True
        return current, False
    return raw, True


def run_setup(path=ANSWERS_PATH, input_fn=input, out=print):
    existing = load_yaml(path)
    cur = setup_defaults(existing)
    out("Apply assist setup. Enter keeps the value in [brackets], '-' clears it.\n")
    result = dict(existing)
    for key, prompt, kind in SETUP_QUESTIONS:
        shown = _s(cur[key])
        while True:
            val, ok = setup_answer(kind, cur[key], input_fn(f"{prompt}{' (y/n)' if kind == 'yn' else ''} [{shown}]: "))
            if ok:
                break
            out("  Please answer y or n (or Enter to keep).")
        result[key] = val
    result.setdefault("custom", [])
    result.setdefault("questions", {})
    save_yaml(path, result, ANSWERS_HEADER)
    out(f"\nSaved {path}")
    return result


def collect_pending(rows, existing=None):
    """rows: [{job: {id, company, role, url}, missing: [{question, type, options}], blockers: [..]}].
    Dedupe questions across companies (normalized, Jaccard >= 0.8); company-specific ones stay separate."""
    pending = {k: dict(v, jobs=list(v.get("jobs") or [])) for k, v in (existing or {}).items() if isinstance(v, dict)}
    for row in rows:
        job = row["job"]
        ref = {"job_id": job.get("id"), "company": job.get("company"), "role": job.get("role"), "url": job.get("url")}
        for m in row.get("missing") or []:
            q = m.get("question") or ""
            nq = norm_question(q)
            if not nq or SENSITIVE_LABEL.search(q):
                continue
            specific = is_company_specific(q, job.get("company"))
            key = f"{norm_question(job.get('company'))}::{nq}" if specific else nq
            if key not in pending and not specific:
                key = next((k for k in pending if "::" not in k and jaccard(k, nq) >= QuestionBank.THRESHOLD), key)
            e = pending.setdefault(key, {"question": q, "type": m.get("type") or "text", "options": [], "jobs": [],
                                         "company_specific": specific,
                                         "company": job.get("company") if specific else None})
            for o in m.get("options") or []:
                if o and o not in e["options"] and not PLACEHOLDER_OPT.match(o.strip()):
                    e["options"].append(o)
            if specific:
                e["note"] = "Company-specific: usually answerable from the job's pack (why_company)."
            if not any(j.get("job_id") == ref["job_id"] for j in e["jobs"]):
                e["jobs"].append(ref)
    for e in pending.values():
        e["blocks"] = len(e["jobs"])
    return dict(sorted(pending.items(), key=lambda kv: -kv[1]["blocks"]))


def unblockable_jobs(rows):
    """Jobs held up only by unanswered questions (no CAPTCHA / login / unknown flow)."""
    return [r["job"] for r in rows if r.get("missing") and not r.get("blockers")]


def compose_pending_email(pending, unblock_count):
    subject = f"Answer these once: {len(pending)} questions (unblocks {unblock_count} applications)"
    lines = ["These required questions are holding up applications. Answer them once and the runner fills them",
             "from then on.", "",
             "Reply to this email with your answers (question number + answer, e.g. '2. 15 LPA'), or run:",
             "  python tools/apply_assist/assist.py --setup --pending", ""]
    for i, e in enumerate(pending.values(), 1):
        lines.append(f"{i}. {e['question']}  [{e.get('type') or 'text'}] - blocks {e['blocks']} job(s)")
        if e.get("options"):
            lines.append("   Options: " + " | ".join(e["options"][:15]))
        if e.get("company_specific"):
            lines.append(f"   Only for {e.get('company')}. {e.get('note', '')}")
        lines.append("   Jobs: " + "; ".join(f"{j['company']} - {j['role']}" for j in e["jobs"][:5]))
    return subject, "\n".join(lines)


def answer_pending(pending, answers, input_fn=input, out=print, now=None):
    """Walk the pending questions (most-blocking first); store answers under answers['questions']."""
    answers.setdefault("questions", {})
    for key in list(pending):
        e = pending[key]
        out(f"\n{e['question']}  (blocks {e.get('blocks', len(e.get('jobs') or []))} job(s))")
        if e.get("company_specific"):
            out(f"  Only for {e.get('company')}.")
        opts = e.get("options") or []
        for i, o in enumerate(opts, 1):
            out(f"  {i}. {o}")
        raw = (input_fn("Answer (number or text, Enter skips): ") or "").strip()
        if not raw:
            continue
        ans = opts[int(raw) - 1] if raw.isdigit() and opts and 1 <= int(raw) <= len(opts) else raw
        qkey = norm_question(e["question"])
        answers["questions"][qkey] = {"question": e["question"], "answer": ans, "type": e.get("type"),
                                      "options_seen": opts, "company": e.get("company"),
                                      "company_specific": bool(e.get("company_specific")), "learned_at": _iso(now)}
        del pending[key]
    return pending, answers


# =====================================================================================================
# Production API
# =====================================================================================================
def app_key(passcode):
    return hashlib.sha256(f"daily:{passcode}".encode()).hexdigest()


def api_base(flag=None):
    return (flag or os.getenv("APPLY_API_BASE") or DEFAULT_API).rstrip("/")


class Api:
    def __init__(self, base=DEFAULT_API, key="", session=None):
        import requests
        self.base, self.http = base.rstrip("/"), session or requests.Session()
        self.http.headers["X-App-Key"] = key  # never printed

    @classmethod
    def from_env(cls, base=None):
        passcode = os.getenv("APP_PASSCODE", "")
        if not passcode:
            sys.exit("APP_PASSCODE is not set (put it in the repo's .env).")
        api = cls(api_base(base), app_key(passcode))
        if not api.reachable():
            if base or os.getenv("APPLY_API_BASE"):
                sys.exit(START_HINT)
            api.base = PROD_API  # local app not running: production has the same database
            if not api.reachable():
                sys.exit(START_HINT)
            print(f"Local app not running: using {PROD_API}")
        return api

    def reachable(self):
        timeout = 3 if self._local() else 20  # Vercel's first request after idle (cold start) can take ~10 s
        for _ in range(2):
            try:
                if self.http.get(self.base + "/api/health", timeout=timeout).ok:
                    return True
            except Exception:
                pass
        return False

    def _local(self):
        return urlparse(self.base).hostname in ("localhost", "127.0.0.1")

    def _get(self, path, timeout=60, **params):
        import requests
        try:
            r = self.http.get(self.base + path, params=params, timeout=timeout)
            if r.status_code < 500 or not self._local():
                r.raise_for_status()
                return r.json()
            why = f"HTTP {r.status_code}"
        except (requests.Timeout, requests.ConnectionError) as e:
            if not self._local():
                raise
            why = type(e).__name__
        # The laptop's app often can't reach the database on campus Wi-Fi; production has the same data.
        print(f"Local app failed ({why}): switching to {PROD_API}")
        self.base = PROD_API
        return self._get(path, timeout=timeout, **params)

    def live_jobs(self, min_score=MIN_SCORE, min_ctc=MIN_CTC, role_types=ROLE_TYPES):
        return self._get("/api/jobs/live", min_score=min_score, min_ctc=min_ctc, role_type=",".join(role_types)).get("data") or []

    def all_live(self):
        return self._get("/api/jobs/live").get("data") or []

    def radar(self):
        return self._get("/api/jobs/radar", timeout=90)

    def pack(self, job_id):
        try:
            return self._get(f"/api/jobs/{int(job_id)}/pack", timeout=150).get("data") or {}
        except Exception as e:
            print(f"  (no pack for job {job_id}: {str(e)[:80]})")
            return {}

    def resume_url(self):
        return (self._get("/api/jobs/resume-file/info").get("data") or {}).get("url")

    def confirm_applied(self, job_id, notes, ref=None, applied_at=None, job=None):
        body = {"job_id": job_id, "notes": notes}
        if not job_id and job:  # a pasted link: Job Radar adds the posting, then records it
            body.update(company=job.get("company"), role=job.get("role"), url=job.get("url"),
                        board=job.get("board"), posting_id=posting_key(job.get("url")))
        if applied_at:
            body["applied_at"] = applied_at
        if ref:
            body["confirmation_ref"] = ref
        r = self.http.post(self.base + "/api/jobs/confirm-applied", json=body, timeout=60)
        if r.status_code == 409:
            return True, "already recorded"
        return r.ok, (r.json().get("message") if r.headers.get("content-type", "").startswith("application/json") else r.text[:120])

    def create_handoff(self, job, reason, missing, url=None):
        body = {"job_id": job.get("id"), "company": job.get("company"), "role": job.get("role"),
                "url": url or job.get("url"), "reason": reason, "missing": list(missing)[:20]}
        try:
            r = self.http.post(self.base + "/api/jobs/handoff", json=body, timeout=60)
            r.raise_for_status()
            return (r.json().get("data") or {}).get("id")
        except Exception as e:
            print(f"  hand-off could not be created: {str(e)[:100]}")
            return None

    def handoff_choice(self, handoff_id):
        try:
            return (self._get(f"/api/jobs/handoff/{int(handoff_id)}").get("data") or {}).get("choice") or "pending"
        except Exception:
            return "pending"

    def runner_report(self, payload):
        try:
            r = self.http.post(self.base + "/api/jobs/runner-report", json=payload, timeout=60)
        except Exception as e:
            print(f"runner-report failed: {str(e)[:100]}")
            return False
        if r.status_code in (404, 405):
            print("runner-report endpoint not live yet")
            return False
        return r.ok

    def runner_email(self, subject, text, html=None):
        """Email Sai through the app server (campus Wi-Fi blocks SMTP from the laptop)."""
        try:
            r = self.http.post(self.base + "/api/jobs/runner-email", json={"subject": subject, "text": text, "html": html},
                               timeout=90)
            return r.ok
        except Exception as e:
            print(f"runner-email failed: {str(e)[:100]}")
            return False


def ensure_resume(api, path=RESUME_PATH):
    """Download Sai's resume PDF once (the URL carries a read-only key: never print it)."""
    p = Path(path)
    if p.exists() and p.stat().st_size > 1000:
        return p.read_bytes()
    url = api.resume_url()
    if not url:
        print("No resume uploaded in Job Radar: resume fields will be left for you.")
        return None
    try:
        r = api.http.get(url, timeout=60)
    except Exception:
        r = None  # the exception text would contain the keyed URL: don't print it
    if r is None or not r.ok or not r.content.startswith(b"%PDF"):
        print(f"Resume download failed ({getattr(r, 'status_code', 'network error')}): resume fields will be left for you.")
        return None
    p.write_bytes(r.content)
    return r.content


AI_PATH = HERE / "ai_answers.yaml"
AI_SYSTEM = (
    "You fill in job application forms for one candidate: a final-year B.Tech CSE student in India applying to "
    "entry-level software roles in India. Answer ONLY from the candidate facts given.\n"
    "- If options are listed, answer with the exact text of one option.\n"
    "- Yes/No questions about willingness or eligibility (relocation, office work, shifts, availability, taking an "
    "assessment, background verification consent): answer in the candidate's favour unless the facts contradict it.\n"
    "- Never invent numbers, dates, IDs, names, employers or work history. Answer null ONLY when the question needs a "
    "personal fact you don't have: date of birth, ID or passport numbers, family details, criminal record, exact "
    "salary figures, or details of a job not in the facts.\n"
    "- Opinion, motivation and technical questions (favourite algorithm, why this role, a project you're proud of, "
    "how you'd design X) always get an answer: 1-3 plain first-person sentences built from the facts and sound CS "
    "knowledge.\n"
    "- Professional experience is 0 years (internships only, under a year in total): for years-of-experience "
    "questions answer 0, or the lowest option.\n"
    "- Languages: the candidate speaks English, Hindi and Telugu. Pick only those; if none is listed, answer null.\n"
    "- Availability: he is a student and can join only from January 2027 (6-month internship Jan-Jun 2027, or full-time "
    "from January 2027). He can NOT join immediately or before January 2027: answer No to 'join immediately / now / "
    "within N days' questions, or pick the option closest to January 2027.\n"
    'Return JSON: {"answer": "<text>"} or {"answer": null}.')
AI_PRIVATE_KEYS = {"phone", "address", "address_line1", "pin_code", "date_of_birth", "dob_day", "dob_month", "dob_year", "email",
                   "workday_password", "workday_passwords_old", "avature_password"}


def ai_facts(values):
    """Resume facts + the non-private answers, as prompt text."""
    try:
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from api.domain.job_pack import facts_text
        facts = facts_text()
    except Exception:
        facts = f"Skills: {KNOWN['skills']}"
    extra = "\n".join(f"{k}: {v}" for k, v in sorted(values.items()) if k not in AI_PRIVATE_KEYS)
    return facts + "\n" + extra


# A model's safety label or refusal instead of an answer ("User Safety: safe" was saved for "Country")
def _unwrap_answer(ans):
    """'{"answer": "January 2027"}' -> 'January 2027': the model sometimes nests its JSON (WorldQuant got the raw text)."""
    for _ in range(3):
        if ans:  # also '```json\n{"answer": ...}\n```'
            ans = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", ans)
        if not (ans and ans.lstrip().startswith("{")):
            break
        try:
            inner = json.loads(ans)
        except ValueError:
            break
        ans = _s(inner.get("answer")) if isinstance(inner, dict) else ans
    return ans


JUNK_ANSWER = re.compile(r"user safety|safety\s*:|\bas an ai\b|i (can't|cannot) (help|answer|provide)", re.I)
PHONE_CODE_OPTION = re.compile(r"\(\+\d{1,4}\)\s*$")  # "India (+91)"


def phone_codes_only(question, options):
    """True when a non-phone question was scanned with a phone-code dropdown's options (Workday leaves it open)."""
    opts = [o for o in (options or []) if _s(o)]
    return bool(opts) and all(PHONE_CODE_OPTION.search(_s(o)) for o in opts) and         not re.search(r"phone|country|code|dial", question or "", re.I)


def make_ai_answerer(values, generate=None, path=AI_PATH):
    """ai(question, ftype, options, company, role) -> answer or None. Answers are cached in ai_answers.yaml (reused
    for the same question, company-specific ones only for that company); fix any wrong one there."""
    if generate is None:
        if not (os.getenv("GEMINI_API_KEY") or os.getenv("OPENROUTER_API_KEY")):
            print("No GEMINI_API_KEY / OPENROUTER_API_KEY: unusual questions will be left for you.")
            return None
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from api.core.clients import LLMClient
        client = LLMClient(budget=45)
        def generate(prompt):
            try:
                return client.generate_json(prompt, temperature=0.2, system=AI_SYSTEM)
            except ValueError:  # the model returned prose / an empty reply instead of JSON: ask once more, plainly
                text = client.generate(prompt + "\nReply with only the answer text (or the single word null).",
                                       temperature=0.2, system=AI_SYSTEM).strip().strip('"')
                return {"answer": None if text.lower() in ("null", "none", "") else text}
    bank = QuestionBank(load_yaml(path) if path else {})
    facts = ai_facts(values)

    def ai(question, ftype, options, company, role=""):
        if phone_codes_only(question, options):
            return None
        _key, e = bank.find(question, company)
        if e and (not options or option_match(options, e["answer"]) is not None):
            return e["answer"]
        prompt = (f"Candidate facts:\n{facts}\n\nCompany: {company}\nRole: {role}\nQuestion: {question}\n"
                  f"Field type: {ftype}\n" + (f"Options: {json.dumps(options, ensure_ascii=False)}\n" if options else ""))
        out = generate(prompt)
        ans = _unwrap_answer(_s(out.get("answer") if isinstance(out, dict) else None))
        if not ans or _norm(ans) in ("null", "none", "unknown") or JUNK_ANSWER.search(ans):
            return None
        if bank.learn(question, ans, ftype, options, company, role) and path:
            save_yaml(path, bank.entries, "# Answers the AI gave to unusual form questions. Fix or delete any that are wrong.")
        return ans
    return ai


# ---------------- Sai's inbox, read-only: security codes and Workday verification links ----------------
WD_LINK = re.compile(r"https://[a-z0-9.-]+\.(?:myworkdayjobs|myworkdaysite|myworkday)\.com/[^\s\"'<>)\]]+", re.I)
VERIFY_HINT = re.compile(r"activat|verif", re.I)
CODE_IN_MAIL = re.compile(r"(?:security|verification|one[- ]time(?: pass)?)\s+code", re.I)
CODE_SENDERS = ("greenhouse", "lever", "ashby", "smartrecruiters", "myworkday", "oracle", "recruiting.ti.com")
MAIL_ALIASES = {"goldman sachs": ("gsrecruiting", "goldman"), "texas instruments": ("recruiting.ti.com", "texas instruments")}


def workday_tenant(url):
    """'https://barclays.wd3.myworkdayjobs.com/...' -> 'barclays'."""
    host = urlparse(url or "").netloc.lower()
    return host.split(".")[0] if "myworkday" in host else ""


def verify_links(text, tenant=None):
    """Workday verify / activate links in an email body (only this company's when `tenant` is given)."""
    import html as _html
    out = []
    for url in WD_LINK.findall(_html.unescape(text or "")):
        url = url.rstrip(".,;")
        if VERIFY_HINT.search(url) and (not tenant or tenant.lower() in url.lower()):
            out.append(url)
    return list(dict.fromkeys(out))


def code_in_mail(text):
    """The security code in an application email ('...security code field on your application: Ab12Cd34')."""
    import html as _html
    plain = re.sub(r"<[^>]+>", " ", _html.unescape(text or ""))
    for m in CODE_IN_MAIL.finditer(plain):
        for code in re.findall(r"\b[A-Za-z0-9]{6,10}\b", plain[m.end():m.end() + 250]):
            if re.search(r"\d", code) or (re.search(r"[a-z]", code) and re.search(r"[A-Z]", code)):
                return code  # real codes mix cases / digits; plain words ("application", "below") don't
    return None


def _email_parts(raw):
    import email as _email
    from email.header import decode_header, make_header
    msg = _email.message_from_bytes(raw)
    subject = str(make_header(decode_header(msg.get("Subject") or "")))
    sender = msg.get("From") or ""
    out = []
    for p in (msg.walk() if msg.is_multipart() else [msg]):
        if p.get_content_type() in ("text/plain", "text/html"):
            try:
                out.append(p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "replace"))
            except Exception:
                continue
    return sender, subject, "\n".join(out)


class Inbox:
    """Sai's Gmail over IMAP, read-only: the mailbox is opened read-only and bodies are fetched with BODY.PEEK, so
    nothing is marked read, moved or sent. Only mail from job-application senders is looked at."""

    def __init__(self, user, password, imap_factory=None, now=time.time):
        import imaplib
        self.user, self.password, self.now = user, password, now
        self.imap_factory = imap_factory or (lambda: imaplib.IMAP4_SSL("imap.gmail.com", timeout=15))
        self.used = set()

    def _recent(self, max_age_s, senders=CODE_SENDERS):
        """[(sender, subject, body, epoch)] of job-site mail from the last max_age_s seconds, newest first."""
        import imaplib
        m = self.imap_factory()
        out = []
        try:
            m.login(self.user, self.password)
            m.select("INBOX", readonly=True)
            since = (datetime.now() - timedelta(seconds=max_age_s + 86400)).strftime("%d-%b-%Y")
            nums = []
            for sender in senders:
                _typ, data = m.search(None, f'(SINCE "{since}" FROM "{sender}")')
                nums += (data[0] or b"").split()
            for num in sorted(set(nums), key=int, reverse=True)[:30]:
                _typ, parts = m.fetch(num, "(INTERNALDATE BODY.PEEK[])")
                meta = next((p[0] for p in parts if isinstance(p, tuple)), b"")
                raw = next((p[1] for p in parts if isinstance(p, tuple)), b"")
                t = imaplib.Internaldate2tuple(meta)
                ts = time.mktime(t) if t else self.now()
                if self.now() - ts > max_age_s:
                    continue
                out.append(_email_parts(raw) + (ts,))
        finally:
            try:
                m.logout()
            except Exception:
                pass
        return out

    def code_for(self, company, max_age_s=900, since=None):
        """Newest unused security code from an email that names this company (last 15 minutes; only mail that
        arrived after `since` when given, so an older code from a previous application is never reused)."""
        for sender, subject, body, ts in self._recent(max_age_s):
            if since and ts < since:
                continue
            text = f"{sender} {subject} {body}".lower()
            names = (company.lower(),) + MAIL_ALIASES.get(company.lower(), ()) if company else ()
            if names and not any(n in text for n in names):
                continue
            code = code_in_mail(body)
            if code and code not in self.used:
                self.used.add(code)
                return code
        return None

    def verify_link(self, tenant, max_age_s=3600):
        for _sender, _subject, body, _ts in self._recent(max_age_s):
            links = [u for u in verify_links(body, tenant) if u not in self.used]
            if links:
                self.used.add(links[0])
                return links[0]
        return None


    def confirmation_mails(self, max_age_s=30 * 86400):
        """[(sender, subject, body, epoch)] of job-site mail that reads like an application confirmation."""
        return [m for m in self._recent(max_age_s, senders=CODE_SENDERS + CONFIRM_SENDERS)
                if CONFIRM_MAIL.search(m[1] + " " + m[2][:3000])]

    def confirmations(self, max_age_s=7 * 86400):
        """[(subject, epoch)] of 'thank you for applying' / 'application received' emails, newest first."""
        out = []
        for sender, subject, body, ts in self._recent(max_age_s, senders=CODE_SENDERS + CONFIRM_SENDERS):
            if CONFIRM_MAIL.search(subject) and not re.search(r"security code|verify", subject, re.I):
                out.append((subject, ts))
        return out


CONFIRM_SENDERS = ("workday", "icims", "taleo", "successfactors", "eightfold", "amazon", "careers", "jobs", "talent")
CONFIRM_MAIL = re.compile(r"thank(s| you) for (applying|your application|your interest)|application (received|submitted|"
                          r"confirmation)|we('ve| have) received your application|your application (to|for|has been)", re.I)


def applied_by_email(mails, jobs):
    """Job ids already applied to, going by the companies' confirmation emails (also ones Sai applied to himself):
    the company must be named in the email and the role title must appear in it. -> {job id: email subject}."""
    out = {}
    for sender, subject, body, _ts in mails:
        if not CONFIRM_MAIL.search(subject + " " + body[:3000]) or re.search(r"security code|verify", subject, re.I):
            continue
        text = f" {_norm(sender)} {_norm(subject)} {_norm(body[:20000])} "
        for job in jobs:
            company, role = _norm(job.get("company")), _norm(job.get("role"))
            if company and role and f" {company} " in text and f" {role} " in text:
                out[job.get("id")] = subject
    return out


def confirmed_by_email(confirmations, jobs):
    """Match confirmation emails to jobs by company name in the subject. -> [(job, epoch, subject)], one per job."""
    out, seen = [], set()
    for job in jobs:
        name = _norm(job.get("company"))
        if not name or job.get("id") in seen:
            continue
        for subject, ts in confirmations:
            if not CONFIRM_MAIL.search(subject) or re.search(r"security code|verify", subject, re.I):
                continue
            if f" {name} " in f" {_norm(subject)} ":
                out.append((job, ts, subject))
                seen.add(job.get("id"))
                break
    return out


def sync_email_confirmations(api, inbox, jobs, log=None):
    """Mark jobs applied in Job Radar from the companies' confirmation emails, dated by the email. Returns count."""
    n = 0
    for job, ts, subject in confirmed_by_email(inbox.confirmations(), jobs):
        when = datetime.fromtimestamp(ts, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        ok, msg = api.confirm_applied(job.get("id"), f"Confirmed by email: {subject[:120]}", applied_at=when)
        if ok and msg != "already recorded":
            n += 1
            print(f"  marked applied from email: {job.get('company')} ({when[:10]})")
            if log:
                log.write({"job_id": job.get("id"), "company": job.get("company"), "role": job.get("role"),
                           "url": job.get("url"), "outcome": "email-confirmed", "applied_at": when})
    return n


TIDY_LABEL = "Job applications"
CODE_SUBJECT = re.compile(r"security code|verification code|one[- ]time (pass)?code", re.I)
CALLBACK = re.compile(r"interview|assessment|online test|\boa\b|coding (test|challenge)|shortlist|next step|screen|offer",
                      re.I)


def tidy_plan(mails, now, min_age_s=3600):
    """Which job-site mails to tidy: security codes -> Trash, application confirmations -> the label (out of the
    inbox). Interview / assessment / OA mails are never touched. mails: [(uid, sender, subject, epoch)]."""
    trash, archive = [], []
    for uid, sender, subject, ts in mails:
        if now - ts < min_age_s or CALLBACK.search(subject):
            continue
        if CODE_SUBJECT.search(subject):
            trash.append(uid)
        elif CONFIRM_MAIL.search(subject):
            archive.append(uid)
    return trash, archive


def tidy_inbox(user, password, imap_factory=None, now=time.time, days=14):
    """Gmail clean-up after applying (the only write the runner does to the mailbox)."""
    import email as _email
    import imaplib
    from email.header import decode_header, make_header
    m = (imap_factory or (lambda: imaplib.IMAP4_SSL("imap.gmail.com", timeout=20)))()
    try:
        m.login(user, password)
        m.select("INBOX")
        since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        uids = set()
        for sender in CODE_SENDERS + CONFIRM_SENDERS:
            _typ, data = m.uid("SEARCH", None, f'(SINCE "{since}" FROM "{sender}")')
            uids.update((data[0] or b"").split())
        mails = []
        for uid in sorted(uids):
            _typ, parts = m.uid("FETCH", uid, "(INTERNALDATE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
            meta = next((x[0] for x in parts if isinstance(x, tuple)), b"")
            raw = next((x[1] for x in parts if isinstance(x, tuple)), b"")
            msg = _email.message_from_bytes(raw)
            t = imaplib.Internaldate2tuple(meta)
            mails.append((uid, msg.get("From") or "", str(make_header(decode_header(msg.get("Subject") or ""))),
                          time.mktime(t) if t else now()))
        trash, archive = tidy_plan(mails, now())
        if archive:
            m.create(f'"{TIDY_LABEL}"')  # fails harmlessly when the label exists
            m.uid("MOVE", b",".join(archive).decode(), f'"{TIDY_LABEL}"')
        if trash:
            ok, _ = m.uid("MOVE", b",".join(trash).decode(), '"[Gmail]/Trash"')
            if ok != "OK":
                m.uid("MOVE", b",".join(trash).decode(), '"[Gmail]/Bin"')
        return len(trash), len(archive)
    finally:
        try:
            m.logout()
        except Exception:
            pass


def make_inbox(email_addr):
    """GMAIL_APP_PASSWORD in .env (an app password of Sai's own Gmail) lets the runner read codes / links itself."""
    password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not password:
        return None
    return Inbox(os.getenv("GMAIL_IMAP_USER") or email_addr, password)


def combine_code_sources(file_reader, inbox, every_s=20, clock=time.monotonic):
    """code_for(job, wait_s): a code pasted into security_codes.yaml, else one from the inbox (checked every 20 s)."""
    last = {"t": -1e9}

    def code_for(job, wait_s=0):
        code = file_reader(job, wait_s=0) if file_reader else None
        if code or not inbox or clock() - last["t"] < every_s:
            return code
        last["t"] = clock()
        try:
            return inbox.code_for(job.get("company"))
        except Exception as e:  # e.g. campus Wi-Fi blocks Gmail's IMAP port: stop trying for this run
            print(f"  (inbox not reachable, paste codes instead: {str(e)[:80]})")
            last["t"] = 1e18
            return None
    return code_for


def make_emailer(api=None):
    """send(subject, body) -> bool via api.core.clients.EmailClient (SENDER_EMAIL / SENDER_PASSWORD / RECEIVER_EMAIL),
    falling back to the app server's /api/jobs/runner-email when SMTP is blocked here."""
    def send(subject, body):
        sender, password = os.getenv("SENDER_EMAIL"), os.getenv("SENDER_PASSWORD")
        receiver = os.getenv("RECEIVER_EMAIL") or "sairaghava1318@gmail.com"
        ok = False
        if sender and password:
            if str(REPO) not in sys.path:
                sys.path.insert(0, str(REPO))
            from api.core.clients import EmailClient
            try:
                ok = EmailClient(sender, password).send_email(receiver, subject, body)
            except Exception:
                ok = False
        if not ok and api is not None:
            ok = api.runner_email(subject, body)
        if not ok:
            print("Email not sent (SMTP unavailable and the app server didn't send it).")
        return ok
    return send


# =====================================================================================================
# Browser driver (Playwright). Everything page-specific lives here; the runner only calls these methods.
# =====================================================================================================
SCAN_JS = r"""() => {
  window.__aaNext = window.__aaNext || 1;
  const txt = (n) => (n ? (n.innerText || n.textContent || '') : '').replace(/\s+/g, ' ').trim();
  const shown = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity || '1') > 0.05; };
  const own = (el) => (el.labels && el.labels.length ? txt(el.labels[0]) : '');
  const labelOf = (el) => {
    const l = own(el); if (l) return l;
    const by = el.getAttribute('aria-labelledby');
    if (by) { const t = by.split(/\s+/).map((i) => document.getElementById(i)).filter(Boolean).map(txt).join(' '); if (t) return t; }
    let n = el.parentElement;
    for (let i = 0; n && i < 4; i++, n = n.parentElement) {
      const c = [...n.querySelectorAll('label, legend, .application-label, [class*="label"], [class*="Label"]')]
        .find((x) => !x.contains(el) && !x.querySelector('input, select, textarea') && txt(x));
      if (c) return txt(c);
    }
    return '';
  };
  const groupOf = (el) => {
    const fs = el.closest('fieldset');
    if (fs) { const lg = fs.querySelector('legend'); if (lg && txt(lg)) return txt(lg); }
    const rg = el.closest('[role="radiogroup"], [role="group"]');
    if (rg) { const by = rg.getAttribute('aria-labelledby'); const l = by ? document.getElementById(by.split(/\s+/)[0]) : null;
      const t = l ? txt(l) : (rg.getAttribute('aria-label') || ''); if (t) return t; }
    const sel = el.name ? `input[name="${CSS.escape(el.name)}"]` : null;
    const total = sel ? document.querySelectorAll(sel).length : 1;
    if (total === 1 && el.type === 'checkbox' && own(el)) return own(el);  // a lone "I agree ..." tick box
    let n = el.parentElement;
    for (let i = 0; n && i < 6; i++, n = n.parentElement) {
      if (sel && n.querySelectorAll(sel).length < total) continue;
      const opts = sel ? [...n.querySelectorAll(sel)].map(own) : [own(el)];
      const lab = [...n.querySelectorAll('label, legend, [class*="label"], [class*="Label"], [class*="question"]')]
        .find((x) => !x.querySelector('input') && txt(x) && !opts.includes(txt(x)));
      if (lab) return txt(lab);
    }
    return labelOf(el);
  };
  const comboValue = (el) => {
    if (el.value) return el.value;
    const VAL = '[class*="single-value"], [class*="singleValue"], [class*="multi-value__label"], [class*="multiValue"], '
      + '[data-automation-id="selectedItem"]';
    // Workday: only this field's own box (walking up reached the phone code's "India (+91)" chip)
    const own = el.closest('[data-automation-id^="formField-"]');
    if (own) { const v = own.querySelector(VAL); return v ? txt(v) : ''; }
    let n = el.parentElement;
    for (let i = 0; n && i < 5; i++, n = n.parentElement) {
      if (n.querySelectorAll('input:not([type="hidden"]), select, textarea').length > 1) break;  // another field's box
      const v = n.querySelector(VAL);
      if (v) return txt(v);
    }
    return '';
  };
  // Workday: styled radios / check boxes are often transparent inputs under a visible label.
  const boxShown = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const out = [];
  for (const el of document.querySelectorAll('input, textarea, select')) {
    if (el.closest('#aa-overlay')) continue;
    const t = (el.type || '').toLowerCase();
    if (['hidden', 'submit', 'button', 'reset', 'image'].includes(t) || el.disabled) continue;
    const isFile = t === 'file';
    const choice = t === 'radio' || t === 'checkbox';
    const wdDate = /dateSection/i.test(el.id || '');  // Workday month/year boxes: sub-pixel inputs under the visible text
    if (!isFile && !wdDate && (!(choice ? boxShown(el) : shown(el)) || el.getAttribute('aria-hidden') === 'true')) continue;
    if (!el.dataset.aaId) el.dataset.aaId = String(window.__aaNext++);
    const role = (el.getAttribute('role') || (el.dataset.uxiWidgetType === 'selectinput' ? 'combobox' : '')).toLowerCase();
    const sel = el.tagName === 'SELECT';
    out.push({
      aid: el.dataset.aaId, tag: el.tagName.toLowerCase(),
      type: sel ? 'select' : (el.tagName === 'TEXTAREA' ? 'textarea' : (t || 'text')), role,
      label: choice ? groupOf(el) : labelOf(el), optlabel: choice ? (own(el) || el.value || '') : '',
      aria: el.getAttribute('aria-label') || '', placeholder: el.placeholder || '', name: el.name || '', id: el.id || '',
      required: !!(el.required || el.getAttribute('aria-required') === 'true'),
      value: role === 'combobox' ? comboValue(el) : (sel ? (el.value && el.selectedIndex >= 0 ? el.options[el.selectedIndex].text.trim() : '')
             : (choice ? el.value : (el.value || ''))),
      checked: !!el.checked, files: isFile && el.files ? el.files.length : 0,
      options: sel ? [...el.options].map((o) => o.text.trim()) : [], in_form: !!el.closest('form'),
    });
  }
  // Workday dropdowns are buttons ("Select One") that open a listbox.
  for (const el of document.querySelectorAll('button[aria-haspopup="listbox"]')) {
    if (el.closest('#aa-overlay') || el.disabled || !shown(el)) continue;
    if (!el.dataset.aaId) el.dataset.aaId = String(window.__aaNext++);
    const aria = el.getAttribute('aria-label') || '';
    const v = txt(el);
    out.push({
      aid: el.dataset.aaId, tag: 'button', type: 'listbox', role: 'listbox',
      label: labelOf(el) || aria.replace(/\s*(select one|required)\s*/gi, ' ').trim(), optlabel: '', aria, placeholder: '',
      name: el.name || '', id: el.id || '',
      required: el.getAttribute('aria-required') === 'true' || /\brequired\b/i.test(aria),
      value: /^select one$/i.test(v) ? '' : v, checked: false, files: 0, options: [], in_form: !!el.closest('form'),
    });
  }
  return out;
}"""

STATE_JS = r"""() => {
  const shown = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const big = (el) => { const r = el.getBoundingClientRect(); return r.width > 30 && r.height > 30; };
  const txt = (n) => (n ? (n.innerText || '') : '').trim();
  const body = document.body ? document.body.innerText : '';
  const capFrame = [...document.querySelectorAll('iframe')].filter((f) => shown(f) && big(f)).some((f) => {
    const s = f.src || ''; if (/size=invisible|checkbox-invisible/.test(s)) return false;
    return /recaptcha|hcaptcha|turnstile|challenges\.cloudflare|arkoselabs|funcaptcha|captcha/i.test(s); });
  const capEl = [...document.querySelectorAll('.g-recaptcha:not([data-size="invisible"]), .h-captcha:not([data-size="invisible"]), .cf-turnstile, #challenge-form')].some(shown);
  const capText = /verify you are (a )?human|complete the security check/i.test(body.slice(0, 5000));
  const login = [...document.querySelectorAll('input[type="password"]')].some(shown);
  const errors = [...document.querySelectorAll('[aria-invalid="true"], .error-message, [class*="error-message"], [class*="field-error"], [class*="ErrorMessage"]')]
    .filter((e) => shown(e) && (e.matches('[aria-invalid="true"]') || txt(e))).length;
  const errtext = [...document.querySelectorAll('[aria-invalid="true"], .error-message, [class*="error-message"], [class*="field-error"], [class*="ErrorMessage"]')]
    .filter((e) => shown(e)).map((e) => {
      if (!e.matches('[aria-invalid="true"]')) return txt(e);
      const lab = e.labels && e.labels[0] ? e.labels[0].innerText : (e.getAttribute('aria-label') || e.name || e.id);
      return 'invalid: ' + (lab || '').replace(/\s+/g, ' ').trim();
    }).filter(Boolean).slice(0, 6);
  return { url: location.href, captcha: capFrame || capEl || capText, login, errors, errtext, text: body.slice(0, 20000) };
}"""

MARK_JS = r"""(items) => {
  for (const [aid, color] of items) {
    const el = document.querySelector(`[data-aa-id="${aid}"]`); if (!el) continue;
    let t = el;
    if (el.type === 'file' || el.type === 'radio' || el.type === 'checkbox' || getComputedStyle(el).opacity === '0')
      t = el.closest('label, [class*="field"], [class*="upload"], [class*="question"], div') || el;
    t.style.outline = `2px solid ${color}`; t.style.outlineOffset = '2px';
  }
  return true;
}"""

OVERLAY_JS = r"""(a) => {
  const old = document.getElementById('aa-overlay'); if (old) old.remove();
  if (!document.body) return false;
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const box = document.createElement('div'); box.id = 'aa-overlay';
  // Top-right (forms put Submit at the bottom), and it can be hidden so it never covers anything.
  box.style.cssText = 'position:fixed;z-index:2147483647;right:16px;top:16px;max-width:340px;background:#111827;color:#fff;'
    + 'font:14px/1.45 system-ui,sans-serif;padding:14px 16px;border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.35)';
  const pill = document.createElement('button'); pill.type = 'button'; pill.textContent = 'Runner ▸';
  pill.style.cssText = 'display:none;position:fixed;z-index:2147483647;right:16px;top:16px;background:#111827;color:#fff;'
    + 'border:0;border-radius:999px;padding:6px 12px;font:600 12px system-ui,sans-serif;cursor:pointer';
  pill.onclick = () => { box.style.display = ''; pill.style.display = 'none'; };
  const list = (a.items || []).slice(0, 10).map((x) => `<li>${esc(x)}</li>`).join('');
  box.innerHTML = `<b>${esc(a.title)}</b>`
    + (list ? `<div style="margin-top:6px;color:#fcd34d">Still for you (orange):</div><ul style="margin:4px 0 0 18px;padding:0">${list}</ul>` : '')
    + `<div style="margin-top:8px;color:#d1d5db">${esc(a.message)}</div>`;
  const row = document.createElement('div'); row.style.marginTop = '10px';
  const btn = (label, bg) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = label;
    b.style.cssText = `margin-right:8px;background:${bg};color:#fff;border:0;border-radius:8px;padding:7px 12px;font-weight:600;cursor:pointer`;
    row.appendChild(b); return b; };
  if (a.cont) { const c = btn('✅ I finished — continue', '#16a34a'); c.onclick = () => { window.__aaContinue = true; c.textContent = 'Continuing…'; }; }
  else { btn('OK', '#f97316').onclick = () => box.remove(); }
  btn('✕ Hide', '#374151').onclick = () => { box.style.display = 'none'; pill.style.display = ''; };
  box.appendChild(row);
  // Drag it anywhere (grab the box, not a button); the spot is kept for the next message on this page.
  const hint = document.createElement('div'); hint.textContent = '⠿ drag to move';
  hint.style.cssText = 'margin:-6px 0 6px;font-size:11px;color:#9ca3af;cursor:move;user-select:none';
  box.insertBefore(hint, box.firstChild); box.style.cursor = 'move';
  const place = (x, y) => { box.style.left = x + 'px'; box.style.top = y + 'px'; box.style.right = 'auto'; };
  if (window.__aaPos) place(window.__aaPos[0], window.__aaPos[1]);
  box.addEventListener('pointerdown', (e) => {
    if (e.target.closest('button')) return;
    const r = box.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
    box.setPointerCapture(e.pointerId);
    const move = (ev) => { const x = Math.max(0, Math.min(window.innerWidth - 60, ev.clientX - dx));
      const y = Math.max(0, Math.min(window.innerHeight - 40, ev.clientY - dy)); place(x, y); window.__aaPos = [x, y]; };
    const up = () => { box.removeEventListener('pointermove', move); box.removeEventListener('pointerup', up); };
    box.addEventListener('pointermove', move); box.addEventListener('pointerup', up);
  });
  document.body.appendChild(box); document.body.appendChild(pill); return true;
}"""

FIND_ENTRY_JS = r"""(p) => {
  const re = new RegExp('^\\s*(' + p + ')\\s*$', 'i');
  const shown = (el) => { const r = el.getBoundingClientRect(); return r.width > 1 && r.height > 1 && getComputedStyle(el).visibility !== 'hidden'; };
  document.querySelectorAll('[data-aa-entry]').forEach((e) => e.removeAttribute('data-aa-entry'));
  const c = [...document.querySelectorAll('a, button, [role="button"]')]
    .find((e) => shown(e) && !e.closest('form') && re.test((e.innerText || e.getAttribute('aria-label') || '').replace(/\s+/g, ' ')));
  if (!c) return false; c.setAttribute('data-aa-entry', '1'); return true;
}"""

FIND_SUBMIT_JS = r"""() => {
  const shown = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none'; };
  document.querySelectorAll('[data-aa-submit]').forEach((e) => e.removeAttribute('data-aa-submit'));
  const forms = [...document.querySelectorAll('form')].map((f) => [f, f.querySelectorAll('[data-aa-id]').length]).sort((a, b) => b[1] - a[1]);
  const scope = forms.length && forms[0][1] > 0 ? forms[0][0] : document;
  const all = [...scope.querySelectorAll('button, input[type="submit"], [role="button"]')].filter(shown);
  const label = (b) => ((b.innerText || '') + ' ' + (b.value || '') + ' ' + (b.getAttribute('aria-label') || '')).replace(/\s+/g, ' ').trim();
  let c = all.filter((b) => /\bsubmit\b|send application/i.test(label(b)));
  if (!c.length) c = all.filter((b) => /^\s*apply( now)?\s*$/i.test(label(b)) || (b.tagName === 'INPUT' && b.type === 'submit'));
  if (!c.length) return null;
  const b = c[c.length - 1]; b.setAttribute('data-aa-submit', '1'); return label(b);
}"""

CAPTCHA_FRAME_URL = re.compile(r"recaptcha|hcaptcha|turnstile|challenges\.cloudflare|arkoselabs|funcaptcha|"
                               r"captcha-delivery\.com", re.I)
# A bot wall that covers the whole page (DataDome on SmartRecruiters' Bosch pages): always a CAPTCHA for Sai, never
# "no form" (invisible reCAPTCHA frames on normal forms don't count)
BOT_WALL_URL = re.compile(r"captcha-delivery\.com", re.I)
DIAG_JS = r"""() => { const vis = (e) => e.offsetParent !== null;
  return {url: location.href, visibility: document.visibilityState,
    ids: [...new Set([...document.querySelectorAll('[data-automation-id]')].filter(vis)
      .map((e) => e.getAttribute('data-automation-id')))].slice(0, 120),
    buttons: [...document.querySelectorAll('button, a[role=button], [role=button]')].filter(vis)
      .map((b) => (b.innerText || b.getAttribute('aria-label') || '').trim()).filter(Boolean).slice(0, 60),
    text: document.body ? document.body.innerText.replace(/\s+/g, ' ').slice(0, 2000) : ''}; }"""
BROWSER_ARGS = ["--disable-renderer-backgrounding", "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows"]
OFFSCREEN_ARGS = ["--window-position=-32000,-32000", "--start-minimized"]


def close_leftover_browsers(profile=PROFILE_DIR):
    """Stop Chrome processes still holding this tool's own profile (left by a crashed run). Never touches Sai's
    normal Chrome: only processes whose command line names this profile folder. Returns how many were stopped."""
    try:
        import psutil
    except ImportError:
        return 0
    needle = str(Path(profile)).lower()
    procs = []
    for p in psutil.process_iter(["cmdline", "ppid"]):
        try:
            if needle in " ".join(p.info["cmdline"] or []).lower():
                procs.append(p)
        except (psutil.Error, OSError):
            continue
    pids = {p.pid for p in procs}
    roots = [p for p in procs if p.info["ppid"] not in pids]
    if any(psutil.pid_exists(p.info["ppid"]) for p in roots):
        return 0  # the run that started it is still alive: another run is using the profile, leave it alone
    n = 0
    for p in procs:
        try:
            p.kill()
            n += 1
        except (psutil.Error, OSError):
            continue
    return n


LEAN_BLOCK = {"image", "media", "font"}


def lean_browsing(ctx):
    """Unattended workers don't need pictures, video or web fonts: skip them (faster pages, less RAM per browser).
    Visible windows Sai looks at load normally. Opt-in with APPLY_LEAN=1 (it broke a Workday Save and Continue test)."""
    def handle(route):
        try:
            if route.request.resource_type in LEAN_BLOCK:
                route.abort()
            else:
                route.continue_()
        except Exception:
            pass
    try:
        ctx.route("**/*", handle)
    except Exception:
        pass


def launch(pw, headless=False, visible=False, profile=None):
    """Normal Playwright Chrome with a persistent profile. Off-screen + minimized unless --visible/--headless.
    Parallel workers each get their own profile folder (Chrome allows one browser per profile)."""
    profile = Path(profile) if profile else PROFILE_DIR
    profile.mkdir(parents=True, exist_ok=True)
    args = BROWSER_ARGS + ([] if headless or visible else OFFSCREEN_ARGS)
    opts = dict(headless=headless, args=args, viewport={"width": 1280, "height": 900}, accept_downloads=False)
    last = None
    for attempt in (1, 2):
        for channel in ("chrome", None):  # installed Chrome first, Playwright's Chromium as a fallback
            try:
                if channel:
                    ctx = pw.chromium.launch_persistent_context(str(profile), channel=channel, **opts)
                else:
                    ctx = pw.chromium.launch_persistent_context(str(profile), **opts)
                if not visible and os.getenv("APPLY_LEAN", "0") == "1":  # off by default: Workday lost its Save button
                    lean_browsing(ctx)
                return ctx
            except Exception as e:
                last = e
        if attempt == 1 and "existing browser session" in str(last) and close_leftover_browsers(profile):
            print("Closed a leftover browser from an earlier run; retrying.")
            time.sleep(2)
            continue
        break
    raise last


class PlaywrightDriver:
    def __init__(self, context, headless=False, visible=False, resume=None, resume_name="Resume.pdf",
                 submit_enabled=False, gh_tokens=None):
        self.context = context
        self.page = context.pages[0] if context.pages else context.new_page()
        self.base_page = self.page
        self.headless, self.visible = headless, visible
        self.resume, self.resume_name = resume, resume_name
        self.submit_enabled = submit_enabled
        self.gh_tokens = gh_tokens or {}
        self.start_url = None
        self._frames = {}
        self._overlay_args = None
        self.inbox = None  # Inbox: Workday verification links from Sai's Gmail (read-only)

    # ---- window: off-screen while working, on-screen only when Sai is needed ----
    def _window(self, bounds):
        s = self.context.new_cdp_session(self.page)
        try:
            wid = s.send("Browser.getWindowForTarget")["windowId"]
            s.send("Browser.setWindowBounds", {"windowId": wid, "bounds": bounds})
        finally:
            s.detach()

    def hide(self):
        if self.headless:
            return
        if self.visible:  # the profile remembers the last (off-screen) position: put the window where Sai can see it
            self.show()
            return
        try:
            self._window({"windowState": "normal"})
            self._window({"left": -32000, "top": -32000})
            self._window({"windowState": "minimized"})
        except Exception as e:
            print(f"  (could not move the window off-screen: {str(e)[:80]})")

    def show(self):
        if self.headless:
            return
        try:
            self._window({"windowState": "normal"})
            self._window({"left": 40, "top": 30, "width": 1320, "height": 980})  # back on-screen first...
            self._window({"windowState": "maximized"})  # ...then full screen, so the whole form (and Submit) fits
        except Exception:
            pass
        self.page.bring_to_front()
        self._raise_native()

    def _raise_native(self):
        """Windows: put the runner's window above whatever Sai is working in, flash it and chime, so he notices."""
        if os.name != "nt":
            return
        try:
            import ctypes
            import winsound
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            title = (self.page.title() or "")[:40]
            found = []

            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def each(hwnd, _):
                n = user32.GetWindowTextLengthW(hwnd)
                if n and user32.IsWindowVisible(hwnd):
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    if title and buf.value.startswith(title) and "Chrome" in buf.value:
                        found.append(hwnd)
                return True
            user32.EnumWindows(each, 0)
            flags = 0x0001 | 0x0002 | 0x0040  # SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW
            for hwnd in found[:1]:
                user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE first: Windows lets a restored window take the foreground
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE (alone, it stayed behind Sai's editor on 2026-10-28)
                user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)  # HWND_TOPMOST: jump above everything...
                user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, flags)  # ...then normal again, so Sai can switch away
                user32.SetForegroundWindow(hwnd)
                user32.FlashWindow(hwnd, True)
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

    # ---- navigation ----
    def url(self):
        try:
            return self.page.url
        except Exception:
            return ""

    def _settle(self):
        try:  # sites with trackers never go network-idle: cap the wait (the fill steps poll for their own fields)
            self.page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass
        self.page.wait_for_timeout(800)

    def _goto(self, url):
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            if "net::" not in str(e):
                raise
            self.page.wait_for_timeout(5000)  # flaky Wi-Fi / DNS: one retry
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self._settle()

    def open(self, job):
        """Go to the application form. Returns a short note on how we got there."""
        url, kind = application_url(job["url"], job.get("company"), self.gh_tokens)
        self._goto(url)
        note = kind
        gh = re.search(r"greenhouse\.io/([^/?#]+)/jobs/(\d+)", url)
        if kind == "greenhouse" and gh and "greenhouse.io" not in urlparse(self.url()).netloc:
            # the board redirected to the company's own careers site: open Greenhouse's form directly
            self._goto(f"https://job-boards.greenhouse.io/embed/job_app?for={gh.group(1)}&token={gh.group(2)}")
            note = "greenhouse (company site redirect, opened form directly)"
        if kind == "other" and ORACLE_CX.search(self.url()):
            return self._oracle_start(job)
        if kind == "other":
            emb = self.page.evaluate("() => { const f = document.querySelector('iframe[src*=\"greenhouse.io/embed/job_app\"]');"
                                     " return f ? f.src : null; }")
            if emb:
                self._goto(emb)
                note = "greenhouse (embedded form)"
            else:
                note = self._open_apply_entry()
                if note.startswith(("followed", "clicked")):  # e.g. Workday: Apply -> "Apply Manually"
                    second = self._open_apply_entry(wait_s=8)
                    if second.startswith(("followed", "clicked")):
                        note += ", then " + second
                if ORACLE_CX.search(self.url()):  # e.g. Goldman Sachs: its site's Apply leads to Oracle
                    return note + ", then " + self._oracle_start(job)
        self.start_url = self.url()
        return note

    def _avature_account(self, values, passwords):
        """Avature career sites (Siemens, Siemens Energy): sign in with the runner's password, or create the candidate
        profile once (email, name, phone, password, data-sharing choice). Leaves the browser on the application."""
        page = self.page
        email = _s(values.get("email"))
        if not email or not passwords:
            return "failed:no email or password for the account"
        if "/Login" in self.url():
            for pw in passwords:
                user = self._visible("input[name='username'], input#username, input[type='email']")
                pwd = self._visible("input[type='password']")
                if user is None or pwd is None:
                    break
                user.fill(email)
                pwd.fill(pw)
                btn = page.get_by_role("button", name=re.compile(r"^\s*log ?in\s*$", re.I))
                if not btn.count():
                    break
                safe_click(btn.first, "account")
                page.wait_for_timeout(5000)
                if "/Login" not in self.url():
                    return "avature (signed in)"
            link = page.get_by_text(re.compile(r"create (a |your )?profile|create (an )?account|^\s*register\s*$", re.I))
            if not link.count():
                return "failed:Avature sign-in failed and no Create profile link"
            safe_click(link.first, "account")
            page.wait_for_timeout(5000)
        if "/Register" not in self.url():
            return "avature"
        phone = re.sub(r"\D", "", national_number(_s(values.get("phone"))) or "")
        for rx, val in ((r"^\s*e-?mail", email), (r"first name", values.get("first_name")),
                        (r"last name", values.get("last_name")), (r"phone", phone),
                        (r"^\s*password\s*\*?\s*$", passwords[0]), (r"password confirmation|confirm", passwords[0])):
            loc = page.get_by_label(re.compile(rx, re.I))
            if val and loc.count():
                loc.first.fill(_s(val), timeout=6000)
        radios = page.locator("input[type='radio']")
        if radios.count():
            safe_click(radios.first, "toggle")  # share the profile with the group's companies (more roles seen)
        nxt = page.locator("button:visible").filter(has_text=re.compile(
            r"^\s*(next|register|create( profile| account)?|continue|confirm)\s*$", re.I))
        if not nxt.count():
            return "failed:no Next button on the Avature registration"
        label = nxt.first.inner_text().strip()
        if re.fullmatch(r"(?i)confirm", label) and "/Register" in self.url():
            # Avature's registration page ends with "Confirm": it creates the candidate profile only (the application
            # steps - Resume, Personal Information, Additional Information - and their Submit come after it)
            safe_click(nxt.first, "avature_register")
        else:
            safe_click(nxt.first, "next_page" if re.fullmatch(r"(?i)next|continue", label) else "account")
        page.wait_for_timeout(6000)
        errs = page.locator(".error, [class*='error' i]:visible").all_inner_texts()
        if "/Register" in self.url() and any(e.strip() for e in errs):
            return "failed:Avature registration: " + "; ".join(e.strip() for e in errs if e.strip())[:150]
        return "avature (profile created)"

    def _oracle_cookies(self):
        """Dismiss an Oracle / Akamai cookie banner ("ACCEPT ALL", "ACCEPT") if it is showing."""
        accept = self.page.locator("button:visible").filter(has_text=re.compile(r"^\s*accept( all)?( cookies)?\s*$", re.I))
        try:
            if accept.count() and accept.first.is_visible():
                safe_click(accept.first, "dismiss")
                self.page.wait_for_timeout(800)
        except Exception:
            pass

    def _oracle_terms(self):
        """Tick the terms box on the email step. Some sites (Honeywell) open an "Important Privacy Information" dialog
        from the box and only tick it after ACCEPT; others take a click on the hidden input."""
        page = self.page
        box = page.locator("#legal-disclaimer-checkbox")
        try:
            if not box.count() or box.first.is_checked():
                return
            label = page.locator("label[for='legal-disclaimer-checkbox']")
            if label.count():
                safe_click(label.first, "toggle_label")
                page.wait_for_timeout(1500)
                self._oracle_cookies()  # the dialog's ACCEPT button (same matcher as the cookie banner)
                page.wait_for_timeout(1000)
            if not box.first.is_checked():
                page.evaluate("""() => { const c = document.getElementById('legal-disclaimer-checkbox');
                                         if (c && !c.checked) c.dispatchEvent(new MouseEvent('click', {bubbles: true})); }""")
        except Exception:
            pass

    def _oracle_start(self, job, code_wait_s=240):
        """Oracle Candidate Experience (Texas Instruments, Goldman Sachs): cookie banner, Apply Now, email + terms,
        then the one-time code it emails. Leaves the browser on the application form."""
        page = self.page
        for sel in ("#consent_prompt_submit", "#onetrust-accept-btn-handler"):
            loc = self._visible(sel)
            if loc is not None:
                try:
                    safe_click(loc, "dismiss")
                    page.wait_for_timeout(1000)
                except Exception:
                    pass
        self._oracle_cookies()
        if "/apply" not in self.url():
            btn = page.get_by_role("button", name=re.compile(r"^\s*apply now\s*$", re.I))
            if btn.count():
                safe_click(btn.first, "open_application")
        for _ in range(20):  # slow sites: wait for the email step or the form itself, not a fixed delay
            self._oracle_cookies()  # Oracle's own cookie modal appears ~2 s late and blocks NEXT (Honeywell)
            if "/apply/email" in self.url() and self._visible('input[type="email"]') is not None:
                break
            if "/apply" in self.url() and len(pick_form_fields(self.scan())) >= 3:
                break
            page.wait_for_timeout(1000)
        email = self._visible('input[type="email"]') if "/apply/email" in self.url() else None  # only the sign-in step
        if email is not None:
            email.fill(_s(getattr(self, "email", "")) or "sairaghava1318@gmail.com", timeout=6000)
            self._oracle_terms()
            self._oracle_cookies()
            nxt = page.get_by_role("button", name=re.compile(r"^\s*next\s*$", re.I))
            self._code_since = time.time() - 60  # mail clocks drift a little
            for _attempt in range(3):  # a late cookie modal can swallow the click: still on the email step -> again
                if not nxt.count() or "/apply/email" not in self.url():
                    break
                self._oracle_cookies()
                safe_click(nxt.first, "next_page")
                page.wait_for_timeout(5000)
        if re.search(r"confirm your identity|verification code", self.page_text() or "", re.I):
            code, deadline = None, time.monotonic() + code_wait_s
            while not code and time.monotonic() < deadline and self.inbox:
                page.wait_for_timeout(8000)
                try:
                    code = self.inbox.code_for(job.get("company") or "", since=getattr(self, "_code_since", None))
                except Exception:
                    code = None
            if not code:
                self.start_url = self.url()
                return "oracle (identity code not received)"
            boxes = page.locator("input[id^='pin-code'], input[autocomplete='one-time-code'], input[inputmode='numeric'], "
                                 "input[aria-label*='verification code digit' i]")
            if boxes.count() >= len(code):
                for i, ch in enumerate(code):
                    boxes.nth(i).fill(ch)
            elif boxes.count():
                boxes.first.fill(code)
            verify = page.get_by_role("button", name=re.compile(r"^\s*verify\s*$", re.I))
            if verify.count():
                safe_click(verify.first, "next_page")
                page.wait_for_timeout(8000)
        self._settle()
        self.start_url = self.url()
        return "oracle (signed in with an emailed code)"

    def _open_apply_entry(self, wait_s=15):
        """Single-page career sites render late: wait for either a form or an 'Apply' entry button."""
        deadline = time.monotonic() + wait_s
        while True:
            if len(pick_form_fields(self.scan())) >= 2:
                return "form on the job page"
            if self.page.evaluate(FIND_ENTRY_JS, APPLY_ENTRY):
                break
            if time.monotonic() >= deadline:
                return "job page (no Apply button found)"
            self.page.wait_for_timeout(1000)
        el = self.page.locator('[data-aa-entry="1"]').first
        info = el.evaluate(ELEMENT_INFO_JS)
        if info.get("tag") == "a" and (info.get("href") or "").startswith("http"):
            self._goto(info["href"])  # follow the link instead of clicking
            return "followed the Apply link"
        before = len(self.context.pages)
        safe_click(el, "open_application", info=info)
        self.page.wait_for_timeout(2500)
        if len(self.context.pages) > before:
            self.page = self.context.pages[-1]
        self._settle()
        return "clicked the Apply button"

    def reset(self):
        """'Close the tab': drop extra tabs and park the main one on a blank page."""
        for p in list(self.context.pages):
            if p is not self.base_page:
                try:
                    p.close()
                except Exception:
                    pass
        self.page = self.base_page
        try:
            self.page.goto("about:blank")
        except Exception:
            pass

    # ---- reading and filling ----
    def scan(self):
        out, self._frames = [], {}
        for i, fr in enumerate(self.page.frames):
            if CAPTCHA_FRAME_URL.search(fr.url or ""):
                continue
            try:
                rows = fr.evaluate(SCAN_JS)
            except Exception:
                continue
            self._frames[i] = fr
            for r in rows:
                r["frame"] = i
                out.append(r)
        return out

    def _loc(self, f):
        return self._frames[f["frame"]].locator(f'[data-aa-id="{f["aid"]}"]').first

    def apply(self, actions):
        filled, failed = [], []
        for a in actions:
            try:
                loc = self._loc(a.f)
                if a.kind == "text" and loc.evaluate("el => el.classList.contains('location-input')"):
                    self._lever_location(loc, str(a.value))
                elif a.kind == "text" and "datesection" in str(a.f.get("id") or "").lower():
                    loc.focus(timeout=6000)  # Workday's month/year boxes only take real keystrokes
                    loc.press_sequentially(str(a.value), delay=60)
                elif a.kind == "text":
                    loc.fill(str(a.value), timeout=6000)
                    try:  # some React forms (HPE) drop pasted values: type it key by key instead
                        if str(a.value) and loc.input_value(timeout=1500) != str(a.value):
                            loc.fill("", timeout=3000)
                            loc.press_sequentially(str(a.value), delay=25)
                    except Exception:
                        pass
                elif a.kind == "select":
                    loc.select_option(index=a.value, timeout=6000)
                elif a.kind == "toggle":
                    safe_click(loc, "toggle")
                elif a.kind == "file":
                    if self.is_workday() and self.page.locator('[data-automation-id="file-upload-item"]').count():
                        filled.append(a)  # Workday empties the file input after an upload: one resume is enough
                        continue
                    loc.set_input_files({"name": self.resume_name, "mimeType": "application/pdf", "buffer": self.resume},
                                        timeout=10000)
                    if self.is_workday():  # "Next" stays disabled while the upload spins
                        try:
                            self.page.locator('[data-automation-id="file-upload-successful"]').first.wait_for(timeout=30000)
                        except Exception:
                            pass
                elif a.kind == "combo" and a.f.get("role") == "listbox":
                    if not self._listbox(loc, a):
                        raise ValueError(f"no option matches {a.value!r}")
                elif a.kind == "combo" and not self._combo(loc, a):
                    raise ValueError(f"no option matches {a.value!r}")
                filled.append(a)
            except Exception as e:
                failed.append(Todo(a.f, a.label, f"couldn't fill automatically ({str(e).splitlines()[0][:60]})",
                                   a.f.get("type"), list(a.f.get("options") or [])))
        return filled, failed

    def _lever_location(self, loc, value):
        """Lever's location box only counts a city picked from its suggestions (typed text alone stays 'missing')."""
        loc.fill("", timeout=5000)
        loc.press_sequentially(value.split(",")[0].strip(), delay=50)
        opt = loc.locator("xpath=..").locator(".dropdown-location:visible").first
        opt.wait_for(state="visible", timeout=8000)
        safe_click(opt, "pick_option")

    def _combo(self, loc, a):
        """Search-as-you-type dropdown: type each search term and pick a matching option; if typing finds nothing
        (e.g. the answer is "Yes" but the options say "I acknowledge"), open the full list and match against it."""
        frame = self._frames[a.f["frame"]]
        pick = lambda: self._pick_option(frame, a)  # noqa: E731

        if rule_key(a.f) == "how_did_you_hear" and self.is_workday():
            # Workday source pickers list categories (Company Website, Job Posting Sites, ...): typed searches only
            # match the leaves, so open the full list and pick a category (then its first sub-source) directly.
            # Newer Workday opens the list only on a click; any source is a formality, so fall back to the first one.
            for opener in ("click", "arrow"):
                try:
                    self.page.keyboard.press("Escape")  # close any other open picker (phone code) first
                    if opener == "click":
                        safe_click(loc, "open_dropdown")
                    else:
                        loc.focus(timeout=5000)
                        loc.press("ArrowDown")
                    self._wait_options(frame)
                    if pick() or self._pick_option(frame, a, any_option=True):
                        return True
                except Exception:
                    pass
        extra = [t for t in (a.targets or [])[1:] if len(t) <= 40]  # e.g. "NIT Rourkela", then "Other"
        for term in list(dict.fromkeys(combo_terms(a.value) + extra))[:7]:
            loc.fill("", timeout=5000)
            loc.press_sequentially(term, delay=35)  # search boxes (school lists) only search on real keystrokes
            self._wait_options(frame)  # search-as-you-type boxes (school lists) load results after ~2 s
            if pick():
                return True
            if a.f.get("role") == "combobox" and self.is_workday():
                try:
                    search_enter(loc)  # Workday search pickers only search on Enter
                except SubmitBlocked:
                    continue
                self.page.wait_for_timeout(1500)
                if pick():
                    return True
        try:
            loc.fill("", timeout=3000)
            loc.focus(timeout=3000)
            loc.press("ArrowDown")
            self.page.wait_for_timeout(1000)
            if pick():
                return True
        except Exception:
            pass
        try:
            loc.fill("", timeout=3000)
            loc.press("Escape")
        except Exception:
            pass
        return False

    # Visible options only: pages hide hundreds of other options (e.g. a phone country-code picker's 240 countries).
    def combo_options(self, f):
        """Open a dropdown, read its visible choices, close it again (nothing is selected)."""
        frame, loc, texts = self._frames.get(f.get("frame")), self._loc(f), []
        if frame is None:
            return []
        try:
            if f.get("role") == "listbox":
                safe_click(loc, "open_dropdown")
            else:
                loc.fill("", timeout=3000)
                loc.focus(timeout=3000)
                loc.press("ArrowDown")
            self.page.wait_for_timeout(900)
            opts = frame.locator(self.OPTION_SEL)
            for i in range(min(opts.count(), 60)):
                try:
                    texts.append(re.sub(r"\s+", " ", opts.nth(i).inner_text(timeout=1000)).strip())
                except Exception:
                    continue
        except Exception:
            pass
        finally:
            try:
                self.page.keyboard.press("Escape")
            except Exception:
                pass
        return list(dict.fromkeys(t for t in texts if t))

    OPTION_SEL = ('[role="option"]:visible, [data-automation-id="promptOption"]:visible, '
                  '.cx-select__list-item:visible')  # last: Oracle Candidate Experience dropdowns

    def _wait_options(self, frame, timeout_ms=3500):
        """Wait until the dropdown shows options (or the timeout passes)."""
        waited = 0
        self.page.wait_for_timeout(700)
        while waited < timeout_ms:
            try:
                if frame.locator(self.OPTION_SEL).count():
                    self.page.wait_for_timeout(300)  # let the list finish rendering
                    return
            except Exception:
                return
            self.page.wait_for_timeout(400)
            waited += 400

    def _pick_option(self, frame, a, any_option=False):
        """Click the visible dropdown option that best matches the action's targets. False if none matches
        (any_option: then the first visible option, for formality questions like "How did you hear about us")."""
        strict = a.source in ("question", "learned")
        targets = a.targets or choice_targets(a.value)
        opts = frame.locator(self.OPTION_SEL)
        seen = []
        for i in range(min(opts.count(), 120)):
            try:
                if opts.nth(i).is_visible():
                    seen.append((i, opts.nth(i).inner_text(timeout=1000)))
            except Exception:
                continue
        if rule_key(a.f) != "phone_country_code":
            seen = [s for s in seen if not PHONE_CODE_OPTION.search(s[1])]  # Workday leaves the phone-code list open
        idx = option_match([t for _, t in seen], targets, strict=strict)
        if idx is None and any_option and seen:
            idx = 0
        if idx is None:
            return False
        safe_click(opts.nth(seen[idx][0]), "pick_option")
        clicked = seen[idx][1].strip()
        self.page.wait_for_timeout(800)
        # Workday multi-level prompts ("How did you hear": Job Board -> LinkedIn): a new list opens after the click
        for _depth in range(2):
            now = []
            for i in range(min(opts.count(), 120)):
                try:
                    if opts.nth(i).is_visible():
                        now.append((i, opts.nth(i).inner_text(timeout=1000)))
                except Exception:
                    continue
            if rule_key(a.f) != "phone_country_code":
                now = [s for s in now if not PHONE_CODE_OPTION.search(s[1])]
            if not now or [t for _, t in now] == [t for _, t in seen]:
                break
            now = [s for s in now if s[1].strip() != clicked] or now  # the sub-list repeats its category as a header
            sub = option_match([t for _, t in now], targets, strict=False)
            pick = now[sub][0] if sub is not None else now[0][0]  # any sub-source is fine (a formality)
            seen, clicked = now, (now[sub] if sub is not None else now[0])[1].strip()
            try:
                safe_click(opts.nth(pick), "pick_option")
            except Exception:
                break
            self.page.wait_for_timeout(800)
        return True

    def _listbox(self, loc, a):
        """Workday "Select One" button: open it, pick the option; for long lists type the first letters to scroll."""
        frame = self._frames[a.f["frame"]]
        safe_click(loc, "open_dropdown")
        self.page.wait_for_timeout(800)
        if self._pick_option(frame, a):
            return True
        for term in combo_terms(a.value)[:2]:
            try:
                self.page.keyboard.type(term[:12], delay=60)  # Workday listboxes jump to the typed text
                self.page.wait_for_timeout(700)
                if self._pick_option(frame, a):
                    return True
            except Exception:
                pass
        try:
            self.page.keyboard.press("Escape")
        except Exception:
            pass
        return False

    # ---- Workday: account step and multi-page navigation ----
    def is_workday(self):
        host = urlparse(self.url()).netloc.lower()
        if "myworkdayjobs.com" in host or "myworkdaysite.com" in host:
            return True
        try:
            return bool(self.page.evaluate("() => !!document.querySelector('[data-automation-id=\"workdayApplication\"],"
                                           " [data-automation-id=\"applyFlowPage\"], [data-automation-id=\"createAccountLink\"]')"))
        except Exception:
            return False

    def _visible(self, selector):
        loc = self.page.locator(selector)
        for i in range(min(loc.count(), 5)):
            if loc.nth(i).is_visible():
                return loc.nth(i)
        return None

    def _wd_button(self, name):
        """Workday covers its buttons with a transparent 'click_filter' div labelled like the button."""
        for sel in (f'[data-automation-id="click_filter"][aria-label="{name}"]',
                    f'[data-automation-id="{WD_BUTTON_IDS.get(name, "")}"]',
                    f'button:has-text("{name}")'):
            loc = self._visible(sel)
            if loc is not None:
                return loc
        return None

    def page_text(self):
        try:
            return self.page.evaluate("() => document.body ? document.body.innerText.slice(0, 20000) : ''")
        except Exception:
            return ""

    def workday_account(self, email, password):
        """Create the candidate account (or sign in if it exists). -> ok | no-password | verify-email | failed:<why>."""
        passwords = [password] if isinstance(password, str) or password is None else [p for p in password if p]
        password = passwords[0] if passwords else ""
        try:
            result = self._workday_account(email, password)
            for older in passwords[1:]:  # accounts Sai made himself earlier, with an older password
                if not re.search(r"wrong email address or password", result, re.I) or self._visible(
                        '[data-automation-id="password"]') is None:
                    break
                result = self._wd_credentials(email, older, creating=False)
            if self.inbox and (result == "verify-email" or re.search(r"wrong email address or password", result, re.I)):
                result = self._verify_from_inbox(email, password) or result
            return result
        except SubmitBlocked as e:
            return f"failed:{e}"

    def _verify_from_inbox(self, email, password, wait_s=240):
        """Open this company's Workday verification link from Sai's inbox, come back and sign in. None if no link."""
        apply_url = self.url()
        tenant = workday_tenant(apply_url)
        print(f"  looking in your inbox for {tenant}'s Workday verification email...", flush=True)
        deadline = time.monotonic() + wait_s
        link = None
        while not link and time.monotonic() < deadline:
            try:
                link = self.inbox.verify_link(tenant)
            except Exception as e:
                print(f"  (inbox check failed: {str(e)[:80]})")
                return None
            if not link:
                self.page.wait_for_timeout(20000)
        if not link:
            return None
        self._goto(link)  # opening the link verifies the account
        self.page.wait_for_timeout(3000)
        self._goto(apply_url)
        if self._wd_wait_state() != "auth":
            return None
        if self._visible('[data-automation-id="verifyPassword"]') is not None:
            sign_in = self._visible('[data-automation-id="signInLink"]')
            if sign_in is not None:
                safe_click(sign_in, "account")
                self._settle()
        return self._wd_credentials(email, password, creating=False)

    WD_AUTH = 'input[type="password"], [data-automation-id="createAccountLink"], [data-automation-id="signInLink"]'

    def _wd_wait_state(self, timeout_s=30):
        """Workday renders late: wait until the page shows a sign-in form ("auth") or an application page ("app")."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._visible(self.WD_AUTH) is not None:
                return "auth"
            email_btn = self._visible('[data-automation-id="SignInWithEmailButton"]')
            if email_btn is not None:  # KLA-style: Apple / Google / LinkedIn / "Sign in with email" first
                try:
                    safe_click(email_btn, "account")
                except SubmitBlocked:
                    pass
                self.page.wait_for_timeout(1500)
                continue
            step = self.workday_step()
            if step and not re.search(r"create account|sign in", step, re.I) and self._next_button() is not None:
                return "app"
            self.page.wait_for_timeout(1000)
        return "unknown"

    def _wd_press_apply(self):
        """Still on the job posting (it rendered after open() stopped waiting): press Apply, then Apply Manually."""
        draft = self._visible('[data-automation-id="continueButton"]')
        if draft is not None:  # an application started earlier: "Continue Application" links to the saved draft
            href = draft.get_attribute("href") or ""
            if href:
                self._goto(urljoin(self.url(), href))
                return True
        if self._visible('[data-automation-id="adventureButton"]') is None:
            return False
        # Apply only opens a menu (Autofill with Resume / Apply Manually / Use My Last Application): go straight to
        # the Apply Manually form, which is the posting URL + /apply/applyManually
        base = re.sub(r"/apply(/.*)?$", "", urlparse(self.url())._replace(query="", fragment="").geturl().rstrip("/"))
        self._goto(base + "/apply/applyManually")
        return True

    def _workday_account(self, email, password):
        state = self._wd_wait_state()
        if state == "unknown" and self._wd_press_apply():
            state = self._wd_wait_state(timeout_s=45)
        if state == "unknown":  # Workday sometimes stalls on first load (several browsers at once): reload once
            try:
                self.page.reload(wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass
            state = self._wd_wait_state(timeout_s=45)
            if state == "unknown" and self._wd_press_apply():
                state = self._wd_wait_state(timeout_s=45)
        if state == "app":
            return "ok"  # already signed in (persistent Chrome profile)
        if state == "unknown" and EXPIRED.search((self.page_text() or "")[:3000]):
            return "expired"  # "The page you are looking for doesn't exist" (Wolters Kluwer)
        if state == "unknown":
            self.diagnose("workday-" + (workday_tenant(self.url()) or "page"))
            return "failed:the Workday page didn't finish loading"
        if not password:
            return "no-password"
        creating = self._visible('[data-automation-id="verifyPassword"]') is not None
        link = self._visible('[data-automation-id="createAccountLink"]')
        if not creating and link is not None:
            safe_click(link, "account")
            self._settle()
            creating = self._visible('[data-automation-id="verifyPassword"]') is not None
        result = self._wd_credentials(email, password, creating)
        if creating and result.startswith("failed:") and self._visible('[data-automation-id="verifyPassword"]') is None:
            # Account created; Workday moved to its Sign In page: sign in with the new account.
            result = self._wd_credentials(email, password, creating=False)
        if result == "exists":
            link = self._visible('[data-automation-id="signInLink"]')
            if link is None:
                return "failed:account exists but no Sign In link"
            safe_click(link, "account")
            self._settle()
            result = self._wd_credentials(email, password, creating=False)
        for _ in range(2):  # Workday's sign-in often needs a second try (slow page, first click ignored)
            if result != "failed:still on the sign-in page" or self._visible('[data-automation-id="password"]') is None:
                break
            self.page.wait_for_timeout(3000)
            result = self._wd_credentials(email, password, creating=False)
        return result

    def _wd_credentials(self, email, password, creating):
        page = self.page
        for sel, val in (('[data-automation-id="email"]', email), ('[data-automation-id="password"]', password),
                         ('[data-automation-id="verifyPassword"]', password if creating else None)):
            loc = self._visible(sel)
            if loc is not None and val:
                loc.fill(val, timeout=6000)
                try:
                    if loc.input_value(timeout=2000) != val:  # React sign-in forms can drop a pasted value
                        loc.fill("", timeout=3000)
                        loc.press_sequentially(val, delay=40)
                except Exception:
                    pass
        if creating:
            box = self._visible('[data-automation-id="createAccountCheckbox"]')
            if box is not None and not box.is_checked():
                safe_click(box, "toggle")
        name = "Create Account" if creating else "Sign In"
        btn = self._wd_button(name)
        if btn is None:
            return f"failed:no {name} button"
        safe_click(btn, "account")
        page.wait_for_timeout(2500)
        self._settle()
        self._wd_wait_state(timeout_s=20)
        text = self.page_text()
        if re.search(r"already (exists|in use|registered)|account with this email", text, re.I):
            return "exists"
        if re.search(r"verify your (email|account)|verification (email|link)|check your (email|inbox)|"
                     r"(email|account) (is )?not (yet )?verified|activate your account", text, re.I):
            return "verify-email"
        if self._visible('input[type="password"]') is not None:
            err = self._visible('[data-automation-id="errorMessage"], [data-automation-id="inputAlert"], [role="alert"]')
            why = (err.inner_text(timeout=1000) if err is not None else "") or "still on the sign-in page"
            return "failed:" + re.sub(r"\s+", " ", why).strip()[:160]
        return "ok"

    WD_EMPTY_SECTIONS_JS = r"""() => {
      // Workday "My Experience": sections (Work Experience, Education) that have an Add button but no entry yet.
      const out = [];
      document.querySelectorAll('[data-automation-id="add-button"]').forEach((b, i) => {
        if (b.offsetParent === null) return;
        const group = b.closest('[role="group"], section, fieldset') || b.parentElement.parentElement;
        const head = (group.querySelector('h3, h4, legend') || {}).textContent || '';
        if (!/work experience|education/i.test(head)) return;
        const prefix = /work/i.test(head) ? 'workExperience-' : 'education-';
        if (!group.querySelector(`[id^="${prefix}"]`)) out.push(i);
      });
      return out;
    }"""

    def workday_wait_form(self, timeout_s=20):
        """Wait until the current Workday page shows its form fields (or the Review page)."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                n = self.page.evaluate("""() => {
                  const fields = [...document.querySelectorAll('[data-automation-id^="formField"], '
                    + '[data-automation-id="add-button"], [data-automation-id="reviewJobApplicationPage"]')]
                    .filter((e) => e.offsetParent !== null).length;
                  const step = (document.querySelector('[data-automation-id="progressBarActiveStep"]') || {}).textContent || '';
                  const footer = document.querySelector('[data-automation-id="pageFooterNextButton"]');
                  // the Review page has no form fields: there the step name plus the footer button is enough
                  return fields || (/review/i.test(step) && footer && footer.offsetParent !== null ? 1 : 0);
                }""")
            except Exception:
                n = 0
            if n:
                self.page.wait_for_timeout(800)  # let the rest of the page finish rendering
                return True
            self.page.wait_for_timeout(500)
        return False

    def workday_add_entries(self):
        """Open one Work Experience and one Education entry where the section is still empty. -> how many."""
        try:
            idx = self.page.evaluate(self.WD_EMPTY_SECTIONS_JS)
        except Exception:
            return 0
        buttons = self.page.locator('[data-automation-id="add-button"]')
        for i in reversed(idx):
            try:
                safe_click(buttons.nth(i), "add_entry")
                self.page.wait_for_timeout(1200)
            except Exception:
                pass
        return len(idx)

    def workday_step(self):
        """Name of the current application step, or ''. The progress bar's active step is screen-reader text (not
        "visible"), and the first visible h2 is the job title on every page, so read the step text directly."""
        try:
            text = self.page.evaluate("""() => {
              const a = document.querySelector('[data-automation-id="progressBarActiveStep"]');
              if (a && a.textContent.trim()) return a.textContent;
              return [...document.querySelectorAll('h2, h3')].filter((h) => h.offsetParent !== null)
                .map((h) => h.textContent.trim()).filter(Boolean).join(' / ');
            }""")
            return re.sub(r"\s+", " ", text or "").strip()
        except Exception:
            return ""

    def _next_button(self):
        for sel in ('[data-automation-id="bottom-navigation-next-button"]', '[data-automation-id="pageFooterNextButton"]'):
            loc = self._visible(sel)
            if loc is not None:
                return loc
        return self._wd_button("Save and Continue") or self._wd_button("Next")

    def workday_on_review(self):
        """The last page: its bottom button says Submit (Workday reuses the 'next' button for it)."""
        if re.search(r"review\b", self.workday_step(), re.I):  # "step 5 of 5Review": no space before it
            return True
        btn = self._next_button()
        try:
            return btn is not None and bool(SUBMIT_WORDS.search(btn.inner_text(timeout=1000)))
        except Exception:
            return False

    def workday_next(self, timeout_s=25):
        """Click 'Save and Continue'. -> moved | errors:<text> | no-button."""
        btn = self._next_button()
        if btn is None:
            return "no-button"
        before = self.workday_step()
        try:
            self.page.keyboard.press("Escape")  # an open dropdown (Country Phone Code) eats the first click otherwise
            self.page.wait_for_timeout(400)
        except Exception:
            pass
        try:
            safe_click(btn, "next_page")
        except SubmitBlocked as e:
            return f"errors:{e}"
        deadline = time.monotonic() + timeout_s
        clicked_again = False
        while time.monotonic() < deadline:
            self.page.wait_for_timeout(1000)
            if not clicked_again and time.monotonic() > deadline - timeout_s + 8 and self.workday_step() == before:
                clicked_again = True  # the first click only closed a popup: press Save and Continue once more
                again = self._next_button()
                if again is not None:
                    try:
                        safe_click(again, "next_page")
                    except Exception:
                        pass
            if self.workday_step() != before:
                self._settle()
                return "moved"
            err = self._visible('[data-automation-id="errorMessage"], [data-automation-id="errorBanner"], [role="alert"]')
            if err is not None:
                try:
                    text = err.inner_text(timeout=1000)
                except Exception:
                    text = ""
                if text.strip() and not re.search(r"success", text, re.I):  # "resume successfully uploaded" is a notice
                    return "errors:" + re.sub(r"\s+", " ", text).strip()[:200]
        text = re.sub(r"\s+", " ", self.page_text() or "")
        m = re.search(r"Errors? Found\s*(.{0,220})", text, re.I)
        if m:
            return "errors:" + m.group(1).strip()
        return "errors:the page did not change after Save and Continue"

    CODE_INPUTS_JS = r"""() => {
      const shown = (el) => { const r = el.getBoundingClientRect(); return r.width > 1 && r.height > 1; };
      document.querySelectorAll('[data-aa-code]').forEach((e) => e.removeAttribute('data-aa-code'));
      const inputs = [...document.querySelectorAll('input')]
        .filter((e) => shown(e) && !['hidden', 'checkbox', 'radio', 'file', 'submit', 'button'].includes((e.type || '').toLowerCase()))
        .filter((e) => /security|code|otp|verif/i.test([e.id, e.name, e.getAttribute('aria-label'), e.autocomplete].join(' ')));
      inputs.forEach((e, i) => e.setAttribute('data-aa-code', String(i)));
      return inputs.map((e) => e.maxLength);
    }"""

    def enter_security_code(self, code):
        """Type the emailed code into the site's code box (one box, or one box per character)."""
        for fr in list(self.page.frames):
            try:
                lens = fr.evaluate(self.CODE_INPUTS_JS)
            except Exception:
                continue
            if not lens:
                continue
            if len(lens) >= len(code) and all(n == 1 for n in lens[:len(code)]):
                for i, ch in enumerate(code):
                    fr.locator(f'[data-aa-code="{i}"]').fill(ch, timeout=5000)
            else:
                fr.locator('[data-aa-code="0"]').fill(code, timeout=5000)
            self.page.wait_for_timeout(800)
            return True
        return False

    def mark(self, items):
        by_frame = {}
        for f, color in items:
            if f is not None and f.get("frame") in self._frames:
                by_frame.setdefault(f["frame"], []).append([f["aid"], color])
        for i, lst in by_frame.items():
            try:
                self._frames[i].evaluate(MARK_JS, lst)
            except Exception:
                pass

    def state(self):
        st = {"url": self.url(), "captcha": False, "login": False, "errors": 0, "text": ""}
        for fr in self.page.frames:
            if CAPTCHA_FRAME_URL.search(fr.url or ""):
                st["captcha"] = st["captcha"] or bool(BOT_WALL_URL.search(fr.url or ""))
                continue
            try:
                s = fr.evaluate(STATE_JS)
            except Exception:
                continue
            st["captcha"] = st["captcha"] or s["captcha"]
            st["login"] = st["login"] or s["login"]
            st["errors"] += s["errors"]
            st["text"] += "\n" + s["text"]
        return st

    def confirmation(self):
        st = self.state()
        return detect_confirmation(st["text"], st["url"], self.start_url)

    def overlay(self, title, items, message, cont=False):
        self._overlay_args = {"title": title, "items": list(items), "message": message, "cont": cont}
        try:
            self.page.evaluate(OVERLAY_JS, self._overlay_args)
        except Exception:
            pass

    def diagnose(self, tag):
        """Screenshot + what a stuck page shows (visible automation ids, buttons, text) in runs/<date>/diag/."""
        try:
            out = RUNS_DIR / datetime.now().strftime("%Y-%m-%d") / "diag"
            out.mkdir(parents=True, exist_ok=True)
            stem = out / f"{datetime.now():%H%M%S}-{re.sub(r'[^a-z0-9]+', '-', tag.lower())[:50]}"
            self.page.screenshot(path=f"{stem}.png")
            Path(f"{stem}.json").write_text(json.dumps(self.page.evaluate(DIAG_JS), indent=1, ensure_ascii=False),
                                            encoding="utf-8")
        except Exception:
            pass

    def screenshot(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(path), full_page=True)

    # ---- the only place that presses Submit (explicit --submit path) ----
    def submit(self):
        if not self.submit_enabled:
            raise SubmitBlocked("Submit is disabled: run with --auto --submit to allow it.")
        for fr in list(self._frames.values()) or [self.page.main_frame]:
            try:
                label = fr.evaluate(FIND_SUBMIT_JS)
            except Exception:
                continue
            if label:
                safe_click(fr.locator('[data-aa-submit="1"]').first, "submit", submit_enabled=True)
                return True
        return False

    def wait_confirmation(self, timeout_s=30):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                ok, ref = self.confirmation()
                if ok:
                    return True, ref
                self.page.wait_for_timeout(1500)
            except Exception:
                time.sleep(1.5)
        return False, None

    # ---- waiting for Sai ----
    def _snapshot(self, tracked, snap):
        if tracked:
            snap.update(read_answers(self.scan(), tracked))

    def wait_continue(self, timeout_s, tracked=()):
        """-> (result, ref, snapshot); result: continue | confirmed | closed | timeout."""
        snap, deadline = {}, time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.page.is_closed():
                return "closed", None, snap
            try:
                self._snapshot(tracked, snap)
                ok, ref = self.confirmation()
                if ok:
                    return "confirmed", ref, snap
                if self.page.evaluate("() => window.__aaContinue === true"):
                    return "continue", None, snap
                if self._overlay_args and not self.page.evaluate("() => !!document.getElementById('aa-overlay')"):
                    self.page.evaluate(OVERLAY_JS, self._overlay_args)  # page navigated: put the button back
                self.page.wait_for_timeout(2000)
            except Exception:
                if self.page.is_closed():
                    return "closed", None, snap
                time.sleep(2)
        return "timeout", None, snap

    def wait_closed(self, tracked=()):
        snap = {}
        while not self.page.is_closed():
            try:
                self._snapshot(tracked, snap)
                self.page.wait_for_timeout(2000)
            except Exception:
                if self.page.is_closed():
                    break
                time.sleep(2)
        return snap


# =====================================================================================================
# Filling one page (works with the real driver and with test fakes)
# =====================================================================================================
@dataclass
class FillResult:
    fields: list
    filled: list
    todo: list
    tracked: list


def fill_page(driver, fc):
    fields = pick_form_fields(driver.scan())
    plan = plan_fields(fields, fc)
    filled, failed = driver.apply(plan.actions)
    todo = plan.todo + failed
    retry_filled, todo = retry_dropdowns_with_options(driver, fc, todo)
    filled += retry_filled
    driver.mark([(a.f, GREEN) for a in filled] + [(t.f, ORANGE) for t in todo])
    return FillResult(fields, filled, todo, tracked_from_todo(todo))


def retry_dropdowns_with_options(driver, fc, todo):
    """Required dropdowns still empty: their choices are only visible once opened, so read them and let the AI
    pick one (it can't invent an option). -> (newly filled actions, remaining todo)."""
    if not (fc.ai and hasattr(driver, "combo_options")):
        return [], todo
    actions, keep = [], []
    for t in todo:
        f = t.f
        if not (f and f.get("role") in ("combobox", "listbox") and is_required(f)):
            keep.append(t)
            continue
        options = [o for o in driver.combo_options(f) if o and not PLACEHOLDER_OPT.match(o.strip())]
        val = _ask_ai(fc, t.label, "select", options) if options else None
        idx = option_match(options, choice_targets(val)) if val else None
        if idx is None:
            keep.append(t)
            continue
        actions.append(Action(f, "combo", options[idx], "ai", t.label, [options[idx]]))
    if not actions:
        return [], todo
    filled, failed = driver.apply(actions)
    done = {a.f.get("aid") for a in filled}
    return filled, [t for t in keep if (t.f or {}).get("aid") not in done] + failed


def looks_like_application(fields):
    """A real first application page asks for an email or a resume; job-alert / search forms don't."""
    return any(f.get("type") == "file" or rule_key(f) == "email" for f in fields)


def check_page(driver):
    """(blocker reasons, missing required labels, page state) after filling."""
    fields = pick_form_fields(driver.scan())
    st = driver.state()
    return blockers(st, fields), missing_required(fields), st


WD_ACCOUNT_REASONS = {
    "no-password": "Workday needs an account: add workday_password to answers.yaml",
    "verify-email": "Workday sent you a verification email: click the link in it, then run this job again",
    "expired": "Posting closed (expired or no longer accepting applications)",
}


def fill_workday(driver, fc, email, password, max_pages=8):
    """Workday: account step, then fill each page and press 'Save and Continue' until the Review page (never Submit).
    -> (FillResult over all pages, blocker reasons, missing required labels, step names seen)."""
    account = driver.workday_account(email, password)
    if account != "ok" and hasattr(driver, "state") and EXPIRED.search((driver.state().get("text") or "")[:3000]):
        return FillResult([], [], [], []), ["Posting closed (expired or no longer accepting applications)"], [], []
    if account != "ok":
        reason = WD_ACCOUNT_REASONS.get(account) or f"Workday sign-in failed ({account.split(':', 1)[-1]})"
        if re.search(r"wrong email address or password", account, re.I):
            reason = ("Workday refused the sign-in. Usually the account still needs its email verified: click the link "
                      "in the company's 'verify your account' email, then run this job again")
        return FillResult([], [], [], []), [reason], [], []
    filled, steps, fill = [], [], FillResult([], [], [], [])
    for _ in range(max_pages):
        if hasattr(driver, "workday_wait_form"):
            driver.workday_wait_form()  # Workday renders each page late: reading, filling or clicking before that fails
        steps.append(driver.workday_step())
        if driver.workday_on_review():
            return FillResult(fill.fields, filled, [], []), [], [], steps
        if hasattr(driver, "workday_add_entries"):
            driver.workday_add_entries()
        fill = fill_page(driver, fc)
        filled += fill.filled
        reasons, missing, _st = check_page(driver)
        for _ in range(3):  # fields that appear only after another answer (address after Country, follow-up questions)
            if not (missing or fill.filled):
                break
            fill = fill_page(driver, fc)
            filled += fill.filled
            reasons, missing, _st = check_page(driver)
        # A page of only buttons/uploads (My Experience) is fine on Workday.
        reasons = [r for r in reasons if not r.startswith("No application form")]
        if reasons or missing:
            if missing and hasattr(driver, "diagnose"):
                driver.diagnose("workday-missing")
            return FillResult(fill.fields, filled, fill.todo, fill.tracked), reasons, missing, steps
        moved = driver.workday_next()
        if moved == "no-button" and hasattr(driver, "workday_wait_form"):
            # half-rendered page (several browsers at once): wait for it once more before giving up
            if getattr(driver, "page", None) is not None:
                driver.page.wait_for_timeout(8000)
            driver.workday_wait_form()
            moved = driver.workday_next()
        if moved == "no-button":
            if hasattr(driver, "diagnose"):
                driver.diagnose("workday-no-next")
            return FillResult(fill.fields, filled, fill.todo, fill.tracked), [
                f"Couldn't find Save and Continue (page: {(steps[-1] if steps else '')[:60]})"], [], steps
        if moved.startswith("errors:"):
            if hasattr(driver, "diagnose"):
                driver.diagnose("workday-errors")
            return FillResult(fill.fields, filled, fill.todo, fill.tracked), [f"Workday says: {moved[7:]}"], [], steps
    return FillResult(fill.fields, filled, fill.todo, fill.tracked), [f"More than {max_pages} pages"], [], steps


CODES_PATH = HERE / "security_codes.yaml"


def make_code_reader(path=CODES_PATH, sleep=time.sleep, clock=time.monotonic):
    """code_for(job, wait_s): the security code Sai pasted into security_codes.yaml for this Job Radar id (used
    once). Waits up to wait_s seconds for one to appear, so the form can stay open while the email arrives."""
    def code_for(job, wait_s=0):
        deadline = clock() + wait_s
        while True:
            codes = load_yaml(path)
            code = _s(codes.pop(str(job.get("id")), ""))
            if code:
                save_yaml(path, codes, "# Security codes the sites emailed after Submit, by Job Radar id. Used once.")
                return code
            if clock() >= deadline:
                return None
            sleep(5)
    return code_for


def is_workday(driver):
    return bool(getattr(driver, "is_workday", lambda: False)())


def workday_passwords(answers, path=ANSWERS_PATH):
    """The runner's Workday password first, then older ones Sai used for accounts he made himself
    (answers.yaml: workday_passwords_old)."""
    old = (answers or {}).get("workday_passwords_old") or []
    return [ensure_workday_password(answers, path)] + [_s(p) for p in ([old] if isinstance(old, str) else old) if _s(p)]


def ensure_site_password(key, path=ANSWERS_PATH):
    """A strong password with nothing personal in it (Avature rejects passwords containing the candidate's name),
    generated once per site family and appended to answers.yaml. Never printed."""
    pw = _s((load_yaml(path) or {}).get(key))
    if pw:
        return pw
    import secrets
    import string
    pw = "Qx" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(14)) + "9#"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f'\n# Password for {key.split("_")[0].title()} candidate profiles the runner creates.\n{key}: "{pw}"\n')
    print(f"Created a password for {key.split('_')[0].title()} profiles and saved it in {Path(path).name} ({key}).")
    return pw


def ensure_workday_password(answers, path=ANSWERS_PATH):
    """One strong password for every Workday candidate account, generated once and appended to answers.yaml.
    Never printed: open answers.yaml to see it."""
    pw = _s((answers or {}).get("workday_password"))
    if pw:
        return pw
    import secrets
    import string
    body = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(14))
    pw = f"Wd{body}7!"  # Workday wants upper, lower, digit and a special character
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f'\n# Password for the Workday candidate accounts the runner creates (one per company site).\n'
                 f'workday_password: "{pw}"\n')
    answers["workday_password"] = pw
    print(f"Created a Workday password and saved it in {Path(path).name} (workday_password).")
    return pw


# =====================================================================================================
# Runner: --auto (dry run or --submit) and --harvest
# =====================================================================================================
AUTO_SUBMIT_BOARDS = {"greenhouse", "lever", "ashby", "smartrecruiters", "workday"}


def known_ats(job):
    """True for application systems the runner knows how to submit and confirm (it may press Submit there)."""
    url = job.get("url") or ""
    kind = application_url(url, job.get("company"), {})[1] if url else "other"
    return kind in AUTO_SUBMIT_BOARDS or (job.get("board") or "").lower() in AUTO_SUBMIT_BOARDS or         "myworkdayjobs.com" in url or "smartrecruiters.com" in url or "careers.qualcomm.com" in url or         "oraclecloud.com" in url or "higher.gs.com" in url or bool(ORACLE_CX.search(url))  # Qualcomm: confirmed by email; Oracle CX flow taught 2026-10-19


NO_HANDOFF = re.compile(r"No application form found|Doesn't look like an application form|blocked this browser|"
                        r"down for maintenance|Workday sign-in failed|Workday refused|Workday sent you a verification|"
                        r"Workday needs an account|More than \d+ pages|Couldn't find Save and Continue", re.I)
SUBMITTED_NOTE = "Submitted by auto-apply (confirmed page)"
SAI_SUBMITTED_NOTE = "Submitted by Sai after an apply-runner hand-off (confirmed page)"


class RunLog:
    def __init__(self, runs_dir=RUNS_DIR, today=None):
        self.dir = Path(runs_dir) / (today or datetime.now().strftime("%Y-%m-%d"))
        self.dir.mkdir(parents=True, exist_ok=True)

    def write(self, entry):
        with open(self.dir / "log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": _iso(), **entry}, ensure_ascii=False) + "\n")

    def needs_you(self, entry):
        p = self.dir / "needs_you.json"
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        data.append({"ts": _iso(), **entry})
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class SubmitGate:
    """One Submit at a time across parallel workers, at least `pace` seconds apart (sites rate-limit applicants who
    submit in bursts: 5 workers at once got "temporarily restricted"). Filling forms stays parallel."""

    STALE_S = 900

    def __init__(self, path, pace=(180, 420), sleep=time.sleep, now=time.time, rng=None):
        self.lock, self.last = Path(str(path) + ".lock"), Path(str(path) + ".last")
        self.pace, self.sleep, self.now, self.rng = pace, sleep, now, rng or random.Random()

    def _acquire(self):
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                os.close(os.open(str(self.lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return
            except FileExistsError:
                try:
                    if self.now() - self.lock.stat().st_mtime > self.STALE_S:
                        self.lock.unlink()  # a worker died holding it
                        continue
                except FileNotFoundError:
                    continue
                self.sleep(2)

    def turn(self):
        from contextlib import contextmanager

        @contextmanager
        def _turn():
            self._acquire()
            try:
                try:
                    last = float(self.last.read_text())
                except (OSError, ValueError):
                    last = 0.0
                wait = last + self.rng.uniform(*self.pace) - self.now()
                if wait > 0:
                    print(f"  waiting {int(wait)} s before submitting (one submission at a time)", flush=True)
                    self.sleep(wait)
                yield
            finally:
                self.last.write_text(str(self.now()))
                try:
                    self.lock.unlink()
                except FileNotFoundError:
                    pass
        return _turn()


class Runner:
    def __init__(self, api, driver, context_for, *, submit=False, max_jobs=25, per_company=1,
                 handoff_wait_s=1800, ask_timeout_s=600, poll_s=15, pending=None, pending_path=PENDING_PATH,
                 learned=None, learned_path=LEARNED_PATH, harvest_first=True, emailer=None, log=None,
                 sleep=time.sleep, clock=time.monotonic, rng=None, pace=(90, 240), confirm_wait_s=30,
                 workday_password="", code_for=None, code_wait_s=600, attended=False, gate=None, tailor=None):
        self.api, self.d, self.context_for = api, driver, context_for
        self.tailor = tailor  # tailor(job, posting_text) -> resume PDF bytes worded for this posting, or None
        self._posting, self._base_resume = "", None
        self.workday_password = workday_password
        self.code_for = code_for  # code_for(job, wait_s) -> the security code the site emailed, or None
        self.code_wait_s = code_wait_s
        self.attended = attended
        self.gate = gate  # SubmitGate shared by parallel workers
        self.submit, self.max_jobs, self.per_company = submit, max_jobs, per_company
        self.handoff_wait_s, self.ask_timeout_s, self.poll_s = handoff_wait_s, ask_timeout_s, poll_s
        self.pending = pending if pending is not None else {}
        self.pending_path, self.learned_path = pending_path, learned_path
        self.learned = learned if learned is not None else QuestionBank()
        self.harvest_first = harvest_first
        self.emailer = emailer or (lambda subject, body: False)
        self.log = log
        self.sleep, self.clock, self.rng, self.pace = sleep, clock, rng or random.Random(), pace
        self.confirm_wait_s = confirm_wait_s
        self.results, self.rows = [], []
        self.learned_today = []
        self.ai_today = []
        self.started_at = _iso()

    # ---- bookkeeping ----
    def _record(self, job, outcome, **extra):
        entry = {"job_id": job.get("id"), "company": job.get("company"), "role": job.get("role"),
                 "url": job.get("url"), "outcome": outcome, **extra}
        self.results.append(entry)
        if self.log:
            self.log.write(entry)
        print(f"  -> {outcome}" + (f": {extra.get('reason')}" if extra.get("reason") else ""))
        return entry

    def _learn(self, job, snap):
        for key, a in (snap or {}).items():
            k = self.learned.learn(a["question"], a["answer"], a.get("type"), a.get("options"),
                                   job.get("company"), job.get("role"))
            if k:
                self.learned_today.append({"question": a["question"], "answer": a["answer"]})
                self.pending.pop(k, None)
        if snap and self.learned_path:
            save_yaml(self.learned_path, self.learned.entries, "# Answers learned from what Sai typed after hand-offs.")

    def _is_pending(self, label, company):
        nq = norm_question(label)
        for k, e in self.pending.items():
            base = k.split("::", 1)[-1]
            if e.get("company_specific") and norm_question(e.get("company")) != norm_question(company):
                continue
            if base == nq or jaccard(base, nq) >= QuestionBank.THRESHOLD:
                return True
        return False

    # ---- hand-off through the server (email with "Complete it now" / "Later") ----
    def handoff(self, job, reasons, fill):
        missing = [t.label for t in fill.todo] if fill else []
        reason = "; ".join(reasons)
        # A hand-off record (and its "Need you" email) only when someone will answer it: with --ask-timeout 0 the job
        # is just logged for later (Sai found the per-job emails unnecessary)
        hid = None if self.attended or not self.ask_timeout_s else \
            self.api.create_handoff(job, reason, missing or reasons, url=self.d.url())
        choice = "now" if self.attended else "pending"  # attended: Sai is at the laptop, bring the window straight up
        if hid:
            deadline = self.clock() + self.ask_timeout_s
            while True:
                choice = self.api.handoff_choice(hid)
                if choice in ("now", "later") or self.clock() >= deadline:
                    break
                self.sleep(self.poll_s)
        if choice == "now":
            self.d.show()
            self.d.overlay(f"Need you: {job.get('company')} — {job.get('role')}", reasons,
                           "Finish the orange parts, then click ✅ I finished — continue.", cont=True)
            result, ref, snap = self.d.wait_continue(self.handoff_wait_s, fill.tracked if fill else [])
            self._learn(job, snap)
            self.d.hide()
            if result in ("continue", "confirmed"):
                return result, ref
            why = "no Continue within the hand-off wait" if result == "timeout" else "window closed"
        else:
            why = "you chose Later" if choice == "later" else "no answer to the hand-off email"
        if self.log:
            self.log.needs_you({"job_id": job.get("id"), "company": job.get("company"), "role": job.get("role"),
                                "url": job.get("url"), "reasons": reasons, "missing": missing, "why": why})
        self.d.reset()
        return "later", why

    # ---- one job ----
    def _min_quals(self, job):
        """Read the posting before opening the form (Sai: 'see min quals before opening the link'). -> reason or None."""
        if not hasattr(self.d, "_goto") or not job.get("url"):
            return None
        try:
            self.d._goto(job["url"])
            self._posting = self.d.page_text() or ""
            return min_quals_problem(self._posting)
        except Exception:
            return None  # can't read it: let the normal flow decide

    def _use_tailored_resume(self, job):
        """Upload a resume worded for this posting (Sai's ask); the original resume.pdf on any failure."""
        if not self.tailor or not hasattr(self.d, "resume"):
            return
        if self._base_resume is None:
            self._base_resume = self.d.resume
        pdf = None
        try:
            pdf = self.tailor(job, self._posting) if len(self._posting) >= 300 else None
        except Exception as e:
            print(f"  (resume tailoring failed, using the original: {str(e)[:80]})")
        self.d.resume = pdf or self._base_resume

    def run_job(self, job):
        self._posting = ""
        problem = self._min_quals(job)
        if problem:
            return self._record(job, "skipped", reason=f"min qualifications: {problem}")
        self._use_tailored_resume(job)
        try:
            note = self.d.open(job)
        except Exception as e:
            return self._record(job, "failed", reason=f"could not open the page ({str(e)[:80]})")
        fill, reasons, missing = self._fill_and_check(job)
        filled_n = len(fill.filled)
        if any(r.startswith("Posting closed") for r in reasons):
            self.d.reset()
            return self._record(job, "expired", reason=reasons[0])
        if not self.submit:  # dry run: report only, never press Submit
            self.rows.append(self._row(job, fill, reasons, missing))
            self.d.reset()
            if reasons or missing:
                return self._record(job, "needs-you", reason="; ".join(reasons + [f"required: {m}" for m in missing]),
                                    missing=missing, filled=filled_n, dry_run=True, how=note)
            return self._record(job, "ready", filled=filled_n, dry_run=True, how=note)
        # Questions already in the pending batch wait for Sai's answers (no per-job hand-off email).
        if not reasons and missing and all(self._is_pending(m, job.get("company")) for m in missing):
            self.d.reset()
            return self._record(job, "waiting-answers", reason="pending questions: " + "; ".join(missing),
                                missing=missing, filled=filled_n)
        if not reasons and not missing and not known_ats(job):
            # Unfamiliar site: a "thank you" can come from a talent-network or job-alert form. Sai submits it himself.
            reasons = ["Unfamiliar application site: check the form and press Submit yourself"]
        if any(r.startswith("Posting closed") for r in reasons):
            self.d.reset()
            return self._record(job, "expired", reason=reasons[0])
        if reasons and not missing and all(NO_HANDOFF.search(r) for r in reasons):
            # Nothing Sai can fix in the window (unsupported site, blocked, Workday down/sign-in): list it and move on.
            self.d.reset()
            return self._record(job, "needs-you", reason="; ".join(reasons), filled=filled_n)
        clicks = 0
        while True:
            if reasons or missing:
                result, ref = self.handoff(job, reasons + [f"required: {m}" for m in missing], fill)
                if result == "confirmed":
                    return self._confirmed(job, ref, by_sai=True)
                if result != "continue":
                    return self._record(job, "needs-you", reason="; ".join(reasons + missing), missing=missing,
                                        why=ref, filled=filled_n)
                ok, ref = self.d.confirmation()
                if ok:
                    return self._confirmed(job, ref, by_sai=True)
                if not known_ats(job):  # only Sai presses Submit on an unfamiliar site
                    self.d.reset()
                    return self._record(job, "needs-you", filled=filled_n,
                                        reason="unfamiliar site: no application confirmation after you continued")
                reasons, missing, _st = check_page(self.d)
                if reasons or missing:
                    self.d.reset()
                    return self._record(job, "needs-you", reason="still incomplete after Continue: "
                                        + "; ".join(reasons + missing), missing=missing, filled=filled_n)
            if clicks >= 2:
                self.d.reset()
                return self._record(job, "unconfirmed", reason="no confirmation page after Submit", filled=filled_n)
            clicks += 1
            if self.gate:  # parallel workers: one Submit at a time, spaced out
                with self.gate.turn():
                    pressed = self.d.submit()
            else:
                pressed = self.d.submit()
            if not pressed:
                reasons, fill = ["Couldn't find the form's Submit button"], None
                continue
            ok, ref = self.d.wait_confirmation(self.confirm_wait_s)
            if ok:
                return self._confirmed(job, ref)
            st = self.d.state()
            if SECURITY_CODE.search(st.get("text") or ""):
                # Greenhouse emails a code after Submit; the application only goes through once it's typed in.
                done = self._await_security_code(job)
                if done:
                    return done
                self.d.reset()
                return self._record(job, "needs-you", filled=filled_n,
                                    reason=f"security code not entered within {self.code_wait_s // 60} min")
            if re.search(r"\d+ issues? that need to be fixed|this info is required", st.get("text") or "", re.I):
                st["errors"] = st.get("errors") or 1  # Oracle's banner: "You have 7 issues that need to be fixed"
                st["errtext"] = (st.get("errtext") or []) + ["Oracle: required questions / sections still empty"]
            if st.get("captcha") or st.get("errors"):
                reasons = (["CAPTCHA appeared after Submit"] if st.get("captcha") else []) + \
                          ([("The site flagged errors after Submit: " + "; ".join(st.get("errtext") or []))[:300]]
                           if st.get("errors") else [])
                missing = []
                continue
            page = self._evidence(job, st)
            self.d.reset()
            return self._record(job, "unconfirmed", reason="no confirmation page after Submit", filled=filled_n,
                                page=page)

    def _try_code(self, job, code):
        """Type a code into the site's code box and submit. -> the 'submitted' record, or None."""
        if not (code and hasattr(self.d, "enter_security_code") and self.d.enter_security_code(code)):
            return None
        print(f"  entered a security code for {job.get('company')}", flush=True)
        if self.d.submit():
            ok, ref = self.d.wait_confirmation(self.confirm_wait_s)
            if ok:
                return self._confirmed(job, ref)
        return None

    def _await_security_code(self, job):
        """The site emailed Sai a code after Submit (a new one on every Submit). Works without anyone orchestrating:
        the window comes up so Sai can type the code into the site's own box and press Submit; a code pasted into
        security_codes.yaml is entered too. Returns the 'submitted' record, or None after code_wait_s."""
        code = self.code_for(job, wait_s=0) if self.code_for else None  # saved earlier: may be stale
        done = self._try_code(job, code)
        if done:
            return done
        self.d.show()
        self.d.overlay(f"Security code needed: {job.get('company')}", [],
                       "Check your email for the security code, type it in the code box on this page and press "
                       "Submit. The runner notices the confirmation and carries on by itself.")
        print(f"\a  WAITING up to {self.code_wait_s // 60} min: type the security code {job.get('company')} emailed you "
              f"into the Chrome window (or put it under '{job.get('id')}' in security_codes.yaml)", flush=True)
        deadline = self.clock() + self.code_wait_s
        while self.clock() < deadline:
            ok, ref = self.d.confirmation()
            if ok:
                self.d.hide()
                return self._confirmed(job, ref, by_sai=True)
            done = self._try_code(job, self.code_for(job, wait_s=0) if self.code_for else None)
            if done:
                self.d.hide()
                return done
            self.sleep(5)
        self.d.hide()
        return None

    def _evidence(self, job, st):
        """What the page showed after Submit (text excerpt; screenshot saved next to the run log)."""
        if self.log and hasattr(self.d, "screenshot"):
            try:
                self.d.screenshot(self.log.dir / f"after_submit_{job.get('id')}.png")
            except Exception:
                pass
        return re.sub(r"\s+", " ", st.get("text") or "").strip()[:400]

    def _confirmed(self, job, ref, by_sai=False):
        link = {} if job.get("id") else {"job": job}  # a pasted link: Job Radar adds the posting first
        ok, msg = self.api.confirm_applied(job.get("id"), SAI_SUBMITTED_NOTE if by_sai else SUBMITTED_NOTE, ref, **link)
        self.d.reset()
        return self._record(job, "submitted", ref=ref, by_sai=by_sai, marked_applied=ok,
                            reason=None if ok else f"confirm-applied failed: {msg}")

    def _fill_and_check(self, job):
        if hasattr(self.d, "_oracle_start") and ORACLE_CX.search(self.d.url() or ""):
            self.d._oracle_start(job)  # reached Oracle late (Goldman Sachs redirects): email step / emailed code
        fc = self.context_for(job)
        if hasattr(self.d, "_avature_account") and AVATURE_LOGIN.search(self.d.url() or ""):
            pws = [ensure_site_password("avature_password")] + list(self.workday_password or [])
            print("  Avature: " + self.d._avature_account(fc.values, pws), flush=True)
        workday = is_workday(self.d)
        if workday:
            fill, reasons, missing, _steps = fill_workday(self.d, fc, fc.values.get("email"), self.workday_password)
        else:
            fill = fill_page(self.d, fc)
            reasons, missing, _st = check_page(self.d)
        for key in fc.used_learned:
            self.learned.mark_used(key)
        self.ai_today += [dict(a, company=job.get("company")) for a in fc.ai_used]
        if not workday and not reasons and not looks_like_application(fill.fields):
            reasons.append("Doesn't look like an application form (no email or resume field)")
        if any(r.startswith(("No application form", "Doesn't look like")) for r in reasons) and re.search(
                r"verification code|confirm your identity|one[- ]time (pass)?code",
                (self.d.page_text() if hasattr(self.d, "page_text") else "") or "", re.I):
            # an emailed-code step (Goldman Sachs / Oracle): not a dead end - Sai can type the code in the window
            reasons = ["Enter the verification code from your email, then finish the form"]
        return fill, reasons, missing

    @staticmethod
    def _row(job, fill, reasons, missing):
        by_label = {t.label: t for t in fill.todo}
        return {"job": job, "blockers": reasons,
                "missing": [{"question": m, "type": by_label[m].ftype if m in by_label else "text",
                             "options": by_label[m].options if m in by_label else []} for m in missing]}

    # ---- the loop ----
    def run(self, jobs):
        work, skipped = plan_queue(jobs, self.max_jobs, self.per_company)
        for job, why in skipped:
            self._record(job, "skipped", reason=why)
        if self.harvest_first and self.submit:
            self.harvest(work)  # ask Sai all unanswered questions in one email before submitting anything
        retry = []
        for n, job in enumerate(work, 1):
            print(f"[{n}/{len(work)}] {job.get('company')} - {job.get('role')}")
            out = self._attempt(job)
            if out["outcome"] in ("needs-you", "failed") and TRANSIENT.search(str(out.get("reason") or "")):
                retry.append(job)
            if out["outcome"] in ("submitted", "unconfirmed") and not out.get("by_sai") and n < len(work) and not self.gate:
                self.sleep(self.rng.uniform(*self.pace))  # pacing between submissions (the gate paces parallel runs)
        for n, job in enumerate(retry, 1):  # page-loading problems usually pass on a second try (network blips)
            print(f"[retry {n}/{len(retry)}] {job.get('company')} - {job.get('role')}")
            self._attempt(job)
        if self.harvest_first and not self.submit:
            self._write_pending(self.rows)  # the dry run doubles as the harvest pass
        elif self.submit and not self.harvest_first:
            self._write_pending(self.rows)  # Sai: mail me the basic questions the runner couldn't answer
        return self.results

    def _attempt(self, job):
        try:
            return self.run_job(job)
        except SubmitBlocked:
            raise
        except Exception as e:
            try:
                self.d.reset()
            except Exception:
                pass
            return self._record(job, "failed", reason=str(e).splitlines()[0][:120])

    # ---- harvest: collect unanswered required questions in one batch (never submits) ----
    def harvest(self, jobs, record=False):
        rows = []
        for n, job in enumerate(jobs, 1):
            print(f"[harvest {n}/{len(jobs)}] {job.get('company')} - {job.get('role')}")
            try:
                self.d.open(job)
                fill, reasons, missing = self._fill_and_check(job)
                row = self._row(job, fill, reasons, missing)
            except Exception as e:
                row = {"job": job, "blockers": [f"failed: {str(e).splitlines()[0][:80]}"], "missing": []}
            finally:
                self.d.reset()
            rows.append(row)
            if record:
                left = row["blockers"] + [f"required: {m['question']}" for m in row["missing"]]
                self._record(job, "needs-you" if left else "ready", reason="; ".join(left),
                             missing=[m["question"] for m in row["missing"]], harvest=True)
        return self._write_pending(rows), rows

    def _write_pending(self, rows):
        before = set(self.pending)
        self.pending = collect_pending(rows, self.pending)
        if self.pending_path:
            save_yaml(self.pending_path, self.pending, "# Required questions the runner could not answer. "
                      "Answer them with: python tools/apply_assist/assist.py --setup --pending")
        if set(self.pending) - before:  # email once per batch of new questions
            self.emailer(*compose_pending_email(self.pending, len(unblockable_jobs(rows))))
        return self.pending

    # ---- end of run ----
    def summary(self, mode):
        return compose_summary(self.results, self.learned_today, mode, self.ai_today)

    def report(self, mode):
        return build_report(self.results, self.learned_today, mode, self.started_at, _iso())


def compose_summary(results, learned, mode="auto", ai=None):
    by = lambda o: [r for r in results if r["outcome"] == o]  # noqa: E731
    submitted, needs = by("submitted"), by("needs-you") + by("waiting-answers")
    unconf, failed = by("unconfirmed"), by("failed") + by("skipped")
    ready = by("ready")
    subject = f"Apply runner: {len(submitted)} submitted, {len(needs)} need you" + (" (dry run)" if mode == "dry-run" else "")
    lines = []

    def section(title, rows, fmt):
        lines.append(f"{title} ({len(rows)})")
        lines.extend(fmt(r) for r in rows)
        if not rows:
            lines.append("  none")
        lines.append("")

    section("Submitted (confirmed)", submitted,
            lambda r: f"  - {r['company']} - {r['role']}: {r['url']}" + (f" (ref {r['ref']})" if r.get("ref") else ""))
    section("Needs you", needs, lambda r: f"  - {r['company']} - {r['role']}: {r['url']}\n    left: {r.get('reason') or ''}")
    section("Submitted but no confirmation page - check these", unconf,
            lambda r: f"  - {r['company']} - {r['role']}: {r['url']}")
    if ready:
        section("Ready to submit (dry run, nothing was submitted)", ready, lambda r: f"  - {r['company']} - {r['role']}: {r['url']}")
    section("Skipped / failed", failed, lambda r: f"  - {r['company']} - {r['role']}: {r.get('reason') or r['outcome']}")
    if learned:
        lines.append("Learned from you today (fix them in tools/apply_assist/learned_answers.yaml if wrong):")
        lines.extend(f"  - {x['question']}: {x['answer']}" for x in learned)
    if ai:
        lines.append("Answered by AI (check them; fix in tools/apply_assist/ai_answers.yaml):")
        lines.extend(f"  - {x.get('company')}: {x['question'][:120]} -> {x['answer'][:160]}" for x in ai)
    if needs and any(r["outcome"] == "waiting-answers" for r in needs):
        lines += ["", "Answer the pending questions with: python tools/apply_assist/assist.py --setup --pending"]
    return subject, "\n".join(lines).rstrip() + "\n"


def build_report(results, learned, mode, started_at, finished_at):
    """JSON for /api/jobs/runner-report. Learned answers to personal questions are sent as question text only."""
    def job(r, *keys):
        return {k: r.get(k) for k in ("job_id", "company", "role", "url", *keys)}
    by = lambda o: [r for r in results if r["outcome"] == o]  # noqa: E731
    return {
        "started_at": started_at, "finished_at": finished_at, "mode": mode,
        "submitted": [job(r, "ref") for r in by("submitted")],
        "needs_you": [dict(job(r), missing=r.get("missing") or [r.get("reason")]) for r in by("needs-you") + by("waiting-answers")],
        "unconfirmed": [job(r) for r in by("unconfirmed")],
        "failed": [{"company": r.get("company"), "role": r.get("role"), "reason": r.get("reason")}
                   for r in by("failed") + by("skipped")],
        "learned": [{"question": x["question"]} if PERSONAL.search(x["question"]) else
                    {"question": x["question"], "answer": x["answer"]} for x in learned],
    }


# =====================================================================================================
# CLI
# =====================================================================================================
def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env")
    except ImportError:
        pass


class LazyPack(dict):
    """The job's answer pack (cover note, why this company), fetched only when a form has a free-text question that
    needs it: generating it can take a minute, and most forms never use it."""

    def __init__(self, loader):
        super().__init__()
        self._loader, self._loaded = loader, False

    def _load(self):
        if not self._loaded:
            self._loaded = True
            self.update(self._loader() or {})

    def __bool__(self):
        self._load()
        return dict.__len__(self) > 0

    def get(self, key, default=None):
        self._load()
        return dict.get(self, key, default)

    def __getitem__(self, key):
        self._load()
        return dict.__getitem__(self, key)


def _fill_context_factory(api, profile, answers, learned, resume, use_ai=True):
    questions = QuestionBank((answers or {}).get("questions") or {})
    packs = {}
    ai = make_ai_answerer(build_values(profile, answers)) if use_ai else None

    def make(job):
        if job.get("id") not in packs:
            jid = job.get("id")
            packs[jid] = LazyPack(lambda: api.pack(jid)) if jid else {}
        return FillContext(values=build_values(profile, answers, job.get("role_type"), job.get("role") or ""), company=job.get("company") or "",
                           custom=(answers or {}).get("custom") or [], questions=questions, learned=learned,
                           pack=packs[job.get("id")], resume=bool(resume), ai=ai, role=job.get("role") or "")
    return make


def _print_jobs(jobs):
    for i, j in enumerate(jobs, 1):
        ctc = j.get("est_ctc") or (f"{j['ctc_lpa']} LPA" if j.get("ctc_lpa") else "CTC ?")
        print(f"{i:>2}. [{j.get('match_score')}] {j.get('company')} - {j.get('role')}  ({j.get('location')}; {ctc}; "
              f"posted {j.get('posted') or '?'}; id {j.get('id')})")


def choose_job(api, args):
    if args.job:
        for j in api.all_live():
            if str(j.get("id")) == str(args.job):
                return j
        sys.exit(f"Job {args.job} is not in the live list.")
    jobs = select_jobs(api.live_jobs(args.min_score, args.min_ctc), args.min_score, args.min_ctc)
    if not jobs:
        sys.exit("No open jobs match the filters right now.")
    if args.next:
        return jobs[0]
    top = jobs[:10]
    _print_jobs(top)
    raw = input("\nWhich one? (1-10, Enter = 1): ").strip() or "1"
    if not raw.isdigit() or not 1 <= int(raw) <= len(top):
        sys.exit("No job picked.")
    return top[int(raw) - 1]


def run_assist(args, api, answers, learned):
    from playwright.sync_api import sync_playwright
    job = choose_job(api, args)
    print(f"\nJob: {job['company']} - {job['role']}\n     {job['url']}")
    profile = (api.radar() or {}).get("profile") or {}
    resume = ensure_resume(api)
    make_fc = _fill_context_factory(api, profile, answers, learned, resume, use_ai=not args.no_ai)
    log = RunLog()
    with sync_playwright() as pw:
        ctx = launch(pw, headless=args.headless, visible=args.visible, profile=getattr(args, "profile_dir", None))
        d = PlaywrightDriver(ctx, headless=args.headless, visible=args.visible, resume=resume,
                             resume_name=_resume_name(profile, answers), gh_tokens=greenhouse_tokens())
        d.hide()
        note = d.open(job)
        fc = make_fc(job)
        if d.is_workday():
            password = workday_passwords(answers, Path(args.answers) if args.answers else ANSWERS_PATH)
            fill, reasons, missing, steps = fill_workday(d, fc, fc.values.get("email"), password)
            note += " (Workday: " + " -> ".join(s for s in steps if s) + ")"
        else:
            fill = fill_page(d, fc)
            reasons, missing, _st = check_page(d)
        still = reasons + list(dict.fromkeys([t.label for t in fill.todo] + missing))
        d.overlay(f"Filled {len(fill.filled)} fields", still,
                  "Review everything, then press the site's Submit button yourself.")
        print(f"Opened via: {note}\nFilled {len(fill.filled)} fields:")
        for a in fill.filled:
            print(f"  + {a.label[:70]}  <- {a.source}")
        print("Still for you:" if still else "Nothing left that the tool knows of.")
        for s in still:
            print(f"  - {s[:90]}")
        log.write({"job_id": job["id"], "company": job["company"], "role": job["role"], "url": job["url"],
                   "outcome": "assist", "filled": [a.label for a in fill.filled], "left": still})
        if args.headless:
            shot = Path(args.screenshot or RUNS_DIR / "demo.png")
            d.screenshot(shot)
            print(f"Screenshot: {shot}")
            ctx.close()
            return
        d.show()
        print("\nThe application is open in Chrome. Review it, press Submit yourself, then close the window.")
        snap = d.wait_closed(fill.tracked)
        try:
            ctx.close()
        except Exception:
            pass
    if snap:
        for a in snap.values():
            learned.learn(a["question"], a["answer"], a.get("type"), a.get("options"), job["company"], job["role"])
        save_yaml(LEARNED_PATH, learned.entries, "# Answers learned from what Sai typed.")
    if input("Did you submit? (y/n) ").strip().lower().startswith("y"):
        ok, msg = api.confirm_applied(job["id"], "Submitted by Sai via apply assist")
        print("Marked as applied in Job Radar." if ok else f"Could not mark it applied: {msg}")


def make_tailor():
    """tailor(job, posting_text) -> PDF bytes via tailor_resume.py; each tailored copy and its changes are saved in
    runs/<date>/resumes/ for Sai to check."""
    import tailor_resume
    generate = tailor_resume.default_generate()
    out_dir = RUNS_DIR / datetime.now().strftime("%Y-%m-%d") / "resumes"

    def tailor(job, text):
        pdf, changes = tailor_resume.tailored_pdf(text, job.get("role") or "", job.get("company") or "",
                                                  generate=generate, out_dir=out_dir)
        if pdf:
            print(f"  resume worded for this posting ({len(changes)} changes)")
        return pdf
    return tailor


def _resume_name(profile, answers):
    name = _s((answers or {}).get("full_name")) or _s((profile or {}).get("full_name")) or "Resume"
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") + "_Resume.pdf"


def attempted_from_logs(days=7, runs_dir=RUNS_DIR, now=None):
    """Jobs the runner submitted or tried to submit in the last `days` days (latest entry per job id)."""
    now, out = now or _now(), {}
    for log in sorted(Path(runs_dir).glob("*/log.jsonl")):
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            ts = _parse_ts(e.get("ts"))
            if e.get("job_id") and ts and now - ts <= timedelta(days=days) and                     e.get("outcome") in ("submitted", "unconfirmed", "needs-you"):
                out[e["job_id"]] = {"id": e["job_id"], "company": e.get("company"), "role": e.get("role"), "url": e.get("url")}
    return list(out.values())


def run_sync_email(api, answers):
    inbox = make_inbox(_s(answers.get("email")) or "sairaghava1318@gmail.com")
    if not inbox:
        sys.exit("Add GMAIL_APP_PASSWORD to .env first.")
    n = sync_email_confirmations(api, inbox, attempted_from_logs(), RunLog())
    print(f"{n} application(s) marked applied from confirmation emails.")


def held_companies(path=HOLD_PATH):
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {_norm(l.split("#")[0]) for l in lines if _norm(l.split("#")[0])}


def shard_of(company, n):
    import zlib
    return zlib.crc32(_norm(company).encode()) % n


def strip_option(argv, name):
    """argv without `name VALUE` / `name=VALUE`."""
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
        elif a == name:
            skip = True
        elif not a.startswith(name + "="):
            out.append(a)
    return out


def run_parallel(argv, n):
    """Start n workers (separate Chrome profiles, a fixed share of companies each) and relay their output."""
    import subprocess
    import threading
    base = strip_option(strip_option(list(argv), "--parallel"), "--shard")
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    procs = []
    for k in range(1, n + 1):
        cmd = [sys.executable, str(Path(__file__).resolve()), *base, "--shard", f"{k}/{n}",
               "--profile-dir", str(HERE / f".profile-w{k}")]
        procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                      encoding="utf-8", errors="replace", env=env, cwd=str(REPO)))

    def relay(k, proc):
        for line in proc.stdout:
            if "UserWarning" not in line and "warnings.warn" not in line:
                print(f"[w{k}] {line.rstrip()}", flush=True)
    threads = [threading.Thread(target=relay, args=(k, pr), daemon=True) for k, pr in enumerate(procs, 1)]
    for t in threads:
        t.start()
    codes = [pr.wait() for pr in procs]
    for t in threads:
        t.join(timeout=5)
    print(f"All {n} workers finished (exit codes {codes}).")


def run_batch(args, api, answers, learned, mode):
    from playwright.sync_api import sync_playwright
    radar = api.radar() or {}
    if args.url:  # one posting Sai pasted (not necessarily in Job Radar)
        jobs = [{"id": job_id_for_url(args.url, (radar.get("jobs") or []) + api.all_live()),
                 "company": args.company or urlparse(args.url).netloc, "role": args.role or "",
                 "url": args.url, "board": application_url(args.url)[1]}]
        before = None if args.again else applied_before(jobs[0], local_history() + server_history(radar.get("jobs")))
        if before:
            print(f"Already applied on {str(before.get('ts') or '?')[:10]}: {before.get('company')} - "
                  f"{before.get('role')}. Not sending it again (--again to override).")
            return
    else:
        types = tuple(t.strip() for t in args.role_types.split(",") if t.strip())
        jobs = select_jobs(api.live_jobs(args.min_score, args.min_ctc, types), args.min_score, args.min_ctc, types)
        jobs = filter_boards(jobs, args.boards)
        if args.only:
            wanted = {s.strip() for s in args.only.split(",") if s.strip()}
            jobs = [j for j in jobs if str(j.get("id")) in wanted]
        history = local_history() + server_history(radar.get("jobs"))
        jobs = dedupe(jobs, () if args.only else recent_role_keys(history))  # --only: Sai picked these ids
        if not args.only:  # same posting under a new title or a new Job Radar row: role keys miss it
            jobs = [j for j in jobs if not applied_before(j, history, same_role=False)]
        held = held_companies()
        if held:
            jobs = [j for j in jobs if _norm(j.get("company")) not in held]
        gone = expired_ids()
        jobs = [j for j in jobs if j.get("id") not in gone]
        inbox_check = None if args.no_inbox else make_inbox(_s(answers.get("email")) or "sairaghava1318@gmail.com")
        if inbox_check:  # applications Sai sent himself only show up in his inbox
            try:
                already = applied_by_email(inbox_check.confirmation_mails(), jobs)
            except Exception as e:
                already = {}
                print(f"(couldn't check Gmail for earlier applications: {str(e)[:60]})")
            for j in jobs:
                if j.get("id") in already:
                    print(f"  already applied (Gmail: {already[j.get('id')][:60]}): {j.get('company')} - {j.get('role')}")
            jobs = [j for j in jobs if j.get("id") not in already]
        if args.shard:  # parallel worker k of n: a fixed share of the companies, so no company is hit twice at once
            k, n = (int(x) for x in args.shard.split("/"))
            jobs = [j for j in jobs if shard_of(j.get("company"), n) == k - 1]
    limit = args.max or (40 if mode == "harvest" else 25)
    print(f"{len(jobs)} open jobs after filters and 30-day dedupe; working through up to {limit}.")
    profile = radar.get("profile") or {}
    resume = ensure_resume(api)
    emailer = make_emailer(api)
    pending = load_yaml(PENDING_PATH)
    inbox = None if args.no_inbox else make_inbox(_s(answers.get("email")) or "sairaghava1318@gmail.com")
    if inbox:
        print("Reading security codes and Workday verification links from your Gmail (read-only).")
    with sync_playwright() as pw:
        ctx = launch(pw, headless=args.headless, visible=args.visible, profile=getattr(args, "profile_dir", None))
        d = PlaywrightDriver(ctx, headless=args.headless, visible=args.visible, resume=resume,
                             resume_name=_resume_name(profile, answers), submit_enabled=(mode == "submit"),
                             gh_tokens=greenhouse_tokens())
        d.inbox = inbox
        d.hide()
        runner = Runner(api, d, _fill_context_factory(api, profile, answers, learned, resume, use_ai=not args.no_ai),
                        submit=(mode == "submit"), max_jobs=limit, per_company=args.per_company,
                        handoff_wait_s=args.handoff_wait * 60, ask_timeout_s=args.ask_timeout * 60,
                        pending=pending, learned=learned, harvest_first=not args.no_harvest,
                        emailer=emailer, log=RunLog(), pace=tuple(float(x) for x in args.pace.split(",")),
                        gate=SubmitGate(RUNS_DIR / "submit_gate", tuple(float(x) for x in args.pace.split(",")))
                        if args.shard else None,
                        workday_password=workday_passwords(answers, Path(args.answers) if args.answers else ANSWERS_PATH),
                        code_for=combine_code_sources(make_code_reader(), inbox), attended=args.attended,
                        tailor=None if args.no_tailor or mode == "harvest" else make_tailor())
        if mode == "harvest":
            work, _skipped = plan_queue(jobs, limit, args.per_company)
            pend, _rows = runner.harvest(work, record=True)
            print(f"\n{len(pend)} pending questions written to {PENDING_PATH}")
        else:
            runner.run(jobs)
        ctx.close()
    if inbox and mode == "submit" and not args.no_tidy and not args.shard:
        try:
            n_trash, n_label = tidy_inbox(inbox.user, inbox.password)
            print(f"Inbox tidied: {n_trash} security-code mails to Trash, {n_label} confirmations moved to "
                  f"'{TIDY_LABEL}'.")
        except Exception as e:
            print(f"(inbox tidy skipped: {str(e)[:80]})")
    if inbox and mode == "submit":
        attempted = [{"id": r.get("job_id"), "company": r.get("company"), "role": r.get("role"), "url": r.get("url")}
                     for r in runner.results if r.get("outcome") in ("unconfirmed", "needs-you")]
        try:
            n = sync_email_confirmations(api, inbox, attempted, runner.log)
            print(f"Confirmation emails: {n} more application(s) marked applied.")
        except Exception as e:
            print(f"(confirmation-email check failed: {str(e)[:80]})")
    if mode != "harvest":
        subject, body = runner.summary(mode)
        print("\n" + subject + "\n" + body)
        # Sai: no per-run summary emails ("unnecessary"); only the unanswered-questions email goes out.
    api.runner_report(runner.report(mode))


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Fill job applications in Chrome from Sai's own data.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--setup", action="store_true", help="one-time questionnaire -> answers.yaml")
    g.add_argument("--pick", action="store_true", help="list the top 10 open jobs and choose one")
    g.add_argument("--job", type=int, help="open this Job Radar job id")
    g.add_argument("--next", action="store_true", help="open the best open job")
    g.add_argument("--auto", action="store_true", help="work through many jobs (dry run unless --submit)")
    g.add_argument("--sync-email", action="store_true",
                   help="mark applied the jobs whose 'thank you for applying' email is in your Gmail")
    g.add_argument("--harvest", action="store_true", help="collect unanswered questions from many forms, email them")
    ap.add_argument("--pending", action="store_true", help="with --setup: answer only the pending questions")
    ap.add_argument("--submit", action="store_true", help="with --auto: really submit complete forms")
    ap.add_argument("--max", type=int, default=None, help="jobs to work through (auto 25, harvest 40)")
    ap.add_argument("--per-company", type=int, default=1)
    ap.add_argument("--handoff-wait", type=int, default=30, help="minutes to wait for you after 'Complete it now'")
    ap.add_argument("--ask-timeout", type=int, default=10, help="minutes to wait for your email choice")
    ap.add_argument("--no-harvest", action="store_true", help="with --auto --submit: skip the harvest pass")
    ap.add_argument("--no-ai", action="store_true", help="don't ask the AI about unusual required questions")
    ap.add_argument("--no-tailor", action="store_true", help="upload resume.pdf as is (no wording for each posting)")
    ap.add_argument("--visible", action="store_true", help="keep Chrome on-screen (debugging)")
    ap.add_argument("--headless", action="store_true", help="no window at all (checks only; never waits for you)")
    ap.add_argument("--screenshot", help="with --headless: where to save a full-page screenshot")
    ap.add_argument("--answers", help="answers file (default tools/apply_assist/answers.yaml)")
    ap.add_argument("--api", help=f"app base URL (default $APPLY_API_BASE or {DEFAULT_API})")
    ap.add_argument("--min-score", type=int, default=MIN_SCORE)
    ap.add_argument("--min-ctc", type=float, default=MIN_CTC)
    ap.add_argument("--role-types", default=",".join(ROLE_TYPES),
                    help="fte,intern_6m by default; add intern for internships of unstated length")
    ap.add_argument("--no-inbox", action="store_true", help="don't read codes / verification links from Gmail")
    ap.add_argument("--attended", action="store_true",
                    help="you're at the laptop: CAPTCHAs / missing answers bring the window straight up (no email)")
    ap.add_argument("--only", default=None, help="only these Job Radar ids, comma-separated (e.g. 5,1,10)")
    ap.add_argument("--url", default=None, help="with --auto: apply to this one posting link (use with --company/--role)")
    ap.add_argument("--again", action="store_true", help="with --url: apply even if this posting was applied to before")
    ap.add_argument("--company", default=None, help="with --url: company name")
    ap.add_argument("--no-tidy", action="store_true", help="don't tidy Gmail (codes to Trash, confirmations to a label)")
    ap.add_argument("--tidy-inbox", action="store_true", help="only tidy Gmail now and exit")
    ap.add_argument("--parallel", type=int, default=1, help="with --auto: run N workers side by side (own browsers)")
    ap.add_argument("--pace", default="180,420",
                    help="seconds to wait between submissions, min,max (default 3-7 min: sites rate-limit fast applicants)")
    ap.add_argument("--shard", default=None, help=argparse.SUPPRESS)  # "k/n": set by --parallel for each worker
    ap.add_argument("--profile-dir", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--role", default=None, help="with --url: role title")
    ap.add_argument("--boards", default=None,
                    help="only these job boards, e.g. greenhouse,lever,ashby (no account needed)")
    args = ap.parse_args(argv)
    if args.tidy_inbox:
        _load_env()
        inbox = make_inbox(_s(load_yaml(ANSWERS_PATH).get("email")) or "sairaghava1318@gmail.com")
        if not inbox:
            sys.exit("Add GMAIL_APP_PASSWORD to .env first.")
        n_trash, n_label = tidy_inbox(inbox.user, inbox.password)
        print(f"Inbox tidied: {n_trash} security-code mails to Trash, {n_label} confirmations moved to '{TIDY_LABEL}'.")
        return
    if args.parallel > 1 and args.auto and not args.shard:
        _load_env()
        return run_parallel(sys.argv[1:] if argv is None else argv, args.parallel)
    if args.submit and not args.auto:
        ap.error("--submit only works together with --auto")
    if args.pending and not args.setup:
        ap.error("--pending only works together with --setup")
    _load_env()
    answers_path = Path(args.answers) if args.answers else ANSWERS_PATH
    if args.setup:
        if args.pending:
            pending = load_yaml(PENDING_PATH)
            if not pending:
                print("No pending questions. Run --harvest (or an --auto run) first.")
                return
            answers = load_yaml(answers_path)
            pending, answers = answer_pending(pending, answers)
            save_yaml(answers_path, answers, ANSWERS_HEADER)
            save_yaml(PENDING_PATH, pending, "# Required questions the runner could not answer.")
            print(f"\nSaved {answers_path}. {len(pending)} questions still pending.")
        else:
            run_setup(answers_path)
        return
    if not answers_path.exists():
        sys.exit("Run --setup first:  python tools/apply_assist/assist.py --setup")
    answers = load_yaml(answers_path)
    learned = QuestionBank(load_yaml(LEARNED_PATH))
    api = Api.from_env(args.api)
    if args.sync_email:
        run_sync_email(api, answers)
    elif args.auto:
        run_batch(args, api, answers, learned, "submit" if args.submit else "dry-run")
    elif args.harvest:
        run_batch(args, api, answers, learned, "harvest")
    elif args.pick or args.job or args.next:
        run_assist(args, api, answers, learned)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
