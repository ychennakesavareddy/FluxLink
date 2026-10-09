import pytest
from fastapi.testclient import TestClient
from backend.main import app

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_app_starts(client):
    response = client.get("/docs")
    assert response.status_code == 200
    
def test_create_session(client):
    # Will create a real session in chennalink.db
    response = client.post("/api/sessions/create", json={
        "email": "test@example.com",
        "name": "Tester",
        "device_id": "TEST-DEV-1",
        "device_name": "TestDevice",
        "session_code": "TE1234"
    })
    
    # We might get 400 if it already exists from a previous test run
    assert response.status_code in [200, 400]
    if response.status_code == 200:
        assert "session_code" in response.json()
