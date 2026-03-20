"""
Утилиты для работы с датой и временем

Единый модуль для timezone-aware datetime операций
"""
from datetime import datetime, timezone, timedelta
from typing import Optional


def now_utc() -> datetime:
    """
    Получение текущего времени в UTC

    Returns:
        Текущее время UTC с timezone info

    Examples:
        >>> now = now_utc()
        >>> now.tzinfo
        datetime.timezone.utc
    """
    return datetime.now(timezone.utc)


def now_utc_timestamp() -> float:
    """
    Получение текущего времени UTC как timestamp

    Returns:
        Timestamp в секундах

    Examples:
        >>> ts = now_utc_timestamp()
        >>> isinstance(ts, float)
        True
    """
    return datetime.now(timezone.utc).timestamp()


def utc_from_timestamp(timestamp: float) -> datetime:
    """
    Конвертация timestamp в UTC datetime

    Args:
        timestamp: Unix timestamp

    Returns:
        UTC datetime
    """
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def ensure_timezone_aware(dt: datetime, default_tz: timezone = timezone.utc) -> datetime:
    """
    Проверка, что datetime имеет timezone info

    Args:
        dt: datetime для проверки
        default_tz: Timezone для добавления если отсутствует

    Returns:
        datetime с timezone info

    Raises:
        ValueError: Если datetime уже имеет timezone, но это не UTC
    """
    if dt.tzinfo is None:
        # Naive datetime - добавляем UTC
        return dt.replace(tzinfo=default_tz)
    elif dt.tzinfo != timezone.utc:
        # Другая timezone - конвертируем в UTC
        return dt.astimezone(timezone.utc)
    else:
        # Уже UTC
        return dt


def to_utc(dt: datetime) -> datetime:
    """
    Конвертация datetime в UTC

    Args:
        dt: datetime (с timezone или без)

    Returns:
        datetime в UTC

    Raises:
        ValueError: Если datetime имеет timezone, но не может быть конвертирован
    """
    if dt.tzinfo is None:
        # Считаем что это UTC
        return dt.replace(tzinfo=timezone.utc)
    else:
        # Конвертируем в UTC
        return dt.astimezone(timezone.utc)


def format_datetime(dt: datetime, format_str: str = "%d.%m.%Y %H:%M:%S") -> str:
    """
    Форматирование datetime в строку

    Args:
        dt: datetime для форматирования
        format_str: Формат строки (по умолчанию "%d.%m.%Y %H:%M:%S")

    Returns:
        Отформатированная строка
    """
    # Конвертируем в UTC если нужно
    dt_utc = to_utc(dt)
    return dt_utc.strftime(format_str)


def parse_datetime(date_str: str, format_str: str = "%d.%m.%Y %H:%M:%S") -> datetime:
    """
    Парсинг строки в datetime

    Args:
        date_str: Строка с датой
        format_str: Формат строки

    Returns:
        datetime в UTC
    """
    dt = datetime.strptime(date_str, format_str)
    return dt.replace(tzinfo=timezone.utc)


def get_start_of_day(dt: Optional[datetime] = None) -> datetime:
    """
    Получение начала дня (00:00:00)

    Args:
        dt: datetime (по умолчанию сейчас)

    Returns:
        Начало дня в UTC
    """
    if dt is None:
        dt = now_utc()

    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def get_end_of_day(dt: Optional[datetime] = None) -> datetime:
    """
    Получение конца дня (23:59:59.999999)

    Args:
        dt: datetime (по умолчанию сейчас)

    Returns:
        Конец дня в UTC
    """
    if dt is None:
        dt = now_utc()

    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def get_start_of_week(dt: Optional[datetime] = None) -> datetime:
    """
    Получение начала недели (понедельник 00:00:00)

    Args:
        dt: datetime (по умолчанию сейчас)

    Returns:
        Начало недели в UTC
    """
    if dt is None:
        dt = now_utc()

    # Понедельник = 0, Воскресенье = 6
    days_since_monday = dt.weekday()
    start_of_week = dt - timedelta(days=days_since_monday)

    return start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)


def get_start_of_month(dt: Optional[datetime] = None) -> datetime:
    """
    Получение начала месяца (1 число 00:00:00)

    Args:
        dt: datetime (по умолчанию сейчас)

    Returns:
        Начало месяца в UTC
    """
    if dt is None:
        dt = now_utc()

    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def get_end_of_month(dt: Optional[datetime] = None) -> datetime:
    """
    Получение конца месяца

    Args:
        dt: datetime (по умолчанию сейчас)

    Returns:
        Конец месяца в UTC
    """
    if dt is None:
        dt = now_utc()

    # Первый день следующего месяца
    if dt.month == 12:
        next_month = dt.replace(year=dt.year + 1, month=1, day=1)
    else:
        next_month = dt.replace(month=dt.month + 1, day=1)

    # Конец текущего месяца = начало следующего - 1 микросекунда
    return next_month - timedelta(microseconds=1)


def get_period_start_end(period: str, reference_dt: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """
    Получение начала и конца периода

    Args:
        period: Период ("today", "yesterday", "week", "last_week", "month", "last_month")
        reference_dt: datetime для отсчёта (по умолчанию сейчас)

    Returns:
        (начало периода, конец периода)

    Examples:
        >>> get_period_start_end("today")
        (datetime(2024, 1, 1, 0, 0, tzinfo=utc), datetime(2024, 1, 1, 23, 59, 59, 999999, tzinfo=utc))
        >>> get_period_start_end("week")
        (начало текущей недели, конец текущей недели)
    """
    if reference_dt is None:
        reference_dt = now_utc()

    if period == "today":
        return get_start_of_day(reference_dt), get_end_of_day(reference_dt)

    elif period == "yesterday":
        yesterday = reference_dt - timedelta(days=1)
        return get_start_of_day(yesterday), get_end_of_day(yesterday)

    elif period == "week":
        start = get_start_of_week(reference_dt)
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
        return start, end

    elif period == "last_week":
        last_week_start = get_start_of_week(reference_dt) - timedelta(days=7)
        last_week_end = last_week_start + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
        return last_week_start, last_week_end

    elif period == "month":
        return get_start_of_month(reference_dt), get_end_of_month(reference_dt)

    elif period == "last_month":
        # Первый день текущего месяца
        first_day_current = get_start_of_month(reference_dt)
        # Последний день предыдущего месяца
        last_day_prev = first_day_current - timedelta(microseconds=1)
        # Первый день предыдущего месяца
        first_day_prev = get_start_of_month(last_day_prev)
        return first_day_prev, last_day_prev

    else:
        raise ValueError(f"Неизвестный период: {period}")


def is_older_than(dt: datetime, days: int) -> bool:
    """
    Проверка, что дата старше N дней

    Args:
        dt: datetime для проверки
        days: Количество дней

    Returns:
        True если дата старше N дней
    """
    cutoff = now_utc() - timedelta(days=days)
    return to_utc(dt) < cutoff


def is_within_period(dt: datetime, start: datetime, end: datetime) -> bool:
    """
    Проверка, что дата в пределах периода

    Args:
        dt: datetime для проверки
        start: Начало периода
        end: Конец периода

    Returns:
        True если дата в пределах периода
    """
    dt_utc = to_utc(dt)
    start_utc = to_utc(start)
    end_utc = to_utc(end)

    return start_utc <= dt_utc <= end_utc


def calculate_age(birth_date: datetime) -> int:
    """
    Расчёт возраста в годах

    Args:
        birth_date: Дата рождения

    Returns:
        Возраст в годах
    """
    today = now_utc()
    birth_utc = to_utc(birth_date)

    age = today.year - birth_utc.year

    # Если день рождения ещё не был в этом году
    if (today.month, today.day) < (birth_utc.month, birth_utc.day):
        age -= 1

    return age
