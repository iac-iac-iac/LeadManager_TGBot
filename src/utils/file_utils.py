"""
Утилиты для безопасной работы с файлами

Защита от Path Traversal и других уязвимостей
"""
import os
import re
import uuid
from pathlib import Path
from typing import Tuple, Optional


MAX_FILENAME_LENGTH = 255
ALLOWED_EXTENSIONS = {'.csv', '.txt', '.json', '.xml'}
DANGEROUS_PATTERNS = ['..', '\x00', '|', '<', '>', '*', ';', '&', '$', '`']


def validate_filename(filename: str, uploads_dir: Path) -> Tuple[bool, Optional[Path], Optional[str]]:
    """
    Валидация имени файла для безопасной загрузки

    Args:
        filename: Исходное имя файла
        uploads_dir: Директория для загрузок

    Returns:
        (успех, безопасный путь или None, сообщение об ошибке)

    Examples:
        >>> validate_filename("test.csv", Path("/uploads"))
        (True, Path("/uploads/uuid_test.csv"), None)
        >>> validate_filename("../etc/passwd", Path("/uploads"))
        (False, None, "Недопустимое имя файла")
    """
    # Проверка на пустое имя
    if not filename or not filename.strip():
        return False, None, "Имя файла не может быть пустым"

    filename = filename.strip()

    # Проверка длины
    if len(filename) > MAX_FILENAME_LENGTH:
        return False, None, f"Имя файла слишком длинное (максимум {MAX_FILENAME_LENGTH} символов)"

    # Проверка расширения
    file_ext = Path(filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return False, None, f"Недопустимое расширение файла (разрешены: {', '.join(ALLOWED_EXTENSIONS)})"

    # Проверка на опасные символы
    for pattern in DANGEROUS_PATTERNS:
        if pattern in filename:
            return False, None, "Имя файла содержит недопустимые символы"

    # Проверка на абсолютный путь
    if os.path.isabs(filename):
        return False, None, "Имя файла не должно содержать абсолютный путь"

    # Извлекаем только имя файла (без пути)
    safe_filename = Path(filename).name

    # Дополнительная проверка через regex (разрешаем только безопасные символы)
    if not re.match(r'^[a-zA-Z0-9_\-\.\s]+$', safe_filename):
        return False, None, "Имя файла содержит недопустимые символы"

    # Генерируем уникальное имя файла
    unique_filename = f"{uuid.uuid4()}_{safe_filename}"
    file_path = uploads_dir / unique_filename

    # Проверка, что путь внутри uploads_dir (защита от Path Traversal)
    try:
        resolved_path = file_path.resolve()
        resolved_uploads = uploads_dir.resolve()
        resolved_path.relative_to(resolved_uploads)
    except ValueError:
        return False, None, "Путь за пределами разрешённой директории"

    return True, file_path, None


def safe_read_file(file_path: Path, base_dir: Path) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Безопасное чтение файла

    Args:
        file_path: Путь к файлу
        base_dir: Базовая директория

    Returns:
        (успех, содержимое или None, сообщение об ошибке)
    """
    try:
        # Разрешаем абсолютный путь
        resolved_file = file_path.resolve()
        resolved_base = base_dir.resolve()

        # Проверяем, что файл внутри base_dir
        resolved_file.relative_to(resolved_base)

        # Читаем файл
        content = file_path.read_text(encoding='utf-8')
        return True, content, None

    except ValueError:
        return False, None, "Файл за пределами разрешённой директории"
    except FileNotFoundError:
        return False, None, "Файл не найден"
    except PermissionError:
        return False, None, "Нет прав на чтение файла"
    except Exception as e:
        return False, None, f"Ошибка чтения файла: {e}"


def safe_write_file(file_path: Path, content: str, base_dir: Path) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Безопасная запись файла

    Args:
        file_path: Путь к файлу
        content: Содержимое для записи
        base_dir: Базовая директория

    Returns:
        (успех, путь к файлу или None, сообщение об ошибке)
    """
    try:
        # Разрешаем абсолютный путь
        resolved_file = file_path.resolve()
        resolved_base = base_dir.resolve()

        # Проверяем, что файл внутри base_dir
        resolved_file.relative_to(resolved_base)

        # Создаём родительские директории
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Записываем файл
        file_path.write_text(content, encoding='utf-8')
        return True, str(file_path), None

    except ValueError:
        return False, None, "Путь за пределами разрешённой директории"
    except PermissionError:
        return False, None, "Нет прав на запись файла"
    except Exception as e:
        return False, None, f"Ошибка записи файла: {e}"


def check_file_permissions(file_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Проверка прав доступа к файлу (только для Unix)

    Args:
        file_path: Путь к файлу

    Returns:
        (успех, сообщение об ошибке или None)
    """
    if os.name != 'posix':
        # Windows не поддерживает Unix права
        return True, None

    try:
        file_stat = file_path.stat()
        st_mode = file_stat.st_mode

        # Проверка: файл не должен быть доступен для чтения другими
        if st_mode & 0o004:
            return False, "Файл доступен для чтения другими пользователями"

        # Проверка: файл не должен быть доступен для записи другими
        if st_mode & 0o002:
            return False, "Файл доступен для записи другими пользователями"

        return True, None

    except FileNotFoundError:
        return False, "Файл не найден"
    except Exception as e:
        return False, f"Ошибка проверки прав: {e}"


def get_secure_temp_filename(base_dir: Path, extension: str = ".tmp") -> Path:
    """
    Генерация безопасного временного имени файла

    Args:
        base_dir: Базовая директория
        extension: Расширение файла

    Returns:
        Путь к временному файлу
    """
    unique_name = f"{uuid.uuid4()}{extension}"
    return base_dir / unique_name


def cleanup_dangerous_chars(filename: str) -> str:
    """
    Очистка имени файла от опасных символов

    Args:
        filename: Исходное имя файла

    Returns:
        Очищенное имя файла
    """
    result = filename

    # Удаляем опасные символы
    for pattern in DANGEROUS_PATTERNS:
        result = result.replace(pattern, '_')

    # Удаляем абсолютные пути
    result = Path(result).name

    # Оставляем только безопасные символы
    result = re.sub(r'[^a-zA-Z0-9_\-.]', '_', result)

    # Ограничиваем длину
    if len(result) > MAX_FILENAME_LENGTH:
        name, ext = os.path.splitext(result)
        max_name_len = MAX_FILENAME_LENGTH - len(ext)
        result = name[:max_name_len] + ext

    return result
