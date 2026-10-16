"""
Application pack for one Job Radar opening: paste-ready text for the official application form.

Integrity (docs/JOB_APPLICATION_SYSTEM_AND_GOALS.txt): nothing here applies anywhere. The pack is text Sai copies
into the company's own form. Every claim comes from RESUME_FACTS or from the job's company / role / location /
listed skills; nothing else is invented.

Design:
  - RESUME_FACTS: the only facts about Sai the pack may use (education, experience, projects, CP, skills).
  - Resume highlights are picked deterministically (skill + role-keyword overlap), never by the LLM.
  - One LLM call (LLMClient.generate_json) writes the free-text parts; its output is cleaned (markdown, emojis,
    hype words), trimmed to word limits, and any field that cites a number not in the facts or the job falls back
    to the template for that field. If the LLM fails, the whole pack comes from the deterministic template.
  - Factual answers (availability, graduation, relocation) are always deterministic.
  - Cached per job in `job_packs`; `?refresh=1` regenerates.

Endpoint (blueprint job_pack_bp, prefix /api/jobs; passcode-protected by app.before_request):
  GET /api/jobs/<job_id>/pack[?refresh=1]
"""
import json
import re
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.exc import IntegrityError

from api.core.clients import LLMClient
from api.core.db import Base, SessionLocal, engine
from api.domain.job_radar import JobOpportunity, JobRadarProfile

COVER_MAX_WORDS = 150
WHY_COMPANY_MAX_WORDS = 80
ANSWER_MAX_WORDS = 120
LLM_BUDGET = 60          # seconds across the Gemini -> OpenRouter fallback chain
TEMPERATURE = 0.4
TEMPLATE_MODEL = "template"
DEFAULT_LOCATIONS = "Bengaluru, Hyderabad, Gurugram, Remote"


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------- Resume facts (the only facts the pack may use) ----------------
RESUME_FACTS = {
    "name": "Nandam Venkata Sai Raghava",
    "education": "B.Tech in Computer Science and Engineering, NIT Rourkela (2023–2027), CGPA 8.99.",
    "graduation_year": 2027,
    "skills": ["C++", "Python", "JavaScript", "SQL", "React", "Node.js", "Express", "Kafka", "Redis",
               "Elasticsearch", "PostgreSQL", "MongoDB"],
    # Each highlight: resume bullet, first-person sentence, and skill tags (canonical form) used for matching.
    "highlights": [
        {"id": "railway",
         "bullet": "Distributed Railway Reservation: 8 microservices, 13 Kafka topics, Redis Lua locks with Postgres "
                   "row locks, Saga-based rollback, API gateway with rate limiting and circuit breakers, Elasticsearch search.",
         "sentence": "I built a distributed railway reservation system with 8 microservices and 13 Kafka topics, using "
                     "Redis Lua locks with Postgres row locks, the Saga pattern, and an API gateway with rate limiting "
                     "and circuit breakers.",
         "tags": ["kafka", "redis", "postgresql", "elasticsearch", "microservices", "distributed", "sql", "rest"]},
        {"id": "maruti",
         "bullet": "Software Engineering Intern, Maruti Suzuki (May–Jul 2026): built a MERN portal with 13 React pages "
                   "and 120+ REST APIs, secured with JWT and role-based access control (RBAC).",
         "sentence": "During my software engineering internship at Maruti Suzuki (May to July 2026) I built a MERN portal "
                     "with 13 React pages and more than 120 REST APIs, secured with JWT and role-based access control.",
         "tags": ["react", "node", "express", "mongodb", "javascript", "rest"]},
        {"id": "cache",
         "bullet": "Cache Server (C++): Redis-compatible server speaking RESP with 30 commands, TTL expiry, O(1) LRU/LFU "
                   "eviction and a thread pool.",
         "sentence": "I wrote a Redis-compatible cache server in C++ that speaks the RESP protocol, supports 30 commands "
                     "with TTL, has O(1) LRU and LFU eviction, and serves clients from a thread pool.",
         "tags": ["c++", "redis", "multithreading", "dsa"]},
        {"id": "dataannotation",
         "bullet": "Coding Expert, DataAnnotation: fixed XTC sampling in the llama.cpp C++ inference engine while "
                   "preserving API compatibility, verified with regression tests.",
         "sentence": "As a Coding Expert at DataAnnotation I fixed XTC sampling in the llama.cpp C++ inference engine "
                     "and kept the API compatible, with regression tests to confirm it.",
         "tags": ["c++", "llm", "testing"]},
        {"id": "cp",
         "bullet": "Competitive programming: LeetCode contest rating 1709 (900+ solved), Codeforces Specialist "
                   "(peak 1425), CodeChef 3-star (1632).",
         "sentence": "My LeetCode contest rating is 1709 with more than 900 problems solved, I am a Codeforces "
                     "Specialist (peak 1425), and I am 3-star on CodeChef (1632).",
         "tags": ["dsa", "c++", "python"]},
        {"id": "react_comps",
         "bullet": "React-Comps: generates React components with an LLM, with Firebase authentication, Razorpay "
                   "payments and NPM publishing.",
         "sentence": "I built React-Comps, which generates React components with an LLM and includes Firebase "
                     "authentication, Razorpay payments and NPM publishing.",
         "tags": ["react", "javascript", "llm"]},
    ],
}

_HIGHLIGHTS = {h["id"]: h for h in RESUME_FACTS["highlights"]}
_DEFAULT_ORDER = [h["id"] for h in RESUME_FACTS["highlights"]]

# Role-title keywords -> highlights they point at (a small bonus on top of skill overlap).
_ROLE_HINTS = [
    (re.compile(r"front[- ]?end|full[- ]?stack|\bweb\b|\breact\b|\bui\b", re.I), ("maruti", "react_comps")),
    (re.compile(r"back[- ]?end|platform|infrastructure|distributed|\bsre\b|site reliability|\bsystems?\b", re.I),
     ("railway", "cache")),
    (re.compile(r"machine learning|\bml\b|\bai\b|\bllms?\b|inference", re.I), ("dataannotation", "react_comps")),
    (re.compile(r"c\+\+|performance|storage|database|low[- ]latency", re.I), ("cache", "dataannotation")),
]

_ALIASES = {
    "node": "node", "nodejs": "node", "express": "express", "expressjs": "express", "react": "react",
    "reactjs": "react", "postgres": "postgresql", "postgresql": "postgresql", "mongo": "mongodb", "mongodb": "mongodb",
    "javascript": "javascript", "js": "javascript", "c++": "c++", "cpp": "c++", "python": "python", "sql": "sql",
    "kafka": "kafka", "apachekafka": "kafka", "redis": "redis", "elasticsearch": "elasticsearch",
    "microservices": "microservices", "microservice": "microservices", "distributedsystems": "distributed",
    "distributed": "distributed", "restapis": "rest", "rest": "rest", "restfulapis": "rest", "llms": "llm",
    "llm": "llm", "multithreading": "multithreading", "concurrency": "multithreading", "dsa": "dsa",
    "datastructuresalgorithms": "dsa", "datastructuresandalgorithms": "dsa", "algorithms": "dsa",
    "git": "git", "linux": "linux", "testing": "testing",
}


def _canon(skill):
    key = re.sub(r"[^a-z0-9+]", "", str(skill or "").lower())
    return _ALIASES.get(key, key)


# Every skill Sai can honestly claim: the listed skills plus what the highlights demonstrate.
_CLAIMABLE = {_canon(s) for s in RESUME_FACTS["skills"]} | {t for h in RESUME_FACTS["highlights"] for t in h["tags"]} | {"git", "linux"}

# ---------------- Template text (deterministic fallback) ----------------
PROJECT_STORIES = {
    "railway": "The hardest project I have built is a distributed railway reservation system. It runs as 8 "
               "microservices that talk over 13 Kafka topics. The difficult part was keeping bookings consistent under "
               "concurrent requests: I combined Redis Lua locks with Postgres row locks, and used the Saga pattern so a "
               "failed step undoes the earlier ones. An API gateway adds rate limiting and circuit breakers, and "
               "Elasticsearch handles search.",
    "cache": "A challenging project was a Redis-compatible cache server in C++. I wrote the RESP protocol handling and "
             "30 commands with TTL expiry. The hard parts were making LRU and LFU eviction O(1) and serving many "
             "clients through a thread pool while keeping the data correct.",
    "dataannotation": "At DataAnnotation I fixed XTC sampling in llama.cpp, a C++ inference engine. The challenge was "
                      "changing sampling behaviour inside an existing codebase without breaking the code that depends "
                      "on it, so I kept the API compatible and added regression tests to confirm the behaviour.",
    "maruti": "At Maruti Suzuki I built a MERN portal with 13 React pages and more than 120 REST APIs. The challenge "
              "was keeping that many endpoints secure and consistent, which I handled with JWT authentication and "
              "role-based access control.",
}

SKILL_STORIES = [
    ("cpp", {"c++", "multithreading", "dsa", "llm"},
     "C++. I used it to write a Redis-compatible cache server (RESP protocol, 30 commands, TTL, O(1) LRU/LFU "
     "eviction, thread pool) and to fix XTC sampling in the llama.cpp inference engine at DataAnnotation. Alongside "
     "this, my LeetCode contest rating is 1709 and I am a Codeforces Specialist (peak 1425)."),
    ("backend", {"kafka", "redis", "postgresql", "elasticsearch", "microservices", "distributed", "sql"},
     "Backend and distributed systems. My railway reservation project uses 8 microservices, 13 Kafka topics, Redis "
     "Lua locks with Postgres row locks, the Saga pattern and an API gateway with rate limiting and circuit breakers. "
     "I also wrote a Redis-compatible cache server in C++."),
    ("web", {"react", "node", "express", "javascript", "mongodb", "rest"},
     "Full-stack JavaScript with React, Node.js and Express. At Maruti Suzuki I built a MERN portal with 13 React "
     "pages and more than 120 REST APIs secured with JWT and role-based access control, and I built React-Comps "
     "with Firebase authentication and Razorpay payments."),
]
_SKILL_ROLE_HINTS = {"web": re.compile(r"front[- ]?end|full[- ]?stack|\bweb\b|\breact\b", re.I),
                     "backend": re.compile(r"back[- ]?end|platform|infrastructure|distributed|\bsre\b", re.I)}

QUESTIONS = [
    ("why_role", "Why are you interested in this role?"),
    ("challenging_project", "Describe a challenging project you worked on."),
    ("strongest_skill", "What is your strongest technical skill?"),
    ("availability", "What is your notice period or availability?"),
    ("graduation", "What is your expected graduation date?"),
    ("relocation", "Are you willing to relocate?"),
]
_LLM_ANSWER_KEYS = ("why_role", "challenging_project", "strongest_skill")

# ---------------- Text hygiene ----------------
BANNED_WORDS = ("passionate", "passion", "leverage", "delve", "seamless", "cutting-edge", "synergy")
_REPLACEMENTS = [
    (re.compile(r"\bpassionate about\b", re.I), "interested in"),
    (re.compile(r"\bpassionate\b", re.I), "keen"),
    (re.compile(r"\bpassion for\b", re.I), "interest in"),
    (re.compile(r"\bpassion\b", re.I), "interest"),
    (re.compile(r"\bleverag(e|es|ed|ing)\b", re.I), lambda m: "us" + m.group(1)),
    (re.compile(r"\bdelv(e|es|ed|ing)\b", re.I),
     lambda m: {"e": "look", "es": "looks", "ed": "looked", "ing": "looking"}[m.group(1).lower()]),
    (re.compile(r"\bseamless(ly)?\b", re.I), lambda m: "smooth" + (m.group(1) or "")),
    (re.compile(r"\bcutting[- ]edge\b", re.I), "modern"),
    (re.compile(r"\bsynerg(y|ies)\b", re.I), "fit"),
]
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_PLACEHOLDER = re.compile(r"\[[^\]]*\]|\{[^}]*\}|<[^>]*>")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _match_case(src, repl):
    return repl[:1].upper() + repl[1:] if src[:1].isupper() else repl


def remove_banned(text):
    for pattern, repl in _REPLACEMENTS:
        text = pattern.sub(lambda m, r=repl: _match_case(m.group(0), r(m) if callable(r) else r), text)
    return text


def clean_text(value):
    """Plain text: no markdown, no emojis, no hype words, tidy whitespace (paragraph breaks kept)."""
    if not isinstance(value, str):
        return ""
    text = _MD_LINK.sub(r"\1", value.replace("\r\n", "\n"))
    text = _EMOJI.sub("", text)
    text = text.replace("**", "").replace("__", "").replace("`", "").replace("*", "")
    lines = []
    for line in text.split("\n"):
        if re.match(r"^\s*#{1,6}\s", line):  # markdown headings are labels, not answer text
            continue
        line = re.sub(r"^\s*([-•]\s+|\d+[.)]\s+|>\s*)", "", line)
        lines.append(re.sub(r"[ \t]+", " ", line).strip())
    text = "\n".join(lines)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)  # single newlines (wrapped lines, bullets) become spaces
    text = re.sub(r"\n{2,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return remove_banned(text).strip()


def trim_words(text, limit):
    """Cut to at most `limit` words, ending on a sentence boundary when one is reasonably close."""
    words = list(re.finditer(r"\S+", text))
    if len(words) <= limit:
        return text
    cut = text[:words[limit - 1].end()]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "), cut.rfind(".\n"))
    if cut.endswith((".", "?", "!")):
        return cut
    if end >= len(cut) * 0.5:
        return cut[:end + 1]
    return cut.rstrip(",;:-– ") + "."


def word_count(text):
    return len(re.findall(r"\S+", text or ""))


# ---------------- Matching ----------------
def job_skills(job):
    try:
        skills = json.loads(job.skills_required or "[]")
    except (ValueError, TypeError):
        skills = []
    return [str(s) for s in skills if isinstance(s, (str, int, float))] if isinstance(skills, list) else []


def matched_skills(job):
    """Job-listed skills Sai can honestly claim, in the job's order, deduplicated."""
    out, seen = [], set()
    for s in job_skills(job):
        c = _canon(s)
        if c in _CLAIMABLE and c not in seen:
            seen.add(c)
            out.append(s)
    return out


SWE_TECH_KEYWORDS = [
    # Languages
    ("Java", re.compile(r"\bjava\b(?!script)", re.I)),
    ("Go", re.compile(r"\b(?:golang|go)\b", re.I)),
    ("C#", re.compile(r"\bc#|\bc-sharp\b", re.I)),
    (".NET", re.compile(r"\b\.net\b", re.I)),
    ("TypeScript", re.compile(r"\btypescript|\bts\b", re.I)),
    ("Rust", re.compile(r"\brust\b", re.I)),
    ("Ruby", re.compile(r"\bruby\b", re.I)),
    ("PHP", re.compile(r"\bphp\b", re.I)),
    ("Swift", re.compile(r"\bswift\b", re.I)),
    ("Kotlin", re.compile(r"\bkotlin\b", re.I)),
    ("Scala", re.compile(r"\bscala\b", re.I)),
    # Cloud & DevOps
    ("AWS", re.compile(r"\baws\b|amazon web services", re.I)),
    ("Azure", re.compile(r"\bazure\b", re.I)),
    ("GCP", re.compile(r"\bgcp\b|google cloud", re.I)),
    ("Docker", re.compile(r"\bdocker\b", re.I)),
    ("Kubernetes", re.compile(r"\b(?:kubernetes|k8s)\b", re.I)),
    ("Terraform", re.compile(r"\bterraform\b", re.I)),
    ("CI/CD", re.compile(r"\bci[/-]?cd\b", re.I)),
    ("Jenkins", re.compile(r"\bjenkins\b", re.I)),
    # Frameworks & Databases
    ("Spring Boot", re.compile(r"\bspring(?: boot)?\b", re.I)),
    ("Angular", re.compile(r"\bangular\b", re.I)),
    ("Vue", re.compile(r"\bvue(?:\.js)?\b", re.I)),
    ("Next.js", re.compile(r"\bnext\.?js\b", re.I)),
    ("Django", re.compile(r"\bdjango\b", re.I)),
    ("Flask", re.compile(r"\bflask\b", re.I)),
    ("FastAPI", re.compile(r"\bfastapi\b", re.I)),
    ("GraphQL", re.compile(r"\bgraphql\b", re.I)),
    ("gRPC", re.compile(r"\bgrpc\b", re.I)),
    ("RabbitMQ", re.compile(r"\brabbitmq\b", re.I)),
    ("Cassandra", re.compile(r"\bcassandra\b", re.I)),
    ("DynamoDB", re.compile(r"\bdynamodb\b", re.I)),
    ("Snowflake", re.compile(r"\bsnowflake\b", re.I)),
    ("Spark", re.compile(r"\bspark\b", re.I)),
    ("Hadoop", re.compile(r"\bhadoop\b", re.I)),
    ("PyTorch", re.compile(r"\bpytorch\b", re.I)),
    ("TensorFlow", re.compile(r"\btensorflow\b", re.I)),
    # Core SWE / Resume skills
    ("C++", re.compile(r"c\+\+|\bcpp\b", re.I)),
    ("Python", re.compile(r"\bpython\b", re.I)),
    ("JavaScript", re.compile(r"\bjavascript|\bjs\b", re.I)),
    ("SQL", re.compile(r"\bsql\b", re.I)),
    ("React", re.compile(r"\breact\b", re.I)),
    ("Node.js", re.compile(r"\bnode(?:\.js)?\b", re.I)),
    ("Express", re.compile(r"\bexpress(?:\.js)?\b", re.I)),
    ("Kafka", re.compile(r"\bkafka\b", re.I)),
    ("Redis", re.compile(r"\bredis\b", re.I)),
    ("Elasticsearch", re.compile(r"\belastic ?search\b", re.I)),
    ("PostgreSQL", re.compile(r"\bpostgres(?:ql)?\b", re.I)),
    ("MongoDB", re.compile(r"\bmongo(?:db)?\b", re.I)),
    ("Microservices", re.compile(r"\bmicro-?services?\b", re.I)),
    ("Distributed systems", re.compile(r"\bdistributed\b", re.I)),
    ("REST APIs", re.compile(r"\brest(?:ful)?\b", re.I)),
    ("Git", re.compile(r"\bgit\b", re.I)),
    ("Linux", re.compile(r"\blinux\b", re.I)),
    ("Multithreading", re.compile(r"\bmulti-?thread|concurren", re.I)),
    ("DSA", re.compile(r"\b(?:data structures|algorithms|dsa)\b", re.I)),
    ("LLMs", re.compile(r"\bllms?\b|large language", re.I)),
]


def skill_gap(job):
    """Compares job skills + role keywords with candidate's claimable resume facts.

    Returns:
      {
        'matched': [skills Sai can claim],
        'missing': [skills the role mentions that Sai does NOT claim],
        'match_ratio': float (0.0 to 1.0),
        'match_pct': int (0 to 100),
        'total_skills': int
      }
    """
    seen_canons = set()
    all_candidates = []

    # 1. Listed skills on the job opportunity
    for s in job_skills(job):
        c = _canon(s)
        if c and c not in seen_canons:
            seen_canons.add(c)
            all_candidates.append((s, c))

    # 2. Extract technical keywords from role title & notes text
    text = f"{getattr(job, 'role', '') or ''} {getattr(job, 'notes', '') or ''}"
    for label, pattern in SWE_TECH_KEYWORDS:
        if pattern.search(text):
            c = _canon(label)
            if c and c not in seen_canons:
                seen_canons.add(c)
                all_candidates.append((label, c))

    matched = []
    missing = []
    for label, c in all_candidates:
        if c in _CLAIMABLE:
            matched.append(label)
        else:
            missing.append(label)

    total = len(matched) + len(missing)
    ratio = round(len(matched) / total, 2) if total > 0 else 1.0
    pct = int(round(ratio * 100))

    return {
        "matched": matched,
        "missing": missing,
        "match_ratio": ratio,
        "match_pct": pct,
        "total_skills": total,
    }


def select_highlights(job, limit=5):
    """3-5 highlights ordered by how well they fit the job's skills and title."""
    canons = {_canon(s) for s in job_skills(job)}
    role = f"{job.role or ''}"
    scores = {}
    for h in RESUME_FACTS["highlights"]:
        scores[h["id"]] = 2 * len(canons & set(h["tags"]))
    for pattern, ids in _ROLE_HINTS:
        if pattern.search(role):
            for i in ids:
                scores[i] += 1
    ranked = sorted(_DEFAULT_ORDER, key=lambda i: (-scores[i], _DEFAULT_ORDER.index(i)))
    chosen = [i for i in ranked if scores[i] > 0][:limit]
    for i in ranked:
        if len(chosen) >= 3:
            break
        if i not in chosen:
            chosen.append(i)
    return [_HIGHLIGHTS[i] for i in chosen]


def _strongest_skill(job):
    canons = {_canon(s) for s in job_skills(job)}
    best = max(SKILL_STORIES, key=lambda s: (len(canons & s[1]) + (1 if s[0] in _SKILL_ROLE_HINTS
                                                                  and _SKILL_ROLE_HINTS[s[0]].search(job.role or "") else 0),
                                             -SKILL_STORIES.index(s)))
    return best[2]


def _join(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _location_prefs(db):
    try:
        prof = db.query(JobRadarProfile).filter(JobRadarProfile.id == 1).first()
        if prof and prof.location_pref:
            return prof.location_pref
    except Exception:
        db.rollback()
    return DEFAULT_LOCATIONS


# ---------------- Deterministic parts ----------------
def fixed_answers(job, location_prefs=DEFAULT_LOCATIONS):
    loc = (job.location or "").strip()
    where = f" to {loc}" if loc and loc.lower() not in ("india", "remote") and len(loc) <= 60 else ""
    if re.search(r"\bintern", job.role or "", re.I):
        availability = ("I am a full-time student at NIT Rourkela, graduating in 2027, so I have no notice period. "
                        "I can take up the internship on the dates the team sets, within my academic calendar.")
    else:
        availability = ("I am a full-time student, so I have no notice period. I graduate from NIT Rourkela in 2027 "
                        "and can join on the company's 2027 start date for this role.")
    return {
        "availability": availability,
        "graduation": "2027. " + RESUME_FACTS["education"],
        "relocation": f"Yes, I am willing to relocate{where}. My preferred locations are {location_prefs}.",
    }


def template_pack(job, highlights=None):
    """Free-text parts built only from RESUME_FACTS and the job's own fields."""
    highlights = highlights or select_highlights(job)
    company, role = job.company, job.role
    skills = matched_skills(job)
    skills_line = (f"The role lists {_join(skills[:5])}, which I have used in the work below."
                   if skills else "I work mainly in C++, Python and JavaScript.")
    story_id = next((h["id"] for h in highlights if h["id"] in PROJECT_STORIES), "railway")
    cover = (f"I am a final-year B.Tech Computer Science and Engineering student at NIT Rourkela (2023–2027, CGPA "
             f"8.99), applying for the {role} role at {company}. {skills_line}\n\n"
             + " ".join(h["sentence"] for h in highlights[:2])
             + f"\n\nI would like to do this kind of work in the {role} role at {company}, and I can join on the "
               f"2027 graduate timeline.")
    why_company = (f"{company} is hiring for {role}, and the role matches the work I have done so far: "
                   + (f"{_join(skills[:4])}, which I have used in my internship or projects. " if skills
                      else "building and shipping software in my internship and projects. ")
                   + "I want to work on production systems with an engineering team after I graduate in 2027, and "
                     "this role is a direct fit for that.")
    why_role = (f"The {role} role is close to what I have built. {highlights[0]['sentence']} "
                + (f"I have hands-on experience with the listed skills ({_join(skills[:4])}). " if skills else "")
                + "I want to keep doing this kind of engineering full time after I graduate in 2027.")
    return {
        "cover_note": trim_words(clean_text(cover), COVER_MAX_WORDS),
        "why_company": trim_words(clean_text(why_company), WHY_COMPANY_MAX_WORDS),
        "why_role": trim_words(clean_text(why_role), ANSWER_MAX_WORDS),
        "challenging_project": trim_words(clean_text(PROJECT_STORIES[story_id]), ANSWER_MAX_WORDS),
        "strongest_skill": trim_words(clean_text(_strongest_skill(job)), ANSWER_MAX_WORDS),
    }


# ---------------- LLM ----------------
SYSTEM_PROMPT = f"""You write job application text for one candidate, {RESUME_FACTS['name']}. He pastes it into official application forms under his own name, so every sentence must be true.

Grounding rules:
- Use ONLY the facts under CANDIDATE FACTS and the job's company name, role title, location and listed skills.
- Do not add any other experience, number, metric, tool, award, date or claim. Copy numbers exactly as given.
- Say nothing about the company beyond its name and the role: no products, mission, culture, customers, news, values or size.
- If a listed job skill is not in the facts, do not claim it.

Style:
- First person, plain and specific, short sentences, like a careful engineering student writing for himself.
- Name concrete details from the facts instead of adjectives.
- No greeting, no sign-off, no placeholders such as [Company]. No markdown, no bullet characters, no emojis, no exclamation marks.
- Never use these words: {", ".join(BANNED_WORDS)}, thrilled, excited, dynamic, innovative, world-class, robust.

Return ONLY one JSON object (no markdown fences) with exactly these string keys:
{{
  "cover_note": "at most {COVER_MAX_WORDS} words, two or three short paragraphs separated by a blank line",
  "why_company": "at most {WHY_COMPANY_MAX_WORDS} words: why this role at this company, tied to his real experience",
  "why_role": "at most 90 words: answer to 'Why are you interested in this role?'",
  "challenging_project": "at most {ANSWER_MAX_WORDS} words: one project from the facts, what was hard and how he handled it, using only stated details",
  "strongest_skill": "at most 80 words: name one skill and back it with facts"
}}"""


def facts_text():
    lines = [f"Name: {RESUME_FACTS['name']}", f"Education: {RESUME_FACTS['education']}"]
    lines += [f"- {h['bullet']}" for h in RESUME_FACTS["highlights"]]
    lines.append("Skills: " + ", ".join(RESUME_FACTS["skills"]))
    return "\n".join(lines)


def build_prompt(job, highlights):
    skills = job_skills(job)
    return (f"JOB\nCompany: {job.company}\nRole: {job.role}\nLocation: {job.location or 'not stated'}\n"
            f"Listed skills: {', '.join(skills) if skills else 'not stated'}\n"
            f"Listed skills he has: {', '.join(matched_skills(job)) or 'none listed'}\n\n"
            f"CANDIDATE FACTS\n{facts_text()}\n\n"
            "MOST RELEVANT FACTS FOR THIS JOB\n" + "\n".join(f"- {h['bullet']}" for h in highlights)
            + "\n\nReturn the JSON object now.")


def _allowed_numbers(job):
    source = " ".join([facts_text(), job.company or "", job.role or "", job.location or "", " ".join(job_skills(job))])
    return set(_NUMBER.findall(source))


def _usable(text, allowed):
    """A field is usable when non-empty, has no placeholders, and cites only numbers present in the facts or job."""
    if not text or _PLACEHOLDER.search(text):
        return False
    return all(n in allowed for n in _NUMBER.findall(text))


def merge_llm_output(job, raw, template):
    """Clean + validate the LLM dict field by field; anything unusable falls back to the template field."""
    if not isinstance(raw, dict):
        return dict(template), 0
    if isinstance(raw.get("answers"), dict):  # tolerate answers nested one level down
        raw = {**raw["answers"], **{k: v for k, v in raw.items() if k != "answers"}}
    allowed = _allowed_numbers(job)
    limits = {"cover_note": COVER_MAX_WORDS, "why_company": WHY_COMPANY_MAX_WORDS}
    out, used = {}, 0
    for key in ("cover_note", "why_company") + _LLM_ANSWER_KEYS:
        text = trim_words(clean_text(raw.get(key)), limits.get(key, ANSWER_MAX_WORDS))
        if _usable(text, allowed):
            out[key], used = text, used + 1
        else:
            out[key] = template[key]
    return out, used


def generate_pack(job, location_prefs=DEFAULT_LOCATIONS):
    """Returns (payload, model). Never raises for LLM problems."""
    highlights = select_highlights(job)
    template = template_pack(job, highlights)
    model = TEMPLATE_MODEL
    parts = template
    try:
        llm = LLMClient(budget=LLM_BUDGET)
        raw = llm.generate_json(build_prompt(job, highlights), temperature=TEMPERATURE, system=SYSTEM_PROMPT,
                                thinking="low")
        parts, used = merge_llm_output(job, raw, template)
        if used:
            model = (llm.last_model or "llm")[:80]
    except Exception as e:  # quota, network, malformed JSON: the template is still a complete pack
        print(f"job pack LLM failed for job {job.id}: {str(e)[:200]}")
    answers = {**{k: parts[k] for k in _LLM_ANSWER_KEYS}, **fixed_answers(job, location_prefs)}
    payload = {
        "cover_note": parts["cover_note"],
        "why_company": parts["why_company"],
        "answers": [{"question": q, "answer": answers[k]} for k, q in QUESTIONS],
        "resume_highlights": [h["bullet"] for h in highlights],
        "matched_skills": matched_skills(job),
        "skill_gap": skill_gap(job),
        "job_key": _job_key(job),
    }
    return payload, model


def _job_key(job):
    return f"{job.company}|{job.role}"


# ---------------- Model ----------------
class JobPack(Base):
    __tablename__ = "job_packs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, unique=True, index=True, nullable=False)
    payload = Column(Text, nullable=False)  # JSON
    model = Column(String(80), nullable=False, default=TEMPLATE_MODEL)
    created_at = Column(DateTime, default=_utcnow)


job_pack_bp = Blueprint("job_pack", __name__, url_prefix="/api/jobs")


@job_pack_bp.record_once
def _ensure_tables(state):
    try:
        JobPack.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        print(f"job_packs check skipped: {e}")
    # Job Radar's tables gain columns over time; add any the live table is missing (add-only, idempotent).
    from api.domain.job_migrations import add_missing_columns
    add_missing_columns()


def _response(job, row, payload, cached):
    payload = {k: v for k, v in payload.items() if k != "job_key"}
    return jsonify({"status": "success", "data": {
        "job_id": job.id, "company": job.company, "role": job.role, "url": job.portal_url, **payload,
        "model": row.model, "cached": cached,
        "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
    }})


@job_pack_bp.route("/<int:job_id>/pack", methods=["GET"])
def get_pack(job_id):
    refresh = request.args.get("refresh", "").lower() in ("1", "true", "yes")
    db = SessionLocal()
    try:
        job = db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
        if not job:
            return jsonify({"status": "error", "message": "Job not found"}), 404
        row = db.query(JobPack).filter(JobPack.job_id == job_id).first()
        if row and not refresh:
            try:
                payload = json.loads(row.payload)
            except ValueError:
                payload = None
            if isinstance(payload, dict) and payload.get("job_key") == _job_key(job):
                return _response(job, row, payload, cached=True)

        payload, model = generate_pack(job, _location_prefs(db))
        if row is None:
            row = JobPack(job_id=job_id)
            db.add(row)
        row.payload, row.model, row.created_at = json.dumps(payload), model, _utcnow()
        try:
            db.commit()
        except IntegrityError:  # a concurrent request cached this job first: overwrite it with ours
            db.rollback()
            row = db.query(JobPack).filter(JobPack.job_id == job_id).first()
            row.payload, row.model, row.created_at = json.dumps(payload), model, _utcnow()
            db.commit()
        return _response(job, row, payload, cached=False)
    finally:
        db.close()


@job_pack_bp.route("/<int:job_id>/skill-gap", methods=["GET"])
def get_skill_gap(job_id):
    db = SessionLocal()
    try:
        job = db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
        if not job:
            return jsonify({"status": "error", "message": "Job not found"}), 404
        return jsonify({"status": "success", "data": {
            "job_id": job.id,
            "company": job.company,
            "role": job.role,
            **skill_gap(job),
        }})
    finally:
        db.close()

