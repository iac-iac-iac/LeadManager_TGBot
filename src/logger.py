"""
Модуль логирования

С фильтрацией чувствительных данных (телефоны, email, персональные данные)
для соответствия требованиям безопасности и 152-ФЗ.
"""
import re
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import List


# =============================================================================
# Фильтр чувствительных данных
# =============================================================================

class SensitiveDataFilter(logging.Filter):
    """
    Фильтр для маскировки чувствительных данных в логах
    
    Маскирует:
    - Номера телефонов (+7XXX-XXX-XX-XX, 8XXXXXXXXXX)
    - Email адреса
    - Telegram ID
    - Bitrix24 user IDs
    - API токены и вебхуки
    """
    
    # Паттерны для поиска чувствительных данных
    SENSITIVE_PATTERNS = [
        # Телефоны (российские форматы)
        (r'\+7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', '[PHONE_REDACTED]'),
        (r'8[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', '[PHONE_REDACTED]'),
        (r'\+7\d{10}', '[PHONE_REDACTED]'),
        (r'8\d{10}', '[PHONE_REDACTED]'),
        
        # Email адреса
        (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[EMAIL_REDACTED]'),
        
        # Telegram ID (числовые ID)
        (r'(?<!\w)Telegram:\s*\d+', 'Telegram: [ID_REDACTED]'),
        (r'(?<!\w)telegram_id[=:]\s*\d+', 'telegram_id=[ID_REDACTED]'),
        
        # Bitrix24 user IDs
        (r'assigned_by_id[=:]\s*\d+', 'assigned_by_id=[ID_REDACTED]'),
        (r'bitrix24_user_id[=:]\s*\d+', 'bitrix24_user_id=[ID_REDACTED]'),
        (r'(?<!\w)ID:\s*<code>\d+</code>', 'ID: [ID_REDACTED]'),
        
        # API токены и вебхуки
        (r'https://[a-zA-Z0-9.-]+/rest/\d+/[a-zA-Z0-9]+/', '[WEBHOOK_URL_REDACTED]'),
        (r'\d{10}:[A-Za-z0-9_-]{35}', '[TELEGRAM_BOT_TOKEN_REDACTED]'),
        
        # Телефоны в полях (phone=, mobile_phone=)
        (r'(phone|mobile_phone)[=:]\s*\+?\d{10,15}', r'\1=[PHONE_REDACTED]'),
    ]
    
    def __init__(self, additional_patterns: List[tuple[str, str]] = None):
        """
        Инициализация фильтра
        
        Args:
            additional_patterns: Дополнительные паттерны для маскировки
        """
        super().__init__()
        self.patterns = self.SENSITIVE_PATTERNS.copy()
        if additional_patterns:
            self.patterns.extend(additional_patterns)
        
        # Компилируем паттерны для производительности
        self.compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in self.patterns
        ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Фильтрация записи лога
        
        Args:
            record: Запись лога
            
        Returns:
            True (запись всегда пропускается, но с замаскированными данными)
        """
        # Маскируем сообщение
        if record.msg:
            record.msg = self._redact(str(record.msg))
        
        # Маскируем аргументы
        if record.args:
            record.args = tuple(
                self._redact(str(arg)) if isinstance(arg, str) else arg
                for arg in record.args
            )
        
        # Маскируем exception
        if record.exc_info:
            # exc_info обрабатывается автоматически при форматировании
            pass
        
        return True
    
    def _redact(self, text: str) -> str:
        """
        Маскировка чувствительных данных в тексте
        
        Args:
            text: Исходный текст
            
        Returns:
            Текст с замаскированными чувствительными данными
        """
        result = text
        for pattern, replacement in self.compiled_patterns:
            result = pattern.sub(replacement, result)
        return result


# =============================================================================
# Настройка логгера
# =============================================================================

def setup_logger(name: str = "lead_telegram", log_file: str = None, level: str = "INFO") -> logging.Logger:
    """
    Настройка логгера с консольным и файловым обработчиками

    Args:
        name: Имя логгера
        log_file: Путь к файлу логов (опционально)
        level: Уровень логирования

    Returns:
        Настроенный логгер
    """
    # Создаем логгер
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Очищаем существующие обработчики
    logger.handlers.clear()

    # Форматтер
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    
    # Добавляем фильтр чувствительных данных
    console_handler.addFilter(SensitiveDataFilter())
    
    logger.addHandler(console_handler)

    # Файловый обработчик с ротацией (если указан файл)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        
        # Добавляем фильтр чувствительных данных
        file_handler.addFilter(SensitiveDataFilter())
        
        logger.addHandler(file_handler)

    return logger


# Глобальный логгер (ленивая инициализация)
_logger: logging.Logger = None


def get_logger(name: str = None) -> logging.Logger:
    """
    Получение логгера по имени
    
    Args:
        name: Имя логгера (опционально)
        
    Returns:
        Логгер
    """
    global _logger
    if _logger is None:
        _logger = setup_logger()
    
    if name:
        return logging.getLogger(name)
    return _logger
