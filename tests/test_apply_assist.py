"""Apply assist (tools/apply_assist/assist.py): pure logic only — no network, no browser."""
import copy
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("apply_assist", ROOT / "tools" / "apply_assist" / "assist.py")
aa = importlib.util.module_from_spec(_spec)
sys.modules["apply_assist"] = aa  # dataclasses look the module up while the class is created
_spec.loader.exec_module(aa)

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
PROFILE = {"full_name": "Nandam Venkata Sai Raghava", "email": "sairaghava1318@gmail.com", "phone": "+91 99999 00000",
           "college": "National Institute of Technology, Rourkela (NIT Rourkela)",
           "degree": "Bachelor of Technology in Computer Science and Engineering", "grad_year": 2027, "cgpa": 8.99,
           "location_pref": "Bengaluru, Hyderabad, Gurugram, Remote", "linkedin": "https://linkedin.com/in/sai",
           "github": "https://github.com/VeratrilS"}


def job(i, company="Acme", role="Software Engineer", **kw):
    base = {"id": i, "company": company, "role": role, "url": f"https://jobs.lever.co/acme/{i}", "match_score": 70,
            "role_type": "fte", "status": "discovered", "ctc_lpa": None, "est_ctc": None, "posted": "2026-10-10",
            "discovered_at": "2026-10-16T02:00:00Z"}
    base.update(kw)
    return base


def fld(aid, label, type="text", required=False, value="", **kw):
    f = {"aid": str(aid), "frame": 0, "tag": "input", "type": type, "role": "", "label": label, "optlabel": "",
         "aria": "", "placeholder": "", "name": kw.pop("name", f"f{aid}"), "id": kw.pop("id", f"f{aid}"),
         "required": required, "value": value, "checked": False, "files": 0, "options": [], "in_form": True}
    f.update(kw)
    return f


def ctx(answers=None, pack=None, learned=None, company="Acme", role_type="fte", resume=True):
    answers = answers if answers is not None else {}
    return aa.FillContext(values=aa.build_values(PROFILE, answers, role_type), company=company,
                          custom=answers.get("custom") or [], questions=aa.QuestionBank(answers.get("questions") or {}),
                          learned=learned or aa.QuestionBank(), pack=pack or {}, resume=resume)


# ------------------------------------------------------------------ job selection
def test_select_jobs_filters_and_sorts_newest_first():
    jobs = [
        job(1, posted="2026-10-01", match_score=90),
        job(2, posted="2026-10-15", match_score=60),
        job(3, posted="2026-10-15", match_score=80),
        job(4, match_score=40),                                  # below min score
        job(5, role_type="intern"),                              # duration not stated
        job(6, role_type="intern_6m", posted="2026-10-12"),
        job(7, status="manual_applied"), job(8, status="skipped"), job(9, status="applied_confirmed"),
        job(10, ctc_lpa=10.0),                                   # known CTC below 15
        job(11, est_ctc="40-50 LPA", posted="2026-09-01"),       # no upper bound
        job(12, ctc_lpa=0, est_ctc=None, posted="2026-09-02"),   # unknown CTC allowed
        job(13, status="approved", posted="2026-09-03"),         # approval not required, but allowed
    ]
    got = [j["id"] for j in aa.select_jobs(jobs)]
    assert got == [1, 3, 6, 13, 12, 11, 2]  # best resume match first, then newest (same company tier)


def test_select_jobs_puts_top_companies_first():
    jobs = [job(1, company="Tiny Startup", match_score=95), job(2, company="Micron", match_score=60),
            job(3, company="Google", match_score=60)]
    assert [j["id"] for j in aa.select_jobs(jobs)] == [3, 2, 1]


def test_dedupe_30_days_and_within_list():
    history = [{"company": "Acme", "role": "Software Engineer", "ts": "2026-10-01T00:00:00Z"},
               {"company": "Old Co", "role": "SDE", "ts": "2026-08-01T00:00:00Z"}]
    keys = aa.recent_role_keys(history, now=NOW)
    jobs = [job(1), job(2, company="Old Co", role="SDE"), job(3, company="Beta"), job(4, company="beta", role="software  engineer")]
    assert [j["id"] for j in aa.dedupe(jobs, keys)] == [2, 3]


def test_plan_queue_limits():
    jobs = [job(1, company="A"), job(2, company="A"), job(3, company="B"), job(4, company="C"), job(5, company="D")]
    work, skipped = aa.plan_queue(jobs, max_jobs=3, per_company=1)
    assert [j["id"] for j in work] == [1, 3, 4]
    assert [j["id"] for j, _ in skipped] == [2]
    work, _ = aa.plan_queue(jobs, max_jobs=10, per_company=2)
    assert [j["id"] for j in work] == [1, 2, 3, 4, 5]


def test_local_history_reads_submitted_runs(tmp_path):
    d = tmp_path / "2026-10-10"
    d.mkdir()
    (d / "log.jsonl").write_text("\n".join(json.dumps(e) for e in [
        {"ts": "2026-10-10T00:00:00Z", "company": "A", "role": "R", "outcome": "submitted"},
        {"ts": "2026-10-10T00:00:00Z", "company": "B", "role": "R", "outcome": "needs-you"}]) + "\nnot json\n")
    assert [h["company"] for h in aa.local_history(tmp_path)] == ["A"]


def test_applied_before_matches_the_same_posting_by_any_link():
    # Rubrik Cloud: Azure was sent three times: once from Job Radar, then twice from pasted/researched links
    history = [{"company": "Rubrik", "role": "Software Engineer - Cloud: Azure", "ts": "2026-10-17T10:51:20Z", "id": 6,
                "url": "https://www.rubrik.com/company/careers/departments/job.8258200?gh_jid=8258200"}]
    embed = {"company": "rubrik", "role": "", "url": "https://job-boards.greenhouse.io/embed/job_app?for=rubrik&token=8258200"}
    assert aa.applied_before(embed, history)["id"] == 6
    retitled = {"company": "Hevo Data", "role": "SDE Intern", "id": 229, "url": "https://jobs.lever.co/hevodata/x"}
    assert aa.applied_before(retitled, [{"company": "Hevo Data", "role": "SDE", "id": 229}])
    same_role = {"company": "Rubrik", "role": "Software Engineer - Cloud: Azure", "url": "https://example.com/other"}
    assert aa.applied_before(same_role, history)
    assert aa.applied_before(same_role, history, same_role=False) is None
    other = {"company": "Rubrik", "role": "SWE Intern", "url": "https://job-boards.greenhouse.io/rubrik/jobs/8166537"}
    assert aa.applied_before(other, history) is None


def test_local_history_keeps_the_link(tmp_path):
    d = tmp_path / "2026-10-10"
    d.mkdir()
    (d / "log.jsonl").write_text(json.dumps({"ts": "2026-10-10T00:00:00Z", "company": "A", "role": "R",
                                             "url": "https://jobs.lever.co/a/1", "outcome": "submitted"}) + "\n")
    assert aa.local_history(tmp_path)[0]["url"] == "https://jobs.lever.co/a/1"


# ------------------------------------------------------------------ URLs
def test_application_urls():
    assert aa.application_url("https://jobs.lever.co/hevodata/95ab9f01") == ("https://jobs.lever.co/hevodata/95ab9f01/apply", "lever")
    assert aa.application_url("https://jobs.lever.co/hevodata/95ab/apply/")[0] == "https://jobs.lever.co/hevodata/95ab/apply"
    assert aa.application_url("https://jobs.ashbyhq.com/cursor/166c") == ("https://jobs.ashbyhq.com/cursor/166c/application", "ashby")
    assert aa.application_url("https://job-boards.greenhouse.io/singlestore/jobs/8212128") == \
        ("https://job-boards.greenhouse.io/singlestore/jobs/8212128", "greenhouse")
    url = "https://www.rubrik.com/company/careers/departments/job.8166537?gh_jid=8166537"
    assert aa.application_url(url, "Rubrik", {"rubrik": "rubrik"}) == \
        ("https://job-boards.greenhouse.io/embed/job_app?for=rubrik&token=8166537", "greenhouse")
    assert aa.application_url(url, "Unknown", {})[1] == "other"
    assert aa.application_url("https://cisco.wd5.myworkdayjobs.com/x/job/1") == ("https://cisco.wd5.myworkdayjobs.com/x/job/1", "other")


def test_greenhouse_tokens_from_job_radar_lists():
    tokens = aa.greenhouse_tokens()
    assert tokens.get("rubrik") == "rubrik" and tokens.get("okta") == "okta"


# ------------------------------------------------------------------ click guard
@pytest.mark.parametrize("info", [
    {"tag": "button", "type": "submit", "text": "Next"},
    {"tag": "input", "type": "submit", "text": ""},
    {"tag": "button", "type": "button", "text": "Submit application"},
    {"tag": "a", "type": "", "text": "Apply now"},
    {"tag": "div", "type": "", "text": "Send"},
])
def test_guard_refuses_submit_like_clicks(info):
    with pytest.raises(aa.SubmitBlocked):
        aa.check_click_allowed(info, "other")
    with pytest.raises(aa.SubmitBlocked):
        aa.check_click_allowed(info, "submit")  # the submit path is closed without --submit


def test_guard_allows_safe_clicks_and_explicit_submit():
    assert aa.check_click_allowed({"tag": "li", "type": "", "text": "Bengaluru, Karnataka, India", "role": "option"}, "pick_option")
    assert aa.check_click_allowed({"tag": "input", "type": "radio", "text": "Yes"}, "toggle")
    assert aa.check_click_allowed({"tag": "a", "type": "", "text": "Apply now", "in_form": False}, "open_application")
    with pytest.raises(aa.SubmitBlocked):  # an "Apply" inside a form is the final button, not the entry link
        aa.check_click_allowed({"tag": "button", "type": "button", "text": "Apply", "in_form": True}, "open_application")
    with pytest.raises(aa.SubmitBlocked):
        aa.check_click_allowed({"tag": "button", "type": "submit", "text": "Apply"}, "open_application")
    with pytest.raises(aa.SubmitBlocked):
        aa.check_click_allowed({"tag": "button", "type": "button", "text": "Next"}, "toggle")
    assert aa.check_click_allowed({"tag": "button", "type": "submit", "text": "Submit application"}, "submit", submit_enabled=True)


class _Loc:
    def __init__(self, info):
        self.info, self.clicked, self.checked = info, 0, 0

    def evaluate(self, js):
        return self.info

    def click(self, **kw):
        self.clicked += 1

    def check(self, **kw):
        self.checked += 1


def test_safe_click_never_reaches_click_on_submit():
    loc = _Loc({"tag": "button", "type": "submit", "text": "Submit"})
    with pytest.raises(aa.SubmitBlocked):
        aa.safe_click(loc, "pick_option")
    assert loc.clicked == 0
    radio = _Loc({"tag": "input", "type": "radio", "text": "Yes"})
    aa.safe_click(radio, "toggle")
    assert radio.checked == 1 and radio.clicked == 0


def test_only_safe_click_calls_click_or_check():
    src = (ROOT / "tools" / "apply_assist" / "assist.py").read_text(encoding="utf-8")
    body = src.split("def safe_click(", 1)[1].split("\n\n\n", 1)[0]
    outside = src.replace(body, "")
    assert not re.search(r"\.(click|check|dblclick|tap)\(", outside)
    enter_body = src.split("def search_enter(", 1)[1].split("\n\n\n", 1)[0]
    assert len(re.findall(r"press\([\"']Enter", src)) == 1 and re.search(r"press\([\"']Enter", enter_body)
    assert "check_enter_allowed(" in enter_body
    for banned in ("webdriver", "stealth", "navigator.plugins", "solve_captcha"):
        assert banned not in src.lower().replace("no stealth", "")


def test_enter_only_in_workday_search_picker():
    assert aa.check_enter_allowed({"uxi": "selectinput", "tag": "input", "in_form": False})
    for info in ({"uxi": "selectinput", "tag": "input", "in_form": True}, {"uxi": "", "tag": "input", "in_form": False},
                 {"uxi": "selectinput", "tag": "button", "in_form": False}):
        with pytest.raises(aa.SubmitBlocked):
            aa.check_enter_allowed(info)


# ------------------------------------------------------------------ field planning
def form():
    return [
        fld(1, "First Name *", required=True),
        fld(2, "Last Name *", required=True),
        fld(3, "Email *", type="email", required=True),
        fld(4, "Phone *", type="tel", required=True),
        fld(5, "LinkedIn Profile"),
        fld(6, "Resume/CV *", type="file", required=True),
        fld(7, "What is your favourite colour? *", required=True),
        fld(8, "School", value="Already typed"),
        fld(9, "Degree", type="select", options=["Select...", "Bachelor of Technology", "Master's"]),
        fld(10, "Cover Letter", type="textarea"),
        fld(11, "Are you legally authorized to work in India? *", type="radio", name="auth", optlabel="Yes"),
        fld(12, "Are you legally authorized to work in India? *", type="radio", name="auth", optlabel="No"),
        fld(13, "Are you authorized to work in the United States? *", type="radio", name="us", optlabel="Yes"),
        fld(14, "Are you authorized to work in the United States? *", type="radio", name="us", optlabel="No"),
        fld(15, "I agree to the privacy policy", type="checkbox", name="gdpr", optlabel="I agree", required=True),
    ]


def test_plan_fills_known_and_leaves_unknown_orange():
    answers = {"work_authorized_india": True, "accept_privacy_notice": "Yes"}
    plan = aa.plan_fields(form(), ctx(answers, pack={"cover_note": "Dear team..."}))
    got = {a.f["aid"]: (a.kind, a.value) for a in plan.actions}
    assert got["1"] == ("text", "Nandam Venkata Sai") and got["2"] == ("text", "Raghava")
    assert got["3"] == ("text", "sairaghava1318@gmail.com")
    assert got["5"] == ("text", "https://linkedin.com/in/sai")
    assert got["6"][0] == "file"
    assert got["9"] == ("select", 1)
    assert got["10"] == ("text", "Dear team...")
    assert got["11"] == ("toggle", True)          # India work authorisation from answers.yaml
    assert got["15"] == ("toggle", True)          # consent only because Sai opted in
    assert "8" not in got                         # never overwrite
    todo = {t.label for t in plan.todo}
    assert "Phone *" in todo                      # phone only ever comes from answers.yaml, not the profile
    assert "What is your favourite colour? *" in todo
    assert "Are you authorized to work in the United States? *" in todo  # never guess for another country


def test_preferred_name_is_never_guessed():
    fields = [fld(1, "Preferred First Name")]
    assert aa.plan_fields(fields, ctx({})).actions == []
    assert aa.plan_fields(fields, ctx({"preferred_name": "Sai"})).actions[0].value == "Sai"


def test_plan_phone_from_answers_and_no_consent_after_opt_out():
    plan = aa.plan_fields(form(), ctx({"phone": "+91 90000 11111", "accept_privacy_notice": "No"}))
    got = {a.f["aid"]: a.value for a in plan.actions}
    assert got["4"] == "+91 90000 11111"
    assert "15" not in got and any(t.label.startswith("I agree") for t in plan.todo)
    assert "15" in {a.f["aid"] for a in aa.plan_fields(form(), ctx({})).actions}  # ticked by default


# Real questions that the 2026-10-16 runs left for Sai (Zscaler, Rubrik, Okta, HackerRank on Greenhouse).
SCREENING = [
    ("Country*", "combobox", "India"),
    ("Do you have the legal right to work in the country where you are applying to work?*", "combobox", "Yes"),
    ("Do you, now or in the future, require a work permit, visa, or additional right to work support for the "
     "country where you are applying to work?*", "combobox", "No"),
    ("Do you currently work for, or have you previously worked for Zscaler?*", "combobox", "No"),
    ("Current Company*", "", "Student, NIT Rourkela"),
    ("What is the name of your current employer?*", "", "Student, NIT Rourkela"),
    ("Current Title*", "", "B.Tech student (final year)"),
    ("Have you been involved in procurement or contract award activities involving Zscaler as a government "
     "employee or official?*", "combobox", "No"),
    ("Home Address*", "", "NIT Rourkela, Sector 1, Rourkela, Odisha 769008, India"),
    ("Are you currently or have you ever been employed by Rubrik or contracted to provide services to Rubrik?*",
     "combobox", "No"),
    ("Have you been employed by Okta, Inc. or any of its subsidiaries in the past?*", "combobox", "No"),
    ("To the best of your knowledge, do you have any family members / relatives or personal relationships at Okta?*",
     "combobox", "No"),
    ("Do you have any outside business activity(ies) (advisory, consulting, or board roles, or side businesses)?*",
     "combobox", "No"),
    ("Are you available to intern with HackerRank for a full-time, 6-month internship starting from Jan 5th 2027?*",
     "combobox", "Yes"),
    ("Are you able to work from our Bangalore office, full-time for the entire 6-month internship period?*",
     "combobox", "Yes"),
    ("How did you learn about this job?*", "", "Company careers website"),
    ("Are you available to start a full-time role in July 2027?*", "combobox", "Yes"),
    ("When can you start?*", "", "May 2027 (after graduation)"),
]


@pytest.mark.parametrize("label,role,expected", SCREENING)
def test_screening_questions_answered_without_sai(label, role, expected):
    plan = aa.plan_fields([fld(1, label, required=True, role=role)], ctx({}))
    assert plan.todo == []
    assert plan.actions[0].value == expected and plan.actions[0].source == "profile"


def test_acknowledgement_dropdown_accepts_agree_wording():
    a = aa.plan_fields([fld(1, "I acknowledge that I have read Rubrik's Candidate Privacy Notice.*", required=True,
                            role="combobox")], ctx({})).actions[0]
    assert a.kind == "combo" and "I acknowledge" in a.targets
    sel = fld(2, "I acknowledge the privacy notice *", type="select", required=True,
              options=["Select...", "I acknowledge", "I do not acknowledge"])
    assert aa.plan_fields([sel], ctx({})).actions[0].value == 1
    assert aa.plan_fields([sel], ctx({"accept_privacy_notice": "No"})).actions == []


def test_unanswered_gender_picks_decline_option_but_never_guesses():
    sel = fld(1, "Sex*", type="select", required=True, options=["Select...", "Male", "Female", "Decline to self-identify"])
    assert aa.plan_fields([sel], ctx({})).actions[0].value == 3
    only = fld(2, "Gender*", type="select", required=True, options=["Select...", "Male", "Female"])
    assert aa.plan_fields([only], ctx({})).actions == []
    assert aa.plan_fields([only], ctx({"gender": "Male"})).actions[0].value == 1


def test_how_did_you_hear_falls_back_to_site_wording():
    sel = fld(1, "How did you hear about us?*", type="select", required=True,
              options=["Select...", "Referral", "LinkedIn", "Company Website"])
    assert aa.plan_fields([sel], ctx({})).actions[0].value == 3


def test_answers_yaml_overrides_defaults():
    plan = aa.plan_fields([fld(1, "Current Company*", required=True)], ctx({"current_company": "DataAnnotation"}))
    assert plan.actions[0].value == "DataAnnotation"


def test_own_address_drops_campus_pin_and_state():
    assert aa.build_values(PROFILE, {})["pin_code"] == "769008"
    v = aa.build_values(PROFILE, {"address": "Kasturi Nagar, Nellore, Andhra Pradesh, India"})
    assert v["address"].startswith("Kasturi Nagar") and "pin_code" not in v and "state" not in v
    assert aa.build_values(PROFILE, {"address": "Nellore", "state": "Andhra Pradesh"})["state"] == "Andhra Pradesh"


def test_ai_answers_unusual_required_questions_only():
    calls = []

    def ai(question, ftype, options, company, role=""):
        calls.append((question, ftype, options))
        return {"Why do you like databases? *": "Safety", "Describe a time you led a team *": "At OpenCode Club I led..."
                }.get(question)
    fields = [fld(1, "Why do you like databases? *", type="select", required=True, options=["Select...", "Speed", "Safety"]),
              fld(2, "Describe a time you led a team *", type="textarea", required=True),
              fld(3, "Optional fun fact"),
              fld(4, "Passport number *", required=True),
              fld(5, "Email *", type="email", required=True)]
    fc = ctx({})
    fc.ai = ai
    plan = aa.plan_fields(fields, fc)
    got = {a.f["aid"]: (a.value, a.source) for a in plan.actions}
    assert got["1"] == (2, "ai") and got["2"] == ("At OpenCode Club I led...", "ai")
    assert "3" not in got and [t.label for t in plan.todo] == ["Passport number *"]
    assert [c[0] for c in calls] == ["Why do you like databases? *", "Describe a time you led a team *",
                                     "Passport number *"]
    assert calls[0][2] == ["Speed", "Safety"]
    assert [x["question"] for x in fc.ai_used] == ["Why do you like databases? *", "Describe a time you led a team *"]


def test_ai_never_sees_sensitive_questions():
    fc = ctx({})
    fc.ai = lambda *a, **k: pytest.fail("AI must not be asked for a password")
    assert aa.plan_fields([fld(1, "Create a password *", type="text", required=True)], fc).actions == []


def test_ai_answerer_caches_and_keeps_private_values_out(tmp_path):
    prompts = []

    def gen(prompt):
        prompts.append(prompt)
        return {"answer": "Yes"}
    values = aa.build_values(PROFILE, {"phone": "+91 90000 11111"})
    ai = aa.make_ai_answerer(values, generate=gen, path=tmp_path / "ai.yaml")
    assert ai("Are you comfortable with rotational shifts?", "select", ["Yes", "No"], "Acme") == "Yes"
    assert ai("Are you comfortable with rotational shifts?", "select", ["Yes", "No"], "Beta") == "Yes"
    assert len(prompts) == 1 and "+91 90000 11111" not in prompts[0] and "769008" not in prompts[0]
    assert aa.load_yaml(tmp_path / "ai.yaml")
    null = aa.make_ai_answerer(values, generate=lambda p: {"answer": None}, path=None)
    assert null("Date you were last promoted", "text", [], "Acme") is None


def test_workday_click_guard():
    ok = aa.check_click_allowed
    assert ok({"tag": "div", "role": "button", "text": "Create Account"}, "account")
    assert ok({"tag": "button", "type": "submit", "text": "Create Account Create Account"}, "account")
    assert ok({"tag": "button", "text": "Sign In"}, "account")
    assert ok({"tag": "button", "type": "button", "text": "Save and Continue"}, "next_page")
    assert ok({"tag": "button", "text": "Select One", "haspopup": "listbox"}, "open_dropdown")
    assert ok({"tag": "div", "text": "India (+91)", "wdid": "promptOption"}, "pick_option")
    for info, purpose in [({"tag": "button", "text": "Submit"}, "next_page"),
                          ({"tag": "button", "text": "Submit Application"}, "account"),
                          ({"tag": "button", "text": "Submit", "haspopup": ""}, "open_dropdown"),
                          ({"tag": "button", "text": "Create Account and Apply"}, "account")]:
        with pytest.raises(aa.SubmitBlocked):
            ok(info, purpose)


def test_workday_phone_and_address_fields():
    fields = [fld(1, "Phone Device Type*", type="listbox", role="listbox", required=True),
              fld(2, "Country Phone Code*", role="combobox", required=True),
              fld(3, "Phone Number*", required=True), fld(4, "Address Line 1*", required=True),
              fld(5, "Address Line 2"), fld(6, "City*", required=True), fld(7, "Postal Code")]
    answers = {"phone": "+91 91234 56789", "address": "Kasturi Nagar, Nellore", "address_line1": "Kasturi Nagar",
               "address_city": "Nellore", "current_city": "Rourkela"}
    plan = aa.plan_fields(fields, ctx(answers))
    got = {a.f["aid"]: a.value for a in plan.actions}
    assert got == {"1": "Mobile", "2": "India (+91)", "3": "9123456789", "4": "Kasturi Nagar", "6": "Nellore"}
    assert plan.todo == []  # postal code / line 2 aren't required
    assert aa.plan_fields([fld(3, "Phone Number*", required=True)], ctx(answers)).actions[0].value == "+91 91234 56789"


def test_workday_password_never_reaches_form_values(tmp_path):
    path = tmp_path / "answers.yaml"
    path.write_text("full_name: X\n", encoding="utf-8")
    answers = aa.load_yaml(path)
    pw = aa.ensure_workday_password(answers, path)
    assert len(pw) >= 12 and re.search(r"[A-Z]", pw) and re.search(r"\d", pw) and "!" in pw
    assert aa.load_yaml(path)["workday_password"] == pw and aa.ensure_workday_password(aa.load_yaml(path), path) == pw
    assert "workday_password" not in aa.build_values(PROFILE, aa.load_yaml(path))
    assert pw not in aa.ai_facts(aa.build_values(PROFILE, aa.load_yaml(path)))


class FakeWorkday:
    """Pages of fields; Save and Continue moves on only when the page's required fields are filled."""

    def __init__(self, pages, account="ok"):
        self.pages, self.i, self.account, self.clicked_next = pages, 0, account, 0

    def workday_account(self, email, password):
        return self.account

    def workday_step(self):
        return "Review" if self.i >= len(self.pages) else f"Step {self.i + 1}"

    def workday_on_review(self):
        return self.i >= len(self.pages)

    def scan(self):
        return self.pages[self.i]

    def apply(self, actions):
        for a in actions:
            a.f["value"] = "x"
            a.f["checked"] = a.kind == "toggle" or a.f.get("checked")
        return actions, []

    def mark(self, items):
        pass

    def state(self):
        return {"captcha": False, "login": False}

    def workday_next(self):
        self.clicked_next += 1
        self.i += 1
        return "moved"


def test_fill_workday_walks_pages_to_review_and_stops():
    d = FakeWorkday([[fld(1, "First Name*", required=True), fld(2, "Email*", type="email", required=True)],
                     [fld(3, "Country*", type="listbox", role="listbox", required=True)]])
    fill, reasons, missing, steps = aa.fill_workday(d, ctx({}), "a@b.c", "pw")
    assert (reasons, missing, steps) == ([], [], ["Step 1", "Step 2", "Review"]) and d.clicked_next == 2
    assert len(fill.filled) == 3


def test_fill_workday_stops_on_unknown_required_and_on_account_problems():
    d = FakeWorkday([[fld(1, "What is your favourite colour? *", required=True)], [fld(2, "City*", required=True)]])
    _fill, reasons, missing, steps = aa.fill_workday(d, ctx({}), "a@b.c", "pw")
    assert missing == ["What is your favourite colour? *"] and d.clicked_next == 0 and steps == ["Step 1"]
    _f, reasons, _m, _s = aa.fill_workday(FakeWorkday([], account="verify-email"), ctx({}), "a@b.c", "pw")
    assert "verification email" in reasons[0]


def test_api_falls_back_to_production_when_local_database_fails():
    import requests

    class Resp:
        def __init__(self, code, data=None):
            self.status_code, self.ok, self._data = code, code < 400, data or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(str(self.status_code))

        def json(self):
            return self._data

    class Http:
        headers = {}

        def __init__(self):
            self.urls = []

        def get(self, url, params=None, timeout=None):
            self.urls.append(url)
            if url.startswith("http://localhost"):
                raise requests.ReadTimeout("db down")
            return Resp(200, {"data": [{"id": 1}]})

    api = aa.Api("http://localhost:5050", "k", session=Http())
    assert api.live_jobs() == [{"id": 1}] and api.base == aa.PROD_API
    remote = aa.Api("https://example.com", "k", session=Http())
    remote.http.get = lambda *a, **k: (_ for _ in ()).throw(requests.ReadTimeout("x"))
    with pytest.raises(requests.ReadTimeout):
        remote.live_jobs()


def test_security_code_after_submit_hands_off_instead_of_unconfirmed():
    d = FakeDriver(SIMPLE, submit_enabled=True, confirm_on_submit=False)
    orig = d.submit

    def submit():
        orig()
        d.text = "Enter the 8-character security code sent to your email"
        return True
    d.submit = submit
    api = FakeApi()
    out = runner(d, api).run_job(job(1))
    assert out["outcome"] == "needs-you" and "security code not entered" in out["reason"]
    assert d.shown == 1 and d.overlays[-1][0].startswith("Security code needed") and api.confirmed == []


GH_MAIL = ("<p>Copy and paste this code into the security code field on your application:</p>"
           "<h1>Ab3dEf7H</h1><p>Okta</p>")


def test_code_and_link_parsing_from_emails():
    assert aa.code_in_mail(GH_MAIL) == "Ab3dEf7H"
    assert aa.code_in_mail("Enter the security code field below") is None
    body = ('Verify: <a href="https://barclays.wd3.myworkdayjobs.com/External/activate/abc123?x=1">here</a> '
            'https://cisco.wd5.myworkdayjobs.com/Cisco/activate/zzz https://barclays.wd3.myworkdayjobs.com/job/1')
    assert aa.verify_links(body, "barclays") == ["https://barclays.wd3.myworkdayjobs.com/External/activate/abc123?x=1"]
    assert aa.workday_tenant("https://barclays.wd3.myworkdayjobs.com/en-US/x") == "barclays"


class FakeImap:
    def __init__(self, mails):
        self.mails, self.calls = mails, []

    def login(self, user, pw):
        self.calls.append("login")

    def select(self, box, readonly=False):
        assert readonly is True  # never opens the mailbox read-write
        self.calls.append("select")

    def search(self, charset, query):
        return "OK", [b" ".join(str(i + 1).encode() for i in range(len(self.mails)))]

    def fetch(self, num, what):
        assert "PEEK" in what  # never marks mail read
        sender, subject, body = self.mails[int(num) - 1]
        raw = f"From: {sender}\r\nSubject: {subject}\r\nContent-Type: text/html\r\n\r\n{body}".encode()
        return "OK", [(b'1 (INTERNALDATE "17-Oct-2026 15:00:00 +0530" BODY[] {9}', raw)]

    def logout(self):
        pass


def test_inbox_reads_company_code_once_readonly():
    mails = [("no-reply@us.greenhouse-mail.io", "Security code for your application to Okta", GH_MAIL)]
    inbox = aa.Inbox("me@x", "pw", imap_factory=lambda: FakeImap(mails), now=lambda: 1792249200)
    assert inbox.code_for("Okta", max_age_s=10 ** 9) == "Ab3dEf7H"
    assert inbox.code_for("Okta", max_age_s=10 ** 9) is None  # same code never used twice
    assert inbox.code_for("Zscaler", max_age_s=10 ** 9) is None


def test_combined_code_source_prefers_file_and_throttles_inbox(tmp_path):
    calls = []

    class In:
        def code_for(self, company):
            calls.append(company)
            return "Zz9Yy8Xx"
    t = {"now": 0.0}
    codes = tmp_path / "c.yaml"
    codes.write_text('"1": "File1234"\n', encoding="utf-8")
    code_for = aa.combine_code_sources(aa.make_code_reader(codes), In(), every_s=20, clock=lambda: t["now"])
    assert code_for(job(1)) == "File1234" and calls == []
    assert code_for(job(1)) == "Zz9Yy8Xx" and calls == ["Acme"]
    assert code_for(job(1)) is None  # throttled: no second IMAP call within 20 s
    t["now"] = 30
    assert code_for(job(1)) == "Zz9Yy8Xx" and len(calls) == 2


def test_confirmation_emails_mark_the_attempted_job_with_email_date():
    confirmations = [("Thank you for applying to SingleStore!", 1792240000.0),
                     ("Security code for your application to Okta", 1792240100.0),
                     ("Your application to HackerRank Careers has been received", 1792230000.0)]
    jobs = [{"id": 224, "company": "SingleStore", "role": "SWE"}, {"id": 1, "company": "Okta", "role": "SRE"},
            {"id": 10, "company": "HackerRank", "role": "Intern"}]
    got = {(j["id"], ts) for j, ts, _s in aa.confirmed_by_email(confirmations, jobs)}
    assert got == {(224, 1792240000.0), (10, 1792230000.0)}  # Okta's security-code mail isn't a confirmation

    class In:
        def confirmations(self):
            return [(s, t) for s, t in confirmations if aa.CONFIRM_MAIL.search(s)]
    api = FakeApi()
    calls = []
    api.confirm_applied = lambda job_id, notes, ref=None, applied_at=None: calls.append((job_id, applied_at)) or (True, "ok")
    assert aa.sync_email_confirmations(api, In(), jobs) == 2
    assert (224, "2026-10-17T12:26:40Z") in calls


def test_attempted_from_logs(tmp_path):
    d = tmp_path / "2026-10-16"
    d.mkdir()
    (d / "log.jsonl").write_text("\n".join(json.dumps(e) for e in [
        {"ts": "2026-10-16T10:00:00Z", "job_id": 5, "company": "Zscaler", "outcome": "unconfirmed"},
        {"ts": "2026-10-16T10:01:00Z", "job_id": 6, "company": "Rubrik", "outcome": "skipped"},
        {"ts": "2026-09-01T10:00:00Z", "job_id": 7, "company": "Old", "outcome": "needs-you"}]), encoding="utf-8")
    assert [j["id"] for j in aa.attempted_from_logs(runs_dir=tmp_path, now=NOW)] == [5]


def test_applied_by_email_needs_company_and_role():
    mails = [("mastercard@myworkday.com", "Thank you for your application!",
              "Thank you for applying to the Software Engineer I-1 position at Mastercard.", 0.0),
             ("no-reply@us.greenhouse-mail.io", "Security code for your application to Okta", "Software Engineer at Okta", 0.0),
             ("noreply@rubrik.com", "Thank you for applying to Rubrik", "We received your application for Software Engineer - Cloud: Azure.", 0.0)]
    jobs = [{"id": 430, "company": "Mastercard", "role": "Software Engineer I-1"},
            {"id": 431, "company": "Mastercard", "role": "Data Engineer"},
            {"id": 1, "company": "Okta", "role": "Software Engineer"},
            {"id": 8, "company": "Rubrik", "role": "Software Engineer- SaaS O365"},
            {"id": 6, "company": "Rubrik", "role": "Software Engineer - Cloud: Azure"}]
    assert set(aa.applied_by_email(mails, jobs)) == {430, 6}  # other roles at the same company stay


def test_submit_gate_spaces_submissions_across_workers(tmp_path):
    clock = {"t": 1000.0}
    slept = []

    def sleep(s):
        slept.append(s)
        clock["t"] += s
    gate = aa.SubmitGate(tmp_path / "gate", pace=(180, 180), sleep=sleep, now=lambda: clock["t"])
    with gate.turn():
        pass  # first submission: no wait
    assert slept == [] and not (tmp_path / "gate.lock").exists()
    clock["t"] += 30
    other = aa.SubmitGate(tmp_path / "gate", pace=(180, 180), sleep=sleep, now=lambda: clock["t"])  # another worker
    with other.turn():
        pass
    assert slept == [150.0]  # 180 s after the previous submit, not 180 s after its own start


def test_gate_makes_runner_submit_through_it():
    turns = []

    class Gate:
        def turn(self):
            from contextlib import contextmanager

            @contextmanager
            def t():
                turns.append(1)
                yield
            return t()
    d = FakeDriver(SIMPLE, submit_enabled=True)
    out = runner(d, FakeApi(), gate=Gate()).run_job(job(1))
    assert out["outcome"] == "submitted" and turns == [1]


def test_hold_list(tmp_path):
    f = tmp_path / "hold.txt"
    f.write_text("# comment\nFamPay  # site broken\n\nZeta Global\n", encoding="utf-8")
    assert aa.held_companies(f) == {"fampay", "zeta global"}
    assert aa.held_companies(tmp_path / "missing.txt") == set()


def test_never_claims_to_join_immediately():
    for q in ("We must fill this position urgently. Can you join us immediately?*", "Can you join within 15 days?*",
              "Are you an immediate joiner?*"):
        f = fld(1, q, role="combobox", required=True)
        assert aa.rule_key(f) == "join_immediately", q
        assert aa.plan_fields([f], ctx({})).actions[0].value == "No"
    assert aa.rule_key(fld(2, "Are you available to start a full-time role in July 2027?*")) == "available"


def test_answer_pack_is_fetched_only_when_a_free_text_question_needs_it():
    calls = []
    pack = aa.LazyPack(lambda: calls.append(1) or {"cover_note": "Dear team..."})
    fc = ctx({})
    fc.pack = pack
    aa.plan_fields([fld(1, "Email *", type="email", required=True), fld(2, "Country*", required=True)], fc)
    assert calls == []  # no essay question: no pack fetch
    plan = aa.plan_fields([fld(3, "Cover Letter", type="textarea")], fc)
    assert calls == [1] and plan.actions[0].value == "Dear team..."


def test_tidy_plan_trashes_codes_archives_confirmations_keeps_callbacks():
    now = 1_800_000_000.0
    mails = [(b"1", "no-reply@us.greenhouse-mail.io", "Security code for your application to Okta", now - 7200),
             (b"2", "no-reply@okta.com", "Thank you for applying to Okta!", now - 7200),
             (b"3", "support@hackerrankforwork.com", "AI TA Screen - Interview - Software Development Engineer Intern", now - 7200),
             (b"4", "no-reply@us.greenhouse-mail.io", "Security code for your application to Rubrik", now - 60),  # in use
             (b"5", "talent@x.com", "Online assessment for Software Engineer", now - 7200),
             (b"6", "noreply@x.com", "Thank you for applying - next steps: coding test", now - 7200)]
    trash, archive = aa.tidy_plan(mails, now)
    assert trash == [b"1"] and archive == [b"2"]


def test_parallel_shards_split_companies_and_strip_options():
    companies = ["Okta", "Zscaler", "Rubrik", "IMC", "Point72", "Hevo Data", "GitLab", "Stripe"]
    shards = [{c for c in companies if aa.shard_of(c, 3) == k} for k in range(3)]
    assert set().union(*shards) == set(companies) and sum(len(x) for x in shards) == len(companies)
    assert aa.shard_of("Okta", 3) == aa.shard_of("okta", 3)  # same company -> same worker, every run
    argv = ["--auto", "--submit", "--parallel", "3", "--max", "30", "--parallel=2", "--shard", "1/3"]
    assert aa.strip_option(aa.strip_option(argv, "--parallel"), "--shard") == ["--auto", "--submit", "--max", "30"]


def test_unfamiliar_site_is_never_auto_submitted():
    d = FakeDriver(SIMPLE, submit_enabled=True)
    api = FakeApi()
    out = runner(d, api, attended=True).run_job(job(1, company="Apple", url="https://jobs.apple.com/en-in/details/1"))
    assert d.submits == 0 and api.confirmed == [] and d.shown >= 1
    assert out["outcome"] == "needs-you"
    assert aa.known_ats(job(2)) and aa.known_ats(job(3, url="https://job-boards.greenhouse.io/x/jobs/1"))
    assert not aa.known_ats(job(4, url="https://jobs.apple.com/en-in/details/1"))
    assert aa.known_ats(job(5, url="https://careers.qualcomm.com/careers/job/1"))


def test_dropdown_options_are_read_and_ai_picks_one():
    class D:
        def __init__(self):
            self.applied = []

        def scan(self):
            return [fld(1, "Years of relevant experience *", role="combobox", required=True),
                    fld(2, "Email *", type="email", required=True)]

        def apply(self, actions):
            self.applied += actions
            ok = [a for a in actions if a.kind != "combo" or a.value in ("0-1 years",)]
            return ok, [aa.Todo(a.f, a.label, "couldn't fill", "text") for a in actions if a not in ok]

        def combo_options(self, f):
            return ["Select...", "0-1 years", "1-3 years", "3+ years"]

        def mark(self, items):
            pass

    asked = []

    def ai(question, ftype, options, company, role=""):
        asked.append(options)
        return "0-1 years" if options else "0"
    fc = ctx({})
    fc.ai = ai
    d = D()
    fill = aa.fill_page(d, fc)
    assert any(a.value == "0-1 years" for a in fill.filled) and fill.todo == []
    assert asked[-1] == ["0-1 years", "1-3 years", "3+ years"]


def test_expired_posting_is_recorded_and_never_retried(tmp_path):
    st = {"url": "u", "text": "Software Dev Engineer I This job has expired Sorry, this job has expired"}
    assert aa.blockers(st, []) == ["Posting closed (expired or no longer accepting applications)"]
    d = FakeDriver([fld(1, "Search")], submit_enabled=True)
    d.text = st["text"]
    d.open = lambda job: "fake"
    d.fields_now = [fld(1, "Search")]
    log = aa.RunLog(tmp_path, today="2026-10-17")
    out = runner(d, FakeApi(), log=log).run_job(job(252, company="Swiggy"))
    assert out["outcome"] == "expired" and d.submits == 0
    assert aa.expired_ids(tmp_path) == {252}


def test_unmarked_job_leaves_local_history(tmp_path):
    d = tmp_path / "2026-10-17"
    d.mkdir()
    (d / "log.jsonl").write_text("\n".join(json.dumps(e) for e in [
        {"ts": "2026-10-17T10:00:00Z", "job_id": 443, "company": "Qualcomm", "role": "Eng", "outcome": "submitted"},
        {"ts": "2026-10-17T11:00:00Z", "job_id": 5, "company": "Zscaler", "role": "SDE", "outcome": "submitted"},
        {"ts": "2026-10-17T12:00:00Z", "job_id": 443, "company": "Qualcomm", "outcome": "unmarked"}]), encoding="utf-8")
    assert [h["company"] for h in aa.local_history(tmp_path)] == ["Zscaler"]


def test_unsupported_site_is_listed_not_handed_off():
    d = FakeDriver([fld(1, "Search jobs")], submit_enabled=True)
    api = FakeApi()
    out = runner(d, api, attended=True).run_job(job(1))
    assert out["outcome"] == "needs-you" and "No application form" in out["reason"]
    assert d.shown == 0 and api.handoffs == [] and d.submits == 0


def test_attended_mode_brings_window_up_without_email():
    d = FakeDriver(SIMPLE, submit_enabled=True, captcha=True)
    api = FakeApi()
    runner(d, api, attended=True).run_job(job(1))
    assert api.handoffs == [] and d.shown >= 1


def test_sai_types_code_in_window_and_runner_carries_on():
    d = FakeDriver(SIMPLE, submit_enabled=True, confirm_on_submit=False)
    orig = d.submit

    def submit():
        orig()
        d.text = "Enter the security code sent to your email"
        return True
    d.submit = submit

    def sleep(_s):  # Sai types the code in the shown window and presses Submit
        d.text = "Thank you for applying! Application ID: OK55555"
    api = FakeApi()
    out = runner(d, api, sleep=sleep).run_job(job(1))
    assert out["outcome"] == "submitted" and out["by_sai"] and out["ref"] == "OK55555" and d.shown == 1


def test_security_code_from_file_is_entered_and_confirmed(tmp_path):
    d = FakeDriver(SIMPLE, submit_enabled=True, confirm_on_submit=False)
    orig, entered = d.submit, []

    def submit():
        orig()
        d.text = "Thank you for applying! Application ID: GH77777" if entered else "Enter the security code sent to you"
        return True
    d.submit = submit
    d.enter_security_code = lambda code: entered.append(code) or True
    codes = tmp_path / "codes.yaml"
    codes.write_text('"1": "AbCd1234"\n', encoding="utf-8")
    api = FakeApi()
    out = runner(d, api, code_for=aa.make_code_reader(codes)).run_job(job(1))
    assert entered == ["AbCd1234"] and out["outcome"] == "submitted" and out["ref"] == "GH77777"
    assert aa.load_yaml(codes) == {}  # used once


def test_stale_code_rejected_then_waits_for_fresh_code(tmp_path):
    d = FakeDriver(SIMPLE, submit_enabled=True, confirm_on_submit=False)
    orig, entered = d.submit, []

    def submit():
        orig()
        ok = entered and entered[-1] == "Fresh123"
        d.text = "Thank you for applying!" if ok else "Invalid code. Enter the security code sent to you"
        return True
    d.submit = submit
    d.enter_security_code = lambda code: entered.append(code) or True
    codes = tmp_path / "codes.yaml"
    codes.write_text('"1": "Stale999"\n', encoding="utf-8")

    def sleep(_s):  # Sai pastes the fresh code while the runner waits
        codes.write_text('"1": "Fresh123"\n', encoding="utf-8")
    out = runner(d, FakeApi(), sleep=sleep, code_for=aa.make_code_reader(codes)).run_job(job(1))
    assert entered == ["Stale999", "Fresh123"] and out["outcome"] == "submitted"


def test_unconfirmed_records_what_the_page_said():
    d = FakeDriver(SIMPLE, submit_enabled=True, confirm_on_submit=False)
    out = runner(d, FakeApi()).run_job(job(1))
    assert out["outcome"] == "unconfirmed" and out["page"] == "Apply for this job"


def test_education_dates_degree_and_languages():
    answers = {"edu_start_month": "August", "edu_start_year": "2023", "edu_end_month": "May", "edu_end_year": "2027",
               "languages": "Hindi, Telugu", "degree": "B.Tech, Computer Science and Engineering"}
    fields = [fld(1, "Start date month*", required=True), fld(2, "Start date year*", required=True),
              fld(3, "End date month*", required=True), fld(4, "End date year*", required=True),
              fld(5, "In which language(s) are you fluent (spoken) other than English?*", required=True),
              fld(6, "Degree*", type="select", required=True, options=["Select...", "High School", "Bachelor's Degree",
                                                                       "Master's Degree"])]
    got = {a.f["aid"]: a.value for a in aa.plan_fields(fields, ctx(answers)).actions}
    assert got == {"1": "August", "2": "2023", "3": "May", "4": "2027", "5": "Hindi, Telugu", "6": 2}
    assert aa.rule_key(fld(7, "Which programming languages do you know?")) is None


def test_blockers_name_maintenance_and_blocked_sites():
    down = {"url": "https://static.community.workday.com/maintenance-page.html",
            "text": "Workday is currently unavailable. We are experiencing a service interruption."}
    assert aa.blockers(down, []) == ["Workday is down for maintenance right now: run this job again later"]
    denied = {"url": "https://lowes.wd5.myworkdayjobs.com/x", "text": "\nAccess Denied\nYou don't have permission"}
    assert aa.blockers(denied, [])[0].startswith("The site blocked this browser")


def test_pick_option_allows_confirm_wording_in_dropdown_options():
    assert aa.check_click_allowed({"tag": "div", "type": "", "text": "Yes, I confirm", "role": "option"}, "pick_option")
    with pytest.raises(aa.SubmitBlocked):
        aa.check_click_allowed({"tag": "button", "type": "", "text": "Confirm", "role": "option"}, "pick_option")


def test_required_detection_and_missing():
    fields = [fld(1, "Name *"), fld(2, "Notes"), fld(3, "City", required=True, value="Pune"),
              fld(4, "Pick", type="select", required=True, options=["Select...", "A"]),
              fld(5, "Q? *", type="radio", name="q", optlabel="Yes"), fld(6, "Q? *", type="radio", name="q", optlabel="No"),
              fld(7, "CV", type="file", required=True, files=1), fld(8, "Combo", role="combobox", required=True)]
    assert aa.is_required(fields[0]) and not aa.is_required(fields[1])
    assert aa.missing_required(fields) == ["Name *", "Pick", "Combo", "Q? *"]
    fields[4]["checked"] = True
    assert "Q? *" not in aa.missing_required(fields)


def test_pick_form_fields_ignores_site_search_box():
    fields = [fld(1, "Search jobs", in_form=False)] + [fld(i, f"F{i}") for i in range(2, 6)]
    assert [f["aid"] for f in aa.pick_form_fields(fields)] == ["2", "3", "4", "5"]


# ------------------------------------------------------------------ answers matching
def test_option_match_rules():
    assert aa.option_match(["Select...", "Yes", "No"], "Yes") == 1
    assert aa.option_match(["None", "No"], "No") == 1
    assert aa.option_match(["Yes, I am authorized", "No, I am not"], "Yes") == 0
    assert aa.option_match(["Bachelor's", "Master's"], "B.Tech, Computer Science and Engineering") is None
    assert aa.option_match(["Male", "Female", "Decline to self-identify"], aa.choice_targets("Prefer not to say")) == 2
    assert aa.option_match(["Yes, I am authorized"], "Yes", strict=True) is None


def test_custom_and_question_answers_win_over_learned():
    learned = aa.QuestionBank({"how many years of python experience do you have":
                               {"answer": "1", "learned_at": "2026-10-01T00:00:00Z"}})
    answers = {"custom": [{"match": "hackerrank", "answer": "https://hackerrank.com/sai"}],
               "questions": {"how many years of python experience do you have": {"answer": "3"}}}
    plan = aa.plan_fields([fld(1, "HackerRank profile"), fld(2, "How many years of Python experience do you have?")],
                          ctx(answers, learned=learned))
    assert [a.value for a in plan.actions] == ["https://hackerrank.com/sai", "3"]
    plan = aa.plan_fields([fld(2, "How many years of Python experience do you have?")], ctx({}, learned=learned))
    assert plan.actions[0].value == "1" and plan.actions[0].source == "learned"


def test_build_values_answers_win_and_start_date_by_role_type():
    answers = {"current_city": "Rourkela", "college": "NIT Rourkela", "start_date_fte": "July 2027",
               "start_date_internship": "January 2027", "willing_to_relocate": True}
    v = aa.build_values(PROFILE, answers, "fte")
    assert v["college"] == "NIT Rourkela" and v["current_city"] == "Rourkela" and v["start_date"] == "July 2027"
    assert v["willing_to_relocate"] == "Yes" and "phone" not in v
    assert aa.build_values(PROFILE, answers, "intern_6m")["start_date"] == "January 2027"
    assert aa.build_values(PROFILE, {}, "fte")["current_city"] == "Bengaluru"


# ------------------------------------------------------------------ confirmation
def test_detect_confirmation():
    assert aa.detect_confirmation("Thank you for applying! Your application ID: APP-12345", "u", "u") == (True, "APP-12345")
    assert aa.detect_confirmation("We have received your application.", "u", "u")[0]
    assert aa.detect_confirmation("Your application has been submitted", "u", "u")[0]
    assert aa.detect_confirmation("", "https://jobs.lever.co/x/1/thanks", "https://jobs.lever.co/x/1/apply")[0]
    assert not aa.detect_confirmation("Apply for this job", "https://a/b/apply?step=2", "https://a/b/apply")[0]
    assert not aa.detect_confirmation("Thank you for your interest in Acme. Apply below.", "u", "u")[0]


# ------------------------------------------------------------------ fakes for the runner
class FakeDriver:
    def __init__(self, fields, submit_enabled=False, confirm_on_submit=True, captcha=False, sai_fills=None,
                 continue_result="continue"):
        self.fields = copy.deepcopy(fields)
        self.submit_enabled, self.confirm_on_submit, self.captcha = submit_enabled, confirm_on_submit, captcha
        self.sai_fills, self.continue_result = sai_fills or {}, continue_result
        self.text, self.submits, self.resets, self.shown, self.overlays = "Apply for this job", 0, 0, 0, []

    def open(self, job):
        self.fields_now = copy.deepcopy(self.fields)
        self.text = "Apply for this job"
        return "fake"

    def url(self):
        return "https://example.com/apply"

    def scan(self):
        return copy.deepcopy(self.fields_now)

    def _set(self, aid, **kw):
        for f in self.fields_now:
            if f["aid"] == aid:
                f.update(kw)

    def apply(self, actions):
        for a in actions:
            if a.kind == "toggle":
                self._set(a.f["aid"], checked=True)
            elif a.kind == "file":
                self._set(a.f["aid"], files=1)
            elif a.kind == "select":
                self._set(a.f["aid"], value=a.f["options"][a.value])
            else:
                self._set(a.f["aid"], value=a.value)
        return list(actions), []

    def mark(self, items):
        pass

    def state(self):
        return {"url": self.url(), "captcha": self.captcha, "login": False, "errors": 0, "text": self.text}

    def confirmation(self):
        return aa.detect_confirmation(self.text, self.url(), self.url())

    def overlay(self, title, items, message, cont=False):
        self.overlays.append((title, list(items), cont))

    def submit(self):
        if not self.submit_enabled:
            raise aa.SubmitBlocked("no")
        self.submits += 1
        if self.confirm_on_submit:
            self.text = "Thank you for applying! Application ID: AB12345"
        return True

    def wait_confirmation(self, timeout_s=30):
        return self.confirmation()

    def wait_continue(self, timeout_s, tracked=()):
        for aid, kw in self.sai_fills.items():
            self._set(aid, **kw)
        self.captcha = False
        return self.continue_result, None, aa.read_answers(self.scan(), tracked)

    def show(self):
        self.shown += 1

    def hide(self):
        pass

    def reset(self):
        self.resets += 1


class FakeApi:
    def __init__(self, choices=("later",)):
        self.confirmed, self.handoffs, self.choices, self.polls = [], [], list(choices), 0

    def confirm_applied(self, job_id, notes, ref=None):
        self.confirmed.append((job_id, notes, ref))
        return True, "ok"

    def create_handoff(self, job, reason, missing, url=None):
        self.handoffs.append({"job_id": job["id"], "reason": reason, "missing": list(missing)})
        return 7

    def handoff_choice(self, hid):
        self.polls += 1
        return self.choices.pop(0) if self.choices else "pending"


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def runner(driver, api=None, answers=None, **kw):
    answers = answers if answers is not None else {"phone": "+91 90000 11111"}
    clock = Clock()
    defaults = dict(submit=True, pending_path=None, learned_path=None, harvest_first=False,
                    sleep=kw.pop("sleep", clock.sleep), clock=clock)
    defaults.update(kw)
    r = aa.Runner(api or FakeApi(), driver, lambda j: ctx(answers, company=j["company"]), **defaults)
    r.clock_obj = clock
    return r


SIMPLE = [fld(1, "Full name *", required=True), fld(2, "Email *", type="email", required=True),
          fld(3, "Phone *", type="tel", required=True), fld(4, "Resume *", type="file", required=True)]
UNKNOWN_Q = SIMPLE + [fld(5, "Why do you like databases? *", type="select", required=True,
                          options=["Select...", "Speed", "Safety"])]


def test_auto_submits_only_complete_forms_and_confirms_after_confirmation_page():
    d = FakeDriver(SIMPLE, submit_enabled=True)
    api = FakeApi()
    out = runner(d, api).run_job(job(1))
    assert out["outcome"] == "submitted" and out["ref"] == "AB12345"
    assert d.submits == 1
    assert api.confirmed == [(1, "Submitted by auto-apply (confirmed page)", "AB12345")]
    assert api.handoffs == []


def test_auto_no_confirmation_means_no_confirm_applied():
    d = FakeDriver(SIMPLE, submit_enabled=True, confirm_on_submit=False)
    api = FakeApi()
    out = runner(d, api).run_job(job(1))
    assert out["outcome"] == "unconfirmed" and api.confirmed == []


def test_auto_missing_required_hands_off_and_later_never_submits(tmp_path):
    d = FakeDriver(UNKNOWN_Q, submit_enabled=True)
    api = FakeApi(choices=["pending", "later"])
    r = runner(d, api, log=aa.RunLog(tmp_path, today="2026-10-16"))
    out = r.run_job(job(1))
    assert out["outcome"] == "needs-you" and d.submits == 0 and api.confirmed == []
    assert api.handoffs[0]["missing"] == ["Why do you like databases? *"]
    assert api.polls == 2 and r.clock_obj.t == 15  # polled every 15 s
    needs = json.loads((tmp_path / "2026-10-16" / "needs_you.json").read_text())
    assert needs[0]["why"] == "you chose Later" and d.resets >= 1


def test_handoff_timeout_without_answer_moves_on():
    d = FakeDriver(UNKNOWN_Q, submit_enabled=True)
    api = FakeApi(choices=[])  # always pending
    r = runner(d, api, ask_timeout_s=600, poll_s=15)
    out = r.run_job(job(1))
    assert out["outcome"] == "needs-you" and out["why"] == "no answer to the hand-off email"
    assert d.shown == 0 and d.submits == 0 and r.clock_obj.t >= 600


def test_handoff_now_then_continue_submits_and_learns(tmp_path):
    d = FakeDriver(UNKNOWN_Q, submit_enabled=True, sai_fills={"5": {"value": "Safety"}})
    api = FakeApi(choices=["now"])
    learned = aa.QuestionBank()
    r = runner(d, api, learned=learned, learned_path=tmp_path / "learned.yaml")
    out = r.run_job(job(1, company="Neon"))
    assert d.shown == 1 and d.overlays[-1][2] is True  # overlay with the Continue button
    assert out["outcome"] == "submitted" and d.submits == 1
    key, e = learned.find("Why do you like databases?")
    assert e["answer"] == "Safety" and e["options_seen"] == ["Select...", "Speed", "Safety"] and e["company"] == "Neon"
    assert r.learned_today == [{"question": "Why do you like databases? *", "answer": "Safety"}]
    assert (tmp_path / "learned.yaml").exists()


def test_handoff_now_but_sai_submits_himself_marks_applied_by_sai():
    d = FakeDriver(UNKNOWN_Q, submit_enabled=True, continue_result="confirmed")
    api = FakeApi(choices=["now"])
    out = runner(d, api).run_job(job(1))
    assert out["outcome"] == "submitted" and out["by_sai"] and d.submits == 0
    assert "Sai" in api.confirmed[0][1]


def test_captcha_is_handed_off_not_bypassed():
    d = FakeDriver(SIMPLE, submit_enabled=True, captcha=True)
    api = FakeApi(choices=["later"])
    out = runner(d, api).run_job(job(1))
    assert out["outcome"] == "needs-you" and "CAPTCHA" in api.handoffs[0]["reason"] and d.submits == 0


def test_pending_questions_wait_without_handoff_email():
    d = FakeDriver(UNKNOWN_Q, submit_enabled=True)
    api = FakeApi()
    pending = {"why do you like databases": {"question": "Why do you like databases?", "jobs": [], "blocks": 1}}
    out = runner(d, api, pending=pending).run_job(job(1))
    assert out["outcome"] == "waiting-answers" and api.handoffs == [] and d.submits == 0


def test_dry_run_never_submits():
    d = FakeDriver(SIMPLE, submit_enabled=False)
    r = runner(d, submit=False)
    out = r.run_job(job(1))
    assert out["outcome"] == "ready" and d.submits == 0
    d2 = FakeDriver(UNKNOWN_Q, submit_enabled=False)
    assert runner(d2, submit=False).run_job(job(2))["outcome"] == "needs-you"


def test_pacing_and_limits():
    sleeps = []
    d = FakeDriver(SIMPLE, submit_enabled=True)
    r = runner(d, max_jobs=3, per_company=1, sleep=sleeps.append, rng=__import__("random").Random(1))
    jobs = [job(1, company="A"), job(2, company="A"), job(3, company="B"), job(4, company="C"), job(5, company="D")]
    results = r.run(jobs)
    outcomes = [(x["job_id"], x["outcome"]) for x in results]
    assert outcomes == [(2, "skipped"), (1, "submitted"), (3, "submitted"), (4, "submitted")]
    assert len(sleeps) == 2 and all(90 <= s <= 240 for s in sleeps)  # between submissions, not after the last


# ------------------------------------------------------------------ learning
def test_learning_never_stores_sensitive_or_huge_values():
    qb = aa.QuestionBank()
    assert qb.learn("Password", "hunter2", "password") is None
    assert qb.learn("Enter the OTP sent to you", "123456", "text") is None
    assert qb.learn("Verification code", "999", "text") is None
    assert qb.learn("Captcha", "abcd", "text") is None
    assert qb.learn("Credit card number", "4111", "text") is None
    assert qb.learn("Upload transcript", "file.pdf", "file") is None
    assert qb.learn("Tell us about yourself", "x" * 1001, "textarea") is None
    assert qb.learn("Tell us about yourself", "I build things.", "textarea") == "tell us about yourself"
    assert list(qb.entries) == ["tell us about yourself"]


def test_read_answers_from_mock_form():
    fields = [fld(1, "Years of Java? *", value="2"), fld(2, "Shift? *", type="radio", name="s", optlabel="Day", checked=True),
              fld(3, "Shift? *", type="radio", name="s", optlabel="Night"), fld(4, "One-time password", value="1234")]
    tracked = [{"key": aa.norm_question("Years of Java? *"), "question": "Years of Java? *", "type": "text", "options": []},
               {"key": aa.norm_question("Shift? *"), "question": "Shift? *", "type": "radio", "options": ["Day", "Night"], "name": "s"},
               {"key": aa.norm_question("One-time password"), "question": "One-time password", "type": "text", "options": []}]
    got = aa.read_answers(fields, tracked)
    assert {k: v["answer"] for k, v in got.items()} == {"years of java": "2", "shift": "Day"}


def test_fuzzy_threshold_and_recency():
    qb = aa.QuestionBank({
        "how many years of professional experience do you have": {"answer": "0", "learned_at": "2026-10-01T00:00:00Z"},
    })
    assert qb.find("How many years of professional experience do you have?")[1]["answer"] == "0"
    assert qb.find("How many years of professional experience do you have in total?")[1] is not None  # 8/9 tokens
    assert qb.find("How many years of experience?")[1] is None  # overlap below 0.8
    qb.entries["years of professional experience do you have how many"] = {"answer": "1", "learned_at": "2026-10-10T00:00:00Z"}
    assert qb.find("How many years of professional experience do you have in total?")[1]["answer"] == "1"  # most recent


def test_company_specific_answers_only_reused_for_that_company():
    qb = aa.QuestionBank()
    qb.learn("Why do you want to join Rubrik?", "Because of their backup tech.", "textarea", company="Rubrik")
    e = qb.entries[aa.norm_question("Why do you want to join Rubrik?")]
    assert e["company_specific"] is True
    assert qb.find("Why do you want to join Rubrik?", company="Rubrik")[1] is not None
    assert qb.find("Why do you want to join Rubrik?", company="Okta")[1] is None


# ------------------------------------------------------------------ setup
def test_setup_prefill_and_rerun_keeps_values(tmp_path):
    path = tmp_path / "answers.yaml"
    d = aa.setup_defaults({})
    assert d["full_name"] == "Nandam Venkata Sai Raghava" and d["grad_year"] == 2027 and d["cgpa"] == 8.99
    assert d["how_did_you_hear"] == "Company careers website" and d["diversity"] == "Prefer not to say"
    assert d["phone"] == ""
    feed = iter(["", "", "", "", "+91 90000 11111"] + [""] * 6 + ["maybe", "n"] + [""] * 100)
    res = aa.run_setup(path, input_fn=lambda _p: next(feed), out=lambda *_: None)
    assert res["phone"] == "+91 90000 11111" and res["active_backlogs"] == "No"
    assert res["email"] == "sairaghava1318@gmail.com" and res["custom"] == [] and res["questions"] == {}
    # re-run: Enter keeps everything, "-" clears one field
    keys = [k for k, _p, _k in aa.SETUP_QUESTIONS]
    feed2 = iter(["-" if k == "class_10" else "" for k in keys])
    res2 = aa.run_setup(path, input_fn=lambda _p: next(feed2), out=lambda *_: None)
    assert res2["phone"] == "+91 90000 11111" and res2["class_10"] == "" and aa.load_yaml(path)["active_backlogs"] == "No"


def test_setup_answer_rules():
    assert aa.setup_answer("text", "a", "") == ("a", True)
    assert aa.setup_answer("text", "a", "-") == ("", True)
    assert aa.setup_answer("yn", "", "Y") == ("Yes", True)
    assert aa.setup_answer("yn", "No", "what") == ("No", False)


def test_known_skills_match_resume_facts():
    from api.domain.job_pack import RESUME_FACTS
    assert aa.KNOWN["skills"] == ", ".join(RESUME_FACTS["skills"])


# ------------------------------------------------------------------ pending questions / harvest
def _row(i, company, missing, blockers=()):
    return {"job": job(i, company=company), "blockers": list(blockers),
            "missing": [{"question": q, "type": t, "options": o} for q, t, o in missing]}


def test_collect_pending_dedupes_and_counts():
    rows = [
        _row(1, "A", [("Notice period? *", "text", []), ("Gender", "select", ["Select...", "Male", "Female"])]),
        _row(2, "B", [("notice period", "text", []), ("Why do you want to join B? *", "textarea", [])]),
        _row(3, "C", [("Gender *", "select", ["Male", "Female", "Other"]), ("Password", "text", [])], blockers=["CAPTCHA on the page"]),
    ]
    p = aa.collect_pending(rows)
    assert list(p)[:2] == ["notice period", "gender"]
    assert p["notice period"]["blocks"] == 2 and p["gender"]["blocks"] == 2
    assert p["gender"]["options"] == ["Male", "Female", "Other"]
    spec = p["b::why do you want to join b"]
    assert spec["company_specific"] and spec["company"] == "B" and "pack" in spec["note"]
    assert not any("password" in k for k in p)
    assert [j["id"] for j in aa.unblockable_jobs(rows)] == [1, 2]
    subject, body = aa.compose_pending_email(p, 2)
    assert subject == "Answer these once: 3 questions (unblocks 2 applications)"
    assert "--setup --pending" in body and "Options: Male | Female | Other" in body


def test_answer_pending_merges_into_answers():
    p = aa.collect_pending([_row(1, "A", [("Gender", "select", ["Male", "Female"]), ("Notice period", "text", [])])])
    feed = iter(["2", ""])
    pending, answers = aa.answer_pending(p, {"phone": "x"}, input_fn=lambda _p: next(feed), out=lambda *_: None)
    assert list(pending) == ["notice period"]
    assert answers["questions"]["gender"]["answer"] == "Female" and answers["phone"] == "x"
    plan = aa.plan_fields([fld(1, "Gender *", type="select", required=True, options=["Select...", "Male", "Female"])], ctx(answers))
    assert plan.actions[0].value == 2


def test_harvest_never_submits_and_emails_once():
    d = FakeDriver(UNKNOWN_Q, submit_enabled=False)
    mails = []
    r = runner(d, submit=False, emailer=lambda s, b: mails.append(s) or True)
    pending, rows = r.harvest([job(1, company="A"), job(2, company="B")], record=True)
    assert d.submits == 0 and len(rows) == 2
    assert pending["why do you like databases"]["blocks"] == 2
    assert mails == ["Answer these once: 1 questions (unblocks 2 applications)"]
    r.harvest([job(3, company="C")])
    assert len(mails) == 1  # nothing new: no second email
    assert [x["outcome"] for x in r.results] == ["needs-you", "needs-you"]


def test_submit_run_harvests_first_then_waits_for_answers():
    d = FakeDriver(UNKNOWN_Q, submit_enabled=True)
    api, mails = FakeApi(), []
    r = runner(d, api, harvest_first=True, emailer=lambda s, b: mails.append(s) or True)
    results = r.run([job(1, company="A")])
    assert [x["outcome"] for x in results] == ["waiting-answers"]
    assert api.handoffs == [] and d.submits == 0 and mails[0].startswith("Answer these once")


# ------------------------------------------------------------------ summary email + runner report
RESULTS = [
    {"job_id": 1, "company": "A", "role": "SDE", "url": "u1", "outcome": "submitted", "ref": "R1"},
    {"job_id": 2, "company": "B", "role": "SDE", "url": "u2", "outcome": "needs-you", "reason": "CAPTCHA on the page", "missing": []},
    {"job_id": 3, "company": "C", "role": "SDE", "url": "u3", "outcome": "unconfirmed"},
    {"job_id": 4, "company": "D", "role": "SDE", "url": "u4", "outcome": "failed", "reason": "timeout"},
    {"job_id": 5, "company": "E", "role": "SDE", "url": "u5", "outcome": "waiting-answers", "reason": "pending", "missing": ["Gender"]},
]
LEARNED = [{"question": "Phone number", "answer": "+91 1"}, {"question": "Years of Java?", "answer": "2"},
           {"question": "Expected CTC", "answer": "20 LPA"}, {"question": "Current address", "answer": "x"}]


def test_summary_email():
    subject, body = aa.compose_summary(RESULTS, LEARNED, "submit")
    assert subject == "Apply runner: 1 submitted, 2 need you"
    for part in ("Submitted (confirmed) (1)", "A - SDE: u1 (ref R1)", "Needs you (2)", "CAPTCHA on the page",
                 "Submitted but no confirmation page - check these (1)", "Skipped / failed (1)", "D - SDE: timeout",
                 "Learned from you today", "Years of Java?: 2", "--setup --pending"):
        assert part in body
    sent = []
    emailer = lambda s, b: sent.append((s, b)) or True  # noqa: E731  (mock EmailClient wrapper)
    emailer(subject, body)
    assert sent[0][0].startswith("Apply runner:")


def test_runner_report_redacts_personal_answers():
    rep = aa.build_report(RESULTS, LEARNED, "submit", "s", "f")
    assert rep["submitted"] == [{"job_id": 1, "company": "A", "role": "SDE", "url": "u1", "ref": "R1"}]
    assert [x["job_id"] for x in rep["needs_you"]] == [2, 5] and rep["needs_you"][1]["missing"] == ["Gender"]
    assert rep["unconfirmed"][0]["job_id"] == 3 and rep["failed"] == [{"company": "D", "role": "SDE", "reason": "timeout"}]
    assert rep["learned"] == [{"question": "Phone number"}, {"question": "Years of Java?", "answer": "2"},
                              {"question": "Expected CTC"}, {"question": "Current address"}]
    assert set(rep) == {"started_at", "finished_at", "mode", "submitted", "needs_you", "unconfirmed", "failed", "learned"}


def test_make_emailer_uses_email_client(monkeypatch):
    sent = []

    class FakeClient:
        def __init__(self, sender, password):
            sent.append(("init", sender))

        def send_email(self, receiver, subject, body, html=None):
            sent.append((receiver, subject))
            return True

    import api.core.clients as clients
    monkeypatch.setattr(clients, "EmailClient", FakeClient)
    monkeypatch.setenv("SENDER_EMAIL", "bot@example.com")
    monkeypatch.setenv("SENDER_PASSWORD", "pw")
    monkeypatch.setenv("RECEIVER_EMAIL", "sai@example.com")
    assert aa.make_emailer()("Apply runner: 0 submitted, 0 need you", "body") is True
    assert sent == [("init", "bot@example.com"), ("sai@example.com", "Apply runner: 0 submitted, 0 need you")]


# ------------------------------------------------------------------ API client (mock HTTP)
class _Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data or {}
        self.ok = 200 <= status < 300
        self.headers = {"content-type": "application/json"}
        self.text = json.dumps(self._data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Session:
    def __init__(self, responses):
        self.headers, self.calls, self.responses = {}, [], list(responses)

    def get(self, url, params=None, timeout=None):
        self.calls.append(("GET", url, params))
        return self.responses.pop(0)

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        return self.responses.pop(0)


def test_api_handoff_confirm_and_report(capsys):
    s = _Session([_Resp(200, {"data": {"id": 9, "choice": "pending"}}), _Resp(200, {"data": {"choice": "now"}}),
                  _Resp(200, {"message": "ok"}), _Resp(404), _Resp(200)])
    api = aa.Api("http://localhost:5050", "k", session=s)
    assert s.headers["X-App-Key"] == "k"
    assert api.create_handoff(job(3), "CAPTCHA", ["x"]) == 9
    assert s.calls[0][1] == "http://localhost:5050/api/jobs/handoff" and s.calls[0][2]["missing"] == ["x"]
    assert api.handoff_choice(9) == "now"
    assert api.confirm_applied(3, "Submitted by Sai via apply assist")[0]
    assert s.calls[2][1].endswith("/api/jobs/confirm-applied") and s.calls[2][2] == {"job_id": 3, "notes": "Submitted by Sai via apply assist"}
    assert api.runner_report({"mode": "dry-run"}) is False
    assert "runner-report endpoint not live yet" in capsys.readouterr().out
    assert api.runner_report({"mode": "dry-run"}) is True


def test_api_base_and_key(monkeypatch):
    monkeypatch.delenv("APPLY_API_BASE", raising=False)
    assert aa.api_base() == "http://localhost:5050"
    monkeypatch.setenv("APPLY_API_BASE", "http://127.0.0.1:9000/")
    assert aa.api_base() == "http://127.0.0.1:9000"
    assert aa.api_base("http://x") == "http://x"
    assert aa.app_key("abc") == __import__("hashlib").sha256(b"daily:abc").hexdigest()


def test_run_without_answers_file_says_setup_first(tmp_path):
    with pytest.raises(SystemExit) as e:
        aa.main(["--next", "--answers", str(tmp_path / "missing.yaml")])
    assert "Run --setup first" in str(e.value)


def test_looks_like_application_needs_email_or_resume():
    alert_form = [{"type": "text", "label": "Keywords"}, {"type": "text", "label": "Location"}]
    assert not aa.looks_like_application(alert_form)
    assert aa.looks_like_application(alert_form + [{"type": "email", "label": "Email"}])
    assert aa.looks_like_application([{"type": "file", "label": "Resume/CV"}])


def test_filter_boards():
    jobs = [{"board": "greenhouse"}, {"board": "workday"}, {"board": "Lever"}]
    assert aa.filter_boards(jobs, "greenhouse, lever") == [jobs[0], jobs[2]]
    assert aa.filter_boards(jobs, None) == jobs


def test_posting_key_and_job_id_for_url():
    assert aa.posting_key("https://job-boards.greenhouse.io/cloudsek/jobs/6222340004") == "6222340004"
    assert aa.posting_key("https://x.com/careers?id=1&gh_jid=6069464") == "6069464"
    assert aa.posting_key("https://jobs.lever.co/drivetrain/BC1C17BC-86ac-4f00-a1e3-0eb85aae4fdc") == \
        "bc1c17bc-86ac-4f00-a1e3-0eb85aae4fdc"
    assert aa.posting_key("https://example.com/careers") is None
    jobs = [{"id": 7, "portal_url": "https://www.squarepoint-capital.com/open-opportunities?id=6069464&gh_jid=6069464"},
            {"id": 9, "portal_url": "https://jobs.lever.co/x/other", "external_id": "x"}]
    assert aa.job_id_for_url("https://job-boards.greenhouse.io/squarepointcapital/jobs/6069464", jobs) == 7
    assert aa.job_id_for_url("https://job-boards.greenhouse.io/squarepointcapital/jobs/1", jobs) is None


def test_posting_key_reads_greenhouse_embed_token():
    assert aa.posting_key("https://job-boards.greenhouse.io/embed/job_app?for=rubrik&token=8258200") == "8258200"


def test_guard_allows_untyped_apply_button_outside_forms():
    # Oracle's "Apply Now" is a <button> with no type attribute, outside any form: the browser calls it "submit"
    assert aa.check_click_allowed({"tag": "button", "type": "submit", "typeattr": "", "text": "Apply Now", "in_form": False},
                                  "open_application")
    with pytest.raises(aa.SubmitBlocked):
        aa.check_click_allowed({"tag": "button", "type": "submit", "typeattr": "submit", "text": "Apply Now", "in_form": False},
                               "open_application")


def test_oracle_one_time_pass_code_is_read_and_matched_by_alias():
    body = "Hello Venkata Sai Raghava, You must confirm your identity using the one-time pass code : 803596 Note"
    assert aa.code_in_mail(body) == "803596"
    assert aa.ORACLE_CX.search("https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/job/25017908")


def test_national_number_keeps_numbers_that_start_with_91():
    assert aa.national_number("9110307856") == "9110307856"
    assert aa.national_number("+91 9110307856") == "9110307856"
    assert aa.national_number("+91 91103 07856") == "9110307856"


def test_min_quals_problem():
    assert aa.min_quals_problem("Requirements: 3+ years of experience in Java") == "asks for 3+ years of experience"
    assert aa.min_quals_problem("0-2 years of experience; freshers welcome") is None
    assert aa.min_quals_problem("Bachelor's in CS. 5 years of relevant experience preferred, 1 year experience required") ==         "asks for 1+ years of experience"  # Sai: 0 experience is a must
    assert aa.min_quals_problem("At least 6 months of work experience") == "asks for 6+ months of work experience"
    assert aa.min_quals_problem("A 6-month internship from January 2027") is None
    assert aa.min_quals_problem("We have 20 years of industry experience as a company") is None
    assert aa.min_quals_problem("Master's degree in CS is required.").startswith("requires a higher degree")
    assert aa.min_quals_problem("Open to 2025 batch graduates") == "only for the 2025 batch"
    assert aa.min_quals_problem("Open to 2026 and 2027 batch graduates") is None
    assert aa.min_quals_problem("B.Tech in CSE, strong C++") is None


def test_run_retries_page_loading_problems_once_at_the_end():
    r = runner(FakeDriver(SIMPLE, submit_enabled=True))
    calls = []

    def run_job(j):
        calls.append(j["id"])
        reason = "Workday sign-in failed (the Workday page didn't finish loading)" if j["id"] == 1 else "CAPTCHA on the page"
        return r._record(j, "needs-you", reason=reason)
    r.run_job = run_job
    r.run([job(1), job(2, company="Other Co")])
    assert calls == [1, 2, 1]  # the CAPTCHA one is not retried


def test_avature_register_purpose_only_allows_confirm_buttons():
    aa.check_click_allowed({"tag": "button", "type": "submit", "text": "Confirm"}, "avature_register")
    for text in ("Submit", "Apply", "Send application"):
        try:
            aa.check_click_allowed({"tag": "button", "type": "submit", "text": text}, "avature_register")
        except aa.SubmitBlocked:
            continue
        raise AssertionError(text)


def test_posting_key_reads_keka_job_ids():
    assert aa.posting_key("https://peepalco.keka.com/careers/jobdetails/92951?src=Linkedin") == "92951"


def test_toggle_label_purpose_only_allows_labels():
    aa.check_click_allowed({"tag": "label", "text": "I have read the Important Privacy Information"}, "toggle_label")
    try:
        aa.check_click_allowed({"tag": "button", "type": "submit", "text": "Next"}, "toggle_label")
    except aa.SubmitBlocked:
        return
    raise AssertionError("a button must not pass as a checkbox label")


def test_dismiss_purpose_allows_only_banner_buttons():
    aa.check_click_allowed({"tag": "button", "type": "submit", "text": "ACCEPT"}, "dismiss")
    try:
        aa.check_click_allowed({"tag": "button", "type": "submit", "text": "Submit application"}, "dismiss")
    except aa.SubmitBlocked:
        return
    raise AssertionError("dismiss must not press a submit button")


def test_other_college_campus_drives_are_skipped():
    assert aa.other_campus("2027 Software Engineer - Campus Graduate Program - IIT BHU")
    assert aa.other_campus("Software Engineer (BITS Pilani)")
    assert not aa.other_campus("Campus Hire 2027 - Software Engineer")
    assert not aa.other_campus("Graduate Engineer - NIT Rourkela")
    assert not aa.fresher_ok({"role": "2027 SWE - Campus Graduate Program - IIT Kanpur"})
    assert "another college" in aa.min_quals_problem("This program is only open to students of IIT Kanpur.")
    assert aa.min_quals_problem("Open to all 2027 graduates.") is None


def test_min_quals_ignores_form_questions():
    page = ("New Grad Software Engineer. Graduating between December 2026 and July 2027.\n"
            "Do you have over 2 years of industry work experience (non-internship experience)? *\nYes\nNo")
    assert aa.min_quals_problem(page) is None
    assert "2+ years" in aa.min_quals_problem("Requirements: 2+ years of professional experience. Apply now?")


def test_tailored_resume_is_used_and_falls_back():
    class D:
        resume = b"original"
    seen = []
    r = runner(D(), tailor=lambda job, text: seen.append(text) or b"tailored")
    r._posting = "x" * 400
    r._use_tailored_resume({"company": "Acme"})
    assert r.d.resume == b"tailored" and seen == ["x" * 400]

    def boom(job, text):
        raise RuntimeError("quota")
    r.tailor = boom
    r._use_tailored_resume({"company": "Acme"})
    assert r.d.resume == b"original"
    r.tailor = lambda job, text: b"tailored"
    r._posting = "short"  # posting not readable: never tailor blind
    r._use_tailored_resume({"company": "Acme"})
    assert r.d.resume == b"original"


def test_month_ranges_from_zero_pass_and_phone_code_lists_are_ignored():
    assert aa.min_quals_problem("Experience: 0-6 months of experience in software development.") is None
    assert "6+ months" in aa.min_quals_problem("At least 6 months of work experience required.")
    assert aa.phone_codes_only("How Did You Hear About Us?*", ["Aruba (+297)", "India (+91)"])
    assert not aa.phone_codes_only("Country Phone Code*", ["India (+91)"])
    assert not aa.phone_codes_only("How Did You Hear About Us?*", ["Job Board", "India (+91)"])
    ai = aa.make_ai_answerer({}, generate=lambda p: {"answer": "India (+91)"}, path=None)
    assert ai("How Did You Hear About Us?*", "select", ["India (+91)"], "JLL") is None


def test_workday_search_select_box_may_be_opened_but_not_buttons():
    box = {"tag": "input", "type": "text", "uxi": "selectinput", "text": "", "role": ""}
    assert aa.check_click_allowed(box, "open_dropdown", False) is True
    with pytest.raises(aa.SubmitBlocked):
        aa.check_click_allowed({"tag": "button", "type": "submit", "uxi": "", "text": "Submit"}, "open_dropdown", False)
    with pytest.raises(aa.SubmitBlocked):
        aa.check_click_allowed({"tag": "input", "type": "text", "uxi": "", "text": ""}, "open_dropdown", False)


def test_model_safety_labels_are_not_saved_as_answers():
    ai = aa.make_ai_answerer({}, generate=lambda p: {"answer": "User Safety: safe"}, path=None)
    assert ai("Country*", "text", [], "SingleStore") is None


def test_previously_employed_with_previously_after_the_company():
    assert aa.rule_key({"label": "Have you worked for Edwards previously?*"}) == "previously_employed"


def test_know_anyone_at_the_company_is_no():
    assert aa.rule_key({"label": "Do you know anyone who works at Smartsheet?*"}) == "is_referral"
    assert aa.rule_key({"label": "Do you have any friends or family employed at Rubrik?"}) == "is_referral"
    assert aa.rule_key({"label": "Do you know Python?"}) is None


def test_how_soon_can_you_join_and_number_only_ctc():
    assert aa.rule_key({"label": "How soon can you join?"}) == "start_date"
    ctc = fld(1, "Current CTC", type="number", required=True)
    plan = aa.plan_fields([ctc], ctx({"current_ctc": "0 / Not applicable"}))
    assert [(a.kind, a.value) for a in plan.actions] == [("text", "0")]


def test_mechanical_and_hardware_design_titles_are_not_my_field():
    # Caterpillar and Analog Devices went through as "engineer" roles
    for role in ("Model Based Developer  - Transmission / Drivetrain", "Associate Design Engineer", "Design Evaluation Engineer"):
        assert aa.NOT_MY_FIELD.search(role), role
    for role in ("Software Design Engineer", "Software Engineer - Structural Data", "Data Engineer"):
        assert not aa.NOT_MY_FIELD.search(role), role


def test_nested_json_answer_is_unwrapped():
    assert aa._unwrap_answer('{"answer": "January 2027"}') == "January 2027"
    assert aa._unwrap_answer("January 2027") == "January 2027"
    assert aa._unwrap_answer("{not json") == "{not json"
    assert aa._unwrap_answer('```json\n{"answer": "B.Tech"}\n```') == "B.Tech"


def test_experience_ceiling_is_not_a_requirement():
    # Stripe new grad: "no more than 18 months of professional experience" was read as "18+ months required"
    assert aa.min_quals_problem("New grad candidates should have no more than 18 months of professional experience") is None
    assert aa.min_quals_problem("Requires 18 months of work experience") == "asks for 18+ months of work experience"
    assert aa.min_quals_problem("3+ years of experience") == "asks for 3+ years of experience"


def test_start_date_follows_the_role():
    # Sai: winter internships from December 2026, 6-month internships from January 2027, full-time from May 2027
    assert aa.build_values({}, {}, None, "Software Engineer (CPD) - Winter Intern")["start_date"] == "December 2026"
    assert aa.build_values({}, {}, None, "Intern, Software Engineer")["start_date"] == "January 2027"
    assert aa.build_values({}, {}, None, "SDE I")["start_date"] == "May 2027 (after graduation)"


def test_start_month_maps_to_quarter_options():
    opts = ["Q4 2026 (October - December)", "Q1 2027 (January - March)", "Q2 2027 (April - June)", "Q3 2027 (July - September)"]
    assert aa.option_match(opts, aa.targets_for("start_date", "May 2027 (after graduation)")) == 2
    assert aa.option_match(opts, aa.targets_for("start_date", "December 2026")) == 0
