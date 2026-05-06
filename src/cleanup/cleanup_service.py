"""
Модуль очистки данных

Очистка логов и старых лидов
"""
from datetime import datetime, timedelta, timezone
from typing import Dict

from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import Log, Lead, LeadStatus
from ..database import crud
from ..logger import get_logger

logger = get_logger(__name__)


def normalize_cleanup_type(raw: str) -> str:
    """
    Приводит тип очистки из callback (`cleanup_logs`, `logs`) к виду, который понимает run_cleanup.
    """
    s = (raw or "").strip()
    if s.startswith("cleanup_"):
        s = s[len("cleanup_"):]
    if s not in ("logs", "duplicates", "imported", "all"):
        raise ValueError(f"Неизвестный тип очистки: {raw!r}")
    return s


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
                func.coalesce(Lead.imported_at, Lead.created_at) < cutoff_date,
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

    async def cleanup_duplicate_and_imported_forced(
        self,
        older_than_days: int,
    ) -> Dict[str, int]:
        """
        Принудительная очистка: DUPLICATE и IMPORTED за один проход по общему порогу «старше N дней».

        DUPLICATE — по ``created_at``. IMPORTED — по ``imported_at``, иначе по ``created_at``.
        """
        if older_than_days < 1:
            raise ValueError("older_than_days должен быть >= 1")

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        logger.info(
            "Принудительная очистка DUPLICATE+IMPORTED: "
            f"older_than_days={older_than_days}, cutoff={cutoff_date}"
        )

        dup_result = await self.session.execute(
            delete(Lead).where(
                Lead.status == LeadStatus.DUPLICATE,
                Lead.created_at < cutoff_date,
            )
        )
        duplicates_deleted = dup_result.rowcount or 0

        imp_result = await self.session.execute(
            delete(Lead).where(
                Lead.status == LeadStatus.IMPORTED,
                func.coalesce(Lead.imported_at, Lead.created_at) < cutoff_date,
            )
        )
        imported_deleted = imp_result.rowcount or 0

        await self.session.flush()

        await crud.create_log(
            self.session,
            event_type="CLEANUP",
            description=(
                f"Принудительно DUPLICATE+IMPORTED: порог {older_than_days} дн.; "
                f"удалено dup={duplicates_deleted}, imp={imported_deleted}"
            ),
        )

        logger.info(
            f"Принудительная очистка завершена: dup={duplicates_deleted}, imp={imported_deleted}"
        )

        return {"duplicates": duplicates_deleted, "imported": imported_deleted}


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

    if cleanup_type == "logs":
        count = await service.cleanup_logs(logs_days)
        return {"logs": count}
    if cleanup_type == "duplicates":
        count = await service.cleanup_duplicate_leads(duplicate_days)
        return {"duplicates": count}
    if cleanup_type == "imported":
        count = await service.cleanup_imported_leads(imported_days)
        return {"imported": count}
    if cleanup_type == "all":
        return await service.run_full_cleanup(logs_days, duplicate_days, imported_days)

    raise ValueError(f"Неизвестный тип очистки: {cleanup_type!r}")


async def run_forced_duplicate_import_cleanup(
    session: AsyncSession,
    older_than_days: int,
) -> Dict[str, int]:
    """Принудительное удаление DUPLICATE и IMPORTED по общему порогу возраста (дней)."""
    service = CleanupService(session)
    return await service.cleanup_duplicate_and_imported_forced(older_than_days)
