# Who is working on what

Two AI agents work in this repo: **Claude Code** and **Antigravity**. Read this file before editing, and update it when you start or finish a task.

## Rules

1. Before starting: `git pull`, then `git status`. If a file has uncommitted changes you didn't make, the other agent is using it — don't edit it.
2. Claim your files below before editing them. Remove the claim when you commit.
3. Stage only your own files (`git add <file> ...`), never `git add -A` / `git add .`.
4. Shared hot spots — `api/app.py`, `src/App.jsx`, `src/lib/features.jsx`, `src/pages/Today.jsx`, `requirements.txt`: keep edits small (one import + one registration line), commit them quickly, and pull right before editing.
5. Commit as `SaiRaghava`, push to `main`, and check the Vercel deploy is live.
6. New features ship as **beta** (see `src/lib/features.jsx`) unless Sai approves otherwise.

## Current claims

| Agent | Task | Files | Since |
|---|---|---|---|
| Antigravity | Job Radar | `api/domain/job_radar.py`, `src/pages/JobRadar.jsx`, `src/components/JobRadarCard.jsx`, edits in `api/app.py`, `src/App.jsx`, `src/pages/Today.jsx`, `src/components/CommandPalette.jsx`, `src/lib/centuryCatalog.js`, `src/lib/featuresList.js` | 2026-10-15 |
| Claude Code | — (idle, waiting for Sai) | — | — |
