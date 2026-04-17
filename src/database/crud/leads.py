"""
CRUD для работы с лидами
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import select, update, delete, func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Lead, LeadStatus, SegmentLock, City
from ...logger import get_logger

logger = get_logger(__name__)


async def create_lead(
    session: AsyncSession,
    phone: Optional[str] = None,
    company_name: Optional[str] = None,
    address: Optional[str] = None,
    city: Optional[str] = None,
    segment: Optional[str] = None,
    source: str = "Холодный звонок",
    mobile_phone: Optional[str] = None,
    work_email: Optional[str] = None,
    website: Optional[str] = None,
    contact_telegram: Optional[str] = None,
    comment: Optional[str] = None,
    manager_telegram_id: Optional[str] = None,
    **kwargs
) -> Lead:
    """Создание лида"""
    lead = Lead(
        phone=phone,
        company_name=company_name,
        address=address,
        city=city,
        segment=segment,
        source=source,
        mobile_phone=mobile_phone,
        work_email=work_email,
        website=website,
        contact_telegram=contact_telegram,
        comment=comment,
        manager_telegram_id=manager_telegram_id,
        **kwargs
    )
    session.add(lead)
    await session.flush()
    return lead


async def create_leads_batch(
    session: AsyncSession,
    leads_data: List[Dict[str, Any]]
) -> List[Lead]:
    """Массовое создание лидов"""
    leads = [Lead(**data) for data in leads_data]
    session.add_all(leads)
    await session.flush()
    return leads


async def get_lead_by_id(session: AsyncSession, lead_id: int) -> Optional[Lead]:
    """Получение лида по ID"""
    result = await session.execute(select(Lead).where(Lead.id == lead_id))
    return result.scalar_one_or_none()


async def get_leads_by_status(
    session: AsyncSession,
    status: LeadStatus,
    limit: Optional[int] = None
) -> List[Lead]:
    """Получение лидов по статусу"""
    query = select(Lead).where(Lead.status == status)
    if limit:
        query = query.limit(limit)
    result = await session.execute(query)
    return result.scalars().all()


async def get_available_leads(
    session: AsyncSession,
    segment: str,
    city: Optional[str] = None,
    limit: int = 200,
    exclude_telegram_id: Optional[str] = None
) -> List[Lead]:
    """
    Получение доступных лидов для выдачи.

    Учитывает статус UNIQUE, FIFO порядок.
    """
    query = select(Lead).where(
        Lead.status == LeadStatus.UNIQUE,
        Lead.segment == segment
    )

    if city:
        query = query.where(Lead.city == city)

    if exclude_telegram_id:
        query = query.where(
            or_(
                Lead.manager_telegram_id.is_(None),
                Lead.manager_telegram_id == exclude_telegram_id
            )
        )

    query = query.order_by(Lead.created_at.asc()).limit(limit)
    result = await session.execute(query)
    return result.scalars().all()


async def count_available_leads(
    session: AsyncSession,
    segment: str,
    city: Optional[str] = None
) -> int:
    """Подсчет количества доступных лидов"""
    query = select(func.count(Lead.id)).where(
        Lead.status == LeadStatus.UNIQUE,
        Lead.segment == segment
    )

    if city:
        query = query.where(Lead.city == city)

    frozen_subquery = select(SegmentLock.segment).where(SegmentLock.is_frozen == True)
    query = query.where(Lead.segment.notin_(frozen_subquery))

    result = await session.execute(query)
    return result.scalar() or 0


async def count_other_leads(
    session: AsyncSession,
    other_type: str,
    segment: str = None,
    tail_threshold: int = 10,
    plusoviki_threshold: int = 3
) -> int:
    """Подсчёт лидов в категории 'Прочее' (города < tail_threshold лидов внутри сегмента)"""
    all_cities_result = await session.execute(select(City))
    city_utc = {c.name: c.utc_offset for c in all_cities_result.scalars().all()}

    query = select(
        Lead.segment, Lead.city, func.count(Lead.id).label('cnt')
    ).where(Lead.status == LeadStatus.UNIQUE)
    if segment:
        query = query.where(Lead.segment == segment)
    query = query.group_by(Lead.segment, Lead.city)

    result = await session.execute(query)
    total = 0

    segment_city_counts: Dict[str, Dict[str, int]] = {}
    segment_total_counts: Dict[str, int] = {}

    for seg, city, count in result.all():
        if seg not in segment_city_counts:
            segment_city_counts[seg] = {}
            segment_total_counts[seg] = 0
        segment_city_counts[seg][city or ""] = count
        segment_total_counts[seg] += count

    for seg, city_counts in segment_city_counts.items():
        seg_total = segment_total_counts.get(seg, 0)
        if seg_total >= tail_threshold:
            for city_name, count in city_counts.items():
                if count < tail_threshold:
                    utc = city_utc.get(city_name, 0)
                    if other_type == "plusoviki" and utc >= plusoviki_threshold:
                        total += count
                    elif other_type == "regular" and utc < plusoviki_threshold:
                        total += count
        else:
            first_city = next(iter(city_counts.keys()), "")
            utc = city_utc.get(first_city, 0) if first_city else 0
            if other_type == "plusoviki" and utc >= plusoviki_threshold:
                total += seg_total
            elif other_type == "regular" and utc < plusoviki_threshold:
                total += seg_total

    logger.info(f"count_other_leads: segment={segment}, other_type={other_type}, total={total}")
    return total


async def get_other_leads_for_assignment(
    session: AsyncSession,
    other_type: str,
    segment: str = None,
    limit: int = 200,
    tail_threshold: int = 10,
    plusoviki_threshold: int = 3
) -> List[Lead]:
    """Получение лидов из категории 'Прочее'"""
    all_cities_result = await session.execute(select(City))
    city_utc = {c.name: c.utc_offset for c in all_cities_result.scalars().all()}

    query = select(
        Lead.segment, Lead.city, func.count(Lead.id).label('cnt')
    ).where(Lead.status == LeadStatus.UNIQUE)
    if segment:
        query = query.where(Lead.segment == segment)
    query = query.group_by(Lead.segment, Lead.city)

    result = await session.execute(query)
    target_cities: List[Tuple[str, Optional[str]]] = []

    segment_city_counts: Dict[str, Dict[str, int]] = {}
    segment_total_counts: Dict[str, int] = {}

    for seg, city, count in result.all():
        if seg not in segment_city_counts:
            segment_city_counts[seg] = {}
            segment_total_counts[seg] = 0
        segment_city_counts[seg][city or ""] = count
        segment_total_counts[seg] += count

    for seg, city_counts in segment_city_counts.items():
        seg_total = segment_total_counts.get(seg, 0)
        if seg_total >= tail_threshold:
            for city_name, count in city_counts.items():
                if count < tail_threshold:
                    utc = city_utc.get(city_name, 0)
                    if other_type == "plusoviki" and utc >= plusoviki_threshold:
                        target_cities.append((seg, city_name if city_name else None))
                    elif other_type == "regular" and utc < plusoviki_threshold:
                        target_cities.append((seg, city_name if city_name else None))
        else:
            first_city = next(iter(city_counts.keys()), "")
            utc = city_utc.get(first_city, 0) if first_city else 0
            if other_type == "plusoviki" and utc >= plusoviki_threshold:
                for city_name in city_counts.keys():
                    target_cities.append((seg, city_name if city_name else None))
            elif other_type == "regular" and utc < plusoviki_threshold:
                for city_name in city_counts.keys():
                    target_cities.append((seg, city_name if city_name else None))

    if not target_cities:
        return []

    logger.info(
        f"get_other_leads_for_assignment: segment={segment}, "
        f"other_type={other_type}, target_cities={len(target_cities)}"
    )

    conditions = []
    for seg, city in target_cities:
        if city is None:
            conditions.append((Lead.segment == seg) & (Lead.city.is_(None)))
        else:
            conditions.append((Lead.segment == seg) & (Lead.city == city))

    if not conditions:
        return []

    query = select(Lead).where(
        or_(*conditions),
        Lead.status == LeadStatus.UNIQUE
    ).order_by(Lead.created_at).limit(limit)

    result = await session.execute(query)
    return result.scalars().all()


async def update_lead_status(
    session: AsyncSession,
    lead_id: int,
    status: LeadStatus,
    **kwargs
) -> Optional[Lead]:
    """Обновление статуса лида"""
    await session.execute(
        update(Lead)
        .where(Lead.id == lead_id)
        .values(status=status, **kwargs)
    )
    return await get_lead_by_id(session, lead_id)


async def assign_leads_to_manager(
    session: AsyncSession,
    lead_ids: List[int],
    manager_telegram_id: str,
    loaded_by_admin: bool = False
) -> int:
    """
    Назначение лидов менеджеру.

    Returns:
        Фактическое количество назначенных лидов (для обнаружения гонок).
    """
    now = datetime.now(timezone.utc)
    result = await session.execute(
        update(Lead)
        .where(
            Lead.id.in_(lead_ids),
            Lead.status == LeadStatus.UNIQUE
        )
        .values(
            status=LeadStatus.ASSIGNED,
            manager_telegram_id=manager_telegram_id,
            assigned_at=now
        )
    )
    return result.rowcount


async def mark_lead_as_duplicate(
    session: AsyncSession,
    lead_id: int,
    bitrix24_lead_id: Optional[int] = None
) -> None:
    """Отметка лида как дубль"""
    await session.execute(
        update(Lead)
        .where(Lead.id == lead_id)
        .values(
            status=LeadStatus.DUPLICATE,
            duplicate_checked_at=datetime.now(timezone.utc),
            bitrix24_lead_id=bitrix24_lead_id
        )
    )


async def mark_lead_as_unique(
    session: AsyncSession,
    lead_id: int
) -> None:
    """Отметка лида как уникальный"""
    await session.execute(
        update(Lead)
        .where(Lead.id == lead_id)
        .values(
            status=LeadStatus.UNIQUE,
            duplicate_checked_at=datetime.now(timezone.utc)
        )
    )


async def mark_lead_as_imported(
    session: AsyncSession,
    lead_id: int,
    bitrix24_lead_id: int
) -> None:
    """Отметка лида как импортированный в Bitrix24"""
    await session.execute(
        update(Lead)
        .where(Lead.id == lead_id)
        .values(
            status=LeadStatus.IMPORTED,
            bitrix24_lead_id=bitrix24_lead_id,
            imported_at=datetime.now(timezone.utc)
        )
    )


async def delete_old_leads(
    session: AsyncSession,
    status: LeadStatus,
    older_than_days: int
) -> int:
    """
    Удаление старых лидов по статусу.

    Returns:
        Количество удаленных лидов
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    result = await session.execute(
        delete(Lead)
        .where(
            Lead.status == status,
            Lead.created_at < cutoff_date
        )
    )
    return result.rowcount


async def get_available_leads_for_assignment(
    session: AsyncSession,
    segment: str,
    city: Optional[str] = None,
    limit: int = 200
) -> List[Lead]:
    """Получение доступных лидов для загрузки менеджеру (без проверки заморозки)"""
    query = select(Lead).where(
        Lead.status == LeadStatus.UNIQUE,
        Lead.segment == segment
    )

    if city:
        query = query.where(Lead.city == city)

    query = query.order_by(Lead.created_at).limit(limit)
    result = await session.execute(query)
    return result.scalars().all()


async def count_available_leads_for_assignment(
    session: AsyncSession,
    segment: str,
    city: Optional[str] = None
) -> int:
    """Подсчёт доступных лидов для загрузки"""
    query = select(func.count(Lead.id)).where(
        Lead.status == LeadStatus.UNIQUE,
        Lead.segment == segment
    )

    if city:
        query = query.where(Lead.city == city)

    result = await session.execute(query)
    count = result.scalar() or 0
    logger.info(f"count_available_leads_for_assignment: segment={segment}, city={city}, count={count}")
    return count
