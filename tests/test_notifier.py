"""The core promise: a LeetCode problem is never sent twice."""
from unittest.mock import MagicMock

import pytest

from api.core.db import Base, engine, SessionLocal
from api.domain.models import NotificationLog, Settings
from api.domain.notifiers import LeetcodeNotifier
from api.domain.problem_bank import PROBLEMS
from api.domain.repositories import NotificationRepository, normalize_title


@pytest.fixture()
def repo():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    yield NotificationRepository(db)
    db.query(NotificationLog).delete()
    db.query(Settings).delete()
    db.commit()
    db.close()


def _notifier(repo, send_ok=True, llm_fails=False):
    llm = MagicMock()
    if llm_fails:
        llm.generate_json.side_effect = RuntimeError("quota")
    else:
        llm.generate_json.return_value = {"statement": "s", "hints": ["h"], "approach": ["a"], "cpp_code": "int main(){}"}
    email = MagicMock()
    email.send_email.return_value = send_ok
    return LeetcodeNotifier(llm, email, repo, "me@example.com")


def test_problem_bank_is_unique():
    slugs = [p[1] for p in PROBLEMS]
    assert len(slugs) == len(set(slugs)) and len(slugs) > 250


def test_never_repeats_across_many_runs(repo):
    notifier = _notifier(repo)
    titles = [notifier.run()["title"] for _ in range(60)]
    assert len(titles) == len(set(titles))


def test_no_repeat_even_when_llm_fails(repo):
    notifier = _notifier(repo, llm_fails=True)
    results = [notifier.run() for _ in range(10)]
    assert len({r["title"] for r in results}) == 10
    assert all(not r["has_writeup"] for r in results)


def test_failed_email_does_not_burn_problem(repo):
    _notifier(repo, send_ok=False).run()
    assert repo.get_sent_keys("leetcode") == set()


def test_legacy_titles_are_respected(repo):
    # Old LLM-era rows had titles only (sometimes with suffixes) and no slug
    repo.log_notification("leetcode", "Two Sum (Fallback)", "q")
    keys = repo.get_sent_keys("leetcode")
    assert normalize_title("Two Sum") in keys
    picked = [_notifier(repo).pick_problem() for _ in range(30)]
    assert all(p["slug"] != "two-sum" for p in picked)


def test_topic_rotates(repo):
    notifier = _notifier(repo)
    topics = [notifier.run()["topic"] for _ in range(12)]
    assert all(a != b for a, b in zip(topics, topics[1:]))


def test_difficulty_preference(repo):
    repo.set_setting("leetcode_difficulty", "hard")
    notifier = _notifier(repo)
    assert all(notifier.run()["difficulty"] == "Hard" for _ in range(5))
