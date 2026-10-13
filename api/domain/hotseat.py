"""
The Hot Seat — High-stakes Mock Oral Defense & Viva Combat Arena.
Faced with a tribunal of 3 demanding AI professors (Dr. Rigor, Architect Vance, Prof. Chaos),
the candidate defends technical intuition under a ticking clock and live Composure meter.
"""
from datetime import datetime, timezone
import json
import random

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, DateTime, Integer, String, Text

from api.core.clients import LLMClient
from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine

hotseat_bp = Blueprint("hotseat", __name__, url_prefix="/api/hotseat")


class HotSeatSession(Base):
    __tablename__ = "hotseat_sessions"

    id = Column(Integer, primary_key=True)
    subject = Column(String(120), nullable=False)
    difficulty = Column(String(40), nullable=False, default="masters")  # undergraduate, masters, phd
    status = Column(String(40), nullable=False, default="active")       # active, completed, roasted
    composure = Column(Integer, nullable=False, default=100)           # 0..100
    questions_total = Column(Integer, nullable=False, default=4)
    current_turn = Column(Integer, nullable=False, default=1)
    turns_data = Column(Text, nullable=False, default="[]")            # JSON serialized list of turns
    final_verdict = Column(String(60), nullable=True)                  # Summa Cum Laude, Magna Cum Laude, Passed, Roasted
    xp_awarded = Column(Integer, nullable=False, default=0)
    feedback_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: now_ist())
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        try:
            turns = json.loads(self.turns_data or "[]")
        except Exception:
            turns = []
        return {
            "id": self.id,
            "subject": self.subject,
            "difficulty": self.difficulty,
            "status": self.status,
            "composure": self.composure,
            "questions_total": self.questions_total,
            "current_turn": self.current_turn,
            "turns": turns,
            "final_verdict": self.final_verdict,
            "xp_awarded": self.xp_awarded,
            "feedback_summary": self.feedback_summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# Ensure table schema is registered
Base.metadata.create_all(bind=engine, tables=[HotSeatSession.__table__], checkfirst=True)


PROFESSORS = [
    {
        "id": "rigor",
        "name": "Dr. Rigor",
        "title": "The Asymptotic Purist",
        "avatar": "⚖️",
        "vibe": "Demands mathematical rigor, tight worst-case bounds, and formal invariants.",
        "quote": "Don't handwave the constants. What is your formal lower bound?"
    },
    {
        "id": "vance",
        "name": "Architect Vance",
        "title": "Principal Distributed Systems Fellow",
        "avatar": "🏗️",
        "vibe": "Probes production failure modes, network partitions, and CAP theorem trade-offs.",
        "quote": "Works on localhost? Good luck when the us-east datacenter goes dark."
    },
    {
        "id": "chaos",
        "name": "Prof. Chaos",
        "title": "Adversarial Edge-Case Inquisitor",
        "avatar": "⚡",
        "vibe": "Pounces on race conditions, memory stomping, integer overflows, and corrupted packets.",
        "quote": "Let's see your invariant hold when two concurrent threads hit this simultaneously."
    }
]

CURATED_TOPICS = [
    {
        "id": "distributed_raft",
        "title": "Raft Consensus & Split Brains",
        "domain": "Distributed Systems",
        "badge": "Hard",
        "starter": "In a Raft cluster of 5 nodes experiencing an asymmetric network partition, how does leader election prevent split-brain commitments?",
        "keywords": ["quorum", "majority", "term", "log index", "heartbeat", "leader election", "split-brain"]
    },
    {
        "id": "transformers_attention",
        "title": "Self-Attention & KV-Caching",
        "domain": "Deep Learning / ML",
        "badge": "Trending",
        "starter": "Explain the time and memory complexity of the Scaled Dot-Product Attention mechanism, and how FlashAttention optimizes GPU SRAM memory hierarchies.",
        "keywords": ["O(N^2)", "softmax", "tiling", "SRAM", "HBM", "tiling", "key-value cache", "memory bandwidth"]
    },
    {
        "id": "db_acid_isolation",
        "title": "MVCC & Repeatable Read Anomalies",
        "domain": "Database Engines",
        "badge": "Core CS",
        "starter": "How does Multi-Version Concurrency Control (MVCC) eliminate read-locks, and what specific anomaly separates Repeatable Read from Serializable isolation?",
        "keywords": ["write skew", "phantom read", "snapshot", "transaction ID", "undo log", "serializable", "locking"]
    },
    {
        "id": "os_virtual_memory",
        "title": "TLB Shootdowns & Page Faults",
        "domain": "Operating Systems",
        "badge": "Systems",
        "starter": "Walk through the hardware and kernel execution path when an instruction triggers a minor page fault versus a major page fault.",
        "keywords": ["TLB", "CR3", "page directory", "swap", "disk I/O", "interrupt", "page frame", "mmap"]
    },
    {
        "id": "tcp_congestion",
        "title": "TCP BBR vs Reno & Bufferbloat",
        "domain": "Computer Networks",
        "badge": "Core CS",
        "starter": "Why does loss-based congestion control (TCP Reno/Cubic) suffer from bufferbloat, and how does BBR measure bottleneck bandwidth and RTT independently?",
        "keywords": ["bufferbloat", "pacing rate", "min RTT", "bottleneck bandwidth", "drop tail", "queuing delay"]
    },
    {
        "id": "cache_coherence",
        "title": "MESI Protocol & False Sharing",
        "domain": "Computer Architecture",
        "badge": "Systems",
        "starter": "What is false sharing in multi-core CPUs, how does the MESI cache coherence protocol exacerbate it, and how do compilers/engineers mitigate it?",
        "keywords": ["cache line", "64 bytes", "invalid state", "bus snooping", "padding", "alignment", "exclusive"]
    }
]


def _evaluate_answer(subject, difficulty, question, answer, professor_id):
    """
    Evaluates student answer via LLM with deterministic fallback.
    Returns (score 0-100, composure_delta, feedback, next_prof, follow_up_q).
    """
    cleaned = (answer or "").strip()
    words = len(cleaned.split())

    # Fallback deterministic evaluation
    if words < 6:
        score = 25
        delta = -25
        feedback = "Candidate gave a virtually blank or trivial response. The tribunal looks profoundly unimpressed."
    elif words < 18:
        score = 50
        delta = -15
        feedback = "Superficial answer. Touched on buzzwords without explaining the core mechanics or invariant."
    elif words < 45:
        score = 75
        delta = +2
        feedback = "Decent explanation with sound fundamentals, but missed crucial edge-case trade-offs."
    else:
        score = 90
        delta = +6
        feedback = "Robust defense! Clear structural depth, mentioned trade-offs, and handled nuances properly."

    # Bonus points if technical keywords matched
    matched_topic = next((t for t in CURATED_TOPICS if t["title"] == subject or t["domain"] in subject), None)
    if matched_topic:
        hits = [kw for kw in matched_topic["keywords"] if kw.lower() in cleaned.lower()]
        if len(hits) >= 2:
            score = min(100, score + 10)
            delta = min(+10, delta + 4)
            feedback += f" Strong mention of core mechanics: {', '.join(hits[:3])}."

    # Try LLM enhancement
    prompt = (
        f"You are evaluating a student's answer in a high-stakes technical oral exam (viva defense).\n"
        f"Subject: {subject}\n"
        f"Difficulty: {difficulty}\n"
        f"Question: {question}\n"
        f"Interrogating Professor: {professor_id}\n"
        f"Student's Answer: {cleaned}\n\n"
        "Return a strictly valid JSON object with:\n"
        "{\n"
        '  "score": <integer 0 to 100>,\n'
        '  "composure_delta": <integer -30 to +10>,\n'
        '  "feedback": "<concise 2-sentence professor commentary in character>",\n'
        '  "next_professor_id": "<rigor | vance | chaos>",\n'
        '  "follow_up_question": "<sharp 1-sentence probing follow-up or challenge for next round>"\n'
        "}"
    )

    try:
        raw_text = LLMClient.ask(prompt, system_instruction="You are a rigorous engineering faculty panel. Respond only with JSON.")
        if raw_text:
            cleaned_json = raw_text.strip()
            if cleaned_json.startswith("```json"):
                cleaned_json = cleaned_json[7:]
            if cleaned_json.startswith("```"):
                cleaned_json = cleaned_json[3:]
            if cleaned_json.endswith("```"):
                cleaned_json = cleaned_json[:-3]
            data = json.loads(cleaned_json.strip())
            score = max(0, min(100, int(data.get("score", score))))
            delta = max(-35, min(15, int(data.get("composure_delta", delta))))
            feedback = str(data.get("feedback", feedback))
            next_prof = str(data.get("next_professor_id", "vance"))
            follow_up = str(data.get("follow_up_question", ""))
            return score, delta, feedback, next_prof, follow_up
    except Exception:
        pass

    # Deterministic next professor and question
    remaining_profs = [p["id"] for p in PROFESSORS if p["id"] != professor_id]
    next_prof = random.choice(remaining_profs)
    
    follow_ups = {
        "rigor": f"Under what mathematical boundary condition does your assumption break down?",
        "vance": f"What happens when the secondary replica has network latency spike to 400ms during this operation?",
        "chaos": f"What if a concurrent thread writes to that exact memory location right before this executes?"
    }
    follow_up = follow_ups.get(next_prof, "How do you guarantee fault-tolerance under catastrophic partial failure?")
    return score, delta, feedback, next_prof, follow_up


@hotseat_bp.route("/topics", methods=["GET"])
def list_topics():
    """Returns curated topics and any active syllabus subjects from DB."""
    topics = list(CURATED_TOPICS)

    # Pull syllabus subjects if available
    try:
        from api.domain.syllabus import Subject
        db = SessionLocal()
        subjects = db.query(Subject).all()
        for s in subjects:
            topics.append({
                "id": f"syllabus_{s.id}",
                "title": s.name,
                "domain": "Semester Course",
                "badge": f"{len(s.topics or [])} Topics",
                "starter": f"Provide a complete architectural synthesis of the fundamental principles of {s.name}.",
                "keywords": [t.title for t in (s.topics or [])[:6]]
            })
        db.close()
    except Exception:
        pass

    return jsonify({"topics": topics, "professors": PROFESSORS})


@hotseat_bp.route("/session/start", methods=["POST"])
def start_session():
    data = request.get_json() or {}
    subject = data.get("subject", "Distributed Systems & Raft")
    difficulty = data.get("difficulty", "masters")

    rounds_map = {"undergraduate": 3, "masters": 4, "phd": 5}
    total_rounds = rounds_map.get(difficulty, 4)

    # Pick starting professor and question
    topic_obj = next((t for t in CURATED_TOPICS if t["title"] == subject), None)
    starter_q = topic_obj["starter"] if topic_obj else f"Explain the core internal mechanisms and performance trade-offs of {subject}."
    start_prof = random.choice(PROFESSORS)["id"]

    initial_turn = {
        "turn": 1,
        "professor_id": start_prof,
        "question": starter_q,
        "answer": None,
        "score": None,
        "composure_delta": 0,
        "feedback": None,
    }

    db = SessionLocal()
    session = HotSeatSession(
        subject=subject,
        difficulty=difficulty,
        status="active",
        composure=100,
        questions_total=total_rounds,
        current_turn=1,
        turns_data=json.dumps([initial_turn]),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    result = session.to_dict()
    db.close()

    return jsonify({"session": result, "professors": PROFESSORS}), 201


@hotseat_bp.route("/session/<int:session_id>/answer", methods=["POST"])
def answer_turn(session_id):
    data = request.get_json() or {}
    answer = (data.get("answer") or "").strip()

    db = SessionLocal()
    session = db.query(HotSeatSession).filter_by(id=session_id).first()
    if not session:
        db.close()
        return jsonify({"error": "Session not found"}), 404

    if session.status != "active":
        result = session.to_dict()
        db.close()
        return jsonify({"error": "Session is already finished", "session": result}), 400

    try:
        turns = json.loads(session.turns_data or "[]")
    except Exception:
        turns = []

    if not turns:
        db.close()
        return jsonify({"error": "No turns in session"}), 400

    current = turns[-1]
    current["answer"] = answer

    # Evaluate answer
    score, delta, feedback, next_prof, follow_up = _evaluate_answer(
        session.subject, session.difficulty, current["question"], answer, current["professor_id"]
    )

    current["score"] = score
    current["composure_delta"] = delta
    current["feedback"] = feedback

    # Update composure
    new_composure = max(0, min(100, session.composure + delta))
    session.composure = new_composure

    # Check for failure (Roasted)
    if new_composure <= 0:
        session.status = "roasted"
        session.final_verdict = "Roasted by Faculty Tribunal"
        session.xp_awarded = 25  # pity XP for trying
        session.feedback_summary = "Composure collapsed under intense grilling. Faculty dismissed the candidate."
        session.completed_at = now_ist()
    elif session.current_turn >= session.questions_total:
        # Final round passed!
        session.status = "completed"
        session.completed_at = now_ist()
        avg_score = sum((t.get("score") or 0) for t in turns) / len(turns)
        
        if avg_score >= 90 and new_composure >= 70:
            session.final_verdict = "Summa Cum Laude"
            session.xp_awarded = 200 + (50 if session.difficulty == "phd" else 25)
            session.feedback_summary = "Outstanding technical defense! The faculty unanimously passes the candidate with highest honors."
        elif avg_score >= 75 and new_composure >= 40:
            session.final_verdict = "Magna Cum Laude"
            session.xp_awarded = 150
            session.feedback_summary = "Command of theory and systems stood up to interrogation. Passed with distinction."
        else:
            session.final_verdict = "Defense Passed"
            session.xp_awarded = 100
            session.feedback_summary = "Candidate survived the defense. Minor revisions advised on edge-case handling."
    else:
        # Advance to next turn
        session.current_turn += 1
        next_turn = {
            "turn": session.current_turn,
            "professor_id": next_prof,
            "question": follow_up or "How does this scale when system capacity is throttled by 90%?",
            "answer": None,
            "score": None,
            "composure_delta": 0,
            "feedback": None,
        }
        turns.append(next_turn)

    session.turns_data = json.dumps(turns)
    db.commit()
    db.refresh(session)
    result = session.to_dict()
    db.close()

    return jsonify({"session": result, "professors": PROFESSORS})


@hotseat_bp.route("/history", methods=["GET"])
def get_history():
    db = SessionLocal()
    sessions = db.query(HotSeatSession).order_by(HotSeatSession.id.desc()).limit(20).all()
    results = [s.to_dict() for s in sessions]
    
    total = len(results)
    completed = [s for s in results if s["status"] == "completed"]
    avg_composure = int(sum(s["composure"] for s in completed) / max(1, len(completed))) if completed else 0
    total_xp = sum(s["xp_awarded"] for s in results)
    best_verdict = next((s["final_verdict"] for s in completed if s["final_verdict"] == "Summa Cum Laude"), 
                        completed[0]["final_verdict"] if completed else "None")

    db.close()
    return jsonify({
        "sessions": results,
        "stats": {
            "total_defenses": total,
            "passed": len(completed),
            "avg_composure": avg_composure,
            "total_xp": total_xp,
            "best_verdict": best_verdict
        }
    })
