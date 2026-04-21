import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestDocumentEndpoints:
    def test_create_document_no_auth(self, client):
        tenant_id = uuid.uuid4()
        resp = client.post(
            f"/api/tenants/{tenant_id}/documents",
            json={"title": "Test", "content": "Test content"},
        )
        assert resp.status_code == 422  # Missing header

    def test_create_document_bad_auth(self, client):
        tenant_id = uuid.uuid4()
        resp = client.post(
            f"/api/tenants/{tenant_id}/documents",
            json={"title": "Test", "content": "Test content"},
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    def test_create_document_empty_title(self, client):
        tenant_id = uuid.uuid4()
        resp = client.post(
            f"/api/tenants/{tenant_id}/documents",
            json={"title": "", "content": "Test content"},
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert resp.status_code == 422

    def test_create_document_empty_content(self, client):
        tenant_id = uuid.uuid4()
        resp = client.post(
            f"/api/tenants/{tenant_id}/documents",
            json={"title": "Test", "content": ""},
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert resp.status_code == 422
