"""
Production smoke test for the job-application automation (mostly read-only).

Usage:
    python scripts/smoke_jobs_prod.py [--base https://productivity-automations.vercel.app] [--no-wait]

Auth: X-App-Key = sha256("daily:" + APP_PASSCODE), APP_PASSCODE read from .env (never printed).

Side effects (accepted): GET /api/jobs/<id>/pack may write one cache row in job_packs; GET /api/jobs/radar may run
the hourly scan itself if the last one is over 60 min old (upserts jobs, no email).
Never calls: POST /api/jobs/scan, /followups, /hourly-check, /dispatch-live-alert, /applied, /settings, or anything
that sends email or changes application status.
"""
import argparse
import hashlib
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE = "https://productivity-automations.vercel.app"
BANNED = ("passionate", "leverage", "delve", "seamless", "cutting-edge", "synergy")
PLACEHOLDER_RE = re.compile(r"\[(Company|Role|Name|Your Name|Hiring Manager)\]", re.I)
SIMULATED_STATUSES = {"auto_applied", "auto-applied", "submitted_auto", "applied_auto"}
FAKE_RECEIPT_HINTS = ("verified", "in screening", "auto-submitted", "auto submitted")
TIMEOUT = 30
PACK_TIMEOUT = 90
RETRIES = 6
RETRY_WAIT = 60

results = []  # (name, ok|None, detail)  None = INFO / WARN


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    tag = "PASS" if ok is True else ("FAIL" if ok is False else "INFO")
    print(f"  [{tag}] {name}" + (f" -- {detail}" if detail and ok is not True else ""))


def short(text, n=400):
    text = str(text).replace("\n", " ")
    return text if len(text) <= n else text[:n] + "..."


class Client:
    def __init__(self, base, key):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "smoke-jobs-prod/1.0"
        if key:
            self.s.headers["X-App-Key"] = key

    def get(self, path, timeout=TIMEOUT, **params):
        return self.s.get(self.base + path, params=params or None, timeout=timeout)


def get_json(client, path, timeout=TIMEOUT, **params):
    """Returns (status_code, json_or_None, text). Never raises for HTTP errors."""
    try:
        r = client.get(path, timeout=timeout, **params)
    except requests.RequestException as e:
        return None, None, f"{type(e).__name__}: {e}"
    try:
        body = r.json()
    except ValueError:
        body = None
    return r.status_code, body, r.text


def check_health(c):
    code, body, text = get_json(c, "/api/health")
    record("GET /api/health", code == 200, f"HTTP {code}: {short(text, 200)}")


def fetch_live(c, min_score, wait):
    attempts = RETRIES + 1 if wait else 1
    for i in range(attempts):
        code, body, text = get_json(c, "/api/jobs/live", min_score=min_score)
        if "UndefinedColumn" in (text or "") and i < attempts - 1:
            print(f"  ... /api/jobs/live?min_score={min_score} -> UndefinedColumn (deploy pending?); "
                  f"retry {i + 1}/{RETRIES} in {RETRY_WAIT}s")
            time.sleep(RETRY_WAIT)
            continue
        return code, body, text
    return code, body, text


def check_live(c, wait):
    code, body, text = fetch_live(c, 0, wait)
    ok = code == 200 and isinstance(body, dict) and body.get("status") == "success"
    record("GET /api/jobs/live?min_score=0 status", ok, f"HTTP {code}: {short(text)}")
    if not ok:
        return []
    jobs = body.get("data")
    if not isinstance(jobs, list):
        record("live: data is a list", False, f"got {type(jobs).__name__}")
        return []
    record("live: data is a list", True)
    print(f"  live jobs (min_score=0): {len(jobs)}")
    record("live: count > 0", len(jobs) > 0, f"count={len(jobs)}")

    required = ("id", "company", "role", "url", "match_score")
    missing = [(j.get("id"), [f for f in required if j.get(f) in (None, "")]) for j in jobs]
    missing = [m for m in missing if m[1]]
    record("live: required fields present", not missing, f"{len(missing)} jobs missing fields, e.g. {missing[:5]}")

    bad_url = [(j.get("id"), j.get("url")) for j in jobs if not str(j.get("url") or "").startswith("https://")]
    record("live: urls are https", not bad_url, f"{len(bad_url)} non-https, e.g. {bad_url[:5]}")

    ids = [j.get("id") for j in jobs]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    record("live: no duplicate ids", not dups, f"duplicates: {dups[:10]}")

    scores = [j.get("match_score") for j in jobs]
    bad_scores = [s for s in scores if not isinstance(s, (int, float)) or not 0 <= s <= 100]
    record("live: match_score numeric 0-100", not bad_scores, f"bad values: {bad_scores[:10]}")
    ordered = all(isinstance(a, (int, float)) and isinstance(b, (int, float)) and a >= b
                  for a, b in zip(scores, scores[1:]))
    record("live: sorted by match_score desc", ordered or bool(bad_scores), "not sorted")

    code50, body50, text50 = fetch_live(c, 50, wait)
    ok50 = code50 == 200 and isinstance(body50, dict) and isinstance(body50.get("data"), list)
    if ok50:
        n50 = len(body50["data"])
        print(f"  live jobs (min_score=50): {n50}")
        below = [j.get("match_score") for j in body50["data"] if (j.get("match_score") or 0) < 50]
        record("GET /api/jobs/live?min_score=50", not below and n50 <= len(jobs),
               f"count={n50}; scores below 50: {below[:5]}")
    else:
        record("GET /api/jobs/live?min_score=50", False, f"HTTP {code50}: {short(text50)}")
    return jobs


def check_radar(c):
    code, body, text = get_json(c, "/api/jobs/radar", timeout=90)
    ok = code == 200 and isinstance(body, dict) and body.get("status") == "success"
    record("GET /api/jobs/radar status", ok, f"HTTP {code}: {short(text)}")
    if not ok:
        return
    print(f"  radar top-level keys: {sorted(body.keys())}")
    jobs = body.get("jobs") or []
    print(f"  radar jobs: {len(jobs)}")
    summary = body.get("summary") or {}
    print(f"  radar summary keys: {sorted(summary.keys())}")

    # Simulation heuristics -------------------------------------------------
    probs = [j.get("shortlist_prob") for j in jobs if isinstance(j.get("shortlist_prob"), (int, float))]
    nonzero = [p for p in probs if p not in (0, 0.0)]
    odd_precision = [p for p in nonzero if len(repr(float(p)).split(".")[-1]) >= 4]
    record("radar: shortlist_prob not random-looking", not odd_precision,
           f"{len(nonzero)}/{len(probs)} non-zero probs, {len(odd_precision)} with >=4 decimals, "
           f"e.g. {odd_precision[:6]}")

    statuses = {}
    for j in jobs:
        statuses[j.get("status")] = statuses.get(j.get("status"), 0) + 1
    print(f"  radar job statuses: {statuses}")
    sim = {s: n for s, n in statuses.items() if str(s).lower() in SIMULATED_STATUSES or "auto" in str(s).lower()}
    record("radar: no auto_applied-style statuses", not sim, f"found {sim}")

    applied = [j for j in jobs if j.get("status") in ("manual_applied", "applied_confirmed")]
    applied_no_ts = [j.get("id") for j in applied if not j.get("applied_at")]
    record("radar: applied jobs have applied_at", not applied_no_ts, f"ids without applied_at: {applied_no_ts[:10]}")
    refs = [(j.get("id"), j.get("application_ref")) for j in jobs if j.get("application_ref")]
    fake_refs = [r for r in refs if r[0] not in {a.get("id") for a in applied}]
    record("radar: no application_ref on un-applied jobs", not fake_refs, f"e.g. {fake_refs[:5]}")

    if summary.get("auto_applied_count") not in (None, summary.get("confirmed_applied_count")):
        record("radar: summary.auto_applied_count == confirmed", False,
               f"auto_applied_count={summary.get('auto_applied_count')} "
               f"confirmed={summary.get('confirmed_applied_count')}")
    if any(summary.get(k) for k in ("auto_apply_enabled", "stealth_mode", "ml_mimic_active")):
        record("radar: auto-apply/stealth/ml_mimic flags off", None,
               "INFO: " + ", ".join(f"{k}={summary.get(k)}" for k in
                                    ("auto_apply_enabled", "stealth_mode", "ml_mimic_active")))
    else:
        record("radar: auto-apply/stealth/ml_mimic flags off", True)

    logs = body.get("recent_logs") or []
    log_auto = [l.get("auto_applied_count") for l in logs if l.get("auto_applied_count")]
    applied_n = len(applied)
    too_many = [n for n in log_auto if n > applied_n]
    record("radar: scan logs auto_applied_count <= confirmed applications", not too_many,
           f"log counts {log_auto[:8]} vs confirmed {applied_n}")
    sim_text = [e.get("event") for l in logs for e in (l.get("log_details") or [])
                if isinstance(e, dict) and re.search(r"auto[- ]?appl|submitted .*application|stealth|mimic",
                                                      str(e.get("event", "")), re.I)]
    record("radar: scan log text has no simulated auto-apply claims", not sim_text, f"e.g. {short(sim_text[:3])}")


def check_pack(c, job):
    jid = job["id"]
    code, body, text = get_json(c, f"/api/jobs/{jid}/pack", timeout=PACK_TIMEOUT)
    ok = code == 200 and isinstance(body, dict) and body.get("status") == "success"
    record(f"GET /api/jobs/{jid}/pack status ({job.get('company')} - {job.get('role')})", ok,
           f"HTTP {code}: {short(text)}")
    if not ok:
        return
    d = body.get("data") or {}
    print(f"  pack keys: {sorted(d.keys())}; model={d.get('model')!r}; cached={d.get('cached')}")
    cover, why = d.get("cover_note"), d.get("why_company")
    answers, highlights = d.get("answers"), d.get("resume_highlights")
    record("pack: cover_note non-empty", isinstance(cover, str) and len(cover.split()) >= 20,
           f"{len(str(cover or '').split())} words")
    record("pack: why_company non-empty", isinstance(why, str) and len(why.split()) >= 10,
           f"{len(str(why or '').split())} words")
    ans_ok = isinstance(answers, list) and answers and all(
        isinstance(a, dict) and a.get("question") and a.get("answer") for a in answers)
    record("pack: answers list of {question, answer}", bool(ans_ok), f"answers={short(answers, 200)}")
    record("pack: resume_highlights non-empty list", isinstance(highlights, list) and len(highlights) > 0,
           f"resume_highlights={short(highlights, 200)}")
    record("pack: model field present", bool(d.get("model")), f"model={d.get('model')!r}")

    texts = [cover or "", why or ""]
    texts += [str(a.get("answer", "")) for a in answers or [] if isinstance(a, dict)]
    texts += [str(h) for h in highlights or []]
    blob = "\n".join(texts)
    hits = sorted({w for w in BANNED if re.search(rf"\b{re.escape(w)}\b", blob, re.I)})
    record("pack: no banned words", not hits, f"found: {hits}")
    ph = sorted(set(m.group(0) for m in PLACEHOLDER_RE.finditer(blob)))
    record("pack: no [Company]-style placeholders", not ph, f"found: {ph}")
    company = job.get("company") or ""
    record("pack: mentions the company", company.lower() in blob.lower(), f"'{company}' not found in text")


def check_status_only(c, path):
    code, body, text = get_json(c, path)
    if code == 405:
        record(f"GET {path} (status only)", None, "INFO: HTTP 405 - route exists but is POST-only (not called)")
    elif code == 404:
        record(f"GET {path} (status only)", None, "INFO: HTTP 404 - endpoint not present")
    else:
        extra = ""
        if code == 200 and isinstance(body, dict) and isinstance(body.get("receipts"), list):
            recs = body["receipts"]
            fake = [r for r in recs if any(h in str(r.get("status", "")).lower() for h in FAKE_RECEIPT_HINTS)]
            extra = f"; {len(recs)} receipts" + (f", {len(fake)} look simulated: {short(fake[:2])}" if fake else "")
            if fake:
                record(f"GET {path}: receipts not simulated", False, extra)
        record(f"GET {path} (status only)", code == 200, f"HTTP {code}{extra}: {short(text, 200)}")


def check_portals(jobs, limit=5):
    s = requests.Session()
    s.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
    for j in jobs[:limit]:
        url = j.get("url")
        name = f"portal reachable: {j.get('company')} (id {j.get('id')})"
        try:
            r = s.head(url, timeout=TIMEOUT, allow_redirects=False)
            if r.status_code in (403, 404, 405, 501) or r.status_code >= 500:
                r = s.get(url, timeout=TIMEOUT, allow_redirects=False, stream=True)
                r.close()
            ok = 200 <= r.status_code < 400
            loc = f" -> {r.headers.get('Location')}" if 300 <= r.status_code < 400 else ""
            record(name, ok, f"HTTP {r.status_code}{loc} {url}")
        except requests.RequestException as e:
            record(name, False, f"{type(e).__name__}: {e} {url}")


def print_table():
    w = max(len(r[0]) for r in results) if results else 10
    w = min(w, 90)
    print("\n" + "=" * (w + 10))
    print(f"{'CHECK':<{w}}  RESULT")
    print("-" * (w + 10))
    for name, ok, _ in results:
        tag = "PASS" if ok is True else ("FAIL" if ok is False else "INFO")
        print(f"{name[:w]:<{w}}  {tag}")
    print("=" * (w + 10))
    fails = [r for r in results if r[1] is False]
    passes = sum(1 for r in results if r[1] is True)
    infos = sum(1 for r in results if r[1] is None)
    print(f"{passes} passed, {len(fails)} failed, {infos} info")
    if fails or infos:
        print("\nDetails:")
        for name, ok, detail in results:
            if ok is not True:
                print(f"- [{'FAIL' if ok is False else 'INFO'}] {name}\n    {detail}")
    return not fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--no-wait", action="store_true", help="don't retry on UndefinedColumn")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    passcode = os.getenv("APP_PASSCODE", "")
    key = hashlib.sha256(f"daily:{passcode}".encode()).hexdigest() if passcode else None
    print(f"Base: {args.base}  (auth header {'set' if key else 'NOT set - APP_PASSCODE missing'})\n")

    c = Client(args.base, key)
    print("Health"); check_health(c)
    print("Live jobs"); jobs = check_live(c, wait=not args.no_wait)
    print("Radar"); check_radar(c)
    print("Pack")
    if jobs:
        check_pack(c, jobs[0])
    else:
        record("GET /api/jobs/<id>/pack", False, "skipped: no live jobs")
    print("Other endpoints")
    check_status_only(c, "/api/jobs/receipts")
    check_status_only(c, "/api/jobs/settings")
    print("Portal urls")
    if jobs:
        check_portals(jobs, limit=5)
    sys.exit(0 if print_table() else 1)


if __name__ == "__main__":
    main()
