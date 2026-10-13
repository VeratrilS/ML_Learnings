"""
Skill Radar & Elo Predictor: Multi-topic DSA skill matrix with dynamic Elo ratings,
weakest topic recovery roadmaps, and contest performance simulations.
"""
from collections import defaultdict
from flask import Blueprint, jsonify, request

from api.core.db import SessionLocal
from api.domain.models import NotificationLog

radar_bp = Blueprint("radar", __name__, url_prefix="/api/radar")

TOPICS = [
    {"key": "Dynamic Programming", "short": "DP", "icon": "⚡", "base_elo": 1200},
    {"key": "Graphs", "short": "Graphs", "icon": "🕸️", "base_elo": 1200},
    {"key": "Binary Trees", "short": "Trees", "icon": "🌲", "base_elo": 1200},
    {"key": "Binary Search", "short": "BS", "icon": "🎯", "base_elo": 1200},
    {"key": "Arrays", "short": "Arrays", "icon": "📊", "base_elo": 1200},
    {"key": "Strings", "short": "Strings", "icon": "🔤", "base_elo": 1200},
]


@radar_bp.route("/elo", methods=["GET"])
def get_elo_radar():
    db = SessionLocal()
    try:
        # Tally solved problems by topic
        solved_logs = db.query(NotificationLog).filter(
            NotificationLog.is_completed == True,  # noqa: E712
        ).all()

        counts = defaultdict(int)
        for log in solved_logs:
            t = log.topic or "Arrays"
            for candidate in TOPICS:
                if candidate["key"].lower() in t.lower():
                    counts[candidate["key"]] += 1

        topic_stats = []
        for t in TOPICS:
            solved = counts[t["key"]]
            elo = t["base_elo"] + (solved * 35)
            # Level: Bronze (1200-1350), Silver (1350-1550), Gold (1550-1800), Diamond (>1800)
            tier = "Bronze" if elo < 1350 else "Silver" if elo < 1550 else "Gold" if elo < 1800 else "Diamond"
            topic_stats.append({
                "key": t["key"],
                "short": t["short"],
                "icon": t["icon"],
                "solved": solved,
                "elo": elo,
                "tier": tier,
            })

        # Find weakest topic (lowest Elo)
        weakest = min(topic_stats, key=lambda x: x["elo"])
        
        # Recovery plan for weakest topic
        recovery_plan = [
            {"step": 1, "action": f"Warmup: Solve 1 Easy {weakest['key']} question on pattern recognition.", "xp": 30},
            {"step": 2, "action": f"Medium Core: Trace 1 classic Medium {weakest['key']} using the Unstuck protocol.", "xp": 60},
            {"step": 3, "action": f"Mastery: Run an Agent Swarm mission focused on {weakest['key']} edge cases.", "xp": 100},
        ]

        overall_elo = int(sum(ts["elo"] for ts in topic_stats) / len(topic_stats))

        return jsonify({
            "status": "success",
            "data": {
                "overall_elo": overall_elo,
                "topics": topic_stats,
                "weakest_topic": weakest,
                "recovery_plan": recovery_plan,
            },
        })
    finally:
        db.close()


@radar_bp.route("/predict", methods=["GET"])
def predict_contest():
    # Predict rating delta based on simulated contest performance (e.g., solved 2 vs 3 vs 4)
    simulations = [
        {"solves": 1, "predicted_cf_delta": -15, "predicted_lc_delta": -10, "rating_band": "Struggle"},
        {"solves": 2, "predicted_cf_delta": +25, "predicted_lc_delta": +15, "rating_band": "Solid Average"},
        {"solves": 3, "predicted_cf_delta": +75, "predicted_lc_delta": +45, "rating_band": "High Performance"},
        {"solves": 4, "predicted_cf_delta": +140, "predicted_lc_delta": +85, "rating_band": "Contest Carry"},
    ]
    return jsonify({"status": "success", "data": simulations})
