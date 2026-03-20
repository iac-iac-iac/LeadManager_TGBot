"""
Тесты для базы данных и CRUD операций
"""
import pytest
import pytest_asyncio
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.database.models import Base, Lead, LeadStatus, User, UserRole, UserStatus, SegmentLock
from src.database import crud


@pytest.fixture
def engine():
    """Создание тестового SQLite in-memory"""
    return create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)


@pytest.fixture
async def tables(engine):
    """Создание таблиц"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def session(engine, tables):
    """Сессия БД для тестов"""
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


class TestLeadCRUD:
    """Тесты CRUD операций для лидов"""
    
    @pytest.mark.asyncio
    async def test_create_lead(self, session: AsyncSession):
        """Создание лида"""
        lead = await crud.create_lead(
            session,
            phone="+74951234567",
            company_name="Тест ООО",
            city="Москва",
            segment="Автосалон",
            status=LeadStatus.NEW
        )
        
        assert lead.id is not None
        assert lead.phone == "+74951234567"
        assert lead.status == LeadStatus.NEW
    
    @pytest.mark.asyncio
    async def test_get_lead_by_id(self, session: AsyncSession):
        """Получение лида по ID"""
        # Создаем лид
        lead = await crud.create_lead(
            session,
            company_name="Тест",
            segment="Тестовый сегмент",
            status=LeadStatus.NEW
        )

        # Получаем
        retrieved = await crud.get_lead_by_id(session, lead.id)

        assert retrieved is not None
        assert retrieved.id == lead.id

    @pytest.mark.asyncio
    async def test_update_lead_status(self, session: AsyncSession):
        """Обновление статуса лида"""
        lead = await crud.create_lead(
            session,
            company_name="Тест",
            segment="Тестовый сегмент",
            status=LeadStatus.NEW
        )
        
        # Обновляем статус
        await crud.update_lead_status(session, lead.id, LeadStatus.UNIQUE)
        await session.commit()
        
        # Проверяем
        updated = await crud.get_lead_by_id(session, lead.id)
        assert updated.status == LeadStatus.UNIQUE
    
    @pytest.mark.asyncio
    async def test_assign_leads_to_manager(self, session: AsyncSession):
        """Назначение лидов менеджеру"""
        lead1 = await crud.create_lead(
            session,
            company_name="Тест 1",
            segment="Тестовый сегмент",
            status=LeadStatus.UNIQUE
        )
        lead2 = await crud.create_lead(
            session,
            company_name="Тест 2",
            segment="Тестовый сегмент",
            status=LeadStatus.UNIQUE
        )

        # Назначаем
        count = await crud.assign_leads_to_manager(
            session,
            [lead1.id, lead2.id],
            manager_telegram_id="123456"
        )

        assert count == 2

        # Проверяем
        updated_lead = await crud.get_lead_by_id(session, lead1.id)
        assert updated_lead.status == LeadStatus.ASSIGNED
        assert updated_lead.manager_telegram_id == "123456"


class TestUserCRUD:
    """Тесты CRUD операций для пользователей"""
    
    @pytest.mark.asyncio
    async def test_create_user(self, session: AsyncSession):
        """Создание пользователя"""
        user = await crud.create_user(
            session,
            telegram_id="123456",
            full_name="Иванов Иван",
            role=UserRole.MANAGER,
            status=UserStatus.PENDING_APPROVAL
        )
        
        assert user.id is not None
        assert user.telegram_id == "123456"
        assert user.role == UserRole.MANAGER
    
    @pytest.mark.asyncio
    async def test_get_user_by_telegram_id(self, session: AsyncSession):
        """Получение пользователя по Telegram ID"""
        user = await crud.create_user(session, telegram_id="123456", full_name="Тест")
        
        retrieved = await crud.get_user_by_telegram_id(session, "123456")
        
        assert retrieved is not None
        assert retrieved.telegram_id == "123456"
    
    @pytest.mark.asyncio
    async def test_approve_user(self, session: AsyncSession):
        """Подтверждение пользователя"""
        user = await crud.create_user(
            session,
            telegram_id="123456",
            full_name="Тест",
            status=UserStatus.PENDING_APPROVAL
        )
        
        # Подтверждаем
        approved = await crud.approve_user(session, "123456", bitrix24_user_id=789)
        
        assert approved.status == UserStatus.ACTIVE
        assert approved.bitrix24_user_id == 789


class TestSegmentLockCRUD:
    """Тесты заморозки сегментов"""
    
    @pytest.mark.asyncio
    async def test_freeze_segment(self, session: AsyncSession):
        """Заморозка сегмента"""
        lock = await crud.freeze_segment(
            session,
            segment="Автосалон",
            admin_comment="Тест"
        )
        
        assert lock.is_frozen is True
        assert lock.segment == "Автосалон"
    
    @pytest.mark.asyncio
    async def test_unfreeze_segment(self, session: AsyncSession):
        """Разморозка сегмента"""
        # Замораживаем
        await crud.freeze_segment(session, segment="Автосалон")
        
        # Размораживаем
        lock = await crud.unfreeze_segment(session, segment="Автосалон")
        
        assert lock.is_frozen is False
    
    @pytest.mark.asyncio
    async def test_is_segment_frozen(self, session: AsyncSession):
        """Проверка заморозки"""
        # Замораживаем
        await crud.freeze_segment(session, segment="Автосалон")
        
        # Проверяем
        assert await crud.is_segment_frozen(session, "Автосалон") is True
        assert await crud.is_segment_frozen(session, "Другой") is False
