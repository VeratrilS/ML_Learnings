"""
Quick capture: turn a line of text or a shared link into to-dos.

Parsing is deterministic first (LeetCode / Codeforces / YouTube links, "tomorrow", #tags,
one item per line or `;`). Gemini is only used on request (`ai: true`) to split a single
ambiguous line that looks like several tasks, with a hard 15s budget.
"""
import re
import threading
from datetime import timedelta
from urllib.parse import urlparse

import requests
from flask import Blueprint, jsonify, request
from sqlalchemy import func

from api.core.config import now_ist
from api.core.db import SessionLocal, engine
from api.domain.todos import MAX_TEXT, Todo, _serialize

capture_bp = Blueprint("capture", __name__, url_prefix="/api/capture")

MAX_INPUT = 4000
MAX_ITEMS = 20
AI_BUDGET_S = 15
OEMBED_TIMEOUT_S = 3
DAYS = ("today", "tomorrow")


@capture_bp.record_once
def _ensure_table(state):
    try:
        Todo.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:  # e.g. a concurrent cold start created it first
        print(f"todos table check skipped: {e}")


# ---------------- helpers ----------------
def _err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _today():
    return now_ist().date()


def _str(v, limit=MAX_INPUT):
    return v.strip()[:limit] if isinstance(v, str) else ""


_URL_RE = re.compile(
    r"(?:https?://|(?<![\w./-])(?:www\.|m\.)?(?=(?:leetcode\.com|leetcode\.cn|codeforces\.com|youtube\.com|youtu\.be)/))"
    r"[^\s<>\"'`]+",
    re.I,
)
_LC_RE = re.compile(r"^(?:[\w-]+\.)?leetcode\.(?:com|cn)/problems/([a-z0-9-]+)", re.I)
_CF_RES = (
    re.compile(r"^(?:[\w-]+\.)?codeforces\.com/(?:contest|gym)/(\d+)/problem/([a-z]\d?)\b", re.I),
    re.compile(r"^(?:[\w-]+\.)?codeforces\.com/problemset/problem/(\d+)/([a-z]\d?)\b", re.I),
)
_YT_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")
_ROMAN = {"ii", "iii", "iv", "vi", "vii", "viii", "ix", "xi"}


def find_url(text):
    m = _URL_RE.search(text or "")
    return m.group(0).rstrip(").,;:!?]") if m else None


def _hostpath(url):
    """'https://www.leetcode.com/problems/x/' -> 'www.leetcode.com/problems/x/'"""
    return re.sub(r"^https?://", "", url, flags=re.I)


def _normalize_url(url):
    return url if re.match(r"^https?://", url, re.I) else f"https://{url}"


def slug_title(slug):
    words = [w for w in slug.split("-") if w]
    return " ".join(w.upper() if w.lower() in _ROMAN else (w[:1].upper() + w[1:]) for w in words)


_yt_cache = {}


def _youtube_title(url):
    """Best-effort video title via oEmbed (3s). Returns None on any failure."""
    if url in _yt_cache:
        return _yt_cache[url]
    title = None
    try:
        r = requests.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"},
                         timeout=OEMBED_TIMEOUT_S)
        if r.ok:
            title = (r.json().get("title") or "").strip()[:200] or None
    except Exception:
        title = None
    if len(_yt_cache) > 128:
        _yt_cache.clear()
    _yt_cache[url] = title
    return title


def _clean_hint(hint, url):
    """Text around a shared link, minus the link and generic site suffixes."""
    hint = (hint or "").replace(url, " ")
    hint = re.sub(r"\s*[-|–—]\s*(YouTube|LeetCode|Codeforces)\s*$", "", hint, flags=re.I)
    return re.sub(r"\s+", " ", hint).strip(" -|:–—")


def classify_url(url, hint=""):
    """Returns a capture item for a URL (leetcode / codeforces / video / link)."""
    hp = _hostpath(url)
    m = _LC_RE.match(hp)
    if m:
        slug = m.group(1).lower()
        return {"kind": "leetcode", "slug": slug, "title": slug_title(slug),
                "url": f"https://leetcode.com/problems/{slug}/"}
    for rx in _CF_RES:
        m = rx.match(hp)
        if m:
            contest, index = m.group(1), m.group(2).upper()
            kind = "gym" if "/gym/" in hp.lower() else "contest"
            return {"kind": "codeforces", "key": f"{contest}{index}", "title": f"CF {contest}{index}",
                    "url": f"https://codeforces.com/{kind}/{contest}/problem/{index}"}
    host = (urlparse(_normalize_url(url)).hostname or "").lower()
    hint = _clean_hint(hint, url)
    if any(host == h or host.endswith("." + h) for h in _YT_HOSTS):
        full = _normalize_url(url)
        return {"kind": "video", "url": full, "title": _youtube_title(full) or hint or None}
    full = _normalize_url(url)
    label = hint or host.removeprefix("www.") or full
    return {"kind": "link", "url": full, "title": label}


# "tomorrow" / "tmrw" (optionally after by/for/on/@), not possessive ("tomorrow's quiz").
_TOMORROW_RE = re.compile(r"(?:\b(?:by|for|on|due)\s+)?@?\b(?:tomorrow|tmrw|tmr|tomorow)\b(?!['’]\w)", re.I)
_TODAY_RE = re.compile(r"(?:\b(?:by|for|on|due)\s+)?@?\b(?:today|tonight|tdy)\b(?!['’]\w)", re.I)
_TAG_RE = re.compile(r"(?<![\w&/])#([A-Za-z][\w-]{0,29})")
_BULLET_RE = re.compile(r"^\s*(?:[-*•●>]+|\d{1,2}[.)]|\[\s?\])\s+")


def parse_todo(text):
    """'Revise DBMS tomorrow #exam' -> {kind:'todo', text:'Revise DBMS', day:'tomorrow', tags:['exam']}"""
    day = "today"
    if _TOMORROW_RE.search(text):
        day = "tomorrow"
        text = _TOMORROW_RE.sub(" ", text)
    else:
        text = _TODAY_RE.sub(" ", text)
    tags = []
    for t in _TAG_RE.findall(text):
        if t.lower() not in tags:
            tags.append(t.lower())
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;-–—")
    return {"kind": "todo", "text": text, "day": day, "tags": tags}


def _parse_line(line, title_hint=""):
    url = find_url(line)
    if url:
        rest = line.replace(url, " ")
        # A plain-text day / tags around a link still count ("https://... tomorrow #dp")
        meta = parse_todo(rest)
        item = classify_url(url, hint=title_hint or meta["text"])
        item["day"] = meta["day"]
        item["tags"] = meta["tags"]
        return item
    item = parse_todo(line)
    return item if item["text"] else None


_SEP_RE = re.compile(r",|\band\b|\bthen\b|\balso\b|\bplus\b|&", re.I)


def looks_multi(text):
    """A single line that may really be several tasks ('solve 2 DP, revise OS and email prof')."""
    if "\n" in text or find_url(text) or len(text) < 25:
        return False
    return len(_SEP_RE.findall(text)) >= 2


def parse_rules(text, url="", title=""):
    """Deterministic parse. Returns a list of items."""
    text, url, title = _str(text), _str(url, 2000), _str(title, 300)
    if url and url not in text:
        meta = parse_todo(text.replace(find_url(text) or "\0", " ")) if text else {"text": "", "day": "today", "tags": []}
        item = classify_url(url, hint=title or meta["text"])
        item.update(day=meta["day"], tags=meta["tags"])
        return [item]
    lines = [_BULLET_RE.sub("", ln).strip() for ln in re.split(r"[\n;]+", text)]
    lines = [ln for ln in lines if ln]
    hint = title if len(lines) == 1 else ""
    items = [it for it in (_parse_line(ln, hint) for ln in lines) if it]
    if not items and title:  # only a title was shared
        items = [parse_todo(title)]
    return items[:MAX_ITEMS]


_AI_SYSTEM = (
    "Split a quick-capture note into separate to-do items. Keep each item short, imperative and in the "
    "user's words; do not invent tasks. If it is really one task, return one item. day is 'tomorrow' only if "
    "the note says so for that item, else 'today'. Output JSON: {\"items\":[{\"text\":str,\"day\":\"today\"|\"tomorrow\"}]}"
)


def _llm_split(text):
    """Gemini split with a hard wall-clock budget. Returns list of items or None."""
    from api.core.clients import LLMClient
    llm = LLMClient(openrouter_key="", budget=AI_BUDGET_S)
    if not llm.gemini_key:
        return None
    out = {}

    def run():
        try:
            out["data"] = llm.generate_json(text, temperature=0, system=_AI_SYSTEM)
        except Exception as e:
            out["error"] = str(e)[:200]

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(AI_BUDGET_S)
    data = out.get("data")
    raw = data.get("items") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return None
    items = []
    for r in raw[:MAX_ITEMS]:
        if not isinstance(r, dict) or not isinstance(r.get("text"), str):
            continue
        it = parse_todo(r["text"][:MAX_TEXT])
        if r.get("day") == "tomorrow":
            it["day"] = "tomorrow"
        if it["text"]:
            items.append(it)
    return items or None


def _todo_text(item):
    """Final to-do text for a capture item, kept under MAX_TEXT."""
    kind = item.get("kind")
    tags = [t for t in (item.get("tags") or []) if isinstance(t, str) and re.fullmatch(r"[\w-]{1,30}", t)]
    suffix = "".join(f" #{t}" for t in tags[:5])
    url = _str(item.get("url"), 1000)
    title = _str(item.get("title"), 300)
    if kind in ("leetcode", "codeforces"):
        if kind == "leetcode" and not url and item.get("slug"):
            url = f"https://leetcode.com/problems/{_str(item['slug'], 120)}/"
        head = f"Solve: {title or _str(item.get('key'), 20) or 'problem'}"
    elif kind == "video":
        head = f"Watch: {title}" if title else "Watch video"
    elif kind == "link":
        head = f"Read: {title}" if title else "Read"
    else:
        head, url = _str(item.get("text"), MAX_TEXT), ""
    tail = (f" {url}" if url else "") + suffix
    if len(head) + len(tail) > MAX_TEXT:
        if len(tail) > MAX_TEXT - 20:  # absurd URL: drop it rather than the task
            tail = suffix
        head = head[: MAX_TEXT - len(tail) - 1].rstrip() + "…"
    return (head + tail).strip()


# ---------------- routes ----------------
@capture_bp.route("/parse", methods=["POST"])
def parse():
    data = _body()
    text, url, title = data.get("text"), data.get("url"), data.get("title")
    if not any(_str(v) for v in (text, url, title)):
        return _err("Nothing to capture.")
    items = parse_rules(text, url, title)
    raw = _str(text)
    ambiguous = len(items) == 1 and items[0]["kind"] == "todo" and looks_multi(raw)
    source = "rules"
    if ambiguous and data.get("ai") is True:
        ai_items = _llm_split(raw)
        if ai_items:
            items, source, ambiguous = ai_items, "ai", False
    today = _today()
    for it in items:
        it["date"] = (today + timedelta(days=1 if it.get("day") == "tomorrow" else 0)).isoformat()
    return jsonify({"status": "success", "data": {"items": items, "ambiguous": ambiguous, "source": source}})


@capture_bp.route("/commit", methods=["POST"])
def commit():
    items = _body().get("items")
    if not isinstance(items, list) or not items:
        return _err("items must be a non-empty list.")
    if len(items) > MAX_ITEMS:
        return _err(f"At most {MAX_ITEMS} items at once.")
    today = _today()
    prepared = []
    for it in items:
        if not isinstance(it, dict):
            return _err("Each item must be an object.")
        if it.get("day", "today") not in DAYS:
            return _err("day must be 'today' or 'tomorrow'.")
        text = _todo_text(it)
        if text:
            prepared.append((text, today + timedelta(days=1 if it.get("day") == "tomorrow" else 0)))
    if not prepared:
        return _err("Nothing to add.")

    db = SessionLocal()
    try:
        created, skipped = [], 0
        next_pos = {}
        for text, day in prepared:
            dup = db.query(Todo).filter(Todo.day == day, Todo.text == text, Todo.done.is_(False)).first()
            if dup:
                skipped += 1
                continue
            if day not in next_pos:
                next_pos[day] = db.query(func.max(Todo.position)).filter(Todo.day == day).scalar() or 0
            next_pos[day] += 1
            t = Todo(text=text, done=False, day=day, position=next_pos[day])
            db.add(t)
            created.append(t)
        db.commit()
        for t in created:
            db.refresh(t)
        return jsonify({"status": "success", "data": [_serialize(t) for t in created], "skipped": skipped})
    finally:
        db.close()
