"""
OA and Interview Preparation generator for Job Radar openings.

Complies strictly with Lead Architect guardrail (AGENT_CHAT.md 08:35 IST):
- Picks questions deterministically from our Striver A2Z set (api.domain.problem_bank.PROBLEMS)
  or repo-verified company sheet data (e.g. Apple).
- Labeled as "Common patterns for SWE OAs (Striver A2Z)" unless from a verified in-repo company sheet.
- 7-day taper plan (4 problems/day = 28 problems total), weighted toward Medium (~60%) and Hard (~30%).
- Absolutely no invented frequencies, percentages, or "asked X times" claims.
- Real LeetCode URLs (https://leetcode.com/problems/<slug>) and real problem IDs.

Blueprint: job_prep_bp
Endpoint: GET /api/jobs/<id>/prep
"""

import logging
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request

from api.core.db import SessionLocal
from api.domain.job_radar import JobOpportunity
from api.domain.problem_bank import PROBLEMS as STRIVER_PROBLEMS
from api.domain.sheets import SheetProblem

logger = logging.getLogger(__name__)

job_prep_bp = Blueprint("job_prep_bp", __name__, url_prefix="/api/jobs")

# Standard 7-day curriculum mapping to Striver topics
# Each day targets specific core topics from the problem bank
DAY_CURRICULUM = [
    {
        "day": 1,
        "focus": "Arrays, Two Pointers & Prefix Sums",
        "topics": ["Arrays"],
    },
    {
        "day": 2,
        "focus": "Binary Search & Sliding Window Strings",
        "topics": ["Binary Search", "Strings", "Sliding Window & Two Pointer"],
    },
    {
        "day": 3,
        "focus": "Linked Lists, Monotonic Stacks & Queues",
        "topics": ["Linked List", "Stack & Queue"],
    },
    {
        "day": 4,
        "focus": "Binary Trees, BSTs & Traversals",
        "topics": ["Binary Trees", "Binary Search Trees"],
    },
    {
        "day": 5,
        "focus": "Graphs, BFS/DFS & Shortest Paths",
        "topics": ["Graphs"],
    },
    {
        "day": 6,
        "focus": "Dynamic Programming & Optimization",
        "topics": ["Dynamic Programming"],
    },
    {
        "day": 7,
        "focus": "Heaps, Greedy Algorithms & Tries",
        "topics": ["Heaps", "Greedy", "Tries", "Bit Manipulation"],
    },
]


def _format_striver_problem(prob_tuple) -> Dict[str, Any]:
    # (title, slug, difficulty, topic, leetcode_id)
    title, slug, diff, topic, lc_id = prob_tuple
    diff_clean = diff.strip().capitalize()
    diff_num = 1 if diff_clean == "Easy" else (3 if diff_clean == "Hard" else 2)
    return {
        "frontend_id": lc_id,
        "title": title,
        "title_slug": slug,
        "url": f"https://leetcode.com/problems/{slug}",
        "difficulty": diff_clean,
        "difficulty_num": diff_num,
        "topic": topic,
    }


def build_striver_prep_plan(company_name: str) -> Dict[str, Any]:
    """
    Constructs a 7-day preparation plan (4 problems/day = 28 total)
    from our verified in-repo Striver A2Z problem bank.
    Weighted: Medium (~60%) and Hard (~30%), Easy (~10%).
    """
    days_plan: List[Dict[str, Any]] = []
    used_slugs = set()
    all_selected: List[Dict[str, Any]] = []

    # Map problem bank by topic
    problems_by_topic: Dict[str, List[Dict[str, Any]]] = {}
    for p in STRIVER_PROBLEMS:
        formatted = _format_striver_problem(p)
        t = formatted["topic"]
        problems_by_topic.setdefault(t, []).append(formatted)

    for day_def in DAY_CURRICULUM:
        day_num = day_def["day"]
        day_focus = day_def["focus"]
        day_topics = day_def["topics"]

        # Collect candidate problems for this day
        candidates: List[Dict[str, Any]] = []
        for t in day_topics:
            candidates.extend(problems_by_topic.get(t, []))

        # Filter out already used
        candidates = [c for c in candidates if c["title_slug"] not in used_slugs]

        # Prioritize 2-3 Mediums, 1-2 Hards, or 1 Easy if early day
        hards = [c for c in candidates if c["difficulty"] == "Hard"]
        mediums = [c for c in candidates if c["difficulty"] == "Medium"]
        easies = [c for c in candidates if c["difficulty"] == "Easy"]

        day_picks: List[Dict[str, Any]] = []

        # If day 1, include 1 Easy foundation
        if day_num == 1 and easies:
            day_picks.append(easies[0])

        # Pick Hard problem
        if hards and len(day_picks) < 4:
            day_picks.append(hards[0])

        # Fill with Mediums
        for m in mediums:
            if len(day_picks) >= 4:
                break
            if m not in day_picks:
                day_picks.append(m)

        # Fallback if needed to reach 4
        for c in candidates:
            if len(day_picks) >= 4:
                break
            if c not in day_picks:
                day_picks.append(c)

        # Mark as used
        for p in day_picks:
            used_slugs.add(p["title_slug"])
            all_selected.append(p)

        days_plan.append({
            "day": day_num,
            "focus": day_focus,
            "topics": day_topics,
            "problems": day_picks,
        })

    easy_count = sum(1 for p in all_selected if p["difficulty"] == "Easy")
    medium_count = sum(1 for p in all_selected if p["difficulty"] == "Medium")
    hard_count = sum(1 for p in all_selected if p["difficulty"] == "Hard")

    return {
        "company": company_name,
        "plan_days": 7,
        "problems_per_day": 4,
        "total_plan_problems": len(all_selected),
        "difficulty_breakdown": {
            "easy": easy_count,
            "medium": medium_count,
            "hard": hard_count,
        },
        "days": days_plan,
        "source": "Common patterns for SWE OAs (Striver A2Z)",
    }


def get_repo_company_problems(company: str) -> List[Dict[str, Any]]:
    """
    Check if the repo has an existing verified company sheet (e.g. Apple).
    """
    clean = company.strip().lower()
    if clean != "apple":
        return []

    db = SessionLocal()
    try:
        rows = (
            db.query(SheetProblem)
            .filter(SheetProblem.sheet == "apple")
            .order_by(SheetProblem.position)
            .limit(50)
            .all()
        )
        results = []
        for r in rows:
            results.append({
                "frontend_id": r.leetcode_id or r.position,
                "title": r.title,
                "title_slug": r.slug.split("/")[-1] if "/" in r.slug else r.slug,
                "url": f"https://leetcode.com/problems/{r.slug.split('/')[-1]}" if r.slug else "https://leetcode.com",
                "difficulty": r.difficulty or "Medium",
                "difficulty_num": 1 if r.difficulty == "Easy" else (3 if r.difficulty == "Hard" else 2),
                "topic": r.topics.split("|||")[0] if r.topics else "DSA",
            })
        return results
    except Exception as e:
        logger.debug("Failed querying repo company problems: %s", e)
        return []
    finally:
        db.close()


@job_prep_bp.route("/<int:job_id>/prep", methods=["GET"])
def get_job_prep_plan(job_id: int):
    """
    Returns an intensive 7-day interview taper plan (4 problems/day, Medium/Hard weighted)
    grounded in in-repo verified Striver A2Z and company problem sets.
    """
    db = SessionLocal()
    try:
        job = db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
        if not job:
            return jsonify({"error": f"Job {job_id} not found"}), 404

        company_name = job.company or "Tech Company"

        # Check in-repo company sheet first (e.g. Apple)
        repo_problems = get_repo_company_problems(company_name)
        if repo_problems and len(repo_problems) >= 28:
            # Build plan using company problems
            days_plan: List[Dict[str, Any]] = []
            for d in range(7):
                day_probs = repo_problems[d * 4 : (d + 1) * 4]
                days_plan.append({
                    "day": d + 1,
                    "focus": DAY_CURRICULUM[d]["focus"],
                    "topics": DAY_CURRICULUM[d]["topics"],
                    "problems": day_probs,
                })
            all_probs = repo_problems[:28]
            prep_plan = {
                "company": company_name,
                "plan_days": 7,
                "problems_per_day": 4,
                "total_plan_problems": len(all_probs),
                "difficulty_breakdown": {
                    "easy": sum(1 for p in all_probs if p.get("difficulty") == "Easy"),
                    "medium": sum(1 for p in all_probs if p.get("difficulty") == "Medium"),
                    "hard": sum(1 for p in all_probs if p.get("difficulty") == "Hard"),
                },
                "days": days_plan,
                "source": f"{company_name} Curated Company Sheet",
            }
        else:
            # Striver A2Z grounded plan
            prep_plan = build_striver_prep_plan(company_name)

        prep_plan["job_id"] = job.id
        prep_plan["role"] = job.role or "Software Engineer"
        prep_plan["portal_url"] = job.portal_url or job.url

        return jsonify(prep_plan), 200
    finally:
        db.close()
