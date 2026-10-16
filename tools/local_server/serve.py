"""
Run the whole app on this laptop: API + built frontend on http://localhost:5050, and every scheduled job
(the same ones .github/workflows/scheduler.yml sends to Vercel), so nothing depends on Vercel.

Data: uses the production Postgres (Neon) URL from .env.production.local when present, so local and
production share the same jobs/applications. Secrets (Gemini, Gmail, passcode) come from .env.

Usage:
  python tools/local_server/serve.py            # foreground, logs to the console
  pythonw tools/local_server/serve.py           # background (no window); logs to tools/local_server/server.log
  python tools/local_server/serve.py --no-jobs  # API + app only, no scheduled jobs
"""
import argparse
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
PORT = int(os.getenv("LOCAL_PORT", "5050"))
LOG = ROOT / "tools" / "local_server" / "server.log"


def _load_env():
    from dotenv import dotenv_values, load_dotenv
    load_dotenv(ROOT / ".env")
    prod = dotenv_values(ROOT / ".env.production.local") if (ROOT / ".env.production.local").exists() else {}
    for key in ("POSTGRES_URL", "DATABASE_URL"):
        val = (prod.get(key) or "").strip()
        if val.startswith("postgres") and not os.getenv(key):
            os.environ[key] = val
    os.environ.setdefault("APP_URL", f"http://localhost:{PORT}")


# (name, path, when) — "when" is a function of the local (IST) datetime returning True at its minute.
def _at(*hm):
    return lambda now: (now.hour, now.minute) in hm


JOBS = [
    ("leetcode problem email", "/api/cron", lambda now: now.minute % 5 == 0),
    ("morning digest", "/api/digest", _at((8, 0))),
    ("job scan", "/api/jobs/scan", _at((7, 0), (11, 30), (15, 30), (19, 30))),
    ("job follow-ups", "/api/jobs/followups", _at((9, 0))),
    ("study reminder", "/api/syllabus/remind", lambda now: now.weekday() in (2, 6) and (now.hour, now.minute) == (19, 0)),
    ("weekly report", "/api/weekly/cron", lambda now: now.weekday() == 6 and (now.hour, now.minute) == (19, 30)),
]


def scheduler(app, stop):
    client = app.test_client()
    last = None
    while not stop.is_set():
        now = datetime.now().replace(second=0, microsecond=0)
        if now != last:
            last = now
            for name, path, due in JOBS:
                if due(now):
                    threading.Thread(target=_run_job, args=(client, name, path), daemon=True).start()
        stop.wait(max(1.0, (now + timedelta(minutes=1) - datetime.now()).total_seconds()))


def _run_job(client, name, path):
    t = time.time()
    try:
        res = client.post(path)
        body = (res.get_data(as_text=True) or "")[:200].replace("\n", " ")
        logging.info("job %-22s %s %s in %.1fs: %s", name, path, res.status_code, time.time() - t, body)
    except Exception as e:
        logging.exception("job %s failed: %s", name, e)


def add_frontend(app):
    """Serve the built React app (dist/) for every non-API path."""
    from flask import send_from_directory
    dist = ROOT / "dist"

    def frontend(path=""):
        target = dist / path
        if path and target.is_file():
            return send_from_directory(dist, path)
        return send_from_directory(dist, "index.html")

    app.add_url_rule("/", "local_frontend_root", frontend)
    app.add_url_rule("/<path:path>", "local_frontend", frontend)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-jobs", action="store_true")
    args = ap.parse_args()
    handlers = [logging.FileHandler(LOG, encoding="utf-8")]
    if sys.stdout and not sys.executable.lower().endswith("pythonw.exe"):
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", handlers=handlers)

    _load_env()
    from api.app import app
    if (ROOT / "dist" / "index.html").exists():
        add_frontend(app)
    else:
        logging.warning("dist/ not built — run `npx vite build` to serve the app UI; the API still works")

    stop = threading.Event()
    if not args.no_jobs:
        threading.Thread(target=scheduler, args=(app, stop), daemon=True).start()
    db = "Neon Postgres" if (os.getenv("POSTGRES_URL") or "").startswith("postgres") else "local SQLite"
    logging.info("Daily running on http://localhost:%s (data: %s, scheduled jobs: %s)", PORT, db, "off" if args.no_jobs else "on")
    try:
        app.run(host="127.0.0.1", port=PORT, threaded=True, use_reloader=False)
    finally:
        stop.set()


if __name__ == "__main__":
    main()
