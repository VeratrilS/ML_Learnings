from api.app import app


def test_feature_flags_roundtrip():
    c = app.test_client()
    assert c.get('/api/features').get_json()["data"] == {}
    assert c.put('/api/features/gym', json={"status": "approved"}).status_code == 200
    assert c.put('/api/features/notes', json={"status": "hidden"}).status_code == 200
    assert c.get('/api/features').get_json()["data"] == {"gym": "approved", "notes": "hidden"}
    assert c.put('/api/features/gym', json={"status": "nope"}).status_code == 400
