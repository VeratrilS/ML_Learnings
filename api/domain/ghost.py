"""
Ghost Racer - Code Time Trial & Algorithm Muscle Memory Arena.
Compete against your personal best Ghost or AI Grandmaster Ghost in real-time code execution!
"""
from datetime import datetime, timezone
import json

from flask import Blueprint, jsonify, request
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, inspect
from sqlalchemy.orm import relationship

from api.core.db import Base, SessionLocal, engine


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class GhostTrack(Base):
    __tablename__ = "ghost_tracks"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(80), unique=True, nullable=False, index=True)
    title = Column(String(120), nullable=False)
    category = Column(String(50), default="dsa", nullable=False)  # 'dsa', 'system', 'concurrency'
    difficulty = Column(String(20), default="Medium", nullable=False)
    target_code = Column(Text, nullable=False)
    language = Column(String(30), default="python", nullable=False)
    ghost_wpm = Column(Integer, default=75, nullable=False)
    ghost_name = Column(String(80), default="Ghost Sensei", nullable=False)
    description = Column(String(250), nullable=True)

    runs = relationship("GhostRun", back_populates="track", cascade="all, delete-orphan",
                        order_by="GhostRun.time_ms.asc()")


class GhostRun(Base):
    __tablename__ = "ghost_runs"

    id = Column(Integer, primary_key=True, index=True)
    track_id = Column(Integer, ForeignKey("ghost_tracks.id", ondelete="CASCADE"), nullable=False, index=True)
    time_ms = Column(Integer, nullable=False)
    wpm = Column(Float, nullable=False)
    accuracy = Column(Float, nullable=False)
    ghost_beaten = Column(Boolean, default=False, nullable=False)
    xp_earned = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=_utcnow)

    track = relationship("GhostTrack", back_populates="runs")


ghost_bp = Blueprint("ghost", __name__, url_prefix="/api/ghost")


@ghost_bp.record_once
def _ensure_tables(state):
    try:
        Base.metadata.create_all(bind=engine, tables=[GhostTrack.__table__, GhostRun.__table__])
    except Exception as e:
        print(f"ghost table check skipped: {e}")


SEED_TRACKS = [
    {
        "slug": "binary-search",
        "title": "Binary Search",
        "category": "dsa",
        "difficulty": "Easy",
        "ghost_wpm": 65,
        "ghost_name": "Ghost Apprentice (65 WPM)",
        "description": "Logarithmic search in a sorted array with pointer convergence.",
        "target_code": """def binary_search(nums: list[int], target: int) -> int:
    left, right = 0, len(nums) - 1
    while left <= right:
        mid = (left + right) // 2
        if nums[mid] == target:
            return mid
        elif nums[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1"""
    },
    {
        "slug": "two-sum-hash",
        "title": "Two Sum (One-Pass Hash)",
        "category": "dsa",
        "difficulty": "Easy",
        "ghost_wpm": 72,
        "ghost_name": "Ghost Sentinel (72 WPM)",
        "description": "O(N) hash map lookup for complement indices.",
        "target_code": """def two_sum(nums: list[int], target: int) -> list[int]:
    seen = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i
    return []"""
    },
    {
        "slug": "reverse-linked-list",
        "title": "Reverse Linked List",
        "category": "dsa",
        "difficulty": "Easy",
        "ghost_wpm": 78,
        "ghost_name": "Ghost Sensei (78 WPM)",
        "description": "Iterative pointer reversal in O(1) auxiliary space.",
        "target_code": """def reverse_list(head):
    prev, curr = None, head
    while curr:
        nxt = curr.next
        curr.next = prev
        prev = curr
        curr = nxt
    return prev"""
    },
    {
        "slug": "lru-cache-node",
        "title": "LRU Cache Doubly Linked List",
        "category": "system",
        "difficulty": "Hard",
        "ghost_wpm": 90,
        "ghost_name": "Ghost Grandmaster (90 WPM)",
        "description": "O(1) eviction and access doubly linked list wiring.",
        "target_code": """class Node:
    def __init__(self, key=0, val=0):
        self.key, self.val = key, val
        self.prev = self.next = None

def remove_node(node):
    node.prev.next = node.next
    node.next.prev = node.prev

def add_to_head(head, node):
    node.next = head.next
    node.prev = head
    head.next.prev = node
    head.next = node"""
    },
    {
        "slug": "kadanes-algorithm",
        "title": "Kadane's Maximum Subarray",
        "category": "dsa",
        "difficulty": "Medium",
        "ghost_wpm": 82,
        "ghost_name": "Ghost Champion (82 WPM)",
        "description": "Dynamic programming running window maximum.",
        "target_code": """def max_sub_array(nums: list[int]) -> int:
    curr_sum = max_sum = nums[0]
    for num in nums[1:]:
        curr_sum = max(num, curr_sum + num)
        max_sum = max(max_sum, curr_sum)
    return max_sum"""
    },
    {
        "slug": "bfs-queue-traversal",
        "title": "BFS Graph Level Traversal",
        "category": "dsa",
        "difficulty": "Medium",
        "ghost_wpm": 85,
        "ghost_name": "Ghost Phantom (85 WPM)",
        "description": "Deque queue breadth-first search with visited set.",
        "target_code": """from collections import deque

def bfs(graph: dict, start: str) -> list[str]:
    visited, order = {start}, []
    queue = deque([start])
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return order"""
    }
]


def _ensure_seeded(db):
    if db.query(GhostTrack.id).first() is None:
        for t in SEED_TRACKS:
            db.add(GhostTrack(**t))
        db.commit()


@ghost_bp.route("/tracks", methods=["GET"])
def get_tracks():
    db = SessionLocal()
    try:
        _ensure_seeded(db)
        tracks = db.query(GhostTrack).all()
        result = []
        for t in tracks:
            best_run = db.query(GhostRun).filter(GhostRun.track_id == t.id).order_by(GhostRun.time_ms.asc()).first()
            result.append({
                "id": t.id,
                "slug": t.slug,
                "title": t.title,
                "category": t.category,
                "difficulty": t.difficulty,
                "language": t.language,
                "ghost_wpm": t.ghost_wpm,
                "ghost_name": t.ghost_name,
                "description": t.description,
                "target_code": t.target_code,
                "char_count": len(t.target_code),
                "best_time_ms": best_run.time_ms if best_run else None,
                "best_wpm": best_run.wpm if best_run else None,
                "ghost_beaten": best_run.ghost_beaten if best_run else False,
            })
        return jsonify({"status": "success", "tracks": result})
    finally:
        db.close()


@ghost_bp.route("/submit", methods=["POST"])
def submit_run():
    db = SessionLocal()
    try:
        data = request.get_json(silent=True) or {}
        track_id = data.get("track_id")
        time_ms = int(data.get("time_ms") or 0)
        accuracy = float(data.get("accuracy") or 100.0)

        track = db.get(GhostTrack, track_id)
        if not track:
            return jsonify({"status": "error", "message": "Track not found"}), 404

        time_s = max(0.5, time_ms / 1000.0)
        words = len(track.target_code) / 5.0
        wpm = round((words / time_s) * 60.0, 1)

        ghost_beaten = wpm >= track.ghost_wpm and accuracy >= 95.0
        base_xp = 35
        if ghost_beaten:
            base_xp += 50
        if accuracy >= 98.0:
            base_xp += 15

        run = GhostRun(
            track_id=track.id,
            time_ms=time_ms,
            wpm=wpm,
            accuracy=accuracy,
            ghost_beaten=ghost_beaten,
            xp_earned=base_xp,
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        return jsonify({
            "status": "success",
            "run": {
                "id": run.id,
                "track_id": track.id,
                "time_ms": run.time_ms,
                "wpm": run.wpm,
                "accuracy": run.accuracy,
                "ghost_beaten": run.ghost_beaten,
                "xp_earned": base_xp,
            },
        })
    finally:
        db.close()


@ghost_bp.route("/profile", methods=["GET"])
def get_profile():
    db = SessionLocal()
    try:
        runs = db.query(GhostRun).all()
        total_races = len(runs)
        ghost_wins = sum(1 for r in runs if r.ghost_beaten)
        avg_wpm = round(sum(r.wpm for r in runs) / total_races, 1) if total_races else 0
        top_wpm = max((r.wpm for r in runs), default=0)

        # Dynamic Ghost Elo computation
        elo = 1200 + (ghost_wins * 25) + int(top_wpm * 2)

        return jsonify({
            "status": "success",
            "stats": {
                "total_races": total_races,
                "ghost_wins": ghost_wins,
                "avg_wpm": avg_wpm,
                "top_wpm": top_wpm,
                "ghost_elo": elo,
            }
        })
    finally:
        db.close()
