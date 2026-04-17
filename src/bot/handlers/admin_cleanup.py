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
)
from ..keyboards.keyboard_factory import (
    create_cleanup_keyboard,
    create_admin_main_menu,
    parse_callback_data,
)
from ...cleanup.cleanup_service import run_cleanup
from ...logger import get_logger

logger = get_logger(__name__)

router = Router()


def create_confirmation_keyboard(confirm_callback: str, cancel_callback: str):
    """Создание клавиатуры подтверждения"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да", callback_data=confirm_callback)
    builder.button(text="❌ Нет", callback_data=cancel_callback)
    builder.adjust(2)
    return builder.as_markup()


@router.callback_query(F.data == "admin_cleanup")
async def handle_cleanup_menu(callback: CallbackQuery):
    """Меню очистки данных"""
    await callback.message.answer(
        CLEANUP_MENU,
        reply_markup=create_cleanup_keyboard()
    )
    await callback.answer()


# ВАЖНО: более специфичный фильтр (cleanup_confirm:) должен быть зарегистрирован
# РАНЬШЕ общего (cleanup_), иначе общий перехватит cleanup_confirm:
@router.callback_query(F.data.startswith("cleanup_confirm:"))
async def handle_cleanup_confirm(callback: CallbackQuery, session: AsyncSession):
    """Подтверждение очистки"""
    parsed = parse_callback_data(callback.data)
    cleanup_type = parsed["params"][0] if parsed["params"] else parsed.get("action", "all")

    try:
        stats = await run_cleanup(session, cleanup_type)
        await session.flush()

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
    """Действие по очистке — показывает подтверждение"""
    parsed = parse_callback_data(callback.data)
    cleanup_type = parsed["action"]

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
