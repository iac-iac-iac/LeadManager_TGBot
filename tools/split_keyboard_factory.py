"""Split keyboard_factory.py into submodules; run: python tools/split_keyboard_factory.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = ROOT / "src" / "bot" / "keyboards"
orig = (src / "keyboard_factory.py").read_text(encoding="utf-8").splitlines(keepends=True)

def chunk(a: int, b: int) -> str:
    return "".join(orig[a:b])

# 0-based line indices (end exclusive, same as str slice)
# escape_markdown .. safe_text only (1-based 39-109) — отдельно от callback_utils/aiogram
common = chunk(38, 109)

segment_emoji = chunk(491, 521)  # get_segment_emoji: 1-based 492-521

# "# Inline" .. create_cancel (1-based 111-486)
inline_core = chunk(110, 486)

# тикеты / бот / reply главное меню (1-based 522-773)
tickets_bot = chunk(521, 773)

# admin load (1-based 776-967, EOF)
admin_load = chunk(775, 967)

common_header = '''"""
Общие утилиты для клавиатур (экранирование, safe_text).
"""
from typing import Optional
from html import escape

'''

segment_header = '''"""
Emoji для отображения сегментов в кнопках.
"""

'''

inline_header = '''"""
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


'''

tickets_header = '''"""
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


'''

admin_load_header = '''"""
Клавиатуры сценария admin_load (менеджер / Bitrix ID).
"""
from typing import List, Tuple, Dict, Any

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..messages.texts import BTN_BACK, BTN_CANCEL, ADMIN_LOAD_LEADS_ALL_CITIES


'''

(src / "keyboard_common.py").write_text(common_header + common, encoding="utf-8")
(src / "keyboard_segment_emoji.py").write_text(segment_header + segment_emoji, encoding="utf-8")
(src / "keyboard_inline_core.py").write_text(inline_header + inline_core, encoding="utf-8")
(src / "keyboard_tickets_bot.py").write_text(tickets_header + tickets_bot, encoding="utf-8")
(src / "keyboard_admin_load.py").write_text(admin_load_header + admin_load, encoding="utf-8")

factory = '''"""
Фабрика клавиатур для Telegram-бота.

Реэкспортирует функции из подмодулей — импорты вида
``from ...keyboards.keyboard_factory import create_manager_main_menu`` сохраняются.
"""
from ...utils.callback_utils import (
    parse_colon_to_action_dict as parse_callback_data,
    parse_colon_action_dict as safe_parse_callback_data,
)

from .keyboard_common import escape_markdown, escape_html, safe_text
from .keyboard_segment_emoji import get_segment_emoji
from .keyboard_inline_core import (
    create_manager_main_menu,
    create_admin_main_menu,
    create_segments_keyboard,
    create_cities_keyboard,
    create_confirmation_keyboard,
    create_back_keyboard,
    create_broadcast_confirm_keyboard,
    create_pending_users_keyboard,
    create_user_action_keyboard,
    create_segments_admin_keyboard,
    create_segment_action_keyboard,
    create_cleanup_keyboard,
    create_stats_period_keyboard,
    create_duplicate_check_keyboard,
    create_manager_reply_menu,
    create_admin_reply_menu,
    create_cancel_keyboard,
)
from .keyboard_tickets_bot import (
    create_feedback_main_menu_keyboard,
    create_feedback_confirm_keyboard,
    create_ticket_filter_keyboard,
    create_tickets_list_keyboard,
    create_ticket_action_keyboard,
    create_my_tickets_keyboard,
    create_bot_control_keyboard,
    create_bot_stop_reason_keyboard,
    create_bot_confirm_keyboard,
    create_main_menu_reply_keyboard,
)
from .keyboard_admin_load import (
    create_managers_list_keyboard,
    create_segments_load_keyboard,
    create_cities_load_keyboard,
    create_load_confirm_keyboard,
    create_not_enough_leads_keyboard,
)

__all__ = [
    "parse_callback_data",
    "safe_parse_callback_data",
    "escape_markdown",
    "escape_html",
    "safe_text",
    "get_segment_emoji",
    "create_manager_main_menu",
    "create_admin_main_menu",
    "create_segments_keyboard",
    "create_cities_keyboard",
    "create_confirmation_keyboard",
    "create_back_keyboard",
    "create_broadcast_confirm_keyboard",
    "create_pending_users_keyboard",
    "create_user_action_keyboard",
    "create_segments_admin_keyboard",
    "create_segment_action_keyboard",
    "create_cleanup_keyboard",
    "create_stats_period_keyboard",
    "create_duplicate_check_keyboard",
    "create_manager_reply_menu",
    "create_admin_reply_menu",
    "create_cancel_keyboard",
    "create_feedback_main_menu_keyboard",
    "create_feedback_confirm_keyboard",
    "create_ticket_filter_keyboard",
    "create_tickets_list_keyboard",
    "create_ticket_action_keyboard",
    "create_my_tickets_keyboard",
    "create_bot_control_keyboard",
    "create_bot_stop_reason_keyboard",
    "create_bot_confirm_keyboard",
    "create_main_menu_reply_keyboard",
    "create_managers_list_keyboard",
    "create_segments_load_keyboard",
    "create_cities_load_keyboard",
    "create_load_confirm_keyboard",
    "create_not_enough_leads_keyboard",
]
'''

(src / "keyboard_factory.py").write_text(factory, encoding="utf-8")
print("OK")
