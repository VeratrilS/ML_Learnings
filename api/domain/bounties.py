"""
Bounties & DSA Gacha: Daily bounty contract board and dopamine-rich mystery problem pulls
with rarity tiers (Common to Legendary), streak bonuses, and XP rewards.
"""
import hashlib
import random
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Boolean, Column, DateTime, Integer, String

from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine

bounties_bp = Blueprint("bounties", __name__, url_prefix="/api/bounties")


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BountyClaim(Base):
    __tablename__ = "bounty_claims"
    id = Column(Integer, primary_key=True, index=True)
    bounty_id = Column(String(50), nullable=False)
    date_key = Column(String(20), nullable=False)  # YYYY-MM-DD
    xp_awarded = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)


class GachaPull(Base):
    __tablename__ = "gacha_pulls"
    id = Column(Integer, primary_key=True, index=True)
    date_key = Column(String(20), nullable=False)
    problem_title = Column(String(200), nullable=False)
    rarity = Column(String(20), nullable=False)  # Common, Rare, Epic, Legendary
    topic = Column(String(100), nullable=False)
    link = Column(String(500), nullable=True)
    xp_bonus = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)


@bounties_bp.record_once
def _ensure_tables(state):
    Base.metadata.create_all(bind=engine, tables=[BountyClaim.__table__, GachaPull.__table__])


# High-frequency curated problem pool across rarity tiers
GACHA_VAULT = [
    # Common (Fundamentals & frequent warmups)
    {"title": "Two Sum", "difficulty": "Easy", "rarity": "Common", "topic": "Arrays & Hash Table", "link": "https://leetcode.com/problems/two-sum/", "xp": 25},
    {"title": "Valid Parentheses", "difficulty": "Easy", "rarity": "Common", "topic": "Stack", "link": "https://leetcode.com/problems/valid-parentheses/", "xp": 25},
    {"title": "Best Time to Buy and Sell Stock", "difficulty": "Easy", "rarity": "Common", "topic": "Sliding Window", "link": "https://leetcode.com/problems/best-time-to-buy-and-sell-stock/", "xp": 25},
    {"title": "Invert Binary Tree", "difficulty": "Easy", "rarity": "Common", "topic": "Binary Trees", "link": "https://leetcode.com/problems/invert-binary-tree/", "xp": 25},
    {"title": "Reverse Linked List", "difficulty": "Easy", "rarity": "Common", "topic": "Linked List", "link": "https://leetcode.com/problems/reverse-linked-list/", "xp": 25},
    
    # Rare (High-yield FAANG Mediums)
    {"title": "Longest Substring Without Repeating Characters", "difficulty": "Medium", "rarity": "Rare", "topic": "Sliding Window", "link": "https://leetcode.com/problems/longest-substring-without-repeating-characters/", "xp": 60},
    {"title": "3Sum", "difficulty": "Medium", "rarity": "Rare", "topic": "Two Pointers", "link": "https://leetcode.com/problems/3sum/", "xp": 60},
    {"title": "Coin Change", "difficulty": "Medium", "rarity": "Rare", "topic": "Dynamic Programming", "link": "https://leetcode.com/problems/coin-change/", "xp": 60},
    {"title": "Number of Islands", "difficulty": "Medium", "rarity": "Rare", "topic": "Graphs (BFS/DFS)", "link": "https://leetcode.com/problems/number-of-islands/", "xp": 60},
    {"title": "Course Schedule", "difficulty": "Medium", "rarity": "Rare", "topic": "Topological Sort", "link": "https://leetcode.com/problems/course-schedule/", "xp": 60},
    {"title": "Kth Largest Element in an Array", "difficulty": "Medium", "rarity": "Rare", "topic": "Heaps / QuickSelect", "link": "https://leetcode.com/problems/kth-largest-element-in-an-array/", "xp": 60},
    
    # Epic (Classic signature medium-to-hard patterns)
    {"title": "LRU Cache", "difficulty": "Medium", "rarity": "Epic", "topic": "Design & Doubly Linked List", "link": "https://leetcode.com/problems/lru-cache/", "xp": 120},
    {"title": "Word Break", "difficulty": "Medium", "rarity": "Epic", "topic": "Trie & 1D DP", "link": "https://leetcode.com/problems/word-break/", "xp": 120},
    {"title": "Alien Dictionary", "difficulty": "Hard", "rarity": "Epic", "topic": "Graph & Kahn's Algorithm", "link": "https://leetcode.com/problems/alien-dictionary/", "xp": 150},
    {"title": "Edit Distance", "difficulty": "Medium", "rarity": "Epic", "topic": "2D Dynamic Programming", "link": "https://leetcode.com/problems/edit-distance/", "xp": 130},
    
    # Legendary (Google OA / Hard Contest Bosses)
    {"title": "Trapping Rain Water", "difficulty": "Hard", "rarity": "Legendary", "topic": "Two Pointers & Monotonic Stack", "link": "https://leetcode.com/problems/trapping-rain-water/", "xp": 250},
    {"title": "Median of Two Sorted Arrays", "difficulty": "Hard", "rarity": "Legendary", "topic": "Binary Search on Partition", "link": "https://leetcode.com/problems/median-of-two-sorted-arrays/", "xp": 300},
    {"title": "Merge k Sorted Lists", "difficulty": "Hard", "rarity": "Legendary", "topic": "Divide and Conquer / Min-Heap", "link": "https://leetcode.com/problems/merge-k-sorted-lists/", "xp": 260},
    {"title": "Largest Rectangle in Histogram", "difficulty": "Hard", "rarity": "Legendary", "topic": "Monotonic Stack $O(N)$", "link": "https://leetcode.com/problems/largest-rectangle-in-histogram/", "xp": 280},
]


def _today_str():
    return now_ist().strftime("%Y-%m-%d")


def _get_daily_bounties(date_key: str):
    # Deterministic generation per IST day
    seed = int(hashlib.md5(f"bounties:{date_key}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    topics = ["Dynamic Programming", "Graphs", "Sliding Window", "Trees", "Binary Search", "Heaps", "Greedy"]
    rng.shuffle(topics)

    bounties = [
        {
            "id": f"bounty-bronze-{date_key}",
            "tier": "Bronze",
            "title": "Speed Warmup",
            "desc": f"Solve any Easy problem or 10 flashcards in {topics[0]}.",
            "xp": 40,
            "badge": "🥉 Bronze Contract",
            "color": "from-amber-600/15 to-amber-700/5 text-amber-500 border-amber-500/20",
        },
        {
            "id": f"bounty-silver-{date_key}",
            "tier": "Silver",
            "title": f"{topics[1]} Mastery",
            "desc": f"Solve a Medium {topics[1]} problem or run a 25m Focus Speedrun.",
            "xp": 100,
            "badge": "🥈 Silver Contract",
            "color": "from-slate-400/15 to-slate-500/5 text-slate-300 border-slate-400/20",
        },
        {
            "id": f"bounty-gold-{date_key}",
            "tier": "Gold",
            "title": "Boss Raid Duel",
            "desc": "Win a Code Arena Duel against an AI rival or hit the Gym Boss for 40+ damage.",
            "xp": 220,
            "badge": "🥇 Gold Contract",
            "color": "from-yellow-500/20 to-amber-500/10 text-yellow-500 border-yellow-500/30",
        },
        {
            "id": f"bounty-legendary-{date_key}",
            "tier": "Legendary",
            "title": "Swarm Parallel Operation",
            "desc": "Launch an ALL OUT Parallel Agent Swarm mission and review the full Sentinel audit.",
            "xp": 350,
            "badge": "💎 Swarm Contract",
            "color": "from-purple-500/20 to-fuchsia-500/10 text-purple-400 border-purple-500/30",
        },
    ]
    return bounties


@bounties_bp.route("/today", methods=["GET"])
def get_today_bounties():
    date_key = _today_str()
    bounties = _get_daily_bounties(date_key)

    db = SessionLocal()
    try:
        claims = {c.bounty_id for c in db.query(BountyClaim).filter(BountyClaim.date_key == date_key).all()}
        for b in bounties:
            b["claimed"] = b["id"] in claims

        # Gacha status today
        pull = db.query(GachaPull).filter(GachaPull.date_key == date_key).first()
        gacha_status = {
            "has_pulled_today": bool(pull),
            "today_pull": {
                "title": pull.problem_title,
                "rarity": pull.rarity,
                "topic": pull.topic,
                "link": pull.link,
                "xp": pull.xp_bonus,
            } if pull else None,
        }

        return jsonify({
            "status": "success",
            "data": {
                "date": date_key,
                "bounties": bounties,
                "completed_count": sum(1 for b in bounties if b["claimed"]),
                "total_count": len(bounties),
                "gacha": gacha_status,
            },
        })
    finally:
        db.close()


@bounties_bp.route("/claim", methods=["POST"])
def claim_bounty():
    data = request.get_json(silent=True) or {}
    bounty_id = data.get("bounty_id")
    if not bounty_id:
        return jsonify({"status": "error", "message": "Missing bounty_id"}), 400

    date_key = _today_str()
    bounties = _get_daily_bounties(date_key)
    target = next((b for b in bounties if b["id"] == bounty_id), None)
    if not target:
        return jsonify({"status": "error", "message": "Invalid bounty for today"}), 400

    db = SessionLocal()
    try:
        existing = db.query(BountyClaim).filter(BountyClaim.bounty_id == bounty_id, BountyClaim.date_key == date_key).first()
        if existing:
            return jsonify({"status": "success", "data": {"already_claimed": True, "xp": existing.xp_awarded}})

        claim = BountyClaim(bounty_id=bounty_id, date_key=date_key, xp_awarded=target["xp"])
        db.add(claim)
        db.commit()
        return jsonify({"status": "success", "data": {"claimed": True, "xp_awarded": target["xp"]}})
    finally:
        db.close()


@bounties_bp.route("/gacha/pull", methods=["POST"])
def gacha_pull():
    date_key = _today_str()
    db = SessionLocal()
    try:
        existing = db.query(GachaPull).filter(GachaPull.date_key == date_key).first()
        if existing:
            return jsonify({
                "status": "success",
                "data": {
                    "already_pulled": True,
                    "pull": {
                        "title": existing.problem_title,
                        "rarity": existing.rarity,
                        "topic": existing.topic,
                        "link": existing.link,
                        "xp": existing.xp_bonus,
                    },
                },
            })

        # Weighted roll for rarity
        # Common: 30%, Rare: 45%, Epic: 18%, Legendary: 7%
        roll = random.random()
        if roll < 0.30:
            target_rarity = "Common"
        elif roll < 0.75:
            target_rarity = "Rare"
        elif roll < 0.93:
            target_rarity = "Epic"
        else:
            target_rarity = "Legendary"

        candidates = [p for p in GACHA_VAULT if p["rarity"] == target_rarity] or GACHA_VAULT
        chosen = random.choice(candidates)

        new_pull = GachaPull(
            date_key=date_key,
            problem_title=chosen["title"],
            rarity=chosen["rarity"],
            topic=chosen["topic"],
            link=chosen.get("link"),
            xp_bonus=chosen["xp"],
        )
        db.add(new_pull)
        db.commit()

        return jsonify({
            "status": "success",
            "data": {
                "pull": {
                    "title": chosen["title"],
                    "rarity": chosen["rarity"],
                    "topic": chosen["topic"],
                    "link": chosen.get("link"),
                    "xp": chosen["xp"],
                    "difficulty": chosen.get("difficulty"),
                },
            },
        })
    finally:
        db.close()
