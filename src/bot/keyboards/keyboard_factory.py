"""
Фабрика клавиатур для Telegram-бота

Создает inline и reply клавиатуры с динамическими данными
Включает защиту от XSS через экранирование пользовательских данных
"""
from typing import List, Optional, Tuple, Dict, Any
from html import escape

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from ..messages.texts import (
    BTN_BACK, BTN_MAIN_MENU, BTN_CANCEL,
    BTN_YES, BTN_NO, BTN_CONFIRM,
    BTN_NEXT, BTN_PREVIOUS,
    MANAGER_GET_LEADS, MANAGER_MY_STATS, MANAGER_ABOUT,
    ADMIN_IMPORT_CSV, ADMIN_DUPLICATE_CHECK, ADMIN_STATS,
    ADMIN_EXPORT, ADMIN_SEGMENTS, ADMIN_CLEANUP, ADMIN_PENDING_USERS, ADMIN_BROADCAST,
    DUPLICATE_CHECK_RUN,
    CLEANUP_LOGS, CLEANUP_DUPLICATES, CLEANUP_IMPORTED,
    SEGMENT_FREEZE, SEGMENT_UNFREEZE,
    PENDING_USER_APPROVE, PENDING_USER_REJECT,
    FEEDBACK_BUTTON, TICKETS_BUTTON,
    TICKETS_FILTER_ALL, TICKETS_FILTER_NEW, TICKETS_FILTER_IN_PROGRESS, TICKETS_FILTER_RESOLVED,
    TICKET_ACTION_RESPOND, TICKET_ACTION_IN_PROGRESS, TICKET_ACTION_RESOLVED, TICKET_ACTION_BACK,
    BOT_CONTROL_BUTTON,
    MAIN_MENU_BUTTON, MAIN_MENU_BUTTON_ADMIN,
    ADMIN_LOAD_LEADS_BUTTON, ADMIN_LOAD_LEADS_ALL_CITIES,
    ADMIN_LOAD_LEADS_BITRIX_ID,
)


def escape_markdown(text: str) -> str:
    """
    Экранирование специальных символов Markdown v2
    
    Telegram использует Markdown v2 для форматирования сообщений.
    Специальные символы: _ * [ ] ( ) ~ ` > # + - = | { } . !
    
    Args:
        text: Текст для экранирования
        
    Returns:
        Экранированный текст
    """
    if not text:
        return ""
    
    # Символы требующие экранирования в Markdown v2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    result = text
    
    for char in escape_chars:
        result = result.replace(char, f'\\{char}')
    
    return result


def escape_html(text: str) -> str:
    """
    Экранирование HTML специальных символов
    
    Args:
        text: Текст для экранирования
        
    Returns:
        Экранированный HTML текст
    """
    if not text:
        return ""
    
    return escape(text)


def safe_text(text: str, max_length: Optional[int] = None) -> str:
    """
    Безопасная обработка пользовательского текста
    
    - Экранирование HTML
    - Обрезка до максимальной длины
    - Удаление control characters
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина (опционально)
        
    Returns:
        Безопасный текст
    """
    if not text:
        return ""
    
    # Удаляем control characters (кроме newline и tab)
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')
    
    # Экранируем HTML
    text = escape(text)
    
    # Обрезаем если нужно
    if max_length and len(text) > max_length:
        text = text[:max_length - 3] + '...'
    
    return text


# =============================================================================
# Inline клавиатуры
# =============================================================================

def create_manager_main_menu() -> InlineKeyboardMarkup:
    """Главное меню менеджера"""
    builder = InlineKeyboardBuilder()

    builder.button(text=MANAGER_GET_LEADS, callback_data="leads_menu")
    builder.button(text=MANAGER_MY_STATS, callback_data="my_stats")
    builder.button(text=FEEDBACK_BUTTON, callback_data="feedback_main")
    builder.button(text=MANAGER_ABOUT, callback_data="about")

    builder.adjust(1)
    return builder.as_markup()


def create_admin_main_menu() -> InlineKeyboardMarkup:
    """Главное меню админа"""
    builder = InlineKeyboardBuilder()

    builder.button(text=ADMIN_IMPORT_CSV, callback_data="admin_import_csv")
    builder.button(text=ADMIN_DUPLICATE_CHECK, callback_data="admin_duplicate_check")
    builder.button(text=ADMIN_STATS, callback_data="admin_stats")
    builder.button(text="📊 Статистика по менеджерам", callback_data="admin_manager_stats")
    builder.button(text=ADMIN_EXPORT, callback_data="admin_export")
    builder.button(text=ADMIN_SEGMENTS, callback_data="admin_segments")
    builder.button(text=TICKETS_BUTTON, callback_data="admin_tickets")
    builder.button(text=BOT_CONTROL_BUTTON, callback_data="bot_control")
    builder.button(text=ADMIN_LOAD_LEADS_BUTTON, callback_data="admin_load_leads")
    builder.button(text=ADMIN_LOAD_LEADS_BITRIX_ID, callback_data="admin_load_leads_bitrix")
    builder.button(text=ADMIN_BROADCAST, callback_data="admin_broadcast")
    builder.button(text=ADMIN_CLEANUP, callback_data="admin_cleanup")
    builder.button(text=ADMIN_PENDING_USERS, callback_data="admin_pending_users")

    builder.adjust(1)
    return builder.as_markup()


def create_segments_keyboard(
    segments: List[Tuple[str, List[str]]],
    prefix: str = "select_segment",
    page: int = 0,
    page_size: int = 20
) -> InlineKeyboardMarkup:
    """
    Клавиатура с сегментами (использует индексы для callback_data)

    Args:
        segments: Список кортежей [(segment_name, [cities]), ...]
        prefix: Префикс для callback_data
        page: Текущая страница (0-based)
        page_size: Количество сегментов на странице
    """
    builder = InlineKeyboardBuilder()
    
    # Разбиваем на страницы
    total_pages = (len(segments) + page_size - 1) // page_size if segments else 1
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(segments))
    
    # Показываем сегменты текущей страницы
    for idx in range(start_idx, end_idx):
        segment, cities = segments[idx]
        
        # Используем глобальный индекс для callback_data
        callback_data = f"{prefix}:{idx}"

        # Отображаем сегмент с количеством городов
        cities_count = f" ({len(cities)} гор.)" if cities else ""
        button_text = f"{get_segment_emoji(segment)} {segment}{cities_count}"

        builder.button(text=button_text, callback_data=callback_data)
    
    # Кнопки пагинации
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{prefix}_page:{page - 1}"))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"{prefix}_page:{page + 1}"))
    
    if nav_buttons:
        # Добавляем информацию о странице
        page_info = InlineKeyboardButton(text=f"Стр. {page + 1}/{total_pages}", callback_data=f"{prefix}_page_info")
        nav_buttons.insert(1, page_info) if len(nav_buttons) > 1 else nav_buttons.append(page_info)
    
    for btn in nav_buttons:
        builder.button(text=btn.text, callback_data=btn.callback_data)
    
    # Кнопка возврата в главное меню
    builder.button(text="🏠 Главное меню", callback_data="to_main_menu")
    builder.adjust(1)

    return builder.as_markup()


def create_cities_keyboard(
    cities: List[str],
    segment: str,
    segment_index: int,
    prefix: str = "city"
) -> InlineKeyboardMarkup:
    """
    Клавиатура с городами (использует индексы)

    Args:
        cities: Список городов
        segment: Сегмент (для отображения)
        segment_index: Индекс сегмента (для callback_data)
        prefix: Префикс для callback_data
    """
    builder = InlineKeyboardBuilder()

    for idx, city in enumerate(cities):
        callback_data = f"{prefix}:{segment_index}:{idx}"
        builder.button(text=city, callback_data=callback_data)
    
    builder.button(text=BTN_BACK, callback_data="back_to_segments")
    builder.adjust(2)
    
    return builder.as_markup()


def create_confirmation_keyboard(
    confirm_callback: str,
    cancel_callback: str,
    confirm_text: str = BTN_YES,
    cancel_text: str = BTN_NO
) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text=confirm_text, callback_data=confirm_callback)
    builder.button(text=cancel_text, callback_data=cancel_callback)
    
    builder.adjust(2)
    return builder.as_markup()


def create_back_keyboard(back_callback: str = "back_to_main") -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой «Назад» или «В главное меню»"""
    builder = InlineKeyboardBuilder()

    # Для возврата в главное меню используем специальную кнопку
    if back_callback == "to_main_menu":
        builder.button(text="🏠 В главное меню", callback_data=back_callback)
    else:
        builder.button(text=BTN_BACK, callback_data=back_callback)

    return builder.as_markup()


def create_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения рассылки"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Отправить", callback_data="broadcast_confirm")
    builder.button(text="❌ Отмена", callback_data="broadcast_cancel")
    builder.adjust(2)
    return builder.as_markup()


def create_pending_users_keyboard(
    users: List[Dict[str, Any]]
) -> InlineKeyboardMarkup:
    """
    Клавиатура с заявками менеджеров
    
    Args:
        users: Список пользователей [{"telegram_id": str, "full_name": str}, ...]
    """
    builder = InlineKeyboardBuilder()
    
    for user in users:
        telegram_id = user["telegram_id"]
        full_name = user["full_name"]
        
        # Кнопка с именем
        builder.button(
            text=f"⏳ {full_name}",
            callback_data=f"user_view:{telegram_id}"
        )
    
    builder.adjust(1)
    return builder.as_markup()


def create_user_action_keyboard(telegram_id: str) -> InlineKeyboardMarkup:
    """Клавиатура действий с пользователем"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text=PENDING_USER_APPROVE, callback_data=f"user_approve:{telegram_id}")
    builder.button(text=PENDING_USER_REJECT, callback_data=f"user_reject:{telegram_id}")
    builder.button(text=BTN_BACK, callback_data="admin_pending_users")
    
    builder.adjust(2)
    return builder.as_markup()


def create_segments_admin_keyboard(
    segments: List[Dict[str, Any]],
    page: int = 0,
    page_size: int = 20
) -> InlineKeyboardMarkup:
    """
    Клавиатура сегментов для админа с пагинацией

    Args:
        segments: Список [{"segment": str, "city": Optional[str], "is_frozen": bool, "count": int}, ...]
        page: Текущая страница (0-based)
        page_size: Количество сегментов на странице
    """
    from ...logger import get_logger
    logger = get_logger(__name__)
    
    builder = InlineKeyboardBuilder()
    
    # Разбиваем на страницы
    total_pages = (len(segments) + page_size - 1) // page_size if segments else 1
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(segments))
    
    # Показываем сегменты текущей страницы
    for idx in range(start_idx, end_idx):
        seg_data = segments[idx]
        segment = seg_data["segment"]
        city = seg_data.get("city")
        is_frozen = seg_data.get("is_frozen", False)
        
        # callback_data содержит глобальный индекс в списке
        callback_data = f"segment_manage:{idx}"
        
        logger.info(f"Кнопка {idx}: {segment} + {city} (заморожен: {is_frozen}) → {callback_data}")

        # Статус
        status_icon = "❄️" if is_frozen else "✅"
        city_text = f" + {city}" if city else ""

        builder.button(
            text=f"{status_icon} {segment}{city_text}",
            callback_data=callback_data
        )
    
    # Кнопки пагинации
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"segments_page:{page - 1}"))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"segments_page:{page + 1}"))
    
    if nav_buttons:
        # Добавляем информацию о странице
        page_info = InlineKeyboardButton(text=f"Стр. {page + 1}/{total_pages}", callback_data="segments_page_info")
        nav_buttons.insert(1, page_info) if len(nav_buttons) > 1 else nav_buttons.append(page_info)
    
    for btn in nav_buttons:
        builder.button(text=btn.text, callback_data=btn.callback_data)
    
    builder.button(text=BTN_BACK, callback_data="admin_menu")
    builder.adjust(1)  # Каждая кнопка в отдельном ряду
    
    return builder.as_markup()


def create_segment_action_keyboard(
    segment: str,
    city: Optional[str],
    is_frozen: bool
) -> InlineKeyboardMarkup:
    """Клавиатура действий с сегментом"""
    builder = InlineKeyboardBuilder()

    # Используем простые callback_data без параметров (данные в state)
    if is_frozen:
        builder.button(
            text=SEGMENT_UNFREEZE,
            callback_data="segment_unfreeze"
        )
    else:
        builder.button(
            text=SEGMENT_FREEZE,
            callback_data="segment_freeze"
        )

    builder.button(text=BTN_BACK, callback_data="admin_segments")
    builder.adjust(1)

    return builder.as_markup()


def create_cleanup_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура очистки данных"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text=CLEANUP_LOGS, callback_data="cleanup_logs")
    builder.button(text=CLEANUP_DUPLICATES, callback_data="cleanup_duplicates")
    builder.button(text=CLEANUP_IMPORTED, callback_data="cleanup_imported")
    builder.button(text=BTN_BACK, callback_data="admin_menu")
    
    builder.adjust(1)
    return builder.as_markup()


def create_stats_period_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора периода статистики"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="📅 Сегодня", callback_data="stats_today")
    builder.button(text="📅 Эта неделя", callback_data="stats_week")
    builder.button(text="📅 Этот месяц", callback_data="stats_month")
    builder.button(text="📊 Всё время", callback_data="stats_all")
    builder.button(text=BTN_BACK, callback_data="admin_menu")
    
    builder.adjust(2)
    return builder.as_markup()


def create_duplicate_check_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура проверки дублей"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text=DUPLICATE_CHECK_RUN, callback_data="duplicate_run")
    builder.button(text=BTN_BACK, callback_data="admin_menu")
    
    builder.adjust(1)
    return builder.as_markup()


# =============================================================================
# Reply клавиатуры
# =============================================================================

def create_manager_reply_menu() -> ReplyKeyboardMarkup:
    """Reply меню менеджера (для основных команд)"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text=MANAGER_GET_LEADS)
    builder.button(text=MANAGER_MY_STATS)
    
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def create_admin_reply_menu() -> ReplyKeyboardMarkup:
    """Reply меню админа"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text=ADMIN_IMPORT_CSV)
    builder.button(text=ADMIN_DUPLICATE_CHECK)
    builder.button(text=ADMIN_STATS)
    builder.button(text=ADMIN_EXPORT)
    builder.button(text=ADMIN_SEGMENTS)
    builder.button(text=ADMIN_CLEANUP)
    builder.button(text=ADMIN_PENDING_USERS)
    
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def create_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text=BTN_CANCEL)
    
    return builder.as_markup(resize_keyboard=True)


# =============================================================================
# Утилиты
# =============================================================================

def get_segment_emoji(segment: str) -> str:
    """
    Возвращает emoji для сегмента
    
    Args:
        segment: Название сегмента
        
    Returns:
        Emoji
    """
    emojis = {
        "Автосалон": "🚗",
        "Автосервис": "🔧",
        "Автомойка": "🚿",
        "Выкуп автомобилей": "💰",
        "Грузовые автомобили": "🚛",
        "Строительство": "🏗",
        "Производство": "🏭",
        "Розница": "🛒",
        "Услуги": "💼",
        "Нефть": "🛢",
        "Авто": "🚗",
    }
    
    # Ищем частичное совпадение
    for key, emoji in emojis.items():
        if key.lower() in segment.lower():
            return emoji
    
    return "📦"  # По умолчанию


def parse_callback_data(callback_data: str) -> Dict[str, str]:
    """
    Парсинг callback_data

    Формат: "action:param1:param2:..."

    Args:
        callback_data: Строка callback_data

    Returns:
        {"action": str, "params": [str, ...]}
    """
    parts = callback_data.split(":")

    return {
        "action": parts[0],
        "params": parts[1:] if len(parts) > 1 else []
    }


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


# =============================================================================
# Клавиатуры для загрузки лидов админом
# =============================================================================

def create_managers_list_keyboard(
    managers: List[Dict[str, Any]],
    page: int = 0,
    page_size: int = 10
) -> InlineKeyboardMarkup:
    """
    Клавиатура со списком менеджеров
    
    Args:
        managers: Список менеджеров [{telegram_id, full_name, leads_count}, ...]
        page: Текущая страница (0-based)
        page_size: Размер страницы
        
    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()
    
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(managers))
    
    for i in range(start_idx, end_idx):
        manager = managers[i]
        button_text = f"👤 {manager['full_name']} ({manager['leads_count']} лидов)"
        builder.button(
            text=button_text,
            callback_data=f"load_leads_manager:{manager['telegram_id']}"
        )
    
    # Пагинация
    total_pages = (len(managers) + page_size - 1) // page_size
    
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"load_leads_managers_page:{page - 1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"load_leads_managers_page:{page + 1}"))
        if nav_buttons:
            builder.row(*nav_buttons)
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="admin_menu"))
    builder.adjust(1, repeat=True)
    
    return builder.as_markup()


def create_segments_load_keyboard(
    segments: List[Tuple[str, List[str]]],
    page: int = 0,
    page_size: int = 10,
    prefix: str = "load_leads_segment",
    back_callback: str = "admin_menu"
) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора сегмента для загрузки
    
    ИСПОЛЬЗУЕТ ИНДЕКСЫ вместо названий для callback_data
    Telegram ограничивает callback_data 64 байтами (UTF-8).
    Кириллица = 2 байта/символ, поэтому используем индексы.
    
    Args:
        segments: Список сегментов [(segment_name, [cities]), ...]
        page: Текущая страница
        page_size: Размер страницы
        prefix: Префикс для callback_data
        back_callback: Callback для кнопки "Назад"
        
    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(segments))

    for i in range(start_idx, end_idx):
        segment, cities = segments[i]
        # ✅ ИСПОЛЬЗУЕМ ИНДЕКС вместо названия (максимум ~25 байт)
        callback_data = f"{prefix}:{i}"
        
        builder.button(
            text=f"📁 {segment}",
            callback_data=callback_data
        )

    # Пагинация
    total_pages = (len(segments) + page_size - 1) // page_size

    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{prefix}_page:{page - 1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"{prefix}_page:{page + 1}"))
        if nav_buttons:
            builder.row(*nav_buttons)

    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data=back_callback))
    builder.adjust(1, repeat=True)

    return builder.as_markup()


def create_cities_load_keyboard(
    cities: List[str],
    segment: str,
    segment_index: int,
    prefix: str = "load_leads_city",
    back_callback: str = "admin_menu"
) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора города для загрузки
    
    Args:
        cities: Список городов
        segment: Сегмент
        segment_index: Индекс сегмента
        prefix: Префикс для callback_data
        back_callback: Callback для кнопки "Назад"
        
    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Все города"
    builder.button(
        text=ADMIN_LOAD_LEADS_ALL_CITIES,
        callback_data=f"{prefix}:{segment_index}:__ALL__"
    )
    
    # Кнопки городов
    for i, city in enumerate(cities):
        builder.button(
            text=f"🏙 {city}",
            callback_data=f"{prefix}:{segment_index}:{i}"
        )
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data=back_callback))
    builder.adjust(1, repeat=True)
    
    return builder.as_markup()


def create_load_confirm_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения загрузки лидов
    
    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(text="✅ Загрузить", callback_data="load_leads_confirm")
    builder.button(text=BTN_CANCEL, callback_data="load_leads_cancel")
    
    builder.adjust(2)
    return builder.as_markup()


def create_not_enough_leads_keyboard(available_count: int) -> InlineKeyboardMarkup:
    """
    Клавиатура для ситуации "недостаточно лидов"
    
    Args:
        available_count: Доступное количество
        
    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text=f"✅ Да, загрузить {available_count}",
        callback_data=f"load_leads_confirm_available:{available_count}"
    )
    builder.button(text=BTN_CANCEL, callback_data="load_leads_cancel")
    
    builder.adjust(1)
    return builder.as_markup()
