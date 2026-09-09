# Suggested Features

Concrete, implementable feature ideas to make the Productivity Automations project more useful and impressive.

---

## 🔥 High Priority — Quick Wins

### 1. Topic-Based Problem Selection
**Instead of fully random**, let the user select DSA topics they want to focus on.

**How it works:**
- Add a topic selector in the dashboard (Arrays, Trees, Graphs, DP, etc.)
- Store selected topics in the Settings table
- Pass the selected topic to the LLM prompt so it picks problems from that category
- Striver's A2Z sheet is already organized by topic — leverage this structure

**System Design Concept:** Strategy Pattern (different topic strategies)

---

### 2. Difficulty Progression System
**Gradually increase difficulty** based on the user's completion rate.

**How it works:**
- Track completion rates per difficulty: Easy / Medium / Hard
- If Easy completion rate > 80%, auto-shift to more Medium problems
- If Medium > 60%, start mixing in Hard
- Show difficulty distribution chart in the dashboard

**System Design Concept:** State Machine (Easy → Medium → Hard transitions)

---

### 3. Email Template with HTML Formatting
**Current emails are plain text.** Make them beautiful with HTML.

**How it works:**
- Create HTML email templates with:
  - Syntax-highlighted C++ code blocks
  - Color-coded difficulty badges (🟢 Easy, 🟡 Medium, 🔴 Hard)
  - Clickable LeetCode/Striver links as buttons
  - Problem number and streak counter
- Use Python's `email.mime.text.MIMEText` with `'html'` subtype

**System Design Concept:** Template Method Pattern

---

### 4. Daily/Weekly Progress Report Email
**Send a summary** of problems received, completed, and pending.

**How it works:**
- New `ReportNotifier` class (inheriting `BaseNotifier`)
- Triggered weekly via a new cron schedule (e.g., Sunday 9:00 AM IST)
- Includes:
  - Total problems sent this week
  - Completion rate
  - Current streak
  - Weak topics (most uncompleted)
  - Leaderboard position (if multi-user)

---

### 5. Streak Tracking & Gamification
**Track daily solving streaks** to motivate consistency.

**How it works:**
- Add `streak_count` and `last_solve_date` to Settings
- When a problem is marked completed, check if it's within 24h of the last solve
  - Yes → increment streak
  - No → reset to 1
- Display streak prominently on the dashboard with fire 🔥 emoji
- Send a "Don't break your streak!" reminder email if no problem solved today

---

## 🟠 Medium Priority — Meaningful Upgrades

### 6. Problem Bookmarking & Notes
**Let users bookmark** problems and add personal notes.

**How it works:**
- Add `is_bookmarked` and `user_notes` columns to NotificationLog
- New API endpoints: `PUT /api/logs/:id/bookmark`, `PUT /api/logs/:id/notes`
- Dashboard tab for bookmarked problems with inline note editing
- Export bookmarks as a study guide PDF

---

### 7. Multi-Language Code Solutions
**Support more than just C++.**

**How it works:**
- Add a language preference setting (C++, Python, Java, JavaScript)
- Modify the LLM prompt to generate solutions in the selected language
- UI toggle in settings
- Store language per problem in the log for mixed-language review

---

### 8. Spaced Repetition v2 — SM-2 Algorithm
**Current retry logic is random (50% chance).** Use a proper spaced repetition algorithm.

**How it works:**
- Implement the [SM-2 algorithm](https://en.wikipedia.org/wiki/SuperMemo#Description_of_SM-2_algorithm)
- Add columns: `ease_factor`, `interval_days`, `repetition_count`, `next_review_date`
- When a user marks a problem:
  - "Easy" → longer interval
  - "Hard" → shorter interval  
  - "Again" → reset to 1 day
- Cron checks `next_review_date` and sends problems due for review

**System Design Concept:** Algorithm Design, State Management

---

### 9. Problem Categories & Tags Dashboard
**Visual analytics** of problem distribution.

**How it works:**
- Parse and store problem categories (Array, Tree, Graph, DP, etc.)
- Dashboard charts:
  - Pie chart of problems by category
  - Bar chart of solved vs unsolved per category
  - Timeline of problems solved per day
- Use Chart.js or Recharts in the React frontend

---

### 10. Slack/Discord Notifications
**Alternative to email** — send problems via Slack or Discord webhooks.

**How it works:**
- New `SlackNotifier` and `DiscordNotifier` classes
- User configures webhook URL in settings
- Format problems as rich Slack Block Kit / Discord Embed messages
- Factory pattern already supports this — just add new notifier types

**System Design Concept:** Open/Closed Principle (extend without modifying existing code)

---

## 🟡 Lower Priority — Nice to Have

### 11. Problem Search & Filter
- Full-text search across problem titles and descriptions
- Filter by: difficulty, solved/unsolved, date range, category
- Sort by: date, difficulty, status

### 12. Export to Notion / Google Sheets
- One-click export of all problems to a Notion database
- Google Sheets integration for tracking in a spreadsheet
- Use Notion API / Google Sheets API

### 13. Browser Extension
- Chrome/Brave extension that shows today's problem as a popup
- Mark as completed directly from the extension
- Shows streak counter in the toolbar

### 14. Mobile PWA
- Convert the React frontend to a Progressive Web App
- Push notifications for new problems (using Service Workers)
- Offline support for viewing previously sent problems

### 15. Collaborative Features
- Share your problem list with study partners
- Compare completion rates
- Group challenges: "Solve 5 Graph problems this week"

### 16. LeetCode API Integration
- Auto-verify if the user actually submitted a solution on LeetCode
- Pull submission status via LeetCode's GraphQL API
- Auto-mark problems as completed when accepted on LeetCode

### 17. Custom Problem Lists
- Let users paste a custom list of problems (not just Striver's sheet)
- Support NeetCode 150, Blind 75, company-specific lists
- The system works through the list sequentially

### 18. Revision Calendar
- Visual calendar showing which problems are due for revision
- Color-coded by urgency (overdue = red, due today = yellow, upcoming = green)
- Click a date to see all problems scheduled for that day

---

## Implementation Suggestions

> **Start with features 1–5** — they're quick wins that make the project significantly more impressive for a portfolio/presentation.

> **Features 6–10** add depth and show understanding of real-world patterns like spaced repetition algorithms and notification channel abstraction.

> **Features 11+** are stretch goals that turn this from a class project into a real product.
