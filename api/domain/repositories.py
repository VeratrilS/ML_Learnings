"""
SYSTEM DESIGN CONCEPT: Repository Pattern
The Repository Pattern mediates between the domain and data mapping layers.
Instead of writing SQL queries all over our application, we encapsulate the DB access
inside a repository class. If we change the database later, we only update the repository.
"""
import re
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from api.domain.models import NotificationLog, Settings, WatchSeries


def normalize_title(title: str) -> str:
    """'Two Sum (Fallback)' / 'two-sum' / 'Two  Sum' -> 'twosum'. Used for robust de-duplication."""
    title = re.sub(r"\(.*?\)", "", (title or "").lower())
    return re.sub(r"[^a-z0-9]", "", title)


# Days after solving (then after each review) before a problem comes back for revision
REVIEW_INTERVALS = [1, 3, 7, 21, 60]

# 'sending' = claimed by an in-flight run, 'hidden' = deleted by the user. Both must still block repeats.
SENT_STATUSES = ("success", "sending", "hidden")


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class NotificationRepository:
    def __init__(self, db_session: Session):
        # DEPENDENCY INJECTION: We inject the DB session into the repository.
        self.db = db_session

    # ---------- Logs ----------
    def log_notification(self, task_type: str, title: str, content: str, status: str = "success",
                         slug: str = None, difficulty: str = None, link: str = None, topic: str = None):
        """Creates a new log entry in the database."""
        new_log = NotificationLog(
            task_type=task_type,
            title=title[:200],
            content=content,
            status=status,
            slug=slug,
            difficulty=difficulty,
            link=link,
            topic=(topic or "")[:200] or None,
        )
        self.db.add(new_log)
        self.db.commit()
        self.db.refresh(new_log)
        return new_log

    def get_recent_logs(self, limit: int = 10):
        """Fetches recent logs."""
        return self.db.query(NotificationLog).order_by(NotificationLog.timestamp.desc()).limit(limit).all()

    def get_logs(self, task_type: str):
        return self.db.query(NotificationLog).filter(
            NotificationLog.task_type == task_type,
            NotificationLog.status == "success",
        ).order_by(NotificationLog.timestamp.desc()).all()

    def get_all_leetcode_logs(self):
        return self.get_logs("leetcode")

    def get_log(self, log_id: int):
        return self.db.query(NotificationLog).filter(NotificationLog.id == log_id).first()

    def mark_task_completed(self, log_id: int, is_completed: bool):
        log = self.get_log(log_id)
        if log:
            self._set_completed(log, is_completed)
            self.db.commit()
            self.db.refresh(log)
        return log

    @staticmethod
    def _set_completed(log, is_completed: bool):
        log.is_completed = is_completed
        log.completed_at = _utcnow() if is_completed else None
        if log.task_type == "leetcode":
            log.review_stage = 0 if is_completed else None
            log.next_review_at = (log.completed_at + timedelta(days=REVIEW_INTERVALS[0])) if is_completed else None

    def get_due_reviews(self, limit: int = 20):
        return self.db.query(NotificationLog).filter(
            NotificationLog.task_type == "leetcode",
            NotificationLog.status == "success",
            NotificationLog.is_completed == True,  # noqa: E712
            NotificationLog.next_review_at != None,  # noqa: E711
            NotificationLog.next_review_at <= _utcnow(),
        ).order_by(NotificationLog.next_review_at.asc()).limit(limit).all()

    def record_review(self, log, result: str):
        """result: 'easy' advances the schedule, 'hard' restarts it at 1 day."""
        stage = 0 if result == "hard" else min((log.review_stage or 0) + 1, len(REVIEW_INTERVALS))
        log.review_stage = stage
        log.next_review_at = None if stage >= len(REVIEW_INTERVALS) else _utcnow() + timedelta(days=REVIEW_INTERVALS[stage])
        self.db.commit()
        self.db.refresh(log)
        return log

    def delete_log(self, log_id: int):
        log = self.get_log(log_id)
        if log:
            self.db.delete(log)
            self.db.commit()
        return log

    def hide_log(self, log_id: int):
        """Soft delete: disappears from lists but still counts as sent, so it is never suggested again."""
        log = self.get_log(log_id)
        if log:
            log.status = "hidden"
            self.db.commit()
        return log

    def update_log(self, log, **fields):
        for k, v in fields.items():
            setattr(log, k, v)
        self.db.commit()
        self.db.refresh(log)
        return log

    def get_uncompleted_leetcode_tasks(self):
        return self.db.query(NotificationLog).filter(
            NotificationLog.task_type == "leetcode",
            NotificationLog.status == "success",
            NotificationLog.is_completed == False,  # noqa: E712
        ).order_by(NotificationLog.timestamp.asc()).all()

    def get_all_sent_titles(self):
        """Returns a set of ALL previously sent leetcode problem titles (completed + uncompleted)."""
        logs = self.db.query(NotificationLog.title).filter(NotificationLog.task_type == "leetcode").all()
        return set(row.title for row in logs)

    def get_sent_keys(self, task_type: str):
        """Slugs + normalized titles of everything successfully sent. Anything in this set is never sent again."""
        rows = self.db.query(NotificationLog.slug, NotificationLog.title).filter(
            NotificationLog.task_type == task_type, NotificationLog.status.in_(SENT_STATUSES)).all()
        keys = set()
        for slug, title in rows:
            if slug:
                keys.add(slug)
                keys.add(normalize_title(slug))
            keys.add(normalize_title(title))
        return keys

    def get_latest_successful_leetcode_log(self):
        """Returns the most recent SUCCESSFUL leetcode log, ignoring failed sends.
        Used by the cron interval logic so a failed send doesn't reset the timer.
        In-flight ('sending') runs count too, so two overlapping runs can't both fire."""
        return self.db.query(NotificationLog).filter(
            NotificationLog.task_type == "leetcode",
            NotificationLog.status.in_(("success", "sending"))
        ).order_by(NotificationLog.timestamp.desc()).first()

    def mark_completed_by_keys(self, task_type: str, keys: set, when: dict = None) -> list:
        """Marks pending logs whose slug or normalized title is in `keys` as completed.
        `when` optionally maps key -> completion datetime (naive UTC)."""
        if not keys:
            return []
        updated = []
        pending = self.db.query(NotificationLog).filter(
            NotificationLog.task_type == task_type,
            NotificationLog.is_completed == False,  # noqa: E712
        ).all()
        for log in pending:
            match = next((k for k in (log.slug, normalize_title(log.title)) if k and k in keys), None)
            if match:
                self._set_completed(log, True)
                if when and when.get(match):
                    # Never earlier than when the problem was sent (it may have been solved before)
                    log.completed_at = max(when[match], log.timestamp or when[match])
                    if log.next_review_at:
                        log.next_review_at = log.completed_at + timedelta(days=REVIEW_INTERVALS[0])
                updated.append(log)
        if updated:
            self.db.commit()
        return updated

    def get_completed_logs(self):
        return self.db.query(NotificationLog).filter(
            NotificationLog.is_completed == True,  # noqa: E712
            NotificationLog.status == "success",
            NotificationLog.task_type.in_(["leetcode", "codeforces", "watch"]),
        ).all()

    # ---------- Settings ----------
    def get_setting(self, key: str, default_value: str = None):
        setting = self.db.query(Settings).filter(Settings.key == key).first()
        return setting.value if setting else default_value

    def set_setting(self, key: str, value: str):
        setting = self.db.query(Settings).filter(Settings.key == key).first()
        if setting:
            setting.value = value
        else:
            setting = Settings(key=key, value=value)
            self.db.add(setting)
        self.db.commit()
        return setting

    # ---------- Watch series ----------
    def get_series(self):
        return self.db.query(WatchSeries).order_by(WatchSeries.is_active.desc(), WatchSeries.id.asc()).all()

    def get_active_series(self):
        return self.db.query(WatchSeries).filter(WatchSeries.is_active == True).first()  # noqa: E712

    def get_series_by_id(self, series_id: int):
        return self.db.query(WatchSeries).filter(WatchSeries.id == series_id).first()

    def save(self, obj):
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, obj):
        self.db.delete(obj)
        self.db.commit()
