"""
Обработчики обратной связи для менеджеров

Отправка тикетов администраторам с идеями/предложениями/жалобами
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from ..states import FeedbackStates
from ..messages.texts import (
    FEEDBACK_BUTTON,
    FEEDBACK_PROMPT,
    FEEDBACK_VALIDATION_ERROR,
    FEEDBACK_TOO_LONG,
    FEEDBACK_CONFIRM_PROMPT,
    FEEDBACK_SUCCESS,
    FEEDBACK_CANCEL,
    FEEDBACK_MY_TICKETS,
    MY_TICKETS_TITLE,
    MY_TICKET_ITEM,
    MY_TICKETS_EMPTY,
    BTN_BACK,
    MANAGER_MAIN_MENU,
)
from ..keyboards.keyboard_factory import (
    create_feedback_confirm_keyboard,
    create_my_tickets_keyboard,
    create_back_keyboard,
)
from ...database import crud
from ...logger import get_logger

logger = get_logger(__name__)

router = Router()


# =============================================================================
# Главное меню: Кнопка обратной связи
# =============================================================================

@router.callback_query(F.data == "feedback_main")
async def start_feedback(callback: CallbackQuery, state: FSMContext):
    """
    Начало отправки обратной связи
    
    Менеджер нажимает кнопку "Обратная связь"
    """
    await state.set_state(FeedbackStates.WAITING_FOR_MESSAGE)
    
    await callback.message.answer(
        FEEDBACK_PROMPT,
        reply_markup=create_back_keyboard("manager_menu")
    )
    
    await callback.answer()


# =============================================================================
# Получение сообщения от менеджера
# =============================================================================

@router.message(FeedbackStates.WAITING_FOR_MESSAGE)
async def process_feedback_message(message: Message, state: FSMContext):
    """
    Обработка текста сообщения от менеджера
    
    Валидация: мин. 10 символов, макс. 1000 символов
    """
    text = message.text.strip()
    
    # Валидация длины
    if len(text) < 10:
        await message.answer(FEEDBACK_VALIDATION_ERROR)
        return
    
    if len(text) > 1000:
        await message.answer(FEEDBACK_TOO_LONG)
        return
    
    # Сохраняем текст в состоянии
    await state.update_data(feedback_message=text)
    
    # Показываем подтверждение
    await message.answer(
        FEEDBACK_CONFIRM_PROMPT.format(message=text),
        reply_markup=create_feedback_confirm_keyboard(text)
    )


# =============================================================================
# Подтверждение отправки
# =============================================================================

@router.callback_query(F.data.startswith("feedback_confirm:"))
async def confirm_feedback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Подтверждение отправки тикета

    Создание тикета в БД
    """
    try:
        # Получаем сообщение из состояния
        state_data = await state.get_data()
        message_text = state_data.get("feedback_message")

        if not message_text:
            await callback.answer("⚠️ Ошибка: сообщение не найдено", show_alert=True)
            await state.clear()
            return

        # Создаем тикет
        ticket = await crud.create_ticket(
            session,
            manager_telegram_id=str(callback.from_user.id),
            message=message_text
        )

        await session.commit()

        logger.info(f"Создан тикет #{ticket.id} от менеджера {callback.from_user.id}")

        # Отправляем подтверждение менеджеру
        await callback.message.answer(
            FEEDBACK_SUCCESS.format(ticket_id=ticket.id)
        )

        # ОТПРАВЛЯЕМ УВЕДОМЛЕНИЕ АДМИНАМ
        try:
            from ...config import get_config
            config = get_config()
            
            # Получаем ID админов из конфига
            admin_ids = config.admin_telegram_ids
            
            # Формируем сообщение
            manager_name = callback.from_user.full_name or "Неизвестно"
            username = callback.from_user.username or "не указан"
            
            notification_text = f"""
🔔 <b>Новый тикет от менеджера!</b>

🎫 Тикет #{ticket.id}
👤 Менеджер: {manager_name}
📱 Telegram: @{username}
ID: <code>{callback.from_user.id}</code>

📝 Сообщение:
{message_text[:500]}{'...' if len(message_text) > 500 else ''}

Перейдите в '📮 Тикеты' для обработки.
"""
            
            # Отправляем каждому админу
            for admin_id in admin_ids:
                try:
                    await callback.bot.send_message(
                        chat_id=str(admin_id),
                        text=notification_text,
                        parse_mode="HTML"
                    )
                    logger.info(f"Уведомление о тикете #{ticket.id} отправлено админу {admin_id}")
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {e}")
                    
        except Exception as e:
            logger.warning(f"Ошибка отправки уведомления админам: {type(e).__name__}: {e}")

        # Очищаем состояние
        await state.clear()

    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка создания тикета: {type(e).__name__}: {e}")
        await callback.message.answer(
            "⚠️ Произошла ошибка при отправке. Попробуйте позже."
        )

    await callback.answer()


@router.callback_query(F.data == "feedback_cancel")
async def cancel_feedback(callback: CallbackQuery, state: FSMContext):
    """
    Отмена отправки тикета
    """
    await state.clear()
    await callback.message.answer(FEEDBACK_CANCEL)
    await callback.answer()


# =============================================================================
# Мои тикеты
# =============================================================================

@router.callback_query(F.data == "feedback_my_tickets")
async def my_tickets(callback: CallbackQuery, session: AsyncSession):
    """
    Просмотр своих тикетов менеджером
    """
    try:
        telegram_id = str(callback.from_user.id)
        
        # Получаем тикеты менеджера
        tickets = await crud.get_tickets_by_manager(session, telegram_id, limit=10)
        
        if not tickets:
            await callback.message.answer(
                MY_TICKETS_EMPTY,
                reply_markup=create_back_keyboard("manager_menu")
            )
            await callback.answer()
            return
        
        # Формируем сообщение
        tickets_text = MY_TICKETS_TITLE.format(count=len(tickets))
        
        for ticket in tickets:
            status_emoji = "🆕" if ticket.status == "new" else "⏳" if ticket.status == "in_progress" else "✅"
            created_at = ticket.created_at.strftime("%d.%m.%Y %H:%M")
            message_preview = ticket.message[:50] + "..." if len(ticket.message) > 50 else ticket.message
            
            tickets_text += MY_TICKET_ITEM.format(
                id=ticket.id,
                status=status_emoji,
                created_at=created_at,
                message_preview=message_preview
            ) + "\n\n"
        
        await callback.message.answer(
            tickets_text,
            reply_markup=create_my_tickets_keyboard(tickets)
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения тикетов менеджера: {type(e).__name__}: {e}")
        await callback.message.answer("⚠️ Ошибка получения тикетов")
    
    await callback.answer()


@router.callback_query(F.data.startswith("my_ticket_view:"))
async def view_my_ticket(callback: CallbackQuery, session: AsyncSession):
    """
    Просмотр деталей своего тикета
    """
    try:
        parsed = callback.data.split(":")
        ticket_id = int(parsed[1])
        
        ticket = await crud.get_ticket_by_id(session, ticket_id)
        
        if not ticket:
            await callback.answer("⚠️ Тикет не найден", show_alert=True)
            return
        
        # Проверяем, что тикет принадлежит менеджеру
        if ticket.manager_telegram_id != str(callback.from_user.id):
            await callback.answer("⚠️ Доступ запрещён", show_alert=True)
            return
        
        # Формируем сообщение
        status_emoji = "🆕" if ticket.status == "new" else "⏳" if ticket.status == "in_progress" else "✅"
        created_at = ticket.created_at.strftime("%d.%m.%Y %H:%M")
        
        ticket_text = f"""
🎫 Тикет #{ticket.id}

📅 Создан: {created_at}
📝 Сообщение:
{ticket.message}

────────────────
Статус: {status_emoji} {ticket.status}
"""
        
        if ticket.admin_response:
            responded_at = ticket.responded_at.strftime("%d.%m.%Y %H:%M") if ticket.responded_at else "Не указано"
            ticket_text += f"""
────────────────
👨‍💼 Ответ админа:
{ticket.admin_response}

📅 Ответ: {responded_at}
"""
        
        await callback.message.answer(
            ticket_text,
            reply_markup=create_back_keyboard("feedback_my_tickets")
        )

    except Exception as e:
        logger.error(f"Ошибка просмотра тикета: {type(e).__name__}: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)

    await callback.answer()


# =============================================================================
# Обработчик кнопки "Назад" в главное меню
# =============================================================================

@router.callback_query(F.data == "manager_menu")
async def handle_manager_menu(callback: CallbackQuery):
    """
    Возврат в главное меню менеджера
    
    Обрабатывает нажатие кнопки "Назад" из различных меню
    """
    from ..keyboards.keyboard_factory import create_manager_main_menu
    
    await callback.message.answer(
        MANAGER_MAIN_MENU,
        reply_markup=create_manager_main_menu()
    )
    await callback.answer()
