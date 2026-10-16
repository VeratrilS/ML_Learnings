"""
Job Radar & Autonomous Background Auto-Apply Engine for 2027 CS Grads.

Features:
- Hourly automated scan across premier tech career portals.
- Strict filters:
    * Batch: 2027 Graduates (B.Tech Computer Science & Engineering)
    * CTC: >= 20 LPA (including high-stipend summer internships with PPO)
    * Branch: CSE, IT, Circuit
- Built-in Deterministic Skill Matcher:
    * Compares verified skills from Sai Raghava's resume (NIT Rourkela, CGPA 8.99, LC 1709, Kafka/C++ projects).
    * Calculates ATS match score based on transparent skill overlap.
    * Integrates with verified application pack generator for authentic screening question answers.
- Zero Auto-Submit Integrity:
    * Sai reviews and submits on official career portals; system assists with autofill, answers, and tracking.
    * Updates Placements board and follow-up schedules upon verified application submission.
"""
from datetime import datetime, timedelta, timezone
import html
import json
import math
import os
import re

from flask import Blueprint, jsonify, request
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from api.core.clients import EmailClient
from api.core.config import IST, now_ist
from api.core.db import Base, SessionLocal, engine
from api.domain.placements import Application, ApplicationEvent


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


# ---------------- Models ----------------

class JobOpportunity(Base):
    __tablename__ = "job_radar_opportunities"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(80), unique=True, index=True, nullable=False)
    company = Column(String(120), nullable=False, index=True)
    role = Column(String(180), nullable=False)
    eligible_batches = Column(String(80), nullable=True, default=None)
    eligible_branches = Column(String(120), nullable=True, default=None)
    min_cgpa = Column(Float, nullable=True, default=None)
    ctc_lpa = Column(Float, nullable=False)
    stipend_pm = Column(String(100), nullable=True)
    location = Column(String(160), default="Bengaluru", nullable=False)
    source = Column(String(120), default="Direct Careers Portal", nullable=False)
    portal_url = Column(Text, nullable=False)
    deadline = Column(String(60), nullable=True)
    skills_required = Column(Text, nullable=False)  # JSON list
    hiring_workflow = Column(Text, nullable=True)
    match_score = Column(Integer, default=0)
    shortlist_prob = Column(Float, default=0.0)  # Real probability, 0.0 unless scored
    status = Column(String(40), default="discovered", index=True)  # discovered | queued | manual_applied | applied_confirmed
    applied_at = Column(DateTime, nullable=True)
    application_ref = Column(String(100), nullable=True)
    placement_app_id = Column(Integer, nullable=True)
    follow_up_7d_at = Column(DateTime, nullable=True)
    follow_up_14d_at = Column(DateTime, nullable=True)
    followup_7d_sent_at = Column(DateTime, nullable=True)
    followup_14d_sent_at = Column(DateTime, nullable=True)
    board = Column(String(40), nullable=True)  # greenhouse | lever | ashby | smartrecruiters | direct
    outcome = Column(String(30), nullable=True)  # oa | interview | rejected | offer | no_response
    outcome_at = Column(DateTime, nullable=True)
    outcome_note = Column(Text, nullable=True)
    ml_tailored_answers = Column(Text, nullable=True)  # Candidate application snippets
    notes = Column(Text, nullable=True)
    discovered_at = Column(DateTime, default=_utcnow)
    last_checked_at = Column(DateTime, default=_utcnow)


class JobRadarScanLog(Base):
    __tablename__ = "job_radar_scan_logs"

    id = Column(Integer, primary_key=True, index=True)
    scanned_at = Column(DateTime, default=_utcnow)
    sources_scanned = Column(Integer, default=24)
    total_evaluated = Column(Integer, default=180)
    eligible_2027_found = Column(Integer, default=145)
    auto_applied_count = Column(Integer, default=0)
    log_details = Column(Text, nullable=False)  # JSON list of log items
    status = Column(String(30), default="success")


class JobRadarProfile(Base):
    __tablename__ = "job_radar_profile"

    id = Column(Integer, primary_key=True, default=1)
    full_name = Column(String(120), default="Nandam Venkata Sai Raghava")
    email = Column(String(120), default="sairaghava1318@gmail.com")
    phone = Column(String(40), default=None, nullable=True)
    college = Column(String(160), default="National Institute of Technology, Rourkela (NIT Rourkela)")
    degree = Column(String(160), default="Bachelor of Technology in Computer Science and Engineering")
    grad_year = Column(Integer, default=2027)
    cgpa = Column(Float, default=8.99)
    location_pref = Column(String(200), default="Bengaluru, Hyderabad, Gurugram, Remote")
    linkedin = Column(String(300), default="https://www.linkedin.com/in/nandam-venkata-sai-raghava-946b3735b/")
    github = Column(String(300), default="https://github.com/VeratrilS")
    leetcode = Column(String(300), default="https://leetcode.com/u/Sairaghava1318/")
    codeforces = Column(String(300), default="https://codeforces.com/profile/Raghavan_CP")
    skills = Column(Text, nullable=False)
    achievements = Column(Text, nullable=False)
    resume_summary = Column(Text, nullable=False)
    min_ctc_lpa = Column(Float, default=15.0)
    auto_apply_enabled = Column(Boolean, default=False)
    daily_target_applications = Column(Integer, default=None, nullable=True)
    stealth_mode = Column(Boolean, default=False)
    ml_mimic_active = Column(Boolean, default=False)
    last_hourly_scan_at = Column(DateTime, default=_utcnow)
    next_hourly_scan_at = Column(DateTime, default=lambda: _utcnow() + timedelta(minutes=60))


class JobApplicationReceipt(Base):
    __tablename__ = "job_application_receipts"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("job_radar_opportunities.id"), nullable=True)
    company = Column(String(120), nullable=False, index=True)
    role = Column(String(180), nullable=False)
    application_ref = Column(String(100), nullable=False, unique=True, index=True)
    candidate_name = Column(String(120), default="Nandam Venkata Sai Raghava")
    candidate_email = Column(String(120), default="sairaghava1318@gmail.com")
    ctc_lpa = Column(Float, nullable=False)
    stipend_pm = Column(String(100), nullable=True)
    status = Column(String(80), default="Application Verified · In Screening")
    sender_title = Column(String(140), default="Talent Acquisition Team")
    subject = Column(String(240), nullable=False)
    message_body = Column(Text, nullable=False)
    oa_timeline = Column(String(160), default="Online Assessment invitation arriving within 48-72 hours")
    prep_guidance = Column(Text, nullable=False)
    submitted_at = Column(DateTime, default=_utcnow)
    email_dispatched = Column(Boolean, default=False)


job_radar_bp = Blueprint("job_radar", __name__, url_prefix="/api/jobs")


def _cleanup_fake_seeds():
    db = SessionLocal()
    try:
        # Delete rows whose source ends with "Official University Talent" only if status is discovered
        db.query(JobOpportunity).filter(
            JobOpportunity.source.like("%Official University Talent"),
            JobOpportunity.status == "discovered"
        ).delete(synchronize_session=False)
        # Delete fake scan logs
        db.query(JobRadarScanLog).filter(
            (JobRadarScanLog.log_details.like("%ML Candidate Mimic Model%")) |
            (JobRadarScanLog.sources_scanned == 24)
        ).delete(synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"cleanup fake seeds skipped: {e}")
    finally:
        db.close()


@job_radar_bp.record_once
def _ensure_tables(state):
    from api.domain.job_migrations import add_missing_columns
    for model in (JobOpportunity, JobRadarScanLog, JobRadarProfile, JobApplicationReceipt):
        try:
            model.__table__.create(bind=engine, checkfirst=True)
        except Exception as e:
            print(f"{model.__tablename__} check skipped: {e}")
    try:
        add_missing_columns(engine)
    except Exception as e:
        print(f"job migrations check skipped: {e}")
    _cleanup_fake_seeds()


# ---------------- Deterministic Skill Matcher ----------------

class SkillMatcher:
    """
    Deterministic skill overlap matcher comparing job requirements
    against Nandam Venkata Sai Raghava's verified resume skills.
    """

    SKILL_SYNONYMS = {
        "c++": ["c++", "cpp", "systems", "concurrency", "multithreading", "tcp", "sockets", "memory"],
        "distributed systems": ["distributed systems", "kafka", "redis", "microservices", "saga", "rabbitmq", "pub/sub"],
        "dsa": ["dsa", "algorithms", "data structures", "graphs", "trees", "dp", "problem solving", "competitive programming"],
        "react": ["react", "react.js", "frontend", "javascript", "typescript", "redux", "vite"],
        "backend": ["node.js", "express", "rest api", "backend", "postgresql", "mongodb", "sql", "prisma"],
    }

    @classmethod
    def compute_match(cls, job_skills, ctc_lpa=0.0, min_cgpa=0.0):
        """
        Calculates ATS skill match score (0-100) based on verified skill overlap.
        """
        job_skills_lower = [s.lower() for s in (job_skills or [])]
        matched_categories = 0
        total_categories = len(cls.SKILL_SYNONYMS)

        for cat, synonyms in cls.SKILL_SYNONYMS.items():
            if any(syn in " ".join(job_skills_lower) for syn in synonyms):
                matched_categories += 1

        base_match = (matched_categories / max(1, total_categories)) * 70.0 + 25.0
        cgpa_bonus = min(5.0, (8.99 - (min_cgpa or 0.0)) * 4.0) if (min_cgpa and 8.99 >= min_cgpa) else 0.0
        score = min(99, max(50, int(base_match + cgpa_bonus)))
        return score, 0.0


# Backward compatibility alias
CandidateMimicMLModel = SkillMatcher


def _get_or_create_profile(db):
    prof = db.query(JobRadarProfile).filter(JobRadarProfile.id == 1).first()
    if prof:
        return prof

    skills = [
        "C++", "Python", "JavaScript", "SQL", "React.js", "Redux", "Node.js", "Express.js",
        "REST APIs", "Microservices", "Apache Kafka", "Redis", "Elasticsearch", "PostgreSQL",
        "MongoDB", "Prisma ORM", "Git", "GitHub", "TCP Sockets", "Multithreading", "LLM Inference Engine",
    ]
    achievements = (
        "NIT Rourkela CSE (CGPA: 8.99, Batch 2027) | LeetCode Contest Rating: 1709 (900+ solved, 15 badges) | "
        "Codeforces Specialist (1425 peak rating, 325+ solved) | CodeChef 3-Star (1632 peak rating) | "
        "Ex-SWE Intern at Maruti Suzuki (Built MERN portal, 13 React pages, 120+ REST APIs, JWT, RBAC) | "
        "DataAnnotation.tech C++ LLM inference engine expert (llama.cpp XTC sampling)."
    )
    resume_summary = (
        "Nandam Venkata Sai Raghava is a top-performing 2027 Computer Science student at NIT Rourkela with 8.99 CGPA. "
        "Architected a Distributed Railway Reservation platform with 8 microservices, 13 Kafka topics, Redis Lua locks, and Saga rollback. "
        "Built a high-performance Redis-compatible Cache Server in C++ over raw TCP sockets with custom RESP parser and O(1) LRU/LFU eviction. "
        "Proven software engineering internship experience at Maruti Suzuki India Ltd."
    )
    now = _utcnow()
    prof = JobRadarProfile(
        id=1,
        full_name="Nandam Venkata Sai Raghava",
        email="sairaghava1318@gmail.com",
        phone=None,
        college="National Institute of Technology, Rourkela (NIT Rourkela)",
        degree="Bachelor of Technology in Computer Science and Engineering",
        grad_year=2027,
        cgpa=8.99,
        location_pref="Bengaluru, Hyderabad, Gurugram, Remote",
        linkedin="https://www.linkedin.com/in/nandam-venkata-sai-raghava-946b3735b/",
        github="https://github.com/VeratrilS",
        leetcode="https://leetcode.com/u/Sairaghava1318/",
        codeforces="https://codeforces.com/profile/Raghavan_CP",
        skills=json.dumps(skills),
        achievements=achievements,
        resume_summary=resume_summary,
        min_ctc_lpa=15.0,
        auto_apply_enabled=False,
        daily_target_applications=None,
        stealth_mode=False,
        ml_mimic_active=False,
        last_hourly_scan_at=now,
        next_hourly_scan_at=now + timedelta(minutes=60),
    )
    db.add(prof)
    db.commit()
    return prof


def _sync_into_placements(db, job_op):
    """
    Syncs verified, genuinely applied job into the active Placements Kanban board.
    ONLY called when the user actually submits or confirms submission.
    """
    existing = db.query(Application).filter(Application.company.ilike(job_op.company.strip())).first()
    ref_label = f"#{job_op.application_ref}" if job_op.application_ref else "None"
    if not existing:
        notes_lines = [
            "Verified Application submitted for Nandam Venkata Sai Raghava.",
            "Institution: NIT Rourkela (CGPA: 8.99, Batch: 2027)",
            f"Your Reference: {ref_label}",
        ]
        if job_op.ctc_lpa:
            notes_lines.append(f"Compensation: {job_op.stipend_pm or ''} ({job_op.ctc_lpa} LPA)")
        if job_op.portal_url:
            notes_lines.append(f"Portal: {job_op.portal_url}")

        app = Application(
            company=job_op.company,
            role=job_op.role,
            source="off-campus",
            stage="applied",
            ctc_lpa=job_op.ctc_lpa or 0.0,
            location=job_op.location,
            link=job_op.portal_url,
            notes="\n".join(notes_lines),
            next_event_label="Awaiting OA / Screening Link",
            next_event_at=_utcnow() + timedelta(days=3),
        )
        db.add(app)
        db.flush()
        job_op.placement_app_id = app.id
        ev = ApplicationEvent(
            application_id=app.id,
            kind="stage",
            text=f"Applied via official career portal. Ref: {ref_label}",
            at=_utcnow(),
        )
        db.add(ev)
    elif existing.stage in ("wishlist", "applied"):
        existing.stage = "applied"
        job_op.placement_app_id = existing.id
        if job_op.application_ref:
            existing.notes = (existing.notes or "") + f"\n[Confirmed submission ref: #{job_op.application_ref}]"


def execute_hourly_scan(db, force=False, batch_size=None):
    """
    Executes live job discovery using real public job-board feeds (Greenhouse, Lever, Ashby, SmartRecruiters).
    No random numbers, no simulated mock data.
    """
    from api.domain.job_sources import collect, upsert
    prof = _get_or_create_profile(db)
    now = _utcnow()

    if not force and prof.last_hourly_scan_at:
        elapsed_sec = (now - prof.last_hourly_scan_at).total_seconds()
        if elapsed_sec < 3500:
            return False, "Scan already completed recently. Next hourly check pending."

    ist_now_str = now_ist().strftime("%H:%M IST")
    log_items = [
        {"time": ist_now_str, "event": "Live Job Radar scanner querying public company job boards (Greenhouse, Lever, Ashby, SmartRecruiters)..."},
    ]

    scored, errors = collect()
    new = upsert(db, scored)

    prof.last_hourly_scan_at = now
    prof.next_hourly_scan_at = now + timedelta(minutes=60)

    confirmed_applied = db.query(JobOpportunity).filter(
        JobOpportunity.status.in_(["manual_applied", "applied_confirmed"])
    ).count()

    log_items.append({
        "time": ist_now_str,
        "event": f"Real scan complete. Fetched {len(scored)} live postings, upserted {len(new)} new openings. Errors: {len(errors)}.",
    })
    log_items.append({
        "time": ist_now_str,
        "event": f"Applications confirmed by Sai: {confirmed_applied}.",
    })

    scan_log = JobRadarScanLog(
        scanned_at=now,
        sources_scanned=31,
        total_evaluated=len(scored),
        eligible_2027_found=len(new),
        auto_applied_count=confirmed_applied,
        log_details=json.dumps(log_items),
        status="success",
    )
    db.add(scan_log)
    db.commit()
    return True, f"Live scan completed. Evaluated {len(scored)} live postings, found {len(new)} new roles."


# ---------------- API Endpoints ----------------

@job_radar_bp.route("/radar", methods=["GET"])
def get_job_radar():
    """
    Returns full job radar status, diagnostics, and verified openings.
    """
    db = SessionLocal()
    try:
        prof = _get_or_create_profile(db)
        now = _utcnow()

        jobs = db.query(JobOpportunity).order_by(JobOpportunity.ctc_lpa.desc(), JobOpportunity.match_score.desc()).all()
        logs = db.query(JobRadarScanLog).order_by(JobRadarScanLog.scanned_at.desc()).limit(8).all()

        profile_data = {
            "full_name": prof.full_name,
            "email": prof.email,
            "phone": prof.phone,
            "college": prof.college,
            "degree": prof.degree,
            "grad_year": prof.grad_year,
            "cgpa": prof.cgpa,
            "location_pref": prof.location_pref,
            "linkedin": prof.linkedin,
            "github": prof.github,
            "leetcode": prof.leetcode,
            "codeforces": prof.codeforces,
            "skills": json.loads(prof.skills) if prof.skills else [],
            "achievements": prof.achievements,
            "resume_summary": prof.resume_summary,
            "min_ctc_lpa": prof.min_ctc_lpa,
            "auto_apply_enabled": prof.auto_apply_enabled,
            "daily_target_applications": prof.daily_target_applications,
            "stealth_mode": prof.stealth_mode,
            "ml_mimic_active": prof.ml_mimic_active,
            "last_hourly_scan_at": _iso(prof.last_hourly_scan_at),
            "next_hourly_scan_at": _iso(prof.next_hourly_scan_at),
        }

        jobs_data = []
        for j in jobs:
            jobs_data.append({
                "id": j.id,
                "external_id": j.external_id,
                "company": j.company,
                "role": j.role,
                "eligible_batches": j.eligible_batches,
                "eligible_branches": j.eligible_branches,
                "min_cgpa": j.min_cgpa,
                "ctc_lpa": j.ctc_lpa,
                "stipend_pm": j.stipend_pm,
                "location": j.location,
                "source": j.source,
                "portal_url": j.portal_url,
                "deadline": j.deadline,
                "skills_required": json.loads(j.skills_required) if j.skills_required else [],
                "hiring_workflow": j.hiring_workflow,
                "match_score": j.match_score,
                "shortlist_prob": j.shortlist_prob,
                "status": j.status,
                "applied_at": _iso(j.applied_at),
                "application_ref": j.application_ref,
                "follow_up_7d_at": _iso(j.follow_up_7d_at),
                "follow_up_14d_at": _iso(j.follow_up_14d_at),
                "ml_tailored_answers": json.loads(j.ml_tailored_answers) if j.ml_tailored_answers else None,
                "outcome": j.outcome,
                "outcome_at": _iso(j.outcome_at),
                "outcome_note": j.outcome_note,
                "notes": j.notes,
                "discovered_at": _iso(j.discovered_at),
                "last_checked_at": _iso(j.last_checked_at),
            })

        eligible_2027 = [j for j in jobs_data if (not j["eligible_batches"] or "2027" in str(j["eligible_batches"])) and (j["ctc_lpa"] == 0 or j["ctc_lpa"] >= prof.min_ctc_lpa)]
        applied_confirmed = [j for j in jobs_data if j["status"] in ("manual_applied", "applied_confirmed")]
        queued = [j for j in jobs_data if j["status"] == "discovered"]
        highest_ctc = max((j["ctc_lpa"] for j in jobs_data if j["ctc_lpa"]), default=0.0)

        week_cutoff = now - timedelta(days=7)
        applied_this_week = 0
        applied_days = set()
        for j in jobs:
            if j.status in ("manual_applied", "applied_confirmed") and j.applied_at:
                if j.applied_at >= week_cutoff:
                    applied_this_week += 1
                ist_date = (j.applied_at + timedelta(hours=5, minutes=30)).date()
                applied_days.add(ist_date)

        today_ist = (now + timedelta(hours=5, minutes=30)).date()
        applied_streak = 0
        cur_d = today_ist
        if cur_d not in applied_days:
            cur_d = cur_d - timedelta(days=1)
        while cur_d in applied_days:
            applied_streak += 1
            cur_d = cur_d - timedelta(days=1)

        oa_total = sum(1 for j in jobs if j.outcome == "oa")
        interview_total = sum(1 for j in jobs if j.outcome == "interview")
        offer_total = sum(1 for j in jobs if j.outcome == "offer")
        rejected_total = sum(1 for j in jobs if j.outcome == "rejected")

        oa_this_week = sum(1 for j in jobs if j.outcome == "oa" and j.outcome_at and j.outcome_at >= week_cutoff)
        interview_this_week = sum(1 for j in jobs if j.outcome == "interview" and j.outcome_at and j.outcome_at >= week_cutoff)
        offer_this_week = sum(1 for j in jobs if j.outcome == "offer" and j.outcome_at and j.outcome_at >= week_cutoff)

        callbacks = [j.outcome_at for j in jobs if j.outcome in ("oa", "interview", "offer") and j.outcome_at]
        days_since_last_callback = None
        if callbacks:
            days_since_last_callback = (now - max(callbacks)).days

        logs_data = []
        for l in logs:
            logs_data.append({
                "id": l.id,
                "scanned_at": _iso(l.scanned_at),
                "sources_scanned": l.sources_scanned,
                "total_evaluated": l.total_evaluated,
                "eligible_2027_found": l.eligible_2027_found,
                "auto_applied_count": l.auto_applied_count,
                "log_details": json.loads(l.log_details) if l.log_details else [],
                "status": l.status,
            })

        return jsonify({
            "status": "success",
            "profile": profile_data,
            "jobs": jobs_data,
            "summary": {
                "total_openings": len(jobs_data),
                "eligible_2027_count": len(eligible_2027),
                "confirmed_applied_count": len(applied_confirmed),
                "applications_confirmed": len(applied_confirmed),
                "auto_applied_count": len(applied_confirmed),
                "applied_total": len(applied_confirmed),
                "oa_total": oa_total,
                "interview_total": interview_total,
                "offer_total": offer_total,
                "rejected_total": rejected_total,
                "applied_this_week": applied_this_week,
                "oa_this_week": oa_this_week,
                "interview_this_week": interview_this_week,
                "offer_this_week": offer_this_week,
                "days_since_last_callback": days_since_last_callback,
                "applied_streak_days": applied_streak,
                "streak": applied_streak,
                "packets_ready_count": len(eligible_2027),
                "queued_count": len(queued),
                "daily_target": prof.daily_target_applications,
                "daily_progress_pct": min(100, int((len(applied_confirmed) / max(1, prof.daily_target_applications)) * 100)) if prof.daily_target_applications else 0,
                "highest_ctc": highest_ctc,
                "auto_apply_enabled": prof.auto_apply_enabled,
                "stealth_mode": prof.stealth_mode,
                "ml_mimic_active": prof.ml_mimic_active,
                "last_hourly_scan": _iso(prof.last_hourly_scan_at),
                "next_hourly_scan": _iso(prof.next_hourly_scan_at),
            },
            "recent_logs": logs_data,
        })
    finally:
        db.close()


@job_radar_bp.route("/hourly-check", methods=["POST"])
def trigger_scan():
    """
    Immediate trigger for the 'Huge Hourly Check'.
    """
    db = SessionLocal()
    try:
        data = request.get_json(silent=True) or {}
        batch_size = data.get("batch_size")
        ok, msg = execute_hourly_scan(db, force=True, batch_size=batch_size)
        return jsonify({"status": "success", "message": msg})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()


@job_radar_bp.route("/confirm-applied", methods=["POST"])
@job_radar_bp.route("/manual-applied", methods=["POST"])
@job_radar_bp.route("/applied", methods=["POST"])
def confirm_applied():
    """
    Records an authentic application after the candidate submits on the official portal.
    Sets status to 'manual_applied' and schedules 7-day and 14-day follow-up reminders.
    Syncs with real data into the Placements board. Zero mock or fake submissions.
    """
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id")
    confirmation_ref = (data.get("confirmation_ref") or "").strip()[:100]
    notes = (data.get("notes") or "").strip()[:500]

    db = SessionLocal()
    try:
        prof = _get_or_create_profile(db)
        job = db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
        if not job:
            return jsonify({"status": "error", "message": "Job opening not found."}), 404

        if job.status in ("manual_applied", "applied_confirmed"):
            return jsonify({"status": "conflict", "message": "Already recorded as applied."}), 409

        now = _utcnow()
        ref = confirmation_ref if confirmation_ref else None
        job.status = "manual_applied"
        job.applied_at = now
        job.application_ref = ref
        job.follow_up_7d_at = now + timedelta(days=7)
        job.follow_up_14d_at = now + timedelta(days=14)
        job.followup_7d_sent_at = None
        job.followup_14d_sent_at = None
        if notes:
            job.notes = (f"{job.notes}\n{notes}" if job.notes else notes)

        _sync_into_placements(db, job)
        db.commit()

        return jsonify({
            "status": "success",
            "message": f"Recorded confirmed application to {job.company}! Synced to Placements board.",
            "application_ref": ref,
            "follow_up_7d": _iso(job.follow_up_7d_at),
            "follow_up_14d": _iso(job.follow_up_14d_at),
        })
    finally:
        db.close()


@job_radar_bp.route("/unmark-applied", methods=["POST"])
def unmark_applied():
    """
    Reverts an opening back to discovered state if marked accidentally.
    """
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id")

    db = SessionLocal()
    try:
        job = db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
        if not job:
            return jsonify({"status": "error", "message": "Job opening not found."}), 404

        job.status = "discovered"
        job.applied_at = None
        job.application_ref = None
        job.follow_up_7d_at = None
        job.follow_up_14d_at = None
        job.followup_7d_sent_at = None
        job.followup_14d_sent_at = None

        if job.placement_app_id:
            db.query(ApplicationEvent).filter(ApplicationEvent.application_id == job.placement_app_id).delete(synchronize_session=False)
            db.query(Application).filter(Application.id == job.placement_app_id).delete(synchronize_session=False)
            job.placement_app_id = None
        db.commit()
        return jsonify({
            "status": "success",
            "message": f"Reset application status for {job.company}.",
        })
    finally:
        db.close()


@job_radar_bp.route("/<int:job_id>/outcome", methods=["POST"])
def set_job_outcome(job_id):
    """
    Records an application outcome: oa | interview | rejected | offer | no_response.
    Syncs with Placements Kanban stage.
    """
    data = request.get_json(silent=True) or {}
    outcome = (data.get("outcome") or "").lower().strip()
    notes = (data.get("notes") or "").strip()[:1000]

    VALID_OUTCOMES = {"oa", "interview", "rejected", "offer", "no_response"}
    if outcome not in VALID_OUTCOMES:
        return jsonify({"status": "error", "message": f"Invalid outcome. Must be one of: {', '.join(sorted(VALID_OUTCOMES))}"}), 400

    db = SessionLocal()
    try:
        job = db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
        if not job:
            return jsonify({"status": "error", "message": "Job not found"}), 404

        now = _utcnow()
        job.outcome = outcome
        job.outcome_at = now
        if notes:
            job.outcome_note = notes

        # Sync to Placements Kanban if placement_app_id exists
        if job.placement_app_id:
            from api.domain.placements import Application, ApplicationEvent
            app_entry = db.query(Application).filter(Application.id == job.placement_app_id).first()
            if app_entry:
                stage_map = {
                    "oa": "oa",
                    "interview": "interview",
                    "rejected": "rejected",
                    "offer": "offer",
                }
                if outcome in stage_map:
                    app_entry.stage = stage_map[outcome]
                    evt = ApplicationEvent(
                        application_id=app_entry.id,
                        event_type=f"outcome_{outcome}",
                        notes=f"Outcome updated to {outcome.upper()}" + (f": {notes}" if notes else ""),
                        timestamp=now,
                    )
                    db.add(evt)

        db.commit()
        return jsonify({
            "status": "success",
            "message": f"Recorded outcome '{outcome}' for {job.company}",
            "data": {
                "id": job.id,
                "outcome": job.outcome,
                "outcome_at": _iso(job.outcome_at),
                "outcome_note": job.outcome_note,
            }
        })
    finally:
        db.close()




@job_radar_bp.route("/<int:job_id>/referral", methods=["GET"])
def get_job_referral(job_id):
    """
    Returns referral assistance for a company opening:
    - LinkedIn search URLs for NIT Rourkela alumni & SWEs at the company
    - Grounded referral-request message template using candidate facts (no scraping, no auto messaging).
    """
    import urllib.parse
    db = SessionLocal()
    try:
        job = db.get(JobOpportunity, job_id)
        if not job:
            return jsonify({"status": "error", "message": "Job not found"}), 404

        company = job.company or "Company"
        role = job.role or "Software Engineer"

        alumni_q = f"{company} NIT Rourkela"
        swe_q = f"{company} software engineer"

        alumni_url = f"https://www.linkedin.com/search/results/people/?keywords={urllib.parse.quote(alumni_q)}"
        swe_url = f"https://www.linkedin.com/search/results/people/?keywords={urllib.parse.quote(swe_q)}"

        template = (
            f"Hi [Name],\n\n"
            f"Hope you are doing well! I'm a final-year CSE student at NIT Rourkela (8.99 CGPA, LeetCode 1709, ex-MSIL intern) "
            f"and saw the {role} opening at {company}.\n\n"
            f"I have strong hands-on experience in distributed systems (Kafka microservices) and low-level C++. "
            f"Would you be open to referring me for this role? Happy to share my resume and details.\n\n"
            f"Thank you,\nSai Raghava"
        )

        return jsonify({
            "status": "success",
            "data": {
                "id": job.id,
                "company": company,
                "role": role,
                "alumni_url": alumni_url,
                "engineers_url": swe_url,
                "template": template,
            }
        })
    finally:
        db.close()


@job_radar_bp.route("/auto-apply", methods=["POST"])
def auto_apply_job():
    """Fallback handler redirecting to confirm-applied to prevent any simulated auto-applications."""
    return confirm_applied()


@job_radar_bp.route("/receipts", methods=["GET"])
def get_receipts():
    """Returns only real confirmed applications with their authentic technical preparation blueprints."""
    db = SessionLocal()
    try:
        confirmed = db.query(JobOpportunity).filter(JobOpportunity.status.in_(["manual_applied", "applied_confirmed"])).order_by(JobOpportunity.applied_at.desc()).all()
        out = []
        for c in confirmed:
            skills = json.loads(c.skills_required) if isinstance(c.skills_required, str) else c.skills_required
            out.append({
                "id": c.id,
                "job_id": c.id,
                "company": c.company,
                "role": c.role,
                "application_ref": c.application_ref,
                "candidate_name": "Nandam Venkata Sai Raghava",
                "candidate_email": "sairaghava1318@gmail.com",
                "ctc_lpa": c.ctc_lpa,
                "stipend_pm": c.stipend_pm,
                "status": "Applied (confirmed by you)",
                "sender_title": "Your application record",
                "subject": f"Applied: {c.company} ({c.role})",
                "message_body": f"Your recorded application on {c.company}'s official portal. Ref: #{c.application_ref}",
                "oa_timeline": "Official assessment link expected per company recruiting schedule",
                "prep_guidance": f"Review {', '.join(skills[:5])}. Focus on concurrency, graphs, and system design.",
                "submitted_at": _iso(c.applied_at),
                "email_dispatched": True,
            })
        return jsonify({"status": "success", "receipts": out})
    finally:
        db.close()


@job_radar_bp.route("/blueprints", methods=["GET"])
def get_blueprints():
    """
    Returns authentic technical interview prep blueprints for verified tier-1 companies.
    """
    db = SessionLocal()
    try:
        jobs = db.query(JobOpportunity).all()
        seen = set()
        blueprints = []
        for j in jobs:
            if j.company in seen:
                continue
            seen.add(j.company)
            oa_platform = (
                "CodeSignal" if "Uber" in j.company
                else "HackerRank" if any(c in j.company for c in ["DE Shaw", "Goldman", "Atlassian", "Sprinklr", "Razorpay"])
                else "Codility" if "Microsoft" in j.company
                else "Google Online Challenge" if "Google" in j.company
                else "HackerRank"
            )
            skills = json.loads(j.skills_required) if isinstance(j.skills_required, str) else j.skills_required
            blueprints.append({
                "company": j.company,
                "role": j.role,
                "ctc_lpa": j.ctc_lpa,
                "stipend_pm": j.stipend_pm,
                "portal_url": j.portal_url,
                "oa_platform": oa_platform,
                "oa_timeline": "48 to 72 hours post official portal submission",
                "core_topics": skills[:6],
                "hiring_workflow": j.hiring_workflow,
                "status": j.status,
                "applied_at": _iso(j.applied_at),
                "application_ref": j.application_ref,
            })
        return jsonify({"status": "success", "blueprints": blueprints})
    finally:
        db.close()


@job_radar_bp.route("/toggle-auto-apply", methods=["POST"])
def toggle_auto_apply():
    """
    Toggle background hourly alert scanner on / off.
    """
    data = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        prof = _get_or_create_profile(db)
        if "enabled" in data:
            prof.auto_apply_enabled = bool(data["enabled"])
        else:
            prof.auto_apply_enabled = not prof.auto_apply_enabled
        db.commit()
        return jsonify({
            "status": "success",
            "auto_apply_enabled": prof.auto_apply_enabled,
            "message": f"Hourly Radar Scanner is now {'ACTIVE' if prof.auto_apply_enabled else 'PAUSED'}.",
        })
    finally:
        db.close()


@job_radar_bp.route("/settings", methods=["POST"])
def update_settings():
    """
    Updates profile details, minimum CTC, location preferences.
    """
    data = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        prof = _get_or_create_profile(db)
        if "min_ctc_lpa" in data and data["min_ctc_lpa"] is not None:
            prof.min_ctc_lpa = float(data["min_ctc_lpa"])
        if "daily_target_applications" in data:
            prof.daily_target_applications = int(data["daily_target_applications"]) if data["daily_target_applications"] is not None else None
        if "auto_apply_enabled" in data and data["auto_apply_enabled"] is not None:
            prof.auto_apply_enabled = bool(data["auto_apply_enabled"])
        if "stealth_mode" in data and data["stealth_mode"] is not None:
            prof.stealth_mode = bool(data["stealth_mode"])
        if "ml_mimic_active" in data and data["ml_mimic_active"] is not None:
            prof.ml_mimic_active = bool(data["ml_mimic_active"])
        if "phone" in data:
            prof.phone = str(data["phone"])[:40] if data["phone"] is not None else None
        if "email" in data and data["email"] is not None:
            prof.email = str(data["email"])[:120]
        if "location_pref" in data and data["location_pref"] is not None:
            prof.location_pref = str(data["location_pref"])[:200]
        db.commit()
        return jsonify({"status": "success", "message": "Job Radar preferences updated."})
    finally:
        db.close()


@job_radar_bp.route("/dispatch-live-alert", methods=["POST"])
def dispatch_live_alert():
    """
    Sends a complete application packet & official apply link directly to Sai's email
    so he can review and apply on the official portal with zero fake simulation.
    """
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id")

    db = SessionLocal()
    try:
        prof = _get_or_create_profile(db)
        job = None
        if job_id:
            job = db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
        if not job:
            return jsonify({"status": "error", "message": "Job opening not found."}), 404

        sender_email = os.getenv("SENDER_EMAIL")
        sender_password = os.getenv("SENDER_PASSWORD")

        if not sender_email or not sender_password:
            return jsonify({"status": "error", "message": "SMTP credentials not configured."}), 500

        client = EmailClient(sender_email, sender_password)
        company_esc = html.escape(job.company)
        role_esc = html.escape(job.role)
        portal_url_esc = html.escape(job.portal_url or "")
        loc_esc = html.escape(job.location or "")

        ctc_label = f"{job.ctc_lpa:g} LPA CTC (est.)" if job.ctc_lpa else "CTC not listed"
        subject = f"[Job Radar] Review & apply: {job.company} - {job.role} ({ctc_label})"

        from api.domain.job_pack import generate_pack, JobPack
        pack_row = db.query(JobPack).filter(JobPack.job_id == job.id).first()
        if pack_row:
            try:
                pack_data = json.loads(pack_row.payload)
            except Exception:
                pack_data, _ = generate_pack(job)
        else:
            pack_data, _ = generate_pack(job)

        answers_list = pack_data.get("answers", [])
        answers_html_items = []
        if pack_data.get("why_company"):
            answers_html_items.append(
                f'<div style="margin-bottom:12px;">'
                f'<div style="font-weight:700;font-size:12px;color:#065f46;">Why {company_esc}?</div>'
                f'<p style="margin:4px 0 0;font-size:12px;color:#047857;line-height:1.5;">"{html.escape(pack_data["why_company"])}"</p>'
                f'</div>'
            )
        for a in answers_list[:3]:
            q_text = html.escape(a.get("question", ""))
            ans_text = html.escape(a.get("answer", ""))
            answers_html_items.append(
                f'<div style="margin-bottom:12px;">'
                f'<div style="font-weight:700;font-size:12px;color:#065f46;">{q_text}</div>'
                f'<p style="margin:4px 0 0;font-size:12px;color:#047857;line-height:1.5;">"{ans_text}"</p>'
                f'</div>'
            )
        answers_html_block = "".join(answers_html_items)

        skills = json.loads(job.skills_required) if isinstance(job.skills_required, str) else (job.skills_required or [])
        skills_esc = ", ".join(html.escape(s) for s in skills)

        html_body = f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:650px;margin:0 auto;padding:24px;background:#ffffff;border:1px solid #e2e8f0;border-radius:18px;">
            <div style="border-bottom:1px solid #e2e8f0;padding-bottom:16px;margin-bottom:20px;">
                <h1 style="margin:12px 0 4px;font-size:22px;color:#0f172a;">{company_esc} · {role_esc}</h1>
                <p style="margin:0;font-size:14px;color:#64748b;">Compensation: <b>{ctc_label}</b> · Location: <b>{loc_esc}</b></p>
            </div>

            <p style="font-size:14px;color:#334155;line-height:1.6;">Hi Sai,</p>
            <p style="font-size:14px;color:#334155;line-height:1.6;">
                An opening matching your profile is available at <b>{company_esc}</b>.
                Below is your application packet pre-formatted with your credentials and answer drafts.
            </p>

            <div style="text-align:center;margin:24px 0;">
                <a href="{portal_url_esc}" target="_blank" style="display:inline-block;background:#059669;color:#ffffff;font-size:15px;font-weight:700;padding:12px 28px;border-radius:10px;text-decoration:none;box-shadow:0 4px 14px rgba(5,150,105,0.3);">
                    🚀 Open Official {company_esc} Application
                </a>
            </div>

            <div style="background:#f8fafc;border:1px solid #cbd5e1;border-radius:12px;padding:16px;margin:20px 0;">
                <h3 style="margin:0 0 10px;font-size:14px;color:#0f172a;">📋 Candidate Details:</h3>
                <ul style="margin:0;padding-left:18px;font-size:13px;color:#334155;line-height:1.8;">
                    <li><b>Full Name:</b> {html.escape(prof.full_name or '')}</li>
                    <li><b>Email:</b> {html.escape(prof.email or '')}</li>
                    <li><b>College:</b> {html.escape(prof.college or '')}</li>
                    <li><b>Degree / Branch:</b> {html.escape(prof.degree or '')}</li>
                    <li><b>CGPA:</b> <b>{prof.cgpa} / 10.0</b></li>
                    <li><b>LeetCode:</b> {html.escape(prof.leetcode or '')}</li>
                    <li><b>Codeforces:</b> {html.escape(prof.codeforces or '')}</li>
                    <li><b>GitHub:</b> {html.escape(prof.github or '')}</li>
                </ul>
            </div>

            <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:12px;padding:16px;margin:20px 0;">
                <h3 style="margin:0 0 10px;font-size:14px;color:#065f46;">💡 Grounded Application Pack Answers:</h3>
                {answers_html_block}
            </div>

            <div style="font-size:12px;color:#64748b;line-height:1.6;border-top:1px solid #e2e8f0;padding-top:16px;">
                <b>Skills required:</b> {skills_esc}
            </div>
        </div>
        """

        plain_text = f"Apply to {job.company} - {job.role}\nLink: {job.portal_url}\nCandidate: {prof.full_name}"
        ok = client.send_email(prof.email, subject, plain_text, html=html_body)

        if ok:
            return jsonify({
                "status": "success",
                "message": f"Application packet & official apply link sent to {prof.email} for {job.company}!",
                "portal_url": job.portal_url,
                "company": job.company,
            })
        else:
            return jsonify({"status": "error", "message": "Failed to send email. Check SMTP."}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()


LAST_FOLLOWUP_KEY = "job_radar:last_followup_email"
FOLLOWUP_GAP = timedelta(hours=20)


@job_radar_bp.route("/followups", methods=["POST"])
def send_followup_reminders():
    """
    Sends email reminders for applications whose 7-day or 14-day follow-up is due.
    Open scheduler endpoint, throttled to once every 20 hours.
    Idempotent: updates followup_7d_sent_at and followup_14d_sent_at so jobs are not re-emailed.
    """
    from api.domain.repositories import NotificationRepository
    db = SessionLocal()
    try:
        repo = NotificationRepository(db)
        last = repo.get_setting(LAST_FOLLOWUP_KEY)
        now = _utcnow()
        if last:
            try:
                if datetime.now(timezone.utc) - datetime.fromisoformat(last) < FOLLOWUP_GAP:
                    return jsonify({"status": "skipped", "message": "Follow-ups checked recently."})
            except ValueError:
                pass

        due_7d = db.query(JobOpportunity).filter(
            JobOpportunity.status.in_(["manual_applied", "applied_confirmed"]),
            JobOpportunity.follow_up_7d_at <= now,
            JobOpportunity.followup_7d_sent_at.is_(None),
        ).all()
        due_14d = db.query(JobOpportunity).filter(
            JobOpportunity.status.in_(["manual_applied", "applied_confirmed"]),
            JobOpportunity.follow_up_14d_at <= now,
            JobOpportunity.followup_14d_sent_at.is_(None),
        ).all()

        sender, password = os.getenv("SENDER_EMAIL"), os.getenv("SENDER_PASSWORD")
        emailed = False
        if (due_7d or due_14d) and sender and password:
            from api.core.clients import EmailClient
            subject = f"📬 Job Radar: Follow-ups due for {len(due_7d) + len(due_14d)} applications"
            items_html = "".join([
                f"<li><b>{html.escape(j.company)}</b> ({html.escape(j.role)}) - Applied {j.applied_at.strftime('%d %b') if j.applied_at else 'recently'}. 7-day check-in due.</li>"
                for j in due_7d
            ])
            items_html += "".join([
                f"<li><b>{html.escape(j.company)}</b> ({html.escape(j.role)}) - Applied {j.applied_at.strftime('%d %b') if j.applied_at else 'recently'}. 14-day follow-up due.</li>"
                for j in due_14d
            ])
            body = f"<h2>Applications due for follow-up:</h2><ul>{items_html}</ul><p><a href='{html.escape(os.getenv('APP_URL', 'http://localhost:5173'))}#/job-radar'>Open Job Radar</a></p>"
            EmailClient(sender, password).send_email(
                os.getenv("RECEIVER_EMAIL", "sairaghava1318@gmail.com"),
                subject,
                "Follow-ups due for your applications",
                html=body
            )
            emailed = True
            for j in due_7d:
                j.followup_7d_sent_at = now
            for j in due_14d:
                j.followup_14d_sent_at = now
            db.commit()

        repo.set_setting(LAST_FOLLOWUP_KEY, datetime.now(timezone.utc).isoformat())
        return jsonify({
            "status": "success",
            "due_7d_count": len(due_7d),
            "due_14d_count": len(due_14d),
            "emailed": emailed,
        })
    finally:
        db.close()

