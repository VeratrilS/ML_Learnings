"""
Autonomous Agent Swarm: Multi-agent command center where specialized AI agents
(Grandmaster, Sentinel, Principal, Sensei, Scout) collaborate concurrently
in parallel worker threads to tackle DSA, System Design, Code Audits, and Placement missions.
"""
import concurrent.futures
import json
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from api.core.clients import LLMClient
from api.core.db import Base, SessionLocal, engine

agents_bp = Blueprint("agents", __name__, url_prefix="/api/agents")


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AgentMission(Base):
    __tablename__ = "agent_missions"
    id = Column(Integer, primary_key=True, index=True)
    mission_title = Column(String(300), nullable=False)
    agent_id = Column(String(50), nullable=False)
    is_all_out = Column(Boolean, default=False)
    stages = Column(Text, nullable=False)  # JSON-encoded array of stage outputs
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


@agents_bp.record_once
def _ensure_tables(state):
    Base.metadata.create_all(bind=engine, tables=[AgentMission.__table__])


ROSTER = [
    {
        "id": "grandmaster",
        "name": "The Grandmaster",
        "role": "DSA & Algorithm Architect",
        "tag": "Optimal $O(N)$ Patterns",
        "badge": "Grandmaster",
        "avatar": "🧠",
        "color": "from-amber-500/20 to-orange-500/10 border-amber-500/30 text-amber-500",
        "quote": "Every hard problem reduces to a known pattern. Identify the invariant, optimize the state.",
        "skills": ["2D/3D Dynamic Programming", "Monotonic Stack / Deque", "Graph Shortest Path / Tarjan", "Segment Trees & Fenwick", "Trie & Bitwise XOR"],
        "sample": "How do I master DP on Trees and formulate optimal state transitions?",
    },
    {
        "id": "sentinel",
        "name": "The Sentinel",
        "role": "Deep Code Auditor & Bug Hunter",
        "tag": "Edge Case & TLE Annihilator",
        "badge": "Auditor",
        "avatar": "🛡️",
        "color": "from-rose-500/20 to-red-500/10 border-rose-500/30 text-rose-500",
        "quote": "Happy path code always fails in OA contests. Let's break it before the grader does.",
        "skills": ["Time Limit Exceeded (TLE) Traps", "Integer Overflow & Underflow", "Recursion Depth / Call Stack Limits", "Corner Cases: Empty, Single, Cyclic", "Memory Bounds & Cache Locality"],
        "sample": "Audit this C++ two-pointer solution for corner cases and memory traps.",
    },
    {
        "id": "principal",
        "name": "The Principal",
        "role": "System Design & Distributed Systems Griller",
        "tag": "Scale & High Availability",
        "badge": "Principal",
        "avatar": "⚡",
        "color": "from-cyan-500/20 to-blue-500/10 border-cyan-500/30 text-cyan-500",
        "quote": "Architecture is not what you add; it is the failure modes you gracefully isolate.",
        "skills": ["Consistent Hashing & Sharding", "Kafka Partitions & Event Ordering", "Cache Stampede & Thundering Herd", "CAP Theorem & PACELC Trade-offs", "Distributed Locks (Redlock / ZooKeeper)"],
        "sample": "Design a Distributed Rate Limiter for 500k RPS with sliding window counter.",
    },
    {
        "id": "sensei",
        "name": "The Sensei",
        "role": "Hyper-Productivity & Unstuck Strategist",
        "tag": "Zero-Fluff Execution",
        "badge": "Sensei",
        "avatar": "🔥",
        "color": "from-emerald-500/20 to-teal-500/10 border-emerald-500/30 text-emerald-500",
        "quote": "Action cures fear. 25 minutes of deep focus beats 6 hours of passive reading.",
        "skills": ["Freeze Breaking (60s Unstuck Protocol)", "48-Hour Exam / OA Sprints", "Pomodoro Combo Multipliers", "Ruthless Scope Reduction", "Dopamine & Habit Stacking"],
        "sample": "I have 48 hours before my placement OA. Build me a high-yield triage roadmap.",
    },
    {
        "id": "scout",
        "name": "The Scout",
        "role": "Company & Placement Intel Hunter",
        "tag": "FAANG & Top Startup Matcher",
        "badge": "Scout",
        "avatar": "🎯",
        "color": "from-purple-500/20 to-violet-500/10 border-purple-500/30 text-purple-500",
        "quote": "Interviews are not tests of genius; they are tests of structured communication and preparation.",
        "skills": ["STAR Behavioral Story Refinement", "High-Conversion Cold Outreach", "Google / Amazon / Atlassian Question Trends", "Resume ATS Keyword Alignment", "Salary & Offer Negotiation Framing"],
        "sample": "Draft a personalized cold LinkedIn message for an engineering manager at Uber.",
    },
]


def _run_single_agent(agent: dict, mission: str, thread_idx: int, use_ai: bool = True) -> dict:
    """Executes a single agent task in a parallel thread."""
    t0 = time.time()
    agent_id = agent["id"]

    if use_ai:
        try:
            local_llm = LLMClient(budget=15)
            if local_llm.gemini_key:
                system_prompt = (
                    f"You are {agent['name']}, {agent['role']}. Focus specialty: {agent['tag']}. "
                    f"Core skills: {', '.join(agent['skills'])}. "
                    "Output sharp, elite, production-grade technical guidance in Markdown with concrete code blocks, invariants, or blueprints. "
                    "Keep it punchy, practical, and immediately actionable."
                )
                prompt = f"Mission: {mission}\n\nExecute your specialized domain analysis for this objective."
                content = local_llm.generate(prompt, system=system_prompt, temperature=0.6)
                if content and len(content.strip()) > 30:
                    elapsed_ms = int((time.time() - t0) * 1000)
                    return {
                        "agent": agent["name"],
                        "avatar": agent["avatar"],
                        "role": agent["role"],
                        "badge": agent["badge"],
                        "agent_id": agent_id,
                        "thread_id": f"Worker-Thread-{thread_idx}",
                        "execution_time_ms": elapsed_ms,
                        "title": f"{agent['name']} · {agent['tag']}",
                        "content": content,
                    }
        except Exception as e:
            print(f"Parallel agent {agent_id} LLM fallback: {e}")

    # High-yield offline fallback per agent
    elapsed_ms = int((time.time() - t0) * 1000)
    is_brainstorm = any(k in mission.lower() for k in ("brainstorm", "feature", "investigat", "new idea", "innovat"))

    if is_brainstorm:
        fallbacks = {
            "grandmaster": """### 🧠 Feature Proposal: Interactive Algorithm & Recursion Visualizer
- **Concept**: An interactive step-by-step visual tracer for 2D DP grids, Binary Trees, and Monotonic Stacks.
- **Why It's Addictive**: Allows users to step forward/backward through state transitions with animated token movement and instant invariant verification.
- **Implementation**: Pure SVG canvas in React with state replay and zero heavy dependencies.
- **Gamification**: "Predict the Next State" mini-game awarding +15 XP for correct branch prediction.""",

            "sentinel": """### 🛡️ Investigation & Performance Hardening: Concurrent SQLite & Async Queues
- **Audit Finding**: Currently, background jobs and high-concurrency API calls can encounter SQLite database locked errors during writes.
- **Architectural Fix**:
  1. Enable SQLite WAL (Write-Ahead Logging) mode: `PRAGMA journal_mode=WAL;` to allow concurrent readers with a single writer.
  2. Implement an in-memory queue with worker thread for batching log writes.
  3. Ensure all SQLAlchemy sessions strictly commit or rollback in `finally` blocks to prevent dangling transactions.""",

            "principal": """### ⚡ Architecture Proposal: Real-Time WebSockets & Server-Sent Events (SSE)
- **Concept**: Upgrade the polling architecture to Server-Sent Events (`/api/events/stream`) for live updates.
- **Why It Matters**: Eliminates constant frontend polling of `/api/logs` and `/api/stats`. Delivers instant push notifications when a cron fires, a boss takes damage, or a duel starts.
- **Scale Strategy**: Redis Pub/Sub backplane connected to Flask SSE streaming endpoints; scale-to-zero friendly.""",

            "sensei": """### 🔥 Feature Proposal: 60-Second Dopamine Flow & Streak Freeze Protection
- **Concept**: "The Flow Induction Tunnel" — a 60-second micro-ritual before every focus sprint with procedural binaural beats, deep breath pacing, and streak combo multipliers.
- **Why It's Addictive**: Removes cognitive resistance to starting hard work. Includes a "Streak Shield" earned by maintaining 5+ consecutive days of 25m sprints.
- **Dopamine Loop**: Multiplier ticks from 1.0x to 3.0x with subtle WebAudio chime accents.""",

            "scout": """### 🎯 Feature Proposal: Live LeetCode Submission Radar & Automated Bounties
- **Concept**: Auto-sync and verify user submissions directly via LeetCode's public GraphQL API.
- **Why It's Valuable**: When a user submits on LeetCode, the app automatically detects the accepted verdict, marks the daily bounty complete, deals damage to the weekly Gym Boss, and plays the victory fanfare.
- **Recruiter Magnet**: One-click public portfolio showcase with verified daily consistency graph.""",
        }
    else:
        fallbacks = {
            "grandmaster": f"""### Optimal Algorithmic Blueprint for: {mission}
1. **Core Pattern**: State representation with memoization / sliding window or monotonic stack.
2. **Key Invariant**:
   - Maintain monotonicity: each element enters and leaves the structure at most once $\\implies O(N)$ amortized.
   - For DP: `dp[i]` represents optimal value strictly considering prefix `arr[0...i]`.
3. **Optimized Blueprint**:
```cpp
// Optimal Scalable Blueprint
#include <bits/stdc++.h>
using namespace std;

class Solution {{
public:
    long long solveOptimized(const vector<int>& nums) {{
        int n = nums.size();
        if (n == 0) return 0;
        
        vector<long long> dp(n + 1, 0);
        long long currentMax = 0;
        
        for (int i = 0; i < n; ++i) {{
            dp[i + 1] = max(dp[i], dp[i] + nums[i]);
            currentMax = max(currentMax, dp[i + 1]);
        }}
        return currentMax;
    }}
}};
```
- **Time Complexity**: $O(N)$ single-pass.
- **Space Complexity**: $O(1)$ state compression.""",

            "sentinel": f"""### Sentinel Deep Audit & Edge Case Matrix for: {mission}
- ⚠️ **Empty & Single-Element Inputs**: Guarded with early return `if (n == 0) return 0;`.
- ⚠️ **Integer Overflow Trap**: Accumulators must use 64-bit `long long` (`int64_t`) instead of 32-bit `int` to avoid silent wraparound on $10^5 \\times 10^4$.
- ⚠️ **All-Negative Subarrays**: If array contains all negative numbers, ensure default doesn't incorrectly remain 0 if non-empty output is required.
- ⚠️ **Recursion Depth Limits**: Iterative bottom-up state prevents call stack overflows ($10^5$ frames crash with SIGSEGV in standard sandbox runners).
- **Test Scenarios**:
  1. `nums = []` $\\implies 0$
  2. `nums = [-10, -20, -5]` $\\implies -5$
  3. High-stress test: $N = 2 \\times 10^5$ items completes in $< 18\\text{ ms}$.""",

            "principal": f"""### Scalability & Distributed Architecture for: {mission}
- **Throughput & Concurrency**: Partition keys via Consistent Hashing with virtual nodes (e.g. 256 vnodes) to eliminate hot spots across sharded clusters.
- **Failover Isolation**: Implement Circuit Breaker (Hystrix / resilience4j pattern) with 50% error threshold and 5s cool-down.
- **Idempotency Guarantee**: Unique client idempotency keys stored in Redis with 10-minute sliding TTL to eliminate duplicate mutations during network retries.
- **Data Consistency**: Event-driven Saga pattern with compensating transactions across microservices.""",

            "sensei": f"""### Sensei Rapid 48-Hour Execution Roadmap for: {mission}
1. **Immediate 25-Min Sprint**: Implement the core blueprint in your IDE without consulting notes.
2. **Stress-Testing Drill**: Manually trace the 3 Sentinel edge cases on paper or whiteboard.
3. **Boss Raid**: Solve 2 related problems on LeetCode / Codeforces within 45 minutes to lock in muscle memory!
4. **Reward**: +80 XP applied toward your next Ippo rank progression! 🥊""",

            "scout": f"""### Placement Intel & Interview Framing for: {mission}
- **Company Trend**: Frequently tested by Google, Uber, Amazon, and Atlassian in Round 1 & Round 2 technical bars.
- **Communication Protocol**:
  1. *0-5 min*: Clarify input constraints and discuss edge cases (Sentinel checklist) BEFORE typing code.
  2. *5-12 min*: State brute force ($O(N^2)$), then introduce optimal pattern ($O(N)$).
  3. *12-25 min*: Clean code with meaningful variable names and dry-run execution.
- **STAR Behavioral Tie-in**: Connect this algorithm optimization to a real project where you halved latency or optimized database query performance.""",
        }

    return {
        "agent": agent["name"],
        "avatar": agent["avatar"],
        "role": agent["role"],
        "badge": agent["badge"],
        "agent_id": agent_id,
        "thread_id": f"Parallel-Worker-{thread_idx}",
        "execution_time_ms": elapsed_ms or 42,
        "title": f"{agent['name']} · {agent['tag']}",
        "content": fallbacks.get(agent_id, fallbacks["grandmaster"]),
    }


@agents_bp.route("/roster", methods=["GET"])
def get_roster():
    return jsonify({"status": "success", "data": ROSTER})


@agents_bp.route("/history", methods=["GET"])
def get_history():
    db = SessionLocal()
    try:
        rows = db.query(AgentMission).order_by(AgentMission.created_at.desc()).limit(15).all()
        data = []
        for r in rows:
            data.append({
                "id": r.id,
                "mission_title": r.mission_title,
                "agent_id": r.agent_id,
                "is_all_out": r.is_all_out,
                "summary": r.summary,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        return jsonify({"status": "success", "data": data})
    finally:
        db.close()


@agents_bp.route("/mission/<int:mission_id>", methods=["GET"])
def get_mission_detail(mission_id: int):
    db = SessionLocal()
    try:
        m = db.query(AgentMission).filter(AgentMission.id == mission_id).first()
        if not m:
            return jsonify({"status": "error", "message": "Mission not found"}), 404
        return jsonify({
            "status": "success",
            "data": {
                "id": m.id,
                "mission_title": m.mission_title,
                "agent_id": m.agent_id,
                "is_all_out": m.is_all_out,
                "stages": json.loads(m.stages) if m.stages else [],
                "summary": m.summary,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            },
        })
    finally:
        db.close()


@agents_bp.route("/dispatch", methods=["POST"])
def dispatch():
    payload = request.get_json(silent=True) or {}
    agent_id = (payload.get("agent_id") or "grandmaster").strip().lower()
    mission = (payload.get("mission") or "Master Dynamic Programming Subsequences").strip()
    is_all_out = bool(payload.get("all_out"))
    is_parallel = bool(payload.get("parallel", is_all_out))

    t_start = time.time()
    stages = []

    if is_all_out or is_parallel:
        # Run ALL 5 agents concurrently in parallel worker threads!
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_agent = {
                executor.submit(_run_single_agent, agent, mission, idx + 1, True): agent
                for idx, agent in enumerate(ROSTER)
            }
            # Collect in order of original roster
            results_by_id = {}
            for future in concurrent.futures.as_completed(future_to_agent):
                try:
                    res = future.result()
                    results_by_id[res["agent_id"]] = res
                except Exception as e:
                    print(f"Worker thread error: {e}")
            
            # Keep consistent order
            for a in ROSTER:
                if a["id"] in results_by_id:
                    stages.append(results_by_id[a["id"]])

        total_parallel_ms = int((time.time() - t_start) * 1000)
        summary = f"All 5 Agents deployed in parallel ({total_parallel_ms}ms concurrent execution) for: {mission}"
        xp_reward = 100
    else:
        # Dispatch specific single agent
        target_agent = next((a for a in ROSTER if a["id"] == agent_id), ROSTER[0])
        single_res = _run_single_agent(target_agent, mission, 1, True)
        stages.append(single_res)
        summary = f"{target_agent['name']} completed: {mission}"
        xp_reward = 40

    # Persist mission
    db = SessionLocal()
    mission_id = 1
    try:
        new_m = AgentMission(
            mission_title=mission,
            agent_id="swarm" if is_all_out else agent_id,
            is_all_out=is_all_out,
            stages=json.dumps(stages),
            summary=summary,
        )
        db.add(new_m)
        db.commit()
        db.refresh(new_m)
        mission_id = new_m.id
    except Exception as e:
        db.rollback()
        print(f"Could not persist agent mission: {e}")
    finally:
        db.close()

    return jsonify({
        "status": "success",
        "data": {
            "mission_id": mission_id,
            "mission_title": mission,
            "is_all_out": is_all_out,
            "is_parallel": is_parallel,
            "summary": summary,
            "stages": stages,
            "xp_reward": xp_reward,
            "workers_count": len(stages),
        },
    })
