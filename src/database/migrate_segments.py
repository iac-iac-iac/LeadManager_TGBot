"""
Скрипт миграции сегментов из поля phone_source

Назначение:
- Обновление поля segment у существующих лидов на основе поля phone_source
- Использует функцию extract_segment_from_phone_source() из csv_importer
- Логирование процесса миграции

Формат phone_source: "название сегмента!остальные данные"
Пример: "быстровозводимые здания!СБП_КраснЯр_Казань__2026-03-18_14_17_02.json"

Использование:
    python -m src.database.migrate_segments

Или через скрипт:
    python scripts/migrate_segments.py
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Tuple

# Добавляем корень проекта в path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Lead, Base
from src.csv_import.csv_importer import extract_segment_from_phone_source, extract_segment_from_lead_title
from src.logger import get_logger

logger = get_logger(__name__)


async def migrate_segments(database_path: str, batch_size: int = 100) -> Tuple[int, int, int]:
    """
    Миграция сегментов из поля phone_source

    Args:
        database_path: Путь к файлу БД SQLite
        batch_size: Размер пакета для обновления

    Returns:
        (всего лидов, обновлено, ошибок)
    """
    # Создаем движок и сессию
    database_url = f"sqlite+aiosqlite:///{database_path}"
    engine = create_async_engine(database_url, echo=False)
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    total_count = 0
    updated_count = 0
    error_count = 0

    try:
        async with engine.begin() as conn:
            # Проверяем существование таблицы
            result = await conn.execute(
                select(func.count(Lead.id))
            )
            total_count = result.scalar() or 0

        logger.info(f"Начало миграции сегментов. Всего лидов: {total_count}")

        # Получаем все лиды с phone_source
        offset = 0
        while True:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(Lead)
                    .where(Lead.phone_source.isnot(None))
                    .order_by(Lead.id)
                    .offset(offset)
                    .limit(batch_size)
                )
                leads = result.scalars().all()

                if not leads:
                    break

                # Обновляем сегменты в этом пакете
                for lead in leads:
                    try:
                        # Извлекаем сегмент из phone_source
                        new_segment = extract_segment_from_phone_source(
                            lead.phone_source,
                            fallback_segment=extract_segment_from_lead_title(lead.lead_title) if lead.lead_title else None
                        )

                        # Обновляем только если сегмент изменился
                        if new_segment != lead.segment:
                            old_segment = lead.segment
                            lead.segment = new_segment

                            logger.debug(
                                f"Лид #{lead.id}: сегмент обновлён '{old_segment}' → '{new_segment}' "
                                f"(phone_source: {lead.phone_source[:50]}...)"
                            )
                            updated_count += 1

                    except Exception as e:
                        logger.error(f"Ошибка обработки лида #{lead.id}: {e}")
                        error_count += 1

                # Коммитим пакет
                await session.commit()
                offset += batch_size

                logger.info(f"Обработано {min(offset, total_count)} из {total_count} лидов")

        logger.info(f"Миграция завершена. Обновлён {updated_count} лидов из {total_count}")
        return total_count, updated_count, error_count

    except Exception as e:
        logger.error(f"Критическая ошибка миграции: {e}")
        return total_count, updated_count, error_count + 1

    finally:
        await engine.dispose()


async def migrate_segments_dry_run(database_path: str, sample_size: int = 20) -> None:
    """
    Тестовый запуск миграции (без записи)

    Показывает примеры изменений для первых sample_size лидов

    Args:
        database_path: Путь к файлу БД
        sample_size: Количество примеров для показа
    """
    database_url = f"sqlite+aiosqlite:///{database_path}"
    engine = create_async_engine(database_url, echo=False)
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    logger.info("=" * 80)
    logger.info("ТЕСТОВЫЙ ЗАПУСК МИГРАЦИИ (без записи)")
    logger.info("=" * 80)

    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Lead)
                .where(Lead.phone_source.isnot(None))
                .order_by(Lead.id)
                .limit(sample_size)
            )
            leads = result.scalars().all()

            if not leads:
                logger.warning("Лиды с phone_source не найдены")
                return

            logger.info(f"Найдено лидов с phone_source: {len(leads)} (показываем первые {sample_size})")

            changes = []
            for lead in leads:
                new_segment = extract_segment_from_phone_source(
                    lead.phone_source,
                    fallback_segment=extract_segment_from_lead_title(lead.lead_title) if lead.lead_title else None
                )

                if new_segment != lead.segment:
                    changes.append({
                        "id": lead.id,
                        "old": lead.segment,
                        "new": new_segment,
                        "phone_source": lead.phone_source[:60] if lead.phone_source else None,
                        "lead_title": lead.lead_title[:40] if lead.lead_title else None
                    })

            if changes:
                logger.info(f"Будет обновлено {len(changes)} лидов из {len(leads)}:")
                for i, change in enumerate(changes, 1):
                    logger.info(
                        f"{i}. Лид #{change['id']}: '{change['old']}' → '{change['new']}' "
                        f"(phone_source: {change['phone_source']}...)"
                    )
            else:
                logger.info("Изменений не требуется (все сегменты уже корректны)")

    finally:
        await engine.dispose()


async def main():
    """Точка входа скрипта миграции"""
    from src.config import load_config

    config = load_config()
    database_path = config.database_path

    logger.info("=" * 80)
    logger.info("МИГРАЦИЯ СЕГМЕНТОВ ИЗ phone_source")
    logger.info("=" * 80)
    logger.info(f"База данных: {database_path}")

    # Проверяем существование БД
    if not Path(database_path).exists():
        logger.error(f"База данных не найдена: {database_path}")
        sys.exit(1)

    # Тестовый запуск
    logger.info("Выполняю тестовый запуск...")
    await migrate_segments_dry_run(database_path)

    # Подтверждение (используем input для интерактивности)
    print("\n" + "=" * 80)  # Оставляем print для интерактивного ввода
    response = input("\nЗапустить миграцию? (yes/no): ").strip().lower()

    if response not in ["yes", "y"]:
        logger.info("Миграция отменена пользователем")
        print("\n❌ Миграция отменена")  # Оставляем print
        sys.exit(0)

    # Запуск миграции
    logger.info("Выполняю миграцию...")
    total, updated, errors = await migrate_segments(database_path)

    # Результаты
    logger.info("=" * 80)
    logger.info("РЕЗУЛЬТАТЫ МИГРАЦИИ")
    logger.info("=" * 80)
    logger.info(f"Всего лидов: {total}")
    logger.info(f"Обновлено: {updated}")
    logger.info(f"Ошибок: {errors}")
    
    if total > 0:
        logger.info(f"Процент обновления: {updated / total * 100:.1f}%")

    if errors > 0:
        logger.warning("Проверьте логи для деталей об ошибках")

    logger.info("=" * 80)
    
    # Вывод результатов для пользователя
    print("\n" + "=" * 80)
    print("РЕЗУЛЬТАТЫ МИГРАЦИИ")
    print("=" * 80)
    print(f"\n✅ Всего лидов:     {total}")
    print(f"✅ Обновлённо:      {updated}")
    print(f"❌ Ошибок:          {errors}")
    if total > 0:
        print(f"\n📊 Процент обновления: {updated / total * 100:.1f}%")

    if errors > 0:
        print(f"\n⚠️ Проверьте логи для деталей об ошибках")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
