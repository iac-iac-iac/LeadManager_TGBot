"""
Обработчики управления тикетами для админов

Просмотр, фильтрация, ответы на тикеты менеджеров
"""
from typing import Dict, Any
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from ..states import FeedbackStates
from ..messages.texts import (
    TICKETS_BUTTON,
    TICKETS_MENU_TITLE,
    TICKETS_FILTER_ALL,
    TICKETS_FILTER_NEW,
    TICKETS_FILTER_IN_PROGRESS,
    TICKETS_FILTER_RESOLVED,
    TICKETS_EMPTY,
    TICKET_CARD,
    TICKET_CARD_WITH_RESPONSE,
    ADMIN_RESPONSE_PROMPT,
    ADMIN_RESPONSE_SUCCESS,
    TICKET_STATUS_CHANGED,
    BTN_BACK,
)
from ..keyboards.keyboard_factory import (
    create_ticket_filter_keyboard,
    create_tickets_list_keyboard,
    create_ticket_action_keyboard,
    create_back_keyboard,
)
from ...database import crud
from ...logger import get_logger

logger = get_logger(__name__)

router = Router()


# =============================================================================
# Главное меню тикетов
# =============================================================================

@router.callback_query(F.data == "admin_tickets")
async def admin_tickets_menu(callback: CallbackQuery, session: AsyncSession):
    """
    Главное меню управления тикетами
    
    Показывает фильтр по статусам
    """
    try:
        # Получаем статистику
        stats = await crud.get_ticket_stats(session)
        new_count = stats.get("new", 0)
        
        # Формируем текст с количеством новых
        new_text = f" ({new_count})" if new_count > 0 else ""
        
        await callback.message.answer(
            TICKETS_MENU_TITLE + new_text,
            reply_markup=create_ticket_filter_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Ошибка меню тикетов: {type(e).__name__}: {e}")
        await callback.message.answer("⚠️ Ошибка получения тикетов")
    
    await callback.answer()


# =============================================================================
# Фильтрация тикетов
# =============================================================================

@router.callback_query(F.data.startswith("ticket_filter:"))
async def filter_tickets(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Фильтрация тикетов по статусу
    
    Показывает список тикетов с пагинацией
    """
    try:
        # Получаем статус из callback_data
        status = callback.data.split(":")[1]
        
        # Маппинг статусов
        status_map = {
            "all": None,
            "new": "new",
            "in_progress": "in_progress",
            "resolved": "resolved"
        }
        
        filter_status = status_map.get(status)
        
        # Сохраняем текущий фильтр в состоянии
        await state.update_data(ticket_filter=filter_status, ticket_page=0)
        
        # Получаем тикеты
        await show_tickets_page(callback, session, state, 0)
        
    except Exception as e:
        logger.error(f"Ошибка фильтрации тикетов: {type(e).__name__}: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)
    
    await callback.answer()


# =============================================================================
# Пагинация тикетов
# =============================================================================

@router.callback_query(F.data.startswith("ticket_page:"))
async def paginate_tickets(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Переключение страницы списка тикетов
    """
    try:
        # Получаем номер страницы
        page = int(callback.data.split(":")[1])
        
        # Показываем страницу
        await show_tickets_page(callback, session, state, page)
        
    except Exception as e:
        logger.error(f"Ошибка пагинации тикетов: {type(e).__name__}: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)
    
    await callback.answer()


async def show_tickets_page(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    page: int
):
    """
    Показ страницы списка тикетов
    
    Args:
        callback: CallbackQuery
        session: Сессия БД
        state: FSM состояние
        page: Номер страницы (0-based)
    """
    # Получаем текущий фильтр из состояния
    state_data = await state.get_data()
    filter_status = state_data.get("ticket_filter")
    
    # Получаем тикеты с пагинацией
    page_size = 20
    tickets, total = await crud.get_tickets_paginated(
        session,
        status=filter_status,
        page=page + 1,  # CRUD использует 1-based
        page_size=page_size
    )
    
    if not tickets:
        await callback.message.answer(
            TICKETS_EMPTY,
            reply_markup=create_back_keyboard("admin_tickets")
        )
        return
    
    # Вычисляем количество страниц
    total_pages = (total + page_size - 1) // page_size
    
    # Показываем клавиатуру
    keyboard = create_tickets_list_keyboard(tickets, page, total_pages)
    
    # Заголовок
    filter_name = filter_status if filter_status else "all"
    header = f"📮 Тикеты (фильтр: {filter_name})\n"
    header += f"Страница {page + 1} из {total_pages}\n\n"
    
    await callback.message.answer(
        header,
        reply_markup=keyboard
    )


# =============================================================================
# Просмотр тикета
# =============================================================================

@router.callback_query(F.data.startswith("ticket_view:"))
async def view_ticket(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Просмотр деталей тикета
    """
    try:
        # Получаем ID тикета
        ticket_id = int(callback.data.split(":")[1])
        
        # Получаем тикет
        ticket = await crud.get_ticket_by_id(session, ticket_id)
        
        if not ticket:
            await callback.answer("⚠️ Тикет не найден", show_alert=True)
            return
        
        # Сохраняем ID в состоянии
        await state.update_data(viewing_ticket_id=ticket_id)
        
        # Получаем имя менеджера
        manager = await crud.get_user_by_telegram_id(session, ticket.manager_telegram_id)
        manager_name = manager.full_name if manager else ticket.manager_telegram_id
        
        # Формируем сообщение
        created_at = ticket.created_at.strftime("%d.%m.%Y %H:%M")
        
        status_map = {
            "new": "🆕 Новый",
            "in_progress": "⏳ В работе",
            "resolved": "✅ Решён",
            "closed": "🔒 Закрыт"
        }
        status_text = status_map.get(ticket.status, ticket.status)
        
        if ticket.admin_response:
            responded_at = ticket.responded_at.strftime("%d.%m.%Y %H:%M") if ticket.responded_at else "Не указано"
            text = TICKET_CARD_WITH_RESPONSE.format(
                id=ticket.id,
                manager_name=manager_name,
                created_at=created_at,
                message=ticket.message,
                admin_response=ticket.admin_response,
                responded_at=responded_at,
                status=status_text
            )
        else:
            text = TICKET_CARD.format(
                id=ticket.id,
                manager_name=manager_name,
                created_at=created_at,
                message=ticket.message,
                status=status_text
            )
        
        # Показываем клавиатуру действий
        keyboard = create_ticket_action_keyboard(ticket_id, ticket.status)

        # Удаляем предыдущее сообщение
        try:
            await callback.message.delete()
        except Exception:
            pass

        await callback.message.answer(
            text,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка просмотра тикета: {type(e).__name__}: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)

    await callback.answer()


# =============================================================================
# Ответ на тикет
# =============================================================================

@router.callback_query(F.data.startswith("ticket_respond:"))
async def start_respond(callback: CallbackQuery, state: FSMContext):
    """
    Начало ответа на тикет
    
    Перевод в состояние ожидания текста ответа
    """
    try:
        # Получаем ID тикета
        ticket_id = int(callback.data.split(":")[1])
        
        # Сохраняем ID в состоянии
        await state.update_data(responding_ticket_id=ticket_id)
        await state.set_state(FeedbackStates.WAITING_FOR_ADMIN_RESPONSE)
        
        await callback.message.answer(ADMIN_RESPONSE_PROMPT)
        
    except Exception as e:
        logger.error(f"Ошибка начала ответа: {type(e).__name__}: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)
    
    await callback.answer()


@router.message(FeedbackStates.WAITING_FOR_ADMIN_RESPONSE)
async def process_admin_response(message: Message, state: FSMContext, session: AsyncSession):
    """
    Обработка ответа админа
    
    Отправка ответа менеджеру и обновление тикета
    """
    try:
        # Получаем ID тикета из состояния
        state_data = await state.get_data()
        ticket_id = state_data.get("responding_ticket_id")
        
        if not ticket_id:
            await message.answer("⚠️ Ошибка: тикет не найден")
            await state.clear()
            return
        
        # Получаем тикет
        ticket = await crud.get_ticket_by_id(session, ticket_id)
        
        if not ticket:
            await message.answer("⚠️ Тикет не найден")
            await state.clear()
            return
        
        # Добавляем ответ
        admin_id = str(message.from_user.id)
        response_text = message.text.strip()
        
        success = await crud.add_admin_response(
            session,
            ticket_id,
            admin_id,
            response_text
        )
        
        if not success:
            await message.answer("⚠️ Ошибка сохранения ответа")
            await state.clear()
            return
        
        logger.info(f"Админ {admin_id} ответил на тикет #{ticket_id}")
        
        # Отправляем подтверждение админу
        await message.answer(
            ADMIN_RESPONSE_SUCCESS.format(ticket_id=ticket_id)
        )
        
        # Отправляем ответ менеджеру
        try:
            await message.bot.send_message(
                chat_id=ticket.manager_telegram_id,
                text=f"""
📮 Ответ на ваш тикет #{ticket_id}

👨‍💼 Администратор ответил:
{response_text}

────────────────
Статус тикета: ⏳ В работе
"""
            )
            logger.info(f"Ответ отправлен менеджеру {ticket.manager_telegram_id}")
        except Exception as e:
            logger.warning(f"Не удалось отправить ответ менеджеру {ticket.manager_telegram_id}: {e}")
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки ответа: {type(e).__name__}: {e}")
        await message.answer("⚠️ Ошибка обработки ответа")
        await state.clear()


# =============================================================================
# Изменение статуса тикета
# =============================================================================

@router.callback_query(F.data.startswith("ticket_status:"))
async def change_ticket_status(callback: CallbackQuery, session: AsyncSession):
    """
    Изменение статуса тикета
    """
    try:
        # Парсим callback_data
        parts = callback.data.split(":")
        ticket_id = int(parts[1])
        new_status = parts[2]
        
        # Получаем ID админа
        admin_id = str(callback.from_user.id)
        
        # Обновляем статус
        success = await crud.update_ticket_status(
            session,
            ticket_id,
            new_status,
            admin_id
        )
        
        if not success:
            await callback.answer("⚠️ Ошибка обновления статуса", show_alert=True)
            return
        
        logger.info(f"Тикет #{ticket_id}: статус изменён на {new_status}")
        
        # Уведомляем менеджера
        ticket = await crud.get_ticket_by_id(session, ticket_id)
        if ticket:
            status_map = {
                "new": "🆕 Новый",
                "in_progress": "⏳ В работе",
                "resolved": "✅ Решён",
                "closed": "🔒 Закрыт"
            }
            status_text = status_map.get(new_status, new_status)
            
            try:
                await callback.bot.send_message(
                    chat_id=ticket.manager_telegram_id,
                    text=f"""
📮 Статус тикета #{ticket_id} изменён

Новый статус: {status_text}
"""
                )
            except Exception as e:
                logger.warning(f"Не удалось уведомить менеджера: {e}")
        
        # Показываем подтверждение
        await callback.answer(
            TICKET_STATUS_CHANGED.format(status=new_status),
            show_alert=True
        )
        
        # Обновляем сообщение с тикетом
        await callback.message.delete()
        await view_ticket(callback, session, await callback.bot.get_state())
        
    except Exception as e:
        logger.error(f"Ошибка изменения статуса: {type(e).__name__}: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)
    
    await callback.answer()
