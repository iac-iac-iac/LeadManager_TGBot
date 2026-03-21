"""
Обработчики админа: проверка дублей, статистика, заявки, экспорт
"""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..states import AdminStates
from ..messages.texts import (
    DUPLICATE_CHECK_MENU,
    DUPLICATE_CHECK_AUTO_ON,
    DUPLICATE_CHECK_AUTO_OFF,
    DUPLICATE_CHECK_RUNNING,
    DUPLICATE_CHECK_RESULT,
    ADMIN_STATS_MENU,
    ADMIN_STATS_REPORT,
    PENDING_USERS_LIST,
    PENDING_USER_ITEM,
    CLEANUP_MENU,
    CLEANUP_CONFIRM,
    CLEANUP_SUCCESS,
    ADMIN_MAIN_MENU,
)
from ..keyboards.keyboard_factory import (
    create_duplicate_check_keyboard,
    create_stats_period_keyboard,
    create_pending_users_keyboard,
    create_user_action_keyboard,
    create_cleanup_keyboard,
    create_back_keyboard,
    create_admin_main_menu,
    parse_callback_data,
)
from ...database import crud
from ...database.models import Lead, LeadStatus, User, UserStatus
from ...bitrix24.client import Bitrix24Client
from ...bitrix24.duplicates import run_duplicate_check
from ...analytics.reports import get_analytics_report, ReportExporter
from ...cleanup.cleanup_service import run_cleanup
from ...config import get_config
from ...logger import get_logger

logger = get_logger(__name__)

router = Router()


# =============================================================================
# Проверка дублей
# =============================================================================

@router.callback_query(F.data == "admin_duplicate_check")
async def handle_duplicate_check_menu(callback: CallbackQuery):
    """Меню проверки дублей"""
    await callback.message.answer(
        DUPLICATE_CHECK_MENU,
        reply_markup=create_duplicate_check_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "duplicate_run")
async def handle_duplicate_run(callback: CallbackQuery, session: AsyncSession, bitrix24_client: Bitrix24Client):
    """Запуск проверки на дубли"""
    # СРАЗУ отвечаем на callback чтобы не истёк таймаут
    await callback.answer("⏳ Запуск проверки на дубли...")

    # Отправляем сообщение о запуске и запоминаем его ID
    status_message = await callback.message.answer(DUPLICATE_CHECK_RUNNING)

    # Получаем все NEW лиды
    result = await session.execute(
        select(Lead.id).where(Lead.status == LeadStatus.NEW)
    )
    new_lead_ids = [row[0] for row in result.all()]

    if not new_lead_ids:
        await status_message.edit_text("ℹ️ Нет новых лидов для проверки.")
        return

    # Запускаем проверку с уведомлениями в Telegram
    stats = await run_duplicate_check(
        session,
        bitrix24_client,
        lead_ids=new_lead_ids,
        bot=callback.bot,
        admin_chat_id=str(callback.from_user.id)  # Отправляем тому кто запустил
    )

    await session.commit()

    # Удаляем сообщение о запуске (если ещё не удалено)
    try:
        await status_message.delete()
    except Exception:
        pass

    # Показываем результат
    await callback.message.answer(
        DUPLICATE_CHECK_RESULT.format(
            duplicates=stats.get('duplicates', 0),
            unique=stats.get('unique', 0),
            errors=stats.get('errors', 0)
        )
    )


# =============================================================================
# Статистика
# =============================================================================

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
    period = parsed["action"]  # today, week, month, all
    
    # Получаем отчёт
    report = await get_analytics_report(session, period)
    
    stats = report['stats']
    segment_stats = report['segment_stats']
    manager_stats = report['manager_stats']
    
    # Формируем текст по сегментам
    segments_text = "\n".join([
        f"  {seg}: {data['imported']}"
        for seg, data in segment_stats.items()
    ]) or "  Нет данных"
    
    # Формируем текст по менеджерам
    managers_text = "\n".join([
        f"  {data['full_name']}: {data['imported']}"
        for data in manager_stats.values()
    ]) or "  Нет данных"
    
    # Период текстом
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


# =============================================================================
# Экспорт отчётов
# =============================================================================

@router.callback_query(F.data == "admin_export")
async def handle_admin_export(callback: CallbackQuery, session: AsyncSession):
    """Экспорт отчёта в CSV"""
    from src.analytics.reports import AnalyticsService, ReportExporter
    
    config = get_config()

    # Генерируем имя файла
    now = datetime.utcnow()
    filename = f"report_{now.strftime('%Y%m%d_%H%M%S')}.csv"
    output_path = config.uploads_folder / filename

    # Получаем данные за месяц
    end_date = now
    start_date = now - timedelta(days=30)

    try:
        # Создаём сервис аналитики и экспортёр
        analytics = AnalyticsService(session)
        exporter = ReportExporter(analytics)
        await exporter.export_stats_to_csv(output_path, start_date, end_date)

        # Отправляем файл
        file = FSInputFile(output_path)
        await callback.message.answer_document(
            document=file,
            caption=f"📊 Отчёт за последние 30 дней\n{filename}"
        )

    except Exception as e:
        logger.error(f"Ошибка экспорта отчёта: {e}")
        await callback.message.answer("❌ Ошибка при экспорте отчёта")

    await callback.answer()


# =============================================================================
# Заявки менеджеров
# =============================================================================

@router.callback_query(F.data == "admin_pending_users")
async def handle_pending_users_menu(callback: CallbackQuery, session: AsyncSession):
    """Список заявок на подтверждение"""
    # Получаем все заявки
    pending_users = await crud.get_pending_users(session)
    
    if not pending_users:
        await callback.message.answer("ℹ️ Нет ожидающих заявок.")
        await callback.answer()
        return
    
    # Формируем список
    users_data = [
        {"telegram_id": u.telegram_id, "full_name": u.full_name}
        for u in pending_users
    ]
    
    keyboard = create_pending_users_keyboard(users_data)
    
    users_text = "\n".join([
        PENDING_USER_ITEM.format(
            full_name=u.full_name,
            telegram=u.telegram_id,
            telegram_id=u.telegram_id
        )
        for u in pending_users
    ])
    
    await callback.message.answer(
        PENDING_USERS_LIST.format(users=users_text),
        reply_markup=keyboard
    )
    
    await callback.answer()


@router.callback_query(F.data.startswith("user_view:"))
async def handle_user_view(callback: CallbackQuery, session: AsyncSession):
    """Просмотр заявки пользователя"""
    parsed = parse_callback_data(callback.data)
    telegram_id = parsed["params"][0]
    
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    keyboard = create_user_action_keyboard(telegram_id)
    
    await callback.message.answer(
        f"👤 Заявка\n\n"
        f"ФИО: {user.full_name}\n"
        f"Telegram: @{user.username or user.telegram_id}\n"
        f"ID: {user.telegram_id}\n"
        f"Дата регистрации: {user.registered_at.strftime('%Y-%m-%d %H:%M') if user.registered_at else 'N/A'}",
        reply_markup=keyboard
    )
    
    await callback.answer()


@router.callback_query(F.data.startswith("user_approve:"))
async def handle_user_approve(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Подтверждение пользователя - запрос Bitrix24 ID"""
    parsed = parse_callback_data(callback.data)
    telegram_id = parsed["params"][0]

    user = await crud.get_user_by_telegram_id(session, telegram_id)

    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    # Сохраняем ID менеджера в состоянии
    await state.update_data(pending_manager_telegram_id=telegram_id)
    await state.set_state(AdminStates.APPROVE_USER_BITRIX_ID)

    await callback.message.answer(
        f"👤 Подтверждение менеджера: {user.full_name}\n\n"
        f"Введите ID пользователя в Bitrix24:\n"
        f"(Найдите пользователя в Bitrix24 и скопируйте ID из URL профиля)\n\n"
        f"Или отправьте '0' если не нужно привязывать."
    )

    await callback.answer()


@router.message(StateFilter(AdminStates.APPROVE_USER_BITRIX_ID))
async def handle_bitrix_id_input(message: Message, state: FSMContext, session: AsyncSession):
    """Ввод Bitrix24 ID для подтверждения менеджера"""
    try:
        bitrix24_user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "⚠️ Пожалуйста, введите числовое значение ID.\n"
            "Или отправьте '0' если не нужно привязывать."
        )
        return

    # Получаем данные из состояния
    state_data = await state.get_data()
    telegram_id = state_data.get("pending_manager_telegram_id")

    if not telegram_id:
        await message.answer("❌ Ошибка: данные не найдены. Начните заново.")
        await state.clear()
        return

    # Подтверждаем с указанным Bitrix24 ID
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    if not user:
        await message.answer("❌ Пользователь не найден.")
        await state.clear()
        return

    await crud.approve_user(session, telegram_id, bitrix24_user_id=bitrix24_user_id if bitrix24_user_id > 0 else None)
    await session.commit()

    await message.answer(
        f"✅ Менеджер {user.full_name} подтверждён!\n"
        f"Bitrix24 ID: {bitrix24_user_id if bitrix24_user_id > 0 else 'не привязан'}"
    )

    # Отправляем уведомление менеджеру
    try:
        await message.bot.send_message(
            chat_id=telegram_id,
            text=(
                f"✅ Ваша заявка подтверждена!\n\n"
                f"Теперь вы можете получать лиды через бота.\n"
                f"Нажмите '📋 Получить лиды' для начала работы."
            )
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление менеджеру {telegram_id}: {e}")

    await state.clear()


@router.callback_query(F.data.startswith("user_reject:"))
async def handle_user_reject(callback: CallbackQuery, session: AsyncSession):
    """Отклонение пользователя"""
    parsed = parse_callback_data(callback.data)
    telegram_id = parsed["params"][0]
    
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    # Отклоняем
    await crud.reject_user(session, telegram_id)
    await session.commit()
    
    await callback.message.answer(
        PENDING_USER_REJECT_SUCCESS.format(full_name=user.full_name)
    )
    
    await callback.answer()


# =============================================================================
# Очистка данных
# =============================================================================

@router.callback_query(F.data == "admin_cleanup")
async def handle_cleanup_menu(callback: CallbackQuery):
    """Меню очистки данных"""
    await callback.message.answer(
        CLEANUP_MENU,
        reply_markup=create_cleanup_keyboard()
    )
    await callback.answer()


# ✅ ВАЖНО: Сначала более специфичный роутер (cleanup_confirm:), потом общий (cleanup_)
# Иначе cleanup_ перехватит cleanup_confirm:

@router.callback_query(F.data.startswith("cleanup_confirm:"))
async def handle_cleanup_confirm(callback: CallbackQuery, session: AsyncSession):
    """Подтверждение очистки"""
    parsed = parse_callback_data(callback.data)
    cleanup_type = parsed["params"][0] if parsed["params"] else parsed.get("action", "all")

    try:
        stats = await run_cleanup(session, cleanup_type)

        # Flush перед commit для применения DELETE запросов
        await session.flush()
        await session.commit()

        count = sum(stats.values())

        await callback.message.answer(
            CLEANUP_SUCCESS.format(count=count),
            reply_markup=create_admin_main_menu()
        )

    except Exception as e:
        logger.error(f"Ошибка очистки: {e}")
        await callback.message.answer("❌ Ошибка при очистке")

    await callback.answer()


@router.callback_query(F.data.startswith("cleanup_"))
async def handle_cleanup_action(callback: CallbackQuery, session: AsyncSession):
    """Действие по очистке"""
    parsed = parse_callback_data(callback.data)
    cleanup_type = parsed["action"]  # logs, duplicates, imported

    # Показываем подтверждение
    keyboard = create_confirmation_keyboard(
        confirm_callback=f"cleanup_confirm:{cleanup_type}",
        cancel_callback="admin_cleanup"
    )

    messages = {
        'logs': "🗑 Очистить логи старше 30 дней?",
        'duplicates': "🗑 Очистить лиды со статусом DUPLICATE (старше 90 дней)?",
        'imported': "🗑 Очистить лиды со статусом IMPORTED (старше 180 дней)?"
    }

    await callback.message.answer(
        messages.get(cleanup_type, "Выполнить очистку?"),
        reply_markup=keyboard
    )

    await callback.answer()


def create_confirmation_keyboard(confirm_callback: str, cancel_callback: str):
    """Создание клавиатуры подтверждения"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да", callback_data=confirm_callback)
    builder.button(text="❌ Нет", callback_data=cancel_callback)
    builder.adjust(2)
    return builder.as_markup()


# =============================================================================
# Статистика по менеджерам
# =============================================================================

@router.callback_query(F.data == "admin_manager_stats")
async def handle_manager_stats_menu(callback: CallbackQuery, session: AsyncSession):
    """Меню статистики по менеджерам"""
    from sqlalchemy import select
    from ...database.models import User, UserRole, UserStatus
    
    # Получаем всех активных менеджеров
    result = await session.execute(
        select(User).where(
            User.role == UserRole.MANAGER,
            User.status == UserStatus.ACTIVE
        ).order_by(User.full_name)
    )
    managers = result.scalars().all()
    
    if not managers:
        await callback.message.answer("ℹ️ Нет активных менеджеров")
        await callback.answer()
        return
    
    # Формируем список с краткой статистикой
    from sqlalchemy import func
    from ...database.models import Lead
    
    managers_text = "👥 <b>Менеджеры:</b>\n\n"
    
    for manager in managers:
        # Считаем количество импортированных лидов
        count_result = await session.execute(
            select(func.count(Lead.id)).where(
                Lead.manager_telegram_id == manager.telegram_id,
                Lead.status == LeadStatus.IMPORTED
            )
        )
        count = count_result.scalar() or 0
        
        managers_text += f"• {manager.full_name} — {count} лидов\n"
    
    # Создаём клавиатуру с менеджерами
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    
    for manager in managers:
        builder.button(
            text=f"👤 {manager.full_name}",
            callback_data=f"manager_detail:{manager.telegram_id}"
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
async def handle_manager_detail(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Детальная статистика по менеджеру"""
    from sqlalchemy import select, func
    from ...database.models import User, UserRole, UserStatus, Lead
    from datetime import datetime, timedelta
    
    parsed = parse_callback_data(callback.data)
    
    if not parsed["params"]:
        await callback.answer("⚠️ Ошибка", show_alert=True)
        return
    
    telegram_id = parsed["params"][0]
    
    # Получаем менеджера
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    
    if not user or user.role != UserRole.MANAGER:
        await callback.answer("❌ Менеджер не найден", show_alert=True)
        return
    
    # Получаем текущую дату
    now = datetime.utcnow()
    
    # Периоды
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    days_since_monday = now.weekday()
    week_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    half_year_start = now - timedelta(days=180)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Функция для получения статистики
    async def get_period_stats(start: datetime, end: datetime = None) -> Dict[str, int]:
        query = select(func.count(Lead.id)).where(
            Lead.manager_telegram_id == telegram_id,
            Lead.assigned_at >= start
        )
        if end:
            query = query.where(Lead.assigned_at <= end)
        
        result = await session.execute(query)
        return result.scalar() or 0
    
    # Получаем статистику по периодам
    today = await get_period_stats(today_start, now)
    week = await get_period_stats(week_start, now)
    month = await get_period_stats(month_start, now)
    half_year = await get_period_stats(half_year_start, now)
    year = await get_period_stats(year_start, now)
    
    # Всего импортировано
    total_result = await session.execute(
        select(func.count(Lead.id)).where(
            Lead.manager_telegram_id == telegram_id,
            Lead.status == LeadStatus.IMPORTED
        )
    )
    total = total_result.scalar() or 0
    
    # Получаем статистику по сегментам
    segment_result = await session.execute(
        select(Lead.segment, func.count(Lead.id)).where(
            Lead.manager_telegram_id == telegram_id,
            Lead.status == LeadStatus.IMPORTED
        ).group_by(Lead.segment)
    )
    segments = segment_result.all()
    
    # Формируем отчёт
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
        for segment, count in segments[:10]:  # ТОП-10 сегментов
            stats_text += f"  • {segment}: {count}\n"
    
    # Сохраняем для экспорта
    await state.update_data(
        selected_manager_id=telegram_id,
        selected_manager_name=user.full_name
    )
    
    # Клавиатура
    from aiogram.utils.keyboard import InlineKeyboardBuilder
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


# =============================================================================
# Экспорт статистики менеджера
# =============================================================================

@router.callback_query(F.data.startswith("export_manager:"))
async def handle_export_manager_stats(callback: CallbackQuery, session: AsyncSession):
    """Экспорт статистики менеджера в CSV"""
    import csv
    import io
    from datetime import datetime, timedelta
    from sqlalchemy import select, func
    from ...database.models import Lead, User
    from aiogram.types import FSInputFile
    
    parsed = parse_callback_data(callback.data)
    
    if not parsed["params"]:
        await callback.answer("⚠️ Ошибка", show_alert=True)
        return
    
    telegram_id = parsed["params"][0]
    
    # Получаем менеджера
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    
    if not user:
        await callback.answer("❌ Менеджер не найден", show_alert=True)
        return
    
    # Получаем все импортированные лиды менеджера
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
    
    # Создаём CSV в памяти с UTF-8 кодировкой
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
    
    # Сохраняем файл с UTF-8 BOM для Excel
    import os
    filename = f"stats_{user.full_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv"
    filepath = f"uploads/{filename}"
    
    # Создаём папку если нет
    os.makedirs("uploads", exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8-sig') as f:
        f.write(output.getvalue())
    
    # Отправляем файл
    await callback.message.answer(
        f"📊 Статистика по менеджеру: {user.full_name}\n"
        f"📁 Лидов: {len(leads)}\n\n"
        f"Файл: {filename}"
    )
    
    csv_file = FSInputFile(filepath)
    await callback.message.answer_document(csv_file)
    
    await callback.answer()
