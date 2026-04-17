"""
Тесты для src/utils/html_utils.py

Покрывает:
- escape()
- format_html_safe()
- safe_delete_message()
- safe_answer_callback()
- safe_parse_callback_data()
"""
import pytest
import logging
from unittest.mock import AsyncMock, MagicMock

from src.utils.html_utils import (
    escape,
    format_html_safe,
    safe_delete_message,
    safe_answer_callback,
    safe_edit_or_answer,
    suppress_telegram_errors,
)
from src.bot.keyboards.keyboard_factory import safe_parse_callback_data


# =============================================================================
# escape()
# =============================================================================

class TestEscape:
    def test_basic_html_chars(self):
        assert escape("<script>") == "&lt;script&gt;"

    def test_ampersand(self):
        assert escape("a & b") == "a &amp; b"

    def test_quotes(self):
        assert escape('"hello"') == "&quot;hello&quot;"

    def test_safe_text_unchanged(self):
        assert escape("Москва") == "Москва"

    def test_int_value(self):
        assert escape(42) == "42"

    def test_none_value(self):
        assert escape(None) == "None"


# =============================================================================
# format_html_safe()
# =============================================================================

class TestFormatHtmlSafe:
    def test_escapes_segment(self):
        result = format_html_safe("<b>{segment}</b>", segment="<evil>")
        assert result == "<b>&lt;evil&gt;</b>"

    def test_escapes_city(self):
        result = format_html_safe("Город: {city}", city="Москва & МО")
        assert result == "Город: Москва &amp; МО"

    def test_multiple_placeholders(self):
        result = format_html_safe(
            "{segment} / {city} / {count}",
            segment="<A>",
            city="Б&В",
            count=10
        )
        assert result == "&lt;A&gt; / Б&amp;В / 10"

    def test_safe_values_unchanged(self):
        result = format_html_safe("{segment}", segment="Автосалон")
        assert result == "Автосалон"

    def test_number_value(self):
        result = format_html_safe("{count}", count=100)
        assert result == "100"

    def test_html_tags_in_template_preserved(self):
        """HTML-теги в шаблоне не экранируются — только значения"""
        result = format_html_safe("<b>{name}</b>", name="test")
        assert result == "<b>test</b>"

    def test_xss_prevention(self):
        """Предотвращение XSS через пользовательские данные"""
        payload = "<script>alert('xss')</script>"
        result = format_html_safe("<b>{user_input}</b>", user_input=payload)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


# =============================================================================
# safe_delete_message()
# =============================================================================

class TestSafeDeleteMessage:
    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        message = AsyncMock()
        message.delete = AsyncMock()
        result = await safe_delete_message(message)
        assert result is True
        message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        message = AsyncMock()
        message.delete = AsyncMock(side_effect=Exception("Message not found"))
        result = await safe_delete_message(message, log=False)
        assert result is False

    @pytest.mark.asyncio
    async def test_logs_on_exception(self, caplog):
        message = AsyncMock()
        message.delete = AsyncMock(side_effect=Exception("timed out"))
        with caplog.at_level(logging.DEBUG, logger="src.utils.html_utils"):
            result = await safe_delete_message(message, log=True)
        assert result is False
        assert "timed out" in caplog.text


# =============================================================================
# safe_answer_callback()
# =============================================================================

class TestSafeAnswerCallback:
    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        callback = AsyncMock()
        callback.answer = AsyncMock()
        result = await safe_answer_callback(callback, "ok")
        assert result is True
        callback.answer.assert_called_once_with("ok", show_alert=False)

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        callback = AsyncMock()
        callback.answer = AsyncMock(side_effect=Exception("Query expired"))
        result = await safe_answer_callback(callback)
        assert result is False

    @pytest.mark.asyncio
    async def test_show_alert_passed(self):
        callback = AsyncMock()
        callback.answer = AsyncMock()
        await safe_answer_callback(callback, "Ошибка!", show_alert=True)
        callback.answer.assert_called_once_with("Ошибка!", show_alert=True)


# =============================================================================
# safe_edit_or_answer()
# =============================================================================

class TestSafeEditOrAnswer:
    @pytest.mark.asyncio
    async def test_edit_succeeds_returns_true(self):
        callback = MagicMock()
        callback.message.edit_text = AsyncMock()
        callback.message.answer = AsyncMock()
        result = await safe_edit_or_answer(callback, "текст")
        assert result is True
        callback.message.edit_text.assert_called_once()
        callback.message.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_to_answer_on_edit_failure(self):
        callback = MagicMock()
        callback.message.edit_text = AsyncMock(side_effect=Exception("Message not modified"))
        callback.message.answer = AsyncMock()
        result = await safe_edit_or_answer(callback, "текст")
        assert result is False
        callback.message.answer.assert_called_once()


# =============================================================================
# suppress_telegram_errors() decorator
# =============================================================================

class TestSuppressTelegramErrors:
    @pytest.mark.asyncio
    async def test_returns_value_on_success(self):
        @suppress_telegram_errors()
        async def my_func():
            return 42

        result = await my_func()
        assert result == 42

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        @suppress_telegram_errors(log=False)
        async def my_func():
            raise Exception("Telegram error")

        result = await my_func()
        assert result is None

    @pytest.mark.asyncio
    async def test_logs_warning_on_exception(self, caplog):
        @suppress_telegram_errors(log=True)
        async def fragile_func():
            raise ValueError("bad value")

        with caplog.at_level(logging.WARNING):
            await fragile_func()

        assert "fragile_func" in caplog.text
        assert "bad value" in caplog.text


# =============================================================================
# safe_parse_callback_data()
# =============================================================================

class TestSafeParseCallbackData:
    def test_basic_action_only(self):
        result = safe_parse_callback_data("admin_menu")
        assert result is not None
        assert result["action"] == "admin_menu"
        assert result["params"] == []

    def test_action_with_single_param(self):
        result = safe_parse_callback_data("user_view:12345")
        assert result is not None
        assert result["action"] == "user_view"
        assert result["params"] == ["12345"]

    def test_action_with_multiple_params(self):
        result = safe_parse_callback_data("ticket_status:42:resolved")
        assert result is not None
        assert result["action"] == "ticket_status"
        assert result["params"] == ["42", "resolved"]

    def test_expected_parts_met(self):
        result = safe_parse_callback_data("ticket_view:7", expected_parts=1)
        assert result is not None
        assert result["params"][0] == "7"

    def test_expected_parts_not_met_returns_none(self):
        result = safe_parse_callback_data("ticket_view", expected_parts=1)
        assert result is None

    def test_empty_string_returns_none(self):
        result = safe_parse_callback_data("")
        assert result is None

    def test_none_returns_none(self):
        result = safe_parse_callback_data(None)
        assert result is None

    def test_expected_parts_zero_allows_any(self):
        result = safe_parse_callback_data("action", expected_parts=0)
        assert result is not None

    def test_multiple_expected_parts(self):
        result = safe_parse_callback_data("a:b:c", expected_parts=2)
        assert result is not None
        assert len(result["params"]) == 2
