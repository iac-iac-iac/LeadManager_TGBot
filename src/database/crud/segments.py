"""
CRUD для работы с сегментами, блокировками сегментов и сводными данными
"""
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Segment, SegmentLock, Lead, LeadStatus, City
)
from ...logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# SegmentLock CRUD
# =============================================================================

async def get_segment_lock(
    session: AsyncSession,
    segment: str,
    city: Optional[str] = None
) -> Optional[SegmentLock]:
    """Получение заморозки сегмента"""
    query = select(SegmentLock).where(SegmentLock.segment == segment)
    if city:
        query = query.where(SegmentLock.city == city)
    else:
        query = query.where(SegmentLock.city.is_(None))
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def freeze_segment(
    session: AsyncSession,
    segment: str,
    city: Optional[str] = None,
    admin_comment: Optional[str] = None
) -> SegmentLock:
    """Заморозка сегмента"""
    lock = await get_segment_lock(session, segment, city)

    if lock:
        await session.execute(
            update(SegmentLock)
            .where(SegmentLock.id == lock.id)
            .values(
                is_frozen=True,
                frozen_at=datetime.now(timezone.utc),
                admin_comment=admin_comment
            )
        )
        return lock
    else:
        new_lock = SegmentLock(
            segment=segment,
            city=city,
            is_frozen=True,
            frozen_at=datetime.now(timezone.utc),
            admin_comment=admin_comment
        )
        session.add(new_lock)
        await session.flush()
        return new_lock


async def unfreeze_segment(
    session: AsyncSession,
    segment: str,
    city: Optional[str] = None
) -> Optional[SegmentLock]:
    """Разморозка сегмента"""
    lock = await get_segment_lock(session, segment, city)

    if lock:
        await session.execute(
            update(SegmentLock)
            .where(SegmentLock.id == lock.id)
            .values(
                is_frozen=False,
                unfrozen_at=datetime.now(timezone.utc)
            )
        )
        return lock
    return None


async def get_all_segment_locks(session: AsyncSession) -> List[SegmentLock]:
    """Получение всех заморозок"""
    result = await session.execute(select(SegmentLock))
    return result.scalars().all()


async def is_segment_frozen(
    session: AsyncSession,
    segment: str,
    city: Optional[str] = None
) -> bool:
    """Проверка, заморожен ли сегмент"""
    segment_lock = await get_segment_lock(session, segment, city=None)
    if segment_lock and segment_lock.is_frozen:
        return True

    if city:
        city_lock = await get_segment_lock(session, segment, city=city)
        if city_lock and city_lock.is_frozen:
            return True

    return False


# =============================================================================
# Segment table CRUD
# =============================================================================

async def get_all_segments(session: AsyncSession, active_only: bool = True) -> List[Segment]:
    """Получение всех сегментов"""
    query = select(Segment).order_by(Segment.name)
    if active_only:
        query = query.where(Segment.is_active == True)
    result = await session.execute(query)
    return result.scalars().all()


async def get_segment_by_name(session: AsyncSession, name: str) -> Optional[Segment]:
    """Получение сегмента по названию"""
    result = await session.execute(
        select(Segment).where(Segment.name == name)
    )
    return result.scalar_one_or_none()


async def create_segment(
    session: AsyncSession,
    name: str,
    description: Optional[str] = None
) -> Segment:
    """Создание сегмента"""
    segment = Segment(name=name, description=description, is_active=True)
    session.add(segment)
    await session.flush()
    return segment


async def sync_segments_from_leads(session: AsyncSession) -> int:
    """
    Синхронизация сегментов из таблицы leads.

    Returns:
        Количество добавленных сегментов
    """
    result = await session.execute(
        select(Lead.segment).distinct().where(Lead.segment.isnot(None))
    )
    lead_segments = result.scalars().all()

    existing_segments = await get_all_segments(session, active_only=False)
    existing_names = {seg.name for seg in existing_segments}

    added_count = 0
    for segment_name in lead_segments:
        if segment_name not in existing_names:
            await create_segment(session, segment_name)
            added_count += 1

    return added_count


# =============================================================================
# Segments with cities (aggregated view)
# =============================================================================

async def get_segments_with_cities(
    session: AsyncSession,
    exclude_frozen: bool = True,
    include_other: bool = True,
    tail_threshold: int = 10,
    plusoviki_threshold: int = 3
) -> List[Tuple[str, List[str]]]:
    """
    Получение списка сегментов с городами.

    Логика:
    - Если сегмент < tail_threshold лидов → весь сегмент в "Прочее"
    - Если сегмент >= tail_threshold → показываем сегмент;
      города с < tail_threshold лидов → "📦 Прочие"

    Returns:
        List кортежей [(segment, [cities]), ...]
    """
    all_cities_result = await session.execute(select(City))
    city_utc = {c.name: c.utc_offset for c in all_cities_result.scalars().all()}

    leads_count_query = select(
        Lead.segment, Lead.city, func.count(Lead.id).label('cnt')
    ).where(
        Lead.status == LeadStatus.UNIQUE
    ).group_by(Lead.segment, Lead.city)

    result = await session.execute(leads_count_query)
    segment_city_counts: Dict[str, Dict[str, int]] = {}
    segment_total_counts: Dict[str, int] = {}

    for segment, city, count in result.all():
        logger.info(f"  Сегмент '{segment}', город '{city or ''}': {count} лидов")
        if segment not in segment_city_counts:
            segment_city_counts[segment] = {}
            segment_total_counts[segment] = 0
        segment_city_counts[segment][city or ""] = count
        segment_total_counts[segment] += count

    if exclude_frozen:
        frozen_cities_query = select(
            SegmentLock.segment, SegmentLock.city
        ).where(
            SegmentLock.is_frozen == True,
            SegmentLock.city.isnot(None)
        )
        frozen_cities = await session.execute(frozen_cities_query)
        for segment, city in frozen_cities.all():
            if segment in segment_city_counts and city in segment_city_counts[segment]:
                del segment_city_counts[segment][city]
            if segment in segment_total_counts:
                segment_total_counts[segment] = sum(segment_city_counts.get(segment, {}).values())

        frozen_segments = select(SegmentLock.segment).where(
            SegmentLock.is_frozen == True,
            SegmentLock.city.is_(None)
        )
        frozen_segs_result = await session.execute(frozen_segments)
        for (frozen_seg,) in frozen_segs_result.all():
            segment_city_counts.pop(frozen_seg, None)
            segment_total_counts.pop(frozen_seg, None)

    result_segments = []
    other_regular_leads = 0
    other_plusoviki_leads = 0

    logger.info(
        f"get_segments_with_cities: сегментов={len(segment_city_counts)}, "
        f"tail_threshold={tail_threshold}"
    )

    for segment, city_counts in segment_city_counts.items():
        total = segment_total_counts.get(segment, 0)
        logger.info(f"  Сегмент '{segment}': {total} лидов, города={list(city_counts.keys())}")

        if total < tail_threshold:
            first_city = next(iter(city_counts.keys()), "")
            utc = city_utc.get(first_city, 0) if first_city else 0
            if utc >= plusoviki_threshold:
                other_plusoviki_leads += total
            else:
                other_regular_leads += total
        else:
            visible_cities = []
            other_regular_count = 0
            seg_other_regular_leads = 0
            other_plusoviki_count = 0
            seg_other_plusoviki_leads = 0

            for city_name, count in city_counts.items():
                if count >= tail_threshold:
                    visible_cities.append(city_name if city_name else "Без города")
                else:
                    utc = city_utc.get(city_name, 0)
                    if utc >= plusoviki_threshold:
                        other_plusoviki_count += 1
                        seg_other_plusoviki_leads += count
                    else:
                        other_regular_count += 1
                        seg_other_regular_leads += count

            if other_regular_count > 0:
                visible_cities.append(f"📦 Прочие (Обыч.) ({seg_other_regular_leads})")
            if other_plusoviki_count > 0:
                visible_cities.append(f"📦 Прочие (Плюсовики) ({seg_other_plusoviki_leads})")

            result_segments.append((segment, visible_cities))
            logger.info(f"    Сегмент '{segment}' добавлен с городами: {visible_cities}")

    if include_other:
        if other_regular_leads > 0:
            result_segments.append((f"📦 Прочее (Обыч.)", []))
            logger.info(f"  Добавлено 'Прочее (Обыч.)': {other_regular_leads} лидов")
        if other_plusoviki_leads > 0:
            result_segments.append((f"📦 Прочее (Плюсовики)", []))
            logger.info(f"  Добавлено 'Прочее (Плюсовики)': {other_plusoviki_leads} лидов")

    logger.info(f"get_segments_with_cities: итого {len(result_segments)} сегментов")
    return result_segments
