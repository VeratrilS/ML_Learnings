import calendar
import json
import math
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from itertools import permutations

import pytest
from flask import Flask

from api.core.config import IST
from api.core.db import Base, engine, SessionLocal
from api.domain import aptitude as mod
from api.domain.aptitude import AptAttempt, AptQuestion, aptitude_bp
from api.domain.aptitude_bank import BANK, TYPES

FIXED_NOW = datetime(2026, 10, 11, 9, 30, tzinfo=IST)


# ---------------- bank integrity ----------------
def test_bank_shape():
    assert len(BANK) >= 60
    per_type = {}
    for q in BANK:
        assert q["type"] in TYPES
        assert len(q["options"]) == 4 and len({o.lower() for o in q["options"]}) == 4, q["question"]
        assert 0 <= q["answer_index"] <= 3
        assert q["explanation"].strip() and q["difficulty"] in (1, 2, 3)
        per_type[q["type"]] = per_type.get(q["type"], 0) + 1
    assert all(per_type.get(t, 0) >= 3 for t in TYPES), per_type
    assert len({q["question"] for q in BANK}) == len(BANK)


def _q(prefix):
    hits = [q for q in BANK if q["question"].startswith(prefix)]
    assert len(hits) == 1, prefix
    return hits[0]


def _answer(prefix):
    q = _q(prefix)
    return q["options"][q["answer_index"]]


def _num(s):
    """First number in an option string ('₹1,380' -> 1380, '22.22 m/s' -> 22.22)."""
    import re
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", s)
    return float(m.group().replace(",", ""))


def _shift(word, k):
    return "".join(chr((ord(c) - 65 + k) % 26 + 65) for c in word)


def _clock_angle(h, m):
    a = abs(30 * h - 5.5 * m)
    return min(a, 360 - a)


def _odd_days(years):
    leaps = sum(1 for y in range(1, years + 1) if calendar.isleap(y))
    return (years + leaps) % 7


# Each numeric answer recomputed from scratch: (question prefix, computed value).
NUMERIC = [
    ("If 35% of a number is 84", 84 / 0.35 * 0.60),
    ("The price of sugar rises by 25%", 25 / 125 * 100),
    ("In an election between two candidates", 1120 / (0.58 - 0.42)),
    ("A shopkeeper buys an article for ₹800", (920 - 800) / 800 * 100),
    ("By selling an article for ₹1,080", 1080 / 0.9 * 1.15),
    ("A can finish a piece of work in 12 days", 1 / (1 / 12 + 1 / 18)),
    ("A and B together can finish a job in 10 days", 1 / (1 / 10 - 1 / 15)),
    ("12 men can complete", 12 * 20 / 16),
    ("A can do a piece of work in 20 days", (1 - 6 * (1 / 20 + 1 / 30)) * 30),
    ("Pipe A can fill a tank", 1 / (1 / 6 - 1 / 9)),
    ("A car covers 360 km", 360 / 4.5 * 5 / 18),
    ("A train 240 m long", (240 + 360) / (240 / 12)),
    ("A person travels from A to B at 40", 2 * 40 * 60 / (40 + 60)),
    ("Two trains, 150 m and 100 m long", 250 / ((50 + 40) * 5 / 18)),
    ("A boat's speed in still water", 36 / 18 + 36 / 12),
    ("₹4,500 is divided", 4500 * 4 / 9),
    ("The present ages of A and B", next(5 * x for x in range(1, 50) if (5 * x + 6) * 4 == (7 * x + 6) * 3)),
    ("A 60-litre mixture", 40 * 2 - 20),
    ("What is the average of the first 20", sum(range(1, 21)) / 20),
    ("The average of 5 numbers is 24", 5 * 24 - 4 * 22),
    ("The average age of 30 students", 31 * 16 - 30 * 15),
    ("A batsman scores 87 runs", next(x + 3 for x in range(200) if 16 * x + 87 == 17 * (x + 3))),
    ("What is the simple interest on ₹5,000", 5000 * 8 * 3 / 100),
    ("What is the compound interest on ₹10,000", 10000 * 1.1 ** 2 - 10000),
    ("What is the difference between compound interest", 8000 * 1.05 ** 2 - 8000 - 8000 * 0.05 * 2),
    ("A sum of money doubles itself in 8 years", 100 / 8),
    ("A sum amounts to ₹8,820", 8820 / 1.05 ** 2),
    ("In how many different ways can the letters of the word 'LEADER'", len(set(permutations("LEADER")))),
    ("A committee of 3 is to be chosen", math.comb(4, 2) * math.comb(5, 1)),
    ("How many 3-digit numbers", len(list(permutations("12345", 3)))),
    ("In how many ways can 5 people be seated", math.factorial(4)),
    ("At a party, each of 10 people", math.comb(10, 2)),
    ("Find the next number in the series: 2, 6, 12", 6 * 7),
    ("Find the next number in the series: 3, 7, 15", 2 ** 7 - 1),
    ("Find the next number in the series: 2, 3, 5, 7", 17),
    ("Find the next number in the series: 4, 9, 25", 13 ** 2),
    ("Find the next number in the series: 1, 2, 6, 24", math.factorial(6)),
    ("Find the wrong term", next(t for i, t in enumerate([2, 5, 10, 17, 26, 38, 50], 1) if t != i * i + 1)),
    ("A walks 10 m east", math.hypot(10 - 4, 14 - 6)),
    ("What is the angle between the hour hand", _clock_angle(3, 40)),
    ("How many odd days are there in 100 years", _odd_days(100)),
    ("The calendar of the year 2021", next(y for y in range(2022, 2100)
                                            if date(y, 1, 1).weekday() == date(2021, 1, 1).weekday()
                                            and calendar.isleap(y) == calendar.isleap(2021))),
]


@pytest.mark.parametrize("prefix,value", NUMERIC, ids=[p[0][:30] for p in NUMERIC])
def test_numeric_answers_recomputed(prefix, value):
    q = _q(prefix)
    got = _num(_answer(prefix))
    assert got == pytest.approx(value, abs=0.01), f"{prefix}: option {got} != computed {value}"
    others = [_num(o) for i, o in enumerate(q["options"]) if i != q["answer_index"]]
    assert all(o != pytest.approx(value, abs=0.01) for o in others), "two options match the computed answer"


def test_fraction_and_symbolic_answers_recomputed():
    dice = Fraction(sum(1 for a in range(1, 7) for b in range(1, 7) if a + b == 8), 36)
    assert _answer("Two fair dice are thrown") == f"{dice.numerator}/{dice.denominator}"
    red = Fraction(math.comb(4, 2), math.comb(10, 2))
    assert _answer("A bag contains 4 red") == f"{red.numerator}/{red.denominator}"
    head = 1 - Fraction(1, 8)
    assert _answer("Three fair coins are tossed") == f"{head.numerator}/{head.denominator}"
    kh = Fraction(4 + 13 - 1, 52)
    assert _answer("A card is drawn at random") == f"{kh.numerator}/{kh.denominator}"

    assert _answer("A number is first increased by 20%") == "4% decrease"  # 1.2 * 0.8 = 0.96
    assert _answer("A shopkeeper marks his goods 40%").startswith(f"{round(140 * 0.75 - 100)}% profit")
    cp = 990 / 1.1 + 990 / 0.9
    assert _answer("Two articles are sold for ₹990") == f"{round((cp - 1980) / cp * 100)}% loss"
    assert _answer("If A : B = 2 : 3 and B : C = 4 : 5") == "8 : 12 : 15"

    assert _answer("If CAT is coded as DBU") == _shift("DOG", 1)
    assert _answer("If MANGO is written as OCPIQ") == _shift("APPLE", 2)
    assert _answer("In a certain code, ROAD") == _shift("SWAN", 3)
    assert _answer("If BOOK is coded") == "-".join(str(ord(c) - 64) for c in "DESK")
    assert _answer("If every letter is replaced by its mirror") == "".join(chr(155 - ord(c)) for c in "GOLD")

    # Ravi: N5, E3, S9 -> 3 east, 4 south
    assert _answer("Ravi walks 5 km north") == f"{math.hypot(3, 9 - 5):g} km South-East"

    assert _answer("If 1 January 2024 was a Monday") == date(2025, 1, 1).strftime("%A")
    assert _answer("What day of the week was 15 August 1947") == date(1947, 8, 15).strftime("%A")
    m = Fraction(120, Fraction(11, 2))  # minutes after 4:00 for the hands to meet
    assert m == Fraction(240, 11) and _answer("At what time between 4 and 5") == "4:21 9/11"
    # Hands coincide 22 times a day (every 12/11 hours)
    assert int(Fraction(24) / Fraction(12, 11)) == 22 and _answer("How many times do the hour") == "22"


# ---------------- API ----------------
class FakeLLM:
    replies = []  # one per generate_json call, in order (dict or Exception)
    calls = []

    def __init__(self, *a, **kw):
        pass

    def generate_json(self, prompt, **kw):
        FakeLLM.calls.append(prompt)
        r = FakeLLM.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _wipe():
    db = SessionLocal()
    db.query(AptAttempt).delete()
    db.query(AptQuestion).delete()
    db.commit()
    db.close()


@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.register_blueprint(aptitude_bp)
    Base.metadata.create_all(bind=engine)
    _wipe()
    yield app
    _wipe()


@pytest.fixture
def now():
    return {"t": FIXED_NOW}


@pytest.fixture
def client(app, monkeypatch, now):
    monkeypatch.setattr(mod, "now_ist", lambda: now["t"])
    monkeypatch.setattr(mod, "LLMClient", FakeLLM)
    FakeLLM.replies, FakeLLM.calls = [], []
    yield app.test_client()
    _wipe()


def _qrow(qid):
    db = SessionLocal()
    q = db.get(AptQuestion, qid)
    db.close()
    return q


def test_today_is_deterministic_and_hides_answers(client):
    a = client.get("/api/aptitude/today").get_json()
    b = client.get("/api/aptitude/today").get_json()
    assert a["status"] == "success" and a["total"] == 5 and a["done"] == 0
    assert [q["id"] for q in a["data"]] == [q["id"] for q in b["data"]]
    assert len({q["id"] for q in a["data"]}) == 5
    assert len({q["type"] for q in a["data"]}) == 5  # spread across types
    assert all("answer_index" not in q and q["attempt"] is None for q in a["data"])
    db = SessionLocal()
    assert db.query(AptQuestion).filter(AptQuestion.source == "seed").count() == len(BANK)
    db.close()


def test_seeded_options_keep_the_right_answer(client):
    client.get("/api/aptitude/today")
    db = SessionLocal()
    for item in BANK:
        q = db.query(AptQuestion).filter(AptQuestion.fingerprint == mod._fingerprint(item["type"], item["question"])).one()
        assert json.loads(q.options)[q.answer_index] == item["options"][item["answer_index"]]
    db.close()


def test_answer_flow_and_set_stability(client):
    first = client.get("/api/aptitude/today").get_json()["data"]
    q0, q1 = first[0], first[1]
    right = _qrow(q0["id"]).answer_index
    r = client.post("/api/aptitude/answer", json={"question_id": q0["id"], "chosen": right, "seconds": 42.5}).get_json()
    assert r["data"]["correct"] is True and r["data"]["explanation"] and r["done_today"] == 1
    wrong = (_qrow(q1["id"]).answer_index + 1) % 4
    r = client.post("/api/aptitude/answer", json={"question_id": q1["id"], "chosen": wrong, "seconds": 10}).get_json()
    assert r["data"]["correct"] is False and r["data"]["answer_index"] == _qrow(q1["id"]).answer_index

    # Re-answering keeps the first answer
    r = client.post("/api/aptitude/answer", json={"question_id": q0["id"], "chosen": (right + 1) % 4}).get_json()
    assert r["data"]["already"] is True and r["data"]["correct"] is True

    t = client.get("/api/aptitude/today").get_json()
    assert [q["id"] for q in t["data"]] == [q["id"] for q in first]  # answering doesn't reshuffle
    assert t["done"] == 2 and t["correct"] == 1 and t["seconds"] == 52.5
    assert t["data"][0]["attempt"]["chosen"] == right and "answer_index" in t["data"][0]


def test_tomorrow_avoids_correct_and_weights_weak_types(client, now):
    db = SessionLocal()
    client.get("/api/aptitude/today")
    # History: every percentages question right; directions all wrong, over several past days.
    past = FIXED_NOW.date() - timedelta(days=3)
    pct = db.query(AptQuestion).filter(AptQuestion.type == "percentages").all()
    for q in pct:
        db.add(AptAttempt(question_id=q.id, type=q.type, chosen=q.answer_index, correct=True, seconds=20, mode="practice", day=past))
    dirs = db.query(AptQuestion).filter(AptQuestion.type == "directions").all()
    for _ in range(5):
        for q in dirs:
            db.add(AptAttempt(question_id=q.id, type=q.type, chosen=(q.answer_index + 1) % 4, correct=False, seconds=30, mode="practice", day=past))
    db.commit()
    pct_ids = {q.id for q in pct}
    db.close()

    hits = 0
    for d in range(20):
        now["t"] = FIXED_NOW + timedelta(days=d)
        data = client.get("/api/aptitude/today").get_json()["data"]
        ids, types = [q["id"] for q in data], [q["type"] for q in data]
        assert not pct_ids & set(ids)
        hits += "directions" in types
    assert hits >= 12  # weak type shows up most days (uniform would be ~5/17 of days)


def test_streak_and_stats(client, now):
    for d in (2, 1, 0):
        now["t"] = FIXED_NOW - timedelta(days=d)
        for q in client.get("/api/aptitude/today").get_json()["data"]:
            client.post("/api/aptitude/answer", json={"question_id": q["id"], "chosen": _qrow(q["id"]).answer_index, "seconds": 30})
    now["t"] = FIXED_NOW
    t = client.get("/api/aptitude/today").get_json()
    assert t["done"] == 5 and t["streak"] == 3
    s = client.get("/api/aptitude/stats").get_json()["data"]
    assert s["streak"] == 3 and s["best_streak"] == 3
    assert s["overall"]["attempts"] == 15 and s["overall"]["accuracy"] == 1.0 and s["overall"]["avg_seconds"] == 30
    tried = [x for x in s["types"] if x["attempts"]]
    assert tried and all(x["accuracy"] == 1.0 for x in tried)
    assert s["history"][-1] == {"day": FIXED_NOW.date().isoformat(), "done": 5, "correct": 5}
    # A missed day breaks the streak
    now["t"] = FIXED_NOW + timedelta(days=2)
    assert client.get("/api/aptitude/stats").get_json()["data"]["streak"] == 0


def test_practice_and_validation(client):
    r = client.get("/api/aptitude/practice?type=pnc").get_json()
    assert r["status"] == "success" and len(r["data"]) == 5 and all(q["type"] == "pnc" for q in r["data"])
    assert client.get("/api/aptitude/practice?type=nope").status_code == 400
    qid = r["data"][0]["id"]
    out = client.post("/api/aptitude/answer", json={"question_id": qid, "chosen": 0, "mode": "practice"}).get_json()
    assert out["data"]["mode"] == "practice" and out["done_today"] == 0
    assert client.post("/api/aptitude/answer", json={"question_id": qid, "chosen": 4}).status_code == 400
    assert client.post("/api/aptitude/answer", json={"question_id": True, "chosen": 1}).status_code == 400
    assert client.post("/api/aptitude/answer", json={"question_id": 999999, "chosen": 1}).status_code == 404


def _gen_q(question, answer, options=None):
    return {"question": question, "options": options or ["10", "20", "30", "40"], "answer_index": answer,
            "explanation": "Because.", "difficulty": "medium"}


def test_generate_keeps_only_agreeing_answers(client):
    FakeLLM.replies = [
        {"questions": [
            _gen_q("What is 25% of 80 in rupees exactly?", 1),        # solver agrees
            _gen_q("What is 15% of 200 in rupees exactly?", 2),       # solver disagrees
            _gen_q("Bad question with three options only?", 0, ["1", "2", "3"]),  # invalid
            _gen_q("What is 40% of 100 in rupees exactly?", "D"),     # letter answer, agrees
        ]},
        {"answers": [{"i": 0, "answer_index": 1}, {"i": 1, "answer_index": 0}, {"i": 2, "answer_index": 3}]},
    ]
    r = client.post("/api/aptitude/generate", json={"type": "percentages", "count": 4}).get_json()
    assert r["status"] == "success" and r["generated"] == 3 and r["kept"] == 2 and r["rejected"] == 1
    assert len(FakeLLM.calls) == 2 and "Because." not in FakeLLM.calls[1]  # solver works blind
    db = SessionLocal()
    ai = db.query(AptQuestion).filter(AptQuestion.source == "ai").all()
    assert {q.question for q in ai} == {"What is 25% of 80 in rupees exactly?", "What is 40% of 100 in rupees exactly?"}
    for q in ai:
        want = "20" if "25%" in q.question else "40"
        assert json.loads(q.options)[q.answer_index] == want  # shuffle kept the right answer
        assert q.difficulty == 2
    db.close()
    # New AI questions don't change today's already-picked set
    assert client.get("/api/aptitude/today").get_json()["total"] == 5


def test_generate_validation_and_failures(client):
    assert client.post("/api/aptitude/generate", json={"type": "nope"}).status_code == 400
    assert client.post("/api/aptitude/generate", json={"type": "pnc", "count": 6}).status_code == 400
    FakeLLM.replies = [RuntimeError("no key")]
    r = client.post("/api/aptitude/generate", json={"type": "pnc", "count": 2})
    assert r.status_code == 502 and "no key" in r.get_json()["message"]
    FakeLLM.replies = [{"questions": [{"question": "x"}]}]
    assert client.post("/api/aptitude/generate", json={"type": "pnc", "count": 1}).status_code == 502
