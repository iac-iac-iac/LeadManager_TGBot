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
        reason: str | None = None,
        timeout: int = 30  # Таймаут рассылки (сек)
    ) -> dict:
        """
        Рассылка уведомлений об изменении статуса бота

        Args:
            session: Сессия БД
            new_status: Новый статус (running, stopped, maintenance)
            reason: Причина (опционально)
            timeout: Таймаут рассылки в секундах

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

        # Запускаем рассылку с таймаутом
        stats = {"sent": 0, "failed": 0}

        async def send_with_semaphore(user: User):
            """Отправка с ограничением параллелизма"""
            async with self._semaphore:
                try:
                    success = await asyncio.wait_for(
                        self._send_to_user(user, message_text),
                        timeout=5.0  # Таймаут на одного пользователя
                    )
                    if success:
                        stats["sent"] += 1
                    else:
                        stats["failed"] += 1
                except asyncio.TimeoutError:
                    logger.warning(f"Таймаут отправки пользователю {user.telegram_id}")
                    stats["failed"] += 1
                except Exception as e:
                    logger.warning(f"Ошибка отправки пользователю {user.telegram_id}: {type(e).__name__}: {e}")
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
        Рассылка уведомлений админам.

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

    async def notify_manager_leads_queued(
        self,
        manager_telegram_id: str,
        admin_name: str,
        leads_count: int,
        segment: str,
        city: str | None
    ) -> bool:
        """
        Уведомление менеджера о постановке лидов в очередь на импорт.

        Returns:
            True если успешно отправлено.
        """
        city_text = city or "Все города"
        text = (
            f"📦 <b>Лиды поставлены в очередь на импорт!</b>\n\n"
            f"👨‍💼 Администратор: {admin_name}\n"
            f"📊 Количество: {leads_count}\n"
            f"📁 Сегмент: {segment}\n"
            f"🏙 Город: {city_text}\n\n"
            f"⏳ Вы получите уведомление когда импорт завершится."
        )
        try:
            await self.bot.send_message(
                chat_id=manager_telegram_id,
                text=text,
                parse_mode="HTML"
            )
            logger.info(
                f"Менеджер {manager_telegram_id} уведомлён о постановке "
                f"в очередь {leads_count} лидов"
            )
            return True
        except Exception as e:
            logger.error(f"Не удалось уведомить менеджера {manager_telegram_id}: {e}")
            return False

    async def notify_manager_leads_imported(
        self,
        manager_telegram_id: str,
        leads_count: int,
        imported_count: int,
        error_count: int = 0
    ) -> bool:
        """
        Уведомление менеджера о завершении импорта лидов.

        Returns:
            True если успешно отправлено.
        """
        text = (
            f"✅ <b>Импорт лидов завершён!</b>\n\n"
            f"📊 Всего лидов: {leads_count}\n"
            f"✅ Импортировано: {imported_count}\n"
        )
        if error_count:
            text += f"❌ Ошибок: {error_count}\n"

        try:
            await self.bot.send_message(
                chat_id=manager_telegram_id,
                text=text,
                parse_mode="HTML"
            )
            return True
        except Exception as e:
            logger.error(f"Не удалось уведомить менеджера {manager_telegram_id}: {e}")
            return False
