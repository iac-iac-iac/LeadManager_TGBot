"""
CRUD для работы со статусом бота
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import BotStatus
from ...logger import get_logger

logger = get_logger(__name__)


async def get_bot_status(session: AsyncSession) -> Optional[BotStatus]:
    """Получение текущего статуса бота (запись id=1)"""
    result = await session.execute(select(BotStatus).where(BotStatus.id == 1))
    return result.scalar_one_or_none()


async def set_bot_status(
    session: AsyncSession,
    status: str,
    reason: Optional[str] = None
) -> BotStatus:
    """Установка статуса бота (running / stopped / maintenance)"""
    bot_status = await get_bot_status(session)

    if bot_status:
        await session.execute(
            update(BotStatus)
            .where(BotStatus.id == 1)
            .values(
                status=status,
                reason=reason,
                updated_at=datetime.now(timezone.utc)
            )
        )
    else:
        bot_status = BotStatus(id=1, status=status, reason=reason)
        session.add(bot_status)

    await session.flush()
    return await get_bot_status(session)


async def is_bot_running(session: AsyncSession) -> bool:
    """True если бот работает (по умолчанию True если запись не найдена)"""
    bot_status = await get_bot_status(session)
    if not bot_status:
        return True
    return bot_status.status == "running"


async def is_bot_maintenance(session: AsyncSession) -> bool:
    """True если бот в режиме техработ"""
    bot_status = await get_bot_status(session)
    if not bot_status:
        return False
    return bot_status.status == "maintenance"
