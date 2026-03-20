"""
Middleware для автоматического удаления предыдущих сообщений

Удаляет сообщение после любого callback_query (кроме пагинации)
"""
from typing import Callable, Dict, Any
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from ...logger import get_logger

logger = get_logger(__name__)


class DeletePreviousMessageMiddleware(BaseMiddleware):
    """
    Middleware для удаления предыдущего сообщения после callback_query
    
    Автоматически удаляет сообщение на которое была нажата кнопка
    """

    async def __call__(
        self,
        handler: Callable,
        event: CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """
        Обработка callback_query с удалением предыдущего сообщения
        
        Args:
            handler: Следующий обработчик
            event: CallbackQuery
            data: Данные события
            
        Returns:
            Результат работы handler
        """
        # Сначала выполняем обработчик
        result = await handler(event, data)
        
        # Проверяем тип события для удаления
        callback_data = event.data
        
        # Исключения для пагинации (edit_text вместо delete)
        pagination_prefixes = [
            "segments_page:",
            "ticket_page:",
            "ticket_filter:",
            "stats_",
        ]
        
        is_pagination = any(
            callback_data.startswith(prefix) 
            for prefix in pagination_prefixes
        )
        
        # Исключения для кнопок информации
        info_buttons = [
            "segments_page_info",
        ]
        
        is_info = callback_data in info_buttons
        
        # Удаляем сообщение если это не пагинация и не info
        if not is_pagination and not is_info:
            try:
                await event.message.delete()
            except Exception as e:
                # Игнорируем ошибки (сообщение уже удалено или нельзя удалить)
                logger.debug(f"Не удалось удалить сообщение: {type(e).__name__}: {e}")
        
        return result
