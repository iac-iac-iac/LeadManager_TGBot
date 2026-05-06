"""
Обработчики очистки данных (admin)
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from ..messages.texts import (
    CLEANUP_MENU,
    CLEANUP_SUCCESS,
    CLEANUP_FORCE_MENU,
    CLEANUP_FORCE_CONFIRM,
    CLEANUP_FORCE_SUCCESS,
)
from ..keyboards.keyboard_factory import (
    create_cleanup_keyboard,
    create_cleanup_force_period_keyboard,
    create_admin_main_menu,
    parse_callback_data,
)
from ...cleanup.cleanup_service import (
    normalize_cleanup_type,
    run_cleanup,
    run_forced_duplicate_import_cleanup,
)
from ...logger import get_logger

logger = get_logger(__name__)

router = Router()

_FORCE_PERIOD_ALLOWED = frozenset({7, 30, 90, 180, 365})


def create_confirmation_keyboard(confirm_callback: str, cancel_callback: str):
    """Создание клавиатуры подтверждения"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да", callback_data=confirm_callback)
    builder.button(text="❌ Нет", callback_data=cancel_callback)
    builder.adjust(2)
    return builder.as_markup()


def _parse_force_days(callback: CallbackQuery) -> int:
    parsed = parse_callback_data(callback.data)
    params = parsed.get("params") or []
    if not params:
        raise ValueError("Не указан период")
    days = int(params[0])
    if days not in _FORCE_PERIOD_ALLOWED:
        raise ValueError(f"Недопустимый период: {days}")
    return days


@router.callback_query(F.data == "admin_cleanup")
async def handle_cleanup_menu(callback: CallbackQuery):
    """Меню очистки данных"""
    await callback.message.answer(
        CLEANUP_MENU,
        reply_markup=create_cleanup_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "cleanup_force_menu")
async def handle_cleanup_force_menu(callback: CallbackQuery):
    """Меню выбора периода для принудительной очистки DUPLICATE + IMPORTED."""
    await callback.message.answer(
        CLEANUP_FORCE_MENU,
        reply_markup=create_cleanup_force_period_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cleanup_force_yes:"))
async def handle_cleanup_force_confirm(callback: CallbackQuery, session: AsyncSession):
    """Подтверждение принудительной очистки."""
    try:
        days = _parse_force_days(callback)
        stats = await run_forced_duplicate_import_cleanup(session, days)
        dup = stats.get("duplicates", 0)
        imp = stats.get("imported", 0)
        total = dup + imp
        await callback.message.answer(
            CLEANUP_FORCE_SUCCESS.format(duplicates=dup, imported=imp, total=total),
            reply_markup=create_admin_main_menu(),
        )
    except ValueError as e:
        logger.warning("Принудительная очистка: %s", e)
        await callback.message.answer("❌ Некорректный запрос очистки.")
    except Exception as e:
        logger.error(f"Ошибка принудительной очистки: {e}")
        await callback.message.answer("❌ Ошибка при очистке")

    await callback.answer()


@router.callback_query(F.data.startswith("cleanup_force_pick:"))
async def handle_cleanup_force_pick(callback: CallbackQuery):
    """Запрос подтверждения после выбора периода."""
    try:
        days = _parse_force_days(callback)
    except (ValueError, IndexError):
        await callback.answer("Некорректный период", show_alert=True)
        return

    keyboard = create_confirmation_keyboard(
        confirm_callback=f"cleanup_force_yes:{days}",
        cancel_callback="admin_cleanup",
    )
    await callback.message.answer(
        CLEANUP_FORCE_CONFIRM.format(days=days),
        reply_markup=keyboard,
    )
    await callback.answer()


# ВАЖНО: более специфичный фильтр (cleanup_confirm:) должен быть зарегистрирован
# РАНЬШЕ общего (cleanup_), иначе общий перехватит cleanup_confirm:
@router.callback_query(F.data.startswith("cleanup_confirm:"))
async def handle_cleanup_confirm(callback: CallbackQuery, session: AsyncSession):
    """Подтверждение очистки"""
    parsed = parse_callback_data(callback.data)
    raw_type = parsed["params"][0] if parsed["params"] else "all"

    try:
        cleanup_type = normalize_cleanup_type(raw_type)
    except ValueError as e:
        logger.warning("Очистка: %s", e)
        await callback.message.answer("❌ Некорректный тип очистки.")
        await callback.answer()
        return

    try:
        stats = await run_cleanup(session, cleanup_type)
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
async def handle_cleanup_action(callback: CallbackQuery):
    """Действие по очистке — показывает подтверждение"""
    parsed = parse_callback_data(callback.data)
    cleanup_type = parsed["action"]

    keyboard = create_confirmation_keyboard(
        confirm_callback=f"cleanup_confirm:{cleanup_type}",
        cancel_callback="admin_cleanup"
    )

    messages = {
        'cleanup_logs': "🗑 Очистить логи старше 30 дней?",
        'cleanup_duplicates': "🗑 Очистить лиды со статусом DUPLICATE (старше 90 дней)?",
        'cleanup_imported': "🗑 Очистить лиды со статусом IMPORTED (старше 180 дней)?"
    }

    await callback.message.answer(
        messages.get(cleanup_type, "Выполнить очистку?"),
        reply_markup=keyboard
    )

    await callback.answer()
