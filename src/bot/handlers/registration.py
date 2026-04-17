"""
Обработчик регистрации менеджеров

Процесс регистрации:
1. Менеджер нажимает /start
2. Бот просит ввести Имя и Фамилию
3. Создаётся заявка со статусом PENDING_APPROVAL
4. Админ получает уведомление
5. Админ подтверждает заявку → статус ACTIVE
"""
import re
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, Command, StateFilter

from ..states import ManagerStates
from ..messages.texts import (
    REGISTRATION_START,
    REGISTRATION_SUCCESS,
    REGISTRATION_ALREADY,
    MANAGER_MAIN_MENU,
)
from ..keyboards.keyboard_factory import create_manager_main_menu, create_admin_main_menu, create_main_menu_reply_keyboard
from ...database import crud
from ...database.models import User, UserRole, UserStatus, AsyncSession
from ...config import Config
from ...logger import get_logger

logger = get_logger(__name__)

router = Router()


# =============================================================================
# Валидация данных пользователя
# =============================================================================

MAX_NAME_LENGTH = 200
MIN_NAME_LENGTH = 2


def validate_full_name(text: str) -> tuple[bool, str]:
    """
    Валидация ФИО пользователя
    
    Args:
        text: Исходный текст
        
    Returns:
        Tuple[bool, str]: (успех, сообщение об ошибке или очищенное имя)
    """
    if not text:
        return False, "Имя не может быть пустым"
    
    # Проверка длины
    if len(text) > MAX_NAME_LENGTH:
        return False, f"Имя слишком длинное (максимум {MAX_NAME_LENGTH} символов)"
    
    if len(text) < MIN_NAME_LENGTH:
        return False, f"Имя слишком короткое (минимум {MIN_NAME_LENGTH} символа)"
    
    # Удаляем control characters
    text_clean = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    text_clean = text_clean.strip()
    
    # Проверка на минимальное количество слов (Имя + Фамилия)
    name_parts = text_clean.split()
    if len(name_parts) < 2:
        return False, "Введите Имя и Фамилию через пробел (например: Иванов Иван)"

    # Проверка разрешённых символов (кириллица, латиница, пробел, дефис, апостроф)
    # Используем Unicode диапазоны вместо \p{Cyrillic} и \p{Latin}
    # Кириллица: \u0400-\u04FF, Латиница: a-zA-Z
    if not re.match(r'^[a-zA-Z\u0400-\u04FF\s\'\-]+$', text_clean, flags=re.UNICODE):
        return False, "Имя должно содержать только буквы (кириллица или латиница)"

    # Проверка на повторяющиеся пробелы
    if '  ' in text_clean:
        return False, "Имя не должно содержать повторяющиеся пробелы"

    return True, text_clean[:MAX_NAME_LENGTH]


def validate_username(username: str | None) -> str | None:
    """
    Валидация username Telegram
    
    Args:
        username: Исходный username
        
    Returns:
        str | None: Очищенный username или None
    """
    if not username:
        return None
    
    # Telegram username может содержать буквы, цифры, подчёркивания
    # и должен быть от 5 до 32 символов
    if len(username) < 5 or len(username) > 32:
        return None
    
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return None
    
    return username


# =============================================================================
# Регистрация: Начало
# =============================================================================

@router.message(CommandStart())
async def handle_start_registration(message: Message, session: AsyncSession, config: Config, state: FSMContext):
    """
    Начало регистрации пользователя

    Если пользователь уже зарегистрирован - показываем меню.
    Если это админ из конфига - создаём автоматически и показываем меню админа.
    """
    from ..keyboards.keyboard_factory import create_admin_main_menu

    telegram_id = str(message.from_user.id)
    full_name = message.from_user.full_name or ""
    username = message.from_user.username

    # Проверяем, является ли пользователь админом из конфига
    is_config_admin = int(telegram_id) in config.admin_telegram_ids

    # Проверяем существующего пользователя
    user = await crud.get_user_by_telegram_id(session, telegram_id)

    if user:
        if user.status == UserStatus.ACTIVE:
            # Уже активный пользователь - показываем меню по роли
            if user.role == UserRole.ADMIN or is_config_admin:
                await message.answer(
                    "👋 Добро пожаловать, администратор!",
                    reply_markup=create_admin_main_menu()
                )
            else:
                await message.answer(
                    f"Добро пожаловать, {user.full_name or 'коллега'}! 👋",
                    reply_markup=create_manager_main_menu()
                )
            return
        elif user.status == UserStatus.PENDING_APPROVAL:
            # Ожидает подтверждения (не должно быть для админов из конфига)
            await message.answer(
                "Ваша заявка ещё на рассмотрении у администратора.\n"
                "Как только вас подтвердят, вы сможете работать с лидами."
            )
            return
        elif user.status == UserStatus.REJECTED:
            # Отклонен
            await message.answer(
                "К сожалению, ваша заявка была отклонена.\n"
                "Обратитесь к администратору за подробностями."
            )
            return

    # Новый пользователь
    if is_config_admin:
        # Автоматически создаём админа из конфига
        try:
            user = await crud.create_user(
                session,
                telegram_id=telegram_id,
                full_name=full_name,
                username=username,
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE
            )

            logger.info(f"Администратор автоматически зарегистрирован: {full_name} (Telegram: {telegram_id})")

            await message.answer(
                f"👋 Добро пожаловать, {full_name or 'администратор'}!",
                reply_markup=create_admin_main_menu()
            )
            return

        except Exception as e:
            logger.error(f"Ошибка при автоматической регистрации админа {telegram_id}: {type(e).__name__}: {e}")
            await message.answer("⚠️ Произошла ошибка при регистрации. Попробуйте позже.")
            return

    # Обычный пользователь - начинаем регистрацию
    await message.answer(REGISTRATION_START)

    # Устанавливаем состояние ожидания имени
    await state.set_state(ManagerStates.REGISTRATION_NAME)
    await message.answer("Введите ваше Имя и Фамилию:")


# =============================================================================
# Регистрация: Получение имени
# =============================================================================

@router.message(StateFilter(ManagerStates.REGISTRATION_NAME))
async def handle_registration_name(message: Message, state: FSMContext, session: AsyncSession, config: Config):
    """
    Обработка введенного имени пользователя

    Создаем заявку со статусом PENDING_APPROVAL
    """
    telegram_id = str(message.from_user.id)
    username = message.from_user.username

    # Валидация имени
    is_valid, result = validate_full_name(message.text)
    
    if not is_valid:
        await message.answer(
            f"⚠️ {result}\n\n"
            "Пожалуйста, введите Имя и Фамилию через пробел.\n"
            "Пример: Иванов Иван"
        )
        return
    
    full_name = result
    username_clean = validate_username(username)

    try:
        # Создаем пользователя
        user = await crud.create_user(
            session,
            telegram_id=telegram_id,
            full_name=full_name,
            username=username_clean,
            role=UserRole.MANAGER,
            status=UserStatus.PENDING_APPROVAL
        )

        logger.info(f"Создана заявка на регистрацию: {full_name} (Telegram: {telegram_id})")

        # Отправляем подтверждение менеджеру
        await message.answer(
            "✅ Ваша заявка на регистрацию принята!\n\n"
            f"Имя: {full_name}\n"
            f"Telegram: @{username_clean or 'не указан'}\n\n"
            "📌 Теперь администратор должен подтвердить вашу заявку.\n"
            "Как только вас подтвердят, вы сможете получать лиды."
        )

        # Отправляем уведомление админам
        from sqlalchemy import select
        from ...database.models import User as UserModel

        # Получаем всех админов
        admins_result = await session.execute(
            select(UserModel.telegram_id).where(
                UserModel.role == UserRole.ADMIN,
                UserModel.status == UserStatus.ACTIVE
            )
        )
        admin_ids = [row[0] for row in admins_result.all()]

        # Добавляем админов из конфига
        for admin_id in config.admin_telegram_ids:
            admin_id_str = str(admin_id)
            if admin_id_str not in admin_ids:
                admin_ids.append(admin_id_str)

        # Отправляем уведомление каждому админу
        for admin_id in admin_ids:
            try:
                await message.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"🔔 <b>Новая заявка на регистрацию!</b>\n\n"
                        f"👤 Менеджер: {full_name}\n"
                        f"📱 Telegram: @{username_clean or 'не указан'}\n"
                        f"ID: <code>{telegram_id}</code>\n\n"
                        f"Перейдите в '👥 Заявки менеджеров' для подтверждения."
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {e}")

        # Очищаем состояние
        await state.clear()

    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка при регистрации пользователя {telegram_id}: {type(e).__name__}: {e}")
        await message.answer(
            "⚠️ Произошла ошибка при регистрации.\n"
            "Пожалуйста, попробуйте позже или обратитесь к администратору."
        )


# =============================================================================
# Регистрация: Отмена
# =============================================================================

@router.message(StateFilter(ManagerStates.REGISTRATION_NAME), F.text.lower().in_(["отмена", "cancel", "/cancel"]))
async def handle_registration_cancel(message: Message, state: FSMContext):
    """Отмена регистрации"""
    await state.clear()
    await message.answer("Регистрация отменена.\nНажмите /start чтобы начать заново.")


# =============================================================================
# Команда /menu - главное меню
# =============================================================================

@router.message(Command("menu"))
async def cmd_menu(message: Message, session: AsyncSession, config: Config):
    """Обработчик команды /menu - показать главное меню"""
    telegram_id = str(message.from_user.id)
    
    # Проверяем пользователя
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    
    if not user:
        await message.answer(
            "⚠️ Сначала нажмите /start для регистрации",
            reply_markup=create_manager_main_menu()
        )
        return
    
    if user.status != UserStatus.ACTIVE:
        await message.answer("⚠️ Ваша заявка ещё не подтверждена администратором")
        return
    
    # Проверяем роль
    is_admin = user.role == UserRole.ADMIN or int(telegram_id) in config.admin_telegram_ids
    
    # Сначала удаляем команду /menu от пользователя
    try:
        await message.delete()
    except Exception:
        pass
    
    # Показываем меню по роли
    if is_admin:
        await message.answer(
            "👋 Главное меню администратора",
            reply_markup=create_admin_main_menu()
        )
    else:
        await message.answer(
            f"👋 Главное меню, {user.full_name or 'коллега'}!",
            reply_markup=create_manager_main_menu()
        )
