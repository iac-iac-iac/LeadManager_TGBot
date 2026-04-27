"""
Основные inline- и reply-клавиатуры менеджера/админа (сегменты, заявки, очистка и т.д.).
"""
from typing import List, Optional, Tuple, Dict, Any

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from ..messages.texts import (
    BTN_BACK, BTN_CANCEL,
    BTN_YES, BTN_NO,
    MANAGER_GET_LEADS, MANAGER_MY_STATS, MANAGER_ABOUT,
    ADMIN_IMPORT_CSV, ADMIN_DUPLICATE_CHECK, ADMIN_STATS,
    ADMIN_EXPORT, ADMIN_SEGMENTS, ADMIN_CLEANUP, ADMIN_PENDING_USERS, ADMIN_BROADCAST, ADMIN_PENDING_CITIES,
    DUPLICATE_CHECK_RUN,
    CLEANUP_LOGS, CLEANUP_DUPLICATES, CLEANUP_IMPORTED,
    SEGMENT_FREEZE, SEGMENT_UNFREEZE,
    PENDING_USER_APPROVE, PENDING_USER_REJECT,
    FEEDBACK_BUTTON, TICKETS_BUTTON,
    BOT_CONTROL_BUTTON,
    ADMIN_LOAD_LEADS_BUTTON, ADMIN_LOAD_LEADS_BITRIX_ID,
)
from .keyboard_segment_emoji import get_segment_emoji



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
    builder.button(text=ADMIN_PENDING_CITIES, callback_data="admin_pending_cities")
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
        # Для "Прочее" сегментов не добавляем "(N гор.)" — там уже есть счётчик лидов
        if "📦 Прочие" in segment or "📦 Прочее" in segment:
            button_text = f"{segment}"
        else:
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

