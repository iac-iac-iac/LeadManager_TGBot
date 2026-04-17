"""
Обработчики проверки дублей (admin)
"""
from typing import Dict

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..messages.texts import (
    DUPLICATE_CHECK_MENU,
    DUPLICATE_CHECK_RESULT,
)
from ..keyboards.keyboard_factory import create_duplicate_check_keyboard
from ...database.models import Lead, LeadStatus
from ...logger import get_logger

logger = get_logger(__name__)

router = Router()


@router.callback_query(F.data == "admin_duplicate_check")
async def handle_duplicate_check_menu(callback: CallbackQuery):
    """Меню проверки дублей"""
    await callback.message.answer(
        DUPLICATE_CHECK_MENU,
        reply_markup=create_duplicate_check_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "duplicate_run")
async def handle_duplicate_run(callback: CallbackQuery, session: AsyncSession):
    """Запуск проверки на дубли (в очереди)"""
    await callback.answer("⏳ Проверка поставлена в очередь...")

    result = await session.execute(
        select(Lead.id).where(Lead.status == LeadStatus.NEW)
    )
    new_lead_ids = [row[0] for row in result.all()]

    if not new_lead_ids:
        await callback.message.answer("ℹ️ Нет новых лидов для проверки.")
        return

    from ...bitrix24.import_queue import get_import_queue
    import_queue = get_import_queue()

    async def duplicate_complete_callback(stats: Dict[str, int]):
        """Уведомление о завершении проверки"""
        try:
            await callback.bot.send_message(
                chat_id=str(callback.from_user.id),
                text=DUPLICATE_CHECK_RESULT.format(
                    duplicates=stats.get('duplicates', 0),
                    unique=stats.get('unique', 0),
                    errors=stats.get('errors', 0)
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления о завершении проверки: {e}")

    queued = await import_queue.add_duplicate_check(
        lead_ids=new_lead_ids,
        callback=duplicate_complete_callback
    )

    if not queued:
        await callback.message.answer("❌ Очередь переполнена, попробуйте позже")
        return

    await callback.message.answer(
        f"✅ <b>Проверка дублей поставлена в очередь!</b>\n\n"
        f"📊 Лидов на проверку: {len(new_lead_ids)}\n"
        f"⏳ Вы получите уведомление когда проверка завершится.",
        parse_mode="HTML"
    )
