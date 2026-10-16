"""
Tailored one-page resume PDF for one Job Radar opening.

Integrity (docs/JOB_APPLICATION_SYSTEM_AND_GOALS.txt): every line comes from job_pack.RESUME_FACTS (education,
experience, projects, achievements, skills) or from the profile's name / email / phone / links. Nothing is invented
and nothing is reworded beyond splitting "Title: details" and capitalising the first letter of the details. Tailoring
only changes ORDER: entries most relevant to the job's skills_required / role come first, and the skills line puts
the job's listed skills first. Skills not in RESUME_FACTS["skills"] are never added.

ATS-friendly layout: single column, Helvetica, plain text headings (Education, Experience, Projects, Achievements,
Skills), "-" bullets, no tables, images, columns or graphics.

Endpoint (blueprint job_resume_bp, prefix /api/jobs; passcode-protected by app.before_request):
  GET /api/jobs/<job_id>/resume.pdf  -> attachment "NandamVenkataSaiRaghava_<Company>.pdf"
"""
import re
import unicodedata
from functools import lru_cache
from types import SimpleNamespace

from flask import Blueprint, Response, jsonify

from api.core.db import SessionLocal
from api.domain.job_pack import _DEFAULT_ORDER, _HIGHLIGHTS, _ROLE_HINTS, RESUME_FACTS, _canon, job_skills
from api.domain.job_radar import JobOpportunity, JobRadarProfile
from api.domain.studio.builders import latin1

FILENAME_PREFIX = "NandamVenkataSaiRaghava"

# Which RESUME_FACTS highlight goes under which heading.
EXPERIENCE_IDS = ("maruti", "dataannotation")
PROJECT_IDS = ("railway", "cache", "react_comps")
ACHIEVEMENT_IDS = ("cp",)
SECTION_ORDER = ("Education", "Experience", "Projects", "Achievements", "Skills")

# Profile fields used in the header (column defaults are used when the profile row is missing).
_LINK_FIELDS = (("linkedin", "LinkedIn"), ("github", "GitHub"), ("leetcode", "LeetCode"), ("codeforces", "Codeforces"))


def _column_default(name):
    default = JobRadarProfile.__table__.c[name].default
    return default.arg if default is not None and not callable(default.arg) else None


def default_profile():
    """A profile object built from the JobRadarProfile column defaults (no DB)."""
    fields = ("full_name", "email", "phone") + tuple(f for f, _ in _LINK_FIELDS)
    return SimpleNamespace(**{f: _column_default(f) for f in fields})


# ---------------- Relevance ----------------
def _word_in(term, text):
    return re.search(r"(?<![a-z0-9+])" + re.escape(term) + r"(?![a-z0-9+])", text) is not None


def highlight_scores(job):
    """Relevance of every RESUME_FACTS highlight to the job: listed-skill/tag overlap, literal mentions, role title."""
    skills = job_skills(job)
    canons = {_canon(s) for s in skills}
    terms = {s.strip().lower() for s in skills if len(s.strip()) >= 3}
    role = job.role or ""
    scores = {}
    for h in RESUME_FACTS["highlights"]:
        tags = set(h["tags"])
        text = h["bullet"].lower()
        score = 2 * len(canons & tags)
        score += sum(1 for t in terms if _canon(t) not in tags and _word_in(t, text))
        scores[h["id"]] = score
    for pattern, ids in _ROLE_HINTS:
        if pattern.search(role):
            for i in ids:
                scores[i] += 1
    return scores


def ranked_ids(job, ids):
    """`ids` reordered most-relevant first; ties keep RESUME_FACTS order."""
    scores = highlight_scores(job)
    return sorted(ids, key=lambda i: (-scores[i], _DEFAULT_ORDER.index(i)))


def ordered_skills(job):
    """RESUME_FACTS skills only: those the job lists first (job order), then those the most relevant work uses,
    then the rest in their original order."""
    listed = RESUME_FACTS["skills"]
    job_pos = {}
    for pos, s in enumerate(job_skills(job)):
        job_pos.setdefault(_canon(s), pos)
    scores = highlight_scores(job)
    support = {}  # best relevance score of a highlight that uses the skill
    for h in RESUME_FACTS["highlights"]:
        for t in h["tags"]:
            support[t] = max(support.get(t, 0), scores[h["id"]])

    def key(item):
        idx, skill = item
        c = _canon(skill)
        if c in job_pos:
            return (0, job_pos[c], idx)
        return (1, -support.get(c, 0), idx)

    return [s for _, s in sorted(enumerate(listed), key=key)]


# ---------------- Content (pure) ----------------
def _split_fact(fact):
    """"Title: details" -> ("Title", "Details"). Text is unchanged apart from the first letter's case."""
    title, sep, detail = fact.partition(": ")
    if not sep:
        return None, fact
    return title, detail[:1].upper() + detail[1:]


def _entry(hid):
    fact = _HIGHLIGHTS[hid]["bullet"]
    title, detail = _split_fact(fact)
    return {"id": hid, "title": title, "bullets": [detail], "fact": fact}


def _display_url(url):
    return re.sub(r"^https?://(www\.)?", "", url).rstrip("/")


def contact_items(profile):
    """[(text, url_or_None)] for the header: email, phone only if set, then profile links."""
    items = []
    email = (getattr(profile, "email", None) or "").strip()
    if email:
        items.append((email, f"mailto:{email}"))
    phone = (getattr(profile, "phone", None) or "").strip()
    if phone:
        items.append((phone, None))
    for field, _label in _LINK_FIELDS:
        url = (getattr(profile, field, None) or "").strip()
        if url.startswith(("http://", "https://")):
            items.append((_display_url(url), url))
    return items


def resume_content(job, profile=None):
    """Everything the PDF shows, in order. Pure: no DB, no network."""
    profile = profile or default_profile()
    name = (getattr(profile, "full_name", None) or "").strip() or RESUME_FACTS["name"]
    sections = [
        {"heading": "Education", "entries": [{"id": "education", "title": None,
                                               "bullets": [RESUME_FACTS["education"]], "fact": RESUME_FACTS["education"]}]},
        {"heading": "Experience", "entries": [_entry(i) for i in ranked_ids(job, EXPERIENCE_IDS)]},
        {"heading": "Projects", "entries": [_entry(i) for i in ranked_ids(job, PROJECT_IDS)]},
        {"heading": "Achievements", "entries": [_entry(i) for i in ranked_ids(job, ACHIEVEMENT_IDS)]},
    ]
    skills = ordered_skills(job)
    sections.append({"heading": "Skills", "entries": [{"id": "skills", "title": None,
                                                        "bullets": [", ".join(skills)], "fact": None}]})
    return {"name": name, "contact": contact_items(profile), "sections": sections, "skills": skills}


def resume_filename(company):
    """NandamVenkataSaiRaghava_<Company>.pdf with the company reduced to ASCII letters and digits."""
    ascii_text = unicodedata.normalize("NFKD", str(company or "")).encode("ascii", "ignore").decode()
    parts = re.findall(r"[A-Za-z0-9]+", ascii_text)
    safe = "".join(p[:1].upper() + p[1:] for p in parts)[:60] or "Company"
    return f"{FILENAME_PREFIX}_{safe}.pdf"


# ---------------- PDF ----------------
@lru_cache(maxsize=1)
def _fpdf_class():
    """fpdf2 is imported on first use so it doesn't slow every cold start of the API."""
    from fpdf import FPDF
    return FPDF


def render_pdf(content):
    pdf = _fpdf_class()(format="A4")
    pdf.set_margins(16, 14, 16)
    pdf.set_auto_page_break(True, margin=14)
    pdf.set_title(latin1(f"{content['name']} - Resume"))
    pdf.set_author(latin1(content["name"]))
    pdf.add_page()
    width = pdf.epw

    pdf.set_font("Helvetica", "B", 17)
    pdf.cell(0, 8, latin1(content["name"]), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9.5)
    contact = "  |  ".join(latin1(text) for text, _ in content["contact"])
    pdf.multi_cell(0, 4.8, contact, align="C", new_x="LMARGIN", new_y="NEXT")

    for section in content["sections"]:
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 6.5, section["heading"], new_x="LMARGIN", new_y="NEXT")
        for entry in section["entries"]:
            if entry["title"]:
                pdf.set_font("Helvetica", "B", 10.5)
                pdf.multi_cell(0, 5.2, latin1(entry["title"]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 10)
            for bullet in entry["bullets"]:
                if entry["title"]:
                    pdf.set_x(pdf.l_margin + 3)
                    pdf.cell(4, 5, "-")
                    pdf.multi_cell(width - 7, 5, latin1(bullet), new_x="LMARGIN", new_y="NEXT")
                else:
                    pdf.multi_cell(0, 5, latin1(bullet), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
    return bytes(pdf.output())


# ---------------- Endpoint ----------------
job_resume_bp = Blueprint("job_resume", __name__, url_prefix="/api/jobs")


def _load_profile(db):
    try:
        prof = db.query(JobRadarProfile).filter(JobRadarProfile.id == 1).first()
        if prof:
            return prof
    except Exception:
        db.rollback()
    return default_profile()


@job_resume_bp.route("/<int:job_id>/resume.pdf", methods=["GET"])
def get_resume_pdf(job_id):
    db = SessionLocal()
    try:
        job = db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
        if not job:
            return jsonify({"status": "error", "message": "Job not found"}), 404
        content = resume_content(job, _load_profile(db))
        filename = resume_filename(job.company)
    finally:
        db.close()
    return Response(render_pdf(content), mimetype="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    })
