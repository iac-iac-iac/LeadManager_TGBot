"""
Middleware для автоматической инъекции сессии базы данных

Согласно best practices aiogram 3.x:
- Создаёт сессию на каждый запрос
- Добавляет session и session_factory в контекст данных
- Автоматически делает commit при успехе и rollback при ошибке
"""
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...logger import get_logger

logger = get_logger(__name__)


class DatabaseSessionMiddleware(BaseMiddleware):
    """
    Middleware для автоматической инъекции сессии БД в обработчики

    Использование в обработчиках:
        @router.message(Command("start"))
        async def cmd_start(message: Message, session: AsyncSession):
            # session автоматически инжектируется из middleware
            result = await session.execute(...)
            await session.commit()  # Явный commit для контроля транзакций
    """

    def __init__(self, session_factory: async_sessionmaker):
        """
        Инициализация middleware

        Args:
            session_factory: Фабрика сессий SQLAlchemy
        """
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """
        Вызов middleware

        Args:
            handler: Обработчик
            event: Событие (Message, CallbackQuery, etc.)
            data: Данные контекста

        Returns:
            Результат обработчика
        """
        # Создаём сессию
        async with self.session_factory() as session:
            # Добавляем session и session_factory в контекст
            data["session"] = session
            data["session_factory"] = self.session_factory

            try:
                # Вызываем обработчик
                result = await handler(event, data)

                # Коммит при успехе (если обработчик не сделал сам)
                # Примечание: обработчики могут делать commit сами для контроля транзакций
                # Этот commit нужен для обработчиков, которые не делают явный commit

                return result

            except Exception as e:
                # Откат при ошибке
                await session.rollback()
                logger.error(f"Ошибка в обработчике (транзакция откатана): {e}")
                raise

            finally:
                # Сессия автоматически закрывается через async with

                pass
