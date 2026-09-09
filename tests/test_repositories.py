import pytest
from api.core.db import Base, engine, SessionLocal
from api.domain.models import NotificationLog, Settings
from api.domain.repositories import NotificationRepository

@pytest.fixture(scope="module")
def db_session():
    # Setup fresh DB for tests
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(autouse=True)
def clean_db(db_session):
    """Clean up test data between tests to prevent cross-contamination."""
    yield
    db_session.query(NotificationLog).delete()
    db_session.query(Settings).delete()
    db_session.commit()

def test_settings_repo(db_session):
    repo = NotificationRepository(db_session)
    
    # Test setting a new value
    repo.set_setting("leetcode_interval_minutes", "10")
    val = repo.get_setting("leetcode_interval_minutes")
    assert val == "10", "Setting should be saved and retrieved correctly"

    # Test updating an existing value
    repo.set_setting("leetcode_interval_minutes", "30")
    val = repo.get_setting("leetcode_interval_minutes")
    assert val == "30", "Setting should be updated correctly"

def test_spaced_repetition_logic(db_session):
    repo = NotificationRepository(db_session)
    
    # 1. Create a log
    log = repo.log_notification(task_type="leetcode", title="Two Sum", content="Array problem")
    assert log.is_completed == False, "New logs should be uncompleted by default"
    
    # 2. Check uncompleted tasks
    uncompleted = repo.get_uncompleted_leetcode_tasks()
    assert len(uncompleted) > 0, "There should be uncompleted tasks"
    assert uncompleted[0].title == "Two Sum"
    
    # 3. Mark as completed
    repo.mark_task_completed(log.id, True)
    
    # 4. Check uncompleted tasks again
    uncompleted_after = repo.get_uncompleted_leetcode_tasks()
    assert len(uncompleted_after) == 0, "Task should be removed from uncompleted list"

def test_get_all_sent_titles(db_session):
    """Tests that get_all_sent_titles returns BOTH completed and uncompleted titles."""
    repo = NotificationRepository(db_session)
    
    # Add a completed and an uncompleted problem
    log1 = repo.log_notification(task_type="leetcode", title="Two Sum", content="Array problem")
    repo.mark_task_completed(log1.id, True)
    repo.log_notification(task_type="leetcode", title="Three Sum", content="Array problem")
    
    # Also add a non-leetcode log that should NOT appear
    repo.log_notification(task_type="incident", title="Traffic Incident", content="Some incident")
    
    sent_titles = repo.get_all_sent_titles()
    assert "Two Sum" in sent_titles, "Completed titles should be in the sent set"
    assert "Three Sum" in sent_titles, "Uncompleted titles should also be in the sent set"
    assert "Traffic Incident" not in sent_titles, "Non-leetcode logs should NOT be in the sent set"
    assert len(sent_titles) == 2

def test_get_latest_successful_leetcode_log(db_session):
    """Tests that failed sends are excluded from the latest successful log query."""
    repo = NotificationRepository(db_session)
    
    # Log a successful entry
    repo.log_notification(task_type="leetcode", title="Two Sum", content="Array", status="success")
    # Log a failed entry (more recent)
    repo.log_notification(task_type="leetcode", title="Three Sum", content="Array", status="failed")
    
    latest = repo.get_latest_successful_leetcode_log()
    assert latest is not None, "Should find a successful log"
    assert latest.title == "Two Sum", "Should return the successful log, not the failed one"
    assert latest.status == "success"

def test_get_latest_successful_returns_none_when_no_success(db_session):
    """Tests that None is returned when there are no successful logs."""
    repo = NotificationRepository(db_session)
    
    # Only log a failed entry
    repo.log_notification(task_type="leetcode", title="Failed Problem", content="Test", status="failed")
    
    latest = repo.get_latest_successful_leetcode_log()
    assert latest is None, "Should return None when no successful logs exist"

