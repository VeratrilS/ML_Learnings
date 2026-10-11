"""
Central configuration: loads .env once and exposes shared constants.
"""
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

# All "day" boundaries (streaks, daily episode, quiet hours) use India Standard Time.
IST = timezone(timedelta(hours=5, minutes=30))

RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL", "sairaghava1318@gmail.com")

APP_URL = os.getenv("APP_URL", "https://productivity-automations.vercel.app")


def now_ist() -> datetime:
    return datetime.now(IST)


def to_ist(dt: datetime) -> datetime:
    """DB timestamps are stored as naive UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)
