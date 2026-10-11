"""
Beta Lab: every new feature ships as 'beta' and only joins the main app once Sai approves it.
Stored server-side so approvals sync between phone and laptop.
"""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, DateTime, Integer, String

from api.core.db import Base, SessionLocal, engine

STATUSES = ("beta", "approved", "hidden")


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    id = Column(Integer, primary_key=True)
    key = Column(String(60), unique=True, nullable=False)
    status = Column(String(20), nullable=False, default="beta")
    updated_at = Column(DateTime, default=_utcnow)


features_bp = Blueprint("features", __name__, url_prefix="/api/features")


@features_bp.record_once
def _ensure_tables(state):
    Base.metadata.create_all(bind=engine, tables=[FeatureFlag.__table__])


@features_bp.route("", methods=["GET"])
def list_flags():
    db = SessionLocal()
    try:
        return jsonify({"status": "success", "data": {f.key: f.status for f in db.query(FeatureFlag).all()}})
    finally:
        db.close()


@features_bp.route("/<key>", methods=["PUT"])
def set_flag(key):
    status = (request.get_json(silent=True) or {}).get("status")
    if status not in STATUSES or not key or len(key) > 60:
        return jsonify({"status": "error", "message": f"status must be one of {', '.join(STATUSES)}"}), 400
    db = SessionLocal()
    try:
        flag = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
        if not flag:
            flag = FeatureFlag(key=key)
            db.add(flag)
        flag.status = status
        flag.updated_at = _utcnow()
        db.commit()
        return jsonify({"status": "success", "data": {"key": key, "status": status}})
    finally:
        db.close()
