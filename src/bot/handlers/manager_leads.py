"""
Обработчик получения лидов менеджером

Сценарий:
1. Менеджер выбирает "📋 Получить лиды"
2. Выбор сегмента (inline-клавиатура)
3. Выбор города (inline-клавиатура)
4. Ввод количества (≤200)
5. Проверка доступности
6. Подтверждение
7. Выдача и постановка импорта в Bitrix24 в общую очередь (последовательная обработка)

«Мне повезёт!»: выбор UTC-пояса → ввод диапазона 10–200 → случайная партия из пула UNIQUE.
"""
import random
from typing import Dict, List, Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from ..states import ManagerStates
from ..messages.texts import (
    SELECT_SEGMENT,
    SELECT_CITY,
    ENTER_LEADS_COUNT,
    LEADS_COUNT_INVALID,
    LEADS_NOT_ENOUGH,
    LEADS_CONFIRM,
    LEADS_CANCELLED,
    MANAGER_MAIN_MENU,
    IMPORT_QUEUED,
    MANAGER_IMPORT_QUEUE_COMPLETE,
    LUCKY_MENU_INTRO,
    LUCKY_ENTER_RANGE,
    LUCKY_RANGE_INVALID,
    LUCKY_NOT_ENOUGH_POOL,
    LUCKY_SEGMENT_REGULAR,
    LUCKY_SEGMENT_PLUSOVIKI,
    LUCKY_CITY_LABEL,
)
from ..keyboards.keyboard_factory import (
    create_segments_keyboard,
    create_cities_keyboard,
    create_confirmation_keyboard,
    create_back_keyboard,
    create_manager_main_menu,
    create_lucky_band_keyboard,
    parse_callback_data,
)
from ...database import crud
from ...logger import get_logger
from ...utils.html_utils import safe_delete_message, format_html_safe
from ...utils.lucky_range import parse_lucky_leads_range

logger = get_logger(__name__)

router = Router()


async def enqueue_manager_import_queue(
    session: AsyncSession,
    bot,
    telegram_id: str,
    lead_ids: List[int],
    assigned_count: int,
    segment: str,
    city_text: str,
    reply_message: Optional[Message] = None,
) -> bool:
    """
    Постановка назначенных лидов в очередь импорта Bitrix и уведомление IMPORT_QUEUED.

    Returns:
        False если очередь переполнена.
    """
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    bitrix24_user_id = user.bitrix24_user_id if user else None
    if bitrix24_user_id is not None:
        bitrix24_user_id = int(bitrix24_user_id)

    from ...bitrix24.import_queue import get_import_queue

    import_queue = get_import_queue()

    async def import_complete_callback(stats: Dict[str, int]):
        try:
            imported_count = stats.get("imported", 0)
            error_count = stats.get("errors", 0)
            errors_line = ""
            if error_count:
                errors_line = f"\n⚠️ Ошибок при импорте: {error_count}"

            text = format_html_safe(
                MANAGER_IMPORT_QUEUE_COMPLETE,
                segment=segment,
                city=city_text,
                assigned=assigned_count,
                imported=imported_count,
                errors_line=errors_line,
            )

            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="HTML",
                reply_markup=create_manager_main_menu(),
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления менеджера об импорте: {e}")

    queued = await import_queue.add_import(
        lead_ids=lead_ids,
        manager_id=telegram_id,
        bitrix_user_id=bitrix24_user_id,
        callback=import_complete_callback,
    )

    if not queued:
        return False

    body = format_html_safe(
        IMPORT_QUEUED,
        count=assigned_count,
        segment=segment,
        city=city_text,
    )
    try:
        if reply_message:
            await reply_message.answer(
                body,
                parse_mode="HTML",
                reply_markup=create_manager_main_menu(),
            )
        else:
            await bot.send_message(
                chat_id=telegram_id,
                text=body,
                parse_mode="HTML",
                reply_markup=create_manager_main_menu(),
            )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение об очереди: {type(e).__name__}: {e}")
        try:
            await bot.send_message(
                chat_id=telegram_id,
                text=body,
                parse_mode="HTML",
                reply_markup=create_manager_main_menu(),
            )
        except Exception as e2:
            logger.warning(f"Не удалось отправить сообщение напрямую: {e2}")

    return True


# =============================================================================
# Меню получения лидов
# =============================================================================

@router.callback_query(F.data == "leads_menu")
async def handle_leads_menu(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Показ меню выбора сегмента"""
    # Очищаем предыдущее состояние
    await state.clear()
    
    telegram_id = str(callback.from_user.id)

    # Проверяем пользователя
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    if not user or user.status.value != "ACTIVE":
        await callback.answer("🚫 Вы не активированы", show_alert=True)
        return

    # Получаем доступные сегменты
    segments = await crud.get_segments_with_cities(session, exclude_frozen=True)

    if not segments:
        await callback.message.answer(
            "⚠️ В данный момент нет доступных лидов.\n"
            "Попробуйте позже или обратитесь к администратору."
        )
        await callback.answer()
        return

    # Сохраняем сегменты в состоянии для пагинации
    await state.update_data(segments_list=segments)

    # Формируем клавиатуру с пагинацией
    keyboard = create_segments_keyboard(segments, prefix="select_segment", page=0, page_size=20)

    await callback.message.answer(
        SELECT_SEGMENT,
        reply_markup=keyboard
    )
    
    # Отвечаем на callback с обработкой ошибок
    try:
        await callback.answer()
    except Exception as e:
        logger.debug(f"Не удалось ответить на callback: {type(e).__name__}: {e}")


# =============================================================================
# Пагинация сегментов
# =============================================================================

@router.callback_query(F.data.startswith("select_segment_page:"))
async def handle_segments_page(callback: CallbackQuery, state: FSMContext):
    """Переключение страницы сегментов"""
    parsed = parse_callback_data(callback.data)
    
    if not parsed["params"]:
        await callback.answer()
        return
    
    try:
        new_page = int(parsed["params"][0])
    except ValueError:
        await callback.answer()
        return
    
    # Получаем список сегментов из состояния
    state_data = await state.get_data()
    segments = state_data.get("segments_list", [])
    
    if not segments:
        await callback.answer("⚠️ Список сегментов не найден", show_alert=True)
        return
    
    # Показываем страницу
    keyboard = create_segments_keyboard(segments, prefix="select_segment", page=new_page, page_size=20)
    
    await callback.message.edit_text(
        SELECT_SEGMENT,
        reply_markup=keyboard
    )
    
    await callback.answer()


@router.callback_query(F.data == "select_segment_page_info")
async def handle_segments_page_info(callback: CallbackQuery):
    """Информация о странице (просто подтверждаем)"""
    await callback.answer()


@router.callback_query(F.data == "to_main_menu")
async def handle_to_main_menu_from_segments(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню из выбора сегментов"""
    await state.clear()
    
    await callback.message.answer(
        "🏠 Главное меню",
        reply_markup=create_manager_main_menu()
    )
    
    await callback.answer()


# =============================================================================
# Выбор сегмента
# =============================================================================

@router.callback_query(F.data.startswith("select_segment:"))
async def handle_segment_select(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора сегмента"""
    telegram_id = str(callback.from_user.id)
    parsed = parse_callback_data(callback.data)

    if len(parsed["params"]) < 1:
        await callback.answer("⚠️ Ошибка выбора", show_alert=True)
        return

    # Получаем индекс сегмента
    segment_index = int(parsed["params"][0])

    # Получаем доступные сегменты
    segments = await crud.get_segments_with_cities(session, exclude_frozen=True)

    if segment_index >= len(segments):
        await callback.answer("⚠️ Сегмент не найден", show_alert=True)
        return

    segment, cities = segments[segment_index]

    # Сохраняем в состоянии
    await state.update_data(selected_segment=segment, segment_index=segment_index)

    # Проверяем, это "Прочее" сегмент
    is_other_regular = "Прочее (Обыч.)" in segment
    is_other_plusoviki = "Прочее (Плюсовики)" in segment
    is_other = is_other_regular or is_other_plusoviki

    # Удаляем предыдущее сообщение
    await safe_delete_message(callback.message)

    if not cities:
        # Нет городов - сразу запрашиваем количество
        await state.update_data(selected_city=None)

        # Проверяем доступное количество
        if is_other:
            # Для "Прочее" используем специальную функцию
            # НЕ передаём segment так как это "📦 Прочее (Обыч.) — N лидов", а не реальный сегмент
            other_type = "regular" if is_other_regular else "plusoviki"
            available_count = await crud.count_other_leads(
                session, other_type=other_type
            )
            logger.info(f"Менеджер сегмент Прочее: other_type={other_type}, count={available_count}")
            await state.update_data(is_other=True, other_type=other_type)
        else:
            available_count = await crud.count_available_leads(session, segment, city=None)
            await state.update_data(is_other=False, other_type=None)

        await state.set_state(ManagerStates.LEADS_COUNT)
        await callback.message.answer(
            f"📊 Доступно лидов: {available_count}\n\n"
            f"{ENTER_LEADS_COUNT.format(max_count=200)}",
            reply_markup=create_back_keyboard("leads_menu")
        )
        await callback.answer()
        return

    # Показываем выбор города
    await state.set_state(ManagerStates.LEADS_CITY)
    keyboard = create_cities_keyboard(cities, segment, segment_index, prefix="select_city")

    await callback.message.answer(
        format_html_safe(SELECT_CITY, segment=segment),
        reply_markup=keyboard
    )
    
    # Отвечаем на callback с обработкой ошибок
    try:
        await callback.answer()
    except Exception as e:
        logger.debug(f"Не удалось ответить на callback: {type(e).__name__}: {e}")


# =============================================================================
# Выбор города
# =============================================================================

@router.callback_query(F.data == "back_to_segments")
async def handle_back_to_segments(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Возврат к выбору сегмента"""
    await state.set_state(ManagerStates.LEADS_SEGMENT)

    # Получаем доступные сегменты
    segments = await crud.get_segments_with_cities(session, exclude_frozen=True)

    keyboard = create_segments_keyboard(segments, prefix="select_segment")

    # Удаляем предыдущее сообщение и показываем новое
    await safe_delete_message(callback.message)
    
    await callback.message.answer(
        SELECT_SEGMENT,
        reply_markup=keyboard
    )

    # Отвечаем на callback с обработкой ошибок
    try:
        await callback.answer()
    except Exception as e:
        logger.debug(f"Не удалось ответить на callback: {type(e).__name__}: {e}")


@router.callback_query(F.data.startswith("select_city:"))
async def handle_city_select(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора города"""
    parsed = parse_callback_data(callback.data)

    if len(parsed["params"]) < 2:
        await callback.answer("⚠️ Ошибка выбора", show_alert=True)
        return

    # Получаем индексы
    segment_index = int(parsed["params"][0])
    city_index = int(parsed["params"][1])

    # Получаем доступные сегменты
    segments = await crud.get_segments_with_cities(session, exclude_frozen=True)

    if segment_index >= len(segments):
        await callback.answer("⚠️ Сегмент не найден", show_alert=True)
        return

    segment, cities = segments[segment_index]

    if city_index >= len(cities):
        await callback.answer("⚠️ Город не найден", show_alert=True)
        return

    city = cities[city_index]

    # Сохраняем город в состоянии
    await state.update_data(selected_city=city, selected_segment=segment)

    # Проверяем, это "Прочие" город
    is_other_regular = city and "Прочие (Обыч.)" in city
    is_other_plusoviki = city and "Прочие (Плюсовики)" in city
    is_other = is_other_regular or is_other_plusoviki

    # Удаляем предыдущее сообщение
    await safe_delete_message(callback.message)

    # Проверяем доступное количество
    if is_other:
        other_type = "regular" if is_other_regular else "plusoviki"
        available_count = await crud.count_other_leads(
            session, other_type=other_type, segment=segment
        )
        logger.info(f"Менеджер: Прочие other_type={other_type}, segment={segment}, count={available_count}")
        await state.update_data(is_other=True, other_type=other_type)
    else:
        available_count = await crud.count_available_leads(session, segment, city)
        await state.update_data(is_other=False, other_type=None)

    # Запрашиваем количество
    await state.set_state(ManagerStates.LEADS_COUNT)
    await callback.message.answer(
        f"📊 Доступно лидов: {available_count}\n\n"
        f"{ENTER_LEADS_COUNT.format(max_count=200)}",
        reply_markup=create_back_keyboard("leads_menu")
    )

    # Отвечаем на callback с обработкой ошибок
    try:
        await callback.answer()
    except Exception as e:
        logger.debug(f"Не удалось ответить на callback: {type(e).__name__}: {e}")


async def show_lead_count_input(callback: CallbackQuery, state: FSMContext, segment: str):
    """Показ ввода количества лидов"""
    keyboard = create_back_keyboard("leads_menu")

    await callback.message.answer(
        ENTER_LEADS_COUNT.format(max_count=200),
        reply_markup=keyboard
    )

    # Устанавливаем состояние ожидания количества
    await state.set_state(ManagerStates.LEADS_COUNT)
    await callback.answer()


# =============================================================================
# Ввод количества
# =============================================================================

@router.message(StateFilter(ManagerStates.LEADS_COUNT))
async def handle_lead_count_input(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка введенного количества лидов"""
    text = message.text.strip()

    # Парсим количество
    count = _parse_lead_count(text)
    if count is None:
        await message.answer(
            LEADS_COUNT_INVALID.format(max_count=200),
            reply_markup=create_back_keyboard("leads_menu")
        )
        return

    # Проверка минимума 10 лидов (исключение для "Прочие")
    data = await state.get_data()
    is_other = data.get("is_other", False)
    
    if count < 10 and not is_other:
        await message.answer(
            "❌ Минимальное количество для загрузки: 10 лидов.\n"
            f"Введите число от 10 до 200.",
            reply_markup=create_back_keyboard("leads_menu")
        )
        return

    # Получаем данные из FSM
    data = await state.get_data()
    segment = data.get("selected_segment")
    city = data.get("selected_city")
    is_other = data.get("is_other", False)
    other_type = data.get("other_type", "regular")

    if not segment:
        await message.answer("⚠️ Ошибка: сегмент не выбран")
        await state.clear()
        return

    # Проверяем доступное количество
    if is_other:
        # Для "Прочее" НЕ передаём segment так как это отображаемое название, а не реальный сегмент
        available_count = await crud.count_other_leads(
            session, other_type=other_type
        )
    else:
        available_count = await crud.count_available_leads(session, segment, city)

    if available_count == 0:
        await message.answer(
            "⚠️ В выбранном сегменте/городе нет доступных лидов.\n"
            "Выберите другой сегмент.",
            reply_markup=create_back_keyboard("leads_menu")
        )
        await state.clear()
        return

    # Для "Прочие" с малым количеством лидов — предлагаем взять всё
    if is_other and available_count < 10:
        await _show_not_enough_leads(
            message, state, available_count, count, allow_take_all=True
        )
        return

    if count > available_count:
        # Запрошено больше чем доступно — предлагаем взять всё
        await _show_not_enough_leads(
            message, state, available_count, count, allow_take_all=True
        )
        return

    # Достаточно лидов - показываем подтверждение
    await show_lead_confirmation(message, state, segment, city, count)


def _parse_lead_count(text: str) -> Optional[int]:
    """
    Парсинг количества лидов из текста

    Args:
        text: Введённый текст

    Returns:
        Количество лидов или None если невалидно
    """
    try:
        count = int(text)
        if 1 <= count <= 200:
            return count
    except ValueError:
        pass
    return None


async def _show_not_enough_leads(
    message: Message,
    state: FSMContext,
    available_count: int,
    requested_count: int,
    allow_take_all: bool = False
) -> None:
    """
    Показ сообщения о недостаточном количестве лидов

    Args:
        message: Сообщение пользователя
        state: FSM состояние
        available_count: Доступное количество
        requested_count: Запрошенное количество
        allow_take_all: Можно ли взять всё доступное (для "Прочее")
    """
    if allow_take_all:
        # Для "Прочее" или малого количества — можно взять всё
        keyboard = create_confirmation_keyboard(
            confirm_callback=f"confirm_leads:{available_count}",
            cancel_callback="cancel_leads"
        )

        if available_count < 10:
            # Малое количество в "Прочие" — предлагаем взять всё
            await message.answer(
                f"📦 В категории 'Прочие' доступно только {available_count} лидов.\n\n"
                f"Хотите взять всё доступное количество ({available_count})?\n\n"
                f"✅ Да, взять {available_count}\n"
                f"❌ Нет, отменить",
                reply_markup=keyboard
            )
        else:
            await message.answer(
                f"⚠️ Доступно только {available_count} лидов.\n\n"
                f"Или нажмите '✅ Да, взять {available_count}'",
                reply_markup=keyboard
            )
    else:
        keyboard = create_confirmation_keyboard(
            confirm_callback=f"confirm_leads:{available_count}",
            cancel_callback="cancel_leads"
        )

        await message.answer(
            format_html_safe(
                LEADS_NOT_ENOUGH,
                available=available_count,
                requested=requested_count
            ),
            reply_markup=keyboard
        )

    # Сохраняем запрошенное количество
    await state.update_data(requested_count=requested_count)
    await state.update_data(available_count=available_count)
    await state.set_state(ManagerStates.LEADS_CONFIRM)


# =============================================================================
# Подтверждение выдачи
# =============================================================================

async def show_lead_confirmation(
    message: Message,
    state: FSMContext,
    segment: str,
    city: str | None,
    count: int
):
    """Показ подтверждения выдачи лидов"""
    keyboard = create_confirmation_keyboard(
        confirm_callback=f"confirm_leads:{count}",
        cancel_callback="cancel_leads"
    )
    
    city_text = city or "Все города"
    
    await message.answer(
        format_html_safe(
            LEADS_CONFIRM,
            segment=segment,
            city=city_text,
            count=count
        ),
        reply_markup=keyboard
    )
    
    # Сохраняем данные
    await state.update_data(
        selected_segment=segment,
        selected_city=city,
        leads_count=count
    )
    await state.set_state(ManagerStates.LEADS_CONFIRM)


@router.callback_query(F.data.startswith("confirm_leads:"))
async def handle_leads_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Подтверждение выдачи лидов (импорт в Bitrix — через общую очередь)"""
    # СРАЗУ отвечаем на callback чтобы не истёк таймаут
    await callback.answer("⏳ Постановка в очередь импорта...")

    # Удаляем сообщение с кнопкой подтверждения чтобы нельзя было нажать повторно
    await safe_delete_message(callback.message)

    telegram_id = str(callback.from_user.id)

    # Берём count из FSM state (а не из callback_data) — защита от подмены через старую кнопку
    data = await state.get_data()
    segment = data.get("selected_segment")
    city = data.get("selected_city")
    count = int(data.get("leads_count", 0))

    if not segment or count == 0:
        await callback.message.answer("⚠️ Ошибка подтверждения")
        await state.clear()
        return

    # Получаем доступные лиды
    is_other = data.get("is_other", False)
    other_type = data.get("other_type", "regular")

    if is_other:
        # НЕ передаём segment — это отображаемое название ("📦 Прочее (Обыч.) — N лидов"),
        # а не реальный сегмент из БД. get_other_leads_for_assignment сам определит цели.
        leads = await crud.get_other_leads_for_assignment(
            session,
            other_type=other_type,
            limit=count,
        )
    else:
        leads = await crud.get_available_leads(
            session,
            segment,
            city,
            limit=count,
            exclude_telegram_id=telegram_id
        )

    if not leads:
        await callback.message.answer(
            "⚠️ Лиды закончились пока вы выбирали.\n"
            "Попробуйте другой сегмент."
        )
        await state.clear()
        return

    # Назначаем лиды менеджеру
    lead_ids = [lead.id for lead in leads]
    assigned_count = await crud.assign_leads_to_manager(session, lead_ids, telegram_id)

    if assigned_count == 0:
        # Все лиды уже были разобраны другим менеджером (гонка)
        try:
            await callback.message.answer(
                "⚠️ Лиды закончились пока вы выбирали.\n"
                "Попробуйте другой сегмент."
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить ошибку гонки: {e}")
        await state.clear()
        return

    await session.flush()

    city_text = city or "Все города"

    ok = await enqueue_manager_import_queue(
        session=session,
        bot=callback.bot,
        telegram_id=telegram_id,
        lead_ids=lead_ids,
        assigned_count=assigned_count,
        segment=segment,
        city_text=city_text,
        reply_message=callback.message,
    )

    if not ok:
        try:
            await callback.message.answer(
                "❌ Очередь импорта переполнена. Попробуйте позже или обратитесь к администратору.",
                reply_markup=create_manager_main_menu(),
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение об ошибке очереди: {e}")
        await state.clear()
        return

    await state.clear()

    logger.info(
        f"Менеджер {telegram_id}: {assigned_count} лидов в очереди импорта ({segment}, {city})"
    )


@router.callback_query(F.data == "lucky_leads_menu")
async def handle_lucky_leads_menu(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
):
    """Меню «Мне повезёт!»"""
    await state.clear()

    telegram_id = str(callback.from_user.id)
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    if not user or user.status.value != "ACTIVE":
        await callback.answer("🚫 Вы не активированы", show_alert=True)
        return

    regular_available = await crud.count_leads_by_utc_band(
        session, "regular", exclude_telegram_id=telegram_id
    )
    plus_available = await crud.count_leads_by_utc_band(
        session, "plusoviki", exclude_telegram_id=telegram_id
    )

    await callback.message.answer(
        format_html_safe(
            LUCKY_MENU_INTRO,
            regular_available=regular_available,
            plus_available=plus_available,
        ),
        parse_mode="HTML",
        reply_markup=create_lucky_band_keyboard(),
    )
    try:
        await callback.answer()
    except Exception as e:
        logger.debug(f"Не удалось ответить на callback: {type(e).__name__}: {e}")


@router.callback_query(F.data.startswith("lucky_pick:"))
async def handle_lucky_pick(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
):
    """Выбор пояса UTC для случайной выдачи"""
    telegram_id = str(callback.from_user.id)
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    if not user or user.status.value != "ACTIVE":
        await callback.answer("🚫 Вы не активированы", show_alert=True)
        return

    band = callback.data.split(":", 1)[1]
    if band not in ("regular", "plusoviki"):
        await callback.answer("⚠️ Ошибка", show_alert=True)
        return

    available = await crud.count_leads_by_utc_band(
        session, band, exclude_telegram_id=telegram_id
    )
    await state.update_data(lucky_band=band)
    await state.set_state(ManagerStates.LUCKY_LEADS_RANGE)

    prompt = (
        f"📊 Доступно в этом поясе: <b>{available}</b>\n\n"
        f"{LUCKY_ENTER_RANGE.strip()}"
    )
    await callback.message.answer(
        prompt,
        parse_mode="HTML",
        reply_markup=create_back_keyboard("lucky_leads_menu"),
    )
    try:
        await callback.answer()
    except Exception as e:
        logger.debug(f"Не удалось ответить на callback: {type(e).__name__}: {e}")


@router.message(StateFilter(ManagerStates.LUCKY_LEADS_RANGE))
async def handle_lucky_range_input(
    message: Message, state: FSMContext, session: AsyncSession
):
    """Ввод диапазона и случайная выдача"""
    back_kb = create_back_keyboard("lucky_leads_menu")
    parsed = parse_lucky_leads_range(message.text)
    if not parsed:
        await message.answer(
            LUCKY_RANGE_INVALID,
            parse_mode="HTML",
            reply_markup=back_kb,
        )
        return

    min_c, max_c = parsed
    data = await state.get_data()
    band = data.get("lucky_band")
    if band not in ("regular", "plusoviki"):
        await state.clear()
        await message.answer("⚠️ Сессия устарела. Начните с «Мне повезёт!» снова.")
        return

    telegram_id = str(message.from_user.id)
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    if not user or user.status.value != "ACTIVE":
        await state.clear()
        await message.answer("🚫 Вы не активированы", reply_markup=create_manager_main_menu())
        return

    available = await crud.count_leads_by_utc_band(
        session, band, exclude_telegram_id=telegram_id
    )
    if available < min_c:
        await message.answer(
            format_html_safe(
                LUCKY_NOT_ENOUGH_POOL,
                available=available,
                min_count=min_c,
            ),
            parse_mode="HTML",
            reply_markup=back_kb,
        )
        return

    target_n = random.randint(min_c, max_c)
    target_n = min(target_n, available)

    leads = await crud.get_random_leads_by_utc_band(
        session,
        band,
        limit=target_n,
        exclude_telegram_id=telegram_id,
    )
    if not leads:
        await message.answer(
            "⚠️ Не удалось выбрать лиды. Попробуйте ещё раз.",
            reply_markup=back_kb,
        )
        return

    lead_ids = [lead.id for lead in leads]
    assigned_count = await crud.assign_leads_to_manager(session, lead_ids, telegram_id)
    if assigned_count == 0:
        await message.answer(
            "⚠️ Лиды закончились. Попробуйте позже.",
            reply_markup=create_manager_main_menu(),
        )
        await state.clear()
        return

    await session.flush()

    segment_label = LUCKY_SEGMENT_REGULAR if band == "regular" else LUCKY_SEGMENT_PLUSOVIKI

    ok = await enqueue_manager_import_queue(
        session=session,
        bot=message.bot,
        telegram_id=telegram_id,
        lead_ids=lead_ids,
        assigned_count=assigned_count,
        segment=segment_label,
        city_text=LUCKY_CITY_LABEL,
        reply_message=message,
    )

    if not ok:
        await message.answer(
            "❌ Очередь импорта переполнена. Попробуйте позже или обратитесь к администратору.",
            reply_markup=create_manager_main_menu(),
        )

    await state.clear()

    logger.info(
        f"Менеджер {telegram_id}: lucky {band} target={target_n} assigned={assigned_count}"
    )


@router.callback_query(F.data == "cancel_leads")
async def handle_leads_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена выдачи лидов"""
    await state.clear()

    # Удаляем предыдущее сообщение
    await safe_delete_message(callback.message)

    await callback.message.answer(
        LEADS_CANCELLED,
        reply_markup=create_manager_main_menu()
    )

    await callback.answer()


# =============================================================================
# Кнопка "Назад"
# =============================================================================

@router.callback_query(F.data == "back_to_main")
async def handle_back_to_main(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()

    # Удаляем предыдущее сообщение
    await safe_delete_message(callback.message)

    await callback.message.answer(
        MANAGER_MAIN_MENU,
        reply_markup=create_manager_main_menu()
    )

    await callback.answer()
