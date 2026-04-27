"""
Общие утилиты для клавиатур (экранирование, safe_text).
"""
from typing import Optional
from html import escape

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
