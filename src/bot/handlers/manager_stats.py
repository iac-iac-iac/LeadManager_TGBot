"""
Обработчик статистики менеджера

Показывает статистику по дням/неделям/месяцам
"""
from datetime import datetime, timedelta
from typing import Dict, Any

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..states import ManagerStates
from ..messages.texts import MANAGER_STATS
from ..keyboards.keyboard_factory import (
    create_back_keyboard,
    create_manager_main_menu,
)
from ...database import crud
from ...database.models import Lead, LeadStatus
from ...logger import get_logger

logger = get_logger(__name__)

router = Router()


async def get_manager_stats(
    session: AsyncSession,
    telegram_id: str,
    start_date: datetime,
    end_date: datetime
) -> Dict[str, int]:
    """
    Получение статистики менеджера за период
    
    Returns:
        {"assigned": N, "imported": N}
    """
    # Выдано лидов
    assigned_result = await session.execute(
        select(func.count(Lead.id)).where(
            Lead.manager_telegram_id == telegram_id,
            Lead.assigned_at >= start_date,
            Lead.assigned_at <= end_date
        )
    )
    assigned_count = assigned_result.scalar() or 0
    
    # Импортировано лидов
    imported_result = await session.execute(
        select(func.count(Lead.id)).where(
            Lead.manager_telegram_id == telegram_id,
            Lead.imported_at >= start_date,
            Lead.imported_at <= end_date,
            Lead.status == LeadStatus.IMPORTED
        )
    )
    imported_count = imported_result.scalar() or 0
    
    return {"assigned": assigned_count, "imported": imported_count}


@router.callback_query(F.data == "my_stats")
async def handle_my_stats(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Показ статистики менеджера"""
    # Очищаем все предыдущие состояния
    await state.clear()
    
    telegram_id = str(callback.from_user.id)
    
    # Получаем текущую дату (UTC)
    now = datetime.utcnow()
    
    # Начало сегодня
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Начало недели (понедельник)
    days_since_monday = now.weekday()
    week_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Начало месяца
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Получаем статистику за периоды
    today_stats = await get_manager_stats(session, telegram_id, today_start, now)
    week_stats = await get_manager_stats(session, telegram_id, week_start, now)
    month_stats = await get_manager_stats(session, telegram_id, month_start, now)
    
    # Всего импортировано
    total_result = await session.execute(
        select(func.count(Lead.id)).where(
            Lead.manager_telegram_id == telegram_id,
            Lead.status == LeadStatus.IMPORTED
        )
    )
    total_count = total_result.scalar() or 0
    
    # Формируем сообщение с детализацией
    stats_text = (
        f"📊 <b>Ваша статистика</b>\n\n"
        f"📅 <b>Сегодня:</b>\n"
        f"   • Выдано: {today_stats['assigned']}\n"
        f"   • Импортировано: {today_stats['imported']}\n\n"
        f"📅 <b>Эта неделя:</b>\n"
        f"   • Выдано: {week_stats['assigned']}\n"
        f"   • Импортировано: {week_stats['imported']}\n\n"
        f"📅 <b>Этот месяц:</b>\n"
        f"   • Выдано: {month_stats['assigned']}\n"
        f"   • Импортировано: {month_stats['imported']}\n\n"
        f"📈 <b>Всего импортировано:</b> {total_count}"
    )
    
    keyboard = create_back_keyboard("to_main_menu")
    
    await callback.message.answer(
        stats_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    
    await callback.answer()


# =============================================================================
# Возврат в главное меню
# =============================================================================

@router.callback_query(F.data == "to_main_menu")
async def handle_to_main_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    
    await callback.message.answer(
        "🏠 Главное меню",
        reply_markup=create_manager_main_menu()
    )
    
    await callback.answer()


# =============================================================================
# О боте
# =============================================================================

@router.callback_query(F.data == "about")
async def handle_about(callback: CallbackQuery):
    """Информация о боте"""
    about_text = (
        "ℹ️ <b>О боте</b>\n\n"
        "Telegram-бот для раздачи холодных лидов с интеграцией в Bitrix24.\n\n"
        "📌 <b>Возможности:</b>\n"
        "• Импорт лидов из CSV\n"
        "• Проверка на дубли в Bitrix24\n"
        "• Выдача лидов менеджерам (до 200 за раз)\n"
        "• Учёт по сегментам и городам\n"
        "• Статистика по менеджерам\n"
        "• Заморозка сегментов\n\n"
        "👥 <b>Для админов:</b>\n"
        "• Импорт CSV файлов\n"
        "• Проверка дублей\n"
        "• Управление сегментами\n"
        "• Статистика по менеджерам\n"
        "• Экспорт отчётов\n\n"
        "📊 <b>Версия:</b> 2.0"
    )
    
    keyboard = create_back_keyboard("to_main_menu")
    
    await callback.message.answer(
        about_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    
    await callback.answer()
