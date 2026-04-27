"""
Тикеты, обратная связь, управление ботом, reply «главное меню».
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from ..messages.texts import (
    BTN_BACK, BTN_CANCEL,
    FEEDBACK_BUTTON,
    TICKETS_FILTER_ALL, TICKETS_FILTER_NEW, TICKETS_FILTER_IN_PROGRESS, TICKETS_FILTER_RESOLVED,
    TICKET_ACTION_RESPOND, TICKET_ACTION_IN_PROGRESS, TICKET_ACTION_RESOLVED, TICKET_ACTION_BACK,
    MAIN_MENU_BUTTON, MAIN_MENU_BUTTON_ADMIN,
)




# =============================================================================
# Клавиатуры для тикетов (Tickets)
# =============================================================================

def create_feedback_main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура главного меню менеджера с кнопкой обратной связи
    
    Returns:
        InlineKeyboardMarkup
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    
    builder = InlineKeyboardBuilder()
    
    # Кнопка обратной связи
    builder.button(text=FEEDBACK_BUTTON, callback_data="feedback_main")
    
    builder.adjust(1)
    return builder.as_markup()


def create_feedback_confirm_keyboard(message_preview: str) -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения отправки тикета
    
    Args:
        message_preview: Текст сообщения для предпросмотра
        
    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(text="✅ Отправить", callback_data=f"feedback_confirm:{len(message_preview)}")
    builder.button(text=BTN_CANCEL, callback_data="feedback_cancel")
    
    builder.adjust(2)
    return builder.as_markup()


def create_ticket_filter_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура фильтрации тикетов для админа
    
    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(text=TICKETS_FILTER_ALL, callback_data="ticket_filter:all")
    builder.button(text=TICKETS_FILTER_NEW, callback_data="ticket_filter:new")
    builder.button(text=TICKETS_FILTER_IN_PROGRESS, callback_data="ticket_filter:in_progress")
    builder.button(text=TICKETS_FILTER_RESOLVED, callback_data="ticket_filter:resolved")
    
    builder.adjust(2)
    return builder.as_markup()


def create_tickets_list_keyboard(
    tickets: list,
    page: int,
    total_pages: int
) -> InlineKeyboardMarkup:
    """
    Клавиатура списка тикетов с пагинацией
    
    Args:
        tickets: Список тикетов
        page: Текущая страница (0-based)
        total_pages: Всего страниц
        
    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопки с тикетами
    for ticket in tickets:
        status_emoji = "🆕" if ticket.status == "new" else "⏳" if ticket.status == "in_progress" else "✅"
        builder.button(
            text=f"{status_emoji} #{ticket.id} - {ticket.manager_telegram_id}",
            callback_data=f"ticket_view:{ticket.id}"
        )
    
    # Пагинация
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"ticket_page:{page - 1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"ticket_page:{page + 1}"))
        builder.row(*nav_buttons)
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="admin_menu"))
    
    builder.adjust(1, repeat=True)
    return builder.as_markup()


def create_ticket_action_keyboard(ticket_id: int, status: str) -> InlineKeyboardMarkup:
    """
    Клавиатура действий с тикетом
    
    Args:
        ticket_id: ID тикета
        status: Текущий статус тикета
        
    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопки действий
    if status == "new":
        builder.button(text=TICKET_ACTION_RESPOND, callback_data=f"ticket_respond:{ticket_id}")
        builder.button(text=TICKET_ACTION_IN_PROGRESS, callback_data=f"ticket_status:{ticket_id}:in_progress")
    elif status == "in_progress":
        builder.button(text=TICKET_ACTION_RESPOND, callback_data=f"ticket_respond:{ticket_id}")
        builder.button(text=TICKET_ACTION_RESOLVED, callback_data=f"ticket_status:{ticket_id}:resolved")
    
    builder.button(text=TICKET_ACTION_BACK, callback_data="admin_tickets")
    
    builder.adjust(1)
    return builder.as_markup()


def create_my_tickets_keyboard(tickets: list) -> InlineKeyboardMarkup:
    """
    Клавиатура моих тикетов для менеджера
    
    Args:
        tickets: Список тикетов
        
    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопки с тикетами
    for ticket in tickets[:10]:  # Максимум 10
        status_emoji = "🆕" if ticket.status == "new" else "⏳" if ticket.status == "in_progress" else "✅"
        builder.button(
            text=f"{status_emoji} #{ticket.id} - {ticket.created_at.strftime('%d.%m.%y')}",
            callback_data=f"my_ticket_view:{ticket.id}"
        )
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="manager_menu"))
    
    builder.adjust(1, repeat=True)
    return builder.as_markup()


# =============================================================================
# Клавиатуры управления статусом бота
# =============================================================================

def create_bot_control_keyboard(current_status: str) -> InlineKeyboardMarkup:
    """
    Клавиатура управления статусом бота
    
    Args:
        current_status: Текущий статус бота (running, stopped, maintenance)
        
    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()
    
    if current_status == "running":
        # Бот работает - предлагаем остановить
        builder.button(text="⏸ Остановить бота", callback_data="bot_stop")
        builder.button(text="🟡 Техработы", callback_data="bot_maintenance")
    else:
        # Бот остановлен - предлагаем запустить
        builder.button(text="▶️ Запустить бота", callback_data="bot_start")
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="admin_menu"))
    builder.adjust(1)
    
    return builder.as_markup()


def create_bot_stop_reason_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура выбора причины остановки
    
    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(text="⏱ Временно", callback_data="stop_reason_temp")
    builder.button(text="🔧 Техработы", callback_data="stop_reason_maintenance")
    builder.button(text="❌ Пропустить", callback_data="stop_reason_skip")
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="bot_control"))
    builder.adjust(2)
    
    return builder.as_markup()


def create_bot_confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения действия с ботом
    
    Args:
        action: Действие (start, stop, maintenance)
        
    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(text="✅ Подтвердить", callback_data=f"bot_confirm_{action}")
    builder.button(text=BTN_CANCEL, callback_data="bot_control")
    
    builder.adjust(2)
    return builder.as_markup()


# =============================================================================
# Reply клавиатуры (постоянные кнопки)
# =============================================================================

def create_main_menu_reply_keyboard(user_role: str = "manager") -> ReplyKeyboardMarkup:
    """
    Постоянная reply-клавиатура с кнопкой главного меню
    
    Всегда видна внизу чата
    
    Args:
        user_role: Роль пользователя (manager/admin)
        
    Returns:
        ReplyKeyboardMarkup
    """
    builder = ReplyKeyboardBuilder()
    
    if user_role == "admin":
        builder.button(text=MAIN_MENU_BUTTON_ADMIN)
    else:
        builder.button(text=MAIN_MENU_BUTTON)
    
    builder.adjust(1)
    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=False,
        persistent=True  # Сохранять после перезапуска
    )
