"""
Обработчики заявок на регистрацию менеджеров (admin)
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from ..states import AdminStates
from ..messages.texts import (
    PENDING_USERS_LIST,
    PENDING_USER_ITEM,
)
from ..keyboards.keyboard_factory import (
    create_pending_users_keyboard,
    create_user_action_keyboard,
    parse_callback_data,
)
from ...database import crud
from ...database.models import UserRole
from ...logger import get_logger
from ...utils.html_utils import format_html_safe

logger = get_logger(__name__)

router = Router()

PENDING_USER_REJECT_SUCCESS = "❌ Заявка <b>{full_name}</b> отклонена."


@router.callback_query(F.data == "admin_pending_users")
async def handle_pending_users_menu(callback: CallbackQuery, session: AsyncSession):
    """Список заявок на подтверждение"""
    pending_users = await crud.get_pending_users(session)

    if not pending_users:
        await callback.message.answer("ℹ️ Нет ожидающих заявок.")
        await callback.answer()
        return

    users_data = [
        {"telegram_id": u.telegram_id, "full_name": u.full_name}
        for u in pending_users
    ]

    keyboard = create_pending_users_keyboard(users_data)

    users_text = "\n".join([
        format_html_safe(
            PENDING_USER_ITEM,
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
    """Подтверждение пользователя — запрос Bitrix24 ID"""
    parsed = parse_callback_data(callback.data)
    telegram_id = parsed["params"][0]

    user = await crud.get_user_by_telegram_id(session, telegram_id)

    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

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

    state_data = await state.get_data()
    telegram_id = state_data.get("pending_manager_telegram_id")

    if not telegram_id:
        await message.answer("❌ Ошибка: данные не найдены. Начните заново.")
        await state.clear()
        return

    user = await crud.get_user_by_telegram_id(session, telegram_id)
    if not user:
        await message.answer("❌ Пользователь не найден.")
        await state.clear()
        return

    await crud.approve_user(
        session, telegram_id,
        bitrix24_user_id=bitrix24_user_id if bitrix24_user_id > 0 else None
    )

    await message.answer(
        f"✅ Менеджер {user.full_name} подтверждён!\n"
        f"Bitrix24 ID: {bitrix24_user_id if bitrix24_user_id > 0 else 'не привязан'}"
    )

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

    await crud.reject_user(session, telegram_id)

    await callback.message.answer(
        format_html_safe(PENDING_USER_REJECT_SUCCESS, full_name=user.full_name)
    )

    await callback.answer()
