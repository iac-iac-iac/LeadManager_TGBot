"""
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
