"""API 路由测试"""
import pytest
from fastapi.testclient import TestClient

from omniops.api.main import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestHealthCheck:
    def test_health(self, client):
        response = client.get("/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestSessionCreation:
    def test_create_session_with_csv(self, client):
        csv_content = b"ne_name,alarm_code,severity\nNE-01,LINK_FAIL,Critical"
        response = client.post(
            "/v1/sessions",
            files={"file": ("alarms.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] in ("analyzing", "perceived", "completed", "needs_review")

    def test_create_session_empty_csv(self, client):
        csv_content = b"ne_name,alarm_code\n"
        response = client.post(
            "/v1/sessions",
            files={"file": ("empty.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 400

    def test_get_nonexistent_session(self, client):
        response = client.get("/v1/sessions/nonexistent_id")
        assert response.status_code == 404

    def test_feedback_requires_valid_session(self, client):
        response = client.post(
            "/v1/sessions/nonexistent_id/feedback",
            json={"decision": "adopted", "actual_action": "test", "effectiveness": "resolved"},
        )
        assert response.status_code == 404