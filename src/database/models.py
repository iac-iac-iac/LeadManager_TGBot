"""
SQLAlchemy модели для базы данных

Версия: 2.0 (с FK constraints и составными индексами)
"""
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional, List

from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, DateTime,
    ForeignKey, Text, JSON, Enum, UniqueConstraint, Index, CheckConstraint, text
)
from sqlalchemy.orm import relationship, declarative_base, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

Base = declarative_base()


class LeadStatus(str, PyEnum):
    """Статусы лидов"""
    NEW = "NEW"
    UNIQUE = "UNIQUE"
    DUPLICATE = "DUPLICATE"
    ASSIGNED = "ASSIGNED"
    IMPORTED = "IMPORTED"
    ERROR_IMPORT = "ERROR_IMPORT"
    PENDING_UTC = "PENDING_UTC"  # Ожидает ввода UTC для города


class UserRole(str, PyEnum):
    """Роли пользователей"""
    MANAGER = "manager"
    ADMIN = "admin"


class UserStatus(str, PyEnum):
    """Статусы пользователей"""
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"


# =============================================================================
# Таблица городов
# =============================================================================

class City(Base):
    """
    Модель города с UTC offset от Москвы

    Таблица для хранения городов и их часовых поясов
    """
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    utc_offset = Column(Integer, nullable=False)  # Часы от Москвы (например, +2, -1)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f"<City(name='{self.name}', utc_offset={self.utc_offset:+d})>"


class PendingCity(Base):
    """
    Модель ожидающего города (нужен ввод UTC от админа)

    Создаётся при импорте CSV, если город не найден в таблице cities
    """
    __tablename__ = "pending_cities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    admin_telegram_id = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f"<PendingCity(name='{self.name}', admin='{self.admin_telegram_id}')>"


class Lead(Base):
    """
    Модель лида

    Таблица для хранения импортированных лидов из CSV

    Attributes:
        id: Первичный ключ
        phone: Телефон компании (нормализованный)
        company_name: Название компании
        address: Адрес компании
        city: Город
        segment: Сегмент/направление
        source: Источник лида
        status: Статус лида (NEW, UNIQUE, DUPLICATE, ASSIGNED, IMPORTED, ERROR_IMPORT)
        manager_telegram_id: Telegram ID менеджера (внешний ключ на users.telegram_id)
        bitrix24_lead_id: ID лида в Bitrix24
        service_type: Тип услуги (ГЦК)
        stage: Стадия (Новая Заявка)
        phone_source: Источник телефона (для аналитики)
        created_at: Дата создания (UTC)
        duplicate_checked_at: Дата проверки на дубли (UTC)
        assigned_at: Дата выдачи менеджеру (UTC)
        imported_at: Дата импорта в Bitrix24 (UTC)
    """
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Данные из CSV (оптимизированные размеры полей)
    phone = Column(String(20), nullable=True)  # +7XXXXXXXXXXX максимум 12 символов
    company_name = Column(String(500), nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(200), nullable=True)
    segment = Column(String(200), nullable=False)
    source = Column(String(200), default="Холодный звонок", nullable=False)

    # Дополнительные поля из CSV
    mobile_phone = Column(String(20), nullable=True)
    work_email = Column(String(320), nullable=True)  # Максимальная длина email
    website = Column(String(500), nullable=True)
    contact_telegram = Column(String(100), nullable=True)  # Telegram username
    comment = Column(Text, nullable=True)
    
    # Новые поля для аналитики и интеграции
    service_type = Column(String(100), default="ГЦК", nullable=True)  # Тип услуги
    stage = Column(String(100), default="Новая Заявка", nullable=True)  # Стадия
    phone_source = Column(String(200), nullable=True)  # Источник телефона

    # Статусы и метаданные
    status = Column(
        Enum(LeadStatus),
        default=LeadStatus.NEW,
        nullable=False,
        index=True
    )

    # Связи (с FK constraint)
    manager_telegram_id = Column(
        String(50),
        ForeignKey('users.telegram_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    
    # Bitrix24 ID (с индексом для быстрого поиска)
    bitrix24_lead_id = Column(BigInteger, nullable=True, index=True)

    # Временные метки (timezone-aware)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    duplicate_checked_at = Column(DateTime(timezone=True), nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    imported_at = Column(DateTime(timezone=True), nullable=True)

    # Составные индексы для производительности и уникальности
    __table_args__ = (
        # Индекс для быстрого поиска доступных лидов
        Index('idx_leads_status_segment_city', 'status', 'segment', 'city'),
        # Индекс для поиска по статусу и дате
        Index('idx_leads_status_created_at', 'status', 'created_at'),
        # Индекс для статистики менеджера
        Index('idx_leads_manager_assigned_at', 'manager_telegram_id', 'assigned_at'),
        # Частичный индекс для уникальных лидов
        Index(
            'idx_leads_unique_available',
            'status', 'segment', 'city', 'created_at',
            postgresql_where=text("status = 'UNIQUE'")
        ),
        # Уникальные ограничения для предотвращения дублей (для SQLite)
        # Дублируются в миграции v3 для совместимости
    )

    def __repr__(self) -> str:
        return f"<Lead(id={self.id}, company='{self.company_name}', status={self.status})>"


class User(Base):
    """
    Модель пользователя

    Таблица для хранения пользователей Telegram (менеджеры и админы)
    
    Attributes:
        id: Первичный ключ
        telegram_id: Telegram ID (уникальный)
        full_name: ФИО пользователя
        username: Username в Telegram
        role: Роль (manager, admin)
        status: Статус (PENDING_APPROVAL, ACTIVE, REJECTED)
        bitrix24_user_id: ID пользователя в Bitrix24
        registered_at: Дата регистрации (UTC)
        approved_at: Дата подтверждения админом (UTC)
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Telegram данные
    telegram_id = Column(String(50), unique=True, nullable=False, index=True)
    full_name = Column(String(200), nullable=True)
    username = Column(String(100), nullable=True)

    # Роль и статус
    role = Column(Enum(UserRole), default=UserRole.MANAGER, nullable=False)
    status = Column(Enum(UserStatus), default=UserStatus.PENDING_APPROVAL, nullable=False)

    # Bitrix24 привязка (используем BigInteger для совместимости)
    bitrix24_user_id = Column(BigInteger, nullable=True)

    # Временные метки (timezone-aware)
    registered_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id='{self.telegram_id}', role={self.role})>"


class SegmentLock(Base):
    """
    Модель заморозки сегментов

    Таблица для управления заморозкой сегментов/городов
    
    Attributes:
        id: Первичный ключ
        segment: Сегмент/направление
        city: Город (NULL = заморозка всего сегмента)
        is_frozen: Флаг заморозки
        frozen_at: Дата установки заморозки (UTC)
        unfrozen_at: Дата снятия заморозки (UTC)
        admin_comment: Комментарий админа
    """
    __tablename__ = "segment_locks"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Сегмент и город
    segment = Column(String(200), nullable=False)
    city = Column(String(200), nullable=True)  # NULL = заморозка всего сегмента

    # Статус заморозки
    is_frozen = Column(Boolean, default=False, nullable=False)

    # Временные метки (timezone-aware)
    frozen_at = Column(DateTime(timezone=True), nullable=True)
    unfrozen_at = Column(DateTime(timezone=True), nullable=True)

    # Комментарий админа
    admin_comment = Column(Text, nullable=True)

    # Индексы и ограничения
    __table_args__ = (
        UniqueConstraint('segment', 'city', name='uq_segment_city'),
        Index('idx_segment_lock_frozen', 'segment', 'city', 'is_frozen'),
    )

    def __repr__(self) -> str:
        city_str = f" + {self.city}" if self.city else ""
        return f"<SegmentLock(segment='{self.segment}'{city_str}, frozen={self.is_frozen})>"


class Log(Base):
    """
    Модель логов

    Таблица для хранения событий системы
    
    Attributes:
        id: Первичный ключ
        event_type: Тип события
        user_telegram_id: Telegram ID пользователя
        related_lead_ids: JSON список ID лидов
        related_segment: Сегмент (если применимо)
        related_city: Город (если применимо)
        timestamp: Дата и время события (UTC)
        description: Текстовое описание
    """
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Тип события
    event_type = Column(String(100), nullable=False, index=True)

    # Пользователь
    user_telegram_id = Column(String(50), nullable=True, index=True)

    # Связанные данные
    related_lead_ids = Column(JSON, nullable=True)  # Список ID лидов
    related_segment = Column(String(200), nullable=True)
    related_city = Column(String(200), nullable=True)

    # Временная метка и описание (timezone-aware)
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )
    description = Column(Text, nullable=True)

    # Индексы для производительности
    __table_args__ = (
        Index('idx_logs_timestamp_type', 'timestamp', 'event_type'),
        Index('idx_logs_user_timestamp', 'user_telegram_id', 'timestamp'),
    )

    def __repr__(self) -> str:
        return f"<Log(id={self.id}, event_type='{self.event_type}', timestamp={self.timestamp})>"


class Segment(Base):
    """
    Модель сегмента

    Таблица для хранения списка сегментов с возможностью управления
    
    Attributes:
        id: Первичный ключ
        name: Название сегмента (уникальное)
        description: Описание сегмента
        is_active: Активен ли сегмент
        created_at: Дата создания (UTC)
    """
    __tablename__ = "segments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f"<Segment(id={self.id}, name='{self.name}', active={self.is_active})>"


class Ticket(Base):
    """
    Модель тикета обратной связи

    Таблица для хранения обращений менеджеров к администраторам

    Attributes:
        id: Первичный ключ
        manager_telegram_id: Telegram ID менеджера (автора тикета)
        message: Текст сообщения/обращения
        status: Статус тикета (new, in_progress, resolved, closed)
        created_at: Дата создания (UTC)
        admin_response: Ответ администратора
        responded_at: Дата ответа (UTC)
        resolved_at: Дата закрытия/решения (UTC)
        admin_telegram_id: Telegram ID администратора, обработавшего тикет
    """
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manager_telegram_id = Column(String(50), nullable=False, index=True)
    message = Column(Text, nullable=False)
    status = Column(String(20), default="new", nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    admin_response = Column(Text, nullable=True)
    responded_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    admin_telegram_id = Column(String(50), nullable=True)

    def __repr__(self) -> str:
        return f"<Ticket(id={self.id}, manager='{self.manager_telegram_id}', status='{self.status}')>"


class BotStatus(Base):
    """
    Модель статуса бота

    Таблица для хранения текущего состояния бота (включён/выключен/техработы)

    Attributes:
        id: Первичный ключ (всегда 1, единственная запись)
        status: Статус бота (running, stopped, maintenance)
        reason: Причина остановки (для maintenance)
        updated_at: Дата последнего обновления (UTC)
    """
    __tablename__ = "bot_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(20), nullable=False, default="running", index=True)
    reason = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<BotStatus(id={self.id}, status='{self.status}')>"


class DatabaseManager:
    """
    Менеджер базы данных

    Управление подключением, сессиями и миграциями

    Attributes:
        database_url: URL подключения к БД
        engine: Асинхронный движок SQLAlchemy
        async_session_factory: Фабрика асинхронных сессий
    """

    def __init__(self, database_path: str):
        """
        Инициализация менеджера БД

        Args:
            database_path: Путь к файлу SQLite базы данных
        """
        from sqlalchemy import event

        self.database_url = f"sqlite+aiosqlite:///{database_path}"
        
        # Создаём движок с правильными настройками для SQLite
        self.engine = create_async_engine(
            self.database_url,
            echo=False,
            future=True,
            # Настройки пула для SQLite
            pool_pre_ping=True,  # Проверка соединения перед использованием
        )
        
        # ✅ Включаем Foreign Keys для SQLite
        @event.listens_for(self.engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")  # WAL mode для конкурентности
            cursor.execute("PRAGMA synchronous=NORMAL")  # Баланс между безопасностью и производительностью
            cursor.close()

        self.async_session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,  # Явное управление транзакциями
            autoflush=False  # Явный flush перед commit
        )

    async def create_tables(self) -> None:
        """Создание всех таблиц"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_tables(self) -> None:
        """Удаление всех таблиц (для тестов)"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    def get_session(self) -> Session:
        """Получение синхронной сессии (для простых операций)"""
        return Session(self.engine.sync_engine)

    async def get_async_session(self) -> AsyncSession:
        """Получение асинхронной сессии"""
        async with self.async_session_factory() as session:
            yield session

    async def execute(self, query):
        """Выполнение запроса"""
        async with self.engine.begin() as conn:
            result = await conn.execute(query)
            return result

    async def commit(self):
        """Коммит транзакции"""
        async with self.engine.begin() as conn:
            await conn.commit()
