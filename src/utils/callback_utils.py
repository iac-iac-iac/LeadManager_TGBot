"""
Утилиты для безопасной работы с callback данными

aiogram 3.x не имеет CallbackData, поэтому используем строковые префиксы с валидацией
"""
from typing import Optional, Tuple, Dict, Any, List
import re

# =============================================================================
# Константы валидации
# =============================================================================

MAX_SEGMENT_INDEX = 10000
MAX_CITY_INDEX = 10000
MAX_LEADS_COUNT = 200
MAX_PAGE_NUMBER = 10000
MAX_USERNAME_LENGTH = 100
MAX_FILENAME_LENGTH = 255

# Префиксы callback данных
CALLBACK_PREFIXES = {
    "manager": ["leads", "stats", "about", "back"],
    "segment": ["select", "back"],
    "city": ["select", "back"],
    "confirm": ["yes", "no"],
    "getleads": ["input"],
    "admin": ["import", "duplicates", "stats", "export", "segments", "cleanup", "users", "back"],
    "import": ["select", "new", "back"],
    "duplicate": ["auto", "manual", "back"],
    "export": ["csv", "back"],
    "cleanup": ["logs", "duplicates", "imported", "back"],
    "segments": ["list", "freeze", "unfreeze", "back"],
    "segmentact": ["freeze_segment", "freeze_city", "unfreeze_segment", "unfreeze_city", "back"],
    "users": ["list", "approve", "reject", "back"],
    "useract": ["view", "approve", "reject", "back"],
    "userappr": ["select", "confirm", "back"],
    "tickets": ["list", "filter", "back"],
    "ticketact": ["view", "respond", "close", "reopen", "back"],
    "botctrl": ["stop", "start", "maintenance", "back"],
}


# =============================================================================
# Валидация callback данных
# =============================================================================

def parse_callback_data(data: str) -> Tuple[Optional[str], List[str]]:
    """
    Парсинг callback данных формата prefix:param1:param2:...

    Args:
        data: Callback data строка

    Returns:
        (префикс, список параметров)

    Examples:
        >>> parse_callback_data("confirm_leads:100")
        ('confirm_leads', ['100'])
        >>> parse_callback_data("segmentact:freeze_segment:Строительство")
        ('segmentact', ['freeze_segment', 'Строительство'])
    """
    if not data:
        return None, []

    parts = data.split(":")
    if len(parts) == 0:
        return None, []

    prefix = parts[0]
    params = parts[1:] if len(parts) > 1 else []

    return prefix, params


def validate_callback_data(prefix: str, params: List[str]) -> Tuple[bool, Optional[str]]:
    """
    Валидация callback данных

    Args:
        prefix: Префикс callback данных
        params: Список параметров

    Returns:
        (успех, сообщение об ошибке или None)

    Examples:
        >>> validate_callback_data("confirm", ["100"])
        (True, None)
        >>> validate_callback_data("confirm", ["9999"])
        (False, "Недопустимое количество лидов")
    """
    # Проверка префикса
    if prefix not in CALLBACK_PREFIXES:
        return False, f"Неизвестный префикс: {prefix}"

    allowed_actions = CALLBACK_PREFIXES[prefix]

    if not params:
        return False, f"Отсутствуют параметры для префикса {prefix}"

    action = params[0]

    # Проверка действия
    if action not in allowed_actions:
        return False, f"Недопустимое действие '{action}' для префикса {prefix}. Разрешены: {allowed_actions}"

    # Валидация числовых параметров
    if prefix == "confirm" and action in ["yes", "no"]:
        if len(params) > 1:
            try:
                count = int(params[1])
                if count < 1 or count > MAX_LEADS_COUNT:
                    return False, f"Недопустимое количество лидов (1-{MAX_LEADS_COUNT})"
            except ValueError:
                return False, "Количество лидов должно быть числом"

    if prefix in ["segment", "city"]:
        if len(params) > 1:
            try:
                idx = int(params[1])
                if idx < 0 or idx > MAX_SEGMENT_INDEX:
                    return False, "Недопустимый индекс"
            except ValueError:
                return False, "Индекс должен быть числом"

    if prefix in ["segments", "users", "tickets"]:
        if len(params) > 1:
            try:
                page = int(params[1])
                if page < 0 or page > MAX_PAGE_NUMBER:
                    return False, "Недопустимый номер страницы"
            except ValueError:
                return False, "Номер страницы должен быть числом"

    if prefix in ["useract", "userappr"]:
        if len(params) > 1:
            try:
                telegram_id = int(params[1])
                if telegram_id <= 0:
                    return False, "Недопустимый Telegram ID"
            except ValueError:
                return False, "Telegram ID должен быть числом"

    if prefix == "ticketact":
        if len(params) > 1:
            try:
                ticket_id = int(params[1])
                if ticket_id <= 0:
                    return False, "Недопустимый ID тикета"
            except ValueError:
                return False, "ID тикета должен быть числом"

    # Проверка строковых параметров
    if prefix == "segmentact" and len(params) > 1:
        segment = params[1]
        if len(segment) > MAX_USERNAME_LENGTH:
            return False, f"Название сегмента слишком длинное (максимум {MAX_USERNAME_LENGTH})"

    if prefix == "import" and len(params) > 1:
        filename = params[1]
        if len(filename) > MAX_FILENAME_LENGTH:
            return False, f"Имя файла слишком длинное (максимум {MAX_FILENAME_LENGTH})"
        # Проверка на опасные символы
        if '..' in filename or '/' in filename or '\\' in filename:
            return False, "Недопустимые символы в имени файла"

    return True, None


def safe_parse_callback_data(data: str) -> Tuple[bool, Optional[Tuple[str, List[str]]], Optional[str]]:
    """
    Безопасный парсинг и валидация callback данных

    Args:
        data: Сырые callback данные

    Returns:
        (успех, (префикс, параметры) или None, сообщение об ошибке)

    Examples:
        >>> safe_parse_callback_data("confirm:yes:100")
        (True, ('confirm', ['yes', '100']), None)
        >>> safe_parse_callback_data("invalid:data")
        (False, None, "Неизвестный префикс: invalid")
    """
    try:
        prefix, params = parse_callback_data(data)

        if not prefix:
            return False, None, "Пустые callback данные"

        is_valid, error_msg = validate_callback_data(prefix, params)
        if not is_valid:
            return False, None, error_msg

        return True, (prefix, params), None

    except Exception as e:
        return False, None, f"Ошибка парсинга callback данных: {e}"


def create_callback_data(prefix: str, *params) -> str:
    """
    Создание callback data строки

    Args:
        prefix: Префикс callback данных
        *params: Параметры

    Returns:
        Callback data строка

    Examples:
        >>> create_callback_data("confirm", "yes", 100)
        'confirm:yes:100'
        >>> create_callback_data("segmentact", "freeze_segment", "Строительство")
        'segmentact:freeze_segment:Строительство'
    """
    # Валидация префикса
    if prefix not in CALLBACK_PREFIXES:
        raise ValueError(f"Неизвестный префикс: {prefix}")

    # Преобразование параметров в строки
    str_params = [str(p) for p in params]

    # Валидация
    is_valid, error_msg = validate_callback_data(prefix, str_params)
    if not is_valid:
        raise ValueError(error_msg)

    return f"{prefix}:{':'.join(str_params)}"
