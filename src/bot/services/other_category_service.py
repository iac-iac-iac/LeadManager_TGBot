"""
OtherCategoryService — единая логика категории 'Прочее'.

Заменяет дублирующийся код в:
- crud.leads.count_other_leads
- crud.leads.get_other_leads_for_assignment
- crud.segments.get_segments_with_cities (часть про прочее)
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.models import Lead, LeadStatus, City, SegmentLock
from ...logger import get_logger

logger = get_logger(__name__)


@dataclass
class SegmentClassification:
    """Результат классификации сегментов и городов"""
    # Пары (segment, city) для Обыч.
    regular_targets: List[Tuple[str, Optional[str]]] = field(default_factory=list)
    # Пары (segment, city) для Плюсовиков
    plusoviki_targets: List[Tuple[str, Optional[str]]] = field(default_factory=list)
    # Суммарное кол-во лидов Обыч.
    regular_count: int = 0
    # Суммарное кол-во лидов Плюсовики
    plusoviki_count: int = 0


class OtherCategoryService:
    """
    Сервис для работы с категорией 'Прочее'.

    Реализует классификацию сегментов/городов по пороговым значениям
    и получение лидов для выдачи.

    Параметры классификации:
        tail_threshold: Порог «хвоста» — если число лидов в (сегмент+город)
                        меньше этого значения, они попадают в «Прочее» (default=10).
        plusoviki_threshold: Если UTC offset города >= порога — это Плюсовики
                             (default=3 часа от МСК).
    """

    def __init__(
        self,
        tail_threshold: int = 10,
        plusoviki_threshold: int = 3
    ):
        self.tail_threshold = tail_threshold
        self.plusoviki_threshold = plusoviki_threshold

    async def classify(
        self,
        session: AsyncSession,
        exclude_frozen: bool = True
    ) -> SegmentClassification:
        """
        Классифицирует все UNIQUE лиды по категориям Обыч./Плюсовики.

        Кэширует словарь городов в пределах вызова (один SELECT).

        Returns:
            SegmentClassification с целевыми парами и суммарным количеством.
        """
        city_utc = await self._load_city_utc(session)

        segment_city_counts: Dict[str, Dict[str, int]] = {}
        segment_total_counts: Dict[str, int] = {}

        rows = await session.execute(
            select(Lead.segment, Lead.city, func.count(Lead.id).label("cnt"))
            .where(Lead.status == LeadStatus.UNIQUE)
            .group_by(Lead.segment, Lead.city)
        )
        for seg, city, count in rows.all():
            city_key = city or ""
            if seg not in segment_city_counts:
                segment_city_counts[seg] = {}
                segment_total_counts[seg] = 0
            segment_city_counts[seg][city_key] = count
            segment_total_counts[seg] += count

        if exclude_frozen:
            segment_city_counts, segment_total_counts = await self._exclude_frozen(
                session, segment_city_counts, segment_total_counts
            )

        result = SegmentClassification()

        for seg, city_counts in segment_city_counts.items():
            seg_total = segment_total_counts.get(seg, 0)

            if seg_total < self.tail_threshold:
                # Весь сегмент — «хвост»; UTC берём по первому городу
                first_city = next(iter(city_counts.keys()), "")
                utc = city_utc.get(first_city, 0)
                for city_name in city_counts.keys():
                    city_val = city_name if city_name else None
                    if utc >= self.plusoviki_threshold:
                        result.plusoviki_targets.append((seg, city_val))
                        result.plusoviki_count += city_counts[city_name]
                    else:
                        result.regular_targets.append((seg, city_val))
                        result.regular_count += city_counts[city_name]
            else:
                # Большой сегмент — берём только города-«хвосты»
                for city_name, count in city_counts.items():
                    if count < self.tail_threshold:
                        utc = city_utc.get(city_name, 0)
                        city_val = city_name if city_name else None
                        if utc >= self.plusoviki_threshold:
                            result.plusoviki_targets.append((seg, city_val))
                            result.plusoviki_count += count
                        else:
                            result.regular_targets.append((seg, city_val))
                            result.regular_count += count

        logger.info(
            f"OtherCategoryService.classify: regular={result.regular_count}, "
            f"plusoviki={result.plusoviki_count}"
        )
        return result

    async def count_by_type(
        self,
        session: AsyncSession,
        other_type: str,
        exclude_frozen: bool = True
    ) -> int:
        """
        Подсчёт лидов категории 'Прочее'.

        Args:
            other_type: 'regular' или 'plusoviki'
        """
        classification = await self.classify(session, exclude_frozen)
        if other_type == "regular":
            return classification.regular_count
        elif other_type == "plusoviki":
            return classification.plusoviki_count
        return 0

    async def get_leads_by_type(
        self,
        session: AsyncSession,
        other_type: str,
        limit: int = 200,
        exclude_frozen: bool = True
    ) -> List[Lead]:
        """
        Получение лидов категории 'Прочее' для выдачи.

        Args:
            other_type: 'regular' или 'plusoviki'
            limit: Максимальное количество лидов
        """
        from sqlalchemy import or_

        classification = await self.classify(session, exclude_frozen)
        targets = (
            classification.regular_targets
            if other_type == "regular"
            else classification.plusoviki_targets
        )

        if not targets:
            return []

        conditions = []
        for seg, city in targets:
            if city is None:
                conditions.append((Lead.segment == seg) & (Lead.city.is_(None)))
            else:
                conditions.append((Lead.segment == seg) & (Lead.city == city))

        rows = await session.execute(
            select(Lead)
            .where(or_(*conditions), Lead.status == LeadStatus.UNIQUE)
            .order_by(Lead.created_at)
            .limit(limit)
        )
        return rows.scalars().all()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _load_city_utc(self, session: AsyncSession) -> Dict[str, int]:
        """Загрузка UTC-смещений городов (один SELECT)"""
        rows = await session.execute(select(City))
        return {c.name: c.utc_offset for c in rows.scalars().all()}

    async def _exclude_frozen(
        self,
        session: AsyncSession,
        segment_city_counts: Dict[str, Dict[str, int]],
        segment_total_counts: Dict[str, int]
    ) -> Tuple[Dict, Dict]:
        """Удаляет замороженные сегменты/города из словарей"""
        # Замороженные города
        frozen_cities_result = await session.execute(
            select(SegmentLock.segment, SegmentLock.city)
            .where(SegmentLock.is_frozen == True, SegmentLock.city.isnot(None))
        )
        for seg, city in frozen_cities_result.all():
            if seg in segment_city_counts and city in segment_city_counts[seg]:
                del segment_city_counts[seg][city]
                segment_total_counts[seg] = sum(segment_city_counts[seg].values())

        # Замороженные сегменты целиком
        frozen_segs_result = await session.execute(
            select(SegmentLock.segment)
            .where(SegmentLock.is_frozen == True, SegmentLock.city.is_(None))
        )
        for (frozen_seg,) in frozen_segs_result.all():
            segment_city_counts.pop(frozen_seg, None)
            segment_total_counts.pop(frozen_seg, None)

        return segment_city_counts, segment_total_counts
