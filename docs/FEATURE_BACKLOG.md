# Feature backlog (not built yet)

Ideas to build later, ranked by how much they keep daily practice going. All new ones ship as **beta** first.
Each line: what it does, why it sticks, rough size (S/M/L), and what existing data it reuses.

## Habit loop (the "addictive" ones)

1. **Daily Spar (2-minute warm-up)** — S
   One quick question a day (pattern spotter, complexity, or a flashcard) before anything else; a streak of its own.
   Why: tiny, finishable task that starts the session. Reuses: problem bank, flashcards.

2. **Ippo rival ghost races** — M
   A weekly race against your own best past week (problems, focus minutes). Beat the ghost → boss-fight XP.
   Why: competition without other people. Reuses: weekly report data, XP, Gym boss fights.

3. **Dempsey Roll combo** — S
   Solve 3 problems of the same pattern within 90 minutes → combo multiplier on XP.
   Why: rewards focused pattern practice. Reuses: logs (topic, completed_at), XP.

4. **Win Jar** — S
   Log small wins (solved a Hard, applied somewhere, finished a video); confetti + they resurface in the weekly email.
   Why: makes progress visible on bad days. Reuses: journal, weekly report.

5. **Opponent cards for Apple problems** — M
   Each Medium/Hard Apple-sheet problem is a "rival" card; solving flips it to defeated in a gallery.
   Why: collection mechanic over a fixed list. Reuses: Apple sheet tracker.

6. **Round Bell focus timer** — S
   Boxing-round timer (e.g. 3 × 25 min rounds, 60 s rest bell) with a "ROUND 3/12" tally on Today.
   Why: turns focus blocks into a game. Reuses: focus sessions.

7. **Focus Gate for the daily episode** — S
   Today's anime episode link unlocks after one 25-minute focus block (never locked forever).
   Why: reward after work, not before. Reuses: watch series, focus sessions.

## Learning that sticks

8. **Pattern Spotter drill** — S/M
   Read a problem statement, name the pattern + complexity in 60–90 s, no code; graded; FSRS schedules misses.
   Reuses: problem bank topics, FSRS.

9. **Hint ladder + spaced re-solve** — M
   Log whether a problem was solved alone or with hints; hint-assisted ones come back as blank-editor re-solves.
   Reuses: logs, FSRS revision.

10. **What-If after a solve** — S
    One counterfactual question after marking solved ("what breaks if n doubles / input is sorted?").
    Reuses: LLM write-ups.

## Interview & exam

11. **Interview Countdown** — M
    Add an OA/interview date on a Placements card → day-by-day taper plan from the Apple sheet + weak topics + mocks.
    Reuses: placements, Apple sheet, insights, interview lab.

12. **Night-before cram sheet** — S
    One page per subject from past-paper picks, weakest flashcards and PDF topics, emailed the evening before the exam.
    Reuses: syllabus exam dates, papers predictor, flashcards, PDF extract.

## Notes for building

- Register new pages in `src/lib/features.jsx` (beta), not in the core nav.
- Prefer features that need no Gemini quota (the free tier runs out); LLM-based ones should degrade gracefully.
- Keep each one testable like `tests/test_weekly.py` / `tests/test_sheets.py`.
