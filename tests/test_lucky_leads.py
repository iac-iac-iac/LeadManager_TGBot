"""Тесты «Мне повезёт!»: парсер диапазона и CRUD по UTC-поясу."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.database.models import Base, LeadStatus, City
from src.database import crud
from src.utils.lucky_range import parse_lucky_leads_range


def test_parse_lucky_range_ok():
    assert parse_lucky_leads_range("10-40") == (10, 40)
    assert parse_lucky_leads_range("10 40") == (10, 40)
    assert parse_lucky_leads_range("200 200") == (200, 200)
    assert parse_lucky_leads_range("15—30") == (15, 30)


def test_parse_lucky_range_fail():
    assert parse_lucky_leads_range("9-20") is None
    assert parse_lucky_leads_range("10-201") is None
    assert parse_lucky_leads_range("20-10") is None
    assert parse_lucky_leads_range("abc") is None
    assert parse_lucky_leads_range("10") is None
    assert parse_lucky_leads_range("5-5") is None


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
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest.mark.asyncio
async def test_count_leads_by_utc_band(session: AsyncSession):
    session.add(City(name="MSK", utc_offset=0))
    session.add(City(name="Vladivostok", utc_offset=7))
    await session.flush()

    await crud.create_lead(
        session, company_name="a", segment="Seg", city="MSK", status=LeadStatus.UNIQUE
    )
    await crud.create_lead(
        session, company_name="b", segment="Seg", city="Vladivostok", status=LeadStatus.UNIQUE
    )
    await crud.create_lead(
        session, company_name="c", segment="Seg", city=None, status=LeadStatus.UNIQUE
    )

    reg = await crud.count_leads_by_utc_band(session, "regular", threshold=3)
    pls = await crud.count_leads_by_utc_band(session, "plusoviki", threshold=3)
    assert reg == 2
    assert pls == 1


@pytest.mark.asyncio
async def test_get_random_leads_by_utc_band_filter_and_limit(session: AsyncSession):
    session.add(City(name="A", utc_offset=1))
    session.add(City(name="B", utc_offset=5))
    await session.flush()

    for i in range(5):
        await crud.create_lead(
            session, company_name=f"r{i}", segment="S", city="A", status=LeadStatus.UNIQUE
        )
    for i in range(3):
        await crud.create_lead(
            session, company_name=f"p{i}", segment="S", city="B", status=LeadStatus.UNIQUE
        )

    batch = await crud.get_random_leads_by_utc_band(session, "regular", limit=3, threshold=3)
    assert len(batch) == 3
    for lead in batch:
        assert lead.city == "A"

    batch_p = await crud.get_random_leads_by_utc_band(session, "plusoviki", limit=10, threshold=3)
    assert len(batch_p) == 3
    for lead in batch_p:
        assert lead.city == "B"


@pytest.mark.asyncio
async def test_get_random_leads_by_utc_band_zero_limit(session: AsyncSession):
    assert await crud.get_random_leads_by_utc_band(session, "regular", 0) == []
