"""
Миграция v8: Таблицы городов и pending городов

Добавляет:
- Таблица cities (город, utc_offset)
- Таблица pending_cities (город ожидающий ввода UTC)
- Статус PENDING_UTC для лидов

Миграция существующих городов:
- Извлекает уникальные города из Lead.city
- Вставляет в cities с utc_offset=0 (админ обновит позже)
"""
import logging
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def migrate_v8(session: AsyncSession, City, Lead, LeadStatus):
    """
    Выполнение миграции v8

    Создаёт таблицы cities и pending_cities,
    мигрирует существующие города из Lead.city
    """
    logger.info("Миграция v8: таблицы городов")

    # Таблицы уже созданы через Base.metadata.create_all()
    # Нужно только мигрировать существующие данные

    # 1. Извлекаем уникальные города из лидов
    result = await session.execute(
        select(Lead.city)
        .where(Lead.city.isnot(None))
        .distinct()
    )
    existing_cities = [row[0] for row in result.all()]

    logger.info("Найдено уникальных городов: %s", len(existing_cities))

    # 2. Вставляем в cities с utc_offset=0 (временное значение)
    added = 0
    for city_name in existing_cities:
        city_name = city_name.strip()
        if not city_name:
            continue

        # Проверяем, нет ли уже такого города
        existing = await session.execute(
            select(City).where(City.name == city_name)
        )
        if existing.scalar():
            continue

        # Вставляем с utc_offset=0
        city = City(name=city_name, utc_offset=0)
        session.add(city)
        added += 1

    await session.commit()
    logger.info("Добавлено городов: %s (utc_offset=0)", added)

    # 3. Записываем версию миграции
    await session.execute(
        text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (:v)"),
        {"v": 8}
    )
    await session.commit()

    logger.info(
        "Миграция v8 завершена. Обновите utc_offset для городов в меню управления городами."
    )
