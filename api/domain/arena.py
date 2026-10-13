"""
Code Duel Arena: 1v1 rapid-fire technical intuition duels against AI bot rivals.
Features 20-second rounds, live HP damage mechanics, sound integration, and combat XP.
"""
import random
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Boolean, Column, DateTime, Integer, String

from api.core.db import Base, SessionLocal, engine

arena_bp = Blueprint("arena", __name__, url_prefix="/api/arena")


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DuelMatch(Base):
    __tablename__ = "duel_matches"
    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String(50), nullable=False)
    player_score = Column(Integer, default=0)
    bot_score = Column(Integer, default=0)
    won = Column(Boolean, default=False)
    xp_awarded = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)


@arena_bp.record_once
def _ensure_tables(state):
    Base.metadata.create_all(bind=engine, tables=[DuelMatch.__table__])


BOT_ROSTER = [
    {
        "id": "rookie_bot",
        "name": "Rookie Bot",
        "avatar": "🤖",
        "tier": "C-Class",
        "accuracy": 0.55,
        "speed_s": 14,
        "quote": "I am still parsing the syntax... please don't hit too hard!",
        "xp_win": 35,
        "color": "border-slate-500/30 text-slate-400 bg-slate-500/10",
    },
    {
        "id": "speedy_py",
        "name": "Speedy Pythonista",
        "avatar": "🐍",
        "tier": "B-Class",
        "accuracy": 0.75,
        "speed_s": 8,
        "quote": "One-liner list comprehension beats your 40-line loop every time.",
        "xp_win": 75,
        "color": "border-emerald-500/30 text-emerald-400 bg-emerald-500/10",
    },
    {
        "id": "algo_demon",
        "name": "Algorithm Demon",
        "avatar": "👹",
        "tier": "A-Class",
        "accuracy": 0.88,
        "speed_s": 5,
        "quote": "Your $O(N^2)$ solution disgusts me. Face my Segment Tree!",
        "xp_win": 140,
        "color": "border-rose-500/30 text-rose-400 bg-rose-500/10",
    },
    {
        "id": "takamura_boss",
        "name": "Takamura The Champion",
        "avatar": "🥊",
        "tier": "World Champion",
        "accuracy": 0.95,
        "speed_s": 4,
        "quote": "What can a beetle do against a Hawk? Taste the world-class power!",
        "xp_win": 250,
        "color": "border-amber-500/40 text-amber-400 bg-amber-500/15",
    },
]

QUESTION_BANK = [
    {
        "id": "q1",
        "question": "What is the tightest time complexity to find the Kth largest element in an unsorted array of size N using QuickSelect (average case)?",
        "options": ["O(N log N)", "O(N)", "O(K log N)", "O(N log K)"],
        "answer": 1,
        "explanation": "QuickSelect partitions in linear time O(N) on average because N + N/2 + N/4 + ... converges to 2N = O(N).",
    },
    {
        "id": "q2",
        "question": "Which data structure is required to maintain the minimum element in an array within a moving window of size K in O(1) amortized per step?",
        "options": ["Min-Heap", "Monotonic Deque", "Red-Black Tree", "Segment Tree"],
        "answer": 1,
        "explanation": "A Monotonic Deque stores indices of candidates in increasing order; elements are pushed/popped at most once, giving O(1) amortized.",
    },
    {
        "id": "q3",
        "question": "In Distributed Systems, what does PACELC theorem state occurs in the absence of a network partition (the 'E' part)?",
        "options": ["Eventual consistency", "Trade-off between Latency and Consistency", "Linearizability only", "Availability is 100%"],
        "answer": 1,
        "explanation": "PACELC: If Partition (P), trade Availability (A) vs Consistency (C); Else (E), trade Latency (L) vs Consistency (C).",
    },
    {
        "id": "q4",
        "question": "What is the maximum recursion depth typically before encountering Stack Overflow on a standard 64-bit OS?",
        "options": ["1,000 to 10,000 frames", "1,000,000 frames", "Unlimited with virtual memory", "50 frames"],
        "answer": 0,
        "explanation": "With a default 8MB thread stack, each frame taking 100-500 bytes causes overflow around 10,000 to 80,000 calls.",
    },
    {
        "id": "q5",
        "question": "What is the optimal bitwise operation to clear the lowest set bit in an integer X?",
        "options": ["X & (X + 1)", "X & (X - 1)", "X ^ (X - 1)", "X | (X - 1)"],
        "answer": 1,
        "explanation": "Brian Kernighan's trick: X & (X - 1) flips the rightmost set bit to 0 in O(1).",
    },
    {
        "id": "q6",
        "question": "Which isolation level in ANSI SQL prevents Phantom Reads?",
        "options": ["Read Committed", "Repeatable Read", "Serializable", "Read Uncommitted"],
        "answer": 2,
        "explanation": "Serializable isolation level prevents dirty reads, non-repeatable reads, and phantom reads using range locks or MVCC snapshot validation.",
    },
    {
        "id": "q7",
        "question": "In Dijkstra's algorithm with a Fibonacci heap, what is the theoretical asymptotic time complexity for V vertices and E edges?",
        "options": ["O(E log V)", "O(E + V log V)", "O(V^2)", "O(E * V)"],
        "answer": 1,
        "explanation": "Fibonacci heaps support O(1) amortized decrease-key, yielding O(E + V log V).",
    },
    {
        "id": "q8",
        "question": "Which hash table collision resolution technique achieves superior CPU cache locality?",
        "options": ["Separate Chaining with linked lists", "Open Addressing with linear probing", "Quadratic Probing", "Double Hashing"],
        "answer": 1,
        "explanation": "Open addressing with linear probing stores elements contiguously in the same cache lines, maximizing spatial locality.",
    },
]


@arena_bp.route("/opponents", methods=["GET"])
def get_opponents():
    return jsonify({"status": "success", "data": BOT_ROSTER})


@arena_bp.route("/stats", methods=["GET"])
def get_stats():
    db = SessionLocal()
    try:
        matches = db.query(DuelMatch).all()
        total = len(matches)
        wins = sum(1 for m in matches if m.won)
        losses = total - wins
        win_rate = round((wins / total) * 100, 1) if total > 0 else 0.0

        # Calculate current streak
        recent = db.query(DuelMatch).order_by(DuelMatch.created_at.desc()).limit(10).all()
        streak = 0
        for m in recent:
            if m.won:
                streak += 1
            else:
                break

        return jsonify({
            "status": "success",
            "data": {
                "total_matches": total,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "current_streak": streak,
            },
        })
    finally:
        db.close()


@arena_bp.route("/match/start", methods=["POST"])
def start_match():
    data = request.get_json(silent=True) or {}
    bot_id = data.get("bot_id") or "speedy_py"
    bot = next((b for b in BOT_ROSTER if b["id"] == bot_id), BOT_ROSTER[1])

    # Sample 5 questions
    sample_size = min(5, len(QUESTION_BANK))
    selected = random.sample(QUESTION_BANK, sample_size)

    # Sanitize by removing correct answer from client payload
    client_questions = []
    for q in selected:
        client_questions.append({
            "id": q["id"],
            "question": q["question"],
            "options": q["options"],
        })

    return jsonify({
        "status": "success",
        "data": {
            "bot": bot,
            "questions": client_questions,
            "round_duration_s": 20,
        },
    })


@arena_bp.route("/match/submit", methods=["POST"])
def submit_match():
    data = request.get_json(silent=True) or {}
    bot_id = data.get("bot_id") or "speedy_py"
    answers = data.get("answers") or {}  # { "q1": 1, ... }
    bot = next((b for b in BOT_ROSTER if b["id"] == bot_id), BOT_ROSTER[1])

    q_map = {q["id"]: q for q in QUESTION_BANK}
    player_score = 0
    bot_score = 0
    results = []

    for q_id, chosen_idx in answers.items():
        if q_id not in q_map:
            continue
        q = q_map[q_id]
        is_player_correct = int(chosen_idx) == q["answer"]
        if is_player_correct:
            player_score += 1

        # Simulate bot intelligence based on accuracy
        is_bot_correct = random.random() < bot["accuracy"]
        if is_bot_correct:
            bot_score += 1

        results.append({
            "question_id": q_id,
            "player_correct": is_player_correct,
            "bot_correct": is_bot_correct,
            "correct_answer": q["answer"],
            "explanation": q["explanation"],
        })

    won = player_score > bot_score
    xp_reward = bot["xp_win"] if won else 15

    db = SessionLocal()
    try:
        match = DuelMatch(
            bot_id=bot_id,
            player_score=player_score,
            bot_score=bot_score,
            won=won,
            xp_awarded=xp_reward,
        )
        db.add(match)
        db.commit()
    finally:
        db.close()

    return jsonify({
        "status": "success",
        "data": {
            "player_score": player_score,
            "bot_score": bot_score,
            "won": won,
            "xp_awarded": xp_reward,
            "results": results,
            "bot": bot,
        },
    })
