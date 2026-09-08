"""
SYSTEM DESIGN CONCEPT: Repository Pattern
The Repository Pattern mediates between the domain and data mapping layers.
Instead of writing SQL queries all over our application, we encapsulate the DB access 
inside a repository class. If we change the database later, we only update the repository.
"""
from sqlalchemy.orm import Session
from backend.domain.models import NotificationLog

class NotificationRepository:
    def __init__(self, db_session: Session):
        # DEPENDENCY INJECTION: We inject the DB session into the repository.
        self.db = db_session

    def log_notification(self, task_type: str, title: str, content: str, status: str = "success"):
        """Creates a new log entry in the database."""
        new_log = NotificationLog(
            task_type=task_type,
            title=title,
            content=content,
            status=status
        )
        self.db.add(new_log)
        self.db.commit()
        self.db.refresh(new_log)
        return new_log

    def get_recent_logs(self, limit: int = 10):
        """Fetches recent logs."""
        return self.db.query(NotificationLog).order_by(NotificationLog.timestamp.desc()).limit(limit).all()
