import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Tenant


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_tenant():
    return Tenant(
        id=uuid.uuid4(),
        name="Test Org",
        slug="test-org",
        api_key="tbm_test123",
        system_prompt="You are a helpful test assistant.",
        widget_config={"primary_color": "#000000"},
        active=True,
    )


class TestChatEndpoint:
    def test_chat_missing_org(self, client):
        resp = client.post("/api/chat", json={
            "org_id": "nonexistent",
            "message": "Hello",
            "session_id": "sess_test",
        })
        assert resp.status_code == 404

    def test_chat_empty_message(self, client):
        resp = client.post("/api/chat", json={
            "org_id": "test",
            "message": "",
            "session_id": "sess_test",
        })
        assert resp.status_code == 422

    def test_chat_missing_session(self, client):
        resp = client.post("/api/chat", json={
            "org_id": "test",
            "message": "Hello",
        })
        assert resp.status_code == 422

    def test_chat_message_too_long(self, client):
        resp = client.post("/api/chat", json={
            "org_id": "test",
            "message": "x" * 4001,
            "session_id": "sess_test",
        })
        assert resp.status_code == 422


class TestHealthCheck:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "tbm-chatbot"
