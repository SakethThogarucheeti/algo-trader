"""Tests for monitoring/telegram.py — TelegramAlerter"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from trading.config.settings import Settings
from trading.monitoring.telegram import TelegramAlerter


def make_settings(token: str | None = "BOT_TOKEN", chat_id: str | None = "CHAT_ID") -> Settings:
    return Settings(
        zerodha_api_key="k",
        zerodha_api_secret="s",
        postgres_url="postgresql+asyncpg://u:p@localhost/t",
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
    )


def make_mock_response(status_code: int, headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.text = "ok"
    return resp


# ---------------------------------------------------------------------------
# No-op when disabled
# ---------------------------------------------------------------------------


async def test_no_http_call_when_token_is_none() -> None:
    alerter = TelegramAlerter(make_settings(token=None))
    with patch("httpx.AsyncClient") as mock_client:
        await alerter.send_alert("test", "module")
    mock_client.assert_not_called()


# ---------------------------------------------------------------------------
# Successful send
# ---------------------------------------------------------------------------


async def test_successful_send_calls_telegram_api() -> None:
    alerter = TelegramAlerter(make_settings())
    mock_resp = make_mock_response(200)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_resp)

        await alerter.send_alert("hello", "heartbeat_miss")

    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    assert "BOT_TOKEN" in args[0]
    assert kwargs["json"]["chat_id"] == "CHAT_ID"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


async def test_rate_limit_second_call_within_window_is_noop() -> None:
    alerter = TelegramAlerter(make_settings())
    mock_resp = make_mock_response(200)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_resp)

        await alerter.send_alert("first", "heartbeat")
        await alerter.send_alert("second", "heartbeat")  # rate-limited

    assert mock_client.post.call_count == 1  # only first call posted


async def test_different_event_types_have_independent_rate_limits() -> None:
    alerter = TelegramAlerter(make_settings())
    mock_resp = make_mock_response(200)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_resp)

        await alerter.send_alert("msg1", "type_a")
        await alerter.send_alert("msg2", "type_b")  # different type → posts

    assert mock_client.post.call_count == 2


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


async def test_http_500_retried_3_times() -> None:
    alerter = TelegramAlerter(make_settings())

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=make_mock_response(500))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await alerter.send_alert("error", "crash")

    # 1 initial + 2 retries = 3 calls (attempt 1, 2, 3; fails at attempt > 3)
    assert mock_client.post.call_count == 3


async def test_http_429_waits_retry_after_then_retries() -> None:
    alerter = TelegramAlerter(make_settings())
    slept: list[int] = []

    # 429 first, then 200
    responses = [
        make_mock_response(429, headers={"Retry-After": "10"}),
        make_mock_response(200),
    ]

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=responses)

        async def fake_sleep(secs: float) -> None:
            slept.append(int(secs))

        with patch("asyncio.sleep", fake_sleep):
            await alerter.send_alert("429 test", "test")

    assert 10 in slept
    assert mock_client.post.call_count == 2


async def test_timeout_retried() -> None:
    alerter = TelegramAlerter(make_settings())

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await alerter.send_alert("timeout test", "event")

    # 3 attempts
    assert mock_client.post.call_count == 3


async def test_no_exception_raised_to_caller_on_failure() -> None:
    """Caller must not receive exceptions — alerts are best-effort."""
    alerter = TelegramAlerter(make_settings())

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=RuntimeError("network down"))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            # Should not raise
            await alerter.send_alert("failure", "event")
