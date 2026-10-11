"""
SYSTEM DESIGN CONCEPT: Repository Pattern
The Repository Pattern mediates between the domain and data mapping layers.
Instead of writing SQL queries all over our application, we encapsulate the DB access
inside a repository class. If we change the database later, we only update the repository.
"""
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from api.core.config import to_ist
from api.domain.models import NotificationLog, Settings, WatchSeries


def normalize_title(title: str) -> str:
    """'Two Sum (Fallback)' / 'two-sum' / 'Two  Sum' -> 'twosum'. Used for robust de-duplication."""
    title = re.sub(r"\(.*?\)", "", (title or "").lower())
    return re.sub(r"[^a-z0-9]", "", title)


# Legacy fixed ladder (days). Only used to seed the memory model for rows reviewed before FSRS-lite.
REVIEW_INTERVALS = [1, 3, 7, 21, 60]

# ---------------- FSRS-lite memory model ----------------
# Stability S (days): the interval after which recall probability falls to 90%.
# Difficulty D (1..10): how hard the problem is for *you*; it scales how fast S grows.
GRADES = ("again", "hard", "good", "easy")
LEGACY_RESULTS = {"easy": "good", "hard": "again"}  # old two-button API: {result: easy|hard}
INITIAL_STABILITY = {"Easy": 3.0, "Medium": 1.5, "Hard": 0.8}
INITIAL_DIFFICULTY = {"Easy": 4.0, "Medium": 5.5, "Hard": 7.0}
S_MIN, S_MAX = 0.3, 365.0
D_MIN, D_MAX = 1.0, 10.0
GRADUATE_AFTER = 180.0  # stability (days) beyond which a problem retires from reviews
FUZZ = 0.08             # +-8% deterministic jitter so same-day solves don't stay clumped
LEVEL_WINDOW = 0.10     # load levelling searches [0.9 I, 1.1 I]
_GROWTH = math.exp(1.05)  # tuned so an on-time 'good' at D=5, S=1.5 multiplies S by ~2.5
_HARD_FACTOR = 0.4        # 'hard' gets 40% of the growth 'good' would
_EASY_BONUS = 1.3


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def recall_probability(stability, elapsed_days):
    """R = (1 + t / (9 S))^-1  -> 0.9 exactly when t == S."""
    if not stability:
        return 1.0
    return (1.0 + max(0.0, elapsed_days) / (9.0 * stability)) ** -1


def next_memory_state(stability, difficulty, elapsed_days, grade):
    """Pure FSRS-like update. Returns (new_stability, new_difficulty, recall_before)."""
    s = _clamp(stability or INITIAL_STABILITY["Medium"], S_MIN, S_MAX)
    d = _clamp(difficulty or INITIAL_DIFFICULTY["Medium"], D_MIN, D_MAX)
    r = recall_probability(s, elapsed_days)
    if grade == "again":
        new_s, new_d = max(S_MIN, min(s, 0.4 * s ** 0.6)), d + 1.0
    else:
        growth = _GROWTH * (11.0 - d) * s ** -0.2 * (math.exp(0.9 * (1.0 - r)) - 1.0)
        if grade == "hard":
            new_s, new_d = s * (1.0 + _HARD_FACTOR * growth), d + 0.5
        elif grade == "good":
            new_s, new_d = s * (1.0 + growth), d
        else:  # easy
            new_s, new_d = s * (1.0 + growth) * _EASY_BONUS, d - 0.5
    return _clamp(new_s, S_MIN, S_MAX), _clamp(new_d, D_MIN, D_MAX), r


def _fuzz(seed: int) -> float:
    """Deterministic value in [-FUZZ, +FUZZ] derived from the row (no RNG -> reproducible schedules)."""
    h = (seed * 2654435761) % (2 ** 32)
    return ((h % 10007) / 10006.0 * 2.0 - 1.0) * FUZZ


def pick_interval_days(interval, load_by_offset, seed=0):
    """Choose a whole number of days within [0.9 I, 1.1 I] (at least 1) with the fewest reviews
    already scheduled; ties go to the day closest to the fuzzed target I * (1 +- 8%).
    `load_by_offset` maps day offset -> number of reviews already due that day."""
    target = max(1.0, interval * (1.0 + _fuzz(seed)))
    lo = max(1, int(round(interval * (1.0 - LEVEL_WINDOW))))
    hi = max(lo, int(round(interval * (1.0 + LEVEL_WINDOW))))
    return min(range(lo, hi + 1), key=lambda d: (load_by_offset.get(d, 0), abs(d - target), d))

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
            if is_completed:
                NotificationRepository._init_memory(log)
            else:
                log.review_stage = log.next_review_at = log.stability = None
                log.difficulty_fsrs = log.last_review_at = log.lapses = None

    @staticmethod
    def _init_memory(log):
        """Fresh solve: initial stability/difficulty come from the LeetCode difficulty."""
        diff = log.difficulty if log.difficulty in INITIAL_STABILITY else "Medium"
        log.review_stage = 0
        log.lapses = 0
        log.stability = INITIAL_STABILITY[diff]
        log.difficulty_fsrs = INITIAL_DIFFICULTY[diff]
        log.last_review_at = None  # elapsed time counts from completed_at until the first review
        log.next_review_at = log.completed_at + timedelta(days=log.stability) if log.completed_at else None

    @staticmethod
    def _ensure_memory(log) -> bool:
        """Lazily backfill rows completed under the old fixed ladder. Returns True if it changed anything."""
        if log.stability is not None or not log.is_completed or log.task_type != "leetcode":
            return False
        diff = log.difficulty if log.difficulty in INITIAL_STABILITY else "Medium"
        stage = log.review_stage or 0
        log.lapses = log.lapses or 0
        log.difficulty_fsrs = log.difficulty_fsrs or INITIAL_DIFFICULTY[diff]
        if log.review_stage is not None and log.next_review_at is None and stage >= len(REVIEW_INTERVALS):
            log.stability = GRADUATE_AFTER + 1  # graduated under the old ladder
        elif stage == 0:
            log.stability = INITIAL_STABILITY[diff]
        else:
            log.stability = float(REVIEW_INTERVALS[min(stage, len(REVIEW_INTERVALS) - 1)])
        if log.review_stage is None:
            log.review_stage = 0
        if stage > 0 and log.next_review_at:
            log.last_review_at = log.next_review_at - timedelta(days=log.stability)
        if log.next_review_at is None and log.stability <= GRADUATE_AFTER and log.completed_at:
            log.next_review_at = log.completed_at + timedelta(days=log.stability)
        return True

    @staticmethod
    def recall_now(log, now=None):
        """Current estimated recall probability (0..1) for a completed problem."""
        now = now or _utcnow()
        since = log.last_review_at or log.completed_at or log.timestamp or now
        return recall_probability(log.stability, (now - since).total_seconds() / 86400.0)

    def _scheduled_query(self):
        return self.db.query(NotificationLog).filter(
            NotificationLog.task_type == "leetcode",
            NotificationLog.status == "success",
            NotificationLog.is_completed == True,  # noqa: E712
            NotificationLog.next_review_at != None,  # noqa: E711
        )

    def get_due_reviews(self, limit: int = 20, now=None):
        """Due problems, weakest memory (lowest current recall) first."""
        now = now or _utcnow()
        due = self._scheduled_query().filter(NotificationLog.next_review_at <= now).all()
        if sum(self._ensure_memory(l) for l in due):
            self.db.commit()
        due.sort(key=lambda l: (self.recall_now(l, now), l.next_review_at, l.id))
        return due[:limit] if limit else due

    def count_due_reviews(self, now=None) -> int:
        return self._scheduled_query().filter(NotificationLog.next_review_at <= (now or _utcnow())).count()

    def review_load(self, start, end, exclude_id=None) -> Counter:
        """Number of scheduled reviews per IST calendar date for next_review_at in [start, end)."""
        q = self._scheduled_query().filter(NotificationLog.next_review_at >= start, NotificationLog.next_review_at < end)
        if exclude_id is not None:
            q = q.filter(NotificationLog.id != exclude_id)
        return Counter(to_ist(l.next_review_at).date() for l in q.all())

    def upcoming_reviews(self, days: int = 7, now=None) -> list:
        """[{date, count}] of reviews that become due on each of the next `days` IST days (today first),
        not counting anything already due."""
        now = now or _utcnow()
        today = to_ist(now).date()
        load = self.review_load(now + timedelta(microseconds=1), now + timedelta(days=days + 1))
        return [{"date": (today + timedelta(days=i)).isoformat(), "count": load.get(today + timedelta(days=i), 0)}
                for i in range(days)]

    def record_review(self, log, grade: str, now=None):
        """grade: again | hard | good | easy. Updates the memory model and schedules the next review."""
        if grade not in GRADES:
            raise ValueError(f"grade must be one of {', '.join(GRADES)}")
        now = now or _utcnow()
        self._ensure_memory(log)
        since = log.last_review_at or log.completed_at or now
        elapsed = max(0.0, (now - since).total_seconds() / 86400.0)
        s, d, r = next_memory_state(log.stability, log.difficulty_fsrs, elapsed, grade)
        log.stability, log.difficulty_fsrs = s, d
        log.lapses = (log.lapses or 0) + (grade == "again")
        log.review_stage = (log.review_stage or 0) + 1
        log.last_review_at = now
        if s > GRADUATE_AFTER:
            log.next_review_at = None
        else:
            today = to_ist(now).date()
            load = self.review_load(now, now + timedelta(days=s * (1 + LEVEL_WINDOW) + 2), exclude_id=log.id)
            by_offset = {(day - today).days: n for day, n in load.items()}
            days = pick_interval_days(s, by_offset, seed=(log.id or 0) * 31 + log.review_stage)
            log.next_review_at = now + timedelta(days=days)
        self.db.commit()
        self.db.refresh(log)
        log.recall_before = r  # transient, for the API response
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
                    if log.next_review_at and log.stability:
                        log.next_review_at = log.completed_at + timedelta(days=log.stability)
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
