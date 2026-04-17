"""
Тесты для DatabaseSessionMiddleware

Покрывает:
- session инжектируется в data
- session_factory инжектируется в data
- commit при успешном завершении handler
- rollback при исключении в handler
- исключение пробрасывается дальше после rollback
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, call

from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.middleware.database import DatabaseSessionMiddleware


@pytest.fixture
def mock_session():
    """Мок AsyncSession с commit/rollback"""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    """Мок фабрики сессий"""
    factory = MagicMock()
    
    # Context manager behavior
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = ctx
    
    return factory


@pytest.fixture
def middleware(mock_session_factory):
    return DatabaseSessionMiddleware(mock_session_factory)


class TestDatabaseSessionMiddleware:
    @pytest.mark.asyncio
    async def test_session_injected_into_data(self, middleware, mock_session):
        """session добавляется в data"""
        captured_data = {}

        async def handler(event, data):
            captured_data.update(data)
            return "ok"

        await middleware(handler, MagicMock(), {})

        assert "session" in captured_data
        assert captured_data["session"] is mock_session

    @pytest.mark.asyncio
    async def test_session_factory_injected_into_data(self, middleware, mock_session_factory):
        """session_factory добавляется в data"""
        captured_data = {}

        async def handler(event, data):
            captured_data.update(data)
            return "ok"

        await middleware(handler, MagicMock(), {})

        assert "session_factory" in captured_data
        assert captured_data["session_factory"] is mock_session_factory

    @pytest.mark.asyncio
    async def test_commit_on_success(self, middleware, mock_session):
        """commit вызывается при успешном выполнении handler"""
        async def handler(event, data):
            return "result"

        await middleware(handler, MagicMock(), {})

        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()

    @pytest.mark.asyncio
    async def test_rollback_on_exception(self, middleware, mock_session):
        """rollback вызывается при исключении в handler"""
        async def handler(event, data):
            raise ValueError("handler error")

        with pytest.raises(ValueError):
            await middleware(handler, MagicMock(), {})

        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_propagates_after_rollback(self, middleware, mock_session):
        """Исключение пробрасывается после rollback"""
        class CustomError(Exception):
            pass

        async def handler(event, data):
            raise CustomError("original error")

        with pytest.raises(CustomError, match="original error"):
            await middleware(handler, MagicMock(), {})

    @pytest.mark.asyncio
    async def test_handler_return_value_preserved(self, middleware):
        """Возвращаемое значение handler не теряется"""
        async def handler(event, data):
            return {"key": "value"}

        result = await middleware(handler, MagicMock(), {})

        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_existing_data_preserved(self, middleware, mock_session):
        """Существующие данные в data не перезаписываются (кроме session/session_factory)"""
        initial_data = {"bot": "mock_bot", "state": "mock_state"}
        captured_data = {}

        async def handler(event, data):
            captured_data.update(data)
            return "ok"

        await middleware(handler, MagicMock(), initial_data.copy())

        assert captured_data["bot"] == "mock_bot"
        assert captured_data["state"] == "mock_state"
        assert "session" in captured_data
