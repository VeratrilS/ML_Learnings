"""
Drillmaster: SuperMemo SM-2 Spaced Repetition Mastery Engine.
Implements the exact SM-2 algorithm for fundamental CS concepts, algorithms,
and active recall retention.
"""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine

drillmaster_bp = Blueprint("drillmaster", __name__, url_prefix="/api/drillmaster")


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SM2Card(Base):
    __tablename__ = "sm2_cards"
    id = Column(Integer, primary_key=True, index=True)
    front = Column(Text, nullable=False)
    back = Column(Text, nullable=False)
    category = Column(String(50), default="Algorithms")
    ease_factor = Column(Float, default=2.5)
    interval_days = Column(Integer, default=1)
    repetition_count = Column(Integer, default=0)
    next_review_at = Column(DateTime, default=_utcnow)
    last_reviewed_at = Column(DateTime, nullable=True)


@drillmaster_bp.record_once
def _ensure_tables(state):
    Base.metadata.create_all(bind=engine, tables=[SM2Card.__table__])
    _seed_cards()


DEFAULT_SEED_CARDS = [
    {
        "category": "Operating Systems",
        "front": "What is the difference between Paging and Segmentation in OS memory management?",
        "back": "Paging divides physical memory into fixed-sized blocks (Pages/Frames) managed by the OS (avoids external fragmentation). Segmentation divides memory into variable-sized logical units (Code, Stack, Heap) mirroring programmer view (can cause external fragmentation).",
    },
    {
        "category": "Networking",
        "front": "Explain the TCP 3-Way Handshake step-by-step.",
        "back": "1. Client sends SYN (seq = x).\n2. Server responds with SYN-ACK (seq = y, ack = x + 1).\n3. Client sends ACK (seq = x + 1, ack = y + 1) and connection state becomes ESTABLISHED.",
    },
    {
        "category": "Database Systems",
        "front": "What is the difference between Clustered and Non-Clustered Indexes in SQL databases?",
        "back": "A Clustered Index alters the physical storage order of rows in the table; there can only be ONE clustered index per table (typically Primary Key). A Non-Clustered Index is a separate B+ tree structure pointing to row locators/clustered keys; multiple can exist.",
    },
    {
        "category": "Algorithms",
        "front": "When should you use Floyd-Warshall vs Bellman-Ford vs Dijkstra?",
        "back": "- Dijkstra: Single-source shortest path, non-negative weights only, O((V + E) log V).\n- Bellman-Ford: Single-source, allows negative edge weights, detects negative cycles, O(V * E).\n- Floyd-Warshall: All-pairs shortest path, dynamic programming, O(V^3).",
    },
    {
        "category": "System Design",
        "front": "How does Consistent Hashing minimize data movement during node additions/removals?",
        "back": "Both servers and keys are hashed onto a circular 360-degree keyspace ring. A key is assigned to the next clockwise server. When a server node is added or removed, only keys residing between adjacent nodes (1/N of keys on average) are relocated, rather than all keys as in hash(k) % N.",
    },
    {
        "category": "Algorithms",
        "front": "State the invariant and transition for Kadane's Algorithm for Maximum Subarray.",
        "back": "Invariant: At step i, max_ending_here = max(nums[i], max_ending_here + nums[i]). If extending the previous subarray yields less than nums[i] alone, discard the prefix and restart at nums[i]. Overall max is tracked globally in O(N) time and O(1) space.",
    },
]


def _seed_cards():
    db = SessionLocal()
    try:
        if db.query(SM2Card).count() == 0:
            for c in DEFAULT_SEED_CARDS:
                card = SM2Card(
                    front=c["front"],
                    back=c["back"],
                    category=c["category"],
                    ease_factor=2.5,
                    interval_days=1,
                    repetition_count=0,
                    next_review_at=_utcnow(),
                )
                db.add(card)
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"Drillmaster card seed skipped: {e}")
    finally:
        db.close()


@drillmaster_bp.route("/deck", methods=["GET"])
def get_deck():
    db = SessionLocal()
    try:
        if db.query(SM2Card).count() == 0:
            _seed_cards()
        now_dt = _utcnow()
        all_cards = db.query(SM2Card).all()
        due_cards = [c for c in all_cards if c.next_review_at is None or c.next_review_at <= now_dt]
        
        cards_payload = []
        for c in due_cards:
            cards_payload.append({
                "id": c.id,
                "front": c.front,
                "back": c.back,
                "category": c.category,
                "ease_factor": round(c.ease_factor, 2),
                "interval_days": c.interval_days,
                "repetition_count": c.repetition_count,
            })

        total = len(all_cards)
        mastered = sum(1 for c in all_cards if c.interval_days >= 14)
        mastery_rate = round((mastered / total) * 100, 1) if total > 0 else 0.0

        return jsonify({
            "status": "success",
            "data": {
                "due_cards": cards_payload,
                "due_count": len(due_cards),
                "total_cards": total,
                "mastered_cards": mastered,
                "mastery_rate": mastery_rate,
            },
        })
    finally:
        db.close()


@drillmaster_bp.route("/review", methods=["POST"])
def review_card():
    data = request.get_json(silent=True) or {}
    card_id = data.get("card_id")
    # grade: 0 = Again, 3 = Hard, 4 = Good, 5 = Easy
    grade = int(data.get("grade") if data.get("grade") is not None else 4)
    grade = max(0, min(5, grade))

    db = SessionLocal()
    try:
        card = db.query(SM2Card).filter(SM2Card.id == card_id).first()
        if not card:
            return jsonify({"status": "error", "message": "Card not found"}), 404

        # SM-2 Algorithm computation
        ef = card.ease_factor or 2.5
        reps = card.repetition_count or 0
        interval = card.interval_days or 1

        if grade < 3:
            # Failed recall: reset repetitions and schedule for tomorrow
            reps = 0
            interval = 1
        else:
            # Successful recall
            if reps == 0:
                interval = 1
            elif reps == 1:
                interval = 6
            else:
                interval = int(interval * ef)

            reps += 1
            # Update Ease Factor: EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
            ef = ef + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
            ef = max(1.3, ef)

        now_dt = _utcnow()
        next_review = now_dt + timedelta(days=interval)

        card.ease_factor = ef
        card.repetition_count = reps
        card.interval_days = interval
        card.next_review_at = next_review
        card.last_reviewed_at = now_dt
        db.commit()

        # Compute XP awarded (5 XP per card reviewed)
        xp_awarded = 10 if grade == 5 else 6 if grade >= 3 else 2

        return jsonify({
            "status": "success",
            "data": {
                "card_id": card.id,
                "new_interval_days": interval,
                "new_ease_factor": round(ef, 2),
                "repetition_count": reps,
                "next_review_at": next_review.isoformat(),
                "xp_awarded": xp_awarded,
            },
        })
    finally:
        db.close()


@drillmaster_bp.route("/card", methods=["POST"])
def add_card():
    data = request.get_json(silent=True) or {}
    front = (data.get("front") or "").strip()
    back = (data.get("back") or "").strip()
    category = (data.get("category") or "Algorithms").strip()

    if not front or not back:
        return jsonify({"status": "error", "message": "Front and back are required"}), 400

    db = SessionLocal()
    try:
        card = SM2Card(
            front=front,
            back=back,
            category=category,
            ease_factor=2.5,
            interval_days=1,
            repetition_count=0,
            next_review_at=_utcnow(),
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        return jsonify({"status": "success", "data": {"id": card.id, "front": card.front}})
    finally:
        db.close()
