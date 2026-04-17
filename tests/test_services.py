"""
Тесты для сервисов:
- OtherCategoryService (classify, count_by_type)
- LeadAssignmentService (assign)

Использует in-memory SQLite + реальные модели.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.database.models import Base, Lead, LeadStatus, City, User, UserRole, UserStatus
from src.bot.services.other_category_service import OtherCategoryService, SegmentClassification


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def engine():
    return create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)


@pytest.fixture
async def tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def session(engine, tables):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess


async def _create_lead(session, segment, city=None, status=LeadStatus.UNIQUE):
    lead = Lead(
        phone=f"+7000{id(segment)}{id(city)}",
        segment=segment,
        city=city,
        status=status,
        created_at=datetime.now(timezone.utc)
    )
    session.add(lead)
    await session.flush()
    return lead


async def _create_city(session, name, utc_offset=0):
    city = City(name=name, utc_offset=utc_offset)
    session.add(city)
    await session.flush()
    return city


# =============================================================================
# OtherCategoryService.classify()
# =============================================================================

class TestOtherCategoryServiceClassify:
    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_classification(self, session):
        svc = OtherCategoryService(tail_threshold=10)
        result = await svc.classify(session, exclude_frozen=False)

        assert isinstance(result, SegmentClassification)
        assert result.regular_count == 0
        assert result.plusoviki_count == 0
        assert result.regular_targets == []
        assert result.plusoviki_targets == []

    @pytest.mark.asyncio
    async def test_small_segment_goes_to_regular(self, session):
        """Сегмент с < tail_threshold лидов → regular (city UTC < threshold)"""
        await _create_city(session, "Москва", utc_offset=0)
        for _ in range(5):
            await _create_lead(session, "МалыйСегмент", "Москва")

        svc = OtherCategoryService(tail_threshold=10, plusoviki_threshold=3)
        result = await svc.classify(session, exclude_frozen=False)

        assert result.regular_count == 5
        assert result.plusoviki_count == 0
        assert ("МалыйСегмент", "Москва") in result.regular_targets

    @pytest.mark.asyncio
    async def test_small_segment_goes_to_plusoviki(self, session):
        """Сегмент с < tail_threshold лидов + high UTC → plusoviki"""
        await _create_city(session, "Владивосток", utc_offset=7)
        for _ in range(3):
            await _create_lead(session, "МалыйСегмент", "Владивосток")

        svc = OtherCategoryService(tail_threshold=10, plusoviki_threshold=3)
        result = await svc.classify(session, exclude_frozen=False)

        assert result.plusoviki_count == 3
        assert result.regular_count == 0
        assert ("МалыйСегмент", "Владивосток") in result.plusoviki_targets

    @pytest.mark.asyncio
    async def test_large_segment_not_in_other(self, session):
        """Сегмент с >= tail_threshold лидов во всех городах — не попадает в «Прочее»"""
        await _create_city(session, "Москва", utc_offset=0)
        for _ in range(15):
            await _create_lead(session, "БольшойСегмент", "Москва")

        svc = OtherCategoryService(tail_threshold=10)
        result = await svc.classify(session, exclude_frozen=False)

        assert result.regular_count == 0
        assert result.plusoviki_count == 0

    @pytest.mark.asyncio
    async def test_large_segment_with_tail_city(self, session):
        """Большой сегмент, но один город-«хвост» → только этот город в regular"""
        await _create_city(session, "Москва", utc_offset=0)
        await _create_city(session, "МалыйГород", utc_offset=1)

        for _ in range(20):
            await _create_lead(session, "СегМентА", "Москва")
        for _ in range(3):
            await _create_lead(session, "СегМентА", "МалыйГород")

        svc = OtherCategoryService(tail_threshold=10)
        result = await svc.classify(session, exclude_frozen=False)

        assert result.regular_count == 3
        assert ("СегМентА", "МалыйГород") in result.regular_targets
        # Москва не попала
        assert ("СегМентА", "Москва") not in result.regular_targets

    @pytest.mark.asyncio
    async def test_only_unique_status_counted(self, session):
        """Только UNIQUE лиды участвуют в классификации"""
        await _create_city(session, "Казань", utc_offset=0)
        await _create_lead(session, "Сег1", "Казань", status=LeadStatus.UNIQUE)
        await _create_lead(session, "Сег1", "Казань", status=LeadStatus.ASSIGNED)
        await _create_lead(session, "Сег1", "Казань", status=LeadStatus.DUPLICATE)

        svc = OtherCategoryService(tail_threshold=10)
        result = await svc.classify(session, exclude_frozen=False)

        # Только 1 UNIQUE → меньше порога → входит в regular
        assert result.regular_count == 1


# =============================================================================
# OtherCategoryService.count_by_type()
# =============================================================================

class TestOtherCategoryServiceCountByType:
    @pytest.mark.asyncio
    async def test_count_regular(self, session):
        await _create_city(session, "Москва", utc_offset=0)
        for _ in range(5):
            await _create_lead(session, "Маленький", "Москва")

        svc = OtherCategoryService(tail_threshold=10)
        count = await svc.count_by_type(session, "regular", exclude_frozen=False)
        assert count == 5

    @pytest.mark.asyncio
    async def test_count_plusoviki(self, session):
        await _create_city(session, "Хабаровск", utc_offset=7)
        for _ in range(4):
            await _create_lead(session, "ВосточныйСег", "Хабаровск")

        svc = OtherCategoryService(tail_threshold=10, plusoviki_threshold=3)
        count = await svc.count_by_type(session, "plusoviki", exclude_frozen=False)
        assert count == 4

    @pytest.mark.asyncio
    async def test_count_unknown_type_returns_zero(self, session):
        svc = OtherCategoryService(tail_threshold=10)
        count = await svc.count_by_type(session, "nonexistent", exclude_frozen=False)
        assert count == 0

    @pytest.mark.asyncio
    async def test_count_empty_db_zero(self, session):
        svc = OtherCategoryService()
        assert await svc.count_by_type(session, "regular", exclude_frozen=False) == 0
        assert await svc.count_by_type(session, "plusoviki", exclude_frozen=False) == 0
