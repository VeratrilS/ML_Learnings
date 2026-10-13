"""
Century Catalog & Beta Command Center — 100 High-Octane Engineering & Learning Features.
Organized across 7 Epic Domains: DSA & Code Combat, System Design, AI & ML,
Semester Academics, Bio-Hacking & Focus, Placement Warfare, and Dev Power Tools.
"""
from datetime import datetime, timezone
import json

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, DateTime, Integer, String, Text

from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine

century_bp = Blueprint("century", __name__, url_prefix="/api/century")


class CenturyFeatureState(Base):
    __tablename__ = "century_feature_states"

    id = Column(Integer, primary_key=True)
    feature_id = Column(String(80), unique=True, nullable=False)
    status = Column(String(40), nullable=False, default="unlocked")  # locked, unlocked, mastered
    usage_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "feature_id": self.feature_id,
            "status": self.status,
            "usage_count": self.usage_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
        }


Base.metadata.create_all(bind=engine, tables=[CenturyFeatureState.__table__], checkfirst=True)


# The 100 Curated Engineering & Learning Features
CENTURY_CATALOG = [
    # ---------------- 1. DSA & Algorithmic Combat (1-15) ----------------
    {"id": "ghost", "title": "Ghost Racer", "domain": "DSA & Combat", "icon": "Timer", "desc": "Speedrun algorithm muscle memory against AI & PB ghosts in real-time code races.", "xp": 100, "route": "#/ghost"},
    {"id": "arena", "title": "Code Duel Arena", "domain": "DSA & Combat", "icon": "Swords", "desc": "1v1 rapid-fire technical intuition & algorithm duels against AI bot rivals with live HP.", "xp": 120, "route": "#/arena"},
    {"id": "bounties", "title": "DSA Gacha & Bounties", "domain": "DSA & Combat", "icon": "Dices", "desc": "Daily bounty contracts and high-stakes mystery problem pulls with rarity tiers.", "xp": 90, "route": "#/bounties"},
    {"id": "complexity", "title": "Complexity Casino", "domain": "DSA & Combat", "icon": "Coins", "desc": "Rapid-fire Big-O prediction shootout with betting chips and streak multipliers.", "xp": 80, "route": "#/complexity"},
    {"id": "bughunt", "title": "Bug Hunt & Autopsy", "domain": "DSA & Combat", "icon": "Bug", "desc": "Forensic code autopsy of notorious real-world FAANG production crashes.", "xp": 110, "route": "#/bughunt"},
    {"id": "radar", "title": "Skill Radar & Elo", "domain": "DSA & Combat", "icon": "Compass", "desc": "Multi-topic DSA Elo ratings, weakest-topic recovery roadmaps, and contest performance predictor.", "xp": 75, "route": "#/radar"},
    {"id": "oa", "title": "OA Simulator", "domain": "DSA & Combat", "icon": "Hourglass", "desc": "Timed online assessment sets auto-verified via LeetCode and Codeforces.", "xp": 150, "route": "#/oa"},
    {"id": "drillmaster", "title": "SM-2 Spaced Repetition", "domain": "DSA & Combat", "icon": "RotateCcw", "desc": "SuperMemo SM-2 spaced repetition engine for fundamental CS concepts and algorithms.", "xp": 70, "route": "#/drillmaster"},
    {"id": "cards", "title": "Fundamentals Deck", "domain": "DSA & Combat", "icon": "Layers", "desc": "OS, DBMS, CN, OOP, and SQL active recall flashcard decks.", "xp": 60, "route": "#/cards"},
    {"id": "patterns", "title": "Algorithm Pattern Matrix", "domain": "DSA & Combat", "icon": "Grid", "desc": "Classification of the 14 essential DSA patterns (Sliding Window, Two Pointers, Monotonic Stack).", "xp": 50, "route": "#/patterns"},
    {"id": "invariant", "title": "Loop Invariant Prover", "domain": "DSA & Combat", "icon": "CheckCheck", "desc": "Step-by-step verification tool for initialization, maintenance, and termination invariants.", "xp": 65, "route": "#/invariant"},
    {"id": "recursion", "title": "Recursion Call Stack Tracer", "domain": "DSA & Combat", "icon": "GitFork", "desc": "Visual tree expansion of recursive state frames, base cases, and return bubbling.", "xp": 75, "route": "#/recursion"},
    {"id": "bitcraft", "title": "Bit Manipulation Sandbox", "domain": "DSA & Combat", "icon": "Binary", "desc": "Interactive bitwise registers, masks, XOR swap mechanics, and Kernighan optimizations.", "xp": 80, "route": "#/bitcraft"},
    {"id": "graphlab", "title": "Graph Traversal & Flow Lab", "domain": "DSA & Combat", "icon": "Share2", "desc": "Visual Dijkstra, Tarjan SCC, Kruskal MST, and topological sorting simulator.", "xp": 95, "route": "#/graphlab"},
    {"id": "sqlarena", "title": "SQL Query Duel", "domain": "DSA & Combat", "icon": "Database", "desc": "Speedrun complex SQL joins, window functions, and indexing strategies.", "xp": 85, "route": "#/sqlarena"},

    # ---------------- 2. System Design & Distributed Systems (16-30) ----------------
    {"id": "hotseat", "title": "The Hot Seat", "domain": "System Design", "icon": "GraduationCap", "desc": "High-stakes mock oral defense & viva against 3 AI professors with live Composure meter.", "xp": 200, "route": "#/hotseat"},
    {"id": "forge", "title": "Commit Forge", "domain": "System Design", "icon": "Hammer", "desc": "Alchemize code snippets & commits into collectible RPG weapons and relics with stat scaling.", "xp": 100, "route": "#/forge"},
    {"id": "cap", "title": "CAP Theorem Calculator", "domain": "System Design", "icon": "Triangle", "desc": "Explore Consistency vs Availability trade-offs under simulated network partitions.", "xp": 60, "route": "#/cap"},
    {"id": "sharding", "title": "Consistent Hashing Ring", "domain": "System Design", "icon": "CircleDot", "desc": "Virtual node distribution simulator for distributed database partitions and cache clusters.", "xp": 90, "route": "#/sharding"},
    {"id": "rate_limit", "title": "Rate Limiting Visualizer", "domain": "System Design", "icon": "Sliders", "desc": "Interactive Token Bucket, Leaky Bucket, and Sliding Window log algorithms.", "xp": 75, "route": "#/ratelimit"},
    {"id": "cache_sim", "title": "Cache Eviction Sandbox", "domain": "System Design", "icon": "HardDrive", "desc": "Simulate hit/miss rates across LRU, LFU, ARC, and 2Q eviction policies.", "xp": 80, "route": "#/cachesim"},
    {"id": "mq", "title": "Message Broker Simulator", "domain": "System Design", "icon": "Forward", "desc": "Kafka partitions, consumer groups, consumer lag, and RabbitMQ exchange fanouts.", "xp": 85, "route": "#/mq"},
    {"id": "outage", "title": "Production Chaos Monkey", "domain": "System Design", "icon": "Flame", "desc": "Random latency injection, disk filling, and database failover triage games.", "xp": 110, "route": "#/outage"},
    {"id": "paxos", "title": "Raft & Paxos State Machine", "domain": "System Design", "icon": "Cpu", "desc": "Step-by-step leader election and log replication across asymmetric partitions.", "xp": 120, "route": "#/paxos"},
    {"id": "loadbal", "title": "Load Balancing Shootout", "domain": "System Design", "icon": "GitPullRequest", "desc": "Least connections vs weighted round-robin under asymmetric server load.", "xp": 70, "route": "#/loadbal"},
    {"id": "circuit", "title": "Circuit Breaker Engine", "domain": "System Design", "icon": "ZapOff", "desc": "Closed, Open, Half-Open state transition visualizer for distributed resilience.", "xp": 75, "route": "#/circuit"},
    {"id": "apispec", "title": "OpenAPI Contract Validator", "domain": "System Design", "icon": "FileCode", "desc": "Detect breaking changes in REST and gRPC schema definitions before deploying.", "xp": 65, "route": "#/apispec"},
    {"id": "cdn", "title": "CDN Edge Invalidation Lab", "domain": "System Design", "icon": "Globe", "desc": "TTL propagation, stale-while-revalidate, and edge cache warming simulations.", "xp": 70, "route": "#/cdn"},
    {"id": "idempotency", "title": "Idempotency Key Forge", "domain": "System Design", "icon": "Key", "desc": "Deduplicate network retries and payment gateway mutations with distributed locks.", "xp": 80, "route": "#/idempotency"},
    {"id": "concurrency", "title": "Mutex & Deadlock Chamber", "domain": "System Design", "icon": "Lock", "desc": "Detect Coffman deadlock conditions and test fine-grained lock striping.", "xp": 95, "route": "#/concurrency"},

    # ---------------- 3. Machine Learning & AI Engineering (31-45) ----------------
    {"id": "agents", "title": "Agents Swarm", "domain": "AI & ML", "icon": "Bot", "desc": "Parallel autonomous AI agents (Grandmaster, Sentinel, Sensei, Scout) execute multi-step plans.", "xp": 150, "route": "#/agents"},
    {"id": "tutor", "title": "AI Socratic Tutor", "domain": "AI & ML", "icon": "Sparkles", "desc": "Intelligent guiding tutor that asks probing hints without spoiling solutions.", "xp": 80, "route": "#/tutor"},
    {"id": "brief", "title": "AI Daily Brief", "domain": "AI & ML", "icon": "Sunrise", "desc": "Gemini-powered dynamic daily briefing that crafts your optimal productivity timeline.", "xp": 70, "route": "#/brief"},
    {"id": "pdfextract", "title": "PDF Topic & Card Extractor", "domain": "AI & ML", "icon": "FileUp", "desc": "Converts dense college lecture slide PDFs into structured syllabus topics and flashcards.", "xp": 85, "route": "#/pdfextract"},
    {"id": "attention", "title": "Attention Matrix Inspector", "domain": "AI & ML", "icon": "Eye", "desc": "Visual scaled dot-product QK^T / sqrt(d) attention weight heatmap and KV-cache simulator.", "xp": 100, "route": "#/attention"},
    {"id": "backprop", "title": "Autograd Graph Tracer", "domain": "AI & ML", "icon": "Network", "desc": "Step backwards through computational graph nodes calculating partial derivatives via chain rule.", "xp": 90, "route": "#/backprop"},
    {"id": "loss", "title": "Loss Surface Explorer", "domain": "AI & ML", "icon": "TrendingDown", "desc": "Explore convex and non-convex loss landscapes, saddle points, and momentum SGD paths.", "xp": 75, "route": "#/loss"},
    {"id": "embeddings", "title": "Vector Similarity Vault", "domain": "AI & ML", "icon": "Compass", "desc": "Cosine distance, Dot product, and Euclidean geometry in high-dimensional vector spaces.", "xp": 70, "route": "#/embeddings"},
    {"id": "tokenlab", "title": "Tokenizer BPE Visualizer", "domain": "AI & ML", "icon": "Scissors", "desc": "Watch Byte-Pair Encoding merge subwords, inspect vocabulary indices, and analyze token density.", "xp": 65, "route": "#/tokenlab"},
    {"id": "finetune", "title": "LoRA Parameter Calculator", "domain": "AI & ML", "icon": "SlidersHorizontal", "desc": "Calculate rank-r decomposition matrix savings vs full parameter fine-tuning.", "xp": 80, "route": "#/finetune"},
    {"id": "promptforge", "title": "Prompt Crafting Crucible", "domain": "AI & ML", "icon": "Terminal", "desc": "Test Chain-of-Thought, ReAct framing, and Few-Shot demonstrations with cost tracking.", "xp": 75, "route": "#/promptforge"},
    {"id": "evals", "title": "Model Evaluation Suite", "domain": "AI & ML", "icon": "CheckSquare", "desc": "Benchmark model completions against automated golden assertions and rubric metrics.", "xp": 85, "route": "#/evals"},
    {"id": "rlhf", "title": "Preference Pair Arena", "domain": "AI & ML", "icon": "Scale", "desc": "Bradley-Terry reward modeling simulator for direct preference optimization (DPO).", "xp": 90, "route": "#/rlhf"},
    {"id": "quant", "title": "VRAM & Quantization Calc", "domain": "AI & ML", "icon": "HardDrive", "desc": "Estimate GPU memory footprint across FP16, INT8, INT4, and KV-cache overhead.", "xp": 60, "route": "#/quant"},
    {"id": "rag", "title": "RAG Chunking Sandbox", "domain": "AI & ML", "icon": "FileSearch", "desc": "Evaluate fixed vs semantic chunking strategies, overlapping windows, and BM25 hybrid reranking.", "xp": 95, "route": "#/rag"},

    # ---------------- 4. Semester 7 & College Academics (46-60) ----------------
    {"id": "study", "title": "Syllabus Mastery Tracker", "domain": "Academics", "icon": "BookOpen", "desc": "End-sem preparation cockpit across modules, units, and active revision countdowns.", "xp": 100, "route": "#/study"},
    {"id": "syllabus_notes", "title": "Topic Notes Synthesizer", "domain": "Academics", "icon": "Sparkles", "desc": "One-click AI revision blueprint generation for any syllabus topic with formulas and traps.", "xp": 80, "route": "#/study"},
    {"id": "vault", "title": "Course Materials Vault", "domain": "Academics", "icon": "Archive", "desc": "Central organized repository for lecture slides, cheatsheets, labs, and exam archives.", "xp": 70, "route": "#/study"},
    {"id": "gpa", "title": "Target GPA Calculator", "domain": "Academics", "icon": "Percent", "desc": "Calculate exact marks required in upcoming end-semester theory and practicals to hit goal GPA.", "xp": 50, "route": "#/gpa"},
    {"id": "attendance", "title": "Attendance Bunk Runway", "domain": "Academics", "icon": "CalendarCheck", "desc": "Calculates exact safe bunk allowance to strictly maintain the 75% or 80% mandatory threshold.", "xp": 50, "route": "#/attendance"},
    {"id": "pyq", "title": "PYQ Frequency Analyzer", "domain": "Academics", "icon": "TrendingUp", "desc": "Identifies high-yield questions repeating across 5 years of semester examination papers.", "xp": 85, "route": "#/pyq"},
    {"id": "lab_records", "title": "Lab Practical Checklist", "domain": "Academics", "icon": "ClipboardList", "desc": "Weekly lab assignments, observation sign-offs, and viva voice quick prompts.", "xp": 65, "route": "#/labrecords"},
    {"id": "cheatsheets", "title": "One-Page Formula Sheets", "domain": "Academics", "icon": "FileText", "desc": "Curated distillation sheets for fast recall 30 minutes before entering the exam hall.", "xp": 60, "route": "#/cheatsheets"},
    {"id": "formulae", "title": "Math & Proofs Ledger", "domain": "Academics", "icon": "Divide", "desc": "Asymptotic bounds, probabilistic proofs, matrix theorems, and recurrence tables.", "xp": 70, "route": "#/formulae"},
    {"id": "vivabank", "title": "500+ Viva Question Bank", "domain": "Academics", "icon": "HelpCircle", "desc": "Comprehensive question-and-answer library covering typical professor defense probes.", "xp": 90, "route": "#/vivabank"},
    {"id": "capstone", "title": "Major Project Milestones", "domain": "Academics", "icon": "FolderGit2", "desc": "Track SRS document, system architecture design, interim review, and final viva deliverable.", "xp": 110, "route": "#/capstone"},
    {"id": "rubric", "title": "Exam Evaluation Rubric", "domain": "Academics", "icon": "Award", "desc": "Understand question paper blueprint: 2-mark definitions vs 16-mark derivations.", "xp": 45, "route": "#/rubric"},
    {"id": "citation", "title": "IEEE Citation Formatter", "domain": "Academics", "icon": "Quote", "desc": "Format research references effortlessly into strict IEEE, ACM, or APA standards.", "xp": 40, "route": "#/citation"},
    {"id": "similarity", "title": "Code Plagiarism Heuristic", "domain": "Academics", "icon": "Fingerprint", "desc": "Tokenized AST structure comparison to verify original implementation before submission.", "xp": 75, "route": "#/similarity"},
    {"id": "professor_faq", "title": "Viva Defense Survival Guide", "domain": "Academics", "icon": "ShieldCheck", "desc": "De-escalation tactics, answering frameworks, and handling trick questions with poise.", "xp": 80, "route": "#/survival"},

    # ---------------- 5. Focus, Bio-Hacking & Momentum (61-75) ----------------
    {"id": "speedrun", "title": "Focus Speedrun", "domain": "Bio-Hacking", "icon": "Flame", "desc": "High-adrenaline focus time trials with combo XP multipliers, WebAudio bells, and Gym boss damage.", "xp": 90, "route": "#/speedrun"},
    {"id": "dempsey", "title": "Dempsey Roll", "domain": "Bio-Hacking", "icon": "Zap", "desc": "Momentum combo engine: close your 4 daily training habits to unleash 24h 2x XP Fever Mode.", "xp": 120, "route": "#/dempsey"},
    {"id": "gym", "title": "The Gym & Boss Battles", "domain": "Bio-Hacking", "icon": "Dumbbell", "desc": "Three daily rings, weekly Ippo boss fights, daily quests, and personal records.", "xp": 100, "route": "#/gym"},
    {"id": "habits", "title": "Body Habits Tracker", "domain": "Bio-Hacking", "icon": "HeartPulse", "desc": "Sleep, water, exercise tracking with a consolidated daily body score.", "xp": 60, "route": "#/habits"},
    {"id": "lofi", "title": "Neural Lo-Fi Studio", "domain": "Bio-Hacking", "icon": "Headphones", "desc": "Generative WebAudio soundscapes (Binaural Alpha, Rain, Cyberpunk Drone, Mechanical ASMR).", "xp": 70, "route": "#/lofi"},
    {"id": "pomodoro", "title": "Adaptive Flow Timer", "domain": "Bio-Hacking", "icon": "Clock", "desc": "Dynamically extends focus blocks when biometric and keyboard velocity indicate flow state.", "xp": 65, "route": "#/pomodoro"},
    {"id": "eye_health", "title": "20-20-20 Vision Sentry", "domain": "Bio-Hacking", "icon": "EyeOff", "desc": "Subtle visual chime every 20 minutes to gaze 20 feet away and prevent optic fatigue.", "xp": 40, "route": "#/eyehealth"},
    {"id": "caffeine", "title": "Caffeine Half-Life Curve", "domain": "Bio-Hacking", "icon": "Coffee", "desc": "Models metabolic plasma caffeine decay to ensure sleep architecture is protected.", "xp": 50, "route": "#/caffeine"},
    {"id": "breath", "title": "Box Breathing Pacer", "domain": "Bio-Hacking", "icon": "Wind", "desc": "4-4-4-4 autonomic nervous system down-regulation pacer before tests or interviews.", "xp": 45, "route": "#/breath"},
    {"id": "dopamine", "title": "Dopamine Friction Wall", "domain": "Bio-Hacking", "icon": "Barrier", "desc": "Add cognitive friction delays to context switching and doom-scrolling impulses.", "xp": 55, "route": "#/dopamine"},
    {"id": "ultradian", "title": "Ultradian Rhythm Planner", "domain": "Bio-Hacking", "icon": "Activity", "desc": "Maps 90-minute peak alertness cycles followed by 20-minute restorative dips.", "xp": 60, "route": "#/ultradian"},
    {"id": "circadian", "title": "Circadian Phase Aligner", "domain": "Bio-Hacking", "icon": "SunMedium", "desc": "Calculates optimal morning light exposure and evening blue-light curfew.", "xp": 50, "route": "#/circadian"},
    {"id": "hydration", "title": "Water Osmosis Ring", "domain": "Bio-Hacking", "icon": "Droplets", "desc": "Target water intake tracking indexed against study hours and caffeine intake.", "xp": 40, "route": "#/hydration"},
    {"id": "midday", "title": "Mid-Day Clarity Protocol", "domain": "Bio-Hacking", "icon": "Sun", "desc": "3-minute midday audit: What is the single highest leverage task remaining today?", "xp": 45, "route": "#/midday"},
    {"id": "shutdown", "title": "Shutdown Ritual", "domain": "Bio-Hacking", "icon": "Moon", "desc": "Evening close-the-day: mood, win, blocker, and tomorrow's top 3 intentions.", "xp": 60, "route": "#/shutdown"},

    # ---------------- 6. Placement Warfare & Career (76-90) ----------------
    {"id": "placements", "title": "Placement Pipeline", "domain": "Placement Warfare", "icon": "Briefcase", "desc": "Visual Kanban board tracking company applications from wishlist to technical rounds to offer.", "xp": 100, "route": "#/placements"},
    {"id": "interview", "title": "AI Interview Lab", "domain": "Placement Warfare", "icon": "MessagesSquare", "desc": "AI mock interviewer across DSA, System Design, and Behavioral rounds with instant rubric score.", "xp": 130, "route": "#/interview"},
    {"id": "mistakes", "title": "Mistake Journal", "domain": "Placement Warfare", "icon": "Bug", "desc": "Log code bugs, logic flaws, and contest slip-ups with automated tag extraction and checklists.", "xp": 80, "route": "#/mistakes"},
    {"id": "ats_scan", "title": "ATS Resume Scanner", "domain": "Placement Warfare", "icon": "FileCheck", "desc": "Analyzes tech stack keywords and bullet-point impact metrics against top job descriptions.", "xp": 90, "route": "#/atsscan"},
    {"id": "star_method", "title": "STAR Behavioral Architect", "domain": "Placement Warfare", "icon": "Star", "desc": "Structure Situation, Task, Action, and Result narratives for leadership and conflict prompts.", "xp": 85, "route": "#/star"},
    {"id": "compensation", "title": "Compensation & CTC Decoder", "domain": "Placement Warfare", "icon": "Banknote", "desc": "Break down Base pay, Joining bonus, ESOP vesting schedules, and post-tax in-hand earnings.", "xp": 70, "route": "#/compensation"},
    {"id": "referral", "title": "Cold Outreach Generator", "domain": "Placement Warfare", "icon": "Send", "desc": "Craft high-converting personalized LinkedIn and email referral messages for tech alumni.", "xp": 65, "route": "#/referral"},
    {"id": "blind75", "title": "Blind-75 Mastery Matrix", "domain": "Placement Warfare", "icon": "CheckCircle2", "desc": "The canonical 75 problems that cover all core patterns with confidence heatmaps.", "xp": 110, "route": "#/blind75"},
    {"id": "sys_rubric", "title": "Staff System Design Rubric", "domain": "Placement Warfare", "icon": "Layers", "desc": "Evaluation framework covering functional requirements, back-of-the-envelope math, and SPOFs.", "xp": 95, "route": "#/sysrubric"},
    {"id": "sprint30", "title": "30-Day Placement Sprint", "domain": "Placement Warfare", "icon": "Calendar", "desc": "Rigorous day-by-day structured curriculum to peak right before campus recruitment drives.", "xp": 120, "route": "#/sprint30"},
    {"id": "offer_eval", "title": "Offer Decision Matrix", "domain": "Placement Warfare", "icon": "Scale", "desc": "Weighted scoring model balancing compensation, growth velocity, engineering culture, and location.", "xp": 60, "route": "#/offereval"},
    {"id": "debrief", "title": "Interview Debrief Journal", "domain": "Placement Warfare", "icon": "Edit3", "desc": "Log questions asked immediately after walking out of an interview while memory is fresh.", "xp": 75, "route": "#/debrief"},
    {"id": "cramkit", "title": "24-Hour Final Cram Kit", "domain": "Placement Warfare", "icon": "Zap", "desc": "High-yield triage kit for the night before an unexpected surprise technical interview.", "xp": 80, "route": "#/cramkit"},
    {"id": "faang_playbook", "title": "Company Interview Playbooks", "domain": "Placement Warfare", "icon": "Shield", "desc": "Specific hiring bar, round structures, and preferred languages for Google, Amazon, and Microsoft.", "xp": 100, "route": "#/faang"},
    {"id": "portfolio", "title": "Verified Developer Portfolio", "domain": "Placement Warfare", "icon": "UserCheck", "desc": "Publicly showcase your verified solve records, focus hours, and engineering artifacts.", "xp": 90, "route": "#/portfolio"},

    # ---------------- 7. Developer Utilities & Productivity Power Tools (91-100) ----------------
    {"id": "capture", "title": "Quick Capture Everywhere", "domain": "Power Tools", "icon": "Zap", "desc": "Global hotkey 'C' to instantly log a problem, task, or note from anywhere without breaking flow.", "xp": 40, "route": "#/capture"},
    {"id": "weekly", "title": "Weekly Report & Recaps", "domain": "Power Tools", "icon": "Mail", "desc": "Sunday evening automated email audit of your solve velocity, focus minutes, and progress.", "xp": 70, "route": "#/weekly"},
    {"id": "pace", "title": "Compound Curve Predictor", "domain": "Power Tools", "icon": "TrendingUp", "desc": "Monte Carlo finish-date projection for your sheet roadmap based on real rolling velocity.", "xp": 65, "route": "#/pace"},
    {"id": "unstuck", "title": "Freeze Breaker Protocol", "domain": "Power Tools", "icon": "LifeBuoy", "desc": "A 60-second psychological intervention when mind goes completely blank mid-problem.", "xp": 50, "route": "#/unstuck"},
    {"id": "heatmap", "title": "Git Velocity Heatmap", "domain": "Power Tools", "icon": "CalendarRange", "desc": "GitHub-style daily contribution matrix visualizing consistency across code, study, and duels.", "xp": 60, "route": "#/heatmap"},
    {"id": "regex", "title": "Regex Playground & Cheats", "domain": "Power Tools", "icon": "Code", "desc": "Interactive regular expression tester with common patterns for log parsing and validation.", "xp": 55, "route": "#/regex"},
    {"id": "cron", "title": "Cron Schedule Synthesizer", "domain": "Power Tools", "icon": "Clock", "desc": "Generate and decode complex 5-field cron expressions with human-readable previews.", "xp": 45, "route": "#/cron"},
    {"id": "jwt", "title": "JWT & Base64 Inspector", "domain": "Power Tools", "icon": "KeyRound", "desc": "Decode JSON Web Tokens, inspect header claims, and verify expiry timestamps locally.", "xp": 50, "route": "#/jwt"},
    {"id": "json_diff", "title": "JSON / YAML Diff Tool", "domain": "Power Tools", "icon": "FileDiff", "desc": "Format, validate, and compare large JSON payloads with visual semantic diffing.", "xp": 55, "route": "#/jsondiff"},
    {"id": "century", "title": "Century Command Center", "domain": "Power Tools", "icon": "Trophy", "desc": "The unified cockpit tracking mastery, unlocks, and action launches for all 100 beta features.", "xp": 250, "route": "#/century"},
]


@century_bp.route("/catalog", methods=["GET"])
def get_catalog():
    db = SessionLocal()
    states = {s.feature_id: s.to_dict() for s in db.query(CenturyFeatureState).all()}
    db.close()

    result = []
    for f in CENTURY_CATALOG:
        st = states.get(f["id"], {"status": "unlocked", "usage_count": 0, "last_used_at": None})
        item = dict(f)
        item["status"] = st["status"]
        item["usage_count"] = st["usage_count"]
        item["last_used_at"] = st["last_used_at"]
        result.append(item)

    domains = sorted(list({f["domain"] for f in CENTURY_CATALOG}))
    total_count = len(result)
    used_count = sum(1 for r in result if r["usage_count"] > 0)
    mastered_count = sum(1 for r in result if r["status"] == "mastered")

    return jsonify({
        "catalog": result,
        "domains": domains,
        "stats": {
            "total_features": total_count,
            "used_features": used_count,
            "mastered_features": mastered_count,
            "completion_pct": round((used_count / max(1, total_count)) * 100, 1),
        }
    })


@century_bp.route("/action/<feature_id>", methods=["POST"])
def trigger_action(feature_id):
    feat = next((f for f in CENTURY_CATALOG if f["id"] == feature_id), None)
    if not feat:
        return jsonify({"error": "Feature not found"}), 404

    db = SessionLocal()
    st = db.query(CenturyFeatureState).filter_by(feature_id=feature_id).first()
    if not st:
        st = CenturyFeatureState(feature_id=feature_id, status="unlocked", usage_count=1, last_used_at=now_ist())
        db.add(st)
    else:
        st.usage_count += 1
        st.last_used_at = now_ist()
        if st.usage_count >= 5:
            st.status = "mastered"

    db.commit()
    res = st.to_dict()
    db.close()

    return jsonify({
        "success": True,
        "feature": feat,
        "state": res,
        "xp_awarded": feat["xp"],
        "message": f"Activated {feat['title']}! +{feat['xp']} XP."
    })
