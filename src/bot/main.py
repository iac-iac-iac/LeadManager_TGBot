"""
Telegram-бот для раздачи холодных лидов с интеграцией в Bitrix24

Точка входа приложения
"""
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_config, Config
from src.logger import setup_logger, get_logger
from src.database.models import DatabaseManager, User, UserRole, UserStatus
from src.database import crud
from src.database.migrations import initialize_database
from src.bitrix24.client import get_bitrix24_client
from src.bot.middleware.access import AccessMiddleware
from src.bot.middleware.database import DatabaseSessionMiddleware
from src.bot.middleware.rate_limit import RateLimitMiddleware
from src.bot.keyboards.keyboard_factory import (
    create_manager_main_menu,
    create_admin_main_menu,
)
from src.bot.messages.texts import (
    MANAGER_MAIN_MENU,
    ADMIN_MAIN_MENU,
)

# Настройка логгера
logger = get_logger(__name__)


# =============================================================================
# Инициализация
# =============================================================================

def init_config() -> Config:
    """Инициализация конфигурации"""
    return get_config()


async def init_database(config: Config) -> DatabaseManager:
    """Инициализация базы данных"""
    db_manager = DatabaseManager(str(config.database_path))
    
    # Создаем таблицы и применяем миграции
    await initialize_database(db_manager)
    
    logger.info(f"База данных инициализирована: {config.database_path}")
    
    return db_manager


def init_bot(config: Config) -> Bot:
    """Инициализация бота"""
    # Настраиваем прокси если указан
    proxy_settings = {}
    if config.telegram.proxy_url:
        proxy_settings["proxy"] = config.telegram.proxy_url
    
    # Создаём сессию с увеличенным таймаутом
    from aiogram.client.session.aiohttp import AiohttpSession
    
    session = AiohttpSession(
        timeout=config.telegram.request_timeout,
        **proxy_settings
    )
    
    bot = Bot(
        token=config.telegram.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    
    logger.info("Бот инициализирован")
    
    return bot


# =============================================================================
# Обработчики команд
# =============================================================================

async def cmd_start(message: Message, session_factory, config: Config):
    """
    Обработчик команды /start
    
    Регистрация пользователя или показ главного меню
    """
    from sqlalchemy.ext.asyncio import AsyncSession
    
    telegram_id = str(message.from_user.id)
    full_name = message.from_user.full_name or ""
    username = message.from_user.username
    
    async with session_factory() as session:
        # Проверяем пользователя
        user = await crud.get_user_by_telegram_id(session, telegram_id)
        
        if not user:
            # Новый пользователь - показываем меню (регистрация через handlers)
            await message.answer(
                "👋 Привет! Я бот для управления холодными лидами.\n\n"
                "Для начала работы нажмите кнопку в меню.",
                reply_markup=create_manager_main_menu()
            )
            return
        
        # Пользователь уже зарегистрирован
        if user.status == UserStatus.ACTIVE:
            # Активный пользователь - показываем меню по роли
            is_admin = user.role == UserRole.ADMIN or int(telegram_id) in config.admin_telegram_ids
            
            if is_admin:
                await message.answer(
                    ADMIN_MAIN_MENU,
                    reply_markup=create_admin_main_menu()
                )
            else:
                await message.answer(
                    MANAGER_MAIN_MENU,
                    reply_markup=create_manager_main_menu()
                )
        else:
            # Ожидает подтверждения или отклонен
            await message.answer(
                f"Ваш статус: {user.status.value}\n"
                "Ожидайте подтверждения администратора."
            )


async def cmd_help(message: Message):
    """Обработчик команды /help"""
    help_text = """
📋 Команды бота:

/start - Запустить бота
/help - Показать эту справку
/menu - Показать главное меню

Для менеджеров:
- 📋 Получить лиды
- 📊 Моя статистика
- ℹ️ О боте

Для админов:
- 📥 Импорт CSV
- 🔍 Проверка дублей
- 📊 Общая статистика
- 📤 Экспорт отчётов
- ⚙️ Управление сегментами
- 🧹 Очистка данных
- 👥 Заявки менеджеров
"""
    await message.answer(help_text)


# =============================================================================
# Регистрация обработчиков
# =============================================================================

def register_handlers(dp: Dispatcher, db_manager: DatabaseManager, config: Config):
    """Регистрация всех обработчиков"""

    # Импортируем роутеры (абсолютные импорты)
    from src.bot.handlers.registration import router as registration_router
    from src.bot.handlers.manager_leads import router as manager_leads_router
    from src.bot.handlers.manager_stats import router as manager_stats_router
    from src.bot.handlers.admin import router as admin_router
    from src.bot.handlers.admin_segments import router as admin_segments_router
    from src.bot.handlers.admin_handlers import router as admin_handlers_router
    from src.bot.handlers.feedback import router as feedback_router
    from src.bot.handlers.admin_tickets import router as admin_tickets_router
    from src.bot.handlers.admin_bot_control import router as bot_control_router
    from src.bot.handlers.admin_load_leads import router as admin_load_leads_router

    # Создаем Bitrix24 клиент
    bitrix24_client = get_bitrix24_client(
        config.bitrix24.webhook_url,
        request_timeout=config.bitrix24.request_timeout,
        retry_attempts=config.bitrix24.retry_attempts,
        retry_delay=config.bitrix24.retry_delay,
        proxy_url=config.bitrix24.proxy_url
    )

    # Регистрируем роутеры
    dp.include_router(registration_router)
    dp.include_router(manager_leads_router)
    dp.include_router(manager_stats_router)
    dp.include_router(admin_router)
    dp.include_router(admin_segments_router)
    dp.include_router(admin_handlers_router)
    dp.include_router(feedback_router)
    dp.include_router(admin_tickets_router)
    dp.include_router(bot_control_router)
    dp.include_router(admin_load_leads_router)

    # Добавляем зависимости в data
    dp["bitrix24_client"] = bitrix24_client
    dp["session_factory"] = db_manager.async_session_factory
    dp["config"] = config

    logger.info("Обработчики зарегистрированы")


# =============================================================================
# Запуск
# =============================================================================

async def main():
    """Основная функция"""
    # Инициализация
    config = init_config()
    
    # Настраиваем логирование с файлом
    from src.logger import setup_logger
    logger = setup_logger(
        log_file=str(config.log_file),
        level=config.logging.level
    )
    
    logger.info("Запуск бота...")
    
    db_manager = await init_database(config)
    bot = init_bot(config)
    
    # Создаем диспетчер
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Добавляем middleware (порядок важен!)
    session_factory = db_manager.async_session_factory

    # 1. DatabaseSessionMiddleware - создаёт сессию БД и добавляет в контекст
    dp.update.outer_middleware(DatabaseSessionMiddleware(session_factory))

    # 2. RateLimitMiddleware - ограничивает частоту запросов (защита от спама)
    rate_limit_middleware = RateLimitMiddleware(
        message_limit=10,  # 10 сообщений в минуту
        message_window=60,
        callback_limit=20,  # 20 callback'ов в минуту
        callback_window=60,
        skip_admins=True  # Админы не ограничены
    )
    dp.message.middleware(rate_limit_middleware)
    dp.callback_query.middleware(rate_limit_middleware)

    # 3. AccessMiddleware - проверяет пользователя и добавляет user/is_admin/is_registered
    dp.message.middleware(AccessMiddleware(session_factory, config.admin_telegram_ids))
    dp.callback_query.middleware(AccessMiddleware(session_factory, config.admin_telegram_ids))

    # 4. BotStatusMiddleware - проверяет статус бота и блокирует обычных пользователей при остановке
    from src.bot.middleware.bot_status import BotStatusMiddleware
    dp.message.middleware(BotStatusMiddleware())
    dp.callback_query.middleware(BotStatusMiddleware())

    # 5. DeletePreviousMessageMiddleware - удаляет предыдущее сообщение после callback_query
    from src.bot.middleware.delete_previous_message import DeletePreviousMessageMiddleware
    dp.callback_query.middleware(DeletePreviousMessageMiddleware())

    # 6. Очередь импорта в Bitrix24
    from src.bitrix24.import_queue import get_import_queue
    import_queue = get_import_queue()
    await import_queue.start_worker()
    dp["import_queue"] = import_queue
    
    logger.info("🔄 Очередь импорта запущена")

    # Регистрируем обработчики
    register_handlers(dp, db_manager, config)

    # Запускаем polling
    logger.info("Бот запущен в режиме polling")
    
    # ОТПРАВЛЯЕМ УВЕДОМЛЕНИЕ ВСЕМ ПОЛЬЗОВАТЕЛЯМ О ЗАПУСКЕ БОТА
    try:
        from src.database import crud as db_crud
        
        async with db_manager.async_session_factory() as session:
            # Получаем ВСЕХ активных пользователей (админы + менеджеры)
            users = await db_crud.get_all_active_users(session)
            
            if users:
                # Формируем сообщение
                bot_info = await bot.get_me()
                startup_message = f"""
✅ <b>Бот запущен!</b>

🤖 Бот: @{bot_info.username}
⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

Бот готов к работе.
"""
                
                # Отправляем каждому пользователю
                sent_count = 0
                failed_count = 0
                
                for user in users:
                    try:
                        await bot.send_message(
                            chat_id=user.telegram_id,
                            text=startup_message,
                            parse_mode="HTML"
                        )
                        sent_count += 1
                        logger.debug(f"Уведомление о запуске отправлено пользователю {user.telegram_id}")
                    except Exception as e:
                        failed_count += 1
                        logger.warning(f"Не удалось отправить уведомление пользователю {user.telegram_id}: {e}")
                
                logger.info(f"Рассылка о запуске: отправлено {sent_count}, ошибок {failed_count}")
                        
    except Exception as e:
        logger.warning(f"Ошибка отправки уведомления о запуске: {type(e).__name__}: {e}")

    # Запускаем polling
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        # Плавная остановка по Ctrl+C
        logger.info("Получен сигнал остановки (Ctrl+C)")
        
        # Уведомляем ВСЕХ пользователей об остановке
        try:
            from src.database import crud as db_crud
            
            async with db_manager.async_session_factory() as session:
                users = await db_crud.get_all_active_users(session)
                
                if users:
                    stop_message = f"""
⛔ <b>Бот остановлен</b>

⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
📝 Причина: Остановка сервера

Бот временно недоступен.
"""
                    
                    sent_count = 0
                    failed_count = 0
                    
                    for user in users:
                        try:
                            await bot.send_message(
                                chat_id=user.telegram_id,
                                text=stop_message,
                                parse_mode="HTML"
                            )
                            sent_count += 1
                            logger.debug(f"Уведомление об остановке отправлено пользователю {user.telegram_id}")
                        except Exception as e:
                            failed_count += 1
                            logger.warning(f"Не удалось отправить уведомление пользователю {user.telegram_id}: {e}")
                    
                    logger.info(f"Рассылка об остановке: отправлено {sent_count}, ошибок {failed_count}")
                    
                    # Даём время на отправку всех уведомлений (1 сек на каждые 10 пользователей)
                    await asyncio.sleep(max(1, len(users) / 10))
                            
        except Exception as e:
            logger.warning(f"Ошибка отправки уведомления об остановке: {type(e).__name__}: {e}")
        
    finally:
        # Останавливаем очередь импорта
        if "import_queue" in dp:
            await dp["import_queue"].stop()
            logger.info("⏹️ Очередь импорта остановлена")
        
        # Закрываем соединения
        logger.info("Закрытие соединений...")
        await bot.session.close()
        await db_manager.engine.dispose()
        logger.info("Бот полностью остановлен")


if __name__ == "__main__":
    # Настраиваем логирование ТОЛЬКО через setup_logger (не дублировать!)
    # logging.basicConfig отключён, чтобы избежать дублирования логов
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Обработка уже выполнена в main()
        pass
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
