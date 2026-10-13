"""
Time Complexity Casino — Rapid-Fire Big-O Intuition & Asymptotic Shootout.
Predict time and space complexity under a timer, build winning streaks,
and unlock Master of Asymptotics achievements with formal recurrence proofs.
"""
from datetime import datetime, timezone
import json
import random

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, DateTime, Integer, String, Text

from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine

complexity_bp = Blueprint("complexity", __name__, url_prefix="/api/complexity")


class ComplexityPlayer(Base):
    __tablename__ = "complexity_players"

    id = Column(Integer, primary_key=True)
    chips = Column(Integer, nullable=False, default=500)
    current_streak = Column(Integer, nullable=False, default=0)
    best_streak = Column(Integer, nullable=False, default=0)
    total_guesses = Column(Integer, nullable=False, default=0)
    correct_guesses = Column(Integer, nullable=False, default=0)
    xp_earned = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: now_ist())

    def to_dict(self):
        return {
            "chips": self.chips,
            "current_streak": self.current_streak,
            "best_streak": self.best_streak,
            "total_guesses": self.total_guesses,
            "correct_guesses": self.correct_guesses,
            "xp_earned": self.xp_earned,
        }


Base.metadata.create_all(bind=engine, tables=[ComplexityPlayer.__table__], checkfirst=True)


CHALLENGES = [
    {
        "id": "c_01_geometric_nested",
        "title": "Geometric Inner Step",
        "badge": "Tricky",
        "code": (
            "def algorithm_one(n):\n"
            "    count = 0\n"
            "    for i in range(n):\n"
            "        j = 1\n"
            "        while j < n:\n"
            "            count += 1\n"
            "            j *= 2\n"
            "    return count"
        ),
        "correct_time": "O(N log N)",
        "correct_space": "O(1)",
        "choices": ["O(N)", "O(N log N)", "O(N^2)", "O(log N)", "O(2^N)"],
        "proof": "The outer loop runs N times. The inner loop doubles j until reaching N, which executes log2(N) times. Total operations: N * log2(N) = O(N log N)."
    },
    {
        "id": "c_02_sqrt_bound",
        "title": "Prime Factor Sieve Boundary",
        "badge": "Classic",
        "code": (
            "def algorithm_two(n):\n"
            "    factors = []\n"
            "    d = 2\n"
            "    while d * d <= n:\n"
            "        if n % d == 0:\n"
            "            factors.append(d)\n"
            "            n //= d\n"
            "        else:\n"
            "            d += 1\n"
            "    return factors"
        ),
        "correct_time": "O(sqrt(N))",
        "correct_space": "O(log N)",
        "choices": ["O(log N)", "O(sqrt(N))", "O(N)", "O(N log N)", "O(1)"],
        "proof": "The loop terminates when d > sqrt(N). In the worst case (prime number), d increments from 2 up to sqrt(N), executing in O(sqrt(N)) time."
    },
    {
        "id": "c_03_divide_conquer",
        "title": "Merge Sort Recurrence",
        "badge": "Master Theorem",
        "code": (
            "def sort_split(arr):\n"
            "    if len(arr) <= 1:\n"
            "        return arr\n"
            "    mid = len(arr) // 2\n"
            "    left = sort_split(arr[:mid])\n"
            "    right = sort_split(arr[mid:])\n"
            "    return merge(left, right)  # linear O(N) merge"
        ),
        "correct_time": "O(N log N)",
        "correct_space": "O(N)",
        "choices": ["O(N)", "O(N log N)", "O(N^2)", "O(log N)", "O(N^2 log N)"],
        "proof": "Recurrence relation T(N) = 2T(N/2) + O(N). By Master Theorem Case 2 (log_b(a) = log_2(2) = 1 == c), T(N) = Theta(N^1 * log N) = O(N log N)."
    },
    {
        "id": "c_04_brian_kernighan",
        "title": "Brian Kernighan's Bit Trick",
        "badge": "Bitwise",
        "code": (
            "def count_set_bits(n):\n"
            "    count = 0\n"
            "    while n > 0:\n"
            "        n &= (n - 1)  # clears least significant set bit\n"
            "        count += 1\n"
            "    return count"
        ),
        "correct_time": "O(K) <= O(log N)",
        "correct_space": "O(1)",
        "choices": ["O(N)", "O(1)", "O(K) <= O(log N)", "O(N^2)", "O(2^N)"],
        "proof": "Each iteration of n &= (n - 1) clears the lowest set bit. The loop runs exactly K times where K is the number of 1-bits, at most ceil(log2 N) iterations."
    },
    {
        "id": "c_05_naive_fibonacci",
        "title": "Unmemoized Tree Recursion",
        "badge": "Exponential",
        "code": (
            "def fibonacci(n):\n"
            "    if n <= 1:\n"
            "        return n\n"
            "    return fibonacci(n - 1) + fibonacci(n - 2)"
        ),
        "correct_time": "O(2^N)",
        "correct_space": "O(N)",
        "choices": ["O(N)", "O(N log N)", "O(2^N)", "O(N!)", "O(log N)"],
        "proof": "Each call branches into two subproblems. The recursion tree has depth N, yielding roughly 2^0 + 2^1 + ... + 2^N = O(2^N) total function calls."
    },
    {
        "id": "c_06_euclidean_gcd",
        "title": "Euclid's Remainder GCD",
        "badge": "Logarithmic",
        "code": (
            "def gcd(a, b):\n"
            "    while b != 0:\n"
            "        a, b = b, a % b\n"
            "    return a"
        ),
        "correct_time": "O(log(min(A, B)))",
        "correct_space": "O(1)",
        "choices": ["O(min(A, B))", "O(log(min(A, B)))", "O(1)", "O(A * B)", "O(sqrt(min(A, B)))"],
        "proof": "By Lamé's Theorem, the remainder at each step is at most half the larger number: (a % b) < a / 2. The number of steps is proportional to the number of decimal digits, O(log(min(a, b)))."
    }
]


def _get_or_create_player(db):
    player = db.query(ComplexityPlayer).first()
    if not player:
        player = ComplexityPlayer(chips=500)
        db.add(player)
        db.commit()
        db.refresh(player)
    return player


@complexity_bp.route("/challenges", methods=["GET"])
def list_challenges():
    db = SessionLocal()
    player = _get_or_create_player(db)
    player_data = player.to_dict()
    db.close()

    sanitized = []
    for c in CHALLENGES:
        sanitized.append({
            "id": c["id"],
            "title": c["title"],
            "badge": c["badge"],
            "code": c["code"],
            "choices": c["choices"],
        })

    return jsonify({"challenges": sanitized, "player": player_data})


@complexity_bp.route("/guess", methods=["POST"])
def submit_guess():
    data = request.get_json() or {}
    challenge_id = data.get("challenge_id")
    guessed_time = (data.get("guessed_time") or "").strip()
    wager = max(10, min(100, int(data.get("wager") or 25)))

    ch = next((c for c in CHALLENGES if c["id"] == challenge_id), None)
    if not ch:
        return jsonify({"error": "Challenge not found"}), 404

    is_correct = (guessed_time == ch["correct_time"])

    db = SessionLocal()
    player = _get_or_create_player(db)
    player.total_guesses += 1

    if is_correct:
        player.correct_guesses += 1
        player.current_streak += 1
        if player.current_streak > player.best_streak:
            player.best_streak = player.current_streak

        # Multiplier scales with streak
        multiplier = 1.0 + min(2.0, (player.current_streak - 1) * 0.25)
        chips_won = int(wager * multiplier)
        xp_gain = 30 + (player.current_streak * 5)
        player.chips += chips_won
        player.xp_earned += xp_gain
    else:
        player.current_streak = 0
        chips_won = -wager
        xp_gain = 5  # pity XP
        player.chips = max(50, player.chips - wager)  # floor at 50 so never bankrupt
        player.xp_earned += xp_gain

    db.commit()
    player_data = player.to_dict()
    db.close()

    return jsonify({
        "correct": is_correct,
        "guessed": guessed_time,
        "actual_time": ch["correct_time"],
        "actual_space": ch["correct_space"],
        "proof": ch["proof"],
        "chips_delta": chips_won,
        "xp_awarded": xp_gain,
        "player": player_data,
    })
