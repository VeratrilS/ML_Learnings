import pytest
from unittest.mock import patch, MagicMock
from api.app import app
from api.core.db import SessionLocal, Base, engine
from api.domain.repositories import NotificationRepository
from api.domain.models import NotificationLog

@pytest.fixture(scope="module")
def client():
    # Setup fresh DB
    Base.metadata.create_all(bind=engine)
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(autouse=True)
def clean_db():
    """Clean up test data between tests to prevent cross-contamination."""
    yield
    db = SessionLocal()
    try:
        db.query(NotificationLog).delete()
        db.commit()
    finally:
        db.close()

def test_cron_skips_when_recent(client):
    db = SessionLocal()
    repo = NotificationRepository(db)
    # Set interval to 60 minutes
    repo.set_setting("leetcode_interval_minutes", "60")
    # Log a very recent successful notification
    repo.log_notification("leetcode", "Recent Title", "Test Content", status="success")
    db.close()
    
    # Should skip because we just logged one
    response = client.post('/api/cron')
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "skipped"
    assert "Only" in data["message"]

def test_cron_does_not_skip_after_failed_send(client):
    """Bug 5 regression test: A failed send should NOT reset the cron timer."""
    db = SessionLocal()
    repo = NotificationRepository(db)
    repo.set_setting("leetcode_interval_minutes", "60")
    # Log a failed notification — this should NOT count as a recent run
    repo.log_notification("leetcode", "Failed Title", "Test Content", status="failed")
    db.close()

    # Mock the notifier so we don't need real API keys
    mock_result = {"status": "success", "title": "Two Sum", "difficulty": "Easy"}
    with patch('api.domain.factory.NotifierFactory.get_notifier') as mock_factory:
        mock_notifier = MagicMock()
        mock_notifier.run.return_value = mock_result
        mock_factory.return_value = mock_notifier

        response = client.post('/api/cron')
        assert response.status_code == 200
        data = response.get_json()
        # Should NOT be skipped because the last log was a failure
        assert data["status"] == "success"

@patch('api.domain.factory.NotifierFactory.get_notifier')
def test_cron_runs_when_due(mock_factory, client):
    db = SessionLocal()
    repo = NotificationRepository(db)
    # Set interval to 0 minutes so it is ALWAYS due
    repo.set_setting("leetcode_interval_minutes", "0")
    db.close()

    mock_result = {"status": "success", "title": "Two Sum", "difficulty": "Easy"}
    mock_notifier = MagicMock()
    mock_notifier.run.return_value = mock_result
    mock_factory.return_value = mock_notifier
    
    response = client.post('/api/cron')
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert "title" in data["data"]

@patch('api.domain.factory.NotifierFactory.get_notifier')
def test_trigger_endpoint(mock_factory, client):
    """Test the /api/trigger endpoint works for both incident and leetcode types."""
    mock_result = {"status": "success", "title": "Test", "category": "Traffic", "type": "Road Accident"}
    mock_notifier = MagicMock()
    mock_notifier.run.return_value = mock_result
    mock_factory.return_value = mock_notifier

    response = client.post('/api/trigger', json={"type": "incident"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"

def test_settings_endpoint(client):
    """Test the /api/settings GET and POST endpoints."""
    # POST a new setting
    response = client.post('/api/settings', json={"leetcode_interval_minutes": "30"})
    assert response.status_code == 200
    
    # GET the setting back
    response = client.get('/api/settings')
    assert response.status_code == 200
    data = response.get_json()
    assert data["leetcode_interval_minutes"] == "30"
