"""
Модуль валидации CSV файлов

Проверяет:
- Размер файла (макс. 10MB)
- Кодировку UTF-8
- Наличие обязательных заголовков
- Валидность данных (телефоны, emails)
- Дубликаты внутри файла
"""
import csv
import re
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass

from ..logger import get_logger

logger = get_logger(__name__)


# Константы валидации
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_ROW_LENGTH = 5000  # Максимальная длина строки в символах
MAX_FIELD_LENGTH = {
    'phone': 20,
    'email': 320,
    'company_name': 500,
    'address': 2000,
    'city': 200,
    'segment': 200,
    'website': 500,
    'telegram': 100,
}


@dataclass
class ValidationError:
    """Ошибка валидации"""
    row_number: int
    field: str
    message: str
    value: Optional[str] = None


@dataclass
class ValidationResult:
    """Результат валидации"""
    is_valid: bool
    total_rows: int
    valid_rows: int
    errors: List[ValidationError]
    warnings: List[str]
    duplicates_found: int


class CSVValidator:
    """Валидатор CSV файлов"""

    # Обязательные заголовки (хотя бы один из списка)
    REQUIRED_HEADERS = {
        'Название компании',
        'Рабочий телефон',
        'Мобильный телефон',
    }

    # Допустимые заголовки
    ALLOWED_HEADERS = {
        'Название лида',
        'Название компании',
        'Рабочий телефон',
        'Мобильный телефон',
        'Адрес',
        'Населенный пункт',
        'Рабочий e-mail',
        'Корпоративный сайт',
        'Контакт Telegram',
        'Комментарий',
        'Ответственный',
        'Источник',
        'Стадия',
    }

    def __init__(self):
        self.errors: List[ValidationError] = []
        self.warnings: List[str] = []

    def validate_file(self, file_path: Path) -> ValidationResult:
        """
        Полная валидация CSV файла

        Args:
            file_path: Путь к файлу

        Returns:
            Результат валидации
        """
        self.errors = []
        self.warnings = []

        # 1. Проверка размера файла
        if not self._check_file_size(file_path):
            return ValidationResult(
                is_valid=False,
                total_rows=0,
                valid_rows=0,
                errors=self.errors,
                warnings=self.warnings,
                duplicates_found=0
            )

        # 2. Проверка кодировки и чтение
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Читаем первую строку для проверки заголовков
                first_line = f.readline()
                if len(first_line) > MAX_ROW_LENGTH:
                    self.errors.append(ValidationError(
                        row_number=1,
                        field='_file',
                        message=f'Длина первой строки превышает {MAX_ROW_LENGTH} символов',
                        value=f'{len(first_line)} символов'
                    ))
                    return ValidationResult(
                        is_valid=False,
                        total_rows=0,
                        valid_rows=0,
                        errors=self.errors,
                        warnings=self.warnings,
                        duplicates_found=0
                    )

        except UnicodeDecodeError as e:
            self.errors.append(ValidationError(
                row_number=0,
                field='_file',
                message=f'Неверная кодировка файла. Ожидается UTF-8. Ошибка: {e}',
                value=None
            ))
            return ValidationResult(
                is_valid=False,
                total_rows=0,
                valid_rows=0,
                errors=self.errors,
                warnings=self.warnings,
                duplicates_found=0
            )

        # 3. Валидация заголовков
        headers = self._validate_headers(file_path)
        if not headers:
            return ValidationResult(
                is_valid=False,
                total_rows=0,
                valid_rows=0,
                errors=self.errors,
                warnings=self.warnings,
                duplicates_found=0
            )

        # 4. Валидация данных
        total_rows, valid_rows, duplicates = self._validate_data(file_path, headers)

        is_valid = len(self.errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            total_rows=total_rows,
            valid_rows=valid_rows,
            errors=self.errors,
            warnings=self.warnings,
            duplicates_found=duplicates
        )

    def _check_file_size(self, file_path: Path) -> bool:
        """Проверка размера файла"""
        try:
            file_size = os.path.getsize(file_path)
            if file_size > MAX_FILE_SIZE_BYTES:
                self.errors.append(ValidationError(
                    row_number=0,
                    field='_file',
                    message=f'Размер файла превышает {MAX_FILE_SIZE_MB}MB',
                    value=f'{file_size / (1024 * 1024):.2f} MB'
                ))
                return False
            return True
        except OSError as e:
            self.errors.append(ValidationError(
                row_number=0,
                field='_file',
                message=f'Ошибка чтения файла: {e}',
                value=None
            ))
            return False

    def _validate_headers(self, file_path: Path) -> Optional[List[str]]:
        """Валидация заголовков CSV"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')
                headers = reader.fieldnames

                if not headers:
                    self.errors.append(ValidationError(
                        row_number=0,
                        field='_file',
                        message='Файл не содержит заголовков',
                        value=None
                    ))
                    return None

                # Проверяем наличие хотя бы одного обязательного поля
                has_required = any(
                    h in headers for h in self.REQUIRED_HEADERS
                )
                if not has_required:
                    self.errors.append(ValidationError(
                        row_number=0,
                        field='_headers',
                        message=f'Отсутствуют обязательные поля. Ожидалось хотя бы одно из: {", ".join(self.REQUIRED_HEADERS)}',
                        value=f'Найдено: {", ".join(headers)}'
                    ))
                    return None

                # Предупреждение о неизвестных полях
                unknown_headers = set(headers) - self.ALLOWED_HEADERS
                if unknown_headers:
                    self.warnings.append(
                        f'Обнаружены неизвестные поля: {", ".join(unknown_headers)}. Они будут проигнорированы.'
                    )

                return headers

        except Exception as e:
            self.errors.append(ValidationError(
                row_number=0,
                field='_file',
                message=f'Ошибка чтения заголовков: {e}',
                value=None
            ))
            return None

    def _validate_data(
        self,
        file_path: Path,
        headers: List[str]
    ) -> Tuple[int, int, int]:
        """
        Валидация данных в файле

        Returns:
            (total_rows, valid_rows, duplicates_count)
        """
        total_rows = 0
        valid_rows = 0
        duplicates = 0
        seen_phones: Set[str] = set()
        seen_emails: Set[str] = set()

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')

                for row_num, row in enumerate(reader, start=2):  # Начинаем с 2 (1 - заголовки)
                    total_rows += 1
                    row_valid = True

                    # Валидация телефонов
                    phone_fields = ['Рабочий телефон', 'Мобильный телефон']
                    for field in phone_fields:
                        if field in row and row[field]:
                            phone = normalize_phone(row[field])
                            if not phone:
                                self.warnings.append(
                                    f'Строка {row_num}: Неверный формат телефона в поле "{field}": {row[field]}'
                                )
                            elif phone in seen_phones:
                                duplicates += 1
                                self.warnings.append(
                                    f'Строка {row_num}: Дубликат телефона {phone} (первое вхождение в строке {seen_phones.index(phone) + 2})'
                                )
                            else:
                                seen_phones.add(phone)

                    # Валидация email
                    if 'Рабочий e-mail' in row and row['Рабочий e-mail']:
                        email = row['Рабочий e-mail'].strip()
                        if not validate_email(email):
                            self.warnings.append(
                                f'Строка {row_num}: Неверный формат email: {email}'
                            )
                        elif email in seen_emails:
                            duplicates += 1
                            self.warnings.append(
                                f'Строка {row_num}: Дубликат email {email}'
                            )
                        else:
                            seen_emails.add(email)

                    # Проверка длин полей
                    for field, value in row.items():
                        if value:
                            max_len = MAX_FIELD_LENGTH.get(field.lower(), 500)
                            if len(value) > max_len:
                                self.warnings.append(
                                    f'Строка {row_num}: Поле "{field}" превышает {max_len} символов ({len(value)} символов). Будет обрезано.'
                                )

                    if row_valid:
                        valid_rows += 1

        except Exception as e:
            self.errors.append(ValidationError(
                row_number=total_rows,
                field='_file',
                message=f'Ошибка чтения данных: {e}',
                value=None
            ))

        return total_rows, valid_rows, duplicates


def normalize_phone(phone: str) -> Optional[str]:
    """
    Нормализация телефона

    Args:
        phone: Телефон для нормализации

    Returns:
        Нормализованный телефон или None
    """
    if not phone:
        return None

    # Удаляем всё кроме цифр и +
    phone = re.sub(r'[^\d+]', '', phone)

    if not phone:
        return None

    # Удаляем все + кроме первого
    phone = phone.replace('+', '', phone.count('+') - 1) if phone.count('+') > 1 else phone

    if phone.startswith('8') and len(phone) == 11:
        phone = '+7' + phone[1:]
    elif phone.startswith('7') and len(phone) == 11:
        phone = '+7' + phone[1:]
    elif phone.startswith('+7') and len(phone) == 12:
        pass  # Уже правильный формат
    elif phone.isdigit() and len(phone) == 10:
        phone = '+7' + phone
    elif phone.startswith('+') and len(phone) == 12:
        pass  # Уже правильный формат
    else:
        # Пытаемся привести к правильному формату
        if phone.startswith('+'):
            digits = phone[1:]
        else:
            digits = phone

        if len(digits) == 11 and digits.startswith('7'):
            phone = '+7' + digits[1:]
        elif len(digits) == 10:
            phone = '+7' + digits

    # Финальная проверка
    if not re.match(r'^\+7\d{10}$', phone):
        return None

    return phone


def validate_email(email: str) -> bool:
    """
    Валидация email

    Args:
        email: Email для проверки

    Returns:
        True если email валиден
    """
    if not email or len(email) > 320:
        return False

    # Простая проверка формата
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


async def validate_csv_file(file_path: Path) -> ValidationResult:
    """
    Асинхронная валидация CSV файла

    Args:
        file_path: Путь к файлу

    Returns:
        Результат валидации
    """
    validator = CSVValidator()
    return validator.validate_file(file_path)
