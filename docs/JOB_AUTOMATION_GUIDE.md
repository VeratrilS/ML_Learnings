# Job automation: how to use it

A short guide for Sai. Everything here describes what is built today; planned items are listed at the end.

## 1. What it does, and what it never does

**It does:**
- Every morning, it reads the public job boards of 100+ companies (Greenhouse, Lever, Ashby, SmartRecruiters, Workday). It keeps software roles in India that aren't senior and were posted in the last 45 days.
- It gives each opening a match score against your resume and emails you the best new ones.
- It shows everything on the Job Radar page with the official application link.
- It fills the standard fields of an application form for you (Autofill).
- It writes paste-ready answers for one job: cover note, "why this company", common questions and resume highlights.
- It reminds you to follow up 7 and 14 days after you apply.

**It never:**
- **Submits an application.** You always press Submit yourself. Company portals use CAPTCHA, SSO/OTP logins and resume uploads that a bot can't (and shouldn't) get past, and botting them can get your email flagged.
- **Logs an application you didn't confirm.** A job counts as applied only after you tap "I applied". Your application records ("receipts") are your own notes, not emails from the company.

## 2. Daily timeline (IST)

| Time | What happens |
|---|---|
| 07:00 | Live scan of all company boards. If new good matches turn up, you get an email ("N new job openings for you") with links. |
| 09:00 | Follow-up check. If any application is 7 or 14 days old, you get a reminder email. |

The scan runs at most once every 20 hours. If nothing new qualifies, you get no email that day.

## 3. One-time setup

1. Open Job Radar at `https://productivity-automations.vercel.app/#/job-radar`. It's also listed in the **Beta Lab**.
2. In the yellow **Autofill** box, press **Copy Code**. Don't use the "Autofill (Drag to Bookmarks)" button. The site's framework blocks that kind of link, so dragging it doesn't work.
3. Make the bookmark by hand (desktop Chrome/Edge):
   - Press Ctrl+Shift+B to show the bookmarks bar. Right-click it and choose **Add page**.
   - Name: `Autofill`.
   - URL: type `javascript:` and paste the copied code straight after it, with no space.
   - Save.
4. On a phone, create the same bookmark. On the job page, type `Autofill` in the address bar and tap the bookmark when it shows up in the suggestions. Some mobile browsers don't run bookmarks like this. If yours doesn't, apply from a laptop.

The code contains your profile (name, email, links, college, CGPA). If you change your profile, copy the code again and update the bookmark.

## 4. Applying to one job in about 30 seconds

1. In Job Radar (or the morning email), open the job's official link.
2. On the application form, click your **Autofill** bookmark.
   - **Green outline**: filled for you (name, email, phone, LinkedIn, GitHub, LeetCode, college, degree, graduation year, CGPA, location). It also answers "authorised to work in India" = Yes and "need sponsorship" = No.
   - **Orange outline**: still needs you, usually the resume upload, required dropdowns and custom questions. A box in the corner lists them.
   - It never overwrites a field that already has text in it.
3. Attach your resume. For a version tuned to this job, press **Tailored Resume** on the job in Job Radar. It downloads a one-page PDF named `NandamVenkataSaiRaghava_<Company>.pdf`. It uses only your real resume facts and changes only their order: the projects, experience and skills that match the job come first. It never adds a skill you don't have.
4. For the orange questions, go back to Job Radar and press **Prepare Answers** on that job. Copy each answer into the form. Check the availability and relocation answers: they are defaults.
5. Read the whole form and press **Submit** on the company site.
6. Back in Job Radar, tap **I Applied** (you can add the confirmation number if one is shown). This records the date and sets up the 7- and 14-day reminders.

## 5. Reading the list

- **Match score (0–100):** a fixed formula with no AI guessing. Every job starts at 35 and gets +5 for each of your resume skills it mentions (up to +40). It gets +20 if it reads as early-career (new grad, campus, 2026/2027, SDE-1, intern), −15 if it asks for 2 years of experience, and −35 for 3+. The live list shows jobs scoring 50 or more. The email only includes jobs scoring 60 or more.
- **"~18–28 LPA (est.)":** a typical fresher pay range for that company, taken from public reports. It's an estimate, not an offer and not from the job post. The **≥ 15 LPA** toggle (on by default) hides companies estimated below that.
- **Source badge** (Greenhouse, Lever, Ashby, SmartRecruiters, Workday): where the posting was read from. These are the companies' own career boards.
- **Curated List (Not Live):** an older saved list further down the page. Its roles weren't checked by the live scan, so open the link before trusting that a role is still open.

## 6. Troubleshooting

**No jobs in the morning email / no email at all.** The email lists only *new* openings that score 60+ and come from companies with est. CTC ≥ 15 LPA (or from the main big-tech list). On a quiet day nothing qualifies and no email is sent. The Job Radar page still shows everything scoring 50+. You can also turn off the ≥ 15 LPA toggle to see more.

**Autofill didn't fill a field.** It matches fields by their labels (e.g. "First name", "LinkedIn"). Unusual labels, dropdowns and file uploads aren't filled, so type those yourself. If nothing happens at all, check that the bookmark URL starts with `javascript:` and that you copied the whole code. Some sites block bookmarklets. Then use Prepare Answers and copy by hand.

**Prepare Answers looks generic / shows "Regenerate".** The AI (Gemini, with OpenRouter as a backup) ran out of free quota, so you got the built-in template answers. They're accurate (built only from your resume facts) but plainer. Press **Regenerate** later in the day for the AI version.

**Applied by mistake.** Use the undo option on that job to remove the "applied" mark. This also cancels its reminders.

## 7. Coming next (not built yet)

- **Approve / Skip by email:** a morning email with one-click Approve or Skip per job, with approved jobs gathered in an "Approved — to apply" section. The code is written but not switched on yet, so you won't get these emails.
- **Telegram approvals:** the same approve/skip flow in Telegram (needs a bot token from you).
- **Company prep:** each company's top LeetCode problems plus a 7-day plan for jobs you've applied to.
