"""
Клавиатуры сценария admin_load (менеджер / Bitrix ID).
"""
from typing import List, Tuple, Dict, Any

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..messages.texts import BTN_BACK, BTN_CANCEL, ADMIN_LOAD_LEADS_ALL_CITIES


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


def create_not_enough_leads_keyboard(
    available_count: int,
    *,
    confirm_callback_prefix: str = "load_leads",
) -> InlineKeyboardMarkup:
    """
    Клавиатура для ситуации "недостаточно лидов"
    
    Args:
        available_count: Доступное количество
        confirm_callback_prefix: Префикс callback: ``{prefix}_confirm_available:{count}``.
            Для сценария «на менеджера» — ``load_leads``; для Bitrix24 ID — ``load_bitrix``.
        
    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text=f"✅ Да, загрузить {available_count}",
        callback_data=f"{confirm_callback_prefix}_confirm_available:{available_count}"
    )
    builder.button(text=BTN_CANCEL, callback_data="load_leads_cancel")
    
    builder.adjust(1)
    return builder.as_markup()
