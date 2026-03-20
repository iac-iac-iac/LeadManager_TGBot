"""
Модуль очистки данных

Очистка логов и старых лидов
"""
from datetime import datetime, timedelta, timezone
from typing import Dict

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import Log, Lead, LeadStatus
from ..database import crud
from ..logger import get_logger

logger = get_logger(__name__)


class CleanupService:
    """Сервис очистки данных"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def cleanup_logs(
        self,
        older_than_days: int = 30
    ) -> int:
        """
        Очистка старых логов

        Args:
            older_than_days: Удалять логи старше N дней

        Returns:
            Количество удалённых записей
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        result = await self.session.execute(
            delete(Log).where(Log.timestamp < cutoff_date)
        )

        deleted_count = result.rowcount

        # Flush для применения изменений
        await self.session.flush()

        logger.info(f"Очищено {deleted_count} записей логов старше {older_than_days} дней")

        return deleted_count
    
    async def cleanup_duplicate_leads(
        self,
        older_than_days: int = 90
    ) -> int:
        """
        Очистка лидов со статусом DUPLICATE

        Args:
            older_than_days: Удалять лиды старше N дней

        Returns:
            Количество удалённых лидов
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        logger.info(f"Очистка дублей: cutoff_date={cutoff_date}, older_than_days={older_than_days}")

        result = await self.session.execute(
            delete(Lead).where(
                Lead.status == LeadStatus.DUPLICATE,
                Lead.created_at < cutoff_date
            )
        )

        deleted_count = result.rowcount

        logger.info(f"DELETE запрос выполнен: rowcount={deleted_count}")

        # Flush для применения изменений
        await self.session.flush()

        logger.info(f"Flush выполнен. Удалено лидов-дублей: {deleted_count}")

        return deleted_count
    
    async def cleanup_imported_leads(
        self,
        older_than_days: int = 180
    ) -> int:
        """
        Очистка импортированных лидов

        Args:
            older_than_days: Удалять лиды старше N дней

        Returns:
            Количество удалённых лидов
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        result = await self.session.execute(
            delete(Lead).where(
                Lead.status == LeadStatus.IMPORTED,
                Lead.imported_at < cutoff_date
            )
        )

        deleted_count = result.rowcount

        # Flush для применения изменений
        await self.session.flush()

        logger.info(f"Очищено {deleted_count} импортированных лидов старше {older_than_days} дней")

        return deleted_count
    
    async def run_full_cleanup(
        self,
        logs_days: int = 30,
        duplicate_days: int = 90,
        imported_days: int = 180
    ) -> Dict[str, int]:
        """
        Полная очистка всех данных
        
        Args:
            logs_days: Логи старше N дней
            duplicate_days: Дубли старше N дней
            imported_days: Импортированные старше N дней
            
        Returns:
            Статистика: {"logs": N, "duplicates": N, "imported": N}
        """
        logger.info("Запуск полной очистки данных...")
        
        stats = {
            'logs': 0,
            'duplicates': 0,
            'imported': 0
        }
        
        try:
            # Очищаем логи
            stats['logs'] = await self.cleanup_logs(logs_days)
            
            # Очищаем дубли
            stats['duplicates'] = await self.cleanup_duplicate_leads(duplicate_days)
            
            # Очищаем импортированные
            stats['imported'] = await self.cleanup_imported_leads(imported_days)
            
            # Создаём запись в логе
            await crud.create_log(
                self.session,
                event_type="CLEANUP",
                description=f"Полная очистка: логи={stats['logs']}, дубли={stats['duplicates']}, импортированные={stats['imported']}"
            )
            
            logger.info(f"Полная очистка завершена: {stats}")
            
        except Exception as e:
            logger.error(f"Ошибка при очистке: {e}")
            raise
        
        return stats


async def run_cleanup(
    session: AsyncSession,
    cleanup_type: str = 'all',
    logs_days: int = 30,
    duplicate_days: int = 90,
    imported_days: int = 180
) -> Dict[str, int]:
    """
    Запуск очистки
    
    Args:
        session: Сессия БД
        cleanup_type: 'logs', 'duplicates', 'imported', 'all'
        logs_days: Логи старше N дней
        duplicate_days: Дубли старше N дней
        imported_days: Импортированные старше N дней
        
    Returns:
        Статистика очистки
    """
    service = CleanupService(session)
    
    if cleanup_type == 'logs':
        count = await service.cleanup_logs(logs_days)
        return {'logs': count}
    elif cleanup_type == 'duplicates':
        count = await service.cleanup_duplicate_leads(duplicate_days)
        return {'duplicates': count}
    elif cleanup_type == 'imported':
        count = await service.cleanup_imported_leads(imported_days)
        return {'imported': count}
    else:  # 'all'
        return await service.run_full_cleanup(logs_days, duplicate_days, imported_days)
