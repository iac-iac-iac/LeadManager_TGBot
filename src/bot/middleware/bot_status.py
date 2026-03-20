"""
Middleware проверки статуса бота

Блокирует обработку сообщений от обычных пользователей,
если бот остановлен или находится на техобслуживании.
Админы всегда имеют доступ.
"""
from typing import Callable, Dict, Any
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import crud
from ...logger import get_logger

logger = get_logger(__name__)


class BotStatusMiddleware(BaseMiddleware):
    """
    Middleware для проверки статуса бота
    
    Если бот остановлен (stopped) или на техобслуживании (maintenance):
    - Админы пропускаются
    - Обычные пользователи получают уведомление и блокируются
    """

    async def __call__(
        self,
        handler: Callable,
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """
        Обработка события
        
        Args:
            handler: Следующий обработчик в цепочке
            event: Событие (Message или CallbackQuery)
            data: Данные события (включая session)
            
        Returns:
            Результат работы handler или None если заблокировано
        """
        # Получаем сессию БД
        session: AsyncSession = data.get("session")
        
        if not session:
            logger.error("BotStatusMiddleware: сессия БД не найдена")
            return await handler(event, data)
        
        # Получаем тип события
        if isinstance(event, Message):
            user_id = event.from_user.id
            full_name = event.from_user.full_name or "Пользователь"
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            full_name = event.from_user.full_name or "Пользователь"
        else:
            # Другие типы событий пропускаем
            return await handler(event, data)
        
        # Проверяем статус бота
        try:
            bot_status = await crud.get_bot_status(session)
            
            # Если бот работает — пропускаем всех
            if not bot_status or bot_status.status == "running":
                return await handler(event, data)
            
            # Проверяем роль пользователя (админ всегда проходит)
            user = await crud.get_user_by_telegram_id(session, str(user_id))
            
            if user and user.role == "admin":
                logger.info(f"Админ {full_name} ({user_id}) получил доступ при статусе бота: {bot_status.status}")
                return await handler(event, data)
            
            # Блокируем обычного пользователя
            reason_text = ""
            if bot_status.status == "maintenance":
                reason_text = f"\n\nПричина: {bot_status.reason}" if bot_status.reason else ""
                message_text = f"""
⚠️ <b>Технические работы</b>

Уважаемый {full_name},

В данный момент проводятся технические работы.
Бот временно недоступен.

Мы скоро вернёмся!{reason_text}
"""
            elif bot_status.status == "stopped":
                reason_text = f"\n\nПричина: {bot_status.reason}" if bot_status.reason else ""
                message_text = f"""
⛔ <b>Бот остановлен</b>

Уважаемый {full_name},

Бот временно прекратил работу.
Попробуйте позже.{reason_text}
"""
            else:
                # Неизвестный статус — пропускаем
                return await handler(event, data)
            
            # Отправляем уведомление пользователю
            try:
                if isinstance(event, Message):
                    await event.answer(message_text, parse_mode="HTML")
                elif isinstance(event, CallbackQuery):
                    await event.answer(message_text, parse_mode="HTML", show_alert=True)
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
            
            logger.info(f"Пользователь {full_name} ({user_id}) заблокирован: бот {bot_status.status}")
            
            # Прерываем обработку
            return None
            
        except Exception as e:
            logger.error(f"BotStatusMiddleware: ошибка проверки статуса: {type(e).__name__}: {e}")
            # При ошибке пропускаем событие (fail-open)
            return await handler(event, data)
