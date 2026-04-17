"""
CRUD операции для базы данных
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
import json

from sqlalchemy import select, update, delete, func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ..logger import get_logger
logger = get_logger(__name__)

from .models import (
    Lead, LeadStatus, User, UserRole, UserStatus,
    SegmentLock, Log, DatabaseManager, Segment, Ticket, BotStatus,
    City, PendingCity
)


# =============================================================================
# Lead CRUD
# =============================================================================

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
    Получение доступных лидов для выдачи
    
    Учитывает:
    - Статус UNIQUE
    - Заморозку сегмента/города
    - FIFO порядок
    """
    # Базовый запрос
    query = select(Lead).where(
        Lead.status == LeadStatus.UNIQUE,
        Lead.segment == segment
    )
    
    # Фильтр по городу
    if city:
        query = query.where(Lead.city == city)
    
    # Исключаем уже выданные этому менеджеру
    if exclude_telegram_id:
        query = query.where(
            or_(
                Lead.manager_telegram_id.is_(None),
                Lead.manager_telegram_id == exclude_telegram_id
            )
        )
    
    # Сортировка по дате создания (FIFO)
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
    
    # Исключаем замороженные сегменты
    frozen_subquery = select(SegmentLock.segment).where(
        SegmentLock.is_frozen == True
    )
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
    """Подсчёт лидов в категории 'Прочее' (города < 10 лидов внутри сегмента)"""
    # Получаем все города с UTC
    all_cities_result = await session.execute(select(City))
    city_utc = {c.name: c.utc_offset for c in all_cities_result.scalars().all()}

    # Считаем лиды по сегмент+город
    query = select(
        Lead.segment, Lead.city, func.count(Lead.id).label('cnt')
    ).where(
        Lead.status == LeadStatus.UNIQUE
    )
    if segment:
        query = query.where(Lead.segment == segment)
    query = query.group_by(Lead.segment, Lead.city)

    result = await session.execute(query)
    total = 0

    # Сначала считаем тоталы по сегментам
    segment_city_counts = {}
    segment_total_counts = {}

    for seg, city, count in result.all():
        if seg not in segment_city_counts:
            segment_city_counts[seg] = {}
            segment_total_counts[seg] = 0
        segment_city_counts[seg][city or ""] = count
        segment_total_counts[seg] += count

    # Теперь считаем "Прочие"
    for seg, city_counts in segment_city_counts.items():
        seg_total = segment_total_counts.get(seg, 0)
        if seg_total >= tail_threshold:
            # Сегмент большой, считаем только малые города
            for city_name, count in city_counts.items():
                if count < tail_threshold:
                    utc = city_utc.get(city_name, 0)
                    if other_type == "plusoviki" and utc >= plusoviki_threshold:
                        total += count
                    elif other_type == "regular" and utc < plusoviki_threshold:
                        total += count
        else:
            # Сегмент малый — весь в "Прочее"
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
    """Получение лидов из категории 'Прочее' (города < 10 лидов внутри сегмента)"""
    # Получаем все города с UTC
    all_cities_result = await session.execute(select(City))
    city_utc = {c.name: c.utc_offset for c in all_cities_result.scalars().all()}

    # Считаем лиды по сегмент+город
    query = select(
        Lead.segment, Lead.city, func.count(Lead.id).label('cnt')
    ).where(
        Lead.status == LeadStatus.UNIQUE
    )
    if segment:
        query = query.where(Lead.segment == segment)
    query = query.group_by(Lead.segment, Lead.city)

    result = await session.execute(query)
    target_cities = []  # (segment, city) tuples

    # Считаем тоталы по сегментам
    segment_city_counts = {}
    segment_total_counts = {}

    for seg, city, count in result.all():
        if seg not in segment_city_counts:
            segment_city_counts[seg] = {}
            segment_total_counts[seg] = 0
        segment_city_counts[seg][city or ""] = count
        segment_total_counts[seg] += count

    # Находим целевые города
    for seg, city_counts in segment_city_counts.items():
        seg_total = segment_total_counts.get(seg, 0)
        if seg_total >= tail_threshold:
            # Сегмент большой, берём только малые города
            for city_name, count in city_counts.items():
                if count < tail_threshold:
                    utc = city_utc.get(city_name, 0)
                    if other_type == "plusoviki" and utc >= plusoviki_threshold:
                        target_cities.append((seg, city_name if city_name else None))
                    elif other_type == "regular" and utc < plusoviki_threshold:
                        target_cities.append((seg, city_name if city_name else None))
        else:
            # Сегмент малый — весь в "Прочее"
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

    logger.info(f"get_other_leads_for_assignment: segment={segment}, other_type={other_type}, target_cities={len(target_cities)}")

    # Строим запрос для получения лидов
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


# =============================================================================
# Город CRUD
# =============================================================================

async def get_city(session, city_name):
    """Получить город по имени"""
    result = await session.execute(
        select(City).where(City.name == city_name)
    )
    return result.scalar()


async def create_city(session, city_name, utc_offset):
    """Создать город"""
    city = City(name=city_name.strip(), utc_offset=utc_offset)
    session.add(city)
    await session.flush()
    return city


async def update_city_utc(session, city_name, utc_offset):
    """Обновить UTC offset города"""
    result = await session.execute(
        select(City).where(City.name == city_name)
    )
    city = result.scalar()
    if city:
        city.utc_offset = utc_offset
        await session.flush()
        return True
    return False


async def get_all_cities(session):
    """Получить все города"""
    result = await session.execute(select(City).order_by(City.name))
    return list(result.scalars().all())


async def delete_city(session, city_name):
    """Удалить город"""
    result = await session.execute(
        select(City).where(City.name == city_name)
    )
    city = result.scalar()
    if city:
        await session.delete(city)
        await session.flush()
        return True
    return False


# =============================================================================
# Pending City CRUD
# =============================================================================

async def create_pending_city(session, city_name, admin_telegram_id):
    """Создать pending город (если ещё не существует)"""
    existing = await session.execute(
        select(PendingCity).where(PendingCity.name == city_name)
    )
    if existing.scalar():
        return None

    in_cities = await session.execute(
        select(City).where(City.name == city_name)
    )
    if in_cities.scalar():
        return None

    pending = PendingCity(name=city_name.strip(), admin_telegram_id=str(admin_telegram_id))
    session.add(pending)
    await session.flush()
    return pending


async def get_pending_cities(session):
    """Получить все pending города"""
    result = await session.execute(
        select(PendingCity).order_by(PendingCity.created_at)
    )
    return list(result.scalars().all())


async def approve_pending_city(session, city_name, utc_offset):
    """
    Одобрить pending город:
    1. Создать запись в cities
    2. Удалить из pending_cities
    3. Обновить лиды со статусом PENDING_UTC → UNIQUE
    """
    city = await create_city(session, city_name, utc_offset)

    result = await session.execute(
        select(Lead.id).where(
            Lead.city == city_name,
            Lead.status == LeadStatus.PENDING_UTC
        )
    )
    lead_ids = [row[0] for row in result.all()]

    if lead_ids:
        from sqlalchemy import update as sql_update
        await session.execute(
            sql_update(Lead)
            .where(Lead.id.in_(lead_ids))
            .values(status=LeadStatus.UNIQUE)
        )

    result = await session.execute(
        select(PendingCity).where(PendingCity.name == city_name)
    )
    pending = result.scalar()
    if pending:
        await session.delete(pending)

    await session.flush()

    return {"approved": len(lead_ids)}


async def reject_pending_city(session, city_name):
    """
    Отклонить pending город:
    1. Удалить лиды со статусом PENDING_UTC
    2. Удалить из pending_cities
    """
    from sqlalchemy import delete as sql_delete

    result = await session.execute(
        select(Lead.id).where(
            Lead.city == city_name,
            Lead.status == LeadStatus.PENDING_UTC
        )
    )
    lead_ids = [row[0] for row in result.all()]

    if lead_ids:
        await session.execute(
            sql_delete(Lead).where(Lead.id.in_(lead_ids))
        )

    result = await session.execute(
        select(PendingCity).where(PendingCity.name == city_name)
    )
    pending = result.scalar()
    if pending:
        await session.delete(pending)

    await session.flush()

    return {"deleted_leads": len(lead_ids)}


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
    Назначение лидов менеджеру

    Args:
        session: Сессия БД
        lead_ids: Список ID лидов
        manager_telegram_id: Telegram ID менеджера
        loaded_by_admin: Флаг загрузки админом (по умолчанию False)

    Returns:
        Количество назначенных лидов
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
    Удаление старых лидов по статусу
    
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


# =============================================================================
# User CRUD
# =============================================================================

async def create_user(
    session: AsyncSession,
    telegram_id: str,
    full_name: Optional[str] = None,
    username: Optional[str] = None,
    role: UserRole = UserRole.MANAGER,
    status: UserStatus = UserStatus.PENDING_APPROVAL,
    bitrix24_user_id: Optional[int] = None
) -> User:
    """Создание пользователя"""
    user = User(
        telegram_id=telegram_id,
        full_name=full_name,
        username=username,
        role=role,
        status=status,
        bitrix24_user_id=bitrix24_user_id
    )
    session.add(user)
    await session.flush()
    return user


async def get_user_by_telegram_id(
    session: AsyncSession,
    telegram_id: str
) -> Optional[User]:
    """Получение пользователя по Telegram ID"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_full_name(
    session: AsyncSession,
    full_name: str
) -> Optional[User]:
    """Получение пользователя по ФИО (для привязки из CSV)"""
    result = await session.execute(
        select(User).where(User.full_name == full_name)
    )
    return result.scalar_one_or_none()


async def get_pending_users(session: AsyncSession) -> List[User]:
    """Получение пользователей, ожидающих подтверждения"""
    result = await session.execute(
        select(User)
        .where(User.status == UserStatus.PENDING_APPROVAL)
        .order_by(User.registered_at)
    )
    return result.scalars().all()


async def approve_user(
    session: AsyncSession,
    telegram_id: str,
    bitrix24_user_id: int
) -> Optional[User]:
    """Подтверждение пользователя админом"""
    await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(
            status=UserStatus.ACTIVE,
            bitrix24_user_id=bitrix24_user_id,
            approved_at=datetime.now(timezone.utc)
        )
    )
    return await get_user_by_telegram_id(session, telegram_id)


async def reject_user(
    session: AsyncSession,
    telegram_id: str
) -> Optional[User]:
    """Отклонение пользователя"""
    await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(status=UserStatus.REJECTED)
    )
    return await get_user_by_telegram_id(session, telegram_id)


async def update_user_name(
    session: AsyncSession,
    telegram_id: str,
    full_name: str
) -> None:
    """Обновление имени пользователя"""
    await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(full_name=full_name)
    )


async def update_user_role(
    session: AsyncSession,
    telegram_id: str,
    role: UserRole
) -> Optional[User]:
    """Обновление роли пользователя"""
    await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(role=role)
    )
    return await get_user_by_telegram_id(session, telegram_id)


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
    # Проверяем заморозку всего сегмента
    segment_lock = await get_segment_lock(session, segment, city=None)
    if segment_lock and segment_lock.is_frozen:
        return True
    
    # Проверяем заморозку сегмент+город
    if city:
        city_lock = await get_segment_lock(session, segment, city=city)
        if city_lock and city_lock.is_frozen:
            return True
    
    return False


# =============================================================================
# Log CRUD
# =============================================================================

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
    Создание записи лога
    
    Args:
        session: Сессия БД
        event_type: Тип события
        user_telegram_id: Telegram ID пользователя
        related_lead_ids: Список ID связанных лидов (валидируется)
        related_segment: Связанный сегмент
        related_city: Связанный город
        description: Описание события
        
    Returns:
        Созданный Log объект
        
    Raises:
        ValueError: Если related_lead_ids содержит некорректные данные
    """
    # Валидация related_lead_ids (защита от SQL injection через JSON)
    validated_lead_ids = None
    if related_lead_ids is not None:
        if not isinstance(related_lead_ids, list):
            raise ValueError(f"related_lead_ids должен быть списком, получен {type(related_lead_ids).__name__}")
        
        # Проверяем каждый ID
        for item in related_lead_ids:
            if not isinstance(item, int):
                raise ValueError(f"Все ID лидов должны быть целыми числами, получен {type(item).__name__}: {item}")
            if item <= 0:
                raise ValueError(f"ID лида должен быть положительным числом, получен {item}")
        
        validated_lead_ids = related_lead_ids
    
    # Валидация строковых полей (защита от injection)
    validated_segment = None
    if related_segment is not None:
        if not isinstance(related_segment, str):
            raise ValueError(f"related_segment должен быть строкой")
        if len(related_segment) > 500:
            raise ValueError(f"related_segment слишком длинный (максимум 500 символов)")
        validated_segment = related_segment
    
    validated_city = None
    if related_city is not None:
        if not isinstance(related_city, str):
            raise ValueError(f"related_city должен быть строкой")
        if len(related_city) > 500:
            raise ValueError(f"related_city слишком длинный (максимум 500 символов)")
        validated_city = related_city
    
    validated_description = None
    if description is not None:
        if not isinstance(description, str):
            raise ValueError(f"description должен быть строкой")
        if len(description) > 5000:
            raise ValueError(f"description слишком длинный (максимум 5000 символов)")
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
    Удаление старых логов
    
    Returns:
        Количество удаленных записей
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    result = await session.execute(
        delete(Log).where(Log.timestamp < cutoff_date)
    )
    return result.rowcount


# =============================================================================
# Analytics Helpers
# =============================================================================

async def get_lead_stats_by_period(
    session: AsyncSession,
    start_date: datetime,
    end_date: datetime,
    segment: Optional[str] = None
) -> Dict[str, Any]:
    """
    Получение статистики лидов за период
    
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


async def get_segments_with_cities(
    session: AsyncSession,
    exclude_frozen: bool = True,
    include_other: bool = True,
    tail_threshold: int = 10,
    plusoviki_threshold: int = 3
) -> List[Tuple[str, List[str]]]:
    """
    Получение списка сегментов с городами

    Логика:
    - Если сегмент < tail_threshold лидов → весь сегмент в "Прочее"
    - Если сегмент >= tail_threshold → показываем сегмент, города < tail_threshold → "📦 Прочие"

    Args:
        session: Сессия БД
        exclude_frozen: Исключать замороженные сегменты
        include_other: Включать категорию "Прочее" для хвостов
        tail_threshold: Порог для "хвоста" (< N лидов)
        plusoviki_threshold: Порог для "плюсовиков" (>= N часов от МСК)

    Returns:
        List кортежей [(segment, [cities]), ...]
    """
    # Получаем все города с их UTC
    all_cities_result = await session.execute(select(City))
    city_utc = {c.name: c.utc_offset for c in all_cities_result.scalars().all()}

    # Считаем лиды по сегмент+город
    leads_count_query = select(
        Lead.segment, Lead.city, func.count(Lead.id).label('cnt')
    ).where(
        Lead.status == LeadStatus.UNIQUE
    ).group_by(Lead.segment, Lead.city)

    result = await session.execute(leads_count_query)
    segment_city_counts = {}
    segment_total_counts = {}

    for segment, city, count in result.all():
        logger.info(f"  Сегмент '{segment}', город '{city or ''}': {count} лидов")
        if segment not in segment_city_counts:
            segment_city_counts[segment] = {}
            segment_total_counts[segment] = 0
        segment_city_counts[segment][city or ""] = count
        segment_total_counts[segment] += count

    # Исключаем замороженные
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
            # Пересчитываем тотал
            if segment in segment_total_counts:
                segment_total_counts[segment] = sum(segment_city_counts.get(segment, {}).values())

        # Исключаем замороженные сегменты целиком
        frozen_segments = select(SegmentLock.segment).where(
            SegmentLock.is_frozen == True,
            SegmentLock.city.is_(None)
        )
        frozen_segs_result = await session.execute(frozen_segments)
        for (frozen_seg,) in frozen_segs_result.all():
            segment_city_counts.pop(frozen_seg, None)
            segment_total_counts.pop(frozen_seg, None)

    result_segments = []
    other_regular_leads = 0  # Счётчик лидов в Обыч
    other_plusoviki_leads = 0  # Счётчик лидов в Плюсовики

    logger.info(f"get_segments_with_cities: сегментов={len(segment_city_counts)}, tail_threshold={tail_threshold}")

    for segment, city_counts in segment_city_counts.items():
        total = segment_total_counts.get(segment, 0)
        logger.info(f"  Сегмент '{segment}': {total} лидов, города={list(city_counts.keys())}")

        if total < tail_threshold:
            # Весь сегмент < 10 → в "Прочее"
            # Определяем UTC по первому городу (или 0 если нет)
            first_city = next(iter(city_counts.keys()), "")
            utc = city_utc.get(first_city, 0) if first_city else 0
            if utc >= plusoviki_threshold:
                other_plusoviki_leads += total
            else:
                other_regular_leads += total
        else:
            # Сегмент >= 10 → показываем
            visible_cities = []
            other_regular_count = 0
            other_regular_leads = 0
            other_plusoviki_count = 0
            other_plusoviki_leads = 0

            for city_name, count in city_counts.items():
                if count >= tail_threshold:
                    visible_cities.append(city_name if city_name else "Без города")
                else:
                    # Определяем UTC города
                    utc = city_utc.get(city_name, 0)
                    if utc >= plusoviki_threshold:
                        other_plusoviki_count += 1
                        other_plusoviki_leads += count
                    else:
                        other_regular_count += 1
                        other_regular_leads += count

            if other_regular_count > 0:
                visible_cities.append(f"📦 Прочие (Обыч.) ({other_regular_leads})")
            if other_plusoviki_count > 0:
                visible_cities.append(f"📦 Прочие (Плюсовики) ({other_plusoviki_leads})")

            result_segments.append((segment, visible_cities))
            logger.info(f"    Сегмент '{segment}' добавлен с городами: {visible_cities}")

    # Добавляем "Прочее" категории
    if include_other:
        if other_regular_leads > 0:
            result_segments.append((f"📦 Прочее (Обыч.)", []))
            logger.info(f"  Добавлено 'Прочее (Обыч.)': {other_regular_leads} лидов")
        if other_plusoviki_leads > 0:
            result_segments.append((f"📦 Прочее (Плюсовики)", []))
            logger.info(f"  Добавлено 'Прочее (Плюсовики)': {other_plusoviki_leads} лидов")

    logger.info(f"get_segments_with_cities: итого {len(result_segments)} сегментов")
    return result_segments


# =============================================================================
# Segment CRUD
# =============================================================================

async def get_all_segments(session: AsyncSession, active_only: bool = True) -> List[Segment]:
    """
    Получение всех сегментов
    
    Args:
        session: Сессия БД
        active_only: Только активные сегменты
        
    Returns:
        Список сегментов
    """
    query = select(Segment).order_by(Segment.name)
    
    if active_only:
        query = query.where(Segment.is_active == True)
    
    result = await session.execute(query)
    return result.scalars().all()


async def get_segment_by_name(session: AsyncSession, name: str) -> Optional[Segment]:
    """
    Получение сегмента по названию
    
    Args:
        session: Сессия БД
        name: Название сегмента
        
    Returns:
        Сегмент или None
    """
    result = await session.execute(
        select(Segment).where(Segment.name == name)
    )
    return result.scalar_one_or_none()


async def create_segment(
    session: AsyncSession,
    name: str,
    description: Optional[str] = None
) -> Segment:
    """
    Создание сегмента
    
    Args:
        session: Сессия БД
        name: Название сегмента
        description: Описание
        
    Returns:
        Созданный сегмент
    """
    segment = Segment(
        name=name,
        description=description,
        is_active=True
    )
    session.add(segment)
    await session.flush()
    return segment


async def sync_segments_from_leads(session: AsyncSession) -> int:
    """
    Синхронизация сегментов из таблицы leads
    
    Добавляет новые сегменты из leads в таблицу segments
    
    Args:
        session: Сессия БД
        
    Returns:
        Количество добавленных сегментов
    """
    # Получаем все уникальные сегменты из leads
    result = await session.execute(
        select(Lead.segment).distinct().where(Lead.segment.isnot(None))
    )
    lead_segments = result.scalars().all()
    
    # Получаем существующие сегменты
    existing_segments = await get_all_segments(session, active_only=False)
    existing_names = {seg.name for seg in existing_segments}
    
    # Добавляем новые
    added_count = 0
    for segment_name in lead_segments:
        if segment_name not in existing_names:
            await create_segment(session, segment_name)
            added_count += 1

    return added_count


# =============================================================================
# Ticket CRUD
# =============================================================================

async def create_ticket(
    session: AsyncSession,
    manager_telegram_id: str,
    message: str
) -> Ticket:
    """
    Создание тикета обратной связи

    Args:
        session: Сессия БД
        manager_telegram_id: Telegram ID менеджера
        message: Текст сообщения

    Returns:
        Созданный тикет
    """
    ticket = Ticket(
        manager_telegram_id=manager_telegram_id,
        message=message,
        status="new"
    )
    session.add(ticket)
    await session.flush()
    return ticket


async def get_ticket_by_id(
    session: AsyncSession,
    ticket_id: int
) -> Optional[Ticket]:
    """
    Получение тикета по ID

    Args:
        session: Сессия БД
        ticket_id: ID тикета

    Returns:
        Тикет или None
    """
    result = await session.execute(
        select(Ticket).where(Ticket.id == ticket_id)
    )
    return result.scalar_one_or_none()


async def get_tickets_paginated(
    session: AsyncSession,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
) -> Tuple[List[Ticket], int]:
    """
    Получение тикетов с пагинацией

    Args:
        session: Сессия БД
        status: Фильтр по статусу (None = все)
        page: Номер страницы (1-based)
        page_size: Размер страницы

    Returns:
        (тикеты, общее количество)
    """
    # Базовый запрос
    query = select(Ticket)
    
    # Фильтр по статусу
    if status:
        query = query.where(Ticket.status == status)
    
    # Получаем общее количество
    count_query = select(func.count(Ticket.id))
    if status:
        count_query = count_query.where(Ticket.status == status)
    
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0
    
    # Пагинация
    offset = (page - 1) * page_size
    query = query.order_by(Ticket.created_at.desc()).offset(offset).limit(page_size)
    
    result = await session.execute(query)
    tickets = result.scalars().all()
    
    return tickets, total


async def get_ticket_stats(session: AsyncSession) -> Dict[str, int]:
    """
    Получение статистики тикетов по статусам

    Args:
        session: Сессия БД

    Returns:
        Dict со статистикой: {status: count}
    """
    result = await session.execute(
        select(Ticket.status, func.count(Ticket.id))
        .group_by(Ticket.status)
    )
    
    stats = {"new": 0, "in_progress": 0, "resolved": 0, "closed": 0}
    for row in result.all():
        status, count = row
        if status in stats:
            stats[status] = count
    
    return stats


async def update_ticket_status(
    session: AsyncSession,
    ticket_id: int,
    status: str,
    admin_telegram_id: Optional[str] = None
) -> bool:
    """
    Обновление статуса тикета

    Args:
        session: Сессия БД
        ticket_id: ID тикета
        status: Новый статус
        admin_telegram_id: Telegram ID админа (опционально)

    Returns:
        True если успешно
    """
    from datetime import datetime, timezone
    
    update_data = {
        "status": status,
    }
    
    # Устанавливаем admin_telegram_id если передан
    if admin_telegram_id:
        update_data["admin_telegram_id"] = admin_telegram_id
    
    # Устанавливаем дату ответа/закрытия
    if status == "in_progress":
        update_data["responded_at"] = datetime.now(timezone.utc)
    elif status in ["resolved", "closed"]:
        update_data["resolved_at"] = datetime.now(timezone.utc)
    
    result = await session.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id)
        .values(**update_data)
    )
    return result.rowcount > 0


async def add_admin_response(
    session: AsyncSession,
    ticket_id: int,
    admin_telegram_id: str,
    response: str
) -> bool:
    """
    Добавление ответа администратора на тикет

    Args:
        session: Сессия БД
        ticket_id: ID тикета
        admin_telegram_id: Telegram ID админа
        response: Текст ответа

    Returns:
        True если успешно
    """
    from datetime import datetime, timezone
    
    result = await session.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id)
        .values(
            admin_response=response,
            responded_at=datetime.now(timezone.utc),
            admin_telegram_id=admin_telegram_id,
            status="in_progress"
        )
    )
    return result.rowcount > 0


async def get_tickets_by_manager(
    session: AsyncSession,
    manager_telegram_id: str,
    limit: int = 10
) -> List[Ticket]:
    """
    Получение тикетов менеджера

    Args:
        session: Сессия БД
        manager_telegram_id: Telegram ID менеджера
        limit: Количество тикетов

    Returns:
        Список тикетов
    """
    result = await session.execute(
        select(Ticket)
        .where(Ticket.manager_telegram_id == manager_telegram_id)
        .order_by(Ticket.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


# =============================================================================
# Bot Status CRUD
# =============================================================================

async def get_bot_status(session: AsyncSession) -> BotStatus | None:
    """
    Получение текущего статуса бота

    Args:
        session: Сессия БД

    Returns:
        Статус бота или None
    """
    # Получаем единственную запись (id=1)
    result = await session.execute(select(BotStatus).where(BotStatus.id == 1))
    return result.scalar_one_or_none()


async def set_bot_status(
    session: AsyncSession,
    status: str,
    reason: str | None = None
) -> BotStatus:
    """
    Установка статуса бота

    Args:
        session: Сессия БД
        status: Новый статус (running, stopped, maintenance)
        reason: Причина (опционально)

    Returns:
        Обновлённый статус бота
    """
    from datetime import datetime, timezone
    
    # Проверяем существование записи
    bot_status = await get_bot_status(session)
    
    if bot_status:
        # Обновляем существующую запись
        await session.execute(
            update(BotStatus)
            .where(BotStatus.id == 1)
            .values(
                status=status,
                reason=reason,
                updated_at=datetime.now(timezone.utc)
            )
        )
    else:
        # Создаём новую запись
        bot_status = BotStatus(id=1, status=status, reason=reason)
        session.add(bot_status)

    await session.flush()
    return await get_bot_status(session)


async def is_bot_running(session: AsyncSession) -> bool:
    """
    Проверка, работает ли бот

    Args:
        session: Сессия БД

    Returns:
        True если бот работает, False если остановлен
    """
    bot_status = await get_bot_status(session)
    
    if not bot_status:
        return True  # По умолчанию бот работает
    
    return bot_status.status == "running"


async def is_bot_maintenance(session: AsyncSession) -> bool:
    """
    Проверка, находится ли бот в режиме техработ

    Args:
        session: Сессия БД

    Returns:
        True если техработы, False если нет
    """
    bot_status = await get_bot_status(session)
    
    if not bot_status:
        return False
    
    return bot_status.status == "maintenance"


async def get_all_active_admins(session: AsyncSession) -> List[User]:
    """
    Получение всех активных админов
    
    Args:
        session: Сессия БД
        
    Returns:
        Список активных админов
    """
    result = await session.execute(
        select(User)
        .where(
            User.role == UserRole.ADMIN,
            User.status == UserStatus.ACTIVE
        )
        .order_by(User.telegram_id)
    )
    return result.scalars().all()


async def get_all_active_users(session: AsyncSession) -> List[User]:
    """
    Получение всех активных пользователей (админы + менеджеры)

    Args:
        session: Сессия БД

    Returns:
        Список всех активных пользователей
    """
    result = await session.execute(
        select(User)
        .where(User.status == UserStatus.ACTIVE)
        .order_by(User.telegram_id)
    )
    return result.scalars().all()


async def get_active_managers_with_stats(session: AsyncSession) -> List[Dict[str, Any]]:
    """
    Получение активных менеджеров со статистикой

    Args:
        session: Сессия БД

    Returns:
        Список менеджеров с информацией: telegram_id, full_name, leads_count
    """
    result = await session.execute(
        select(
            User.telegram_id,
            User.full_name,
            func.count(Lead.id).label("leads_count")
        )
        .outerjoin(Lead, User.telegram_id == Lead.manager_telegram_id)
        .where(
            User.role == UserRole.MANAGER,
            User.status == UserStatus.ACTIVE
        )
        .group_by(User.telegram_id, User.full_name)
        .order_by(User.full_name)
    )
    
    managers = []
    for row in result.all():
        managers.append({
            "telegram_id": row.telegram_id,
            "full_name": row.full_name or "Без имени",
            "leads_count": row.leads_count or 0
        })
    
    return managers


async def get_available_leads_for_assignment(
    session: AsyncSession,
    segment: str,
    city: Optional[str] = None,
    limit: int = 200
) -> List[Lead]:
    """
    Получение доступных лидов для загрузки менеджеру

    Args:
        session: Сессия БД
        segment: Сегмент лидов
        city: Город (опционально)
        limit: Максимальное количество

    Returns:
        Список доступных лидов
    """
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
