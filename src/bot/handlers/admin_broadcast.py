"""
Обработчик рассылки сообщений пользователям

Админ может отправить сообщение всем активным пользователям
"""
import asyncio
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from ..states import AdminStates
from ..messages.texts import (
    BROADCAST_INPUT_PROMPT,
    BROADCAST_TOO_LONG,
    BROADCAST_CONFIRM,
    BROADCAST_SUCCESS,
    BROADCAST_CANCELLED,
)
from ..keyboards.keyboard_factory import create_back_keyboard
from ...database import crud
from ...logger import get_logger
from ...utils.html_utils import safe_delete_message

logger = get_logger(__name__)

router = Router()


@router.callback_query(F.data == "admin_broadcast")
async def handle_broadcast_menu(callback: CallbackQuery, state: FSMContext):
    """Меню рассылки"""
    await state.set_state(AdminStates.BROADCAST_INPUT_TEXT)
    
    await callback.message.answer(
        BROADCAST_INPUT_PROMPT,
        parse_mode="HTML"
    )
    
    await callback.answer()


@router.message(AdminStates.BROADCAST_INPUT_TEXT)
async def handle_broadcast_input(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка ввода текста рассылки"""
    text = message.text.strip()
    
    # Проверка длины
    if len(text) > 500:
        await message.answer(BROADCAST_TOO_LONG, parse_mode="HTML")
        return
    
    # Сохраняем текст
    await state.update_data(broadcast_text=text)
    
    # Получаем количество пользователей
    users = await crud.get_all_active_users(session)
    user_count = len(users)
    
    if user_count == 0:
        await message.answer("⚠️ Нет активных пользователей для рассылки")
        await state.clear()
        return
    
    # Показываем подтверждение
    await state.set_state(AdminStates.BROADCAST_CONFIRM)
    await state.update_data(user_count=user_count)
    
    # Клавиатура подтверждения
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Отправить", callback_data="broadcast_confirm")
    builder.button(text="❌ Отмена", callback_data="broadcast_cancel")
    builder.adjust(2)
    
    await message.answer(
        BROADCAST_CONFIRM.format(
            message_text=text[:200] + ("..." if len(text) > 200 else ""),
            user_count=user_count
        ),
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "broadcast_confirm")
async def handle_broadcast_confirm(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Подтверждение рассылки"""
    # Отвечаем сразу
    await callback.answer("⏳ Рассылка запущена...")
    
    # Показываем сообщение о начале
    status_msg = await callback.message.answer("⏳ <b>Рассылка...</b>\n\nЭто может занять несколько минут.")
    
    # Получаем текст
    state_data = await state.get_data()
    text = state_data.get("broadcast_text", "")
    
    if not text:
        await callback.message.answer("⚠️ Текст сообщения не найден")
        await state.clear()
        return
    
    # Получаем пользователей
    users = await crud.get_all_active_users(session)
    
    # Рассылаем с задержками
    sent = 0
    failed = 0
    
    for i, user in enumerate(users, 1):
        try:
            await callback.bot.send_message(
                chat_id=user.telegram_id,
                text=text,
                parse_mode="HTML"
            )
            sent += 1
            
            # Задержка каждые 10 сообщений
            if i % 10 == 0:
                await asyncio.sleep(1)
            else:
                await asyncio.sleep(0.1)
                
        except Exception as e:
            failed += 1
            logger.warning(f"Не удалось отправить пользователю {user.telegram_id}: {e}")
    
    # Удаляем сообщение о начале
    await safe_delete_message(status_msg)
    
    # Показываем результат
    await callback.message.answer(
        BROADCAST_SUCCESS.format(sent=sent, failed=failed),
        reply_markup=create_back_keyboard("admin_menu"),
        parse_mode="HTML"
    )
    
    # Логируем
    logger.info(f"Рассылка завершена: отправлено {sent}, ошибок {failed}")
    
    await state.clear()


@router.callback_query(F.data == "broadcast_cancel")
async def handle_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена рассылки"""
    await callback.message.answer(
        BROADCAST_CANCELLED,
        reply_markup=create_back_keyboard("admin_menu")
    )
    
    await state.clear()
    await callback.answer()


@router.message(StateFilter(AdminStates.BROADCAST_INPUT_TEXT, AdminStates.BROADCAST_CONFIRM), Command("cancel"))
async def handle_broadcast_cancel_command(message: Message, state: FSMContext):
    """Отмена рассылки командой /cancel"""
    await message.answer(
        BROADCAST_CANCELLED,
        reply_markup=create_back_keyboard("admin_menu")
    )
    
    await state.clear()
