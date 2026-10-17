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
from urllib.parse import parse_qs, quote, urlparse, urlunparse

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


def select_jobs(jobs, min_score=MIN_SCORE, min_ctc=MIN_CTC, role_types=ROLE_TYPES):
    """Open jobs worth applying to, newest first (posting date, then match score). No approval needed."""
    keep = [j for j in jobs
            if (j.get("status") or "discovered") not in DONE_STATUSES and j.get("url")
            and j.get("role_type") in role_types and (j.get("match_score") or 0) >= min_score and ctc_ok(j, min_ctc)]
    return sorted(keep, key=lambda j: (j.get("posted") or (j.get("discovered_at") or "")[:10],
                                       j.get("match_score") or 0, j.get("discovered_at") or ""), reverse=True)


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
                out.append({"company": e.get("company"), "role": e.get("role"), "ts": e.get("ts")})
    return out


def server_history(radar_jobs):
    return [{"company": j.get("company"), "role": j.get("role"), "ts": j.get("applied_at")}
            for j in radar_jobs or [] if j.get("status") in APPLIED_STATUSES]


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


# =====================================================================================================
# The click guard. Every click in this file goes through safe_click().
# =====================================================================================================
class SubmitBlocked(RuntimeError):
    pass


SUBMIT_WORDS = re.compile(r"\b(submit|apply|send|finish|complete|confirm)\b", re.I)
APPLY_ENTRY = (r"apply|apply now|apply for this (job|role|position)|apply here|apply online|apply to this job|"
               r"apply manually|start (your )?application|i.?m interested")
ACCOUNT_BUTTONS = r"create account|sign in"
WD_BUTTON_IDS = {"Create Account": "createAccountSubmitButton", "Sign In": "signInSubmitButton"}
NEXT_BUTTONS = r"save and continue|next|continue"


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
        if t != "submit" and not info.get("in_form") and re.fullmatch(rf"\s*({APPLY_ENTRY})\s*", text, re.I):
            return True
        raise SubmitBlocked(f"Refusing to click {text!r}: not a plain 'Apply' entry button.")
    if purpose == "pick_option" and info.get("tag") not in ("button", "input", "a") and (
            info.get("role") == "option" or info.get("wdid") in ("promptOption", "promptLeafNode")):
        return True  # a dropdown option ("Yes, I confirm") can't submit the form
    if purpose in ("account", "next_page"):
        # Workday: "Create Account" / "Sign In" and "Save and Continue" / "Next". The label may repeat (text + aria-label).
        words = ACCOUNT_BUTTONS if purpose == "account" else NEXT_BUTTONS
        if re.fullmatch(rf"\s*(?:{words})(?:\s+(?:{words}))*\s*", text, re.I) and not SUBMIT_WORDS.search(text):
            return True
        raise SubmitBlocked(f"Refusing to click {text or t!r} as a {purpose} button.")
    if purpose == "open_dropdown":
        if info.get("haspopup") == "listbox" and t != "submit" and not SUBMIT_WORDS.search(text):
            return True
        raise SubmitBlocked(f"Refusing to click {text or t!r}: not a dropdown.")
    if is_submit_like(info):
        raise SubmitBlocked(f"Refusing to click {text or t!r}: looks like a submit/apply/send control.")
    return True


ELEMENT_INFO_JS = """(el) => ({
  tag: el.tagName.toLowerCase(), type: (el.type || el.getAttribute('type') || '').toLowerCase(),
  role: (el.getAttribute('role') || '').toLowerCase(), in_form: !!el.closest('form'), href: el.tagName === 'A' ? el.href : '',
  haspopup: (el.getAttribute('aria-haspopup') || '').toLowerCase(), wdid: el.getAttribute('data-automation-id') || '',
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
            locator.check(timeout=5000, force=True)
    else:
        locator.click(timeout=10000)
    return info


# =====================================================================================================
# Field model: what the page scan returns, and how each field maps to Sai's data
# =====================================================================================================
# field dict: {aid, frame, tag, type, role, label, optlabel, aria, placeholder, name, id, required, value,
#              checked, files, options, in_form}
RULES = [  # (pattern, key) in priority order; matched against label, aria-label, placeholder, name and id
    (r"preferred\s*(first\s*)?name|nick\s*name", "preferred_name"),  # only from answers.yaml, never guessed
    (r"first\s*name|given\s*name|_systemfield_first|^first$", "first_name"),
    (r"last\s*name|surname|family\s*name|^last$", "last_name"),
    (r"^(full\s*)?name\s*\*?$|your (full )?name|_systemfield_name|legal name|candidate name|^full name", "full_name"),
    (r"e-?mail", "email"),
    (r"phone device type|device type", "phone_device_type"),
    (r"country phone code|phone (country )?code|dialing code|country code", "phone_country_code"),
    (r"phone|mobile|contact number|whatsapp", "phone"),
    (r"linked\s*in", "linkedin"),
    (r"git\s*hub", "github"),
    (r"leet\s*code", "leetcode"),
    (r"codeforces", "codeforces"),
    (r"portfolio|personal (web)?site|^website|other (link|url)", "portfolio"),
    (r"10th|tenth|class x\b|\bssc\b|secondary school", "class_10"),
    (r"12th|twelfth|class xii|intermediate|higher secondary|\bhsc\b", "class_12"),
    (r"school|university|college|institution", "college"),
    (r"degree|qualification|major|discipline|field of study", "degree"),
    (r"grad(uation)?\s*(year|date)|year of (graduation|passing)|class of|\bbatch\b|passing year", "grad_year"),
    (r"cgpa|\bgpa\b|grade point", "cgpa"),
    (r"backlog", "active_backlogs"),
    (r"date of birth|\bdob\b|birth\s*date", "date_of_birth"),
    (r"pin\s*code|postal code|\bzip\b", "pin_code"),
    (r"address line 1|street address|^street", "address_line1"),
    (r"address line 2", "address_line2"),  # never filled
    (r"address", "address"),
    (r"^city\W*$|^town\W*$", "address_city"),  # the bare "City" of an address block
    (r"expected (ctc|salary|compensation|pay)|salary expectation|desired (salary|compensation)", "expected_ctc"),
    (r"current (ctc|salary|compensation)|present (ctc|salary)", "current_ctc"),
    (r"notice period", "notice_period"),
    (r"^(are|is|will|would|can|could|do) you\b.{0,25}\b(available|able|willing|open|ready) to", "available"),  # yes/no
    (r"earliest (start|joining)|when can you (start|join)|start date|joining date|available to (start|join)", "start_date"),
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
    "accept_privacy_notice": ["I agree", "I acknowledge", "I accept", "I consent", "Agree", "Acknowledge",
                              "Acknowledged", "Accept", "I have read"],
    "how_did_you_hear": ["Company website", "Company careers page", "Careers page", "Careers site", "Career site",
                         "Website", "Job board", "Online job board", "LinkedIn", "Other"],
    "notice_period": ["Immediate", "Immediately", "0 days", "Not applicable", "N/A", "Less than 15 days", "None"],
    "current_ctc": ["Not applicable", "N/A", "0"],
    "phone_country_code": ["India (+91)", "India", "+91"],
    "phone_device_type": ["Mobile", "Mobile Phone", "Cell"],
}
DECLINE_KEYS = ("gender", "pronouns", "diversity")  # unanswered -> pick a decline option if the field offers one
RESUME_FIELD = re.compile(r"resume|\bcv\b|curriculum", re.I)
COVER_FIELD = re.compile(r"cover", re.I)
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
    "office_or_hybrid": "Yes",
    "available": "Yes",
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
    "active_backlogs": "No",
    "notice_period": "Immediate (final-year student)",
    "current_ctc": "0 / Not applicable",
    "expected_ctc": "As per company norms",
    "start_date_fte": "July 2027 (after graduation)",
    "start_date_internship": "January 2027",
    "address": "NIT Rourkela, Sector 1, Rourkela, Odisha 769008, India",
    "pin_code": "769008",
    "state": "Odisha",
    "phone_device_type": "Mobile",
    "phone_country_code": "India (+91)",
}
ADDRESS_DEFAULT_KEYS = ("pin_code", "state")


def build_values(profile, answers, role_type=None):
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
    intern = (role_type or "").startswith("intern")
    v["start_date"] = _s(a.get("start_date_internship" if intern else "start_date_fte")) or _s(a.get("start_date"))
    # Address blocks split into line 1 / city: default to the whole address and the current city.
    v["address_line1"] = _s(a.get("address_line1")) or _s(v.get("address"))
    v["address_city"] = _s(a.get("address_city")) or v["current_city"]
    v.pop("workday_password", None)  # passed to the Workday sign-in only, never to a form field or the AI
    return {k: val for k, val in v.items() if val}


def national_number(phone):
    """'+91 91103 07856' -> '9110307856' (for forms with a separate country-code dropdown)."""
    return re.sub(r"\D", "", re.sub(r"^\s*\+?91[\s-]*", "", phone or ""))


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
            is_resume = RESUME_FIELD.search(desc) or (len(files) == 1 and not COVER_FIELD.search(desc))
            if has_value(f):
                continue
            if is_resume and fc.resume:
                actions.append(Action(f, "file", None, "resume", label))
            elif is_required(f):
                todo.append(Todo(f, label, "upload" if not is_resume else "resume not available", "file"))
            continue
        if has_value(f):
            continue  # never overwrite what's already there
        is_combo = f.get("role") in ("combobox", "listbox")
        val, src = resolve(f, fc, choice=t == "select" or is_combo)
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
                src, targets, strict = "ai", choice_targets(val), False
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
    r"your application is (complete|submitted)", re.I)
CONFIRM_URL = re.compile(r"/(thanks|thank-you|thank_you|thankyou|confirmation|confirmed|success|submitted|applied)\b", re.I)
REF = re.compile(r"(?:application|reference|confirmation|candidate)\s*(?:id|number|no\.?|#|code)\s*[:#]?\s*([A-Z0-9][A-Z0-9-]{3,})", re.I)


def detect_confirmation(text, url, start_url=None):
    """(confirmed?, reference or None). Needs a thank-you message, or a URL change to a thanks/confirmation page."""
    ok = bool(CONFIRM_TEXT.search(text or ""))
    if not ok and url and start_url and url != start_url:
        ok = bool(CONFIRM_URL.search(urlparse(url).path or ""))
    m = REF.search(text or "") if ok else None
    return ok, (m.group(1) if m else None)


def blockers(state, fields):
    reasons = []
    if state.get("captcha"):
        reasons.append("CAPTCHA on the page")
    if state.get("login"):
        reasons.append("Login or account needed")
    if len(fields) < 2 and not state.get("login"):
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
    ("phone", "Phone (with +91)", "text"),
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
             "from then on.", "", "Run:  python tools/apply_assist/assist.py --setup --pending", ""]
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
        try:
            return self.http.get(self.base + "/api/health", timeout=5).ok
        except Exception:
            return False

    def _get(self, path, timeout=60, **params):
        r = self.http.get(self.base + path, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()

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

    def confirm_applied(self, job_id, notes, ref=None):
        body = {"job_id": job_id, "notes": notes}
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
    'Return JSON: {"answer": "<text>"} or {"answer": null}.')
AI_PRIVATE_KEYS = {"phone", "address", "address_line1", "pin_code", "date_of_birth", "email", "workday_password"}


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
        generate = lambda prompt: client.generate_json(prompt, temperature=0.2, system=AI_SYSTEM)  # noqa: E731
    bank = QuestionBank(load_yaml(path) if path else {})
    facts = ai_facts(values)

    def ai(question, ftype, options, company, role=""):
        _key, e = bank.find(question, company)
        if e and (not options or option_match(options, e["answer"]) is not None):
            return e["answer"]
        prompt = (f"Candidate facts:\n{facts}\n\nCompany: {company}\nRole: {role}\nQuestion: {question}\n"
                  f"Field type: {ftype}\n" + (f"Options: {json.dumps(options, ensure_ascii=False)}\n" if options else ""))
        out = generate(prompt)
        ans = _s(out.get("answer") if isinstance(out, dict) else None)
        if not ans or _norm(ans) in ("null", "none", "unknown"):
            return None
        if bank.learn(question, ans, ftype, options, company, role) and path:
            save_yaml(path, bank.entries, "# Answers the AI gave to unusual form questions. Fix or delete any that are wrong.")
        return ans
    return ai


def make_emailer():
    """send(subject, body) -> bool via api.core.clients.EmailClient (SENDER_EMAIL / SENDER_PASSWORD / RECEIVER_EMAIL)."""
    def send(subject, body):
        sender, password = os.getenv("SENDER_EMAIL"), os.getenv("SENDER_PASSWORD")
        receiver = os.getenv("RECEIVER_EMAIL") or "sairaghava1318@gmail.com"
        if not (sender and password):
            print("Email not configured (SENDER_EMAIL / SENDER_PASSWORD): skipped.")
            return False
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from api.core.clients import EmailClient
        return EmailClient(sender, password).send_email(receiver, subject, body)
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
    let n = el.parentElement;
    for (let i = 0; n && i < 5; i++, n = n.parentElement) {
      const v = n.querySelector('[class*="single-value"], [class*="singleValue"], [class*="multi-value__label"], [class*="multiValue"], '
        + '[data-automation-id="selectedItem"]');
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
    if (!isFile && (!(choice ? boxShown(el) : shown(el)) || el.getAttribute('aria-hidden') === 'true')) continue;
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
  return { url: location.href, captcha: capFrame || capEl || capText, login, errors, text: body.slice(0, 20000) };
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
  box.style.cssText = 'position:fixed;z-index:2147483647;right:16px;bottom:16px;max-width:380px;background:#111827;color:#fff;'
    + 'font:14px/1.45 system-ui,sans-serif;padding:14px 16px;border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.35)';
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
  box.appendChild(row); document.body.appendChild(box); return true;
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

CAPTCHA_FRAME_URL = re.compile(r"recaptcha|hcaptcha|turnstile|challenges\.cloudflare|arkoselabs|funcaptcha", re.I)
BROWSER_ARGS = ["--disable-renderer-backgrounding", "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows"]
OFFSCREEN_ARGS = ["--window-position=-32000,-32000", "--start-minimized"]


def launch(pw, headless=False, visible=False):
    """Normal Playwright Chrome with a persistent profile. Off-screen + minimized unless --visible/--headless."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    args = BROWSER_ARGS + ([] if headless or visible else OFFSCREEN_ARGS)
    opts = dict(headless=headless, args=args, viewport={"width": 1280, "height": 900}, accept_downloads=False)
    last = None
    for channel in ("chrome", None):  # installed Chrome first, Playwright's Chromium as a fallback
        try:
            if channel:
                return pw.chromium.launch_persistent_context(str(PROFILE_DIR), channel=channel, **opts)
            return pw.chromium.launch_persistent_context(str(PROFILE_DIR), **opts)
        except Exception as e:
            last = e
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

    # ---- window: off-screen while working, on-screen only when Sai is needed ----
    def _window(self, bounds):
        s = self.context.new_cdp_session(self.page)
        try:
            wid = s.send("Browser.getWindowForTarget")["windowId"]
            s.send("Browser.setWindowBounds", {"windowId": wid, "bounds": bounds})
        finally:
            s.detach()

    def hide(self):
        if self.headless or self.visible:
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
            self._window({"left": 40, "top": 30, "width": 1320, "height": 980})
        except Exception:
            pass
        self.page.bring_to_front()

    # ---- navigation ----
    def url(self):
        try:
            return self.page.url
        except Exception:
            return ""

    def _settle(self):
        try:
            self.page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        self.page.wait_for_timeout(1500)

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
        self.start_url = self.url()
        return note

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
                if a.kind == "text":
                    loc.fill(str(a.value), timeout=6000)
                elif a.kind == "select":
                    loc.select_option(index=a.value, timeout=6000)
                elif a.kind == "toggle":
                    safe_click(loc, "toggle")
                elif a.kind == "file":
                    loc.set_input_files({"name": self.resume_name, "mimeType": "application/pdf", "buffer": self.resume},
                                        timeout=10000)
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

    def _combo(self, loc, a):
        """Search-as-you-type dropdown: type each search term and pick a matching option; if typing finds nothing
        (e.g. the answer is "Yes" but the options say "I acknowledge"), open the full list and match against it."""
        frame = self._frames[a.f["frame"]]
        pick = lambda: self._pick_option(frame, a)  # noqa: E731

        for term in combo_terms(a.value):
            loc.fill(term, timeout=5000)
            self.page.wait_for_timeout(1200)
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

    OPTION_SEL = '[role="option"], [data-automation-id="promptOption"]'

    def _pick_option(self, frame, a):
        """Click the visible dropdown option that best matches the action's targets. False if none matches."""
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
        idx = option_match([t for _, t in seen], targets, strict=strict)
        if idx is None:
            return False
        safe_click(opts.nth(seen[idx][0]), "pick_option")
        self.page.wait_for_timeout(500)
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
        try:
            return self._workday_account(email, password)
        except SubmitBlocked as e:
            return f"failed:{e}"

    def _workday_account(self, email, password):
        if self._visible('input[type="password"]') is None and self._visible('[data-automation-id="createAccountLink"]') is None:
            return "ok"  # already signed in (persistent Chrome profile) or no account step
        if not password:
            return "no-password"
        creating = self._visible('[data-automation-id="verifyPassword"]') is not None
        link = self._visible('[data-automation-id="createAccountLink"]')
        if not creating and link is not None:
            safe_click(link, "account")
            self._settle()
            creating = self._visible('[data-automation-id="verifyPassword"]') is not None
        result = self._wd_credentials(email, password, creating)
        if result == "exists":
            link = self._visible('[data-automation-id="signInLink"]')
            if link is None:
                return "failed:account exists but no Sign In link"
            safe_click(link, "account")
            self._settle()
            result = self._wd_credentials(email, password, creating=False)
        return result

    def _wd_credentials(self, email, password, creating):
        page = self.page
        for sel, val in (('[data-automation-id="email"]', email), ('[data-automation-id="password"]', password),
                         ('[data-automation-id="verifyPassword"]', password if creating else None)):
            loc = self._visible(sel)
            if loc is not None and val:
                loc.fill(val, timeout=6000)
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
        text = self.page_text()
        if re.search(r"already (exists|in use|registered)|account with this email", text, re.I):
            return "exists"
        if re.search(r"verify your (email|account)|verification (email|link)|check your (email|inbox)", text, re.I):
            return "verify-email"
        if self._visible('input[type="password"]') is not None:
            err = self._visible('[data-automation-id="errorMessage"], [role="alert"]')
            why = (err.inner_text(timeout=1000) if err is not None else "still on the sign-in page")[:120]
            return f"failed:{why}"
        return "ok"

    def workday_step(self):
        """Name of the current application step (progress bar), or ''."""
        loc = self._visible('[data-automation-id="progressBarActiveStep"], [data-automation-id="pageHeaderTitle"], h2')
        try:
            return re.sub(r"\s+", " ", loc.inner_text(timeout=1000)).strip() if loc is not None else ""
        except Exception:
            return ""

    def _next_button(self):
        for sel in ('[data-automation-id="bottom-navigation-next-button"]',):
            loc = self._visible(sel)
            if loc is not None:
                return loc
        return self._wd_button("Save and Continue") or self._wd_button("Next")

    def workday_on_review(self):
        """The last page: its bottom button says Submit (Workday reuses the 'next' button for it)."""
        if re.search(r"\breview\b", self.workday_step(), re.I):
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
            safe_click(btn, "next_page")
        except SubmitBlocked as e:
            return f"errors:{e}"
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self.page.wait_for_timeout(1000)
            if self.workday_step() != before:
                self._settle()
                return "moved"
            err = self._visible('[data-automation-id="errorMessage"], [data-automation-id="errorBanner"], [role="alert"]')
            if err is not None:
                try:
                    text = err.inner_text(timeout=1000)
                except Exception:
                    text = ""
                if text.strip():
                    return "errors:" + re.sub(r"\s+", " ", text).strip()[:200]
        return "errors:the page did not change after Save and Continue"

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
    driver.mark([(a.f, GREEN) for a in filled] + [(t.f, ORANGE) for t in todo])
    return FillResult(fields, filled, todo, tracked_from_todo(todo))


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
}


def fill_workday(driver, fc, email, password, max_pages=8):
    """Workday: account step, then fill each page and press 'Save and Continue' until the Review page (never Submit).
    -> (FillResult over all pages, blocker reasons, missing required labels, step names seen)."""
    account = driver.workday_account(email, password)
    if account != "ok":
        reason = WD_ACCOUNT_REASONS.get(account) or f"Workday sign-in failed ({account.split(':', 1)[-1]})"
        return FillResult([], [], [], []), [reason], [], []
    filled, steps, fill = [], [], FillResult([], [], [], [])
    for _ in range(max_pages):
        steps.append(driver.workday_step())
        if driver.workday_on_review():
            return FillResult(fill.fields, filled, [], []), [], [], steps
        fill = fill_page(driver, fc)
        filled += fill.filled
        reasons, missing, _st = check_page(driver)
        if missing:  # fields that appear only after another answer (State after Country): one more pass
            fill = fill_page(driver, fc)
            filled += fill.filled
            reasons, missing, _st = check_page(driver)
        # A page of only buttons/uploads (My Experience) is fine on Workday.
        reasons = [r for r in reasons if not r.startswith("No application form")]
        if reasons or missing:
            return FillResult(fill.fields, filled, fill.todo, fill.tracked), reasons, missing, steps
        moved = driver.workday_next()
        if moved == "no-button":
            return FillResult(fill.fields, filled, fill.todo, fill.tracked), ["Couldn't find Save and Continue"], [], steps
        if moved.startswith("errors:"):
            return FillResult(fill.fields, filled, fill.todo, fill.tracked), [f"Workday says: {moved[7:]}"], [], steps
    return FillResult(fill.fields, filled, fill.todo, fill.tracked), [f"More than {max_pages} pages"], [], steps


def is_workday(driver):
    return bool(getattr(driver, "is_workday", lambda: False)())


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


class Runner:
    def __init__(self, api, driver, context_for, *, submit=False, max_jobs=25, per_company=1,
                 handoff_wait_s=1800, ask_timeout_s=600, poll_s=15, pending=None, pending_path=PENDING_PATH,
                 learned=None, learned_path=LEARNED_PATH, harvest_first=True, emailer=None, log=None,
                 sleep=time.sleep, clock=time.monotonic, rng=None, pace=(90, 240), confirm_wait_s=30,
                 workday_password=""):
        self.api, self.d, self.context_for = api, driver, context_for
        self.workday_password = workday_password
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
        hid = self.api.create_handoff(job, reason, missing or reasons, url=self.d.url())
        choice = "pending"
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
    def run_job(self, job):
        try:
            note = self.d.open(job)
        except Exception as e:
            return self._record(job, "failed", reason=f"could not open the page ({str(e)[:80]})")
        fill, reasons, missing = self._fill_and_check(job)
        filled_n = len(fill.filled)
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
                reasons, missing, _st = check_page(self.d)
                if reasons or missing:
                    self.d.reset()
                    return self._record(job, "needs-you", reason="still incomplete after Continue: "
                                        + "; ".join(reasons + missing), missing=missing, filled=filled_n)
            if clicks >= 2:
                self.d.reset()
                return self._record(job, "unconfirmed", reason="no confirmation page after Submit", filled=filled_n)
            clicks += 1
            if not self.d.submit():
                reasons, fill = ["Couldn't find the form's Submit button"], None
                continue
            ok, ref = self.d.wait_confirmation(self.confirm_wait_s)
            if ok:
                return self._confirmed(job, ref)
            st = self.d.state()
            if st.get("captcha") or st.get("errors"):
                reasons = (["CAPTCHA appeared after Submit"] if st.get("captcha") else []) + \
                          (["The site flagged errors after Submit"] if st.get("errors") else [])
                missing = []
                continue
            self.d.reset()
            return self._record(job, "unconfirmed", reason="no confirmation page after Submit", filled=filled_n)

    def _confirmed(self, job, ref, by_sai=False):
        ok, msg = self.api.confirm_applied(job.get("id"), SAI_SUBMITTED_NOTE if by_sai else SUBMITTED_NOTE, ref)
        self.d.reset()
        return self._record(job, "submitted", ref=ref, by_sai=by_sai, marked_applied=ok,
                            reason=None if ok else f"confirm-applied failed: {msg}")

    def _fill_and_check(self, job):
        fc = self.context_for(job)
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
        for n, job in enumerate(work, 1):
            print(f"[{n}/{len(work)}] {job.get('company')} - {job.get('role')}")
            try:
                out = self.run_job(job)
            except SubmitBlocked:
                raise
            except Exception as e:
                try:
                    self.d.reset()
                except Exception:
                    pass
                out = self._record(job, "failed", reason=str(e).splitlines()[0][:120])
            if out["outcome"] in ("submitted", "unconfirmed") and not out.get("by_sai") and n < len(work):
                self.sleep(self.rng.uniform(*self.pace))  # pacing between submissions
        if self.harvest_first and not self.submit:
            self._write_pending(self.rows)  # the dry run doubles as the harvest pass
        return self.results

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


def _fill_context_factory(api, profile, answers, learned, resume, use_ai=True):
    questions = QuestionBank((answers or {}).get("questions") or {})
    packs = {}
    ai = make_ai_answerer(build_values(profile, answers)) if use_ai else None

    def make(job):
        if job.get("id") not in packs:
            packs[job.get("id")] = api.pack(job["id"]) if job.get("id") else {}
        return FillContext(values=build_values(profile, answers, job.get("role_type")), company=job.get("company") or "",
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
        ctx = launch(pw, headless=args.headless, visible=args.visible)
        d = PlaywrightDriver(ctx, headless=args.headless, visible=args.visible, resume=resume,
                             resume_name=_resume_name(profile, answers), gh_tokens=greenhouse_tokens())
        d.hide()
        note = d.open(job)
        fc = make_fc(job)
        if d.is_workday():
            password = ensure_workday_password(answers, Path(args.answers) if args.answers else ANSWERS_PATH)
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


def _resume_name(profile, answers):
    name = _s((answers or {}).get("full_name")) or _s((profile or {}).get("full_name")) or "Resume"
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") + "_Resume.pdf"


def run_batch(args, api, answers, learned, mode):
    from playwright.sync_api import sync_playwright
    jobs = select_jobs(api.live_jobs(args.min_score, args.min_ctc), args.min_score, args.min_ctc)
    jobs = filter_boards(jobs, args.boards)
    radar = api.radar() or {}
    done = recent_role_keys(local_history() + server_history(radar.get("jobs")))
    jobs = dedupe(jobs, done)
    limit = args.max or (40 if mode == "harvest" else 25)
    print(f"{len(jobs)} open jobs after filters and 30-day dedupe; working through up to {limit}.")
    profile = radar.get("profile") or {}
    resume = ensure_resume(api)
    emailer = make_emailer()
    pending = load_yaml(PENDING_PATH)
    with sync_playwright() as pw:
        ctx = launch(pw, headless=args.headless, visible=args.visible)
        d = PlaywrightDriver(ctx, headless=args.headless, visible=args.visible, resume=resume,
                             resume_name=_resume_name(profile, answers), submit_enabled=(mode == "submit"),
                             gh_tokens=greenhouse_tokens())
        d.hide()
        runner = Runner(api, d, _fill_context_factory(api, profile, answers, learned, resume, use_ai=not args.no_ai),
                        submit=(mode == "submit"), max_jobs=limit, per_company=args.per_company,
                        handoff_wait_s=args.handoff_wait * 60, ask_timeout_s=args.ask_timeout * 60,
                        pending=pending, learned=learned, harvest_first=not args.no_harvest,
                        emailer=emailer, log=RunLog(),
                        workday_password=ensure_workday_password(answers, Path(args.answers) if args.answers else ANSWERS_PATH))
        if mode == "harvest":
            work, _skipped = plan_queue(jobs, limit, args.per_company)
            pend, _rows = runner.harvest(work, record=True)
            print(f"\n{len(pend)} pending questions written to {PENDING_PATH}")
        else:
            runner.run(jobs)
        ctx.close()
    if mode != "harvest":
        subject, body = runner.summary(mode)
        print("\n" + subject + "\n" + body)
        emailer(subject, body)
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
    g.add_argument("--harvest", action="store_true", help="collect unanswered questions from many forms, email them")
    ap.add_argument("--pending", action="store_true", help="with --setup: answer only the pending questions")
    ap.add_argument("--submit", action="store_true", help="with --auto: really submit complete forms")
    ap.add_argument("--max", type=int, default=None, help="jobs to work through (auto 25, harvest 40)")
    ap.add_argument("--per-company", type=int, default=1)
    ap.add_argument("--handoff-wait", type=int, default=30, help="minutes to wait for you after 'Complete it now'")
    ap.add_argument("--ask-timeout", type=int, default=10, help="minutes to wait for your email choice")
    ap.add_argument("--no-harvest", action="store_true", help="with --auto --submit: skip the harvest pass")
    ap.add_argument("--no-ai", action="store_true", help="don't ask the AI about unusual required questions")
    ap.add_argument("--visible", action="store_true", help="keep Chrome on-screen (debugging)")
    ap.add_argument("--headless", action="store_true", help="no window at all (checks only; never waits for you)")
    ap.add_argument("--screenshot", help="with --headless: where to save a full-page screenshot")
    ap.add_argument("--answers", help="answers file (default tools/apply_assist/answers.yaml)")
    ap.add_argument("--api", help=f"app base URL (default $APPLY_API_BASE or {DEFAULT_API})")
    ap.add_argument("--min-score", type=int, default=MIN_SCORE)
    ap.add_argument("--min-ctc", type=float, default=MIN_CTC)
    ap.add_argument("--boards", default=None,
                    help="only these job boards, e.g. greenhouse,lever,ashby (no account needed)")
    args = ap.parse_args(argv)
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
    if args.auto:
        run_batch(args, api, answers, learned, "submit" if args.submit else "dry-run")
    elif args.harvest:
        run_batch(args, api, answers, learned, "harvest")
    elif args.pick or args.job or args.next:
        run_assist(args, api, answers, learned)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
