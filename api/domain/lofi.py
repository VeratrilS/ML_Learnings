"""
Neural Lo-Fi Studio — Generative WebAudio Focus Soundscapes & Binaural Beats.
Zero-dependency, browser-synthesized audio environments (Binaural Alpha, Rain,
Mechanical ASMR, Cyberpunk Drone) that reward continuous deep study sessions.
"""
from datetime import datetime, timezone
import json

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, DateTime, Integer, String

from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine

lofi_bp = Blueprint("lofi", __name__, url_prefix="/api/lofi")


class LofiSession(Base):
    __tablename__ = "lofi_sessions"

    id = Column(Integer, primary_key=True)
    preset_id = Column(String(60), nullable=False)
    duration_min = Column(Integer, nullable=False, default=0)
    xp_earned = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: now_ist())

    def to_dict(self):
        return {
            "id": self.id,
            "preset_id": self.preset_id,
            "duration_min": self.duration_min,
            "xp_earned": self.xp_earned,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


Base.metadata.create_all(bind=engine, tables=[LofiSession.__table__], checkfirst=True)


PRESETS = [
    {
        "id": "binaural_alpha",
        "title": "Binaural Alpha Wave (14Hz)",
        "category": "Brainwave Entrainment",
        "color": "emerald",
        "icon": "Brain",
        "desc": "Left ear 200Hz, Right ear 214Hz. Stimulates alertness, memory consolidation, and deep algorithmic problem solving.",
        "params": {"type": "binaural", "baseFreq": 200, "beatFreq": 14}
    },
    {
        "id": "cyberpunk_drone",
        "title": "Cyberpunk Neon Drone",
        "category": "Atmospheric Synth",
        "color": "indigo",
        "icon": "Radio",
        "desc": "Low 110Hz sub-oscillator with modulated filter resonance for immersive terminal flow.",
        "params": {"type": "drone", "baseFreq": 110, "filterFreq": 450}
    },
    {
        "id": "campus_rain",
        "title": "Rain on Campus Window",
        "category": "Organic Noise",
        "color": "sky",
        "icon": "CloudRain",
        "desc": "Continuous pink noise generator with random raindrop impulses to mask library distractions.",
        "params": {"type": "noise", "noiseColor": "pink"}
    },
    {
        "id": "mechanical_asmr",
        "title": "Cherry MX Mechanical Ticks",
        "category": "Rhythmic ASMR",
        "color": "amber",
        "icon": "Keyboard",
        "desc": "Subtle periodic keycap click impulses simulating late-night competitive code sprints.",
        "params": {"type": "asmr", "bpm": 72}
    },
    {
        "id": "brown_noise",
        "title": "Deep Velvet Brown Noise",
        "category": "Acoustic Masking",
        "color": "rose",
        "icon": "Sparkles",
        "desc": "Deep, rumbling low-frequency brown noise that calms racing ADHD thoughts and anxiety.",
        "params": {"type": "noise", "noiseColor": "brown"}
    }
]


@lofi_bp.route("/presets", methods=["GET"])
def list_presets():
    return jsonify({"presets": PRESETS})


@lofi_bp.route("/session/log", methods=["POST"])
def log_session():
    data = request.get_json() or {}
    preset_id = data.get("preset_id", "binaural_alpha")
    duration_min = max(1, min(240, int(data.get("duration_min") or 15)))

    # 2 XP per 5 minutes of listening
    xp = (duration_min // 5) * 2

    db = SessionLocal()
    session = LofiSession(preset_id=preset_id, duration_min=duration_min, xp_earned=xp)
    db.add(session)
    db.commit()
    db.refresh(session)
    result = session.to_dict()
    db.close()

    return jsonify({"session": result, "xp_awarded": xp}), 201


@lofi_bp.route("/stats", methods=["GET"])
def get_stats():
    db = SessionLocal()
    sessions = db.query(LofiSession).all()
    total_minutes = sum(s.duration_min for s in sessions)
    total_xp = sum(s.xp_earned for s in sessions)
    db.close()

    return jsonify({
        "stats": {
            "total_minutes": total_minutes,
            "total_hours": round(total_minutes / 60, 1),
            "sessions_count": len(sessions),
            "total_xp": total_xp
        }
    })
