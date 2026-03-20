"""
Модуль импорта CSV файлов в базу данных

Поддерживает структуру CSV из проекта:
- Разделитель: точка с запятой (;)
- Кодировка: UTF-8
- Поля: Название лида, Название компании, телефоны, адрес, ответственный и т.д.
"""
import csv
import re
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import crud
from ..database.models import LeadStatus, User, Lead
from ..logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Извлечение данных из CSV
# =============================================================================

def extract_segment_from_lead_title(lead_title: str) -> str:
    """
    Извлечение сегмента из поля "Название лида"

    Формат: "{Сегмент} - {Название компании}"
    Пример: "Автосалон - Империя Авто" → "Автосалон"

    Args:
        lead_title: Значение поля "Название лида"

    Returns:
        Название сегмента
    """
    if not lead_title:
        return "Без сегмента"

    # Разделяем по " - "
    parts = lead_title.split(" - ", 1)
    if len(parts) >= 1:
        return parts[0].strip()

    return lead_title.strip()


def extract_segment_from_phone_source(phone_source: str, fallback_segment: Optional[str] = None) -> str:
    """
    Извлечение сегмента из поля "Источник телефона" (phone_source)

    Формат: "название сегмента!остальные данные"
    Пример: "быстровозводимые здания!СБП_КраснЯр_Казань__2026-03-18_14_17_02.json"

    Логика извлечения:
    1. Если есть "!" — взять часть до него (если не пусто)
    2. Если нет "!" — попробовать взять первое слово (по пробелу)
    3. Если пусто — вернуть "Без сегмента"
    4. Fallback: если phone_source пуст, использовать переданный fallback_segment

    Args:
        phone_source: Значение поля "Источник телефона"
        fallback_segment: Резервный сегмент (например, из lead_title)

    Returns:
        Название сегмента
    """
    # Если phone_source пуст, используем fallback
    if not phone_source or not phone_source.strip():
        return fallback_segment if fallback_segment else "Без сегмента"

    phone_source = phone_source.strip()

    # Логика 1: Есть "!" — берем часть до него
    if "!" in phone_source:
        segment = phone_source.split("!", 1)[0].strip()
        # Если часть до "!" не пустая, возвращаем её
        if segment:
            return segment
        # Если часть до "!" пустая (например, "!данные"), пробуем взять часть после "!"
        after_exclamation = phone_source.split("!", 1)[1].strip()
        if after_exclamation:
            # Берем первое слово из части после "!"
            if " " in after_exclamation:
                return after_exclamation.split(" ", 1)[0].strip()
            return after_exclamation
        # Иначе используем fallback
        return fallback_segment if fallback_segment else "Без сегмента"

    # Логика 2: Нет "!" — пробуем взять первое слово по пробелу
    if " " in phone_source:
        segment = phone_source.split(" ", 1)[0].strip()
        if segment:
            return segment

    # Логика 3: Возвращаем всё значение
    segment = phone_source.strip()
    if segment:
        return segment

    # Логика 4: Fallback
    return fallback_segment if fallback_segment else "Без сегмента"


def extract_city_from_address(address: str) -> Optional[str]:
    """
    Извлечение города из адреса
    
    Логика:
    1. Разбить адрес по запятым
    2. Проверить первый элемент:
       - Если содержит "область", "край", "республика" → город во втором элементе
       - Если содержит "Москва", "Санкт-Петербург" → это и есть город
       - Иначе → первый элемент = город
    3. Очистить от мусора
    
    Args:
        address: Полный адрес
        
    Returns:
        Название города или None
    """
    if not address:
        return None
    
    # Разбиваем по запятым
    parts = [p.strip() for p in address.split(",")]
    
    if not parts:
        return None
    
    # Города федерального значения
    federal_cities = ["москва", "санкт-петербург", "севастополь"]
    
    # Ключевые слова для регионов
    region_keywords = ["область", "край", "республика", "автономная", "автономный", "округ"]
    
    first_part = parts[0].lower()
    
    # Проверяем первый элемент
    if any(keyword in first_part for keyword in region_keywords):
        # Регион указан первым, город должен быть вторым
        if len(parts) > 1:
            return clean_city_name(parts[1])
    elif any(city in first_part for city in federal_cities):
        # Город федерального значения
        return clean_city_name(parts[0])
    else:
        # Первый элемент - город
        return clean_city_name(parts[0])
    
    return None


def clean_city_name(city: str) -> str:
    """
    Очистка названия города от мусора
    
    Args:
        city: Название города
        
    Returns:
        Очищенное название
    """
    # Убираем "г.", "город"
    city = re.sub(r"^\s*(г\.|город)\.?\s*", "", city, flags=re.IGNORECASE)
    
    # Убираем лишние пробелы
    city = city.strip()
    
    # Убираем кавычки
    city = city.strip('"\'')
    
    return city


def normalize_phone(phone: str) -> Optional[str]:
    """
    Нормализация телефона
    
    Args:
        phone: Телефон в любом формате
        
    Returns:
        Нормализованный телефон или None
    """
    if not phone:
        return None
    
    # Удаляем все нецифровые символы кроме +
    phone = re.sub(r"[^\d+]", "", phone)
    
    # Если начинается с 8, заменяем на +7
    if phone.startswith("8") and len(phone) == 11:
        phone = "+7" + phone[1:]
    elif phone.startswith("7") and len(phone) == 11:
        phone = "+7" + phone[1:]
    elif phone.startswith("+7") and len(phone) == 12:
        pass  # Уже правильный формат
    elif phone.isdigit() and len(phone) == 10:
        phone = "+7" + phone
    
    return phone if phone else None


async def find_manager_by_name(
    full_name: str,
    session: AsyncSession
) -> Optional[str]:
    """
    Поиск менеджера по ФИО из CSV

    Args:
        full_name: ФИО из поля "Ответственный"
        session: Сессия БД

    Returns:
        Telegram ID менеджера или None
    """
    if not full_name:
        return None

    # Ищем пользователя с таким full_name (асинхронно)
    from sqlalchemy import select

    result = await session.execute(
        select(User).where(
            User.full_name.ilike(f"%{full_name}%")
        )
    )
    user = result.scalar_one_or_none()

    return user.telegram_id if user else None


# =============================================================================
# Парсинг CSV
# =============================================================================

class CSVImporter:
    """
    Импорт CSV файлов в базу данных
    """
    
    # Маппинг полей CSV → поля БД
    CSV_FIELD_MAPPING = {
        "Название лида": "lead_title",
        "Название компании": "company_name",
        "Рабочий телефон": "work_phone",
        "Мобильный телефон": "mobile_phone",
        "Адрес": "address",
        "Населенный пункт": "locality",
        "Рабочий e-mail": "work_email",
        "Корпоративный сайт": "website",
        "Контакт Telegram": "contact_telegram",
        "Комментарий": "comment",
        "Ответственный": "manager_name",
        "Источник": "source",
        "Стадия": "stage",
    }
    
    def __init__(
        self,
        delimiter: str = ";",
        encoding: str = "utf-8"
    ):
        """
        Инициализация импортера

        Args:
            delimiter: Разделитель CSV
            encoding: Кодировка файла
        """
        self.delimiter = delimiter
        self.encoding = encoding

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Вычисление MD5 хеша файла для проверки на повторную загрузку"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    async def _check_sqlite_duplicate(
        self,
        session: AsyncSession,
        phone: Optional[str],
        mobile_phone: Optional[str],
        company_name: Optional[str]
    ) -> bool:
        """
        Проверка дубля в SQLite перед загрузкой
        
        Args:
            session: Сессия БД
            phone: Рабочий телефон
            mobile_phone: Мобильный телефон
            company_name: Название компании
            
        Returns:
            True если дубль найден
        """
        # Проверка по рабочему телефону + компания
        if phone:
            query = select(Lead.id).where(
                Lead.phone == phone,
                Lead.company_name == company_name
            ).limit(1)
            result = await session.execute(query)
            if result.scalar():
                return True
        
        # Проверка по мобильному телефону + компания
        if mobile_phone:
            query = select(Lead.id).where(
                Lead.mobile_phone == mobile_phone,
                Lead.company_name == company_name
            ).limit(1)
            result = await session.execute(query)
            if result.scalar():
                return True
        
        return False
    
    def parse_csv_file(self, file_path: Path) -> Tuple[List[Dict[str, Any]], int]:
        """
        Парсинг CSV файла
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            (список записей, количество строк)
        """
        records = []
        
        with open(file_path, "r", encoding=self.encoding) as f:
            reader = csv.DictReader(f, delimiter=self.delimiter)
            
            for row in reader:
                record = self._parse_row(row)
                if record:
                    records.append(record)
        
        logger.info(f"Спаршено {len(records)} записей из файла {file_path}")
        return records, len(records)
    
    def _parse_row(self, row: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Парсинг одной строки CSV

        Args:
            row: Строка CSV

        Returns:
            Словарь с данными для БД
        """
        # Извлекаем сырые поля из CSV
        raw_fields = self._extract_raw_fields(row)
        
        # Извлекаем сегмент
        segment = self._extract_segment(
            phone_source=raw_fields["phone_source"],
            lead_title=raw_fields["lead_title"]
        )
        
        # Извлекаем город
        city = self._extract_city(
            address=raw_fields["address"],
            locality=raw_fields["locality"]
        )
        
        # Нормализуем телефоны
        work_phone = normalize_phone(raw_fields["work_phone"])
        mobile_phone = normalize_phone(raw_fields["mobile_phone"])
        phone = work_phone or mobile_phone
        
        # Очищаем Telegram username
        contact_telegram = self._clean_telegram_contact(raw_fields["contact_telegram"])
        
        # Формируем company_name с fallback на lead_title
        company_name = self._extract_company_name(
            raw_fields["company_name"],
            raw_fields["lead_title"]
        )
        
        return {
            "lead_title": raw_fields["lead_title"],
            "company_name": company_name,
            "phone": phone,
            "mobile_phone": mobile_phone,
            "address": raw_fields["address"],
            "city": city,
            "segment": segment,
            "source": raw_fields["source"],
            "work_email": raw_fields["work_email"],
            "website": raw_fields["website"],
            "contact_telegram": contact_telegram,
            "comment": raw_fields["comment"],
            "manager_name": raw_fields["manager_name"],
            "service_type": raw_fields["service_type"],
            "stage": raw_fields["stage"],
            "phone_source": raw_fields["phone_source"],
        }

    def _extract_raw_fields(self, row: Dict[str, str]) -> Dict[str, str]:
        """
        Извлечение сырых полей из строки CSV

        Args:
            row: Строка CSV

        Returns:
            Словарь с извлечёнными полями
        """
        return {
            "lead_title": row.get("Название лида", "").strip(),
            "company_name": row.get("Название компании", "").strip(),
            "work_phone": row.get("Рабочий телефон", "").strip(),
            "mobile_phone": row.get("Мобильный телефон", "").strip(),
            "address": row.get("Адрес", "").strip(),
            "locality": row.get("Населенный пункт", "").strip(),
            "work_email": row.get("Рабочий e-mail", "").strip(),
            "website": row.get("Корпоративный сайт", "").strip(),
            "contact_telegram": row.get("Контакт Telegram", "").strip(),
            "comment": row.get("Комментарий", "").strip(),
            "manager_name": row.get("Ответственный", "").strip(),
            "source": row.get("Источник", "").strip() or "Холодный звонок",
            "service_type": row.get("Тип услуги", "").strip() or "ГЦК",
            "stage": row.get("Стадия", "").strip() or "Новая Заявка",
            "phone_source": row.get("Источник телефона", "").strip(),
        }

    def _extract_segment(self, phone_source: str, lead_title: str) -> str:
        """
        Извлечение сегмента из phone_source с fallback на lead_title

        Args:
            phone_source: Источник телефона
            lead_title: Название лида

        Returns:
            Название сегмента
        """
        segment_from_phone = extract_segment_from_phone_source(phone_source)
        
        if segment_from_phone == "Без сегмента":
            return extract_segment_from_lead_title(lead_title)
        
        return segment_from_phone

    def _extract_city(self, address: str, locality: str) -> Optional[str]:
        """
        Извлечение города из адреса или населённого пункта

        Args:
            address: Полный адрес
            locality: Населённый пункт

        Returns:
            Название города или None
        """
        city = extract_city_from_address(address)
        
        if not city and locality:
            return clean_city_name(locality)
        
        return city

    def _clean_telegram_contact(self, contact_telegram: str) -> str:
        """
        Очистка Telegram username от "@"

        Args:
            contact_telegram: Исходный username

        Returns:
            Очищенный username
        """
        if contact_telegram:
            return contact_telegram.lstrip('@')
        return contact_telegram

    def _extract_company_name(self, company_name: Optional[str], lead_title: str) -> Optional[str]:
        """
        Извлечение названия компании с fallback на lead_title

        Args:
            company_name: Название компании из CSV
            lead_title: Название лида

        Returns:
            Название компании
        """
        if company_name:
            return company_name
        
        # Fallback: извлекаем из lead_title (формат "Сегмент - Компания")
        if " - " in lead_title:
            return lead_title.split(" - ")[-1].strip()
        
        return None
    
    async def import_to_database(
        self,
        session: AsyncSession,
        file_path: Path
    ) -> Dict[str, int]:
        """
        Импорт CSV файла в базу данных

        Args:
            session: Сессия БД
            file_path: Путь к файлу

        Returns:
            Статистика импорта: {"imported": N, "errors": N, "sqlite_duplicates": N}
        """
        stats = {"imported": 0, "errors": 0, "sqlite_duplicates": 0}

        try:
            # Проверяем, не загружался ли этот файл ранее (по хешу)
            file_hash = self._calculate_file_hash(file_path)
            
            # Проверяем логи на наличие импорта этого файла
            existing_logs = await crud.get_logs_by_description(
                session,
                description_contains=f"хеш файла: {file_hash}"
            )
            if existing_logs:
                logger.warning(f"Файл {file_path} уже импортировался ранее (хеш: {file_hash})")
                return {"imported": 0, "errors": 0, "sqlite_duplicates": 0, "already_imported": True}

            # Парсим файл
            records, total_rows = self.parse_csv_file(file_path)

            if not records:
                logger.warning(f"Файл {file_path} не содержит записей для импорта")
                return {"imported": 0, "errors": 0, "sqlite_duplicates": 0}
            
            # Создаем лиды в БД с проверкой на дубли
            leads_data = []
            duplicate_count = 0
            
            for record in records:
                # Проверка на дубль в SQLite
                is_duplicate = await self._check_sqlite_duplicate(
                    session,
                    record["phone"],
                    record["mobile_phone"],
                    record["company_name"]
                )
                
                if is_duplicate:
                    duplicate_count += 1
                    logger.debug(f"Пропущен дубль: {record['company_name']} ({record['phone'] or record['mobile_phone']})")
                    continue
                
                lead_data = {
                    "company_name": record["company_name"],
                    "phone": record["phone"],
                    "mobile_phone": record["mobile_phone"],
                    "address": record["address"],
                    "city": record["city"],
                    "segment": record["segment"],
                    "source": record["source"],
                    "work_email": record["work_email"],
                    "website": record["website"],
                    "contact_telegram": record["contact_telegram"],
                    "comment": record["comment"],
                    "service_type": record["service_type"],
                    "stage": record["stage"],
                    "phone_source": record["phone_source"],
                    "status": LeadStatus.NEW,
                }
                leads_data.append(lead_data)
            
            stats["sqlite_duplicates"] = duplicate_count

            # Массовое создание с обработкой дублей
            if leads_data:
                imported_count = 0
                failed_count = 0
                
                for idx, lead_data in enumerate(leads_data):
                    try:
                        lead = Lead(**lead_data)
                        session.add(lead)
                        await session.flush()
                        imported_count += 1
                        
                        # Коммитим каждые 100 лидов для производительности
                        if (idx + 1) % 100 == 0:
                            await session.commit()
                            
                    except Exception as e:
                        if "UNIQUE constraint" in str(e):
                            # Дубль всё таки попал (гонка данных)
                            logger.debug(f"Пропущен дубль при вставке: {lead_data['company_name']}")
                            duplicate_count += 1
                            # Откатываем транзакцию и продолжаем
                            await session.rollback()
                        else:
                            logger.error(f"Ошибка при вставке лида: {e}")
                            failed_count += 1
                            await session.rollback()
                
                # Финальный коммит оставшихся лидов
                await session.commit()
                
                stats["imported"] = imported_count
                stats["sqlite_duplicates"] = duplicate_count
                stats["errors"] = failed_count

                logger.info(f"Импортировано {stats['imported']} лидов из файла {file_path}")

                # Создаем запись в логе с хешем файла
                lead_ids_result = await session.execute(
                    select(Lead.id).where(
                        Lead.status == LeadStatus.NEW,
                        Lead.created_at >= datetime.now(timezone.utc) - timedelta(seconds=60)
                    )
                )
                lead_ids = [row[0] for row in lead_ids_result.all()]
                
                await crud.create_log(
                    session,
                    event_type="CSV_IMPORT",
                    related_lead_ids=lead_ids,
                    description=f"Импортировано {stats['imported']} лидов из файла {file_path.name} (хеш файла: {file_hash})"
                )
            else:
                logger.info(f"Нет новых лидов для импорта (все дубли или ошибки)")

            return stats
            
        except Exception as e:
            logger.error(f"Ошибка импорта файла {file_path}: {e}")
            stats["errors"] = 1
            return stats


async def import_csv_file(
    session: AsyncSession,
    file_path: Path,
    delimiter: str = ";",
    encoding: str = "utf-8"
) -> Dict[str, int]:
    """
    Импорт CSV файла

    Args:
        session: Сессия БД
        file_path: Путь к файлу
        delimiter: Разделитель CSV
        encoding: Кодировка

    Returns:
        Статистика импорта
    """
    importer = CSVImporter(delimiter=delimiter, encoding=encoding)
    return await importer.import_to_database(session, file_path)


async def import_csv_from_uploads(
    session: AsyncSession,
    uploads_folder: Path,
    filename: Optional[str] = None,
    delimiter: str = ";",
    encoding: str = "utf-8"
) -> Dict[str, Any]:
    """
    Импорт CSV из папки uploads
    
    Args:
        session: Сессия БД
        uploads_folder: Путь к папке uploads
        filename: Конкретный файл для импорта (опционально)
        delimiter: Разделитель CSV
        encoding: Кодировка
        
    Returns:
        {"success": bool, "file": str, "stats": dict, "error": Optional[str]}
    """
    if filename:
        # Импортируем конкретный файл
        file_path = uploads_folder / filename
        if not file_path.exists():
            return {
                "success": False,
                "file": filename,
                "stats": {},
                "error": f"Файл {filename} не найден"
            }
        
        stats = await import_csv_file(session, file_path, delimiter, encoding)
        return {
            "success": True,
            "file": filename,
            "stats": stats,
            "error": None
        }
    else:
        # Возвращаем список доступных файлов
        csv_files = list(uploads_folder.glob("*.csv"))
        return {
            "success": True,
            "files": [f.name for f in csv_files],
            "error": None
        }
