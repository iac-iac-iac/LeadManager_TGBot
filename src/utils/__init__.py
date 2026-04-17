"""
Утилиты проекта

Модули:
- phone_utils: Нормализация и валидация телефонов
- callback_utils: Безопасная работа с callback данными (aiogram 3.x)
- file_utils: Безопасная работа с файлами
- datetime_utils: Timezone-aware datetime операции
- html_utils: Безопасное HTML-экранирование в шаблонах Telegram
"""

from .phone_utils import (
    normalize_phone,
    normalize_phone_for_bitrix24,
    validate_phone,
    format_phone_display,
)

from .callback_utils import (
    CALLBACK_PREFIXES,
    MAX_SEGMENT_INDEX,
    MAX_CITY_INDEX,
    MAX_LEADS_COUNT,
    MAX_PAGE_NUMBER,
    MAX_USERNAME_LENGTH,
    MAX_FILENAME_LENGTH,
    parse_callback_data,
    validate_callback_data,
    safe_parse_callback_data,
    create_callback_data,
)

from .file_utils import (
    validate_filename,
    safe_read_file,
    safe_write_file,
    check_file_permissions,
    get_secure_temp_filename,
    cleanup_dangerous_chars,
)

from .html_utils import (
    escape,
    format_html_safe,
    suppress_telegram_errors,
    safe_delete_message,
    safe_answer_callback,
    safe_edit_or_answer,
)

from .datetime_utils import (
    now_utc,
    now_utc_timestamp,
    utc_from_timestamp,
    ensure_timezone_aware,
    to_utc,
    format_datetime,
    parse_datetime,
    get_start_of_day,
    get_end_of_day,
    get_start_of_week,
    get_start_of_month,
    get_end_of_month,
    get_period_start_end,
    is_older_than,
    is_within_period,
)

__all__ = [
    # Phone utils
    'normalize_phone',
    'normalize_phone_for_bitrix24',
    'validate_phone',
    'format_phone_display',

    # Callback utils
    'CALLBACK_PREFIXES',
    'MAX_SEGMENT_INDEX',
    'MAX_CITY_INDEX',
    'MAX_LEADS_COUNT',
    'MAX_PAGE_NUMBER',
    'MAX_USERNAME_LENGTH',
    'MAX_FILENAME_LENGTH',
    'parse_callback_data',
    'validate_callback_data',
    'safe_parse_callback_data',
    'create_callback_data',

    # HTML utils
    'escape',
    'format_html_safe',
    'suppress_telegram_errors',
    'safe_delete_message',
    'safe_answer_callback',
    'safe_edit_or_answer',

    # File utils
    'validate_filename',
    'safe_read_file',
    'safe_write_file',
    'check_file_permissions',
    'get_secure_temp_filename',
    'cleanup_dangerous_chars',

    # Datetime utils
    'now_utc',
    'now_utc_timestamp',
    'utc_from_timestamp',
    'ensure_timezone_aware',
    'to_utc',
    'format_datetime',
    'parse_datetime',
    'get_start_of_day',
    'get_end_of_day',
    'get_start_of_week',
    'get_start_of_month',
    'get_end_of_month',
    'get_period_start_end',
    'is_older_than',
    'is_within_period',
]
