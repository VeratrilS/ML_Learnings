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
