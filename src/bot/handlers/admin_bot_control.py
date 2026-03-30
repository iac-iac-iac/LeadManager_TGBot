"""
Обработчики управления статусом бота

Включение/выключение бота, установка причины остановки,
рассылка уведомлений пользователям
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from ..states import FeedbackStates
from ..messages.texts import (
    BOT_CONTROL_TITLE,
    BOT_STATUS_RUNNING,
    BOT_STATUS_STOPPED,
    BOT_STATUS_MAINTENANCE,
    BOT_STOP_REASON_PROMPT,
    BOT_STOP_CONFIRM,
    BOT_START_CONFIRM,
    BOT_STOPPED_SUCCESS,
    BOT_STARTED_SUCCESS,
    BOT_MAINTENANCE_SUCCESS,
)
from ..keyboards.keyboard_factory import (
    create_bot_control_keyboard,
    create_bot_stop_reason_keyboard,
    create_bot_confirm_keyboard,
    create_back_keyboard,
)
from ...database import crud
from ...bot.services.notification_service import NotificationService
from ...logger import get_logger

logger = get_logger(__name__)

router = Router()


# =============================================================================
# Главное меню управления ботом
# =============================================================================

@router.callback_query(F.data == "bot_control")
async def bot_control_menu(callback: CallbackQuery, session: AsyncSession):
    """
    Меню управления статусом бота
    
    Показывает текущий статус и кнопки управления
    """
    try:
        # Получаем текущий статус
        bot_status = await crud.get_bot_status(session)
        
        if bot_status:
            status_text = {
                "running": BOT_STATUS_RUNNING,
                "stopped": BOT_STATUS_STOPPED,
                "maintenance": BOT_STATUS_MAINTENANCE
            }.get(bot_status.status, f"❓ {bot_status.status}")
            
            reason_text = f"Причина: {bot_status.reason}" if bot_status.reason else ""
        else:
            status_text = BOT_STATUS_RUNNING
            reason_text = ""
        
        # Формируем сообщение
        message_text = BOT_CONTROL_TITLE.format(
            status=status_text,
            reason_text=reason_text
        )
        
        # Показываем клавиатуру
        current_status = bot_status.status if bot_status else "running"
        keyboard = create_bot_control_keyboard(current_status)
        
        await callback.message.answer(
            message_text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Ошибка меню управления ботом: {type(e).__name__}: {e}")
        await callback.message.answer("⚠️ Ошибка получения статуса бота")
    
    await callback.answer()


# =============================================================================
# Остановка бота
# =============================================================================

@router.callback_query(F.data == "bot_stop")
async def bot_stop(callback: CallbackQuery, state: FSMContext):
    """
    Начало процесса остановки бота
    
    Предлагает выбрать причину остановки
    """
    try:
        await state.update_data(bot_action="stop")
        await state.set_state(FeedbackStates.WAITING_FOR_TICKET_ID)  # Используем существующее состояние
        
        await callback.message.answer(
            BOT_STOP_REASON_PROMPT,
            reply_markup=create_bot_stop_reason_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Ошибка остановки бота: {type(e).__name__}: {e}")
        await callback.message.answer("⚠️ Ошибка")
    
    await callback.answer()


@router.callback_query(F.data.startswith("stop_reason_"))
async def stop_reason_select(callback: CallbackQuery, state: FSMContext):
    """
    Выбор причины остановки
    """
    try:
        reason_type = callback.data.split("_")[2]
        
        reason_map = {
            "temp": "Временная остановка",
            "maintenance": "Технические работы",
            "skip": None
        }
        
        reason = reason_map.get(reason_type)
        
        # Сохраняем причину в состоянии
        await state.update_data(bot_stop_reason=reason)
        
        # Показываем подтверждение
        reason_text = reason or "без указания причины"
        await callback.message.answer(
            BOT_STOP_CONFIRM.format(reason=reason_text),
            reply_markup=create_bot_confirm_keyboard("stop")
        )
        
    except Exception as e:
        logger.error(f"Ошибка выбора причины: {type(e).__name__}: {e}")
        await callback.message.answer("⚠️ Ошибка")
    
    await callback.answer()


@router.callback_query(F.data == "bot_confirm_stop")
async def bot_confirm_stop(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Подтверждение остановки бота
    
    Обновление статуса в БД и рассылка уведомлений
    """
    try:
        # Получаем причину из состояния
        state_data = await state.get_data()
        reason = state_data.get("bot_stop_reason")
        
        # Обновляем статус в БД
        await crud.set_bot_status(session, "stopped", reason)
        
        logger.info(f"Бот остановлен админом {callback.from_user.id}, причина: {reason}")
        
        # Отправляем подтверждение админу
        await callback.message.answer(
            BOT_STOPPED_SUCCESS.format(reason=reason or "не указана")
        )
        
        # Запускаем рассылку уведомлений
        try:
            notification_service = NotificationService(callback.bot)
            stats = await notification_service.notify_bot_status_change(
                session,
                "stopped",
                reason
            )
            logger.info(f"Рассылка при остановке: отправлено {stats['sent']}, ошибок {stats['failed']}")
        except Exception as e:
            logger.error(f"Ошибка рассылки при остановке: {type(e).__name__}: {e}")
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка подтверждения остановки: {type(e).__name__}: {e}")
        await callback.message.answer("⚠️ Ошибка остановки бота")
    
    await callback.answer()


# =============================================================================
# Запуск бота
# =============================================================================

@router.callback_query(F.data == "bot_start")
async def bot_start(callback: CallbackQuery, state: FSMContext):
    """
    Начало процесса запуска бота
    """
    try:
        await state.update_data(bot_action="start")
        
        await callback.message.answer(
            BOT_START_CONFIRM,
            reply_markup=create_bot_confirm_keyboard("start")
        )
        
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {type(e).__name__}: {e}")
        await callback.message.answer("⚠️ Ошибка")
    
    await callback.answer()


@router.callback_query(F.data == "bot_confirm_start")
async def bot_confirm_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Подтверждение запуска бота
    
    Обновление статуса в БД и рассылка уведомлений
    """
    try:
        # Обновляем статус в БД
        await crud.set_bot_status(session, "running", None)
        
        logger.info(f"Бот запущен админом {callback.from_user.id}")
        
        # Отправляем подтверждение админу
        await callback.message.answer(BOT_STARTED_SUCCESS)
        
        # Запускаем рассылку уведомлений
        try:
            notification_service = NotificationService(callback.bot)
            stats = await notification_service.notify_bot_status_change(
                session,
                "running",
                None
            )
            logger.info(f"Рассылка при запуске: отправлено {stats['sent']}, ошибок {stats['failed']}")
        except Exception as e:
            logger.error(f"Ошибка рассылки при запуске: {type(e).__name__}: {e}")
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка подтверждения запуска: {type(e).__name__}: {e}")
        await callback.message.answer("⚠️ Ошибка запуска бота")
    
    await callback.answer()


# =============================================================================
# Техобслуживание
# =============================================================================

@router.callback_query(F.data == "bot_maintenance")
async def bot_maintenance(callback: CallbackQuery, state: FSMContext):
    """
    Начало техобслуживания бота
    """
    try:
        await state.update_data(bot_action="maintenance")
        await state.set_state(FeedbackStates.WAITING_FOR_TICKET_ID)
        
        await callback.message.answer(
            BOT_STOP_REASON_PROMPT,
            reply_markup=create_bot_stop_reason_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Ошибка техобслуживания: {type(e).__name__}: {e}")
        await callback.message.answer("⚠️ Ошибка")
    
    await callback.answer()


@router.callback_query(F.data == "bot_confirm_maintenance")
async def bot_confirm_maintenance(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Подтверждение начала техобслуживания
    """
    try:
        # Получаем причину из состояния
        state_data = await state.get_data()
        reason = state_data.get("bot_stop_reason")
        
        # Обновляем статус в БД
        await crud.set_bot_status(session, "maintenance", reason)
        
        logger.info(f"Бот переведён в режим техобслуживания админом {callback.from_user.id}, причина: {reason}")
        
        # Отправляем подтверждение админу
        await callback.message.answer(
            BOT_MAINTENANCE_SUCCESS.format(reason=reason or "не указана")
        )
        
        # Запускаем рассылку уведомлений
        try:
            notification_service = NotificationService(callback.bot)
            stats = await notification_service.notify_bot_status_change(
                session,
                "maintenance",
                reason
            )
            logger.info(f"Рассылка при техобслуживании: отправлено {stats['sent']}, ошибок {stats['failed']}")
        except Exception as e:
            logger.error(f"Ошибка рассылки при техобслуживании: {type(e).__name__}: {e}")
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка подтверждения техобслуживания: {type(e).__name__}: {e}")
        await callback.message.answer("⚠️ Ошибка")
    
    await callback.answer()


# =============================================================================
# Ввод пользовательской причины
# =============================================================================

@router.message(FeedbackStates.WAITING_FOR_TICKET_ID)
async def process_custom_reason(message: Message, state: FSMContext):
    """
    Обработка пользовательской причины остановки
    
    Если админ ввёл свой текст вместо выбора из кнопок
    """
    try:
        reason_text = message.text.strip()
        
        # Проверяем на "нет" / "пропустить"
        if reason_text.lower() in ["нет", "пропустить", "skip"]:
            reason = None
        else:
            reason = reason_text[:500]  # Ограничение длины
        
        # Сохраняем причину
        await state.update_data(bot_stop_reason=reason)
        
        # Получаем действие
        state_data = await state.get_data()
        action = state_data.get("bot_action", "stop")
        
        # Показываем подтверждение
        reason_display = reason or "без указания причины"
        confirm_text = BOT_STOP_CONFIRM.format(reason=reason_display)
        
        await message.answer(
            confirm_text,
            reply_markup=create_bot_confirm_keyboard(action)
        )
        
        # Сбрасываем состояние ввода
        await state.set_state(None)
        
    except Exception as e:
        logger.error(f"Ошибка ввода причины: {type(e).__name__}: {e}")
        await message.answer("⚠️ Ошибка. Попробуйте ещё раз или выберите из кнопок.")

    # await message.answer()  # Удалено - не нужен пустой ответ
