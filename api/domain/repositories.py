"""
SYSTEM DESIGN CONCEPT: Repository Pattern
The Repository Pattern mediates between the domain and data mapping layers.
Instead of writing SQL queries all over our application, we encapsulate the DB access 
inside a repository class. If we change the database later, we only update the repository.
"""
from sqlalchemy.orm import Session
from api.domain.models import NotificationLog

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

    def get_all_leetcode_logs(self):
        return self.db.query(NotificationLog).filter(NotificationLog.task_type == "leetcode").order_by(NotificationLog.timestamp.desc()).all()

    def mark_task_completed(self, log_id: int, is_completed: bool):
        from api.domain.models import NotificationLog
        log = self.db.query(NotificationLog).filter(NotificationLog.id == log_id).first()
        if log:
            log.is_completed = is_completed
            self.db.commit()
            self.db.refresh(log)
        return log

    def get_uncompleted_leetcode_tasks(self):
        return self.db.query(NotificationLog).filter(
            NotificationLog.task_type == "leetcode", 
            NotificationLog.is_completed == False
        ).all()

    def get_all_sent_titles(self):
        """Returns a set of ALL previously sent leetcode problem titles (completed + uncompleted).
        Used for programmatic dedup to prevent sending the same question twice."""
        logs = self.db.query(NotificationLog.title).filter(
            NotificationLog.task_type == "leetcode"
        ).all()
        return set(row.title for row in logs)

    def get_latest_successful_leetcode_log(self):
        """Returns the most recent SUCCESSFUL leetcode log, ignoring failed sends.
        Used by the cron interval logic so a failed send doesn't reset the timer."""
        return self.db.query(NotificationLog).filter(
            NotificationLog.task_type == "leetcode",
            NotificationLog.status == "success"
        ).order_by(NotificationLog.timestamp.desc()).first()

    def get_setting(self, key: str, default_value: str = None):
        from api.domain.models import Settings
        setting = self.db.query(Settings).filter(Settings.key == key).first()
        return setting.value if setting else default_value

    def set_setting(self, key: str, value: str):
        from api.domain.models import Settings
        setting = self.db.query(Settings).filter(Settings.key == key).first()
        if setting:
            setting.value = value
        else:
            setting = Settings(key=key, value=value)
            self.db.add(setting)
        self.db.commit()
        return setting
