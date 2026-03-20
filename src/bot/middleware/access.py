"""
Middleware для проверки доступа и прав пользователя
"""
from typing import Callable, Dict, Any, Awaitable, Optional

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.handlers import CallbackQueryHandler

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from ...database import crud
from ...database.models import User, UserRole, UserStatus
from ...logger import get_logger

logger = get_logger(__name__)


class AccessMiddleware(BaseMiddleware):
    """
    Middleware для проверки доступа пользователя
    
    Проверяет:
    - Зарегистрирован ли пользователь
    - Статус пользователя (ACTIVE, PENDING, REJECTED)
    - Роль (admin, manager)
    """
    
    def __init__(self, session_factory, admin_ids: list[int]):
        """
        Инициализация middleware
        
        Args:
            session_factory: Фабрика сессий БД
            admin_ids: Список Telegram ID админов
        """
        self.session_factory = session_factory
        self.admin_ids = admin_ids
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Вызов middleware
        
        Args:
            handler: Обработчик
            event: Событие (Message или CallbackQuery)
            data: Данные контекста
            
        Returns:
            Результат обработчика или None
        """
        # Получаем пользователя из события
        if isinstance(event, Message):
            telegram_user = event.from_user
        elif isinstance(event, CallbackQuery):
            telegram_user = event.from_user
        else:
            return await handler(event, data)
        
        telegram_id = str(telegram_user.id)
        username = telegram_user.username
        full_name = telegram_user.full_name or ""
        
        # Получаем сессию
        async with self.session_factory() as session:
            # Проверяем пользователя в БД
            user = await crud.get_user_by_telegram_id(session, telegram_id)

            if not user:
                # Пользователь не зарегистрирован
                data["user"] = None
                data["is_admin"] = False
                data["is_registered"] = False
                logger.debug(f"Пользователь {telegram_id} не найден в БД")
            else:
                data["user"] = user
                data["is_admin"] = user.role == UserRole.ADMIN
                # Проверяем статус - ACTIVE означает зарегистрирован
                data["is_registered"] = user.status == UserStatus.ACTIVE
                logger.debug(f"Пользователь {telegram_id}: status={user.status}, is_registered={data['is_registered']}")

                # Проверяем, не изменилось ли имя (обновляем через CRUD функцию)
                if user.full_name != full_name and full_name:
                    await crud.update_user_name(session, telegram_id, full_name[:200])

            # Проверяем админов по ID из конфига (только для superadmin доступа)
            if int(telegram_id) in self.admin_ids:
                # Если пользователь ещё не админ в БД, логируем это
                if not data["is_admin"]:
                    logger.warning(f"Admin ID из конфига не совпадает с ролью в БД: {telegram_id}")
                data["is_admin"] = True

        # Продолжаем обработку
        return await handler(event, data)


class AdminOnlyMiddleware(BaseMiddleware):
    """
    Middleware для ограничения доступа только для админов
    
    Блокирует выполнение обработчика, если пользователь не админ
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Вызов middleware
        
        Args:
            handler: Обработчик
            event: Событие
            data: Данные контекста
            
        Returns:
            Результат обработчика или None
        """
        is_admin = data.get("is_admin", False)
        
        if not is_admin:
            # Доступ запрещён
            if isinstance(event, Message):
                await event.answer("🚫 Доступ запрещён. Эта команда доступна только администратору.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Доступ запрещён.", show_alert=True)
            return None
        
        return await handler(event, data)


class RegisteredOnlyMiddleware(BaseMiddleware):
    """
    Middleware для ограничения доступа только для зарегистрированных пользователей
    
    Блокирует выполнение обработчика, если пользователь не активен
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Вызов middleware
        
        Args:
            handler: Обработчик
            event: Событие
            data: Данные контекста
            
        Returns:
            Результат обработчика или None
        """
        is_registered = data.get("is_registered", False)

        if not is_registered:
            # Пользователь не зарегистрирован
            if isinstance(event, Message):
                logger.warning(f"Блокировка сообщения от незарегистрированного пользователя {event.from_user.id}")
                await event.answer("🚫 Вы ещё не зарегистрированы. Нажмите /start для регистрации.")
            elif isinstance(event, CallbackQuery):
                logger.warning(f"Блокировка callback от незарегистрированного пользователя {event.from_user.id}")
                await event.answer("🚫 Вы ещё не зарегистрированы.", show_alert=True)
            return None

        logger.debug(f"Пользователь {event.from_user.id} прошёл проверку is_registered={is_registered}")
        return await handler(event, data)
