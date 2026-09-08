"""
SYSTEM DESIGN CONCEPT: CLI Entrypoint
This script allows the Windows Task Scheduler to trigger our business logic 
without needing to make HTTP requests to the Flask app.
"""
import argparse
from api.core.db import init_db, SessionLocal
from api.domain.factory import NotifierFactory

def main():
    parser = argparse.ArgumentParser(description="Run background automations.")
    parser.add_argument("--type", choices=["incident", "leetcode"], required=True, help="Type of task to run")
    args = parser.parse_args()

    # Ensure DB is initialized
    init_db()

    db = SessionLocal()
    try:
        print(f"Starting {args.type} task...")
        notifier = NotifierFactory.get_notifier(args.type, db)
        result = notifier.run()
        print(f"Task completed: {result}")
    except Exception as e:
        print(f"Task failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
