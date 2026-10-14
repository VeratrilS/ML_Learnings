import json
import pytest

from api.app import app
from api.core.db import Base, SessionLocal, engine
from api.domain.century import CenturyFeatureState, CENTURY_CATALOG


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.query(CenturyFeatureState).delete()
    db.commit()
    yield
    db.query(CenturyFeatureState).delete()
    db.commit()
    db.close()


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_century_catalog_length_and_domains(client):
    res = client.get("/api/century/catalog")
    assert res.status_code == 200
    data = res.get_json()
    assert "catalog" in data
    assert "domains" in data
    assert "stats" in data
    # Verifies the full century catalog
    assert len(data["catalog"]) == 100
    assert len(data["domains"]) >= 7


def test_century_action_trigger_and_xp(client):
    res = client.post("/api/century/action/bughunt")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["xp_awarded"] >= 50
    assert data["state"]["usage_count"] == 1


def test_century_mastery_progression(client):
    # Trigger 5 actions to test mastery unlock
    for i in range(5):
        res = client.post("/api/century/action/hotseat")
        assert res.status_code == 200

    catalog_res = client.get("/api/century/catalog")
    cat = catalog_res.get_json()["catalog"]
    hotseat_feat = next((f for f in cat if f["id"] == "hotseat"), None)
    assert hotseat_feat is not None
    assert hotseat_feat["status"] == "mastered"


def test_ats_analyze(client):
    res = client.post("/api/century/ats/analyze", json={
        "bullet": "Worked on backend REST API to make it faster and helped team fix bugs.",
        "target_role": "Backend Engineer"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "score" in data
    assert len(data["ai_rewrites"]) == 3
    assert len(data["weak_verbs_found"]) >= 1


def test_archsim_simulate(client):
    res = client.post("/api/century/archsim/simulate", json={
        "rps": 20000,
        "instances": 4,
        "cdn_enabled": True,
        "cache_enabled": True,
        "db_replicas": 2,
        "scenario": "none"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "metrics" in data
    assert data["metrics"]["p99_latency_ms"] > 0
    assert "bottlenecks" in data
