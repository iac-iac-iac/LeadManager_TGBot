"""
CRUD для работы с пользователями
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, UserRole, UserStatus, Lead
from ...logger import get_logger

logger = get_logger(__name__)


async def create_user(
    session: AsyncSession,
    telegram_id: str,
    full_name: Optional[str] = None,
    username: Optional[str] = None,
    role: UserRole = UserRole.MANAGER,
    status: UserStatus = UserStatus.PENDING_APPROVAL,
    bitrix24_user_id: Optional[int] = None
) -> User:
    """Создание пользователя"""
    user = User(
        telegram_id=telegram_id,
        full_name=full_name,
        username=username,
        role=role,
        status=status,
        bitrix24_user_id=bitrix24_user_id
    )
    session.add(user)
    await session.flush()
    return user


async def get_user_by_telegram_id(
    session: AsyncSession,
    telegram_id: str
) -> Optional[User]:
    """Получение пользователя по Telegram ID"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_full_name(
    session: AsyncSession,
    full_name: str
) -> Optional[User]:
    """Получение пользователя по ФИО (для привязки из CSV)"""
    result = await session.execute(
        select(User).where(User.full_name == full_name)
    )
    return result.scalar_one_or_none()


async def get_pending_users(session: AsyncSession) -> List[User]:
    """Получение пользователей, ожидающих подтверждения (в порядке регистрации)"""
    result = await session.execute(
        select(User)
        .where(User.status == UserStatus.PENDING_APPROVAL)
        .order_by(User.registered_at)
    )
    return result.scalars().all()


async def approve_user(
    session: AsyncSession,
    telegram_id: str,
    bitrix24_user_id: int
) -> Optional[User]:
    """Подтверждение пользователя админом"""
    await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(
            status=UserStatus.ACTIVE,
            bitrix24_user_id=bitrix24_user_id,
            approved_at=datetime.now(timezone.utc)
        )
    )
    return await get_user_by_telegram_id(session, telegram_id)


async def reject_user(
    session: AsyncSession,
    telegram_id: str
) -> Optional[User]:
    """Отклонение пользователя"""
    await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(status=UserStatus.REJECTED)
    )
    return await get_user_by_telegram_id(session, telegram_id)


async def update_user_name(
    session: AsyncSession,
    telegram_id: str,
    full_name: str
) -> None:
    """Обновление имени пользователя"""
    await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(full_name=full_name)
    )


async def update_user_role(
    session: AsyncSession,
    telegram_id: str,
    role: UserRole
) -> Optional[User]:
    """Обновление роли пользователя"""
    await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(role=role)
    )
    return await get_user_by_telegram_id(session, telegram_id)


async def get_all_active_admins(session: AsyncSession) -> List[User]:
    """Получение всех активных админов"""
    result = await session.execute(
        select(User)
        .where(
            User.role == UserRole.ADMIN,
            User.status == UserStatus.ACTIVE
        )
        .order_by(User.telegram_id)
    )
    return result.scalars().all()


async def get_all_active_users(session: AsyncSession) -> List[User]:
    """Получение всех активных пользователей (админы + менеджеры)"""
    result = await session.execute(
        select(User)
        .where(User.status == UserStatus.ACTIVE)
        .order_by(User.telegram_id)
    )
    return result.scalars().all()


async def get_active_managers_with_stats(session: AsyncSession) -> List[Dict[str, Any]]:
    """Получение активных менеджеров со статистикой лидов"""
    result = await session.execute(
        select(
            User.telegram_id,
            User.full_name,
            func.count(Lead.id).label("leads_count")
        )
        .outerjoin(Lead, User.telegram_id == Lead.manager_telegram_id)
        .where(
            User.role == UserRole.MANAGER,
            User.status == UserStatus.ACTIVE
        )
        .group_by(User.telegram_id, User.full_name)
        .order_by(User.full_name)
    )

    managers = []
    for row in result.all():
        managers.append({
            "telegram_id": row.telegram_id,
            "full_name": row.full_name or "Без имени",
            "leads_count": row.leads_count or 0
        })

    return managers
