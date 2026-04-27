"""
Сценарий загрузки лидов на менеджера (FSM AdminLoadLeadsStates).
"""
from typing import Dict, Any
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...states import AdminLoadLeadsStates, AdminLoadLeadsBitrixStates
from ...messages.texts import (
    ADMIN_LOAD_LEADS_SELECT_MANAGER,
    ADMIN_LOAD_LEADS_SELECT_SEGMENT,
    ADMIN_LOAD_LEADS_SELECT_CITY,
    ADMIN_LOAD_LEADS_COUNT,
    ADMIN_LOAD_LEADS_NOT_ENOUGH,
    ADMIN_LOAD_LEADS_CONFIRM,
    ADMIN_LOAD_LEADS_ERROR,
    MANAGER_LEADS_LOADED_NOTIFICATION,
    IMPORT_QUEUED,
    IMPORT_COMPLETE,
    BTN_BACK,
)
from ...keyboards.keyboard_factory import (
    create_managers_list_keyboard,
    create_segments_load_keyboard,
    create_cities_load_keyboard,
    create_load_confirm_keyboard,
    create_not_enough_leads_keyboard,
    create_back_keyboard,
)
from ....database import crud
from ....logger import get_logger
from ....utils.html_utils import (
    safe_answer_callback,
    safe_edit_or_answer,
    safe_delete_message,
    format_html_safe,
)
from .bitrix_flow import confirm_bitrix_load, process_bitrix_load

logger = get_logger(__name__)
router = Router()


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

        await safe_edit_or_answer(callback, ADMIN_LOAD_LEADS_SELECT_MANAGER, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка пагинации менеджеров: {type(e).__name__}: {e}")
        await safe_answer_callback(callback, "⚠️ Ошибка", show_alert=True)


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
        segments = await crud.get_segments_for_admin_load(session)
        
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
            reply_markup=keyboard,
        )

        await safe_answer_callback(callback)

    except Exception as e:
        logger.error(f"Ошибка выбора менеджера: {type(e).__name__}: {e}")
        await safe_answer_callback(callback, "⚠️ Ошибка", show_alert=True)


# =============================================================================
# Пагинация сегментов
# =============================================================================

@router.callback_query(F.data.startswith("load_leads_segment_page:"))
async def handle_leads_segment_page(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Пагинация сегментов для загрузки на менеджера"""
    try:
        parsed = callback.data.split(":")
        new_page = int(parsed[1])

        # Получаем данные из состояния
        state_data = await state.get_data()
        segments = state_data.get("segments_list", [])

        if not segments:
            await callback.answer("⚠️ Список сегментов не найден", show_alert=True)
            return

        # Обновляем страницу
        await state.update_data(current_page=new_page)

        # Показываем новую страницу
        keyboard = create_segments_load_keyboard(segments, page=new_page, page_size=10)

        await safe_edit_or_answer(callback, ADMIN_LOAD_LEADS_SELECT_SEGMENT, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка пагинации сегментов: {type(e).__name__}: {e}")
        await safe_answer_callback(callback, "⚠️ Ошибка", show_alert=True)


# =============================================================================
# Выбор сегмента
# =============================================================================

@router.callback_query(F.data.startswith("load_leads_segment:"))
async def handle_segment_select(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора сегмента (для загрузки на менеджера)"""
    try:
        parsed = callback.data.split(":", 1)
        segment_index = int(parsed[1])  # ✅ Получаем индекс сегмента

        logger.info(f"handle_segment_select: index={segment_index}")

        # Получаем данные из состояния
        state_data = await state.get_data()
        segments = state_data.get("segments_list", [])

        logger.info(f"handle_segment_select: segments count={len(segments)}")
        for i, (seg, cities) in enumerate(segments):
            logger.info(f"  [{i}] '{seg}' cities={cities}")

        # ✅ Находим сегмент по индексу
        if segment_index < 0 or segment_index >= len(segments):
            await callback.answer("⚠️ Сегмент не найден", show_alert=True)
            return

        segment_data = segments[segment_index]
        segment_name, cities = segment_data

        # Сохраняем в состоянии
        await state.update_data(
            selected_segment=segment_name,
            segment_index=segment_index,
        )

        # Проверяем, это "Прочее" сегмент
        is_other_regular = "Прочее (Обыч.)" in segment_name
        is_other_plusoviki = "Прочее (Плюсовики)" in segment_name
        is_other = is_other_regular or is_other_plusoviki

        if not cities:
            # Нет городов - сразу к количеству
            await state.update_data(selected_city=None)
            await state.set_state(AdminLoadLeadsStates.ENTER_COUNT)

            # Проверяем доступное количество
            if is_other:
                # Для "Прочее" используем специальную функцию
                other_type = "regular" if is_other_regular else "plusoviki"
                available_count = await crud.count_other_leads(
                    session, other_type=other_type, segment=segment_name
                )
                # Сохраняем тип "Прочее" для последующего получения лидов
                await state.update_data(is_other=True, other_type=other_type)
            else:
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
            format_html_safe(ADMIN_LOAD_LEADS_SELECT_CITY, segment=segment_name),
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

        # Проверяем, это "Прочие" город
        is_other_regular = selected_city and "Прочие (Обыч.)" in str(selected_city)
        is_other_plusoviki = selected_city and "Прочие (Плюсовики)" in str(selected_city)
        is_other = is_other_regular or is_other_plusoviki

        await state.set_state(AdminLoadLeadsStates.ENTER_COUNT)

        # Проверяем доступное количество
        if is_other:
            other_type = "regular" if is_other_regular else "plusoviki"
            logger.info(f"Выбран 'Прочие': other_type={other_type}, selected_city={selected_city}")
            available_count = await crud.count_other_leads(
                session, other_type=other_type, segment=segment_name
            )
            logger.info(f"count_other_leads вернул: {available_count}")
            await state.update_data(is_other=True, other_type=other_type)
        else:
            available_count = await crud.count_available_leads_for_assignment(
                session, segment_name, city=selected_city
            )
            logger.info(f"count_available_leads_for_assignment вернул: {available_count}")
        
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
        is_other = state_data.get("is_other", False)
        other_type = state_data.get("other_type", "regular")

        if is_other:
            available_count = await crud.count_other_leads(
                session, other_type=other_type, segment=segment
            )
        else:
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
async def confirm_load(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    session_factory: async_sessionmaker,
):
    """Подтверждение загрузки лидов (на менеджера)"""
    # СРАЗУ отвечаем на callback чтобы не истёк таймаут
    await callback.answer("⏳ Загрузка лидов в Bitrix24...")
    
    # Удаляем сообщение с кнопкой подтверждения чтобы нельзя было нажать повторно
    await safe_delete_message(callback.message)
    
    # Отправляем сообщение о начале загрузки (best-effort)
    try:
        await callback.message.answer("⏳ <b>Загрузка лидов в Bitrix24...</b>\n\nЭто может занять несколько минут.")
    except Exception as e:
        logger.warning(f"Не удалось отправить сообщение о загрузке: {type(e).__name__}: {e}")

    # Проверяем состояние - если это Bitrix24 ID, вызываем другой обработчик
    current_state = await state.get_state()
    if current_state in AdminLoadLeadsBitrixStates.__all_states__:
        await confirm_bitrix_load(callback, state, session)
        return

    await process_load_leads(
        callback, state, session, None, session_factory=session_factory
    )


@router.callback_query(F.data.startswith("load_leads_confirm_available:"))
async def confirm_load_available(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    session_factory: async_sessionmaker,
):
    """Подтверждение загрузки доступного количества (сценарий на менеджера)."""
    current_state = await state.get_state()
    if current_state in AdminLoadLeadsBitrixStates.__all_states__:
        parsed = callback.data.split(":")
        available_count = int(parsed[1])
        await process_bitrix_load(callback, state, session, available_count)
        return
    parsed = callback.data.split(":")
    available_count = int(parsed[1])
    await process_load_leads(
        callback, state, session, available_count, session_factory=session_factory
    )


async def process_load_leads(
    target,
    state: FSMContext,
    session: AsyncSession,
    override_count: int = None,
    *,
    session_factory: async_sessionmaker,
):
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
        is_other = state_data.get("is_other", False)
        other_type = state_data.get("other_type", "regular")

        if is_other:
            # НЕ передаём segment — это отображаемое название, а не реальный сегмент из БД.
            leads = await crud.get_other_leads_for_assignment(
                session, other_type=other_type, limit=count
            )
        else:
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
        
        # Flush чтобы назначение было видно в текущей сессии перед постановкой в очередь
        await session.flush()

        # Получаем Bitrix24 ID менеджера
        manager = await crud.get_user_by_telegram_id(session, manager_id)
        bitrix_user_id = manager.bitrix24_user_id if manager else None
        
        # Получаем очередь импорта из контекста
        from ....bitrix24.import_queue import get_import_queue
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
                
                # Уведомляем менеджера (отдельная сессия: HTTP-запрос уже завершён)
                async with session_factory() as cb_session:
                    admin_user = await crud.get_user_by_telegram_id(
                        cb_session, str(target.from_user.id)
                    )
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
            await safe_delete_message(target.message)
            
            await target.answer(
                format_html_safe(IMPORT_QUEUED, count=len(lead_ids), segment=segment, city=city or "Все города"),
                reply_markup=create_back_keyboard("admin_menu")
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление: {type(e).__name__}: {e}")
            # Пробуем отправить новым сообщением если callback истёк
            try:
                await target.bot.send_message(
                    chat_id=target.from_user.id,
                    text=format_html_safe(IMPORT_QUEUED, count=len(lead_ids), segment=segment, city=city or "Все города"),
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
            f"Админ {target.from_user.id} загрузил {len(lead_ids)} лидов менеджеру {manager_id} "
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
            await safe_delete_message(target.message)
            
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
            except Exception as _e:
                logger.warning(f"Финальный fallback не удался: {type(_e).__name__}: {_e}")
        
        await state.clear()
# =============================================================================
# Отмена
# =============================================================================

@router.callback_query(F.data == "load_leads_cancel")
async def cancel_load(callback: CallbackQuery, state: FSMContext):
    """Отмена загрузки лидов"""
    await state.clear()
    
    # Удаляем предыдущее сообщение
    await safe_delete_message(callback.message)
    
    await callback.message.answer(
        "❌ Загрузка отменена",
        reply_markup=create_back_keyboard("admin_menu")
    )
    
    await callback.answer()
