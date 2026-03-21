"""
Миграции базы данных

Управление версионированием схемы БД
"""
import importlib.util
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import DatabaseManager, Base

# Импортируем функции миграции v7 из подпапки migrations
# Используем importlib для обхода конфликта имён (migrations.py vs migrations/)
_migrations_dir = Path(__file__).parent / "migrations"
_spec = importlib.util.spec_from_file_location(
    "v7_migration",
    _migrations_dir / "v7_add_critical_indexes.py"
)
_v7_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_v7_module)

migration_v7_add_critical_indexes = _v7_module.migration_v7_add_critical_indexes
rollback_migration_v7 = _v7_module.rollback_migration_v7


# Версия схемы
SCHEMA_VERSION = 7  # Увеличиваем версию для критических индексов


async def run_migrations(db_manager: DatabaseManager):
    """
    Запуск всех миграций

    Args:
        db_manager: Менеджер базы данных
    """
    async with db_manager.engine.begin() as conn:
        # Создаем все таблицы
        await conn.run_sync(Base.metadata.create_all)

        # Создаем таблицу версий миграций
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Получаем список примененных миграций
        result = await conn.execute(text("SELECT version FROM schema_migrations ORDER BY version"))
        applied_versions = [row[0] for row in result.all()]

        # Применяем новые миграции
        max_version = max(applied_versions) if applied_versions else 0

        for version in range(max_version + 1, SCHEMA_VERSION + 1):
            if version not in applied_versions:
                if version == 1:
                    await migration_v1_initial(conn)
                elif version == 2:
                    await migration_v2_add_fields(conn)
                elif version == 3:
                    await migration_v3_add_unique_constraints(conn)
                elif version == 4:
                    await migration_v4_create_segments_table(conn)
                elif version == 5:
                    await migration_v5_create_tickets_table(conn)
                elif version == 6:
                    await migration_v6_create_bot_status_table(conn)
                elif version == 7:
                    await migration_v7_add_critical_indexes(conn)
                    # Записываем версию в таблицу миграций
                    await conn.execute(
                        text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                        {"version": 7}
                    )


async def apply_migration(conn, version: int):
    """
    Применение конкретной миграции

    Args:
        conn: Соединение с БД
        version: Версия миграции
    """
    migrations = {
        1: migration_v1_initial,
        2: migration_v2_add_fields,
        3: migration_v3_add_unique_constraints,
        4: migration_v4_create_segments_table,
        5: migration_v5_create_tickets_table,
        6: migration_v6_create_bot_status_table,
        7: migration_v7_add_critical_indexes,
    }

    if version in migrations:
        await migrations[version](conn)

        # Записываем версию в таблицу миграций (SQLite синтаксис)
        await conn.execute(
            text("INSERT INTO schema_migrations (version) VALUES (:version)"),
            {"version": version}
        )


async def migration_v1_initial(conn):
    """
    Миграция v1: Начальная схема
    
    Создает все таблицы с индексами
    """
    # Таблица уже создана через Base.metadata.create_all
    # Здесь можно добавить дополнительные индексы или триггеры
    
    # Создаем индексы для производительности
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_leads_status_created ON leads(status, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_leads_segment_city ON leads(segment, city)",
        "CREATE INDEX IF NOT EXISTS idx_leads_manager ON leads(manager_telegram_id)",
        "CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)",
        "CREATE INDEX IF NOT EXISTS idx_segment_locks_frozen ON segment_locks(is_frozen)",
        "CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)",
    ]

    for index_sql in indexes:
        await conn.execute(text(index_sql))


async def migration_v2_add_fields(conn):
    """
    Миграция v2: Добавление новых полей в таблицу leads
    
    Добавляет поля:
    - service_type: Тип услуги (ГЦК)
    - stage: Стадия (Новая Заявка)
    - phone_source: Источник телефона
    """
    # Проверяем существование колонок перед добавлением
    # SQLite не поддерживает IF NOT EXISTS для ALTER TABLE ADD COLUMN
    
    try:
        # Пробуем добавить колонки (если уже есть - будет ошибка, которую игнорируем)
        await conn.execute(text("""
            ALTER TABLE leads ADD COLUMN service_type TEXT DEFAULT 'ГЦК'
        """))
    except Exception as e:
        if "duplicate column" not in str(e).lower():
            raise
    
    try:
        await conn.execute(text("""
            ALTER TABLE leads ADD COLUMN stage TEXT DEFAULT 'Новая Заявка'
        """))
    except Exception as e:
        if "duplicate column" not in str(e).lower():
            raise
    
    try:
        await conn.execute(text("""
            ALTER TABLE leads ADD COLUMN phone_source TEXT
        """))
    except Exception as e:
        if "duplicate column" not in str(e).lower():
            raise
    
    # Записываем версию миграции
    await conn.execute(text("INSERT INTO schema_migrations (version) VALUES (2)"))


async def migration_v3_add_unique_constraints(conn):
    """
    Миграция v3: Добавление уникальных ограничений
    
    Создаёт уникальные индексы для:
    - phone + company_name (предотвращение дублей по телефону)
    - mobile_phone + company_name (предотвращение дублей по мобильному)
    """
    # Создаём уникальные индексы для предотвращения дублей
    # Используем частичные индексы (WHERE IS NOT NULL) для SQLite
    try:
        await conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_unique_phone_company 
            ON leads(phone, company_name)
            WHERE phone IS NOT NULL
        """))
    except Exception as e:
        if "duplicate" not in str(e).lower() and "already exists" not in str(e).lower():
            raise
    
    try:
        await conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_unique_mobile_company 
            ON leads(mobile_phone, company_name)
            WHERE mobile_phone IS NOT NULL
        """))
    except Exception as e:
        if "duplicate" not in str(e).lower() and "already exists" not in str(e).lower():
            raise
    
    # Записываем версию миграции
    await conn.execute(text("INSERT INTO schema_migrations (version) VALUES (3)"))


async def migration_v4_create_segments_table(conn):
    """
    Миграция v4: Создание таблицы segments
    
    Создаёт таблицу для хранения списка сегментов с возможностью управления
    """
    # Создаём таблицу segments
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    
    # Создаём индекс на name
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_segments_name ON segments(name)
    """))
    
    # Заполняем уникальными сегментами из leads
    await conn.execute(text("""
        INSERT OR IGNORE INTO segments (name, description, is_active)
        SELECT DISTINCT segment, NULL, 1
        FROM leads
        WHERE segment IS NOT NULL
        ORDER BY segment
    """))
    
    # Записываем версию миграции
    await conn.execute(text("INSERT INTO schema_migrations (version) VALUES (4)"))


async def migration_v5_create_tickets_table(conn):
    """
    Миграция v5: Создание таблицы tickets

    Создаёт таблицу для обратной связи менеджеров с административным интерфейсом
    """
    # Создаём таблицу tickets
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manager_telegram_id TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            admin_response TEXT,
            responded_at TIMESTAMP,
            resolved_at TIMESTAMP,
            admin_telegram_id TEXT
        )
    """))

    # Создаем индексы для производительности
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)",
        "CREATE INDEX IF NOT EXISTS idx_tickets_manager ON tickets(manager_telegram_id)",
        "CREATE INDEX IF NOT EXISTS idx_tickets_created ON tickets(created_at)",
    ]
    
    for index_sql in indexes:
        await conn.execute(text(index_sql))

    # Записываем версию миграции
    await conn.execute(text("INSERT INTO schema_migrations (version) VALUES (5)"))


async def migration_v6_create_bot_status_table(conn):
    """
    Миграция v6: Создание таблицы bot_status

    Создаёт таблицу для хранения статуса бота (включён/выключен)
    """
    # Создаём таблицу bot_status
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS bot_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL DEFAULT 'running',
            reason TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # Создаём индекс на status
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_bot_status_status ON bot_status(status)
    """))

    # Вставляем запись по умолчанию (бот запущен)
    await conn.execute(text("""
        INSERT OR IGNORE INTO bot_status (id, status, reason)
        VALUES (1, 'running', NULL)
    """))

    # Записываем версию миграции
    await conn.execute(text("INSERT INTO schema_migrations (version) VALUES (6)"))


async def rollback_migration(db_manager: DatabaseManager, target_version: int):
    """
    Откат миграции до указанной версии
    
    Args:
        db_manager: Менеджер базы данных
        target_version: Целевая версия
    """
    # В продакшене здесь был бы код отката
    # Для простоты просто удаляем таблицы и создаем заново
    async with db_manager.engine.begin() as conn:
        await conn.execute(text(f"DELETE FROM schema_migrations WHERE version > {target_version}"))


async def get_migration_status(db_manager: DatabaseManager) -> Tuple[int, bool]:
    """
    Получение статуса миграций
    
    Args:
        db_manager: Менеджер базы данных
        
    Returns:
        (current_version, is_latest)
    """
    async with db_manager.engine.begin() as conn:
        result = await conn.execute(
            text("SELECT MAX(version) FROM schema_migrations")
        )
        row = result.scalar()
        current_version = row if row else 0
        return current_version, current_version >= SCHEMA_VERSION


async def initialize_database(db_manager: DatabaseManager):
    """
    Инициализация базы данных
    
    Args:
        db_manager: Менеджер базы данных
    """
    await run_migrations(db_manager)
    
    # Проверяем статус миграций
    current_version, is_latest = await get_migration_status(db_manager)
    
    if not is_latest:
        raise RuntimeError(
            f"Схема базы данных устарела. Текущая версия: {current_version}, "
            f"требуемая: {SCHEMA_VERSION}"
        )
