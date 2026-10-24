#!/usr/bin/env python
"""
Send LinkedIn connection requests (with a short note) to recruiters in runs/recruiter_queue.json, a few per day.
Sai asked for 3 a day. Uses the LinkedIn session in .profile-li (sign in once: linkedin_apply.py --login).

  python tools/apply_assist/linkedin_connect.py            # preview today's notes, send nothing
  python tools/apply_assist/linkedin_connect.py --send     # send today's batch (default 3)

Never sends twice to the same person (status kept in the queue file); skips people already connected or pending.
"""
import argparse
import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assist  # noqa: E402

QUEUE = assist.RUNS_DIR / "recruiter_queue.json"
PROFILE = assist.HERE / ".profile-li"


def note_for(r):
    first = (r.get("name") or "").split()[0] if r.get("name") else "there"
    company = r.get("company") or "your team"
    owner = company + ("'" if company.endswith("s") else "'s")
    text = (f"Hi {first}, I'm Sai, final-year CSE at NIT Rourkela (2027, CGPA 8.99). I build backend and distributed "
            f"systems in C++/Java. I'd love to be considered for {owner} SDE or intern roles. Thank you!")
    if len(text) > 200:  # LinkedIn's limit for notes on free accounts
        text = (f"Hi {first}, I'm Sai, final-year CSE at NIT Rourkela (2027, CGPA 8.99). I'd love to be considered "
                f"for SDE or intern roles at {company}. Thank you!")
    return text[:200]


def sent_today(queue):
    today = datetime.now().strftime("%Y-%m-%d")
    return sum(1 for r in queue if str(r.get("sent_at", "")).startswith(today) and r.get("status", "").startswith("sent"))


def connect(page, r):
    url = re.sub(r"^http://", "https://", r["linkedin"]).rstrip("/") + "/"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)
    if "/login" in page.url or "authwall" in page.url:
        sys.exit("Not signed in to LinkedIn: run linkedin_apply.py --login first.")
    main = page.locator("main").first
    top = main.locator("section").first
    if top.locator("button:visible").filter(has_text=re.compile(r"^\s*Pending\s*$")).count():
        return "skipped: request already pending"
    btn = top.locator("button:visible").filter(has_text=re.compile(r"^\s*Connect\s*$"))
    if not btn.count():
        more = top.locator("button:visible").filter(has_text=re.compile(r"^\s*More\s*$"))
        if more.count():
            more.first.click()
            page.wait_for_timeout(1200)
            btn = page.locator("[role=menu] [role=button]:visible, .artdeco-dropdown__content [role=button]:visible") \
                .filter(has_text=re.compile(r"^\s*Connect\s*$"))
    if not btn.count():
        return "skipped: no Connect button (already connected, or follow-only profile)"
    btn.first.click()
    page.wait_for_timeout(2000)
    dialog = page.locator("[role=dialog]:visible").last
    add_note = dialog.locator("button").filter(has_text=re.compile(r"Add a note", re.I))
    if add_note.count():
        add_note.first.click()
        page.wait_for_timeout(1200)
        box = dialog.locator("textarea")
        if box.count():
            box.first.fill(note_for(r))
            send = dialog.locator("button").filter(has_text=re.compile(r"^\s*Send\s*$", re.I))
            if send.count() and send.first.is_enabled():
                send.first.click()
                page.wait_for_timeout(2500)
                return "sent with note"
        # free-account note limit reached (Premium upsell): close it and send without a note
        close = page.locator("[role=dialog]:visible button[aria-label*='Dismiss' i]")
        if close.count():
            close.last.click()
            page.wait_for_timeout(1200)
        btn.first.click()
        page.wait_for_timeout(2000)
        dialog = page.locator("[role=dialog]:visible").last
    plain = dialog.locator("button").filter(has_text=re.compile(r"Send without a note|^\s*Send\s*$", re.I))
    if plain.count():
        plain.first.click()
        page.wait_for_timeout(2500)
        return "sent without note"
    return "failed: no Send button in the dialog"


def main(argv=None):
    ap = argparse.ArgumentParser(description="LinkedIn connection requests to recruiters, a few per day.")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--per-day", type=int, default=3)
    args = ap.parse_args(argv)
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    left = max(0, args.per_day - sent_today(queue))
    batch = [r for r in queue if r.get("status") == "queued"][:left]
    if not batch:
        print(f"Nothing to send today ({sent_today(queue)} already sent, limit {args.per_day}).")
        return
    for r in batch:
        print(f"{r['name']} - {r['title'][:50]} @ {r['company']}\n  note: {note_for(r)}")
    if not args.send:
        print("\n(preview only: add --send)")
        return
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = assist.launch(pw, profile=PROFILE)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for i, r in enumerate(batch):
            try:
                out = connect(page, r)
            except SystemExit:
                raise
            except Exception as e:
                out = f"failed: {str(e).splitlines()[0][:120]}"
            r["status"] = out if not out.startswith("sent") else out.replace(" ", "-")
            r["sent_at"] = datetime.now().isoformat(timespec="seconds")
            QUEUE.write_text(json.dumps(queue, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  -> {r['name']} @ {r['company']}: {out}", flush=True)
            if i < len(batch) - 1:
                time.sleep(random.uniform(60, 120))
        ctx.close()


if __name__ == "__main__":
    main()
