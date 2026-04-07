"""
Обработчики загрузки лидов админом для менеджеров

Админ может выбрать менеджера, сегмент, город и количество лидов,
затем загрузить их в Bitrix24 и уведомить менеджера
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from ..states import AdminLoadLeadsStates, AdminLoadLeadsBitrixStates
from ..messages.texts import (
    ADMIN_LOAD_LEADS_BUTTON,
    ADMIN_LOAD_LEADS_BITRIX_ID,
    ADMIN_LOAD_LEADS_SELECT_MANAGER,
    ADMIN_LOAD_LEADS_MANAGER_INFO,
    ADMIN_LOAD_LEADS_SELECT_SEGMENT,
    ADMIN_LOAD_LEADS_SELECT_CITY,
    ADMIN_LOAD_LEADS_COUNT,
    ADMIN_LOAD_LEADS_NOT_ENOUGH,
    ADMIN_LOAD_LEADS_CONFIRM,
    ADMIN_LOAD_LEADS_SUCCESS,
    ADMIN_LOAD_LEADS_ERROR,
    MANAGER_LEADS_LOADED_NOTIFICATION,
    ADMIN_LOAD_LEADS_ENTER_BITRIX_ID,
    ADMIN_LOAD_LEADS_BITRIX_INFO,
    ADMIN_LOAD_LEADS_INVALID_BITRIX_ID,
    ADMIN_LOAD_LEADS_BITRIX_SUCCESS,
    IMPORT_QUEUED,
    IMPORT_COMPLETE,
    BTN_BACK,
    BTN_CANCEL,
)
from ..keyboards.keyboard_factory import (
    create_managers_list_keyboard,
    create_segments_load_keyboard,
    create_cities_load_keyboard,
    create_load_confirm_keyboard,
    create_not_enough_leads_keyboard,
    create_back_keyboard,
)
from ...database import crud
from ...bitrix24.client import get_bitrix24_client
from ...bitrix24.leads import import_assigned_leads
from ...config import get_config
from ...logger import get_logger

logger = get_logger(__name__)

router = Router()


# =============================================================================
# Главное меню загрузки лидов
# =============================================================================

@router.callback_query(F.data == "admin_load_leads")
async def admin_load_leads_menu(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Меню загрузки лидов менеджеру
    
    Показывает список активных менеджеров
    """
    try:
        # Сбрасываем состояние
        await state.clear()
        await state.set_state(AdminLoadLeadsStates.SELECT_MANAGER)
        
        # Получаем менеджеров
        managers = await crud.get_active_managers_with_stats(session)
        
        if not managers:
            await callback.message.answer(
                "⚠️ Нет активных менеджеров",
                reply_markup=create_back_keyboard("admin_menu")
            )
            await callback.answer()
            return
        
        # Сохраняем в состоянии
        await state.update_data(managers_list=managers, current_page=0)
        
        # Показываем список
        keyboard = create_managers_list_keyboard(managers, page=0, page_size=10)
        
        await callback.message.answer(
            ADMIN_LOAD_LEADS_SELECT_MANAGER,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Ошибка меню загрузки лидов: {type(e).__name__}: {e}")
        await callback.message.answer("⚠️ Ошибка получения списка менеджеров")
    
    await callback.answer()


# =============================================================================
# Пагинация менеджеров
# =============================================================================

@router.callback_query(F.data.startswith("load_leads_managers_page:"))
async def managers_page(callback: CallbackQuery, state: FSMContext):
    """Переключение страницы списка менеджеров"""
    try:
        parsed = callback.data.split(":")
        new_page = int(parsed[1])

        # Получаем данные из состояния
        state_data = await state.get_data()
        managers = state_data.get("managers_list", [])

        if not managers:
            await callback.answer("⚠️ Список менеджеров не найден", show_alert=True)
            return

        # Обновляем страницу
        await state.update_data(current_page=new_page)

        # Показываем новую страницу (edit_text чтобы не удалять сообщение)
        keyboard = create_managers_list_keyboard(managers, page=new_page, page_size=10)

        try:
            await callback.message.edit_text(
                ADMIN_LOAD_LEADS_SELECT_MANAGER,
                reply_markup=keyboard
            )
        except Exception:
            # Если edit не удался, отправляем новое сообщение
            await callback.message.answer(
                ADMIN_LOAD_LEADS_SELECT_MANAGER,
                reply_markup=keyboard
            )

    except Exception as e:
        logger.error(f"Ошибка пагинации менеджеров: {type(e).__name__}: {e}")
        try:
            await callback.answer("⚠️ Ошибка", show_alert=True)
        except Exception:
            pass


# =============================================================================
# Выбор менеджера
# =============================================================================

@router.callback_query(F.data.startswith("load_leads_manager:"))
async def handle_manager_select(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора менеджера"""
    try:
        parsed = callback.data.split(":")
        manager_telegram_id = parsed[1]
        
        # Получаем данные из состояния
        state_data = await state.get_data()
        managers = state_data.get("managers_list", [])
        
        # Находим менеджера
        manager = next((m for m in managers if m["telegram_id"] == manager_telegram_id), None)
        
        if not manager:
            await callback.answer("⚠️ Менеджер не найден", show_alert=True)
            return
        
        # Сохраняем в состоянии
        await state.update_data(
            selected_manager_id=manager_telegram_id,
            selected_manager_name=manager["full_name"]
        )
        
        # Получаем сегменты (включая замороженные — админ может загружать в любые)
        segments = await crud.get_segments_with_cities(session, exclude_frozen=False)
        
        if not segments:
            await callback.message.answer(
                "⚠️ Нет доступных сегментов",
                reply_markup=create_back_keyboard("admin_load_leads")
            )
            await state.clear()
            return
        
        # Сохраняем сегменты
        await state.update_data(segments_list=segments)
        await state.set_state(AdminLoadLeadsStates.SELECT_SEGMENT)
        
        # Показываем сегменты
        keyboard = create_segments_load_keyboard(segments, page=0, page_size=10)

        await callback.message.answer(
        ADMIN_LOAD_LEADS_SELECT_SEGMENT,
        reply_markup=keyboard
        )

            # Отвечаем на callback
        try:
            await callback.answer()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Ошибка выбора менеджера: {type(e).__name__}: {e}")
        try:
            await callback.answer("⚠️ Ошибка", show_alert=True)
        except Exception:
            pass


# =============================================================================
# Выбор сегмента
# =============================================================================

@router.callback_query(F.data.startswith("load_leads_segment:"))
async def handle_segment_select(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора сегмента (для загрузки на менеджера)"""
    try:
        # Проверяем состояние - если это загрузка на Bitrix24 ID, пропускаем
        current_state = await state.get_state()
        if current_state == AdminLoadLeadsBitrixStates.SELECT_SEGMENT:
            return  # Это загрузка на Bitrix24 ID, обрабатывается в handle_bitrix_segment_select

        parsed = callback.data.split(":", 1)
        segment_index = int(parsed[1])  # ✅ Получаем индекс сегмента

        # Получаем данные из состояния
        state_data = await state.get_data()
        segments = state_data.get("segments_list", [])

        # ✅ Находим сегмент по индексу
        if segment_index < 0 or segment_index >= len(segments):
            await callback.answer("⚠️ Сегмент не найден", show_alert=True)
            return

        segment_data = segments[segment_index]
        segment_name, cities = segment_data

        # Сохраняем в состоянии
        await state.update_data(
            selected_segment=segment_name,
            segment_index=segment_index
        )
        
        if not cities:
            # Нет городов - сразу к количеству
            await state.update_data(selected_city=None)
            await state.set_state(AdminLoadLeadsStates.ENTER_COUNT)
            
            # Проверяем доступное количество
            available_count = await crud.count_available_leads_for_assignment(
                session, segment_name, city=None
            )
            
            await callback.message.answer(
                f"📊 Доступно лидов: {available_count}\n\n"
                f"{ADMIN_LOAD_LEADS_COUNT}",
                reply_markup=create_back_keyboard("load_leads_segment_select")
            )
            await callback.answer()
            return
        
        # Сохраняем города
        await state.update_data(cities_list=cities)
        await state.set_state(AdminLoadLeadsStates.SELECT_CITY)
        
        # Показываем города
        keyboard = create_cities_load_keyboard(cities, segment_name, segment_index)
        
        await callback.message.answer(
            ADMIN_LOAD_LEADS_SELECT_CITY.format(segment=segment_name),
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Ошибка выбора сегмента: {type(e).__name__}: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)
    
    await callback.answer()


# =============================================================================
# Выбор города
# =============================================================================

@router.callback_query(F.data.startswith("load_leads_city:"))
async def handle_city_select(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора города"""
    try:
        parsed = callback.data.split(":")
        segment_index = int(parsed[1])
        city_value = parsed[2]
        
        # Получаем данные из состояния
        state_data = await state.get_data()
        segments = state_data.get("segments_list", [])
        cities = state_data.get("cities_list", [])
        
        if segment_index >= len(segments):
            await callback.answer("⚠️ Сегмент не найден", show_alert=True)
            return
        
        segment_name = segments[segment_index][0]
        
        # Определяем город
        if city_value == "__ALL__":
            selected_city = None
        else:
            city_index = int(city_value)
            if city_index >= len(cities):
                await callback.answer("⚠️ Город не найден", show_alert=True)
                return
            selected_city = cities[city_index]
        
        # Сохраняем город
        await state.update_data(selected_city=selected_city)
        await state.set_state(AdminLoadLeadsStates.ENTER_COUNT)
        
        # Проверяем доступное количество
        available_count = await crud.count_available_leads_for_assignment(
            session, segment_name, city=selected_city
        )
        
        await callback.message.answer(
            f"📊 Доступно лидов: {available_count}\n\n"
            f"{ADMIN_LOAD_LEADS_COUNT}",
            reply_markup=create_back_keyboard("load_leads_segment_select")
        )
        
    except Exception as e:
        logger.error(f"Ошибка выбора города: {type(e).__name__}: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)
    
    await callback.answer()


# =============================================================================
# Ввод количества
# =============================================================================

@router.message(AdminLoadLeadsStates.ENTER_COUNT)
async def handle_count_input(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка ввода количества лидов"""
    try:
        # Парсим количество
        try:
            count = int(message.text.strip())
        except ValueError:
            await message.answer(
                "❌ Введите число от 1 до 200"
            )
            return
        
        # Валидация
        if count < 1 or count > 200:
            await message.answer(
                "❌ Количество должно быть от 1 до 200"
            )
            return
        
        # Получаем данные из состояния
        state_data = await state.get_data()
        segment = state_data.get("selected_segment")
        city = state_data.get("selected_city")
        
        # Проверяем доступное количество
        available_count = await crud.count_available_leads_for_assignment(
            session, segment, city=city
        )
        
        if count > available_count:
            # Недостаточно лидов
            await state.update_data(requested_count=count)
            await state.set_state(AdminLoadLeadsStates.CONFIRM)
            
            await message.answer(
                ADMIN_LOAD_LEADS_NOT_ENOUGH.format(
                    available=available_count,
                    requested=count
                ),
                reply_markup=create_not_enough_leads_keyboard(available_count)
            )
            return
        
        # Достаточно лидов - показываем подтверждение
        await state.update_data(lead_count=count)
        await show_confirm(message, state)
        
    except Exception as e:
        logger.error(f"Ошибка ввода количества: {type(e).__name__}: {e}")
        await message.answer("⚠️ Ошибка. Введите число от 1 до 200")


async def show_confirm(target, state: FSMContext):
    """Показ подтверждения загрузки"""
    state_data = await state.get_data()
    
    manager_name = state_data.get("selected_manager_name", "Неизвестно")
    segment = state_data.get("selected_segment", "Не указан")
    city = state_data.get("selected_city")
    city_text = city or "Все города"
    count = state_data.get("lead_count", 0)
    
    await target.answer(
        ADMIN_LOAD_LEADS_CONFIRM.format(
            manager_name=manager_name,
            segment=segment,
            city=city_text,
            count=count
        ),
        reply_markup=create_load_confirm_keyboard()
    )


# =============================================================================
# Подтверждение загрузки
# =============================================================================

@router.callback_query(F.data == "load_leads_confirm")
async def confirm_load(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Подтверждение загрузки лидов (на менеджера)"""
    # СРАЗУ отвечаем на callback чтобы не истёк таймаут
    await callback.answer("⏳ Загрузка лидов в Bitrix24...")
    
    # Удаляем сообщение с кнопкой подтверждения чтобы нельзя было нажать повторно
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    # Отправляем сообщение о начале загрузки
    try:
        await callback.message.answer("⏳ <b>Загрузка лидов в Bitrix24...</b>\n\nЭто может занять несколько минут.")
    except Exception:
        pass
    
    # Проверяем состояние - если это Bitrix24 ID, вызываем другой обработчик
    current_state = await state.get_state()
    if current_state in AdminLoadLeadsBitrixStates.__all_states__:
        await confirm_bitrix_load(callback, state, session)
        return

    await process_load_leads(callback, state, session, None)


@router.callback_query(F.data == "load_bitrix_confirm")
async def confirm_bitrix_load_direct(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Прямой вызов подтверждения загрузки на Bitrix24 ID"""
    # СРАЗУ отвечаем на callback чтобы не истёк таймаут
    await callback.answer("⏳ Загрузка лидов в Bitrix24...")
    
    # Удаляем сообщение с кнопкой подтверждения чтобы нельзя было нажать повторно
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    # Отправляем сообщение о начале загрузки
    try:
        await callback.message.answer("⏳ <b>Загрузка лидов в Bitrix24...</b>\n\nЭто может занять несколько минут.")
    except Exception:
        pass

    await process_bitrix_load(callback, state, session, None)


@router.callback_query(F.data.startswith("load_leads_confirm_available:"))
async def confirm_load_available(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Подтверждение загрузки доступного количества"""
    parsed = callback.data.split(":")
    available_count = int(parsed[1])
    await process_load_leads(callback, state, session, available_count)


async def process_load_leads(target, state: FSMContext, session: AsyncSession, override_count: int = None):
    """Процесс загрузки лидов"""
    try:
        # Получаем данные из состояния
        state_data = await state.get_data()
        
        manager_id = state_data.get("selected_manager_id")
        manager_name = state_data.get("selected_manager_name", "Неизвестно")
        segment = state_data.get("selected_segment")
        city = state_data.get("selected_city")
        count = override_count or state_data.get("lead_count", 0)
        
        if not manager_id or not segment:
            await target.answer("⚠️ Ошибка: нет данных для загрузки", show_alert=True)
            await state.clear()
            return
        
        # Получаем доступные лиды
        leads = await crud.get_available_leads_for_assignment(
            session, segment, city=city, limit=count
        )
        
        if not leads:
            await target.answer(
                ADMIN_LOAD_LEADS_ERROR.format(error="Нет доступных лидов"),
                reply_markup=create_back_keyboard("admin_menu")
            )
            await state.clear()
            return
        
        # Назначаем лиды менеджеру и ставим в очередь на импорт
        lead_ids = [lead.id for lead in leads]
        await crud.assign_leads_to_manager(
            session, lead_ids, manager_id, loaded_by_admin=True
        )
        
        # Коммитим назначение
        await session.commit()

        # Получаем Bitrix24 ID менеджера
        manager = await crud.get_user_by_telegram_id(session, manager_id)
        bitrix_user_id = manager.bitrix24_user_id if manager else None
        
        # Получаем очередь импорта из контекста
        from ...bitrix24.import_queue import get_import_queue
        import_queue = get_import_queue()
        
        # Создаём callback для уведомления о завершении
        async def import_complete_callback(stats: Dict[str, int]):
            """Уведомление о завершении импорта"""
            try:
                imported_count = stats.get("imported", 0)
                error_count = stats.get("errors", 0)
                
                # Уведомляем админа
                await target.bot.send_message(
                    chat_id=target.from_user.id,
                    text=IMPORT_COMPLETE.format(
                        imported=imported_count,
                        errors=error_count
                    ),
                    parse_mode="HTML"
                )
                
                # Уведомляем менеджера
                admin_user = await crud.get_user_by_telegram_id(session, str(target.from_user.id))
                admin_name = admin_user.full_name if admin_user else "Администратор"
                city_text = city or "Все города"
                
                await target.bot.send_message(
                    chat_id=manager_id,
                    text=MANAGER_LEADS_LOADED_NOTIFICATION.format(
                        admin_name=admin_name,
                        count=imported_count,
                        segment=segment,
                        city=city_text
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления о завершении импорта: {e}")
        
        # Добавляем в очередь
        queued = await import_queue.add_import(
            lead_ids=lead_ids,
            manager_id=manager_id,
            bitrix_user_id=bitrix_user_id,
            callback=import_complete_callback
        )
        
        if not queued:
            await target.answer(
                ADMIN_LOAD_LEADS_ERROR.format(error="Очередь переполнена, попробуйте позже"),
                reply_markup=create_back_keyboard("admin_menu")
            )
            await state.clear()
            return

        # Показываем сообщение о постановке в очередь
        try:
            # Сначала пытаемся удалить сообщение о начале загрузки
            try:
                await target.message.delete()
            except Exception:
                pass
            
            await target.answer(
                IMPORT_QUEUED.format(
                    count=len(lead_ids),
                    segment=segment,
                    city=city or "Все города"
                ),
                reply_markup=create_back_keyboard("admin_menu")
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление: {type(e).__name__}: {e}")
            # Пробуем отправить новым сообщением если callback истёк
            try:
                await target.bot.send_message(
                    chat_id=target.from_user.id,
                    text=IMPORT_QUEUED.format(
                        count=len(lead_ids),
                        segment=segment,
                        city=city or "Все города"
                    ),
                    reply_markup=create_back_keyboard("admin_menu")
                )
            except Exception as e2:
                logger.error(f"Не удалось отправить сообщение: {type(e2).__name__}: {e2}")

        # Уведомляем менеджера о том что лиды в очереди
        try:
            admin_user = await crud.get_user_by_telegram_id(session, str(target.from_user.id))
            admin_name = admin_user.full_name if admin_user else "Администратор"

            city_text = city or "Все города"

            await target.bot.send_message(
                chat_id=manager_id,
                text=f"📦 <b>Лиды поставлены в очередь на импорт!</b>\n\n"
                     f"👨‍💼 Администратор: {admin_name}\n"
                     f"📊 Количество: {len(lead_ids)}\n"
                     f"📁 Сегмент: {segment}\n"
                     f"🏙 Город: {city_text}\n\n"
                     f"⏳ Вы получите уведомление когда импорт завершится.",
                parse_mode="HTML"
            )
            logger.info(f"Менеджер {manager_id} уведомлён о постановке в очередь {len(lead_ids)} лидов")
        except Exception as e:
            logger.error(f"Не удалось уведомить менеджера {manager_id}: {e}")
        
        # Логируем
        logger.info(
            f"Админ {target.from_user.id} загрузил {imported_count} лидов менеджеру {manager_id} "
            f"(сегмент: {segment}, город: {city or 'Все'})"
        )
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка загрузки лидов: {type(e).__name__}: {e}")
        
        # Пробуем отправить ошибку
        try:
            # Сначала пытаемся удалить сообщение о начале загрузки
            try:
                await target.message.delete()
            except Exception:
                pass
            
            await target.answer(
                ADMIN_LOAD_LEADS_ERROR.format(error=str(e)),
                reply_markup=create_back_keyboard("admin_menu")
            )
        except Exception:
            try:
                await target.bot.send_message(
                    chat_id=target.from_user.id,
                    text=ADMIN_LOAD_LEADS_ERROR.format(error=str(e)),
                    reply_markup=create_back_keyboard("admin_menu")
                )
            except Exception:
                pass
        
        await state.clear()


# =============================================================================
# Отмена
# =============================================================================

@router.callback_query(F.data == "load_leads_cancel")
async def cancel_load(callback: CallbackQuery, state: FSMContext):
    """Отмена загрузки лидов"""
    await state.clear()
    
    # Удаляем предыдущее сообщение
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    await callback.message.answer(
        "❌ Загрузка отменена",
        reply_markup=create_back_keyboard("admin_menu")
    )
    
    await callback.answer()


# =============================================================================
# Назад к выбору сегмента
# =============================================================================

@router.callback_query(F.data == "load_leads_segment_select")
async def back_to_segment_select(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Возврат к выбору сегмента"""
    try:
        # Сохраняем bitrix_user_id перед возвратом (чтобы не потерялся)
        state_data = await state.get_data()
        bitrix_id = state_data.get("bitrix_user_id")
        
        # Получаем сегменты (включая замороженные — админ может загружать в любые)
        segments = await crud.get_segments_with_cities(session, exclude_frozen=False)

        if not segments:
            await callback.message.answer(
                "⚠️ Нет доступных сегментов",
                reply_markup=create_back_keyboard("admin_load_leads")
            )
            await state.clear()
            return

        # Сохраняем в состоянии (включая bitrix_user_id)
        await state.update_data(
            segments_list=segments,
            bitrix_user_id=bitrix_id  # Сохраняем ID
        )
        await state.set_state(AdminLoadLeadsBitrixStates.SELECT_SEGMENT)

        # Показываем сегменты
        keyboard = create_segments_load_keyboard(segments, page=0, page_size=10)

        # Удаляем предыдущее сообщение
        try:
            await callback.message.delete()
        except Exception:
            pass

        await callback.message.answer(
            ADMIN_LOAD_LEADS_SELECT_SEGMENT,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка возврата к сегментам: {type(e).__name__}: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)

    await callback.answer()


# =============================================================================
# Загрузка лидов на Bitrix24 ID (незарегистрированный менеджер)
# =============================================================================

@router.callback_query(F.data == "admin_load_leads_bitrix")
async def admin_load_leads_bitrix_menu(callback: CallbackQuery, state: FSMContext):
    """
    Меню загрузки лидов на Bitrix24 ID
    
    Запрос Bitrix24 ID пользователя
    """
    try:
        # Удаляем предыдущее сообщение
        try:
            await callback.message.delete()
        except Exception:
            pass
        
        await state.set_state(AdminLoadLeadsBitrixStates.ENTER_BITRIX_ID)
        
        await callback.message.answer(
            ADMIN_LOAD_LEADS_ENTER_BITRIX_ID.format(
                bitrix_info=ADMIN_LOAD_LEADS_BITRIX_INFO
            ),
            reply_markup=create_back_keyboard("admin_menu")
        )
        
    except Exception as e:
        logger.error(f"Ошибка меню загрузки на Bitrix24 ID: {type(e).__name__}: {e}")
        await callback.message.answer("⚠️ Ошибка")
    
    await callback.answer()


@router.message(AdminLoadLeadsBitrixStates.ENTER_BITRIX_ID)
async def handle_bitrix_id_input(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка ввода Bitrix24 ID"""
    try:
        # Логируем что пришло
        logger.info(f"Получено сообщение: '{message.text}' (type: {type(message.text)})")
        
        # Парсим ID
        try:
            bitrix_id = int(message.text.strip())
            logger.info(f"Распаршено ID: {bitrix_id}")
        except ValueError as e:
            logger.error(f"Ошибка парсинга ID: {e}")
            await message.answer(ADMIN_LOAD_LEADS_INVALID_BITRIX_ID)
            return

        # Валидация
        if bitrix_id <= 0:
            logger.error(f"ID отрицательный: {bitrix_id}")
            await message.answer(ADMIN_LOAD_LEADS_INVALID_BITRIX_ID)
            return
        
        logger.info(f"ID валиден: {bitrix_id}")
        
        # Сохраняем ID
        await state.update_data(bitrix_user_id=bitrix_id)
        await state.set_state(AdminLoadLeadsBitrixStates.SELECT_SEGMENT)

        # Получаем сегменты (включая замороженные — админ может загружать в любые)
        segments = await crud.get_segments_with_cities(session, exclude_frozen=False)

        if not segments:
            await message.answer(
                "⚠️ Нет доступных сегментов",
                reply_markup=create_back_keyboard("admin_load_leads_bitrix")
            )
            await state.clear()
            return

        # Сохраняем сегменты
        await state.update_data(segments_list=segments)
        await state.update_data(back_callback="load_leads_segment_select")

        # Показываем сегменты с отдельным префиксом для Bitrix24 ID
        keyboard = create_segments_load_keyboard(
            segments, 
            page=0, 
            page_size=10, 
            prefix="load_bitrix_segment",
            back_callback="load_leads_segment_select"
        )
        
        await message.answer(
            ADMIN_LOAD_LEADS_SELECT_SEGMENT,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка ввода Bitrix24 ID: {type(e).__name__}: {e}", exc_info=True)
        await message.answer("⚠️ Ошибка. Введите положительное число")


@router.callback_query(F.data.startswith("load_bitrix_segment:"))
async def handle_bitrix_segment_select(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора сегмента для загрузки на Bitrix24 ID"""
    try:
        # СРАЗУ отвечаем на callback чтобы не истёк таймаут
        await callback.answer()
        
        parsed = callback.data.split(":")
        # ✅ Получаем ИНДЕКС сегмента
        segment_index = int(parsed[1])

        # Получаем данные из состояния
        state_data = await state.get_data()
        segments = state_data.get("segments_list", [])

        # ✅ Проверяем границы
        if segment_index >= len(segments):
            logger.error(f"Индекс сегмента вне диапазона: {segment_index} >= {len(segments)}")
            await callback.message.answer("⚠️ Сегмент не найден")
            return

        # ✅ Получаем сегмент по индексу
        segment_data = segments[segment_index]
        segment_name, cities = segment_data

        # Сохраняем в состоянии
        await state.update_data(
            selected_segment=segment_name,
            segment_index=segment_index
        )

        logger.info(f"Выбран сегмент: {segment_name}, индекс: {segment_index}, города: {cities}")

        if not cities:
            # Нет городов - сразу к количеству
            await state.update_data(selected_city=None)
            await state.set_state(AdminLoadLeadsBitrixStates.ENTER_COUNT)

            # Проверяем доступное количество
            available_count = await crud.count_available_leads_for_assignment(
                session, segment_name, city=None
            )

            # Получаем back_callback из состояния
            state_data = await state.get_data()
            back_callback = state_data.get("back_callback", "admin_menu")
            
            logger.info(f"back_callback={back_callback}, available_count={available_count}")
            
            # Удаляем предыдущее сообщение
            try:
                await callback.message.delete()
            except Exception:
                pass

            await callback.message.answer(
                f"📊 Доступно лидов: {available_count}\n\n"
                f"{ADMIN_LOAD_LEADS_COUNT}",
                reply_markup=create_back_keyboard(back_callback)
            )
            await callback.answer()
            return
        
        # Сохраняем города
        await state.update_data(cities_list=cities)
        await state.set_state(AdminLoadLeadsBitrixStates.SELECT_CITY)

        # Получаем back_callback из состояния
        state_data = await state.get_data()
        back_callback = state_data.get("back_callback", "admin_menu")
        
        # Удаляем предыдущее сообщение
        try:
            await callback.message.delete()
        except Exception:
            pass

        # Показываем города с правильным префиксом и back_callback
        keyboard = create_cities_load_keyboard(cities, segment_name, segment_index, prefix="load_bitrix_city", back_callback=back_callback)
        
        await callback.message.answer(
            ADMIN_LOAD_LEADS_SELECT_CITY.format(segment=segment_name),
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Ошибка выбора сегмента (Bitrix ID): {type(e).__name__}: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)
    
    await callback.answer()


@router.callback_query(F.data.startswith("load_bitrix_city:"))
async def handle_bitrix_city_select(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора города для загрузки на Bitrix24 ID"""
    try:
        parsed = callback.data.split(":")
        segment_index = int(parsed[1])
        city_value = parsed[2]
        
        # Получаем данные из состояния
        state_data = await state.get_data()
        segments = state_data.get("segments_list", [])
        cities = state_data.get("cities_list", [])
        
        if segment_index >= len(segments):
            await callback.answer("⚠️ Сегмент не найден", show_alert=True)
            return
        
        segment_name = segments[segment_index][0]
        
        # Определяем город
        if city_value == "__ALL__":
            selected_city = None
        else:
            city_index = int(city_value)
            if city_index >= len(cities):
                await callback.answer("⚠️ Город не найден", show_alert=True)
                return
            selected_city = cities[city_index]
        
        # Сохраняем город
        await state.update_data(selected_city=selected_city)
        await state.set_state(AdminLoadLeadsBitrixStates.ENTER_COUNT)
        
        # Проверяем доступное количество
        available_count = await crud.count_available_leads_for_assignment(
            session, segment_name, city=selected_city
        )
        
        # Получаем back_callback из состояния
        state_data = await state.get_data()
        back_callback = state_data.get("back_callback", "admin_menu")
        
        # Удаляем предыдущее сообщение
        try:
            await callback.message.delete()
        except Exception:
            pass
        
        await callback.message.answer(
            f"📊 Доступно лидов: {available_count}\n\n"
            f"{ADMIN_LOAD_LEADS_COUNT}",
            reply_markup=create_back_keyboard(back_callback)
        )
        
    except Exception as e:
        logger.error(f"Ошибка выбора города (Bitrix ID): {type(e).__name__}: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)
    
    await callback.answer()


@router.message(AdminLoadLeadsBitrixStates.ENTER_COUNT)
async def handle_bitrix_count_input(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка ввода количества для загрузки на Bitrix24 ID"""
    try:
        # Получаем данные из состояния ПЕРЕД парсингом
        state_data = await state.get_data()
        logger.info(f"handle_bitrix_count_input: state_data = {state_data}")
        
        segment = state_data.get("selected_segment")
        city = state_data.get("selected_city")
        bitrix_id = state_data.get("bitrix_user_id")
        
        logger.info(f"segment={segment}, city={city}, bitrix_id={bitrix_id}")
        
        if not segment:
            logger.error("segment не найден в состоянии!")
            await message.answer("⚠️ Ошибка: сегмент не выбран. Начните сначала.")
            await state.clear()
            return
        
        # Парсим количество
        try:
            count = int(message.text.strip())
        except ValueError:
            await message.answer("❌ Введите число от 1 до 200")
            return

        # Валидация
        if count < 1 or count > 200:
            await message.answer("❌ Количество должно быть от 1 до 200")
            return

        # Проверяем доступное количество
        available_count = await crud.count_available_leads_for_assignment(
            session, segment, city=city
        )

        if count > available_count:
            # Недостаточно лидов
            await state.update_data(requested_count=count)
            await state.set_state(AdminLoadLeadsBitrixStates.CONFIRM)

            await message.answer(
                ADMIN_LOAD_LEADS_NOT_ENOUGH.format(
                    available=available_count,
                    requested=count
                ),
                reply_markup=create_not_enough_leads_keyboard(available_count)
            )
            return

        # Достаточно лидов - показываем подтверждение
        await state.update_data(lead_count=count)
        
        # Удаляем предыдущее сообщение
        try:
            await message.delete()
        except Exception:
            pass
        
        await show_bitrix_confirm(message, state)

    except Exception as e:
        logger.error(f"Ошибка ввода количества (Bitrix ID): {type(e).__name__}: {e}", exc_info=True)
        await message.answer("⚠️ Ошибка. Введите число от 1 до 200")


async def show_bitrix_confirm(target, state: FSMContext):
    """Показ подтверждения загрузки на Bitrix24 ID"""
    state_data = await state.get_data()
    
    logger.info(f"show_bitrix_confirm: state_data = {state_data}")

    bitrix_id = state_data.get("bitrix_user_id", 0)
    segment = state_data.get("selected_segment", "Не указан")
    city = state_data.get("selected_city")
    city_text = city or "Все города"
    count = state_data.get("lead_count", 0)
    
    logger.info(f"bitrix_id={bitrix_id}, segment={segment}, city={city_text}, count={count}")

    # Создаём клавиатуру с ПРАВИЛЬНЫМ callback для Bitrix24 ID
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Загрузить", callback_data="load_bitrix_confirm")
    builder.button(text=BTN_CANCEL, callback_data="load_leads_cancel")
    builder.adjust(2)
    
    await target.answer(
        ADMIN_LOAD_LEADS_CONFIRM.format(
            manager_name=f"Bitrix24 ID: {bitrix_id}",
            segment=segment,
            city=city_text,
            count=count
        ),
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data == "load_bitrix_confirm")
async def confirm_bitrix_load(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Подтверждение загрузки на Bitrix24 ID"""
    # Удаляем предыдущее сообщение
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    await process_bitrix_load(callback, state, session, None)


@router.callback_query(F.data.startswith("load_bitrix_confirm_available:"))
async def confirm_bitrix_load_available(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Подтверждение загрузки доступного количества на Bitrix24 ID"""
    # Удаляем предыдущее сообщение
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    parsed = callback.data.split(":")
    available_count = int(parsed[1])
    await process_bitrix_load(callback, state, session, available_count)


async def process_bitrix_load(target, state: FSMContext, session: AsyncSession, override_count: int = None):
    """Процесс загрузки лидов на Bitrix24 ID"""
    try:
        # Получаем данные из состояния
        state_data = await state.get_data()
        
        logger.info(f"process_bitrix_load: state_data = {state_data}")
        
        bitrix_id = state_data.get("bitrix_user_id")
        segment = state_data.get("selected_segment")
        city = state_data.get("selected_city")
        count = override_count or state_data.get("lead_count", 0)
        
        logger.info(f"bitrix_id={bitrix_id}, segment={segment}, city={city}, count={count}")
        
        if not bitrix_id or not segment:
            logger.error(f"Нет данных: bitrix_id={bitrix_id}, segment={segment}")
            await target.answer("⚠️ Ошибка: нет данных для загрузки", show_alert=True)
            await state.clear()
            return
        
        # Получаем доступные лиды
        leads = await crud.get_available_leads_for_assignment(
            session, segment, city=city, limit=count
        )
        
        if not leads:
            await target.answer(
                ADMIN_LOAD_LEADS_ERROR.format(error="Нет доступных лидов"),
                reply_markup=create_back_keyboard("admin_menu")
            )
            await state.clear()
            return
        
        # Назначаем лиды на Bitrix24 ID (без привязки к менеджеру в боте)
        lead_ids = [lead.id for lead in leads]
        
        # Обновляем статусы лидов - назначаем на Bitrix24 ID
        from datetime import datetime, timezone
        from sqlalchemy import update
        from ...database.models import Lead, LeadStatus
        
        now = datetime.utcnow()
        await session.execute(
            update(Lead)
            .where(
                Lead.id.in_(lead_ids),
                Lead.status == LeadStatus.UNIQUE
            )
            .values(
                status=LeadStatus.ASSIGNED,
                manager_telegram_id=None,  # Нет менеджера в боте
                assigned_at=now
            )
        )
        
        # Импортируем в Bitrix24
        config = get_config()
        bitrix_client = get_bitrix24_client(config.bitrix24.webhook_url)
        
        # Импортируем каждый лид с задержками
        imported_count = 0
        for i, lead in enumerate(leads, 1):
            try:
                # Формируем название
                title = f"{lead.segment} - {lead.company_name or 'Без названия'}"

                # Маппинг типов услуг
                SERVICE_TYPE_MAP = {
                    "ГЦК": 101,
                    "ГЦК без КЦ": 102,
                    "Call-центр": 103,
                    "Лид-код": 104,
                    "Авито": 105,
                    "Рекрутинг": 106,
                }
                service_type_id = SERVICE_TYPE_MAP.get(lead.service_type, 101)

                await bitrix_client.add_lead(
                    title=title,
                    company_title=lead.company_name,
                    phone=lead.phone,
                    mobile_phone=lead.mobile_phone,
                    email=lead.work_email,
                    address=lead.address,
                    city=lead.city,
                    website=lead.website,
                    comment=lead.comment,
                    assigned_by_id=bitrix_id if bitrix_id and bitrix_id > 0 else None,
                    source_id=lead.source or "TELEGRAM",
                    service_type=service_type_id,
                    phone_source=lead.phone_source
                )
                imported_count += 1
                
                # Задержка между импортами для снижения нагрузки на API (50% уменьшено)
                if i % 10 == 0:  # Каждые 10 лидов
                    logger.info(f"⏳ Пауза 1.5 сек после {i} лидов...")
                    await asyncio.sleep(1.5)  # Было 3 сек
                else:
                    await asyncio.sleep(0.25)  # Было 0.5 сек
                
                # Обновляем статус лида
                lead.status = LeadStatus.IMPORTED
                lead.imported_at = datetime.now(timezone.utc)
                
            except Exception as e:
                logger.error(f"Ошибка импорта лида {lead.id} в Bitrix24: {e}")
        
        await session.commit()

        # Показываем успех (с обработкой ошибок callback)
        try:
            # Сначала пытаемся удалить сообщение о начале загрузки
            try:
                await target.message.delete()
            except Exception:
                pass
            
            await target.answer(
                ADMIN_LOAD_LEADS_BITRIX_SUCCESS.format(
                    bitrix_id=bitrix_id,
                    count=imported_count,
                    segment=segment
                ),
                reply_markup=create_back_keyboard("admin_menu")
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление: {type(e).__name__}: {e}")
            # Пробуем отправить новым сообщением если callback истёк
            try:
                await target.bot.send_message(
                    chat_id=target.from_user.id,
                    text=ADMIN_LOAD_LEADS_BITRIX_SUCCESS.format(
                        bitrix_id=bitrix_id,
                        count=imported_count,
                        segment=segment
                    ),
                    reply_markup=create_back_keyboard("admin_menu")
                )
            except Exception as e2:
                logger.error(f"Не удалось отправить сообщение: {type(e2).__name__}: {e2}")

        # Логируем
        logger.info(
            f"Админ {target.from_user.id} загрузил {imported_count} лидов на Bitrix24 ID {bitrix_id} "
            f"(сегмент: {segment}, город: {city or 'Все'})"
        )

        # Очищаем состояние
        await state.clear()

    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка загрузки на Bitrix24 ID: {type(e).__name__}: {e}")
        
        # Пробуем отправить ошибку
        try:
            # Сначала пытаемся удалить сообщение о начале загрузки
            try:
                await target.message.delete()
            except Exception:
                pass
            
            await target.answer(
                ADMIN_LOAD_LEADS_ERROR.format(error=str(e)),
                reply_markup=create_back_keyboard("admin_menu")
            )
        except Exception:
            try:
                await target.bot.send_message(
                    chat_id=target.from_user.id,
                    text=ADMIN_LOAD_LEADS_ERROR.format(error=str(e)),
                    reply_markup=create_back_keyboard("admin_menu")
                )
            except Exception:
                pass
        
        await state.clear()
