#!/usr/bin/env python
"""
Resume tailoring: adapt the WORDING of Sai's resume to one job posting and render it as a one-page PDF.

  tailored_pdf(posting, role, company, generate=default_generate()) -> (pdf bytes or None, changes)

What may change, and what may not:
  * Experience / project bullets are rephrased by one LLM call to use the posting's own terms, but every rewrite
    passes check_bullet(): same numbers, no technology / employer that isn't already on the resume, no inflated
    claims, no first person, at most 15% longer, no extra wrapped line. Anything else keeps the original bullet.
  * Projects are reordered by how well they match the posting; items inside each skills category the posting
    mentions move first. Experience stays chronological; nothing is ever added.
  * None is returned when nothing changed, so the runner uploads the original resume.pdf.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"

RESUME = {
    "name": "Nandam Venkata Sai Raghava",
    "location": "Nellore, Andhra Pradesh",
    "contact": [
        {"key": "phone"},  # filled from answers.yaml by _with_contact(): the repo is public
        {"key": "email"},
        {"text": "LinkedIn", "url": "https://www.linkedin.com/in/nandam-venkata-sai-raghava-946b3735b/"},
        {"text": "LeetCode", "url": "https://leetcode.com/u/Sairaghava1318/"},
        {"text": "Codeforces", "url": "https://codeforces.com/profile/Raghavan_CP"},
        {"text": "GitHub", "url": "https://github.com/VeratrilS"},
    ],
    "education": [
        {"title": "National Institute of Technology, Rourkela", "date": "Aug 2023 – 2027",
         "subtitle": "Bachelor of Technology in Computer Science and Engineering (CGPA: 8.99)",
         "location": "Rourkela, Odisha"},
        {"title": "Narayana Junior College, Brahmadevam", "date": "May 2023",
         "subtitle": "Andhra Pradesh Board of Intermediate Education (Percentage: 97.1%)",
         "location": "Nellore, Andhra Pradesh"},
    ],
    "coursework": ["Data Structures", "Algorithms", "Object-Oriented Programming", "Database Management Systems",
                   "Operating Systems", "Computer Networks"],
    "experience": [
        {"id": "e1", "title": "Maruti Suzuki India Limited (MSIL)", "date": "May 2026 – Jul 2026",
         "link": {"text": "Certificate",
                  "url": "https://drive.google.com/file/d/1SI_AFaqTetcKILkznr3fn2OW1-HCVuns/view?usp=sharing"},
         "subtitle": "Software Engineering Intern", "location": "Gurugram, India",
         "bullets": [
             "Built the internal **ITEA Department Portal** (MERN) with employee, attendance, leave, project and task modules.",
             "Developed **13 React.js pages** integrated with **120+ REST APIs** (Node.js/Express.js) backed by MongoDB.",
             "Implemented JWT authentication and **role-based access control** (User, Manager, Admin); reviewed backend code.",
         ]},
        {"id": "e2", "title": "DataAnnotation.tech", "date": "May 2026 – Present",
         "link": {"text": "Proof",
                  "url": "https://drive.google.com/file/d/1a4eKYbDAV47isPna7iFTe--GVPPcWMwT/view?usp=sharing"},
         "subtitle": "Coding Expert (Freelance)", "location": "Remote",
         "bullets": [
             "Fixed XTC sampling in a **llama.cpp**-based C++ LLM inference engine to preserve end-of-sequence and special tokens.",
             "Preserved sampler API **backward compatibility** via vocabulary-derived token IDs, verified by regression tests.",
             "Evaluated AI-generated **JavaScript** solutions for graph problems such as Kahn’s topological sort and cycle detection.",
         ]},
    ],
    "projects": [
        {"id": "p1", "name": "Distributed Railway Reservation Platform",
         "tech": "Node.js, Apache Kafka, Redis, PostgreSQL, Elasticsearch", "date": "Aug 2026",
         "bullets": [
             "Architected **8 microservices** (database-per-service, Prisma) linked by **13 Kafka topics** with dead-letter queues.",
             "Prevented **double-booking** via Redis Lua locks and PostgreSQL row locks; a Saga rolls back failed payments.",
             "Designed an **API gateway** (JWT, sliding-window rate limiting, circuit breakers) and Elasticsearch fuzzy search.",
         ]},
        {"id": "p2", "name": "React-Comps", "tech": "React.js, Vite, Express.js, MongoDB, Redux, Firebase, Razorpay",
         "date": "May 2026", "link": {"text": "GitHub", "url": "https://github.com/VeratrilS/React-Comps"},
         "bullets": [
             "Built a full-stack platform that converts text prompts into **React components** using an LLM, with live preview.",
             "Integrated Google sign-in (Firebase), JWT-based sessions, a credit system and **Razorpay** payments.",
             "Automated publishing to an **NPM component library**: a single admin action builds, versions and publishes the package.",
         ]},
        {"id": "p3", "name": "Cache Server", "tech": "C++, TCP Sockets, Multithreading, RESP", "date": "Jun 2026",
         "link": {"text": "GitHub", "url": "https://github.com/VeratrilS/Cache-Server"},
         "bullets": [
             "Developed a **Redis-compatible** cache server in C++ on raw TCP sockets, with a RESP parser for pipelined requests.",
             "Implemented **30 commands** across strings, lists and hashes with TTL expiry and **O(1) LRU/LFU eviction**.",
             "Handled clients via a **thread pool** with mutex-guarded state; added snapshots, graceful shutdown and hit-rate metrics.",
         ]},
    ],
    "achievements": [
        {"text": "**LeetCode**: Contest rating **1709**; 900+ problems solved and 15 badges (365 Days, SQL).",
         "links": [{"text": "Contest", "url": "https://leetcode.com/u/Veratril/"},
                   {"text": "Profile", "url": "https://leetcode.com/u/Sairaghava1318/"}]},
        {"text": "**Codeforces Specialist**: Peak rating **1425** with 325+ problems solved (Oct 2025).",
         "links": [{"text": "Profile", "url": "https://codeforces.com/profile/Raghavan_CP"}]},
        {"text": "**CodeChef 3-Star**: Peak rating **1632** across 23 rated contests; 437 problems solved (Jul 2025).",
         "links": [{"text": "Profile", "url": "https://www.codechef.com/users/sairaghava1318"}]},
    ],
    "skills": [
        {"name": "Languages", "items": ["C++", "Python", "JavaScript", "SQL"]},
        {"name": "Frontend", "items": ["HTML", "CSS", "React.js", "Redux", "Tailwind CSS", "Vite"]},
        {"name": "Backend", "items": ["Node.js", "Express.js", "REST APIs", "Microservices", "Apache Kafka", "Redis",
                                      "Elasticsearch"]},
        {"name": "Databases & Tools", "items": ["PostgreSQL", "MongoDB", "Prisma ORM", "Git", "GitHub"]},
    ],
    "extracurricular": [
        {"title": "OpenCode Club, NIT Rourkela", "date": "Nov 2023 – Present", "subtitle": "Technical Team Member",
         "location": "",
         "bullets": ["Contributed to organizing technical events, hands-on workshops and club activities."]},
    ],
}


# ---------------------------------------------------------------- text helpers

def _plain(s):
    return str(s or "").replace("**", "")


def _resume_text(resume):
    """Every visible word of the resume, plain text (what check_bullet treats as 'already on the resume')."""
    out = []

    def walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k not in ("url", "id", "underline"):
                    walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            out.append(_plain(v))
    walk(resume)
    return "\n".join(out)


def _rx(term, flags=re.I):
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9+#])", flags)


def _has(text, term, flags=re.I):
    return bool(_rx(term, flags).search(text or ""))


def bullet_ids(resume):
    """{id: bullet} for every experience and project bullet, e.g. 'e1.2', 'p3.1'."""
    out = {}
    for sec in ("experience", "projects"):
        for entry in resume[sec]:
            for j, b in enumerate(entry["bullets"], 1):
                out[f"{entry['id']}.{j}"] = b
    return out


def _set_bullet(resume, bid, text):
    eid, j = bid.split(".")
    for sec in ("experience", "projects"):
        for entry in resume[sec]:
            if entry["id"] == eid:
                entry["bullets"][int(j) - 1] = text
                return


def _entry_label(resume, bid):
    eid = bid.split(".")[0]
    for sec, key in (("experience", "title"), ("projects", "name")):
        for entry in resume[sec]:
            if entry["id"] == eid:
                return f"{sec.title()}: {entry[key]}"
    return bid


def _with_contact(resume, answers=None):
    """Phone and email from answers.yaml (gitignored); entries with no value are dropped."""
    if answers is None:
        try:
            import yaml
            answers = yaml.safe_load((HERE / "answers.yaml").read_text(encoding="utf-8")) or {}
        except Exception:
            answers = {}
    phone = str(answers.get("phone") or "").strip()
    email = str(answers.get("email") or "").strip()
    filled = {"phone": {"text": f"(+91) {phone}"} if phone else None,
              "email": {"text": email, "url": f"mailto:{email}", "underline": True} if email else None}
    out = copy.deepcopy(resume)
    out["contact"] = [filled.get(c["key"]) if "key" in c else c for c in out["contact"]]
    out["contact"] = [c for c in out["contact"] if c]
    return out


# ---------------------------------------------------------------- guard

_INFLATION = re.compile(
    r"\b(led|lead|leading|spearhead\w*|headed|mentor\w*|manag\w* (?:a |the )?team|team of|millions?|billions?"
    r"|thousands?|users?|customers?|production|revenue|awards?|awarded|deploy\w*|launch\w*|patent\w*)\b", re.I)
_NUM_WORDS = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundreds?"
    r"|dozens?|double|twice|triple)\b", re.I)
_FIRST_PERSON = re.compile(r"(?<![/\w])I(?![/\w'])|\b(me|my|mine|we|our|ours|us)\b", re.I)
_OK_CHARS = set("–—‘’“”•…→×")
_SUFFIXES = ("s", "es", "ful", "ed", "ing")
_STRIP = ".,;:()[]{}\"'!?"
_FILLER = {"with", "from", "into", "that", "this", "using", "across", "such", "via", "both", "each"}


def _is_tech(tok):
    return bool(tok) and (tok[0].isupper() or any(c.isupper() or c.isdigit() for c in tok[1:])
                          or any(c in "+.#" for c in tok))


def _known(tok, resume_text, posting=""):
    if any(_has(resume_text, t) for t in (tok, tok + "s", tok + "es")):
        return True
    # posting's own spelling of a term already on the resume: "RESTful" for REST, "Microservice" for Microservices
    if posting and _has(posting, tok):
        low = tok.lower()
        return any(low.endswith(s) and len(tok) - len(s) >= 3 and _has(resume_text, tok[:-len(s)]) for s in _SUFFIXES)
    return False


def check_bullet(original, new, resume_text, posting=""):
    """None if `new` is a safe rewording of `original`, else the reason it is rejected."""
    if not isinstance(new, str) or not new.strip():
        return "empty"
    if new.count("**") % 2:
        return "unbalanced bold markers"
    po, pn = _plain(original), _plain(new)
    num = r"\d+(?:\.\d+)?"
    if Counter(re.findall(num, pn)) != Counter(re.findall(num, po)):
        return "numbers changed"
    for rx, what in ((_NUM_WORDS, "number word"), (_INFLATION, "inflated claim")):
        for m in rx.finditer(pn):
            if not _has(po, m.group(0)):
                return f"{what}: {m.group(0)}"
    if "%" in pn and "%" not in po:
        return "inflated claim: %"
    if len(pn) > 1.15 * len(po):
        return "too long"
    # the leading verb may change ("Architected" -> "Built"); the rest of the detail must stay
    words = [w for w in re.findall(r"[a-z][a-z0-9+.#-]{3,}", po.lower())[1:] if w not in _FILLER]
    kept = sum(1 for w in words if re.search(r"(?<![a-z])" + re.escape(w.rstrip(".")[:max(4, len(w) - 3)]), pn.lower()))
    if words and kept < 0.75 * len(words):
        return "drops detail"
    if _FIRST_PERSON.search(pn):
        return "first person"
    if any(ord(c) > 0x24F and c not in _OK_CHARS for c in pn):
        return "emoji / unsupported character"
    for i, raw in enumerate(pn.split()):
        for part in re.split(r"[/\-]", raw.strip(_STRIP)):
            part = part.strip(_STRIP)
            if not _is_tech(part) or _known(part, resume_text, posting):
                continue
            if i == 0 and part.isalpha() and part[1:].islower() and part.lower().endswith("ed"):
                continue  # sentence-initial verb, "Engineered"
            return f"new term: {part}"
    return None


# ---------------------------------------------------------------- deterministic tailoring

_ALIASES = {
    "PostgreSQL": ["Postgres"], "MongoDB": ["Mongo"], "REST APIs": ["REST", "RESTful", "REST API"],
    "Microservices": ["microservice"], "Apache Kafka": ["Kafka"], "Tailwind CSS": ["Tailwind"],
    "Prisma ORM": ["Prisma", "ORM"], "Multithreading": ["multi-threading", "multithreaded", "concurrency"],
    "TCP Sockets": ["TCP", "sockets"], "React.js": ["React", "ReactJS"], "Node.js": ["Node", "NodeJS"],
    "Express.js": ["Express", "ExpressJS"],
}
_CASE_SENSITIVE = {"Node", "Express", "React"}  # also plain English words
_CONCEPTS = [r"distributed", r"back-?end|server-side", r"full[- ]stack", r"front-?end", r"cach(?:e|ing)",
             r"multi-?thread\w*|concurren\w*|thread pool", r"rate[- ]limit\w*", r"search", r"payments?",
             r"authenticat\w*|authoriz\w*|JWT", r"LLMs?|generative AI|GenAI", r"event-driven|message queues?|pub/?sub",
             r"API gateway", r"sockets?|TCP|networking", r"locks?|locking|transactions?", r"fault[- ]toleran\w*|circuit breakers?"]


def _mentions(text, item):
    if _has(text, item):
        return True
    return any(_has(text, a, 0 if a in _CASE_SENSITIVE else re.I) for a in _ALIASES.get(item, []))


def _terms(resume):
    seen = []
    for cat in resume["skills"]:
        seen += cat["items"]
    for p in resume["projects"]:
        seen += [t.strip() for t in p["tech"].split(",")]
    return list(dict.fromkeys(seen))


def project_score(project, posting, terms):
    blob = " ".join([project["name"], project["tech"], *map(_plain, project["bullets"])])
    score = sum(1 for t in terms if _mentions(posting, t) and _mentions(blob, t))
    return score + sum(1 for c in _CONCEPTS if re.search(c, posting, re.I) and re.search(c, blob, re.I))


def reorder(resume, posting):
    """Projects by match with the posting (stable on ties); posting-mentioned skills first in each category."""
    changes = []
    terms = _terms(resume)
    before = [p["name"] for p in resume["projects"]]
    resume["projects"] = sorted(resume["projects"], key=lambda p: -project_score(p, posting, terms))
    after = [p["name"] for p in resume["projects"]]
    if after != before:
        changes.append(("Projects order", ", ".join(before), ", ".join(after)))
    for cat in resume["skills"]:
        items = sorted(cat["items"], key=lambda t: not _mentions(posting, t))
        if items != cat["items"]:
            changes.append((f"Skills: {cat['name']}", ", ".join(cat["items"]), ", ".join(items)))
            cat["items"] = items
    return changes


# ---------------------------------------------------------------- LLM rewording

SYSTEM = ("You adapt the wording of resume bullets to a job posting without changing any fact. "
          "You never invent experience, tools, numbers or outcomes. Reply with JSON only.")


def build_prompt(bullets, posting, role="", company=""):
    return f"""Job: {role or "(role not given)"} at {company or "(company not given)"}
Posting (may be truncated):
\"\"\"
{(posting or "")[:5000]}
\"\"\"

Resume bullets (id -> text). **...** marks the bold key terms.
{json.dumps(bullets, indent=1, ensure_ascii=False)}

Rewrite each bullet so it uses the posting's own terminology wherever the bullet ALREADY describes the same thing.
Examples: the posting says "RESTful services" and the bullet says "REST APIs"; the posting says "distributed systems"
or "scalable backend services" and the bullet describes microservices linked by Kafka.
Rules:
- Keep exactly the same facts, numbers, technologies and names. Add nothing: no new tools, languages, metrics, users,
  scale, leadership, deployment or outcomes. Do not drop numbers or technologies either.
- Keep **bold** markers around the key terms (they may wrap the posting's equivalent phrase instead).
- Keep each bullet about the same length (at most 10% longer), starting with a past-tense verb, no first person,
  no emojis.
- If the posting has no matching terminology for a bullet, return it unchanged.
Return {{"bullets": {{"<id>": "<text>", ...}}}} with every id."""


def default_generate():
    """The production LLM (Gemini with OpenRouter fallback) as prompt -> dict, or None without API keys."""
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("OPENROUTER_API_KEY")):
        return None
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from api.core.clients import LLMClient
    client = LLMClient(budget=45)

    def generate(prompt):
        try:
            return client.generate_json(prompt, temperature=0.3, system=SYSTEM)
        except ValueError:  # an empty or prose reply now and then: ask once more, plainly
            text = client.generate(prompt + "\nReply with only the JSON object, no other text.", temperature=0.2,
                                   system=SYSTEM)
            return json.loads(text[text.find("{"):text.rfind("}") + 1])
    return generate


def _llm_bullets(resume, posting, role, company, generate):
    try:
        out = generate(build_prompt(bullet_ids(resume), posting, role, company))
    except Exception as e:  # LLM down / bad JSON: keep the original wording
        print(f"  tailor: LLM failed ({type(e).__name__}: {e})")
        return {}
    if not isinstance(out, dict):
        return {}
    got = out.get("bullets", out)
    return got if isinstance(got, dict) else {}


# ---------------------------------------------------------------- tailoring

def tailor(resume, posting_text, role="", company="", generate=None, rejected=None):
    """-> (new_resume, changes); changes = [(section, original, new)]. Rejected rewrites go to `rejected` if given."""
    posting = posting_text or ""
    new = copy.deepcopy(resume)
    rejected = rejected if rejected is not None else []
    text = _resume_text(resume)
    originals = bullet_ids(resume)
    accepted = {}
    if generate and posting.strip():
        for bid, cand in _llm_bullets(resume, posting, role, company, generate).items():
            orig = originals.get(bid)
            if orig is None or not isinstance(cand, str) or cand.strip() == orig:
                continue
            cand = re.sub(r"\s+", " ", cand).strip()
            reason = check_bullet(orig, cand, text, posting)
            if not reason and _line_count(cand) > _line_count(orig):
                reason = "wraps to an extra line"
            if reason:
                rejected.append((bid, orig, cand, reason))
            else:
                accepted[bid] = cand
    for bid, cand in accepted.items():
        _set_bullet(new, bid, cand)
    order_changes = reorder(new, posting)

    # must stay one page: undo the rewrites that grew most first
    for bid in sorted(accepted, key=lambda b: len(_plain(accepted[b])) - len(_plain(originals[b])), reverse=True):
        if page_count(render(new)) == 1:
            break
        _set_bullet(new, bid, originals[bid])
        rejected.append((bid, originals[bid], accepted.pop(bid), "page overflow"))
    changes = [(_entry_label(resume, b), originals[b], accepted[b]) for b in originals if b in accepted]
    return new, changes + order_changes


def _slug(s):
    return re.sub(r"[^A-Za-z0-9.-]+", "_", str(s or "").strip()).strip("_")[:50] or "job"


def tailored_pdf(posting_text, role, company, generate=None, out_dir=None, resume=None):
    """-> (pdf bytes, changes), or (None, []) when nothing changed and the original resume.pdf should be used."""
    rejected = []
    new, changes = tailor(resume or RESUME, posting_text, role, company, generate=generate, rejected=rejected)
    if not changes:
        return None, []
    pdf = render(new)
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        stem = f"{_slug(company)}_{_slug(role)}"
        (out / f"{stem}.pdf").write_bytes(pdf)
        (out / f"{stem}.json").write_text(json.dumps({
            "company": company, "role": role, "created": datetime.now().isoformat(timespec="seconds"),
            "changes": [{"section": s, "original": o, "new": n} for s, o, n in changes],
            "rejected": [{"id": i, "original": o, "proposed": p, "reason": r} for i, o, p, r in rejected],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    return pdf, changes


# ---------------------------------------------------------------- rendering

PAGE_W, PAGE_H = 595.28, 841.89  # A4 in pt
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 30.0, 22.0, 24.0
TEXT_W = PAGE_W - 2 * MARGIN_X
BODY, TITLE, HEAD = 10.5, 11.4, 12.6  # font sizes
BULLET_X, BULLET_TEXT_X = 3.0, 11.0  # bullet glyph / text offsets from the margin
LEAD = 1.27  # line height / font size
F = "TNR"


def page_count(pdf_bytes):
    return len(re.findall(rb"/Type\s*/Page(?![A-Za-z])", pdf_bytes or b""))


def _new_pdf():
    from fpdf import FPDF
    pdf = FPDF(unit="pt", format="A4")
    pdf.set_auto_page_break(False)
    pdf.set_margins(MARGIN_X, MARGIN_TOP, MARGIN_X)
    files = {"": "times.ttf", "B": "timesbd.ttf", "I": "timesi.ttf", "BI": "timesbi.ttf"}
    if all((FONT_DIR / f).exists() for f in files.values()):
        for style, f in files.items():
            pdf.add_font(F, style, str(FONT_DIR / f))
        pdf.unicode_ok = True
    else:
        pdf.unicode_ok = False
    return pdf


def _font(pdf, style, size):
    pdf.set_font(F if pdf.unicode_ok else "Times", style, size)


def _t(pdf, s):
    if pdf.unicode_ok:
        return s
    return s.replace("–", "-").replace("—", "-").replace("’", "'").replace("‘", "'").replace("•", chr(149))


def _w(pdf, s, style, size):
    _font(pdf, style, size)
    return pdf.get_string_width(_t(pdf, s))


def _words(text, base=""):
    """'a **b c**-d' -> [[('a', '')], [('b', 'B')], [('c', 'B'), ('-d', '')]] (words of styled fragments)."""
    words, cur = [], []
    for i, part in enumerate(str(text).split("**")):
        style = "".join(sorted(set(base + ("B" if i % 2 else ""))))
        for j, chunk in enumerate(part.split(" ")):
            if j:
                if cur:
                    words.append(cur)
                cur = []
            if chunk:
                cur.append((chunk, style))
    if cur:
        words.append(cur)
    return words


def _wrap(pdf, text, width, size, base=""):
    space = _w(pdf, " ", base, size)
    lines, line, lw = [], [], 0.0
    for word in _words(text, base):
        ww = sum(_w(pdf, f, s, size) for f, s in word)
        if line and lw + space + ww > width:
            lines.append(line)
            line, lw = [], 0.0
        lw += (space if line else 0) + ww
        line.append(word)
    if line:
        lines.append(line)
    return lines, space


_MEASURE = None


def _line_count(text):
    """Lines a bullet takes in render() (same font, size and width)."""
    global _MEASURE
    if _MEASURE is None:
        _MEASURE = _new_pdf()
    return len(_wrap(_MEASURE, text, TEXT_W - BULLET_TEXT_X, BODY)[0]) or 1


class _Layout:
    def __init__(self, gap, lead):
        self.pdf = _new_pdf()
        self.pdf.add_page()
        self.gap, self.lead = gap, lead
        self.y = MARGIN_TOP
        self.flex = 0.0  # total of the stretchable gaps, to scale them to fill the page

    def space(self, pts):
        self.y += pts * self.gap
        self.flex += pts

    def need(self, h):
        if self.y + h > PAGE_H - MARGIN_BOTTOM:
            self.pdf.add_page()
            self.y = MARGIN_TOP

    def segs(self, x, y, segs, size):
        """Draw [(text, style, url)] from x on baseline y; returns end x."""
        pdf = self.pdf
        for text, style, url in segs:
            w = _w(pdf, text, style, size)
            pdf.text(x, y, _t(pdf, text))
            if url:
                pdf.link(x, y - size * 0.8, w, size, url)
            x += w
        return x

    def seg_w(self, segs, size):
        return sum(_w(self.pdf, t, s, size) for t, s, _ in segs)

    def row(self, left, right, size, h=None):
        """One line with left segments and right-aligned segments."""
        h = h or size * self.lead
        self.need(h)
        base = self.y + size * 0.85
        self.segs(MARGIN_X, base, left, size)
        self.segs(PAGE_W - MARGIN_X - self.seg_w(right, size), base, right, size)
        self.y += h

    def rich(self, text, x, width, size, base="", bullet=False, right=None):
        """Wrapped paragraph with **bold** spans, optional bullet and right-aligned segments on its first line."""
        pdf, lh = self.pdf, size * self.lead
        rw = self.seg_w(right, size) + 8 if right else 0
        lines, space = _wrap(pdf, text, width - rw, size, base)
        self.need(lh * len(lines))
        for n, line in enumerate(lines):
            b = self.y + size * 0.85
            if bullet and n == 0:
                _font(pdf, "", size * 0.95)
                pdf.text(MARGIN_X + BULLET_X, b - 0.4, _t(pdf, "•"))
            cx = x
            for word in line:
                for frag, style in word:
                    _font(pdf, style, size)
                    pdf.text(cx, b, _t(pdf, frag))
                    cx += pdf.get_string_width(_t(pdf, frag))
                cx += space
            if right and n == 0:
                self.segs(PAGE_W - MARGIN_X - self.seg_w(right, size), b, right, size)
            self.y += lh
        return len(lines)

    def bullet(self, text, right=None):
        self.rich(text, MARGIN_X + BULLET_TEXT_X, TEXT_W - BULLET_TEXT_X, BODY, bullet=True, right=right)

    def heading(self, title):
        self.space(6.5)
        self.need(HEAD * 1.6 + BODY * 2.5)
        _font(self.pdf, "B", HEAD)
        self.pdf.text(MARGIN_X, self.y + HEAD * 0.82, title)
        self.y += HEAD * 1.08
        self.pdf.set_line_width(0.5)
        self.pdf.line(MARGIN_X, self.y, PAGE_W - MARGIN_X, self.y)
        self.space(4.5)


def _link_segs(link, sep_first=True):
    if not link:
        return []
    return ([(" | ", "I", None)] if sep_first else []) + [(link["text"], "B", link["url"])]


def _layout(resume, gap=1.0, lead=LEAD):
    L = _Layout(gap, lead)
    pdf = L.pdf

    # name: initials full size, the rest uppercase smaller (LaTeX small caps), letter-spaced
    big, small, cs = 25.0, 19.5, 0.9
    parts = []
    for k, word in enumerate(resume["name"].split()):
        if k:
            parts.append((" ", small))
        parts += [(word[0].upper(), big), (word[1:].upper(), small)]
    width = sum(_w(pdf, t, "", s) + cs * len(t) for t, s in parts) - cs
    x, base = (PAGE_W - width) / 2, L.y + big * 0.75
    pdf.set_char_spacing(cs)
    for t, s in parts:
        _font(pdf, "", s)
        pdf.text(x, base, _t(pdf, t))
        x += _w(pdf, t, "", s) + cs * len(t)
    pdf.set_char_spacing(0)
    L.y += big * 0.98

    def centered(segs, size):
        base = L.y + size * 0.85
        x = (PAGE_W - L.seg_w(segs, size)) / 2
        for text, style, url in segs:
            w = _w(pdf, text, style, size)
            L.segs(x, base, [(text, style, url)], size)
            if url and url.startswith("mailto:"):  # the email is underlined, like the original
                pdf.set_line_width(0.4)
                pdf.line(x, base + 1.6, x + w, base + 1.6)
            x += w
        L.y += size * L.lead

    centered([(resume["location"], "", None)], BODY)
    contact = []
    for k, c in enumerate(resume["contact"]):
        if k:
            contact.append(("   |   ", "", None))
        contact.append((c["text"], "", c.get("url")))
    centered(contact, BODY)

    def entry(title, title_segs_right, subtitle, location, bullets, title_size=TITLE):
        L.space(2.8)
        L.need(title_size * L.lead + BODY * L.lead * (1 + len(bullets)))
        L.row([(title, "B", None)], title_segs_right, title_size, h=title_size * 1.22)
        if subtitle or location:
            L.row([(subtitle, "I", None)], [(location, "I", None)] if location else [], BODY, h=BODY * 1.3)
        for b in bullets:
            L.bullet(b)

    L.heading("Education")
    for k, e in enumerate(resume["education"]):
        if k:
            L.space(2)
        entry(e["title"], [(e["date"], "B", None)], e["subtitle"], e["location"], [])

    if resume.get("coursework"):
        L.heading("Relevant Coursework")
        L.space(1.5)
        items = resume["coursework"]
        rows = -(-len(items) // 3)
        col_w = (TEXT_W - 18) / 3
        L.need(rows * BODY * L.lead)
        for r in range(rows):
            base = L.y + BODY * 0.85
            for c in range(3):
                i = c * rows + r
                if i < len(items):
                    x = MARGIN_X + 18 + c * col_w
                    _font(pdf, "", BODY * 0.95)
                    pdf.text(x, base - 0.4, _t(pdf, "•"))
                    _font(pdf, "", BODY)
                    pdf.text(x + 8, base, _t(pdf, items[i]))
            L.y += BODY * 1.15

    L.heading("Experience")
    for e in resume["experience"]:
        entry(e["title"], [(e["date"], "B", None)] + _link_segs(e.get("link")), e["subtitle"], e["location"],
              e["bullets"])

    L.heading("Projects")
    for p in resume["projects"]:
        L.space(2.8)
        L.need(BODY * L.lead * (1 + len(p["bullets"])))
        L.row([(p["name"], "B", None), (" | ", "I", None), (p["tech"], "I", None)],
              [(p["date"], "B", None)] + _link_segs(p.get("link")), BODY, h=BODY * 1.3)
        for b in p["bullets"]:
            L.bullet(b)

    if resume.get("achievements"):
        L.heading("Achievements")
        L.space(1.5)
        for a in resume["achievements"]:
            right = []
            for k, link in enumerate(a.get("links", [])):
                if k:
                    right.append((" | ", "I", None))
                right.append((link["text"], "", link["url"]))
            L.bullet(a["text"], right=right)

    L.heading("Technical Skills")
    L.space(1.5)
    for cat in resume["skills"]:
        L.bullet(f"**{cat['name']}**: " + ", ".join(cat["items"]))

    if resume.get("extracurricular"):
        L.heading("Extracurricular Activities")
        for e in resume["extracurricular"]:
            entry(e["title"], [(e["date"], "B", None)], e.get("subtitle", ""), e.get("location", ""), e["bullets"])
    return L


def render(resume=None):
    """One-page A4 PDF (bytes) in the look of Sai's LaTeX resume. Spacing stretches to fill the page, or shrinks
    when content runs long; check page_count() — it is 2 only if even the tightest spacing overflows."""
    resume = resume or RESUME
    if any("key" in c for c in resume.get("contact", [])):
        resume = _with_contact(resume)
    L = _layout(resume)
    if L.pdf.page == 1:
        spare = PAGE_H - MARGIN_BOTTOM - L.y
        if spare > 2 and L.flex:
            stretched = _layout(resume, gap=min(1 + (spare - 2) / L.flex, 2.2))
            if stretched.pdf.page == 1:
                L = stretched
    else:
        for gap, lead in ((0.7, LEAD), (0.45, LEAD - 0.04), (0.2, LEAD - 0.08)):
            L = _layout(resume, gap, lead)
            if L.pdf.page == 1:
                break
    return bytes(L.pdf.output())


if __name__ == "__main__":
    # python tailor_resume.py posting.txt "Role" "Company" [out_dir]  (uses the LLM when the .env has keys)
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env")
    except ImportError:
        pass
    if len(sys.argv) < 2 or sys.argv[1].endswith(".pdf"):  # tailor_resume.py out.pdf: render the untailored resume
        out = Path(sys.argv[1] if len(sys.argv) > 1 else "resume_render.pdf")
        out.write_bytes(render(RESUME))
        print(out)
        sys.exit(0)
    posting = Path(sys.argv[1]).read_text(encoding="utf-8")
    pdf, changes = tailored_pdf(posting, sys.argv[2] if len(sys.argv) > 2 else "", sys.argv[3] if len(sys.argv) > 3
                                else "", generate=default_generate(), out_dir=sys.argv[4] if len(sys.argv) > 4 else None)
    for s, o, n in changes:
        print(f"[{s}]\n  - {o}\n  + {n}")
    print("unchanged: upload resume.pdf" if pdf is None else f"{len(pdf)} bytes, {page_count(pdf)} page(s)")
