import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from src.main import app


@pytest.mark.asyncio
async def test_ingest_single_email():
    mock_resolve = AsyncMock(
        return_value={
            "profile_id": "550e8400-e29b-41d4-a716-446655440000",
            "is_known": False,
            "confidence": 1.0,
            "signals_count": 1,
        }
    )
    with patch("src.api.v1.identity.resolve", mock_resolve):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/identity/ingest",
                json={
                    "signals": [{"type": "email", "value": "test@example.com"}],
                    "source": "test",
                },
            )
    assert response.status_code == 200
    data = response.json()
    assert "profile_id" in data
    assert data["confidence"] == 1.0


@pytest.mark.asyncio
async def test_ingest_multiple_signals():
    mock_resolve = AsyncMock(
        return_value={
            "profile_id": "550e8400-e29b-41d4-a716-446655440001",
            "is_known": False,
            "confidence": 1.0,
            "signals_count": 3,
        }
    )
    with patch("src.api.v1.identity.resolve", mock_resolve):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/identity/ingest",
                json={
                    "signals": [
                        {"type": "email", "value": "user@example.com"},
                        {"type": "phone", "value": "+5511999999999"},
                        {"type": "gclid", "value": "Cj0KCQjwlN6tBhCsMARIsAKZvD"},
                    ],
                    "source": "web",
                },
            )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_profile_not_found():
    with patch(
        "src.api.v1.identity.get_profile_with_signals",
        AsyncMock(return_value=(None, [])),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/identity/profile/00000000-0000-0000-0000-000000000000"
            )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_signal_hash_determinism():
    from src.identity.hashing import SignalType, compute_hash

    h1 = compute_hash(SignalType.EMAIL, "  TEST@Gmail.COM  ")
    h2 = compute_hash(SignalType.EMAIL, "test@gmail.com")
    assert h1 == h2, "Normalização de email deve ser determinística"


@pytest.mark.asyncio
async def test_phone_normalization():
    from src.identity.hashing import SignalType, compute_hash

    h1 = compute_hash(SignalType.PHONE, "+55 (11) 99999-9999")
    h2 = compute_hash(SignalType.PHONE, "5511999999999")
    assert h1 == h2, "Normalização de telefone deve remover caracteres não numéricos"
