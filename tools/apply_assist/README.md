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

`answers.yaml`, `learned_answers.yaml`, `pending_questions.yaml`, `resume.pdf` (downloaded once from
Job Radar), `.profile/` (the Chrome profile, so logins stick), `runs/` (logs and screenshots).

Other flags: `--visible` shows the window the whole time, `--headless` runs with no window and only checks the
fill (it never waits for you), and `--handoff-wait` / `--ask-timeout` set the wait times in minutes.
