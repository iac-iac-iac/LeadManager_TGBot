"""
LeadAssignmentService — единый сервис выдачи лидов.

Устраняет дублирование бизнес-логики между:
- handlers/manager_leads.py (handle_leads_confirm)
- handlers/admin_load_leads.py (process_load_leads, process_bitrix_load)
"""
from dataclasses import dataclass, field
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

from ...database import crud
from ...database.models import Lead
from ...logger import get_logger

logger = get_logger(__name__)


@dataclass
class AssignmentResult:
    """Результат назначения и импорта лидов"""
    assigned_count: int = 0
    imported_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    assigned_lead_ids: List[int] = field(default_factory=list)
    message: str = ""

    @property
    def success(self) -> bool:
        return self.assigned_count > 0


class LeadAssignmentService:
    """
    Сервис выдачи лидов менеджерам.

    Объединяет:
    1. Подбор доступных лидов
    2. Атомарное назначение (UPDATE WHERE status=UNIQUE)
    3. Проверку rowcount (защита от гонок)
    4. Импорт в Bitrix24 (sync или через очередь)
    """

    def __init__(self, bitrix24_client=None):
        self.bitrix24_client = bitrix24_client

    async def get_leads_for_segment(
        self,
        session: AsyncSession,
        segment: str,
        city: Optional[str],
        count: int,
        is_other: bool = False,
        other_type: Optional[str] = None
    ) -> List[Lead]:
        """
        Подбор лидов по сегменту/типу.

        Args:
            segment: Название сегмента (или 'Прочее')
            city: Город (None = все города)
            count: Нужное количество
            is_other: Флаг категории 'Прочее'
            other_type: 'regular' или 'plusoviki' (только если is_other=True)
        """
        if is_other:
            from .other_category_service import OtherCategoryService
            service = OtherCategoryService()
            leads = await service.get_leads_by_type(
                session, other_type or "regular", limit=count
            )
        else:
            leads = await crud.get_available_leads(
                session, segment, city, limit=count
            )
        return leads

    async def assign(
        self,
        session: AsyncSession,
        lead_ids: List[int],
        manager_telegram_id: str,
        loaded_by_admin: bool = False
    ) -> int:
        """
        Атомарное назначение лидов с защитой от гонок.

        Returns:
            Фактическое количество назначенных лидов.
        """
        if not lead_ids:
            return 0
        count = await crud.assign_leads_to_manager(
            session, lead_ids, manager_telegram_id, loaded_by_admin
        )
        if count < len(lead_ids):
            logger.warning(
                f"Гонка данных: запрошено {len(lead_ids)}, "
                f"назначено {count} лидов менеджеру {manager_telegram_id}"
            )
        return count

    async def assign_and_import(
        self,
        session: AsyncSession,
        manager_telegram_id: str,
        bitrix24_user_id: Optional[str],
        segment: str,
        city: Optional[str],
        count: int,
        *,
        loaded_by_admin: bool = False,
        via_queue: bool = False,
        is_other: bool = False,
        other_type: Optional[str] = None
    ) -> AssignmentResult:
        """
        Полный цикл: подбор → назначение → импорт в Bitrix24.

        Args:
            via_queue: True — ставим в очередь, False — импортируем синхронно
        """
        result = AssignmentResult()

        # 1. Подбираем лиды
        leads = await self.get_leads_for_segment(
            session, segment, city, count,
            is_other=is_other, other_type=other_type
        )

        if not leads:
            result.message = "Лиды не найдены"
            return result

        lead_ids = [lead.id for lead in leads]

        # 2. Назначаем
        assigned = await self.assign(
            session, lead_ids, manager_telegram_id, loaded_by_admin
        )
        result.assigned_count = assigned
        result.assigned_lead_ids = lead_ids[:assigned]

        if assigned == 0:
            result.message = "Все лиды уже разобраны"
            return result

        # 3. Импорт
        if via_queue:
            from ...bitrix24.import_queue import get_import_queue
            import_queue = get_import_queue()
            if import_queue and self.bitrix24_client:
                await import_queue.add_task(
                    session=session,
                    manager_telegram_id=manager_telegram_id,
                    bitrix24_user_id=bitrix24_user_id,
                    lead_ids=result.assigned_lead_ids,
                    bitrix24_client=self.bitrix24_client
                )
            result.message = f"Поставлено в очередь: {assigned} лидов"
        elif self.bitrix24_client and bitrix24_user_id:
            imported, errors = await self._import_sync(
                session, result.assigned_lead_ids, bitrix24_user_id
            )
            result.imported_count = imported
            result.error_count = errors
            result.message = (
                f"Назначено: {assigned}, импортировано: {imported}"
                + (f", ошибок: {errors}" if errors else "")
            )
        else:
            result.message = f"Назначено: {assigned} лидов (без импорта в Bitrix24)"

        return result

    async def _import_sync(
        self,
        session: AsyncSession,
        lead_ids: List[int],
        bitrix24_user_id: str
    ):
        """Синхронный импорт в Bitrix24 (один за другим)"""
        imported = 0
        errors = 0

        for lead_id in lead_ids:
            lead = await crud.get_lead_by_id(session, lead_id)
            if not lead:
                errors += 1
                continue

            try:
                bitrix_id = await self.bitrix24_client.add_lead(
                    lead=lead,
                    responsible_id=bitrix24_user_id
                )
                await crud.mark_lead_as_imported(session, lead_id, bitrix_id)
                imported += 1
            except Exception as e:
                logger.error(f"Ошибка импорта лида {lead_id}: {e}")
                errors += 1

        return imported, errors
