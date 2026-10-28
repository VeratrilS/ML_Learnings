#!/usr/bin/env python
"""
LinkedIn Easy Apply with the runner's answers (answers.yaml, learned answers, the AI fallback for odd questions).
Sai signs in to LinkedIn once in a window; the session stays in .profile-li.

  python tools/apply_assist/linkedin_apply.py --login                      # window: sign in once
  python tools/apply_assist/linkedin_apply.py URL [URL ...]                # fill each one, stop before Submit
  python tools/apply_assist/linkedin_apply.py --submit URL [URL ...]       # submit the complete ones

Same rules as assist.py: fresher roles only (min qualifications read first), companies in hold.txt skipped,
one submission at a time across all runners (SubmitGate). A job with the company's own Apply button prints that
link (run it through assist.py --url). Questions nobody answered are never guessed: the job is left for Sai.
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assist  # noqa: E402

PROFILE = assist.HERE / ".profile-li"
MODAL = "dialog[data-testid='dialog'], dialog[open], .jobs-easy-apply-modal, [data-test-modal-id='easy-apply-modal'], div[role='dialog']:has(button[aria-label*='Easy Apply' i]), div[role='dialog']:has(form)"
NEXT = ["Submit application", "Review your application", "Continue to next step"]
SENT = re.compile(r"application (was )?sent|you applied|applied \d+ (second|minute)s? ago", re.I)


def job_id(url):
    m = re.search(r"(?:jobs/view/(?:[^/?#]*-)?|currentJobId=)(\d{6,})", url or "")
    return m.group(1) if m else None


def login():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = assist.launch(pw, visible=True, profile=PROFILE)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto("https://www.linkedin.com/login")
        pg.bring_to_front()
        end = time.time() + 1800
        while time.time() < end and "/feed" not in pg.url:
            pg.wait_for_timeout(2000)
        print("Signed in." if "/feed" in pg.url else "Timed out waiting for the LinkedIn sign-in.")
        ctx.close()


class LinkedIn:
    def __init__(self, ctx, fc_for, resume, gate=None, submit=False, log=None, api=None):
        self.d = assist.PlaywrightDriver(ctx, headless=False, resume=resume, resume_name="Resume.pdf",
                                         submit_enabled=submit)
        self.page, self.fc_for, self.gate, self.submit = self.d.page, fc_for, gate, submit
        self.log, self.api = log or assist.RunLog(), api

    # ---- page helpers ----
    def _text(self, sel):
        try:
            loc = self.page.locator(sel).first
            return re.sub(r"\s+", " ", loc.inner_text(timeout=3000)).strip() if loc.count() else ""
        except Exception:
            return ""

    def _modal(self):
        loc = self.page.locator(MODAL)
        for i in range(loc.count()):
            if loc.nth(i).is_visible():
                return loc.nth(i)
        return None

    def _button(self, root, name):
        for sel in (f"button[aria-label='{name}']", f"button:has-text('{name.split(' ')[0]}')"):
            b = root.locator(sel)
            for i in range(b.count()):
                if b.nth(i).is_visible() and name.split(" ")[0].lower() in (b.nth(i).inner_text() + " " + (b.nth(i).get_attribute("aria-label") or "")).lower():
                    return b.nth(i)
        return None

    def _errors(self, modal):
        out = []
        e = modal.locator(".artdeco-inline-feedback--error, [data-test-form-element-error-messages]")
        for i in range(e.count()):
            if e.nth(i).is_visible():
                t = re.sub(r"\s+", " ", e.nth(i).inner_text()).strip()
                if t:
                    out.append(t)
        return out

    def _discard(self):
        try:
            m = self._modal()
            if m is not None:
                x = m.locator("button[aria-label='Dismiss']").first
                if x.count():
                    x.click(timeout=4000)
                    self.page.wait_for_timeout(800)
            for name in ("Discard", "Don't save"):
                b = self.page.locator(f"button:has-text('{name}')").first
                if b.count() and b.is_visible():
                    b.click(timeout=4000)
                    break
        except Exception:
            pass

    def _fill_step(self, fc):
        fields = self.d.scan()
        inside = set(self.page.evaluate(
            "(sel) => [...document.querySelectorAll(sel)].flatMap(m => [...m.querySelectorAll('[data-aa-id]')]"
            ".map(e => e.getAttribute('data-aa-id')))", MODAL))
        fields = [f for f in fields if f.get("frame") == 0 and str(f.get("aid")) in inside]
        plan = assist.plan_fields(fields, fc)
        filled, failed = self.d.apply(plan.actions)
        todo = plan.todo + failed
        left = [t.label for t in todo if assist.is_required(t.f)]
        return filled, left

    # ---- one job ----
    def run(self, url):
        jid = job_id(url)
        if not jid:
            return {"url": url, "outcome": "skipped", "reason": "not a LinkedIn job link"}
        url = f"https://www.linkedin.com/jobs/view/{jid}/"
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(3500)
        if "/login" in self.page.url or "authwall" in self.page.url:
            sys.exit("Not signed in to LinkedIn: run with --login first.")
        role = self._text(".job-details-jobs-unified-top-card__job-title, .jobs-unified-top-card__job-title, h1")
        company = self._text(".job-details-jobs-unified-top-card__company-name, .jobs-unified-top-card__company-name")
        desc = self._text("#job-details, .jobs-description__content, .jobs-box__html-content")
        if not (role and company):  # 2026 layout: no classes; the tab title is "Role | Company | LinkedIn"
            parts = [p.strip() for p in (self.page.title() or "").split("|")]
            if len(parts) >= 3:
                role, company = role or parts[0], company or parts[1]
        if not desc:  # never judge the requirements on an empty description
            desc = self._text("main") or self.page.inner_text("body")
        job = {"company": company or "?", "role": role or "?", "url": url, "board": "linkedin"}
        print(f"{job['company']} - {job['role']}")
        if any(assist._norm(company) == assist._norm(h) or assist._norm(h) in assist._norm(company)
               for h in assist.held_companies()):
            return {**job, "outcome": "skipped", "reason": "company on hold (hold.txt)"}
        if not assist.fresher_ok(job):
            return {**job, "outcome": "skipped", "reason": "not a fresher role (title)"}
        why = assist.min_quals_problem(desc)
        if why:
            return {**job, "outcome": "skipped", "reason": "min qualifications: " + why}
        if re.search(r"no longer accepting applications", self.page.inner_text("body"), re.I):
            return {**job, "outcome": "skipped", "reason": "closed (no longer accepting applications)"}
        btn = self.page.locator("button.jobs-apply-button, .jobs-apply-button--top-card button").first
        if not btn.count():  # 2026 layout: the top-card button is only recognisable by its aria-label
            btn = self.page.locator("[aria-label='Easy Apply to this job'], [aria-label='Apply on company website']").first
        if btn.count() and (btn.get_attribute("href") or "").startswith("https://www.linkedin.com/safety/go/"):
            from urllib.parse import parse_qs, urlparse
            link = parse_qs(urlparse(btn.get_attribute("href")).query).get("url", [""])[0]
            return {**job, "outcome": "external", "reason": "company site", "external_url": link}
        if not btn.count():
            body = self.page.inner_text("body")
            if re.search(r"\bApplied\b", body[:4000]):
                return {**job, "outcome": "skipped", "reason": "already applied on LinkedIn"}
            return {**job, "outcome": "needs-you", "reason": "no Apply button found"}
        label = (btn.inner_text() + " " + (btn.get_attribute("aria-label") or "")).lower()
        if "easy apply" not in label:  # the company's own site: hand the link to assist.py --url
            try:
                with self.page.context.expect_page(timeout=15000) as newp:
                    btn.click()
                ext = newp.value
                ext.wait_for_load_state("domcontentloaded", timeout=30000)
                link = ext.url
                ext.close()
            except Exception:
                link = self.page.url
            return {**job, "outcome": "external", "reason": "company site", "external_url": link}
        btn.click()
        self.page.wait_for_timeout(2000)
        fc = self.fc_for(job)
        all_filled, stuck_rounds, dropped_entry = [], 0, False
        for _step in range(14):
            modal = self._modal()
            if modal is None:
                break
            filled, left = self._fill_step(fc)
            if os.environ.get("LI_DEBUG"):
                print("   step", _step, [a.label for a in filled], "left:", left, "|",
                      re.sub(r"\s+", " ", modal.inner_text())[:300 if os.environ["LI_DEBUG"] == "1" else 3000])
            all_filled += [a.label for a in filled]
            if left:
                self._discard()
                return {**job, "outcome": "needs-you", "reason": "questions without an answer", "left": left}
            submit = self._button(modal, "Submit application")
            if submit is not None:
                if not self.submit:
                    self._discard()
                    return {**job, "outcome": "dry-run", "reason": "complete; stopped before Submit",
                            "filled": all_filled}
                follow = modal.locator("input#follow-company-checkbox")
                try:
                    if follow.count() and follow.is_checked():
                        modal.locator("label[for='follow-company-checkbox']").click(timeout=3000)
                except Exception:
                    pass
                ctx = self.gate.turn() if self.gate else None
                if ctx:
                    with ctx:
                        submit.click()
                        self.page.wait_for_timeout(4000)
                else:
                    submit.click()
                    self.page.wait_for_timeout(4000)
                body = self.page.inner_text("body")
                ok = bool(SENT.search(body))
                done = self.page.locator("button:has-text('Done'), button[aria-label='Dismiss']").first
                try:
                    if done.count():
                        done.click(timeout=3000)
                except Exception:
                    pass
                return {**job, "outcome": "submitted" if ok else "unconfirmed",
                        "reason": "" if ok else "no 'application sent' message", "filled": all_filled}
            nxt = self._button(modal, "Review your application") or self._button(modal, "Continue to next step") or self._button(modal, "Next")  # 2026 layout: plain "Next"
            if nxt is None:
                self._discard()
                return {**job, "outcome": "needs-you", "reason": "no Next/Review/Submit button in the form"}
            before = modal.inner_text()[:600]
            nxt.click()
            self.page.wait_for_timeout(1800)
            m2 = self._modal()
            errs = self._errors(m2) if m2 is not None else []
            if not errs and m2 is not None and "This field is required" in m2.inner_text():  # 2026 layout: no error class
                text = m2.inner_text()
                drop = m2.locator("button:has-text('Delete experience')").first
                if "Work experience" in text and drop.count() and not dropped_entry:
                    # LinkedIn parsed an undated entry ("Member, Axiom NIT Rourkela") from an old resume into the form; it
                    # isn't on Sai's profile. Deleting it here only changes this application.
                    try:
                        drop.scroll_into_view_if_needed(timeout=3000)
                        drop.click(timeout=5000)
                    except Exception:
                        drop.evaluate("b => b.click()")  # off-screen window: a DOM click still works
                    self.page.wait_for_timeout(1500)
                    ok = self.page.locator("button:text-is('Delete'), button:text-is('Yes, delete')").last
                    if ok.count() and ok.is_visible():  # "Delete this experience?" confirmation, if LinkedIn asks
                        try:
                            ok.click(timeout=5000)
                        except Exception:
                            ok.evaluate("b => b.click()")
                        self.page.wait_for_timeout(1500)
                    dropped_entry = True
                    continue
                errs = ["a required field LinkedIn takes from your profile is empty (e.g. dates of a work-experience entry)"]
            if errs and m2 is not None and m2.inner_text()[:600] == before:
                stuck_rounds += 1
                if stuck_rounds >= 2:
                    self._discard()
                    return {**job, "outcome": "needs-you", "reason": "form errors: " + "; ".join(errs[:3])}
        self._discard()
        return {**job, "outcome": "needs-you", "reason": "form did not finish in 14 steps"}


def main(argv=None):
    ap = argparse.ArgumentParser(description="LinkedIn Easy Apply from Sai's saved answers.")
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--login", action="store_true", help="open a window to sign in to LinkedIn once")
    ap.add_argument("--submit", action="store_true", help="really submit complete applications")
    ap.add_argument("--pace", default="60,150")
    ap.add_argument("--no-ai", action="store_true")
    args = ap.parse_args(argv)
    if args.login:
        return login()
    if not args.urls:
        ap.error("give LinkedIn job links (or --login)")
    try:
        from dotenv import load_dotenv
        load_dotenv(assist.REPO / ".env")
    except ImportError:
        pass
    from playwright.sync_api import sync_playwright
    api = assist.Api.from_env()
    answers = assist.load_yaml(assist.ANSWERS_PATH)
    learned = assist.QuestionBank(assist.load_yaml(assist.LEARNED_PATH))
    profile = (api.radar() or {}).get("profile") or {}
    resume = assist.ensure_resume(api)
    fc_for = assist._fill_context_factory(api, profile, answers, learned, resume, use_ai=not args.no_ai)
    gate = assist.SubmitGate(assist.RUNS_DIR / "submit_gate", tuple(float(x) for x in args.pace.split(",")))
    log = assist.RunLog()
    with sync_playwright() as pw:
        ctx = assist.launch(pw, profile=PROFILE)
        li = LinkedIn(ctx, fc_for, resume, gate=gate, submit=args.submit, log=log, api=api)
        li.d.hide()
        for url in args.urls:
            try:
                r = li.run(url)
            except SystemExit:
                raise
            except Exception as e:
                r = {"url": url, "outcome": "failed", "reason": str(e).splitlines()[0][:160]}
                li._discard()
            extra = r.get("external_url") or "; ".join(r.get("left") or [])
            print(f"  -> {r['outcome']}: {r.get('reason', '')}" + (f" | {extra}" if extra else ""), flush=True)
            log.write({k: v for k, v in r.items() if k != "filled"} | {"via": "linkedin_apply"})
            if r["outcome"] == "submitted":
                ok, msg = api.confirm_applied(None, "Submitted by the runner via LinkedIn Easy Apply", job=r)
                print("     recorded in Job Radar" if ok else f"     could not record it: {msg}")
        ctx.close()


if __name__ == "__main__":
    main()
