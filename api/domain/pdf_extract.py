"""
PDF Studio -> syllabus topics + flashcards.

The browser renders a few lecture pages to JPEG (pdf.js) and sends them with the extracted text.
Gemini (vision) reads them and returns the exam-relevant topics, each with a short summary,
how likely it is to carry marks, and up to three flashcards. The server stays stateless:
adding topics / creating cards is done by the client through the syllabus and cards APIs.
"""
import base64
import binascii
import re

from flask import Blueprint, jsonify, request

from api.core.clients import LLMClient

MAX_IMAGES = 12
MAX_IMAGE_CHARS = 3_000_000  # one base64 page; the whole request is capped by the host anyway
MAX_TEXT = 20000
MAX_SUBJECT = 120
MAX_LABEL = 40
MAX_UNIT = 120
MAX_TOPICS = 20
MAX_TITLE = 200
MAX_SUMMARY = 280
MAX_CARDS = 3
MAX_Q = 300
MAX_A = 600
LLM_BUDGET = 90  # seconds across the whole model fallback chain
MARKS = ("low", "medium", "high")
_IMAGE_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}

SYSTEM = (
    "You turn university lecture slides and notes into a revision syllabus. "
    "Identify the distinct, exam-relevant topics actually covered on the pages (not the course in general). "
    "Merge tiny fragments into one meaningful topic and skip title slides, agendas, references and admin. "
    "Topic titles are short noun phrases (2-8 words) without commas or semicolons and without numbering. "
    "Summaries are at most two short lines. Flashcards must be self-contained (the question names the concept), "
    "test understanding rather than trivia, and have concise answers. Never use LaTeX; write math in plain text."
)

pdf_extract_bp = Blueprint("pdf_extract", __name__, url_prefix="/api/pdf-extract")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _one_line(value, limit):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip(" ,;:-") + "…"
    return text


def _clean_title(value):
    title = _one_line(value, MAX_TITLE)
    title = re.sub(r"^(?:[\-*•·#>]+\s*|\(?\d{1,3}(?:\.\d+)*[.)]\s+)", "", title)  # leading bullets / numbering
    return title.strip(" .:;,-–—|*").strip()


def _clean_summary(value):
    lines = [re.sub(r"\s+", " ", ln).strip(" -•*") for ln in str(value or "").splitlines()]
    text = " ".join(ln for ln in lines if ln)[:2000]
    return _one_line(text, MAX_SUMMARY)


def _clean_marks(value):
    v = str(value or "").strip().lower()
    if v in MARKS:
        return v
    if v in ("med", "moderate", "mid", "average"):
        return "medium"
    if v in ("very high", "very_high", "important", "critical"):
        return "high"
    if v in ("very low", "minor", "rare"):
        return "low"
    return "medium"


def _clean_cards(value):
    out, seen = [], set()
    for card in value if isinstance(value, list) else []:
        if not isinstance(card, dict):
            continue
        q = _one_line(card.get("q") or card.get("question") or card.get("front"), MAX_Q)
        a = _one_line(card.get("a") or card.get("answer") or card.get("back"), MAX_A)
        if not q or not a or q.lower() in seen:
            continue
        seen.add(q.lower())
        out.append({"q": q, "a": a})
        if len(out) >= MAX_CARDS:
            break
    return out


def normalize(raw, fallback_unit="Imported from PDF"):
    """Validates / clamps the model output into {unit, topics:[{title, summary, likely_marks, flashcards}]}."""
    if isinstance(raw, list):
        raw = {"topics": raw}
    if not isinstance(raw, dict):
        raw = {}
    unit = _one_line(raw.get("unit") or raw.get("title") or "", MAX_UNIT) or _one_line(fallback_unit, MAX_UNIT)
    topics, seen = [], set()
    for t in raw.get("topics") if isinstance(raw.get("topics"), list) else []:
        if isinstance(t, str):
            t = {"title": t}
        if not isinstance(t, dict):
            continue
        title = _clean_title(t.get("title") or t.get("topic") or t.get("name"))
        if not title or not re.search(r"[A-Za-z]", title) or title.lower() in seen:
            continue
        seen.add(title.lower())
        topics.append({
            "title": title,
            "summary": _clean_summary(t.get("summary") or t.get("description")),
            "likely_marks": _clean_marks(t.get("likely_marks") or t.get("marks") or t.get("importance")),
            "flashcards": _clean_cards(t.get("flashcards") or t.get("cards")),
        })
        if len(topics) >= MAX_TOPICS:
            break
    return {"unit": unit, "topics": topics}


def _decode_image(value):
    """Returns (bytes, mime) for a data URL or bare base64 string. Raises ValueError."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("empty image")
    if len(value) > MAX_IMAGE_CHARS:
        raise ValueError("image too large")
    mime, data = "image/jpeg", value.strip()
    if data.startswith("data:"):
        header, _, data = data.partition(",")
        mime = header[5:].split(";", 1)[0].lower() or "image/jpeg"
        if mime not in _IMAGE_MIME:
            raise ValueError("unsupported image type")
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("invalid base64")
    if not raw:
        raise ValueError("empty image")
    return raw, ("image/jpeg" if mime == "image/jpg" else mime)


def build_prompt(label, subject_name, text):
    where = f"pages {label}" if label else "these pages"
    return (
        f"These are {where} of a lecture PDF"
        + (f" for the subject \"{subject_name}\"" if subject_name else "")
        + ". List the syllabus topics they cover for end-semester exam revision.\n\n"
        "Return JSON only, exactly this shape:\n"
        "{\"unit\": str (a short heading for this part of the course, e.g. \"Black box testing\"),\n"
        " \"topics\": [{\"title\": str, \"summary\": str (max 2 short lines),\n"
        "   \"likely_marks\": \"low\" | \"medium\" | \"high\" (how likely and how heavily it is examined),\n"
        "   \"flashcards\": [{\"q\": str, \"a\": str}] (0-3 cards)}]}\n"
        f"Give between 1 and {MAX_TOPICS} topics in the order they appear. "
        "If the pages carry no study content, return an empty topics list."
        + (f"\n\nExtracted text (may be imperfect, diagrams are missing):\n{text}" if text else "")
    )


# ---------------- route ----------------
@pdf_extract_bp.route("/topics", methods=["POST"])
def extract_topics():
    data = _body()
    images = data.get("images") or []
    if not isinstance(images, list):
        return _err("images must be a list of base64 JPEG pages.")
    if len(images) > MAX_IMAGES:
        return _err(f"Send at most {MAX_IMAGES} pages at a time.")
    text = data.get("text") if isinstance(data.get("text"), str) else ""
    text = text.strip()[:MAX_TEXT]
    if not images and not text:
        return _err("No pages provided.")
    subject_name = _one_line(data.get("subject_name"), MAX_SUBJECT)
    label = _one_line(data.get("label"), MAX_LABEL)

    llm = LLMClient(budget=LLM_BUDGET)
    contents = [build_prompt(label, subject_name, text)]
    try:
        for img in images:
            raw, mime = _decode_image(img)
            contents.append(llm.image_part(raw, mime))
    except ValueError as e:
        return _err(f"A page image couldn't be read ({e}).")

    try:
        raw = llm.generate_json(contents, temperature=0.3, system=SYSTEM, thinking="low")
    except ValueError:  # json.JSONDecodeError is a ValueError
        return _err("The model returned malformed output. Try again.", 502)
    except Exception as e:
        message = str(e)
        if "No API key" in message:
            return _err("AI isn't configured on the server (set GEMINI_API_KEY).", 503)
        return _err("The AI is busy or timed out. Try again in a minute. " + message[:300], 502)

    result = normalize(raw, fallback_unit=f"Pages {label}" if label else "Imported from PDF")
    result["label"] = label
    return jsonify({"status": "success", "data": result})
