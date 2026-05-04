from fastapi.testclient import TestClient
from main import app
import pytest

client = TestClient(app)

def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "document-intelligence-api"}

def test_users_me_unauthorized():
    response = client.get("/api/users/me")
    assert response.status_code == 401
