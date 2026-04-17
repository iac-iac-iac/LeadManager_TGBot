"""
Утилиты для безопасного HTML-экранирования в шаблонах Telegram-сообщений

Использование:
    from src.utils.html_utils import format_html_safe

    text = format_html_safe(
        "<b>{segment}</b>: город {city}",
        segment=segment,
        city=city
    )
"""
import html
import functools
import logging
from typing import Any

logger = logging.getLogger(__name__)


def escape(value: Any) -> str:
    """HTML-экранирование одного значения"""
    return html.escape(str(value))


def format_html_safe(template: str, **kwargs: Any) -> str:
    """
    Форматирует шаблон с автоматическим HTML-экранированием всех значений.

    Все {placeholders} экранируются через html.escape(), что предотвращает
    XSS/HTML-инъекцию от пользовательских данных (segment, city, full_name).

    Args:
        template: Строка-шаблон с {placeholder}
        **kwargs: Значения для подстановки (будут экранированы)

    Returns:
        Строка с экранированными значениями

    Example:
        >>> format_html_safe("<b>{name}</b>: {city}", name="<script>", city="Москва")
        '<b>&lt;script&gt;</b>: Москва'
    """
    escaped_kwargs = {k: html.escape(str(v)) for k, v in kwargs.items()}
    return template.format(**escaped_kwargs)


def suppress_telegram_errors(log: bool = True):
    """
    Декоратор для подавления Telegram-ошибок при работе с сообщениями.

    Заменяет паттерн:
        try:
            await message.delete()
        except Exception:
            pass

    На:
        @suppress_telegram_errors(log=True)
        async def delete_msg(message):
            await message.delete()

    Использование для inline-вызовов:
        from src.utils.html_utils import suppress_telegram_errors
        from functools import partial

        async def safe_delete(msg):
            try:
                await msg.delete()
            except Exception as e:
                logger.debug(f"Не удалось удалить сообщение: {e}")
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if log:
                    logger.warning(
                        f"{func.__name__} suppressed Telegram error: "
                        f"{type(e).__name__}: {e}"
                    )
                return None
        return wrapper
    return decorator


async def safe_delete_message(message, log: bool = True) -> bool:
    """
    Безопасное удаление сообщения с логированием.

    Returns:
        True если удалено, False если ошибка
    """
    try:
        await message.delete()
        return True
    except Exception as e:
        if log:
            logger.debug(f"Не удалось удалить сообщение: {type(e).__name__}: {e}")
        return False


async def safe_answer_callback(callback, text: str = "", show_alert: bool = False) -> bool:
    """
    Безопасный ответ на callback_query с логированием.

    Заменяет паттерн:
        try:
            await callback.answer()
        except Exception:
            pass

    Returns:
        True если ответ отправлен, False если ошибка
    """
    try:
        await callback.answer(text, show_alert=show_alert)
        return True
    except Exception as e:
        logger.debug(f"Не удалось ответить на callback: {type(e).__name__}: {e}")
        return False


async def safe_edit_or_answer(callback, text: str, **kwargs) -> bool:
    """
    Редактирует существующее сообщение или отправляет новое, если edit не удался.

    Заменяет паттерн:
        try:
            await callback.message.edit_text(...)
        except Exception:
            await callback.message.answer(...)

    Returns:
        True если edit, False если answer (fallback)
    """
    try:
        await callback.message.edit_text(text, **kwargs)
        return True
    except Exception as e:
        logger.debug(f"edit_text не удался ({type(e).__name__}), отправляем новое сообщение")
        await callback.message.answer(text, **kwargs)
        return False
