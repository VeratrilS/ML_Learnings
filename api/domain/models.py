"""
OOP CONCEPT: Encapsulation & Inheritance
Models define the structure of our data. They map Python objects to Database rows.
We inherit from the SQLAlchemy `Base` class.
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from datetime import datetime, timezone
from api.core.db import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    # Encapsulation: These attributes define the internal state of a NotificationLog.
    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(String(50), nullable=False)  # 'incident' | 'leetcode' | 'codeforces' | 'watch'
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)  # JSON payload (question/approach/code) for leetcode
    status = Column(String(20), default="success")  # 'success' or 'failed'
    is_completed = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=_utcnow)
    # Stable identity used for de-duplication (leetcode slug, codeforces "1850/C", ...)
    slug = Column(String(200), nullable=True, index=True)
    difficulty = Column(String(20), nullable=True)
    link = Column(String(500), nullable=True)
    topic = Column(String(200), nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        """String representation of the object (Magic Method)"""
        return f"<NotificationLog(type={self.task_type}, title={self.title}, status={self.status})>"


class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(String(100), nullable=False)


class WatchSeries(Base):
    """A show watched one episode per day (e.g. Hajime no Ippo)."""
    __tablename__ = "watch_series"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    url_template = Column(String(500), nullable=False)  # must contain {ep}
    total_episodes = Column(Integer, nullable=False, default=1)
    next_episode = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)
