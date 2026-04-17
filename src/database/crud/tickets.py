"""
CRUD для работы с тикетами обратной связи
"""
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Ticket
from ...logger import get_logger

logger = get_logger(__name__)


async def create_ticket(
    session: AsyncSession,
    manager_telegram_id: str,
    message: str
) -> Ticket:
    """Создание тикета обратной связи"""
    ticket = Ticket(
        manager_telegram_id=manager_telegram_id,
        message=message,
        status="new"
    )
    session.add(ticket)
    await session.flush()
    return ticket


async def get_ticket_by_id(session: AsyncSession, ticket_id: int) -> Optional[Ticket]:
    """Получение тикета по ID"""
    result = await session.execute(
        select(Ticket).where(Ticket.id == ticket_id)
    )
    return result.scalar_one_or_none()


async def get_tickets_paginated(
    session: AsyncSession,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
) -> Tuple[List[Ticket], int]:
    """Получение тикетов с пагинацией"""
    query = select(Ticket)
    count_query = select(func.count(Ticket.id))

    if status:
        query = query.where(Ticket.status == status)
        count_query = count_query.where(Ticket.status == status)

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(Ticket.created_at.desc()).offset(offset).limit(page_size)

    result = await session.execute(query)
    tickets = result.scalars().all()

    return tickets, total


async def get_ticket_stats(session: AsyncSession) -> Dict[str, int]:
    """Получение статистики тикетов по статусам"""
    result = await session.execute(
        select(Ticket.status, func.count(Ticket.id))
        .group_by(Ticket.status)
    )

    stats = {"new": 0, "in_progress": 0, "resolved": 0, "closed": 0}
    for row in result.all():
        status, count = row
        if status in stats:
            stats[status] = count

    return stats


async def update_ticket_status(
    session: AsyncSession,
    ticket_id: int,
    status: str,
    admin_telegram_id: Optional[str] = None
) -> bool:
    """Обновление статуса тикета"""
    update_data: Dict = {"status": status}

    if admin_telegram_id:
        update_data["admin_telegram_id"] = admin_telegram_id

    if status == "in_progress":
        update_data["responded_at"] = datetime.now(timezone.utc)
    elif status in ["resolved", "closed"]:
        update_data["resolved_at"] = datetime.now(timezone.utc)

    result = await session.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id)
        .values(**update_data)
    )
    return result.rowcount > 0


async def add_admin_response(
    session: AsyncSession,
    ticket_id: int,
    admin_telegram_id: str,
    response: str
) -> bool:
    """Добавление ответа администратора на тикет"""
    result = await session.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id)
        .values(
            admin_response=response,
            responded_at=datetime.now(timezone.utc),
            admin_telegram_id=admin_telegram_id,
            status="in_progress"
        )
    )
    return result.rowcount > 0


async def get_tickets_by_manager(
    session: AsyncSession,
    manager_telegram_id: str,
    limit: int = 10
) -> List[Ticket]:
    """Получение тикетов менеджера"""
    result = await session.execute(
        select(Ticket)
        .where(Ticket.manager_telegram_id == manager_telegram_id)
        .order_by(Ticket.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()
