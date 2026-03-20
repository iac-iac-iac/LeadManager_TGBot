"""
Модуль импорта лидов в Bitrix24
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from .client import Bitrix24Client, Bitrix24Error
from ..database.models import LeadStatus
from ..database import crud
from ..logger import get_logger

logger = get_logger(__name__)


class LeadImporter:
    """
    Сервис импорта лидов в Bitrix24
    """
    
    def __init__(self, bitrix24_client: Bitrix24Client):
        """
        Инициализация сервиса
        
        Args:
            bitrix24_client: Клиент Bitrix24 API
        """
        self.client = bitrix24_client
    
    async def import_lead(
        self,
        session: AsyncSession,
        lead_id: int,
        bitrix24_user_id: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Импорт лида в Bitrix24
        
        Args:
            session: Сессия БД
            lead_id: ID лида
            bitrix24_user_id: ID ответственного в Bitrix24
            
        Returns:
            (success: bool, error_message: Optional[str])
        """
        try:
            # Получаем лид из БД
            lead = await crud.get_lead_by_id(session, lead_id)
            
            if not lead:
                logger.error(f"Лид {lead_id} не найден в БД")
                return False, "Лид не найден"
            
            if lead.status not in [LeadStatus.UNIQUE, LeadStatus.ASSIGNED, LeadStatus.ERROR_IMPORT]:
                logger.warning(f"Лид {lead_id} имеет статус {lead.status}, импорт невозможен")
                return False, f"Недопустимый статус лида: {lead.status}"
            
            # Формируем название лида
            title = f"{lead.segment} - {lead.company_name or 'Без названия'}"

            # Логгируем для отладки
            logger.info(f"Импорт лида {lead_id}: title={title}, assigned_by_id={bitrix24_user_id}")

            # Маппинг названий услуг в ID значений Bitrix24
            SERVICE_TYPE_MAP = {
                "ГЦК": 101,
                "ГЦК без КЦ": 102,
                "Call-центр": 103,
                "Лид-код": 104,
                "Авито": 105,
                "Рекрутинг": 106,
            }
            
            # Получаем ID типа услуги
            service_type_id = SERVICE_TYPE_MAP.get(lead.service_type, 101)  # По умолчанию ГЦК
            
            # Импортируем в Bitrix24 с дополнительными полями
            # Для выпадающих списков передаём ID значения
            bitrix24_lead_id = await self.client.add_lead(
                title=title,
                company_title=lead.company_name,
                phone=lead.phone,
                mobile_phone=lead.mobile_phone,
                email=lead.work_email,
                address=lead.address,
                city=lead.city,
                website=lead.website,
                comment=lead.comment,
                assigned_by_id=bitrix24_user_id if bitrix24_user_id and bitrix24_user_id > 0 else None,
                source_id=lead.source or "TELEGRAM",
                service_type=service_type_id,  # Тип услуги (ID значения)
                phone_source=lead.phone_source,
            )

            logger.info(f"Bitrix24 вернул ID: {bitrix24_lead_id} (тип: {type(bitrix24_lead_id)})")

            if bitrix24_lead_id:
                # Обновляем статус лида
                await crud.mark_lead_as_imported(session, lead_id, bitrix24_lead_id)
                
                logger.info(f"Лид {lead_id} успешно импортирован в Bitrix24 как #{bitrix24_lead_id}")
                return True, None
            else:
                logger.error(f"Не удалось импортировать лид {lead_id}: Bitrix24 не вернул ID")
                return False, "Bitrix24 не вернул ID лида"
                
        except Bitrix24Error as e:
            error_msg = f"Ошибка Bitrix24 API при импорте лида {lead_id}: {e.message}"
            logger.error(error_msg)
            
            # Обновляем статус на ERROR_IMPORT
            await crud.update_lead_status(
                session,
                lead_id,
                LeadStatus.ERROR_IMPORT
            )
            
            return False, e.message
        
        except Exception as e:
            error_msg = f"Неожиданная ошибка при импорте лида {lead_id}: {e}"
            logger.error(error_msg)
            
            await crud.update_lead_status(
                session,
                lead_id,
                LeadStatus.ERROR_IMPORT
            )
            
            return False, str(e)
    
    async def import_leads_batch(
        self,
        session: AsyncSession,
        lead_ids: List[int],
        bitrix24_user_id: Optional[int] = None
    ) -> Dict[str, int]:
        """
        Пакетный импорт лидов в Bitrix24
        
        Args:
            session: Сессия БД
            lead_ids: Список ID лидов
            bitrix24_user_id: ID ответственного в Bitrix24
            
        Returns:
            Статистика: {"imported": N, "errors": N}
        """
        stats = {"imported": 0, "errors": 0}
        errors_list = []
        
        logger.info(f"Начат импорт {len(lead_ids)} лидов в Bitrix24")
        
        for i, lead_id in enumerate(lead_ids, 1):
            success, error = await self.import_lead(session, lead_id, bitrix24_user_id)
            
            if success:
                stats["imported"] += 1
            else:
                stats["errors"] += 1
                errors_list.append(f"Лид {lead_id}: {error}")
            
            # Логгируем прогресс
            if i % 10 == 0:
                logger.info(f"Импортировано {i}/{len(lead_ids)} лидов")
        
        # Создаем запись в логе
        await crud.create_log(
            session,
            event_type="LEAD_IMPORTED",
            related_lead_ids=lead_ids,
            description=f"Импортировано лидов: {stats['imported']}, Ошибки: {stats['errors']}"
        )
        
        if errors_list:
            logger.warning(f"Ошибки при импорте: {'; '.join(errors_list[:5])}")  # Показываем первые 5
        
        logger.info(f"Завершён импорт лидов. Успешно: {stats['imported']}, Ошибки: {stats['errors']}")
        
        return stats


async def import_assigned_leads(
    session: AsyncSession,
    bitrix24_client: Bitrix24Client,
    manager_telegram_id: str,
    bitrix24_user_id: Optional[int] = None
) -> Dict[str, int]:
    """
    Импорт назначенных менеджеру лидов
    
    Args:
        session: Сессия БД
        bitrix24_client: Клиент Bitrix24
        manager_telegram_id: Telegram ID менеджера
        bitrix24_user_id: ID менеджера в Bitrix24
        
    Returns:
        Статистика импорта
    """
    # Получаем все назначенные лиды менеджера
    from sqlalchemy import select
    from ..database.models import Lead
    
    query = select(Lead).where(
        Lead.manager_telegram_id == manager_telegram_id,
        Lead.status == LeadStatus.ASSIGNED
    )
    
    result = await session.execute(query)
    leads = result.scalars().all()
    
    if not leads:
        logger.info(f"Нет лидов для импорта у менеджера {manager_telegram_id}")
        return {"imported": 0, "errors": 0}
    
    lead_ids = [lead.id for lead in leads]
    
    importer = LeadImporter(bitrix24_client)
    return await importer.import_leads_batch(session, lead_ids, bitrix24_user_id)
