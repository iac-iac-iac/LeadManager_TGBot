"""
Сервис уведомлений пользователей

Рассылка сообщений при изменении статуса бота
"""
import asyncio
from typing import List
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...database.models import User
from ...database import crud
from ...logger import get_logger

logger = get_logger(__name__)


class NotificationService:
    """
    Сервис массовых уведомлений пользователей
    
    Особенности:
    - Ограничение параллелизма (semaphore)
    - Обработка ошибок Telegram API
    - Логирование прогресса
    """
    
    # Ограничение параллелизма (чтобы не получить бан от Telegram)
    MAX_PARALLEL = 10
    
    # Задержка между отправками (сек)
    SEND_DELAY = 0.1

    def __init__(self, bot: Bot):
        """
        Инициализация сервиса
        
        Args:
            bot: Экземпляр бота для отправки сообщений
        """
        self.bot = bot
        self._semaphore = asyncio.Semaphore(self.MAX_PARALLEL)

    async def notify_bot_status_change(
        self,
        session: AsyncSession,
        new_status: str,
        reason: str | None = None
    ) -> dict:
        """
        Рассылка уведомлений об изменении статуса бота
        
        Args:
            session: Сессия БД
            new_status: Новый статус (running, stopped, maintenance)
            reason: Причина (опционально)
            
        Returns:
            Статистика рассылки: {sent: int, failed: int}
        """
        # Получаем всех активных пользователей
        users = await self._get_active_users(session)
        
        if not users:
            logger.info("Нет активных пользователей для рассылки")
            return {"sent": 0, "failed": 0}
        
        # Формируем сообщение
        message_text = self._build_notification_message(new_status, reason)
        
        logger.info(f"Начало рассылки: {len(users)} пользователей, статус: {new_status}")
        
        # Запускаем рассылку
        stats = {"sent": 0, "failed": 0}
        
        async def send_with_semaphore(user: User):
            """Отправка с ограничением параллелизма"""
            async with self._semaphore:
                success = await self._send_to_user(user, message_text)
                if success:
                    stats["sent"] += 1
                else:
                    stats["failed"] += 1
                
                # Небольшая задержка для естественности
                await asyncio.sleep(self.SEND_DELAY)
        
        # Запускаем параллельную рассылку
        tasks = [send_with_semaphore(user) for user in users]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info(f"Рассылка завершена: отправлено {stats['sent']}, ошибок {stats['failed']}")
        
        return stats

    async def _get_active_users(self, session: AsyncSession) -> List[User]:
        """
        Получение списка активных пользователей
        
        Args:
            session: Сессия БД
            
        Returns:
            Список активных пользователей
        """
        result = await session.execute(
            select(User)
            .where(User.status == "ACTIVE")
            .order_by(User.telegram_id)
        )
        return result.scalars().all()

    def _build_notification_message(self, status: str, reason: str | None = None) -> str:
        """
        Формирование текста уведомления
        
        Args:
            status: Статус бота
            reason: Причина
            
        Returns:
            Текст сообщения
        """
        if status == "running":
            message = """
🎉 <b>Бот снова работает!</b>

Уважаемые пользователи,

Технические работы завершены.
Бот доступен в обычном режиме.

Спасибо за ожидание!
"""
        elif status == "maintenance":
            reason_text = f"\n\nПричина: {reason}" if reason else ""
            message = f"""
⚠️ <b>Технические работы</b>

Уважаемые пользователи,

Бот временно недоступен из-за технических работ.

Мы скоро вернёмся!{reason_text}
"""
        elif status == "stopped":
            reason_text = f"\n\nПричина: {reason}" if reason else ""
            message = f"""
⛔ <b>Бот остановлен</b>

Уважаемые пользователи,

Бот временно прекратил работу.

Попробуйте позже.{reason_text}
"""
        else:
            message = "🔄 Статус бота изменён"
        
        return message

    async def _send_to_user(self, user: User, message: str) -> bool:
        """
        Отправка сообщения одному пользователю
        
        Args:
            user: Пользователь для отправки
            message: Текст сообщения
            
        Returns:
            True если успешно, False если ошибка
        """
        try:
            await self.bot.send_message(
                chat_id=user.telegram_id,
                text=message,
                parse_mode="HTML"
            )
            logger.debug(f"Уведомление отправлено пользователю {user.telegram_id}")
            return True
            
        except Exception as e:
            # Логируем ошибку, но не прерываем рассылку
            error_type = type(e).__name__
            
            # Критические ошибки (пользователь заблокировал бота)
            if "bot was blocked" in str(e):
                logger.warning(f"Пользователь {user.telegram_id} заблокировал бота")
            elif "chat not found" in str(e).lower():
                logger.warning(f"Чат {user.telegram_id} не найден")
            else:
                logger.error(f"Ошибка отправки пользователю {user.telegram_id}: {error_type}: {e}")
            
            return False

    async def notify_admins(
        self,
        session: AsyncSession,
        message: str,
        admin_ids: List[str]
    ) -> dict:
        """
        Рассылка уведомлений админам
        
        Args:
            session: Сессия БД
            message: Текст сообщения
            admin_ids: Список Telegram ID админов
            
        Returns:
            Статистика: {sent: int, failed: int}
        """
        stats = {"sent": 0, "failed": 0}
        
        for admin_id in admin_ids:
            try:
                await self.bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode="HTML"
                )
                stats["sent"] += 1
                logger.info(f"Уведомление отправлено админу {admin_id}")
            except Exception as e:
                stats["failed"] += 1
                logger.error(f"Ошибка отправки админу {admin_id}: {type(e).__name__}: {e}")
        
        return stats
