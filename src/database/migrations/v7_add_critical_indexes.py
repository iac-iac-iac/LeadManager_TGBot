"""
Миграция v7: Добавление критических составных индексов производительности

Оставлены только реально полезные составные индексы.
Одноколоночные индексы уже определены в models.py и не дублируются:
    - idx_leads_bitrix24_lead_id  (Lead.bitrix24_lead_id)
    - idx_users_telegram_id_unique (User.telegram_id, уникальный)
    - idx_segments_active          (Segment.is_active)
"""
from sqlalchemy import text

from src.logger import setup_logger

logger = setup_logger()


async def migration_v7_add_critical_indexes(conn):
    """
    Применение миграции v7: составные индексы.

    Созданные индексы:
    1. idx_leads_phone          — для поиска дублей по телефону
    2. idx_leads_company_name   — для поиска дублей по компании
    3. idx_users_role_status    — для фильтрации пользователей по роли+статусу
    4. idx_tickets_status_created — для сортировки тикетов по статусу+дате
    """
    indexes = [
        # Для проверки дублей по телефону
        ("idx_leads_phone", "leads", "phone"),
        # Для проверки дублей по компании
        ("idx_leads_company_name", "leads", "company_name"),
        # Составной для получения менеджеров/админов по роли+статусу
        ("idx_users_role_status", "users", "role, status"),
        # Составной для тикетов — сортировка по статусу + дате
        ("idx_tickets_status_created", "tickets", "status, created_at DESC"),
    ]

    for idx_name, table_name, columns in indexes:
        try:
            check_query = text(
                f"SELECT name FROM sqlite_master WHERE type='index' AND name='{idx_name}'"
            )
            result = await conn.execute(check_query)
            existing = result.fetchone()

            if existing:
                logger.debug(f"Индекс {idx_name} уже существует")
                continue

            create_query = text(
                f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name} ({columns})"
            )
            await conn.execute(create_query)
            logger.info(f"✅ Создан индекс: {idx_name} на {table_name}({columns})")

        except Exception as e:
            logger.error(f"❌ Ошибка создания индекса {idx_name}: {e}")
            continue

    logger.info("🎉 Миграция v7 успешно применена!")


async def rollback_migration_v7(conn):
    """Откат миграции v7: Удаление составных индексов"""
    indexes_to_drop = [
        "idx_leads_phone",
        "idx_leads_company_name",
        "idx_users_role_status",
        "idx_tickets_status_created",
    ]

    for idx_name in indexes_to_drop:
        try:
            drop_query = text(f"DROP INDEX IF EXISTS {idx_name}")
            await conn.execute(drop_query)
            logger.info(f"✅ Удалён индекс: {idx_name}")
        except Exception as e:
            logger.error(f"❌ Ошибка удаления индекса {idx_name}: {e}")
