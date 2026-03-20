"""
Обработчики администратора

Импорт CSV, проверка дублей, статистика, управление сегментами, очистка
"""
import re
import uuid
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from ..states import AdminStates
from ..messages.texts import (
    IMPORT_CSV_SELECT,
    IMPORT_CSV_FILE_LIST,
    IMPORT_CSV_UPLOAD_NEW,
    IMPORT_CSV_SUCCESS,
    IMPORT_CSV_ERROR,
    ADMIN_MAIN_MENU,
)
from ..keyboards.keyboard_factory import (
    create_back_keyboard,
)
from ...database import crud
from ...csv_import.csv_importer import import_csv_from_uploads, import_csv_file
from ...bitrix24.client import get_bitrix24_client
from ...bitrix24.duplicates import run_duplicate_check
from ...config import get_config
from ...logger import get_logger


# =============================================================================
# Валидация имён файлов
# =============================================================================

MAX_FILENAME_LENGTH = 255
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def validate_filename(filename: str) -> tuple[bool, str]:
    """
    Валидация имени файла для защиты от path traversal и других атак
    
    Args:
        filename: Исходное имя файла
        
    Returns:
        Tuple[bool, str]: (успех, сообщение об ошибке или безопасное имя)
    """
    if not filename:
        return False, "Имя файла пустое"
    
    # Базовая проверка длины
    if len(filename) > MAX_FILENAME_LENGTH:
        return False, f"Имя файла слишком длинное (максимум {MAX_FILENAME_LENGTH} символов)"
    
    # Проверка на опасные символы (path traversal)
    dangerous_patterns = [
        '..', '/', '\\', '\x00',  # Path traversal и null-байты
        '|', '<', '>', '?', '*',  # Windows reserved chars
        '"', "'",                  # Кавычки
        ';', '&', '$', '`',        # Shell injection
    ]
    
    for pattern in dangerous_patterns:
        if pattern in filename:
            return False, f"Имя файла содержит недопустимые символы"
    
    # Проверка расширения
    if not filename.lower().endswith('.csv'):
        return False, "Разрешены только CSV файлы"
    
    # Удаляем любые потенциально опасные Unicode-символы (control characters)
    filename_clean = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
    
    # Извлекаем только имя файла (на случай если путь всё же просочился)
    safe_filename = Path(filename_clean).name
    
    # Генерируем уникальное безопасное имя с UUID
    unique_filename = f"{uuid.uuid4()}_{safe_filename}"
    
    return True, unique_filename

logger = get_logger(__name__)

router = Router()


# =============================================================================
# Главное меню админа
# =============================================================================

@router.callback_query(F.data == "admin_menu")
async def handle_admin_menu(callback: CallbackQuery):
    """Показ главного меню админа"""
    from ..keyboards.keyboard_factory import create_admin_main_menu
    
    await callback.message.answer(
        ADMIN_MAIN_MENU,
        reply_markup=create_admin_main_menu()
    )
    await callback.answer()


# =============================================================================
# Импорт CSV: Выбор файла
# =============================================================================

@router.callback_query(F.data == "admin_import_csv")
async def handle_import_csv_menu(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Меню импорта CSV"""
    config = get_config()
    uploads_folder = config.uploads_folder

    # Получаем список CSV файлов
    csv_files = list(uploads_folder.glob("*.csv"))

    if not csv_files:
        # Удаляем предыдущее сообщение
        try:
            await callback.message.delete()
        except Exception:
            pass
        
        await callback.message.answer(
            "📁 В папке uploads нет CSV файлов.\n\n"
            "Отправьте файл или поместите его в папку uploads."
        )
        await callback.answer()
        return

    # Удаляем предыдущее сообщение
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Формируем список
    files_text = "\n".join([f"📄 {f.name}" for f in csv_files[:10]])
    if len(csv_files) > 10:
        files_text += f"\n... и ещё {len(csv_files) - 10} файлов"

    await callback.message.answer(
        IMPORT_CSV_FILE_LIST.format(files=files_text),
        reply_markup=create_back_keyboard("admin_menu")
    )

    # Устанавливаем состояние выбора файла
    await state.set_state(AdminStates.IMPORT_FILE_SELECT)
    await callback.answer()


# =============================================================================
# Импорт CSV: Выбор из списка
# =============================================================================

@router.message(StateFilter(AdminStates.IMPORT_FILE_SELECT))
async def handle_file_select(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка выбора файла из списка"""
    filename = message.text.strip()
    
    # Проверяем файл
    config = get_config()
    file_path = config.uploads_folder / filename
    
    if not file_path.exists():
        await message.answer(
            f"❌ Файл {filename} не найден.\n"
            "Выберите другой файл:"
        )
        return
    
    # Импортируем
    await message.answer(f"⏳ Запуск импорта файла {filename}...")

    try:
        result = await import_csv_file(session, file_path)

        if result.get("imported", 0) > 0:
            await message.answer(
                IMPORT_CSV_SUCCESS.format(
                    count=result["imported"],
                    filename=filename
                ) + "\n\n"
                f"📌 Для проверки на дубли используйте кнопку '🔍 Проверка дублей' в главном меню админа."
            )
        elif result.get("already_imported", False):
            await message.answer(
                f"⚠️ Файл '{filename}' уже был импортирован ранее.\n"
                f"Повторная загрузка невозможна."
            )
        else:
            await message.answer(
                IMPORT_CSV_ERROR.format(error="Файл пуст или все лиды уже существуют")
            )

    except Exception as e:
        logger.error(f"Ошибка импорта файла {filename}: {e}")
        await message.answer(
            IMPORT_CSV_ERROR.format(error=str(e))
        )

    await state.clear()


# =============================================================================
# Импорт CSV: Загрузка нового файла
# =============================================================================

@router.message(StateFilter(AdminStates.IMPORT_FILE_SELECT), F.document)
async def handle_file_upload(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка загруженного файла с валидацией и проверкой размера"""
    document = message.document

    await message.answer(f"⏳ Проверка файла {document.file_name}...")

    try:
        # Получаем информацию о файле для проверки размера
        file = await message.bot.get_file(document.file_id)
        
        # Проверка размера файла (защита от DoS)
        if hasattr(file, 'file_size') and file.file_size > MAX_FILE_SIZE:
            await message.answer(
                f"❌ Файл слишком большой.\n"
                f"Максимальный размер: {MAX_FILE_SIZE // (1024 * 1024)} MB"
            )
            await state.clear()
            return

        # Валидация имени файла (защита от path traversal)
        is_valid, result = validate_filename(document.file_name)
        if not is_valid:
            await message.answer(f"❌ Ошибка валидации файла: {result}")
            await state.clear()
            return
        
        safe_filename = result
        config = get_config()
        file_path = config.uploads_folder / safe_filename

        # Скачиваем файл
        await message.answer(f"⏳ Сохранение файла...")
        downloaded = await message.bot.download_file(file.file_path, file_path)

        # Импортируем
        result = await import_csv_file(session, file_path, auto_check_duplicates=False)

        if result.get("imported", 0) > 0:
            await message.answer(
                IMPORT_CSV_SUCCESS.format(
                    count=result["imported"],
                    filename=document.file_name
                )
            )
        else:
            await message.answer(
                IMPORT_CSV_ERROR.format(error="Файл пуст или ошибка импорта")
            )

    except Exception as e:
        logger.error(f"Ошибка загрузки файла {document.file_name}: {e}")
        await message.answer(
            IMPORT_CSV_ERROR.format(error=str(e))
        )

    await state.clear()
