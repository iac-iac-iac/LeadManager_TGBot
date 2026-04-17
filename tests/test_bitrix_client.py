"""
Тесты для src/bitrix24/client.py

Покрывает:
- Валидацию webhook URL
- HTTP non-200 → Bitrix24Error
- Ошибки API в JSON → Bitrix24Error
- Retry при ClientError
- Retry при TimeoutError
- Успешный запрос
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from src.bitrix24.client import Bitrix24Client, Bitrix24Error


VALID_WEBHOOK = "https://mycompany.bitrix24.ru/rest/1/abc123def456/"


# =============================================================================
# Валидация URL
# =============================================================================

class TestWebhookValidation:
    def test_valid_ru_webhook(self):
        client = Bitrix24Client(VALID_WEBHOOK)
        assert client.webhook_url == VALID_WEBHOOK.rstrip("/")

    def test_valid_com_webhook(self):
        client = Bitrix24Client("https://mycompany.bitrix24.com/rest/2/xyz789/")
        assert "bitrix24.com" in client.webhook_url

    def test_invalid_http_scheme(self):
        with pytest.raises(ValueError):
            Bitrix24Client("http://mycompany.bitrix24.ru/rest/1/abc123/")

    def test_invalid_domain(self):
        with pytest.raises(ValueError):
            Bitrix24Client("https://mycompany.evil.com/rest/1/abc123/")

    def test_invalid_path_structure(self):
        with pytest.raises(ValueError):
            Bitrix24Client("https://mycompany.bitrix24.ru/api/1/abc123/")

    def test_webhook_url_stripped(self):
        client = Bitrix24Client(VALID_WEBHOOK)
        assert not client.webhook_url.endswith("/")


# =============================================================================
# HTTP non-200 responses
# =============================================================================

class TestHttpErrorHandling:
    @pytest.fixture
    def client(self):
        return Bitrix24Client(VALID_WEBHOOK, retry_attempts=1)

    def _make_response(self, status: int, text: str = "Error"):
        response = AsyncMock()
        response.status = status
        response.text = AsyncMock(return_value=text)
        response.json = AsyncMock(return_value={})
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=False)
        return response

    def _make_session(self, response):
        session = MagicMock()
        session.post = MagicMock(return_value=response)
        session.closed = False
        return session

    @pytest.mark.asyncio
    async def test_404_raises_bitrix_error(self, client):
        response = self._make_response(404, "Not Found")
        mock_session = self._make_session(response)

        with patch.object(client, '_get_session', return_value=mock_session):
            with pytest.raises(Bitrix24Error) as exc_info:
                await client._request("crm.lead.get", {"id": 1})

        assert "HTTP 404" in str(exc_info.value)
        assert exc_info.value.error_code == 404

    @pytest.mark.asyncio
    async def test_500_raises_bitrix_error(self, client):
        response = self._make_response(500, "Internal Server Error")
        mock_session = self._make_session(response)

        with patch.object(client, '_get_session', return_value=mock_session):
            with pytest.raises(Bitrix24Error) as exc_info:
                await client._request("crm.lead.add", {})

        assert "HTTP 500" in str(exc_info.value)
        assert exc_info.value.error_code == 500

    @pytest.mark.asyncio
    async def test_error_text_truncated_to_200_chars(self, client):
        long_error = "x" * 500
        response = self._make_response(400, long_error)
        mock_session = self._make_session(response)

        with patch.object(client, '_get_session', return_value=mock_session):
            with pytest.raises(Bitrix24Error) as exc_info:
                await client._request("crm.lead.add", {})

        assert len(str(exc_info.value)) <= 300

    @pytest.mark.asyncio
    async def test_200_with_api_error_field(self, client):
        response = self._make_response(200)
        response.json = AsyncMock(return_value={
            "error": "ACCESS_DENIED",
            "error_description": "Access denied"
        })
        mock_session = self._make_session(response)

        with patch.object(client, '_get_session', return_value=mock_session):
            with pytest.raises(Bitrix24Error) as exc_info:
                await client._request("crm.lead.get", {"id": 99})

        assert "Access denied" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_200_success_returns_result(self, client):
        response = self._make_response(200)
        response.json = AsyncMock(return_value={"result": {"ID": "42"}})
        mock_session = self._make_session(response)

        with patch.object(client, '_get_session', return_value=mock_session):
            result = await client._request("crm.lead.get", {"id": 42})

        assert result == {"ID": "42"}


# =============================================================================
# Retry logic
# =============================================================================

class TestRetryLogic:
    @pytest.fixture
    def client(self):
        return Bitrix24Client(VALID_WEBHOOK, retry_attempts=3, retry_delay=0.0)

    def _make_response(self, status: int = 200):
        response = AsyncMock()
        response.status = status
        response.text = AsyncMock(return_value="error")
        response.json = AsyncMock(return_value={"result": {"ID": "1"}})
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=False)
        return response

    @pytest.mark.asyncio
    async def test_retries_on_client_error_then_succeeds(self, client):
        """Клиент делает retry при ClientError, потом успешно"""
        success_response = self._make_response(200)
        
        call_count = 0
        
        async def mock_get_session():
            nonlocal call_count
            session = MagicMock()
            call_count += 1
            if call_count < 3:
                # Первые 2 попытки — ошибка
                fail_resp = MagicMock()
                fail_resp.__aenter__ = MagicMock(side_effect=aiohttp.ClientError("connection failed"))
                fail_resp.__aexit__ = AsyncMock(return_value=False)
                session.post = MagicMock(return_value=fail_resp)
            else:
                session.post = MagicMock(return_value=success_response)
            session.closed = False
            return session

        with patch.object(client, '_get_session', side_effect=mock_get_session):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await client._request("crm.lead.get", {"id": 1})

        assert result == {"ID": "1"}

    @pytest.mark.asyncio
    async def test_raises_after_all_retries_exhausted(self, client):
        """После исчерпания всех попыток — Bitrix24Error"""
        call_count = 0

        async def mock_get_session():
            nonlocal call_count
            call_count += 1
            session = MagicMock()
            fail_resp = MagicMock()
            fail_resp.__aenter__ = MagicMock(side_effect=aiohttp.ClientError("connection refused"))
            fail_resp.__aexit__ = AsyncMock(return_value=False)
            session.post = MagicMock(return_value=fail_resp)
            session.closed = False
            return session

        with patch.object(client, '_get_session', side_effect=mock_get_session):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                with pytest.raises(Bitrix24Error) as exc_info:
                    await client._request("crm.lead.get", {"id": 1})

        assert call_count == 3
        assert "Ошибка соединения" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_raises_on_timeout_after_all_retries(self, client):
        """Timeout exhausts retries → Bitrix24Error"""
        call_count = 0

        async def mock_get_session():
            nonlocal call_count
            call_count += 1
            session = MagicMock()
            fail_resp = MagicMock()
            fail_resp.__aenter__ = MagicMock(side_effect=asyncio.TimeoutError())
            fail_resp.__aexit__ = AsyncMock(return_value=False)
            session.post = MagicMock(return_value=fail_resp)
            session.closed = False
            return session

        with patch.object(client, '_get_session', side_effect=mock_get_session):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                with pytest.raises(Bitrix24Error) as exc_info:
                    await client._request("crm.lead.get", {"id": 1})

        assert call_count == 3
        assert "Таймаут" in str(exc_info.value)
