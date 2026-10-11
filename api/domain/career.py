"""
Career kit for placement season: three small tools that share one blueprint.

1. Resume <-> JD check. Saved resume versions, plus a match that combines a deterministic keyword
   overlap (tokenizer + stopwords + tech-term dictionary, computed here) with a Gemini review
   (score, missing / matched keywords, bullet rewrites). The prompt forbids inventing metrics or
   experience: rewrites use placeholders like [X%] for numbers only the user knows.
2. STAR story bank. Behavioral stories (Situation / Task / Action / Result + tags); Gemini can
   tighten one into a ~90 second spoken answer with three likely follow-up questions.
3. Referral tracker. People who could refer you, their status and follow-up dates; Gemini drafts
   a short personal message that the user copies and sends by hand (nothing is ever sent from here).

If the model is slow or out of quota the deterministic parts still work and the AI parts return a
friendly error.
"""
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, Text
from sqlalchemy.exc import IntegrityError

from api.core.clients import LLMClient
from api.core.config import now_ist
from api.core.db import Base, SessionLocal, engine

MAX_LABEL = 120
MAX_RESUME = 30000
MAX_JD = 15000
MAX_TITLE = 160
MAX_STAR = 3000
MAX_NOTES = 2000
LLM_BUDGET = 110  # seconds across the fallback chain; Vercel gives us 300

STORY_TAGS = ["leadership", "conflict", "failure", "teamwork", "tech-depth", "ownership"]
CONTACT_STATUSES = ["to-ask", "asked", "referred", "declined"]
CLOSED_STATUSES = {"referred", "declined"}


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------- models ----------------
class ResumeVersion(Base):
    __tablename__ = "career_resumes"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(MAX_LABEL), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=_utcnow)  # naive UTC


class Story(Base):
    __tablename__ = "career_stories"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(MAX_TITLE), nullable=False)
    situation = Column(Text, nullable=True)
    task = Column(Text, nullable=True)
    action = Column(Text, nullable=True)
    result = Column(Text, nullable=True)
    tags = Column(String(200), nullable=True)  # comma separated, from STORY_TAGS
    draft = Column(Boolean, default=False, nullable=False)
    polished = Column(Text, nullable=True)  # JSON of the last polish result
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class Contact(Base):
    __tablename__ = "career_contacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    company = Column(String(120), nullable=True)
    role = Column(String(160), nullable=True)
    link = Column(String(500), nullable=True)
    how_known = Column(String(200), nullable=True)
    status = Column(String(16), default="to-ask", nullable=False)
    last_contact = Column(Date, nullable=True)
    follow_up = Column(Date, nullable=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class CareerMeta(Base):
    """One-off flags (e.g. the example story was seeded), so deleting it doesn't bring it back."""
    __tablename__ = "career_meta"

    key = Column(String(64), primary_key=True)
    value = Column(String(200), nullable=True)


career_bp = Blueprint("career", __name__, url_prefix="/api/career")


@career_bp.record_once
def _ensure_tables(state):
    """Create the tables when the blueprint is registered, so wiring it in needs no extra step."""
    for model in (ResumeVersion, Story, Contact, CareerMeta):
        try:
            model.__table__.create(bind=engine, checkfirst=True)
        except Exception as e:  # e.g. a concurrent cold start created it first
            print(f"{model.__tablename__} table check skipped: {e}")


# ---------------- helpers ----------------
class _Invalid(ValueError):
    pass


def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _today():
    return now_ist().date()


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _str(value, field, max_len, required=False):
    if value is None:
        if required:
            raise _Invalid(f"{field} is required.")
        return None
    if not isinstance(value, str):
        raise _Invalid(f"{field} must be text.")
    value = value.strip()
    if not value:
        if required:
            raise _Invalid(f"{field} is required.")
        return None
    if len(value) > max_len:
        raise _Invalid(f"{field} must be at most {max_len} characters.")
    return value


def _date(value, field):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise _Invalid(f"{field} must be a date (YYYY-MM-DD).")
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        raise _Invalid(f"{field} must be a date (YYYY-MM-DD).")


def _tags(value):
    if value is None or value == "":
        return []
    items = value.split(",") if isinstance(value, str) else value
    if not isinstance(items, list):
        raise _Invalid("Tags must be a list.")
    out = []
    for t in items:
        t = t.strip().lower() if isinstance(t, str) else ""
        if not t:
            continue
        if t not in STORY_TAGS:
            raise _Invalid(f"Tags must be from: {', '.join(STORY_TAGS)}.")
        if t not in out:
            out.append(t)
    return out


def _friendly(e):
    msg = str(e)
    if "No API key" in msg:
        return "AI is not configured (set GEMINI_API_KEY)."
    if re.search(r"429|quota|RESOURCE_EXHAUSTED|overloaded|503|UNAVAILABLE|timed? ?out|deadline", msg, re.I):
        return "The AI is busy right now (free tier). Please retry in a minute."
    if isinstance(e, (json.JSONDecodeError, ValueError, TypeError, AttributeError)):
        return "The AI returned something unreadable. Please retry."
    return f"AI error: {msg[:240]}"


def _llm_json(prompt, system, temperature=0.4):
    return LLMClient(budget=LLM_BUDGET).generate_json(prompt, temperature=temperature, system=system, thinking="low")


def _s(value, max_len=600):
    """Coerce a model value to a trimmed string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.strip()[:max_len]


def _str_list(value, limit, max_len=80):
    if isinstance(value, str):
        value = [v for v in re.split(r"[,\n]", value)]
    if not isinstance(value, list):
        return []
    out, seen = [], set()
    for v in value:
        v = _s(v, max_len)
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
        if len(out) >= limit:
            break
    return out


# ---------------- deterministic keyword overlap ----------------
# Canonical tech term -> aliases (all lower case). Multi-word and symbol terms are matched as phrases.
TECH_TERMS = {
    # languages
    "python": ["python", "python3"], "java": ["java"], "c++": ["c++", "cpp"], "c": ["c language", "ansi c"],
    "c#": ["c#", "csharp"], "javascript": ["javascript", "js", "es6", "ecmascript"],
    "typescript": ["typescript", "ts"], "go": ["golang", "go lang"], "rust": ["rust"], "kotlin": ["kotlin"],
    "swift": ["swift"], "scala": ["scala"], "ruby": ["ruby"], "php": ["php"], "r": ["r programming", "rstudio"],
    "sql": ["sql"], "bash": ["bash", "shell scripting", "shell script"], "dart": ["dart"], "matlab": ["matlab"],
    # web / frameworks
    "react": ["react", "reactjs", "react.js"], "next.js": ["next.js", "nextjs"], "angular": ["angular", "angularjs"],
    "vue": ["vue", "vue.js", "vuejs"], "node.js": ["node.js", "nodejs", "node"], "express": ["express", "express.js", "expressjs"],
    "django": ["django"], "flask": ["flask"], "fastapi": ["fastapi"], "spring boot": ["spring boot", "springboot", "spring"],
    "html": ["html", "html5"], "css": ["css", "css3"], "tailwind": ["tailwind", "tailwindcss"], "redux": ["redux"],
    "graphql": ["graphql"], "rest api": ["rest api", "rest apis", "restful", "rest"], "grpc": ["grpc"],
    "websockets": ["websocket", "websockets"], "flutter": ["flutter"], "react native": ["react native"],
    "android": ["android"], "ios": ["ios"], ".net": [".net", "dotnet", "asp.net"],
    # data / ml
    "machine learning": ["machine learning", "ml"], "deep learning": ["deep learning", "dl"],
    "nlp": ["nlp", "natural language processing"], "computer vision": ["computer vision", "cv models"],
    "llm": ["llm", "llms", "large language model", "large language models", "genai", "generative ai"],
    "rag": ["rag", "retrieval augmented generation", "retrieval-augmented generation"],
    "pytorch": ["pytorch", "torch"], "tensorflow": ["tensorflow", "tf"], "keras": ["keras"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"], "pandas": ["pandas"], "numpy": ["numpy"],
    "spark": ["spark", "pyspark", "apache spark"], "hadoop": ["hadoop"], "kafka": ["kafka", "apache kafka"],
    "airflow": ["airflow"], "etl": ["etl"], "data structures": ["data structures", "dsa"],
    "algorithms": ["algorithms", "algorithm"], "statistics": ["statistics", "statistical"],
    "tableau": ["tableau"], "power bi": ["power bi", "powerbi"], "excel": ["excel"],
    # databases
    "postgresql": ["postgresql", "postgres", "psql"], "mysql": ["mysql"], "mongodb": ["mongodb", "mongo"],
    "redis": ["redis"], "sqlite": ["sqlite"], "dynamodb": ["dynamodb"], "cassandra": ["cassandra"],
    "elasticsearch": ["elasticsearch", "elastic search"], "firebase": ["firebase"], "nosql": ["nosql"],
    "sqlalchemy": ["sqlalchemy"], "orm": ["orm"],
    # cloud / devops
    "aws": ["aws", "amazon web services"], "gcp": ["gcp", "google cloud"], "azure": ["azure"],
    "docker": ["docker", "containers", "containerization"], "kubernetes": ["kubernetes", "k8s"],
    "terraform": ["terraform"], "ci/cd": ["ci/cd", "cicd", "ci cd", "continuous integration", "github actions", "jenkins"],
    "linux": ["linux", "unix"], "git": ["git", "github", "gitlab", "version control"], "serverless": ["serverless", "lambda"],
    "vercel": ["vercel"], "nginx": ["nginx"], "microservices": ["microservices", "microservice"],
    # cs fundamentals / practices
    "system design": ["system design", "distributed systems", "scalability", "scalable"],
    "oop": ["oop", "oops", "object oriented", "object-oriented"], "dbms": ["dbms", "database management"],
    "operating systems": ["operating systems", "operating system"], "computer networks": ["computer networks", "networking", "tcp/ip"],
    "multithreading": ["multithreading", "concurrency", "multi-threading"], "unit testing": ["unit testing", "unit tests", "pytest", "junit", "jest"],
    "agile": ["agile", "scrum"], "api design": ["api design"], "caching": ["caching", "cache"],
    "security": ["security", "oauth", "jwt", "authentication"], "debugging": ["debugging"],
    "competitive programming": ["competitive programming", "codeforces", "leetcode", "codechef"],
}

STOPWORDS = set("""
a about above after again against all also am an and any are as at be because been before being below between both
but by can could did do does doing down during each etc few for from further had has have having he her here hers
him his how i if in into is it its itself just me more most my no nor not now of off on once only or other our ours
out over own same she should so some such than that the their them then there these they this those through to too
under until up very was we were what when where which while who whom why will with would you your yours
using use used via within across etc. e.g i.e per plus including include includes like well new good great
""".split())

# Words that appear in every JD and say nothing about fit.
JD_NOISE = set("""
experience experiences year years work working team teams strong ability able skills skill knowledge understanding
role roles candidate candidates company job position responsibilities responsibility requirements required
requirement preferred plus must should looking join opportunity opportunities apply applicants degree bachelor
bachelors master masters btech b.tech be b.e mtech graduate graduates graduating freshers fresher batch cgpa
salary ctc lpa location bangalore bengaluru hyderabad pune chennai mumbai delhi gurgaon gurugram noida india
remote hybrid office onsite full time full-time intern internship days etc ensure help helps make makes build
building develop developing developer developers engineer engineers engineering software including various multiple
excellent good great solid proven hands hands-on familiarity familiar exposure proficiency proficient minimum
equivalent related field fields environment environments product products business customer customers
users user problems problem solving solve high quality quality best practices practice deliver delivering
part across day within based key well e.g. i.e. etc. will can may per other others new one two three
""".split())

_ALIAS_PATTERNS = []
for _canon, _aliases in TECH_TERMS.items():
    for _alias in _aliases:
        _ALIAS_PATTERNS.append((_canon, re.compile(r"(?<![a-z0-9+#])" + re.escape(_alias) + r"(?![a-z0-9+#])")))
# Longest aliases first so "react native" claims its text before "react".
_ALIAS_PATTERNS.sort(key=lambda p: -len(p[1].pattern))

_WORD_RE = re.compile(r"[a-z][a-z0-9+#]*(?:[.\-][a-z0-9+#]+)*")


def _norm_word(w):
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def extract_terms(text):
    """Returns (tech_terms: set of canonical names, words: Counter of other meaningful words)."""
    text = (text or "").lower()
    tech = set()
    masked = text
    for canon, pat in _ALIAS_PATTERNS:
        if pat.search(masked):
            tech.add(canon)
            masked = pat.sub(" ", masked)
    words = Counter()
    for w in _WORD_RE.findall(masked):
        if len(w) < 3 or w in STOPWORDS or w in JD_NOISE:
            continue
        w = _norm_word(w)
        if w in STOPWORDS or w in JD_NOISE:
            continue
        words[w] += 1
    return tech, words


def keyword_overlap(resume_text, jd_text, max_words=15):
    """Deterministic resume vs JD overlap. Tech terms weigh 2, other recurring JD words weigh 1."""
    jd_tech, jd_words = extract_terms(jd_text)
    cv_tech, cv_words = extract_terms(resume_text)
    # Generic JD words worth checking: recurring ones first, then single mentions, capped.
    generic = [w for w, c in jd_words.most_common() if c >= 2][:max_words]
    if len(generic) < 5:
        generic += [w for w, _ in jd_words.most_common() if w not in generic][:5 - len(generic)]

    matched, missing = [], []
    got = total = 0
    for t in sorted(jd_tech):
        total += 2
        if t in cv_tech:
            got += 2
            matched.append(t)
        else:
            missing.append(t)
    gen_matched, gen_missing = [], []
    for w in generic:
        total += 1
        if w in cv_words:
            got += 1
            gen_matched.append(w)
        else:
            gen_missing.append(w)
    return {
        "score": round(100 * got / total) if total else 0,
        "matched": matched + gen_matched,
        "missing": missing + gen_missing,
        "tech_matched": matched,
        "tech_missing": missing,
        "jd_terms": len(jd_tech) + len(generic),
    }


# ---------------- serialization ----------------
def _serialize_resume(r, full=True):
    data = {
        "id": r.id,
        "label": r.label,
        "chars": len(r.text or ""),
        "preview": (r.text or "")[:160],
        "created_at": _iso(r.created_at),
    }
    if full:
        data["text"] = r.text
    return data


def _serialize_story(s):
    polished = None
    if s.polished:
        try:
            polished = json.loads(s.polished)
        except ValueError:
            polished = None
    return {
        "id": s.id,
        "title": s.title,
        "situation": s.situation or "",
        "task": s.task or "",
        "action": s.action or "",
        "result": s.result or "",
        "tags": [t for t in (s.tags or "").split(",") if t],
        "draft": bool(s.draft),
        "polished": polished,
        "created_at": _iso(s.created_at),
        "updated_at": _iso(s.updated_at),
    }


def _is_due(c, today):
    return bool(c.follow_up and c.follow_up <= today and c.status not in CLOSED_STATUSES)


def _serialize_contact(c, today):
    return {
        "id": c.id,
        "name": c.name,
        "company": c.company or "",
        "role": c.role or "",
        "link": c.link or "",
        "how_known": c.how_known or "",
        "status": c.status,
        "last_contact": c.last_contact.isoformat() if c.last_contact else None,
        "follow_up": c.follow_up.isoformat() if c.follow_up else None,
        "notes": c.notes or "",
        "due": _is_due(c, today),
        "created_at": _iso(c.created_at),
        "updated_at": _iso(c.updated_at),
    }


# ======================= 1. Resume <-> JD =======================
MATCH_SYSTEM = """You are a blunt, kind placement mentor reviewing an Indian CS final-year student's resume against one job description.
Rules you must never break:
- NEVER invent metrics, numbers, technologies, employers, projects or experience that are not in the resume.
- When a bullet would be stronger with a number the resume doesn't give, write a placeholder like [X%], [N users], [Y ms] and say in `why` which real number to fill in.
- Rewrites must stay truthful to the original bullet: sharpen the verb, surface the impact, add JD keywords ONLY if the original clearly implies that skill.
- missing_keywords are JD skills/terms the resume does not show; matched_keywords are JD skills the resume does show.
Return JSON only:
{"score": <integer 0-100, honest fit for this JD>,
 "missing_keywords": ["..."], "matched_keywords": ["..."],
 "weak_bullets": [{"original": "<exact bullet from the resume>", "rewrite": "<improved bullet, placeholders for unknown numbers>", "why": "<one line>"}],
 "summary": "<2-3 sentences: overall fit and the top things to change before applying>"}
Give at most 12 keywords per list and 3-6 weak_bullets (the weakest ones)."""


def _normalize_match(raw):
    if not isinstance(raw, dict):
        raise ValueError("model did not return an object")
    try:
        score = int(round(float(raw.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    bullets = []
    for b in raw.get("weak_bullets") or []:
        if not isinstance(b, dict):
            continue
        original, rewrite = _s(b.get("original"), 600), _s(b.get("rewrite"), 600)
        if original and rewrite:
            bullets.append({"original": original, "rewrite": rewrite, "why": _s(b.get("why"), 300)})
        if len(bullets) >= 8:
            break
    return {
        "score": max(0, min(100, score)),
        "missing_keywords": _str_list(raw.get("missing_keywords"), 15),
        "matched_keywords": _str_list(raw.get("matched_keywords"), 15),
        "weak_bullets": bullets,
        "summary": _s(raw.get("summary"), 1200),
    }


@career_bp.route("/resume", methods=["GET"])
def list_resumes():
    db = SessionLocal()
    try:
        rows = db.query(ResumeVersion).order_by(ResumeVersion.created_at.desc(), ResumeVersion.id.desc()).all()
        return jsonify({"status": "success", "data": [_serialize_resume(r) for r in rows]})
    finally:
        db.close()


@career_bp.route("/resume", methods=["POST"])
def create_resume():
    data = _body()
    try:
        text = _str(data.get("text"), "Resume text", MAX_RESUME, required=True)
        label = _str(data.get("label"), "Label", MAX_LABEL)
    except _Invalid as e:
        return _err(str(e))
    db = SessionLocal()
    try:
        r = ResumeVersion(label=label or f"Resume · {_today().strftime('%d %b %Y')}", text=text)
        db.add(r)
        db.commit()
        db.refresh(r)
        return jsonify({"status": "success", "data": _serialize_resume(r)})
    finally:
        db.close()


@career_bp.route("/resume/<int:resume_id>", methods=["GET", "DELETE"])
def resume_detail(resume_id):
    db = SessionLocal()
    try:
        r = db.get(ResumeVersion, resume_id)
        if not r:
            return _err("Resume version not found", 404)
        if request.method == "DELETE":
            db.delete(r)
            db.commit()
            return jsonify({"status": "success"})
        return jsonify({"status": "success", "data": _serialize_resume(r)})
    finally:
        db.close()


@career_bp.route("/match", methods=["POST"])
def match_resume():
    data = _body()
    try:
        jd = _str(data.get("jd_text"), "Job description", MAX_JD, required=True)
        resume_text = _str(data.get("resume_text"), "Resume text", MAX_RESUME)
    except _Invalid as e:
        return _err(str(e))
    resume_id = data.get("resume_id")
    if not resume_text:
        if resume_id in (None, ""):
            return _err("Paste your resume or pick a saved version.")
        if isinstance(resume_id, bool) or not isinstance(resume_id, (int, str)) or not str(resume_id).isdigit():
            return _err("resume_id must be a number.")
        db = SessionLocal()
        try:
            r = db.get(ResumeVersion, int(resume_id))
            if not r:
                return _err("Resume version not found", 404)
            resume_text = r.text
        finally:
            db.close()
    if len(jd) < 40:
        return _err("Paste the full job description (at least a few lines).")

    keywords = keyword_overlap(resume_text, jd)
    ai, ai_error = None, None
    prompt = (f"JOB DESCRIPTION:\n\"\"\"\n{jd}\n\"\"\"\n\nRESUME:\n\"\"\"\n{resume_text}\n\"\"\"\n\n"
              f"For reference, a keyword scan found these JD terms missing from the resume: {', '.join(keywords['missing'][:20]) or 'none'}.")
    try:
        ai = _normalize_match(_llm_json(prompt, MATCH_SYSTEM, temperature=0.3))
    except Exception as e:
        print(f"career match AI failed: {str(e)[:200]}")
        ai_error = _friendly(e)
    return jsonify({"status": "success", "data": {"keywords": keywords, "ai": ai, "ai_error": ai_error}})


# ======================= 2. STAR stories =======================
EXAMPLE_STORY = {
    "title": "Built 'Daily', my own placement-prep dashboard",
    "situation": ("Final year, placement season: my prep was scattered across LeetCode, Codeforces, notes and "
                  "calendar reminders, and I kept forgetting problems I'd solved weeks earlier."),
    "task": ("I decided to build one app that tells me what to revise, what to practise and how ready I am, "
             "and to ship it to production for free so I'd actually use it daily."),
    "action": ("Built a Flask API on Vercel serverless with Neon Postgres and a React + Tailwind frontend. "
               "Used the FSRS spaced-repetition algorithm to schedule problem revisions, an Elo-style rating to "
               "pick problems at the right difficulty, and a Monte Carlo simulation to estimate exam / contest "
               "readiness. Added Gemini for AI write-ups and mock interviews, with fallbacks and time budgets "
               "because the free tier is slow. Wrote pytest tests against SQLite so I could ship changes safely."),
    "result": ("I use it every day; it schedules [N] revisions a week and my revision recall went from [X%] to "
               "[Y%]. Fill in real numbers before using this story; also mention one thing that went wrong "
               "(e.g. serverless timeouts) and how you fixed it."),
    "tags": "ownership,tech-depth",
}


def _seed_example(db):
    """Insert the example story once ever (tracked in career_meta, so deleting it is permanent)."""
    if db.get(CareerMeta, "story_seeded"):
        return
    try:
        db.add(CareerMeta(key="story_seeded", value=_today().isoformat()))
        db.add(Story(draft=True, **EXAMPLE_STORY))
        db.commit()
    except IntegrityError:  # another request seeded it first
        db.rollback()


def _story_fields(data, story=None):
    """Validates and applies the editable fields. On create (story=None) the title is required."""
    out = {}
    if story is None or "title" in data:
        out["title"] = _str(data.get("title"), "Title", MAX_TITLE, required=True)
    for f in ("situation", "task", "action", "result"):
        if story is None or f in data:
            out[f] = _str(data.get(f), f.capitalize(), MAX_STAR)
    if story is None or "tags" in data:
        out["tags"] = ",".join(_tags(data.get("tags")))
    if "draft" in data:
        out["draft"] = bool(data.get("draft"))
    return out


@career_bp.route("/stories", methods=["GET"])
def list_stories():
    db = SessionLocal()
    try:
        _seed_example(db)
        rows = db.query(Story).order_by(Story.updated_at.desc(), Story.id.desc()).all()
        return jsonify({"status": "success", "data": [_serialize_story(s) for s in rows], "tags": STORY_TAGS})
    finally:
        db.close()


@career_bp.route("/stories", methods=["POST"])
def create_story():
    try:
        fields = _story_fields(_body())
    except _Invalid as e:
        return _err(str(e))
    db = SessionLocal()
    try:
        s = Story(**fields)
        db.add(s)
        db.commit()
        db.refresh(s)
        return jsonify({"status": "success", "data": _serialize_story(s)})
    finally:
        db.close()


@career_bp.route("/stories/<int:story_id>", methods=["GET", "PUT", "DELETE"])
def story_detail(story_id):
    db = SessionLocal()
    try:
        s = db.get(Story, story_id)
        if not s:
            return _err("Story not found", 404)
        if request.method == "GET":
            return jsonify({"status": "success", "data": _serialize_story(s)})
        if request.method == "DELETE":
            db.delete(s)
            db.commit()
            return jsonify({"status": "success"})
        try:
            fields = _story_fields(_body(), s)
        except _Invalid as e:
            return _err(str(e))
        for k, v in fields.items():
            setattr(s, k, v)
        s.updated_at = _utcnow()
        db.commit()
        db.refresh(s)
        return jsonify({"status": "success", "data": _serialize_story(s)})
    finally:
        db.close()


POLISH_SYSTEM = """You coach Indian CS students for behavioral interview rounds (SDE / ML roles).
Turn the student's STAR notes into a spoken answer of about 90 seconds (180-230 words), first person, natural and confident, not robotic.
Structure: one line of context, the challenge, what *I* did (most of the time here, concrete), the result, one line of reflection / learning.
Rules: NEVER invent facts, numbers, names or outcomes that are not in the notes. If a number would help and is missing, keep a placeholder like [X%] or [N users].
Then list exactly 3 follow-up questions an interviewer is most likely to ask about this story.
Return JSON only: {"answer": "...", "follow_ups": ["...", "...", "..."], "tip": "<one short delivery tip>"}"""


@career_bp.route("/stories/<int:story_id>/polish", methods=["POST"])
def polish_story(story_id):
    db = SessionLocal()
    try:
        s = db.get(Story, story_id)
        if not s:
            return _err("Story not found", 404)
        if not any((s.situation, s.task, s.action, s.result)):
            return _err("Fill in at least the Situation and Action first.")
        prompt = (f"Title: {s.title}\nTags: {s.tags or 'none'}\n\nSituation: {s.situation or '-'}\n"
                  f"Task: {s.task or '-'}\nAction: {s.action or '-'}\nResult: {s.result or '-'}")
        try:
            raw = _llm_json(prompt, POLISH_SYSTEM, temperature=0.5)
            if not isinstance(raw, dict):
                raise ValueError("model did not return an object")
            answer = _s(raw.get("answer"), 3000)
            if len(answer) < 40:
                raise ValueError("empty answer")
        except Exception as e:
            print(f"career polish failed: {str(e)[:200]}")
            return _err(_friendly(e), 502)
        words = len(answer.split())
        polished = {
            "answer": answer,
            "follow_ups": _str_list(raw.get("follow_ups"), 3, 300),
            "tip": _s(raw.get("tip"), 300),
            "words": words,
            "seconds": round(words / 2.4),  # ~145 spoken words per minute
            "at": _iso(_utcnow()),
        }
        s.polished = json.dumps(polished)
        db.commit()
        db.refresh(s)
        return jsonify({"status": "success", "data": _serialize_story(s)})
    finally:
        db.close()


# ======================= 3. Referral tracker =======================
def _contact_fields(data, contact=None):
    out = {}
    if contact is None or "name" in data:
        out["name"] = _str(data.get("name"), "Name", 120, required=True)
    for f, label, n in (("company", "Company", 120), ("role", "Role", 160), ("how_known", "How you know them", 200),
                        ("notes", "Notes", MAX_NOTES)):
        if contact is None or f in data:
            out[f] = _str(data.get(f), label, n)
    if contact is None or "link" in data:
        link = _str(data.get("link"), "Link", 500)
        if link and not re.match(r"^https?://", link, re.I):
            link = "https://" + link
        out["link"] = link
    if contact is None or "status" in data:
        status = data.get("status") if contact is not None or data.get("status") else "to-ask"
        status = status.strip().lower() if isinstance(status, str) else ""
        if status not in CONTACT_STATUSES:
            raise _Invalid(f"Status must be one of: {', '.join(CONTACT_STATUSES)}.")
        out["status"] = status
    for f, label in (("last_contact", "Last contact"), ("follow_up", "Follow-up")):
        if contact is None or f in data:
            out[f] = _date(data.get(f), label)
    return out


def _contacts_sorted(rows, today):
    # Due first (oldest follow-up first), then open ones by follow-up date, closed last.
    def key(c):
        closed = c.status in CLOSED_STATUSES
        return (closed, not _is_due(c, today), c.follow_up or date.max, -(c.id or 0))
    return sorted(rows, key=key)


@career_bp.route("/contacts", methods=["GET"])
def list_contacts():
    db = SessionLocal()
    try:
        today = _today()
        rows = _contacts_sorted(db.query(Contact).all(), today)
        counts = Counter(c.status for c in rows)
        return jsonify({
            "status": "success",
            "data": [_serialize_contact(c, today) for c in rows],
            "due_count": sum(1 for c in rows if _is_due(c, today)),
            "counts": {s: counts.get(s, 0) for s in CONTACT_STATUSES},
            "statuses": CONTACT_STATUSES,
            "today": today.isoformat(),
        })
    finally:
        db.close()


@career_bp.route("/contacts/due", methods=["GET"])
def due_contacts():
    db = SessionLocal()
    try:
        today = _today()
        rows = (db.query(Contact)
                .filter(Contact.follow_up.isnot(None), Contact.follow_up <= today,
                        Contact.status.notin_(list(CLOSED_STATUSES)))
                .order_by(Contact.follow_up, Contact.id).all())
        return jsonify({"status": "success", "data": [_serialize_contact(c, today) for c in rows],
                        "total": len(rows), "today": today.isoformat()})
    finally:
        db.close()


@career_bp.route("/contacts", methods=["POST"])
def create_contact():
    try:
        fields = _contact_fields(_body())
    except _Invalid as e:
        return _err(str(e))
    db = SessionLocal()
    try:
        c = Contact(**fields)
        db.add(c)
        db.commit()
        db.refresh(c)
        return jsonify({"status": "success", "data": _serialize_contact(c, _today())})
    finally:
        db.close()


@career_bp.route("/contacts/<int:contact_id>", methods=["GET", "PUT", "DELETE"])
def contact_detail(contact_id):
    db = SessionLocal()
    try:
        c = db.get(Contact, contact_id)
        if not c:
            return _err("Contact not found", 404)
        if request.method == "GET":
            return jsonify({"status": "success", "data": _serialize_contact(c, _today())})
        if request.method == "DELETE":
            db.delete(c)
            db.commit()
            return jsonify({"status": "success"})
        try:
            fields = _contact_fields(_body(), c)
        except _Invalid as e:
            return _err(str(e))
        for k, v in fields.items():
            setattr(c, k, v)
        c.updated_at = _utcnow()
        db.commit()
        db.refresh(c)
        return jsonify({"status": "success", "data": _serialize_contact(c, _today())})
    finally:
        db.close()


DRAFT_SYSTEM = """You help an Indian CS final-year student write a referral request they will copy and send themselves (LinkedIn DM / WhatsApp / email).
Write it like a real person, not a template: short (70-120 words), warm, specific, respectful of the reader's time.
- Open with the real connection (how they know each other) if given; no fake familiarity, no flattery, no "I hope this finds you well".
- One or two lines on why the student fits THIS role, using only facts from the notes / job description given. NEVER invent achievements, numbers or shared history. Use placeholders like [your project] or [job link] where a detail is missing.
- A clear, easy ask (a referral for the role, or a quick 10-minute chat if they don't know the student well), and offer to share resume + job ID.
- Polite, zero pressure; no emojis, no hashtags, no ALL CAPS.
If the status is "asked" this is a gentle follow-up: even shorter (40-70 words), acknowledge they're busy.
Return JSON only: {"subject": "<short subject line for email, else empty>", "message": "..."}"""


@career_bp.route("/contacts/<int:contact_id>/draft", methods=["POST"])
def draft_message(contact_id):
    data = _body()
    try:
        jd = _str(data.get("jd_text"), "Job description", MAX_JD)
    except _Invalid as e:
        return _err(str(e))
    db = SessionLocal()
    try:
        c = db.get(Contact, contact_id)
        if not c:
            return _err("Contact not found", 404)
        lines = [f"Contact name: {c.name}", f"Company: {c.company or 'unknown'}", f"Their role: {c.role or 'unknown'}",
                 f"How we know each other: {c.how_known or 'not stated (treat as a cold but polite message)'}",
                 f"Status: {c.status}"]
        if c.last_contact:
            lines.append(f"Last contacted: {c.last_contact.isoformat()}")
        if c.notes:
            lines.append(f"My notes: {c.notes}")
        if jd:
            lines.append(f"Job description:\n\"\"\"\n{jd}\n\"\"\"")
        try:
            raw = _llm_json("\n".join(lines), DRAFT_SYSTEM, temperature=0.7)
            if not isinstance(raw, dict):
                raise ValueError("model did not return an object")
            message = _s(raw.get("message"), 2000)
            if len(message) < 20:
                raise ValueError("empty message")
        except Exception as e:
            print(f"career draft failed: {str(e)[:200]}")
            return _err(_friendly(e), 502)
        return jsonify({"status": "success", "data": {"subject": _s(raw.get("subject"), 200), "message": message,
                                                       "contact_id": c.id}})
    finally:
        db.close()
