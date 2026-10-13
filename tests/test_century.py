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
