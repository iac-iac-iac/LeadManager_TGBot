"""
Утилиты для работы с телефонами

Единый модуль для нормализации и валидации телефонных номеров
"""
import re
from typing import Optional


def normalize_phone(phone: str) -> Optional[str]:
    """
    Нормализация телефона к формату +7XXXXXXXXXX

    Поддерживаемые форматы:
    - +7XXXXXXXXXX
    - 8XXXXXXXXXX
    - 7XXXXXXXXXX
    - XXXXXXXXXX (10 цифр)
    - +7 (XXX) XXX-XX-XX
    - 8-XXX-XXX-XX-XX

    Args:
        phone: Телефон в любом формате

    Returns:
        Нормализованный телефон или None если некорректный

    Examples:
        >>> normalize_phone("+7 (495) 123-45-67")
        '+74951234567'
        >>> normalize_phone("84951234567")
        '+74951234567'
        >>> normalize_phone("4951234567")
        '+74951234567'
    """
    if not phone:
        return None

    # Удаляем все нецифровые символы кроме +
    phone = re.sub(r"[^\d+]", "", phone).strip()

    if not phone:
        return None

    # Обработка различных форматов
    if phone.startswith('+8') and len(phone) == 12:
        # +8XXXXXXXXXX → +7XXXXXXXXXX
        phone = '+7' + phone[2:]
    elif phone.startswith('8') and len(phone) == 11:
        # 8XXXXXXXXXX → +7XXXXXXXXXX
        phone = '+7' + phone[1:]
    elif phone.startswith('7') and len(phone) == 11:
        # 7XXXXXXXXXX → +7XXXXXXXXXX
        phone = '+' + phone
    elif phone.startswith('+7') and len(phone) == 12:
        # Уже правильный формат
        pass
    elif phone.isdigit() and len(phone) == 10:
        # XXXXXXXXXX → +7XXXXXXXXXX
        phone = '+7' + phone
    elif phone.startswith('+') and len(phone) == 12:
        # +XXXXXXXXXX → оставляем как есть
        pass
    else:
        # Некорректный формат
        return None

    # Финальная проверка: должен быть +7 и 11 цифр
    if not phone.startswith('+7') or len(phone) != 12:
        return None

    return phone


def normalize_phone_for_bitrix24(phone: str) -> Optional[str]:
    """
    Нормализация телефона для поиска в Bitrix24

    Bitrix24 хранит телефоны без + (например: 73432472960)

    Args:
        phone: Телефон в любом формате

    Returns:
        Телефон без + для поиска в Bitrix24

    Examples:
        >>> normalize_phone_for_bitrix24("+74951234567")
        '74951234567'
        >>> normalize_phone_for_bitrix24("84951234567")
        '74951234567'
    """
    normalized = normalize_phone(phone)
    if not normalized:
        return None

    # Удаляем +
    return normalized.lstrip('+')


def validate_phone(phone: str) -> tuple[bool, Optional[str]]:
    """
    Валидация телефона

    Args:
        phone: Телефон для проверки

    Returns:
        (успех, сообщение об ошибке или None)

    Examples:
        >>> validate_phone("+74951234567")
        (True, None)
        >>> validate_phone("123")
        (False, "Некорректный формат телефона")
    """
    normalized = normalize_phone(phone)

    if normalized:
        return True, None
    else:
        return False, "Некорректный формат телефона"


def format_phone_display(phone: str) -> str:
    """
    Форматирование телефона для отображения

    Args:
        phone: Телефон в формате +7XXXXXXXXXX

    Returns:
        Телефон в формате +7 (XXX) XXX-XX-XX

    Examples:
        >>> format_phone_display("+74951234567")
        '+7 (495) 123-45-67'
    """
    if not phone or len(phone) != 12:
        return phone

    return f"+7 ({phone[2:5]}) {phone[5:8]}-{phone[8:10]}-{phone[10:12]}"
