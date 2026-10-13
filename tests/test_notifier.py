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


def test_spaced_repetition_schedule(repo):
    from datetime import timedelta
    from api.domain.repositories import INITIAL_STABILITY
    log = repo.log_notification("leetcode", "Two Sum", None, slug="two-sum", difficulty="Easy")
    repo.mark_task_completed(log.id, True)
    assert log.review_stage == 0 and log.next_review_at - log.completed_at == timedelta(days=INITIAL_STABILITY["Easy"])
    assert repo.get_due_reviews() == []
    log.next_review_at = log.completed_at - timedelta(minutes=1)
    repo.db.commit()
    assert [l.id for l in repo.get_due_reviews()] == [log.id]
    repo.record_review(log, "good")
    assert log.review_stage == 1 and repo.get_due_reviews() == []
    repo.record_review(log, "again")
    assert log.review_stage == 2 and log.lapses == 1  # review_stage counts reviews
    now = log.last_review_at
    for _ in range(40):  # on-time 'easy' reviews eventually retire the problem
        if log.next_review_at is None:
            break
        now = log.next_review_at
        repo.record_review(log, "easy", now=now)
    assert log.next_review_at is None  # graduated


def test_hidden_rows_still_block_repeats(repo):
    log = repo.log_notification("leetcode", "Two Sum", None, slug="two-sum")
    repo.hide_log(log.id)
    assert "two-sum" in repo.get_sent_keys("leetcode")
    assert repo.get_logs("leetcode") == []


def test_mixed_favours_medium_and_hard(repo):
    from collections import Counter
    counts = Counter(_notifier(repo).pick_problem("mixed")["difficulty"] for _ in range(600))
    assert counts["Medium"] > counts["Easy"] and counts["Hard"] > counts["Easy"]
    assert counts["Easy"] < 600 * 0.3  # weights 1:3:2 -> about 1 in 6 is Easy


def test_only_striver_problems_when_bank_exhausted(repo, monkeypatch):
    import api.domain.integrations as integrations
    monkeypatch.setattr(integrations, "leetcode_random_unsent", lambda *a, **k: pytest.fail("must not leave the A2Z bank"))
    for title, slug, *_ in PROBLEMS:
        repo.log_notification("leetcode", title, "q", slug=slug)
    slugs = {p[1] for p in PROBLEMS}
    assert _notifier(repo).pick_problem()["slug"] in slugs  # an unsolved A2Z problem comes back
