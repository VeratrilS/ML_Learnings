# Apply assist

Fills job applications in Chrome on your laptop, using only your own data: `answers.yaml`, your Job Radar
profile, the job's pack (cover note, "why this company"), and answers you typed before. Anything it doesn't
know stays empty and gets an orange outline.

Chrome runs off-screen and minimized, so you can keep using your laptop. A window only comes up when the
tool needs you (or when you add `--visible`).

## Before you start

The tool talks to the local app, so start that first: `tools\local_server\start_local.bat`
(or set `APPLY_API_BASE` / pass `--api URL` to use another server).

One-time install:

```
pip install playwright pyyaml requests python-dotenv
python -m playwright install chromium
```

## 1. Setup (do this once)

```
python tools/apply_assist/assist.py --setup
```

Press Enter to keep a value, or `-` to clear it. Everything goes into `tools/apply_assist/answers.yaml`, which
is never committed. If you run it again, it shows what you saved before and only changes what you edit.

## 2. Apply to one job (you press Submit)

```
python tools/apply_assist/assist.py --pick        # choose from the top 10 open jobs
python tools/apply_assist/assist.py --next        # the newest good match
python tools/apply_assist/assist.py --job 224     # a specific Job Radar id
```

The form is filled, then the window comes up with a box listing what's still yours to do. Check every field
and press the site's Submit button yourself. When you close the window, the console asks "Did you submit?".
If you answer `y`, the job is marked applied in Job Radar.

## 3. Many jobs

```
python tools/apply_assist/assist.py --auto                      # dry run: fills each form, never submits
python tools/apply_assist/assist.py --auto --submit --max 25    # really submits complete forms
```

Rules for `--submit`:
- It only clicks Submit when every required field came from your data and there's no CAPTCHA or login.
- A job counts as applied only after a confirmation page ("thank you for applying"). With no confirmation,
  it's listed under "check these" and isn't marked.
- If it gets stuck (CAPTCHA, login, a flow it doesn't know), you get an email with **Complete it now** and
  **Later** buttons. "Complete it now" brings the filled window up. Finish it, then click
  **✅ I finished — continue**. "Later" (or no answer in 10 minutes) saves the job to
  `runs/<date>/needs_you.json`, and the tool moves on.
- It applies to at most one job per company per run (`--per-company`), skips any company and role you
  applied to in the last 30 days, and waits 90–240 s between submissions.
- At the end of the run you get a summary email ("Apply runner: N submitted, M need you").

## Run it by yourself (no Claude needed)

```
python tools/apply_assist/assist.py --auto --submit --attended --max 10
```

It submits each complete form. When a site needs you, the Chrome window comes up and the runner waits. This
happens when the site emails a security code after Submit (Greenhouse does this), shows a CAPTCHA, or asks a
question the runner can't answer. Type the code, or fix what's outlined in orange, and press Submit on the page.
The runner sees the "thank you" page, marks the job applied, and moves on to the next one. It waits up to 10
minutes per code. You can also paste a code into `security_codes.yaml` under the job's id (for example
`'224': AbC12345`). `--only 5,1,10` limits a run to those Job Radar ids.

## Run it every day

Run these two commands once, in a normal (non-admin) terminal. They make the runner apply every day at 10:30 and
19:30 (after the morning job scan). The laptop has to be on, and on a network where Gmail works (a hotspot, not campus
Wi-Fi):

```
schtasks /Create /TN "ApplyRunner 10-30" /TR "C:\desktop\Sem-7\ML_Fun\tools\apply_assist\daily_run.cmd" /SC DAILY /ST 10:30
schtasks /Create /TN "ApplyRunner 19-30" /TR "C:\desktop\Sem-7\ML_Fun\tools\apply_assist\daily_run.cmd" /SC DAILY /ST 19:30
```

To stop them: `schtasks /Delete /TN "ApplyRunner 10-30" /F` (and the same for 19-30). Each run's output goes to
`tools\apply_assist\runs\daily.log`. Results also appear in Job Radar's Application desk.

## What the runner has learned (site playbook, 2026-10-17)

| Site | What happens | What the runner does |
|---|---|---|
| Greenhouse (Zscaler, Okta, HackerRank, SingleStore, Rubrik, Point72) | After Submit, an 8-character security code is emailed (`no-reply@us.greenhouse-mail.io`). It's valid only for that Submit, because every Submit sends a new one. | Keeps the form open, reads the newest code for that company from Gmail (or you type it in), enters it and submits. |
| Greenhouse dropdowns | The choices only appear once the dropdown is opened, and a hidden phone country picker adds 240 invisible "options". | Reads only visible options. For required dropdowns it opens them, reads the real choices and lets the AI pick one. |
| School search boxes (IMC) | NIT Rourkela isn't in some schools' lists. | Tries "NIT Rourkela" and the full name, then picks "Other". |
| Lever (Hevo Data) | reCAPTCHA after Submit. | Hands the form to you, never solves it. |
| Workday (Barclays, Lowe's, Cisco, ...) | Create Account is blocked for automated browsers by a hidden bot check, and no email is sent. | You create the account once (password in `answers.yaml`). After that it signs in and fills every page. |
| Company sites (Qualcomm, Microsoft, Amazon, Apple, Goldman, TI) | Not a standard form. A "thank you" can come from a talent-network signup. | Never auto-submits there. Lists them for you. |
| Expired postings ("This job has expired") | | Logged as `expired` and never tried again. |
| Campus Wi-Fi | Blocks Gmail IMAP (993) and Postgres (5432). | Falls back to the production app. Inbox reading needs a hotspot. |

Facts the AI always uses: 0 years of professional experience (internships only), languages English, Hindi and
Telugu, education Aug 2023 – May 2027. If an AI answer is wrong, fix it in `ai_answers.yaml`: it's reused.

## Workday (Cisco, Barclays, Mastercard, Deutsche Bank, ...)

Each Workday site needs a candidate account. The tool creates it with your email and one password, then signs in
with it on later runs. It generates the password the first time and saves it in `answers.yaml`
(`workday_password`). The password is never printed, so open the file to see it. The tool then fills every page,
presses **Save and Continue** after each one, and stops on the **Review** page. You press Submit (or let
`--auto --submit` do it).

If a site emails you a verification link, click it, then run the same job again. If a page has a question it
can't answer, the window comes up with that field outlined in orange.

## What it answers by itself

You don't need to answer the standard screening questions. Unless `answers.yaml` says otherwise, it uses these
defaults (`AUTO_DEFAULTS` in `assist.py`):

- Country India, authorised to work in India: Yes, need visa sponsorship: No
- Current company "Student, NIT Rourkela", current title "B.Tech student (final year)"
- Worked for this company before / relatives there / outside business / government procurement: No
- Willing to relocate, work from office, available to start or intern: Yes. Earliest start: July 2027 (full-time) or
  January 2027 (internship). Notice period: Immediate
- Address: NIT Rourkela, Sector 1, Rourkela, Odisha 769008. Active backlogs: No. 18 or older: Yes
- Privacy / consent / "I acknowledge" questions are accepted. Gender, race and similar questions get the
  "decline to answer" option when the form has one. It never guesses your gender.
- "How did you hear about us": careers website, or the closest option the form offers

Any other required question goes to the AI (Gemini, with OpenRouter as a backup). It sees your resume facts and
the answers above, but not your phone, email, address or date of birth. It answers in 1-3 sentences or picks one
of the form's options. It returns nothing for facts it can't know (date of birth, ID numbers, criminal record),
and those stay orange for you. AI answers are saved in `ai_answers.yaml` and reused. Each run's summary email
lists them, so check them, and edit that file to fix any. Use `--no-ai` to turn this off.

If the local app isn't running, the tool uses the production app automatically (same database).

## Questions it can't answer

Each `--auto` run starts by collecting the required questions it couldn't answer from all the forms. You get
one email listing them ("Answer these once: …"). You can also collect them on their own with `--harvest`.
Answer them all in one go:

```
python tools/apply_assist/assist.py --setup --pending
```

Jobs held up only by those questions are retried on the next run. Anything you type into a form after a
hand-off is saved to `learned_answers.yaml` and reused later. Passwords, OTPs, codes, card numbers and
uploads are never saved. Answers that name a company (like "Why Rubrik?") are reused only for that company.
Edit either YAML file if something is wrong.

## Files (all gitignored)

`answers.yaml`, `learned_answers.yaml`, `ai_answers.yaml`, `pending_questions.yaml`, `resume.pdf` (downloaded once from
Job Radar), `.profile/` (the Chrome profile, so logins stick), `runs/` (logs and screenshots).

Other flags: `--visible` shows the window the whole time, `--headless` runs with no window and only checks the
fill (it never waits for you), and `--handoff-wait` / `--ask-timeout` set the wait times in minutes.
