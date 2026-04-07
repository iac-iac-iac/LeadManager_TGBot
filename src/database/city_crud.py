"""
CRUD операции для городов и pending городов
"""
from sqlalchemy import select, func, update as sql_update, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from .models import City, PendingCity, Lead, LeadStatus


async def get_city(session: AsyncSession, city_name: str):
    """Получить город по имени"""
    result = await session.execute(
        select(City).where(City.name == city_name)
    )
    return result.scalar()


async def create_city(session: AsyncSession, city_name: str, utc_offset: int):
    """Создать город"""
    city = City(name=city_name.strip(), utc_offset=utc_offset)
    session.add(city)
    await session.flush()
    return city


async def update_city_utc(session: AsyncSession, city_name: str, utc_offset: int) -> bool:
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


async def get_all_cities(session: AsyncSession):
    """Получить все города"""
    result = await session.execute(select(City).order_by(City.name))
    return list(result.scalars().all())


async def delete_city(session: AsyncSession, city_name: str) -> bool:
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


async def create_pending_city(session: AsyncSession, city_name: str, admin_telegram_id: str):
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


async def get_pending_cities(session: AsyncSession):
    """Получить все pending города"""
    result = await session.execute(
        select(PendingCity).order_by(PendingCity.created_at)
    )
    return list(result.scalars().all())


async def approve_pending_city(session: AsyncSession, city_name: str, utc_offset: int) -> dict:
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


async def reject_pending_city(session: AsyncSession, city_name: str) -> dict:
    """
    Отклонить pending город:
    1. Удалить лиды со статусом PENDING_UTC
    2. Удалить из pending_cities
    """
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


async def count_pending_cities(session: AsyncSession) -> int:
    """Количество pending городов"""
    result = await session.execute(select(func.count(PendingCity.id)))
    return result.scalar() or 0


async def delete_approved_city(session: AsyncSession, city_name: str) -> dict:
    """
    Удалить одобренный город из cities и все его лиды из leads
    """
    # Находим город
    result = await session.execute(
        select(City).where(City.name == city_name)
    )
    city = result.scalar()
    if not city:
        return {"deleted_leads": 0, "city_found": False}

    # Удаляем все лиды этого города
    result = await session.execute(
        select(Lead.id).where(Lead.city == city_name)
    )
    lead_ids = [row[0] for row in result.all()]

    if lead_ids:
        await session.execute(
            sql_delete(Lead).where(Lead.id.in_(lead_ids))
        )

    # Удаляем город
    await session.delete(city)
    await session.flush()

    return {"deleted_leads": len(lead_ids), "city_found": True}
