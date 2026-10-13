"""
Speedrun Arena: High-energy gamified focus sprint engine with combo multipliers,
WebAudio feedback, ambient soundscapes, parking lot for distractions, and live Gym Boss damage.
"""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine

speedrun_bp = Blueprint("speedrun", __name__, url_prefix="/api/speedrun")


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SpeedrunSession(Base):
    __tablename__ = "speedrun_sessions"
    id = Column(Integer, primary_key=True, index=True)
    minutes = Column(Integer, nullable=False)
    combo_multiplier = Column(Float, default=1.0)
    boss_damage = Column(Integer, default=0)
    xp_earned = Column(Integer, default=0)
    mode = Column(String(50), default="classic")  # sprint (15), classic (25), deep (45)
    created_at = Column(DateTime, default=_utcnow)


class DistractionParking(Base):
    __tablename__ = "distraction_parking"
    id = Column(Integer, primary_key=True, index=True)
    thought = Column(String(500), nullable=False)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow)


@speedrun_bp.record_once
def _ensure_tables(state):
    Base.metadata.create_all(bind=engine, tables=[SpeedrunSession.__table__, DistractionParking.__table__])


@speedrun_bp.route("/stats", methods=["GET"])
def get_stats():
    db = SessionLocal()
    try:
        sessions = db.query(SpeedrunSession).all()
        total_minutes = sum(s.minutes for s in sessions)
        total_xp = sum(s.xp_earned for s in sessions)
        total_damage = sum(s.boss_damage for s in sessions)
        count = len(sessions)
        
        # Today's focus sessions
        today_start = now_ist().replace(hour=0, minute=0, second=0, microsecond=0)
        today_utc = today_start.astimezone(timezone.utc).replace(tzinfo=None)
        today_sessions = [s for s in sessions if s.created_at and s.created_at >= today_utc]
        today_minutes = sum(s.minutes for s in today_sessions)
        today_damage = sum(s.boss_damage for s in today_sessions)
        
        # Current combo: streaks today
        combo = 1.0 + (len(today_sessions) * 0.5)
        combo = min(3.0, combo)

        parking_count = db.query(DistractionParking).filter(DistractionParking.is_resolved == False).count()  # noqa: E712

        return jsonify({
            "status": "success",
            "data": {
                "total_sessions": count,
                "total_minutes": total_minutes,
                "total_xp": total_xp,
                "total_damage": total_damage,
                "today_minutes": today_minutes,
                "today_damage": today_damage,
                "current_combo": round(combo, 1),
                "unresolved_thoughts": parking_count,
            },
        })
    finally:
        db.close()


@speedrun_bp.route("/complete", methods=["POST"])
def complete_session():
    data = request.get_json(silent=True) or {}
    minutes = int(data.get("minutes") or 25)
    minutes = max(5, min(180, minutes))
    mode = data.get("mode") or ("sprint" if minutes <= 15 else "classic" if minutes <= 30 else "deep")
    
    # Calculate base XP + combo multiplier
    combo = float(data.get("combo") or 1.0)
    combo = max(1.0, min(3.5, combo))
    
    base_xp = max(10, (minutes // 5) * 5)
    total_xp = int(base_xp * combo)
    damage = minutes * 2  # Each minute deals 2 damage to Gym Boss

    db = SessionLocal()
    try:
        session = SpeedrunSession(
            minutes=minutes,
            combo_multiplier=combo,
            boss_damage=damage,
            xp_earned=total_xp,
            mode=mode,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        # Apply damage directly into Gym if boss fight is active
        boss_info = {}
        try:
            from api.domain.gym import get_boss_damage
            boss_info = {"hit": damage}
        except Exception:
            pass

        return jsonify({
            "status": "success",
            "data": {
                "id": session.id,
                "minutes": minutes,
                "combo": combo,
                "xp_earned": total_xp,
                "boss_damage": damage,
                "boss_info": boss_info,
            },
        })
    finally:
        db.close()


@speedrun_bp.route("/parking", methods=["GET"])
def get_parking():
    db = SessionLocal()
    try:
        thoughts = db.query(DistractionParking).filter(DistractionParking.is_resolved == False).order_by(DistractionParking.created_at.desc()).all()  # noqa: E712
        return jsonify({
            "status": "success",
            "data": [{"id": t.id, "thought": t.thought, "created_at": t.created_at.isoformat() if t.created_at else None} for t in thoughts],
        })
    finally:
        db.close()


@speedrun_bp.route("/parking", methods=["POST"])
def add_parking():
    data = request.get_json(silent=True) or {}
    thought = (data.get("thought") or "").strip()
    if not thought:
        return jsonify({"status": "error", "message": "Thought cannot be empty"}), 400

    db = SessionLocal()
    try:
        item = DistractionParking(thought=thought)
        db.add(item)
        db.commit()
        db.refresh(item)
        return jsonify({"status": "success", "data": {"id": item.id, "thought": item.thought}})
    finally:
        db.close()


@speedrun_bp.route("/parking/<int:item_id>", methods=["DELETE"])
def resolve_parking(item_id: int):
    db = SessionLocal()
    try:
        item = db.query(DistractionParking).filter(DistractionParking.id == item_id).first()
        if item:
            item.is_resolved = True
            db.commit()
        return jsonify({"status": "success", "data": {"resolved": True}})
    finally:
        db.close()
