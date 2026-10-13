"""
Commit Forge & Code Alchemy - RPG Artifact Crafting from Real Code.
Alchemizes your algorithms, functions, and commit snippets into collectible RPG Gear!
"""
from datetime import datetime, timezone
import hashlib
import random
import re

from flask import Blueprint, jsonify, request
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from api.core.db import Base, SessionLocal, engine


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ForgedArtifact(Base):
    __tablename__ = "forged_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    rarity = Column(String(30), default="Rare", nullable=False)  # Common, Rare, Epic, Legendary, Mythic
    slot = Column(String(30), default="Weapon", nullable=False)  # Weapon, Shield, Relic, Armor, Ring
    power = Column(Integer, default=50, nullable=False)
    resilience = Column(Integer, default=50, nullable=False)
    speed = Column(Integer, default=50, nullable=False)
    elegance = Column(Integer, default=50, nullable=False)
    level = Column(Integer, default=1, nullable=False)
    flavor_text = Column(String(300), nullable=True)
    code_snippet = Column(Text, nullable=True)
    language = Column(String(30), default="python", nullable=False)
    created_at = Column(DateTime, default=_utcnow)


forge_bp = Blueprint("forge", __name__, url_prefix="/api/forge")


@forge_bp.record_once
def _ensure_tables(state):
    try:
        Base.metadata.create_all(bind=engine, tables=[ForgedArtifact.__table__])
    except Exception as e:
        print(f"forge table check skipped: {e}")


ARTIFACT_NAMES = {
    "Weapon": [
        "Blade of Logarithmic Convergence",
        "Edge of Constant Asymptote",
        "Dagger of Bitwise Precision",
        "Glaive of Recursive Depth",
        "Scythe of Garbage Collection",
    ],
    "Shield": [
        "Aegis of Idempotent State",
        "Bulwark of Boundary Safety",
        "Barrier of Thread Isolation",
        "Guard of Zero Latency",
    ],
    "Relic": [
        "Tome of Master Theorem",
        "Orb of Monadic Purity",
        "Prism of Spectral Decomposition",
        "Crown of Dynamic Recurrence",
        "Amulet of Async Resilience",
    ],
    "Ring": [
        "Band of Cyclic Pointers",
        "Ring of Hash Collisions",
        "Signet of Memoized Eternity",
    ],
}

FLAVORS = [
    "Forged in the fiery crucible of production edge-cases.",
    "Whispers of O(1) runtime echo through its spectral crystalline frame.",
    "Immune to race conditions; blessed by Dijkstra's shortest path.",
    "Infused with immutable memory semantics and atomic consistency.",
    "A legendary relic whispered to solve NP-complete theorems in polynomial time.",
]


def _analyze_code(code: str):
    """Computes code statistics: complexity, elegance, and power."""
    lines = [l for l in code.splitlines() if l.strip()]
    num_lines = max(1, len(lines))
    chars = len(code)
    has_recursion = bool(re.search(r"\bdef\s+(\w+).*?\1\s*\(", code, re.DOTALL))
    has_loops = len(re.findall(r"\b(for|while)\b", code))
    has_conditionals = len(re.findall(r"\b(if|elif|else)\b", code))
    has_typing = bool(re.search(r"->\s*|:\s*(int|str|list|dict|float|bool)", code))

    complexity = 40 + min(40, (has_loops * 8) + (has_conditionals * 5) + (15 if has_recursion else 0))
    elegance = 50 + (15 if has_typing else 0) + (15 if num_lines <= 25 else 0)
    resilience = 45 + (15 if "try:" in code or "except" in code else 5) + min(25, num_lines * 2)
    speed = 50 + (25 if "return" in code and has_loops <= 1 else 10)

    # Compute overall score (0 - 100)
    score = (complexity + elegance + resilience + speed) / 4.0
    return {
        "complexity": complexity,
        "elegance": elegance,
        "resilience": resilience,
        "speed": speed,
        "score": score,
        "num_lines": num_lines,
        "chars": chars,
    }


def _roll_rarity(score: float):
    # Weighted by code quality score
    roll = random.random() * 100.0 + (score * 0.25)
    if roll >= 95:
        return "Mythic"
    if roll >= 80:
        return "Legendary"
    if roll >= 60:
        return "Epic"
    if roll >= 35:
        return "Rare"
    return "Common"


@forge_bp.route("/inventory", methods=["GET"])
def get_inventory():
    db = SessionLocal()
    try:
        artifacts = db.query(ForgedArtifact).order_by(ForgedArtifact.created_at.desc()).all()
        total_power = sum(a.power + a.resilience + a.speed + a.elegance for a in artifacts)
        forge_level = 1 + (len(artifacts) // 2)

        return jsonify({
            "status": "success",
            "forge_level": forge_level,
            "total_power": total_power,
            "artifacts_count": len(artifacts),
            "artifacts": [
                {
                    "id": a.id,
                    "name": a.name,
                    "rarity": a.rarity,
                    "slot": a.slot,
                    "power": a.power,
                    "resilience": a.resilience,
                    "speed": a.speed,
                    "elegance": a.elegance,
                    "level": a.level,
                    "flavor_text": a.flavor_text,
                    "language": a.language,
                    "code_snippet": a.code_snippet,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in artifacts
            ]
        })
    finally:
        db.close()


@forge_bp.route("/transmute", methods=["POST"])
def transmute_code():
    db = SessionLocal()
    try:
        data = request.get_json(silent=True) or {}
        code = (data.get("code") or "").strip()
        custom_name = (data.get("name") or "").strip()
        slot = data.get("slot") or random.choice(list(ARTIFACT_NAMES.keys()))
        language = (data.get("language") or "python").strip()

        if not code or len(code) < 15:
            return jsonify({"status": "error", "message": "Code snippet must be at least 15 characters to alchemize."}), 400

        analysis = _analyze_code(code)
        rarity = _roll_rarity(analysis["score"])

        # Stat multipliers based on rarity
        mult = {"Common": 1.0, "Rare": 1.25, "Epic": 1.5, "Legendary": 1.85, "Mythic": 2.25}.get(rarity, 1.0)
        power = min(150, int(analysis["complexity"] * mult))
        resilience = min(150, int(analysis["resilience"] * mult))
        speed = min(150, int(analysis["speed"] * mult))
        elegance = min(150, int(analysis["elegance"] * mult))

        artifact_name = custom_name or random.choice(ARTIFACT_NAMES.get(slot, ARTIFACT_NAMES["Weapon"]))
        flavor = random.choice(FLAVORS)

        artifact = ForgedArtifact(
            name=artifact_name,
            rarity=rarity,
            slot=slot,
            power=power,
            resilience=resilience,
            speed=speed,
            elegance=elegance,
            level=1,
            flavor_text=flavor,
            code_snippet=code[:1000],
            language=language,
        )
        db.add(artifact)
        db.commit()
        db.refresh(artifact)

        xp_reward = {"Common": 40, "Rare": 65, "Epic": 95, "Legendary": 140, "Mythic": 220}.get(rarity, 50)

        return jsonify({
            "status": "success",
            "artifact": {
                "id": artifact.id,
                "name": artifact.name,
                "rarity": artifact.rarity,
                "slot": artifact.slot,
                "power": artifact.power,
                "resilience": artifact.resilience,
                "speed": artifact.speed,
                "elegance": artifact.elegance,
                "level": artifact.level,
                "flavor_text": artifact.flavor_text,
                "code_snippet": artifact.code_snippet,
            },
            "analysis": analysis,
            "xp_earned": xp_reward,
        }), 201
    finally:
        db.close()


@forge_bp.route("/upgrade/<int:artifact_id>", methods=["POST"])
def upgrade_artifact(artifact_id):
    db = SessionLocal()
    try:
        artifact = db.get(ForgedArtifact, artifact_id)
        if not artifact:
            return jsonify({"status": "error", "message": "Artifact not found"}), 404

        artifact.level += 1
        artifact.power += random.randint(4, 9)
        artifact.resilience += random.randint(4, 9)
        artifact.speed += random.randint(3, 8)
        artifact.elegance += random.randint(3, 8)
        db.commit()
        db.refresh(artifact)

        return jsonify({
            "status": "success",
            "artifact": {
                "id": artifact.id,
                "name": artifact.name,
                "level": artifact.level,
                "power": artifact.power,
                "resilience": artifact.resilience,
                "speed": artifact.speed,
                "elegance": artifact.elegance,
            }
        })
    finally:
        db.close()
