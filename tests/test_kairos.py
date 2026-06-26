"""Testes KAIROS v2."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.agents.kairos.guardrails import is_within_sending_window
from src.main import app

ADMIN_HEADERS = {"X-Admin-Key": "test_admin_key"}


@pytest.fixture(autouse=True)
def _admin_key():
    with patch("src.api.v1.admin.settings.admin_api_key", "test_admin_key"):
        yield


def test_sending_window_returns_tuple():
    ok, reason = is_within_sending_window()
    assert isinstance(ok, bool)
    assert isinstance(reason, str)


@pytest.mark.asyncio
async def test_kairos_run_starts():
    with patch("src.api.v1.kairos.run_kairos", AsyncMock(return_value={"run_id": "abc"})):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/kairos/run",
                headers=ADMIN_HEADERS,
                json={
                    "trigger_type": "manual",
                    "segment": "existing_customer",
                    "max_per_segment": 3,
                },
            )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"
    assert data["segment"] == "existing_customer"


@pytest.mark.asyncio
async def test_kairos_status_requires_admin():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/kairos/status")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_kairos_status_ok():
    mock_stats = [{"status": "email_sent", "count": 2, "segment": "existing_customer"}]
    mock_runs = [{"run_id": "abc12345", "started_at": "2026-06-26", "sequences": 2}]

    async def fake_execute(query, params=None):
        class Result:
            def fetchall(self):
                sql = str(query)
                if "GROUP BY status" in sql:
                    return [type("Row", (), {"_mapping": mock_stats[0]})()]
                return [type("Row", (), {"_mapping": mock_runs[0]})()]

        return Result()

    mock_session = AsyncMock()
    mock_session.execute = fake_execute
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("src.api.v1.kairos.AsyncSessionFactory", return_value=mock_session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/kairos/status", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    assert "sequence_stats" in response.json()


@pytest.mark.asyncio
async def test_resend_webhook_accepts_payload():
    with patch(
        "src.api.v1.webhooks.handle_resend_event",
        AsyncMock(return_value=None),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/webhooks/resend/email-events",
                json={"type": "email.opened", "data": {"email_id": "msg_123"}},
            )
    assert response.status_code == 200
    assert response.json()["received"] is True
