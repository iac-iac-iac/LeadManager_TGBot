"""
Модуль аналитики и формирования отчётов

Агрегация метрик по дням/неделям/месяцам
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import csv
from pathlib import Path

from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import Lead, LeadStatus, User, Log
from ..logger import get_logger

logger = get_logger(__name__)


class AnalyticsService:
    """Сервис аналитики лидов"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_stats_for_period(
        self,
        start_date: datetime,
        end_date: datetime,
        segment: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Получение статистики за период
        
        Args:
            start_date: Начало периода
            end_date: Конец периода
            segment: Сегмент (опционально)
            
        Returns:
            Dict со статистикой
        """
        # Базовый запрос
        query = select(
            Lead.status,
            func.count(Lead.id).label('count')
        ).where(
            Lead.created_at >= start_date,
            Lead.created_at <= end_date
        )
        
        if segment:
            query = query.where(Lead.segment == segment)
        
        query = query.group_by(Lead.status)
        
        result = await self.session.execute(query)
        rows = result.all()
        
        # Формируем статистику
        stats = {
            'loaded': 0,
            'duplicates': 0,
            'unique': 0,
            'assigned': 0,
            'imported': 0,
            'errors': 0
        }
        
        for row in rows:
            status, count = row
            if status == LeadStatus.NEW:
                stats['loaded'] = count
            elif status == LeadStatus.DUPLICATE:
                stats['duplicates'] = count
            elif status == LeadStatus.UNIQUE:
                stats['unique'] = count
            elif status == LeadStatus.ASSIGNED:
                stats['assigned'] = count
            elif status == LeadStatus.IMPORTED:
                stats['imported'] = count
            elif status == LeadStatus.ERROR_IMPORT:
                stats['errors'] = count
        
        # Считаем проценты
        total_checked = stats['duplicates'] + stats['unique']
        stats['duplicate_percent'] = round(
            (stats['duplicates'] / total_checked * 100) if total_checked > 0 else 0,
            2
        )
        
        return stats
    
    async def get_stats_by_segment(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Dict[str, int]]:
        """
        Статистика по сегментам
        
        Returns:
            {"Сегмент": {"imported": N, "assigned": N}, ...}
        """
        query = select(
            Lead.segment,
            Lead.status,
            func.count(Lead.id).label('count')
        ).where(
            Lead.created_at >= start_date,
            Lead.created_at <= end_date,
            Lead.status.in_([LeadStatus.IMPORTED, LeadStatus.ASSIGNED])
        ).group_by(Lead.segment, Lead.status)
        
        result = await self.session.execute(query)
        
        stats: Dict[str, Dict[str, int]] = {}
        for segment, status, count in result.all():
            if segment not in stats:
                stats[segment] = {'imported': 0, 'assigned': 0}
            
            if status == LeadStatus.IMPORTED:
                stats[segment]['imported'] = count
            elif status == LeadStatus.ASSIGNED:
                stats[segment]['assigned'] = count
        
        return stats
    
    async def get_stats_by_manager(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Dict[str, Any]]:
        """
        Статистика по менеджерам

        Returns:
            {"Telegram ID": {"full_name": str, "imported": N, "assigned": N}, ...}
        """
        # Исправление N+1: используем JOIN с User вместо отдельных запросов
        query = select(
            Lead.manager_telegram_id,
            Lead.status,
            func.count(Lead.id).label('count'),
            User.full_name
        ).join(
            User, Lead.manager_telegram_id == User.telegram_id, isouter=True
        ).where(
            Lead.manager_telegram_id.isnot(None),
            Lead.assigned_at >= start_date,
            Lead.assigned_at <= end_date,
            Lead.status.in_([LeadStatus.IMPORTED, LeadStatus.ASSIGNED])
        ).group_by(Lead.manager_telegram_id, Lead.status, User.full_name)

        result = await self.session.execute(query)

        stats: Dict[str, Dict[str, Any]] = {}
        for telegram_id, status, count, full_name in result.all():
            if telegram_id not in stats:
                stats[telegram_id] = {
                    'full_name': full_name or str(telegram_id),
                    'imported': 0,
                    'assigned': 0
                }

            if status == LeadStatus.IMPORTED:
                stats[telegram_id]['imported'] = count
            elif status == LeadStatus.ASSIGNED:
                stats[telegram_id]['assigned'] = count

        return stats
    
    async def get_daily_stats(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Ежедневная статистика
        
        Returns:
            Список [{"date": str, "imported": N, "duplicates": N}, ...]
        """
        # Для SQLite используем date() функцию
        query = select(
            func.date(Lead.created_at).label('date'),
            Lead.status,
            func.count(Lead.id).label('count')
        ).where(
            Lead.created_at >= start_date,
            Lead.created_at <= end_date
        ).group_by(func.date(Lead.created_at), Lead.status)
        
        result = await self.session.execute(query)
        
        # Группируем по датам
        daily_stats: Dict[str, Dict[str, int]] = {}
        for date, status, count in result.all():
            date_str = str(date)
            if date_str not in daily_stats:
                daily_stats[date_str] = {
                    'loaded': 0,
                    'duplicates': 0,
                    'unique': 0,
                    'imported': 0,
                    'assigned': 0
                }
            
            daily_stats[date_str][status.value.lower()] = count
        
        return [
            {'date': date, **stats}
            for date, stats in sorted(daily_stats.items())
        ]


class ReportExporter:
    """Экспорт отчётов в CSV"""
    
    def __init__(self, analytics: AnalyticsService):
        self.analytics = analytics
    
    async def export_stats_to_csv(
        self,
        output_path: Path,
        start_date: datetime,
        end_date: datetime
    ) -> Path:
        """
        Экспорт статистики в CSV
        
        Args:
            output_path: Путь для сохранения
            start_date: Начало периода
            end_date: Конец периода
            
        Returns:
            Путь к сохранённому файлу
        """
        # Получаем данные
        daily_stats = await self.analytics.get_daily_stats(start_date, end_date)
        segment_stats = await self.analytics.get_stats_by_segment(start_date, end_date)
        manager_stats = await self.analytics.get_stats_by_manager(start_date, end_date)
        
        # Создаём CSV файл с UTF-8 BOM для Excel
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            
            # Заголовок
            writer.writerow(['Статистика за период', 
                           start_date.strftime('%Y-%m-%d'), 
                           end_date.strftime('%Y-%m-%d')])
            writer.writerow([])
            
            # Ежедневная статистика
            writer.writerow(['Дата', 'Загружено', 'Дубли', 'Уникальные', 'Выдано', 'Импортировано'])
            for day in daily_stats:
                writer.writerow([
                    day['date'],
                    day.get('loaded', 0),
                    day.get('duplicates', 0),
                    day.get('unique', 0),
                    day.get('assigned', 0),
                    day.get('imported', 0)
                ])
            
            writer.writerow([])
            
            # По сегментам
            writer.writerow(['Сегмент', 'Импортировано', 'Выдано'])
            for segment, stats in segment_stats.items():
                writer.writerow([
                    segment,
                    stats.get('imported', 0),
                    stats.get('assigned', 0)
                ])
            
            writer.writerow([])
            
            # По менеджерам
            writer.writerow(['Менеджер', 'Импортировано', 'Выдано'])
            for telegram_id, stats in manager_stats.items():
                writer.writerow([
                    stats.get('full_name', telegram_id),
                    stats.get('imported', 0),
                    stats.get('assigned', 0)
                ])
        
        logger.info(f"Отчёт экспортирован в {output_path}")
        return output_path


async def get_analytics_report(
    session: AsyncSession,
    period: str = 'today'
) -> Dict[str, Any]:
    """
    Получение отчёта за период
    
    Args:
        session: Сессия БД
        period: 'today', 'week', 'month', 'all'
        
    Returns:
        Dict с отчётом
    """
    analytics = AnalyticsService(session)
    
    # Определяем даты (используем timezone-aware datetime)
    now = datetime.now(timezone.utc)

    if period == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif period == 'week':
        days_since_monday = now.weekday()
        start_date = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif period == 'month':
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    else:  # 'all'
        # Получаем самую раннюю запись
        result = await session.execute(
            select(func.min(Lead.created_at))
        )
        start_date = result.scalar() or now - timedelta(days=365)
        end_date = now
    
    # Получаем общую статистику
    stats = await analytics.get_stats_for_period(start_date, end_date)
    
    # По сегментам
    segment_stats = await analytics.get_stats_by_segment(start_date, end_date)
    
    # По менеджерам
    manager_stats = await analytics.get_stats_by_manager(start_date, end_date)
    
    return {
        'period': period,
        'start_date': start_date,
        'end_date': end_date,
        'stats': stats,
        'segment_stats': segment_stats,
        'manager_stats': manager_stats
    }
