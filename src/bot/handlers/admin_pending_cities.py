"""
Обработчик управления pending городами

Админ может:
- Просматривать список городов ожидающих UTC
- Вводить UTC offset для города
- Одобрять город (лиды становятся UNIQUE)
- Отклонять город (лиды удаляются)
"""
import re
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from ..states import AdminStates
from ..messages.texts import (
    BTN_BACK,
)
from ..keyboards.keyboard_factory import create_back_keyboard
from ...database import crud
from ...logger import get_logger

logger = get_logger(__name__)

router = Router()

# Тексты
PENDING_CITIES_MENU = """
🌍 <b>Управление городами</b>

Ожидают ввода UTC: {pending_count}

Введите команду:
• <code>+3 Екатеринбург</code> — одобрить город (+3ч от МСК)
• <code>-1 Калининград</code> — одобрить город (-1ч от МСК)
• <code>удалить Новосибирск</code> — удалить город и лиды

Диапазон: от -12 до +12 часов от Москвы
"""

CITY_APPROVED = """
✅ <b>Город одобрен!</b>

🏙 {city_name} ({utc_offset:+d}ч от МСК)
📊 Активировано лидов: {approved}
"""

CITY_REJECTED = """
❌ <b>Город удалён</b>

🏙 {city_name}
🗑 Удалено лидов: {deleted_leads}
"""

CITY_INPUT_ERROR = """
❌ <b>Ошибка ввода</b>

Формат: <code>+3 Екатеринбург</code> или <code>-1 Калининград</code>
Диапазон: от -12 до +12

Примеры:
• <code>+3 Екатеринбург</code>
• <code>+7 Новосибирск</code>
• <code>-1 Калининград</code>
• <code>0 Москва</code>
"""

CITY_NOT_FOUND = """
⚠️ <b>Город не найден</b>

Введите имя города точно как в списке pending:
"""


@router.callback_query(F.data == "admin_pending_cities")
async def handle_pending_cities_menu(callback: CallbackQuery, session: AsyncSession):
    """Меню pending городов"""
    pending_count = await crud.count_pending_cities(session)

    await callback.message.answer(
        PENDING_CITIES_MENU.format(pending_count=pending_count),
        reply_markup=create_back_keyboard("admin_menu"),
        parse_mode="HTML"
    )

    await callback.answer()


@router.message(StateFilter(AdminStates.BROADCAST_INPUT_TEXT, AdminStates.BROADCAST_CONFIRM), F.text)
async def handle_broadcast_messages(message: Message, state: FSMContext):
    """Проброс сообщений для рассылки (если состояние активно)"""
    # Этот обработчик нужен чтобы не конфликтовать с рассылкой
    pass


@router.message(F.text.regexp(r"^(?i)(удалить|DELETE)\s+(.+)$"))
async def handle_city_reject(message: Message, session: AsyncSession):
    """Отклонение города: 'удалить Новосибирск' или 'DELETE Novosibirsk'"""
    match = re.match(r"^(?:удалить|DELETE)\s+(.+)$", message.text.strip(), re.IGNORECASE)
    if not match:
        return

    city_name = match.group(1).strip()

    result = await crud.reject_pending_city(session, city_name)
    await session.commit()

    await message.answer(
        CITY_REJECTED.format(
            city_name=city_name,
            deleted_leads=result.get("deleted_leads", 0)
        ),
        reply_markup=create_back_keyboard("admin_pending_cities"),
        parse_mode="HTML"
    )


@router.message(F.text.regexp(r"^([+-]?\d{1,2})\s+(.+)$"))
async def handle_city_approve(message: Message, session: AsyncSession):
    """Одобрение города: '+3 Екатеринбург' или '-1 Калининград'"""
    match = re.match(r"^([+-]?\d{1,2})\s+(.+)$", message.text.strip())
    if not match:
        await message.answer(
            CITY_INPUT_ERROR,
            reply_markup=create_back_keyboard("admin_pending_cities"),
            parse_mode="HTML"
        )
        return

    utc_offset = int(match.group(1))
    city_name = match.group(2).strip()

    # Проверка диапазона
    if utc_offset < -12 or utc_offset > 12:
        await message.answer(
            "❌ UTC offset должен быть от -12 до +12",
            reply_markup=create_back_keyboard("admin_pending_cities")
        )
        return

    # Проверяем, есть ли такой pending город
    pending_cities = await crud.get_pending_cities(session)
    pending_names = [c.name.lower() for c in pending_cities]

    # Ищем точное совпадение или частичное
    found_city = None
    for pc in pending_cities:
        if pc.name.lower() == city_name.lower():
            found_city = pc.name
            break

    if not found_city:
        # Пробуем частичное совпадение
        for pc in pending_cities:
            if city_name.lower() in pc.name.lower():
                found_city = pc.name
                break

    if not found_city:
        # Показываем список pending городов
        if pending_cities:
            cities_list = "\n".join([f"• {c.name}" for c in pending_cities])
            await message.answer(
                f"{CITY_NOT_FOUND}\n\n📋 <b>Ожидают UTC:</b>\n{cities_list}",
                reply_markup=create_back_keyboard("admin_pending_cities"),
                parse_mode="HTML"
            )
        else:
            await message.answer(
                "✅ Нет городов ожидающих UTC",
                reply_markup=create_back_keyboard("admin_pending_cities")
            )
        return

    # Одобряем город
    result = await crud.approve_pending_city(session, found_city, utc_offset)
    await session.commit()

    await message.answer(
        CITY_APPROVED.format(
            city_name=found_city,
            utc_offset=utc_offset,
            approved=result.get("approved", 0)
        ),
        reply_markup=create_back_keyboard("admin_pending_cities"),
        parse_mode="HTML"
    )

    pending_count = await crud.count_pending_cities(session)
    if pending_count > 0:
        await message.answer(
            f"📋 Ожидают ещё: {pending_count}",
            reply_markup=create_back_keyboard("admin_pending_cities")
        )
