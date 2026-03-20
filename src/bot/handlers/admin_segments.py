"""
Обработчик управления сегментами

Заморозка/разморозка сегментов и сегмент+город
"""
from typing import List, Dict

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..states import AdminStates
from ..messages.texts import (
    SEGMENTS_LIST,
    SEGMENT_STATUS_ACTIVE,
    SEGMENT_STATUS_FROZEN,
    SEGMENT_DETAIL,
    SEGMENT_FROZEN_SUCCESS,
    SEGMENT_UNFROZEN_SUCCESS,
    ADMIN_MAIN_MENU,
)
from ..keyboards.keyboard_factory import (
    create_segments_admin_keyboard,
    create_segment_action_keyboard,
    create_back_keyboard,
    parse_callback_data,
)
from ...database import crud
from ...database.models import Lead, LeadStatus, SegmentLock
from ...logger import get_logger

logger = get_logger(__name__)

router = Router()


# =============================================================================
# Меню управления сегментами
# =============================================================================

@router.callback_query(F.data == "admin_segments")
async def handle_admin_segments(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Показ списка сегментов с пагинацией"""
    from ...database.models import Segment
    
    # Синхронизируем сегменты из leads (на случай если добавлены новые)
    added_count = await crud.sync_segments_from_leads(session)
    
    if added_count > 0:
        logger.info(f"Добавлено {added_count} новых сегментов из leads")
    
    # Получаем все активные сегменты
    segments = await crud.get_all_segments(session, active_only=True)
    
    logger.info(f"Получено сегментов: {len(segments)}")
    
    if not segments:
        await callback.message.answer(
            "⚠️ Нет доступных сегментов.\n"
            "Импортируйте лиды через CSV."
        )
        await callback.answer()
        return
    
    # Сохраняем список сегментов в состоянии для пагинации
    segments_list = []
    
    for segment in segments:
        # Проверяем заморозку всего сегмента
        lock = await crud.get_segment_lock(session, segment.name, city=None)
        is_frozen = lock.is_frozen if lock else False
        
        # Считаем количество доступных лидов в сегменте
        count_result = await session.execute(
            select(func.count(Lead.id)).where(
                Lead.segment == segment.name,
                Lead.status == LeadStatus.UNIQUE
            )
        )
        count = count_result.scalar() or 0
        
        segments_list.append({
            "segment": segment.name,
            "city": None,
            "is_frozen": is_frozen,
            "count": count
        })
        
        # Проверяем заморозки по городам
        city_locks_result = await session.execute(
            select(SegmentLock.city, SegmentLock.is_frozen)
            .where(SegmentLock.segment == segment.name, SegmentLock.city.isnot(None))
        )
        
        for city, city_frozen in city_locks_result.all():
            segments_list.append({
                "segment": segment.name,
                "city": city,
                "is_frozen": city_frozen,
                "count": 0  # Для городов не показываем count
            })
    
    # Сохраняем в состоянии
    await state.update_data(segments_list=segments_list, current_page=0)
    
    # Показываем первую страницу
    keyboard = create_segments_admin_keyboard(segments_list, page=0, page_size=20)
    
    await callback.message.answer(
        SEGMENTS_LIST.format(
            segments="\n".join([
                f"{'❄️' if s['is_frozen'] else '✅'} {s['segment']}" +
                (f" + {s['city']}" if s['city'] else "")
                for s in segments_list[:20]  # Показываем первые 20 в тексте
            ])
        ),
        reply_markup=keyboard
    )
    
    await callback.answer()


# =============================================================================
# Пагинация сегментов
# =============================================================================

@router.callback_query(F.data.startswith("segments_page:"))
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
    segments_list = state_data.get("segments_list", [])

    if not segments_list:
        await callback.answer("⚠️ Список сегментов не найден", show_alert=True)
        return

    # Сохраняем новую страницу
    await state.update_data(current_page=new_page)

    # Показываем страницу (edit_text для пагинации)
    keyboard = create_segments_admin_keyboard(segments_list, page=new_page, page_size=20)

    # Показываем сегменты текущей страницы
    page_size = 20
    start_idx = new_page * page_size
    end_idx = min(start_idx + page_size, len(segments_list))

    try:
        await callback.message.edit_text(
            SEGMENTS_LIST.format(
                segments="\n".join([
                    f"{'❄️' if s['is_frozen'] else '✅'} {s['segment']}" +
                    (f" + {s['city']}" if s['city'] else "")
                    for s in segments_list[start_idx:end_idx]
                ])
            ),
            reply_markup=keyboard
        )
    except Exception:
        # Если сообщение нельзя редактировать - удаляем и создаём новое
        try:
            await callback.message.delete()
        except Exception:
            pass
        
        await callback.message.answer(
            SEGMENTS_LIST.format(
                segments="\n".join([
                    f"{'❄️' if s['is_frozen'] else '✅'} {s['segment']}" +
                    (f" + {s['city']}" if s['city'] else "")
                    for s in segments_list[start_idx:end_idx]
                ])
            ),
            reply_markup=keyboard
        )

    await callback.answer()


@router.callback_query(F.data == "segments_page_info")
async def handle_segments_page_info(callback: CallbackQuery):
    """Информация о странице (просто подтверждаем)"""
    await callback.answer()


# =============================================================================
# Выбор сегмента для управления
# =============================================================================

@router.callback_query(F.data.startswith("segment_manage:"))
async def handle_segment_manage(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Показ деталей сегмента с полной обработкой ошибок"""
    try:
        parsed = parse_callback_data(callback.data)

        if not parsed["params"]:
            logger.error("segment_manage: отсутствуют параметры")
            await callback.answer("⚠️ Ошибка выбора сегмента", show_alert=True)
            return

        # Получаем индекс сегмента
        try:
            segment_index = int(parsed["params"][0])
        except ValueError as e:
            logger.error(f"segment_manage: некорректный индекс {parsed['params'][0]}: {e}")
            await callback.answer("⚠️ Ошибка формата индекса", show_alert=True)
            return

        # Получаем все сегменты из БД
        from sqlalchemy import select
        from sqlalchemy.exc import SQLAlchemyError
        from ...database.models import Segment, SegmentLock

        try:
            # Получаем все активные сегменты из таблицы segments
            segments = await crud.get_all_segments(session, active_only=True)
        except SQLAlchemyError as e:
            logger.error(f"segment_manage: ошибка БД при получении сегментов: {e}")
            await callback.answer("⚠️ Ошибка получения данных из БД", show_alert=True)
            return
        except Exception as e:
            logger.error(f"segment_manage: непредвиденная ошибка: {type(e).__name__}: {e}")
            await callback.answer("⚠️ Внутренняя ошибка", show_alert=True)
            return

        logger.info(f"Получено сегментов: {len(segments)}")

        if not segments:
            await callback.answer("⚠️ Нет доступных сегментов", show_alert=True)
            return

        # Формируем список сегментов с информацией о заморозке
        segments_list = []

        for segment in segments:
            try:
                # Проверяем заморозку всего сегмента
                lock = await crud.get_segment_lock(session, segment.name, city=None)
                is_frozen = lock.is_frozen if lock else False

                segments_list.append({
                    "segment": segment.name,
                    "city": None,  # Все города
                    "is_frozen": is_frozen
                })
            except Exception as e:
                logger.warning(f"segment_manage: ошибка обработки сегмента {segment.name}: {e}")
                # Продолжаем с другими сегментами

        logger.info(f"Всего уникальных сегментов: {len(segments_list)}, выбран индекс: {segment_index}")

        # Проверяем индекс
        if segment_index >= len(segments_list) or segment_index < 0:
            logger.error(f"Индекс {segment_index} вне диапазона (0-{len(segments_list)-1})")
            await callback.answer(
                f"⚠️ Сегмент не найден (индекс {segment_index} из {len(segments_list)})",
                show_alert=True
            )
            return

        # Получаем выбранный сегмент
        selected = segments_list[segment_index]
        segment = selected["segment"]
        city = selected["city"]

        logger.info(f"Выбран сегмент: {segment} + {city}")

        # Сохраняем в состоянии для последующих действий
        await state.update_data(selected_segment=segment, selected_city=city)

        # Проверяем заморозку
        try:
            lock = await crud.get_segment_lock(session, segment, city)
            is_frozen = lock.is_frozen if lock else False
        except Exception as e:
            logger.error(f"segment_manage: ошибка проверки заморозки: {e}")
            is_frozen = False  # По умолчанию считаем не замороженным

        # Считаем доступные лиды
        try:
            available_count = await crud.count_available_leads(session, segment, city)
        except Exception as e:
            logger.error(f"segment_manage: ошибка подсчёта лидов: {e}")
            available_count = 0

    except Exception as e:
        # Глобальная обработка ошибок
        logger.critical(f"segment_manage: критическая ошибка: {type(e).__name__}: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла непредвиденная ошибка", show_alert=True)
        return

    # Формируем сообщение
    city_text = f" + {city}" if city else ""

    # Удаляем предыдущее сообщение
    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        SEGMENT_DETAIL.format(
            segment=segment,
            available=available_count,
            frozen="Да" if is_frozen else "Нет"
        ),
        reply_markup=create_segment_action_keyboard(segment, city, is_frozen)
    )

    await callback.answer()


# =============================================================================
# Заморозка сегмента
# =============================================================================

@router.callback_query(F.data == "segment_freeze")
async def handle_segment_freeze(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Заморозка сегмента"""
    # Получаем данные из состояния
    state_data = await state.get_data()
    segment = state_data.get("selected_segment")
    city = state_data.get("selected_city")

    if not segment:
        await callback.answer("⚠️ Сегмент не выбран", show_alert=True)
        return

    try:
        # Замораживаем
        await crud.freeze_segment(session, segment, city)
        await session.commit()

        logger.info(f"Сегмент заморожен: {segment}{' + ' + city if city else ''}")

        await callback.message.answer(
            SEGMENT_FROZEN_SUCCESS.format(
                segment=segment,
                city=city or "Все города"
            )
        )

    except Exception as e:
        logger.error(f"Ошибка заморозки сегмента {segment}: {e}")
        await callback.answer("❌ Ошибка при заморозке", show_alert=True)

    await callback.answer()


# =============================================================================
# Разморозка сегмента
# =============================================================================

@router.callback_query(F.data == "segment_unfreeze")
async def handle_segment_unfreeze(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Разморозка сегмента"""
    # Получаем данные из состояния
    state_data = await state.get_data()
    segment = state_data.get("selected_segment")
    city = state_data.get("selected_city")

    if not segment:
        await callback.answer("⚠️ Сегмент не выбран", show_alert=True)
        return

    try:
        # Размораживаем
        await crud.unfreeze_segment(session, segment, city)
        await session.commit()

        logger.info(f"Сегмент разморожен: {segment}{' + ' + city if city else ''}")

        await callback.message.answer(
            SEGMENT_UNFROZEN_SUCCESS.format(
                segment=segment,
                city=city or "Все города"
            )
        )

    except Exception as e:
        logger.error(f"Ошибка разморозки сегмента {segment}: {e}")
        await callback.answer("❌ Ошибка при разморозке", show_alert=True)

    await callback.answer()
