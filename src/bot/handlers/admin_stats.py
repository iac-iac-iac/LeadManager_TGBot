"""
Обработчики статистики и экспорта отчётов (admin)
"""
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..messages.texts import (
    ADMIN_STATS_MENU,
    ADMIN_STATS_REPORT,
)
from ..keyboards.keyboard_factory import (
    create_stats_period_keyboard,
    create_back_keyboard,
    parse_callback_data,
)
from ...analytics.reports import get_analytics_report, ReportExporter
from ...config import get_config
from ...logger import get_logger

logger = get_logger(__name__)

router = Router()


@router.callback_query(F.data == "admin_stats")
async def handle_admin_stats_menu(callback: CallbackQuery):
    """Меню статистики"""
    await callback.message.answer(
        ADMIN_STATS_MENU,
        reply_markup=create_stats_period_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("stats_"))
async def handle_stats_period(callback: CallbackQuery, session: AsyncSession):
    """Показ статистики за период"""
    parsed = parse_callback_data(callback.data)
    period = parsed["action"]

    report = await get_analytics_report(session, period)

    stats = report['stats']
    segment_stats = report['segment_stats']
    manager_stats = report['manager_stats']

    segments_text = "\n".join([
        f"  {seg}: {data['imported']}"
        for seg, data in segment_stats.items()
    ]) or "  Нет данных"

    managers_text = "\n".join([
        f"  {data['full_name']}: {data['imported']}"
        for data in manager_stats.values()
    ]) or "  Нет данных"

    period_names = {
        'today': 'Сегодня',
        'week': 'Эту неделю',
        'month': 'Этот месяц',
        'all': 'Всё время'
    }

    await callback.message.answer(
        ADMIN_STATS_REPORT.format(
            period=period_names.get(period, period),
            loaded=stats.get('loaded', 0),
            checked=stats.get('duplicates', 0) + stats.get('unique', 0),
            duplicates=stats.get('duplicates', 0),
            duplicate_percent=stats.get('duplicate_percent', 0),
            unique=stats.get('unique', 0),
            assigned=stats.get('assigned', 0),
            imported=stats.get('imported', 0),
            errors=stats.get('errors', 0),
            segments_stats=segments_text,
            managers_stats=managers_text
        ),
        reply_markup=create_back_keyboard("admin_stats")
    )

    await callback.answer()


@router.callback_query(F.data == "admin_export")
async def handle_admin_export(callback: CallbackQuery, session: AsyncSession):
    """Экспорт отчёта в CSV"""
    from src.analytics.reports import AnalyticsService

    config = get_config()

    now = datetime.utcnow()
    filename = f"report_{now.strftime('%Y%m%d_%H%M%S')}.csv"
    output_path = config.uploads_folder / filename

    end_date = now
    start_date = now - timedelta(days=30)

    try:
        analytics = AnalyticsService(session)
        exporter = ReportExporter(analytics)
        await exporter.export_stats_to_csv(output_path, start_date, end_date)

        file = FSInputFile(output_path)
        await callback.message.answer_document(
            document=file,
            caption=f"📊 Отчёт за последние 30 дней\n{filename}"
        )

    except Exception as e:
        logger.error(f"Ошибка экспорта отчёта: {e}")
        await callback.message.answer("❌ Ошибка при экспорте отчёта")

    await callback.answer()
