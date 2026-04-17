"""
CRUD для работы с логами и аналитикой
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import select, delete, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Log, Lead, LeadStatus
from ...logger import get_logger

logger = get_logger(__name__)


async def create_log(
    session: AsyncSession,
    event_type: str,
    user_telegram_id: Optional[str] = None,
    related_lead_ids: Optional[List[int]] = None,
    related_segment: Optional[str] = None,
    related_city: Optional[str] = None,
    description: Optional[str] = None
) -> Log:
    """
    Создание записи лога.

    Raises:
        ValueError: Если related_lead_ids содержит некорректные данные
    """
    validated_lead_ids = None
    if related_lead_ids is not None:
        if not isinstance(related_lead_ids, list):
            raise ValueError(
                f"related_lead_ids должен быть списком, получен {type(related_lead_ids).__name__}"
            )
        for item in related_lead_ids:
            if not isinstance(item, int):
                raise ValueError(
                    f"Все ID лидов должны быть целыми числами, получен {type(item).__name__}: {item}"
                )
            if item <= 0:
                raise ValueError(f"ID лида должен быть положительным числом, получен {item}")
        validated_lead_ids = related_lead_ids

    validated_segment = None
    if related_segment is not None:
        if not isinstance(related_segment, str):
            raise ValueError("related_segment должен быть строкой")
        if len(related_segment) > 500:
            raise ValueError("related_segment слишком длинный (максимум 500 символов)")
        validated_segment = related_segment

    validated_city = None
    if related_city is not None:
        if not isinstance(related_city, str):
            raise ValueError("related_city должен быть строкой")
        if len(related_city) > 500:
            raise ValueError("related_city слишком длинный (максимум 500 символов)")
        validated_city = related_city

    validated_description = None
    if description is not None:
        if not isinstance(description, str):
            raise ValueError("description должен быть строкой")
        if len(description) > 5000:
            raise ValueError("description слишком длинный (максимум 5000 символов)")
        validated_description = description

    log = Log(
        event_type=event_type,
        user_telegram_id=user_telegram_id,
        related_lead_ids=json.dumps(validated_lead_ids) if validated_lead_ids else None,
        related_segment=validated_segment,
        related_city=validated_city,
        description=validated_description
    )
    session.add(log)
    await session.flush()
    return log


async def get_logs(
    session: AsyncSession,
    event_type: Optional[str] = None,
    user_telegram_id: Optional[str] = None,
    limit: int = 100
) -> List[Log]:
    """Получение логов"""
    query = select(Log)

    if event_type:
        query = query.where(Log.event_type == event_type)
    if user_telegram_id:
        query = query.where(Log.user_telegram_id == user_telegram_id)

    query = query.order_by(Log.timestamp.desc()).limit(limit)
    result = await session.execute(query)
    return result.scalars().all()


async def get_logs_by_description(
    session: AsyncSession,
    description_contains: str,
    limit: int = 10
) -> List[Log]:
    """Получение логов по содержащемуся тексту в описании"""
    query = select(Log).where(
        Log.description.contains(description_contains)
    ).limit(limit)

    result = await session.execute(query)
    return result.scalars().all()


async def delete_old_logs(
    session: AsyncSession,
    older_than_days: int
) -> int:
    """
    Удаление старых логов.

    Returns:
        Количество удаленных записей
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    result = await session.execute(
        delete(Log).where(Log.timestamp < cutoff_date)
    )
    return result.rowcount


# =============================================================================
# Analytics
# =============================================================================

async def get_lead_stats_by_period(
    session: AsyncSession,
    start_date: datetime,
    end_date: datetime,
    segment: Optional[str] = None
) -> Dict[str, Any]:
    """
    Получение статистики лидов за период.

    Returns:
        Dict с метриками: loaded, duplicates, unique, assigned, imported, errors
    """
    query = select(
        Lead.status,
        func.count(Lead.id)
    ).where(
        Lead.created_at >= start_date,
        Lead.created_at <= end_date
    )

    if segment:
        query = query.where(Lead.segment == segment)

    query = query.group_by(Lead.status)

    result = await session.execute(query)
    stats = {
        "loaded": 0,
        "duplicates": 0,
        "unique": 0,
        "assigned": 0,
        "imported": 0,
        "errors": 0
    }

    for row in result.all():
        status, count = row
        if status == LeadStatus.NEW:
            stats["loaded"] = count
        elif status == LeadStatus.DUPLICATE:
            stats["duplicates"] = count
        elif status == LeadStatus.UNIQUE:
            stats["unique"] = count
        elif status == LeadStatus.ASSIGNED:
            stats["assigned"] = count
        elif status == LeadStatus.IMPORTED:
            stats["imported"] = count
        elif status == LeadStatus.ERROR_IMPORT:
            stats["errors"] = count

    return stats


async def get_manager_stats(
    session: AsyncSession,
    manager_telegram_id: str,
    start_date: datetime,
    end_date: datetime
) -> Dict[str, int]:
    """Получение статистики менеджера за период"""
    result = await session.execute(
        select(
            func.count(Lead.id).label("total"),
            func.sum(
                case(
                    (Lead.status == LeadStatus.IMPORTED, 1),
                    else_=0
                )
            ).label("imported")
        )
        .where(
            Lead.manager_telegram_id == manager_telegram_id,
            Lead.assigned_at >= start_date,
            Lead.assigned_at <= end_date
        )
    )

    row = result.one()
    return {
        "total": row.total or 0,
        "imported": row.imported or 0
    }
