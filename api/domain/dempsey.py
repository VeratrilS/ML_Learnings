"""
Dempsey Roll: Momentum & Fever Mode engine, Hajime no Ippo themed.
When the user hits all 4 daily core habits (Solve, Focus Sprint, Flashcard Review, Agent Mission),
the Dempsey Roll is unleashed, activating a 24-hour 2x XP Fever Mode and combo damage to the Gym Boss.
"""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Boolean, Column, DateTime, Integer, String

from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine

dempsey_bp = Blueprint("dempsey", __name__, url_prefix="/api/dempsey")


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DempseyFever(Base):
    __tablename__ = "dempsey_fever"
    id = Column(Integer, primary_key=True, index=True)
    date_key = Column(String(20), nullable=False, unique=True)  # YYYY-MM-DD
    is_unleashed = Column(Boolean, default=False)
    combo_count = Column(Integer, default=0)
    unleashed_at = Column(DateTime, nullable=True)


@dempsey_bp.record_once
def _ensure_tables(state):
    Base.metadata.create_all(bind=engine, tables=[DempseyFever.__table__])


def _today_bounds_utc():
    start_ist = now_ist().replace(hour=0, minute=0, second=0, microsecond=0)
    start = start_ist.astimezone(timezone.utc).replace(tzinfo=None)
    return start


@dempsey_bp.route("/status", methods=["GET"])
def get_status():
    date_key = now_ist().strftime("%Y-%m-%d")
    today_utc = _today_bounds_utc()

    db = SessionLocal()
    try:
        # Check four habits today:
        # 1. Solved any DSA question
        from api.domain.models import NotificationLog
        solves_today = db.query(NotificationLog).filter(
            NotificationLog.is_completed == True,  # noqa: E712
            NotificationLog.completed_at >= today_utc,
        ).count()

        # 2. Focus speedrun
        from api.domain.speedrun import SpeedrunSession
        sprints_today = db.query(SpeedrunSession).filter(
            SpeedrunSession.created_at >= today_utc,
        ).count()

        # 3. Flashcard / Drillmaster review
        from api.domain.drillmaster import SM2Card
        drills_today = db.query(SM2Card).filter(
            SM2Card.last_reviewed_at >= today_utc,
        ).count()

        # 4. Agent mission
        from api.domain.agents import AgentMission
        agents_today = db.query(AgentMission).filter(
            AgentMission.created_at >= today_utc,
        ).count()

        habits = [
            {"id": "solve", "label": "DSA Problem Solved", "done": solves_today > 0, "icon": "Code2"},
            {"id": "sprint", "label": "Focus Speedrun Sprint", "done": sprints_today > 0, "icon": "Flame"},
            {"id": "drill", "label": "SM-2 Active Recall", "done": drills_today > 0, "icon": "RotateCcw"},
            {"id": "agent", "label": "Agent Swarm Mission", "done": agents_today > 0, "icon": "Bot"},
        ]
        completed_count = sum(1 for h in habits if h["done"])
        ready_to_unleash = completed_count == 4

        record = db.query(DempseyFever).filter(DempseyFever.date_key == date_key).first()
        is_active = bool(record and record.is_unleashed)

        # Total fever days
        total_fevers = db.query(DempseyFever).filter(DempseyFever.is_unleashed == True).count()  # noqa: E712

        return jsonify({
            "status": "success",
            "data": {
                "date": date_key,
                "habits": habits,
                "completed_count": completed_count,
                "total_habits": 4,
                "ready_to_unleash": ready_to_unleash,
                "fever_active": is_active,
                "total_fever_days": total_fevers,
                "xp_multiplier": 2.0 if is_active else 1.0,
            },
        })
    finally:
        db.close()


@dempsey_bp.route("/unleash", methods=["POST"])
def unleash():
    date_key = now_ist().strftime("%Y-%m-%d")
    db = SessionLocal()
    try:
        record = db.query(DempseyFever).filter(DempseyFever.date_key == date_key).first()
        if not record:
            record = DempseyFever(
                date_key=date_key,
                is_unleashed=True,
                combo_count=1,
                unleashed_at=_utcnow(),
            )
            db.add(record)
        else:
            record.is_unleashed = True
            record.unleashed_at = _utcnow()
        db.commit()

        return jsonify({
            "status": "success",
            "data": {
                "unleashed": True,
                "xp_multiplier": 2.0,
                "message": "DEMPSEY ROLL UNLEASHED! 2x XP Fever Mode activated for today!",
            },
        })
    finally:
        db.close()
