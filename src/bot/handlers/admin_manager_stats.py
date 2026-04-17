"""
Обработчики статистики по менеджерам и экспорта (admin)

Содержит оптимизированные запросы (без N+1) для статистики менеджеров.
"""
import csv
import io
import os
from datetime import datetime, timedelta
from typing import Dict

from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..keyboards.keyboard_factory import parse_callback_data
from ...database import crud
from ...database.models import Lead, LeadStatus, User, UserRole, UserStatus
from ...logger import get_logger

logger = get_logger(__name__)

router = Router()


@router.callback_query(F.data == "admin_manager_stats")
async def handle_manager_stats_menu(callback: CallbackQuery, session: AsyncSession):
    """Меню статистики по менеджерам (один агрегирующий запрос — нет N+1)"""
    managers = await crud.get_active_managers_with_stats(session)

    if not managers:
        await callback.message.answer("ℹ️ Нет активных менеджеров")
        await callback.answer()
        return

    managers_text = "👥 <b>Менеджеры:</b>\n\n"
    for m in managers:
        managers_text += f"• {m['full_name']} — {m['leads_count']} лидов\n"

    builder = InlineKeyboardBuilder()
    for m in managers:
        builder.button(
            text=f"👤 {m['full_name']}",
            callback_data=f"manager_detail:{m['telegram_id']}"
        )
    builder.adjust(1)
    builder.button(text="⬅️ Назад", callback_data="admin_menu")

    await callback.message.answer(
        managers_text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


@router.callback_query(F.data.startswith("manager_detail:"))
async def handle_manager_detail(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext
):
    """Детальная статистика по менеджеру"""
    parsed = parse_callback_data(callback.data)

    if not parsed["params"]:
        await callback.answer("⚠️ Ошибка", show_alert=True)
        return

    telegram_id = parsed["params"][0]

    user = await crud.get_user_by_telegram_id(session, telegram_id)

    if not user or user.role != UserRole.MANAGER:
        await callback.answer("❌ Менеджер не найден", show_alert=True)
        return

    now = datetime.utcnow()

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    half_year_start = now - timedelta(days=180)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    async def get_period_stats(start: datetime, end: datetime = None) -> int:
        query = select(func.count(Lead.id)).where(
            Lead.manager_telegram_id == telegram_id,
            Lead.assigned_at >= start
        )
        if end:
            query = query.where(Lead.assigned_at <= end)
        result = await session.execute(query)
        return result.scalar() or 0

    today = await get_period_stats(today_start, now)
    week = await get_period_stats(week_start, now)
    month = await get_period_stats(month_start, now)
    half_year = await get_period_stats(half_year_start, now)
    year = await get_period_stats(year_start, now)

    total_result = await session.execute(
        select(func.count(Lead.id)).where(
            Lead.manager_telegram_id == telegram_id,
            Lead.status == LeadStatus.IMPORTED
        )
    )
    total = total_result.scalar() or 0

    segment_result = await session.execute(
        select(Lead.segment, func.count(Lead.id)).where(
            Lead.manager_telegram_id == telegram_id,
            Lead.status == LeadStatus.IMPORTED
        ).group_by(Lead.segment)
    )
    segments = segment_result.all()

    stats_text = (
        f"👤 <b>{user.full_name}</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• За день: {today} лидов\n"
        f"• За неделю: {week} лидов\n"
        f"• За месяц: {month} лидов\n"
        f"• За полгода: {half_year} лидов\n"
        f"• За год: {year} лидов\n"
        f"• Всего: {total} лидов\n\n"
    )

    if segments:
        stats_text += "📁 <b>По сегментам:</b>\n"
        for segment, count in segments[:10]:
            stats_text += f"  • {segment}: {count}\n"

    await state.update_data(
        selected_manager_id=telegram_id,
        selected_manager_name=user.full_name
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="📥 Экспорт CSV", callback_data=f"export_manager:{telegram_id}")
    builder.button(text="⬅️ Назад", callback_data="admin_manager_stats")
    builder.adjust(1)

    await callback.message.answer(
        stats_text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


@router.callback_query(F.data.startswith("export_manager:"))
async def handle_export_manager_stats(callback: CallbackQuery, session: AsyncSession):
    """Экспорт статистики менеджера в CSV"""
    parsed = parse_callback_data(callback.data)

    if not parsed["params"]:
        await callback.answer("⚠️ Ошибка", show_alert=True)
        return

    telegram_id = parsed["params"][0]

    user = await crud.get_user_by_telegram_id(session, telegram_id)

    if not user:
        await callback.answer("❌ Менеджер не найден", show_alert=True)
        return

    result = await session.execute(
        select(Lead).where(
            Lead.manager_telegram_id == telegram_id,
            Lead.status == LeadStatus.IMPORTED
        ).order_by(Lead.imported_at.desc())
    )
    leads = result.scalars().all()

    if not leads:
        await callback.answer("ℹ️ Нет лидов для экспорта", show_alert=True)
        return

    output = io.StringIO()
    fieldnames = [
        'ID', 'Компания', 'Сегмент', 'Город', 'Телефон',
        'Дата импорта', 'Тип услуги', 'Источник телефона'
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=';')

    writer.writeheader()
    for lead in leads:
        writer.writerow({
            'ID': lead.id,
            'Компания': lead.company_name or '',
            'Сегмент': lead.segment,
            'Город': lead.city or '',
            'Телефон': lead.phone or '',
            'Дата импорта': lead.imported_at.strftime('%Y-%m-%d %H:%M') if lead.imported_at else '',
            'Тип услуги': lead.service_type or '',
            'Источник телефона': lead.phone_source or ''
        })

    filename = (
        f"stats_{user.full_name.replace(' ', '_')}"
        f"_{datetime.now().strftime('%Y%m%d')}.csv"
    )
    filepath = f"uploads/{filename}"

    os.makedirs("uploads", exist_ok=True)

    with open(filepath, 'w', encoding='utf-8-sig') as f:
        f.write(output.getvalue())

    await callback.message.answer(
        f"📊 Статистика по менеджеру: {user.full_name}\n"
        f"📁 Лидов: {len(leads)}\n\n"
        f"Файл: {filename}"
    )

    csv_file = FSInputFile(filepath)
    await callback.message.answer_document(csv_file)

    await callback.answer()
