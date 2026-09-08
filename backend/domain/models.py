"""
OOP CONCEPT: Encapsulation & Inheritance
Models define the structure of our data. They map Python objects to Database rows.
We inherit from the SQLAlchemy `Base` class.
"""
from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from backend.core.db import Base

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    # Encapsulation: These attributes define the internal state of a NotificationLog.
    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(String(50), nullable=False) # e.g., 'incident' or 'leetcode'
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    status = Column(String(20), default="success") # 'success' or 'failed'
    timestamp = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        """String representation of the object (Magic Method)"""
        return f"<NotificationLog(type={self.task_type}, title={self.title}, status={self.status})>"
