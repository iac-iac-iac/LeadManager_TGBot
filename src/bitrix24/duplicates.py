"""
Модуль проверки дублей в Bitrix24

Использует параллельную обработку с контролем rate limiting
"""
import asyncio
import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from .client import Bitrix24Client, Bitrix24Error
from ..database.models import Lead, LeadStatus
from ..database import crud
from ..logger import get_logger

logger = get_logger(__name__)


class DuplicateChecker:
    """
    Сервис проверки лидов на дубли
    
    Использует Bitrix24 API метод crm.duplicate.findbycomm
    """
    
    def __init__(self, bitrix24_client: Bitrix24Client):
        """
        Инициализация сервиса
        
        Args:
            bitrix24_client: Клиент Bitrix24 API
        """
        self.client = bitrix24_client
    
    async def check_lead_duplicate(
        self,
        session: AsyncSession,
        lead_id: int,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        company_name: Optional[str] = None,
        address: Optional[str] = None
    ) -> bool:
        """
        Проверка конкретного лида на дубль

        Args:
            session: Сессия БД
            lead_id: ID лида
            phone: Телефон для проверки
            email: Email для проверки
            company_name: Название компании для проверки
            address: Адрес для проверки

        Returns:
            True если дубль найден, False если уникальный
        """
        try:
            is_duplicate = False
            duplicate_reason = None
            bitrix24_lead_id = None

            # 1. Проверка по телефону (основная)
            if phone:
                result = await self.client.find_duplicates_by_comm(
                    phone=phone,
                    email=email,
                    entity_type=Bitrix24Client.DUPLICATE_TYPE_LEAD
                )

                if result.get("DUPLICATE", False):
                    is_duplicate = True
                    duplicate_reason = "PHONE"
                    duplicate_data = result.get("DUBLICATE_ELEMENT_LIST", [])
                    if duplicate_data and len(duplicate_data) > 0:
                        bitrix24_lead_id = duplicate_data[0].get("id")
                    logger.info(f"Лид {lead_id}: найден дубль по телефону")

            # 2. Проверка по названию компании (если не найден по телефону)
            if not is_duplicate and company_name:
                try:
                    company_leads = await self.client.find_leads_by_company_name(
                        company_name=company_name,
                        limit=5
                    )
                    logger.info(f"Лид {lead_id}: поиск по компании '{company_name}' → найдено {len(company_leads)} лидов")
                    if company_leads:
                        is_duplicate = True
                        duplicate_reason = "COMPANY"
                        bitrix24_lead_id = company_leads[0].get("id")
                        logger.info(f"Лид {lead_id}: найден дубль по компании '{company_name}' (ID: {bitrix24_lead_id})")
                except Exception as e:
                    logger.error(f"Лид {lead_id}: ошибка проверки по компании: {e}")

            # 3. Проверка по адресу (опционально, если не найден по другим критериям)
            if not is_duplicate and address:
                try:
                    address_leads = await self.client.find_leads_by_address(
                        address=address,
                        limit=5
                    )
                    logger.info(f"Лид {lead_id}: поиск по адресу '{address}' → найдено {len(address_leads)} лидов")
                    if address_leads:
                        is_duplicate = True
                        duplicate_reason = "ADDRESS"
                        bitrix24_lead_id = address_leads[0].get("id")
                        logger.info(f"Лид {lead_id}: найден дубль по адресу '{address}' (ID: {bitrix24_lead_id})")
                except Exception as e:
                    logger.error(f"Лид {lead_id}: ошибка проверки по адресу: {e}")

            # Обновляем статус лида
            if is_duplicate:
                await crud.mark_lead_as_duplicate(
                    session,
                    lead_id,
                    bitrix24_lead_id
                )
                logger.info(f"Лид {lead_id}: дубль ({duplicate_reason})")
                return True
            else:
                await crud.mark_lead_as_unique(session, lead_id)
                logger.info(f"Лид {lead_id}: дублей не найдено")
                return False

        except Bitrix24Error as e:
            logger.error(f"Ошибка проверки дубля для лида {lead_id}: {e}")
            # При ошибке API помечаем как уникальный (чтобы не блокировать импорт)
            await crud.mark_lead_as_unique(session, lead_id)
            return False
    
    async def check_leads_batch(
        self,
        session: AsyncSession,
        lead_ids: List[int],
        batch_size: int = 10,
        max_parallel: int = 3,  # Уменьшено с 5 до 3 для снижения нагрузки
        rate_limit_delay: float = 0.5  # Увеличено с 0.2 до 0.5 сек
    ) -> Dict[str, int]:
        """
        Пакетная проверка лидов на дубли с параллельной обработкой

        Args:
            session: Сессия БД
            lead_ids: Список ID лидов для проверки
            batch_size: Размер пакета (для обратной совместимости)
            max_parallel: Максимальное количество параллельных запросов
            rate_limit_delay: Задержка между запросами для одного воркера

        Returns:
            Статистика: {"duplicates": N, "unique": N, "errors": N}
        """
        stats = {"duplicates": 0, "unique": 0, "errors": 0}

        # Получаем лиды из БД
        leads = []
        for lead_id in lead_ids:
            lead = await crud.get_lead_by_id(session, lead_id)
            if lead and lead.status == LeadStatus.NEW:
                leads.append(lead)

        logger.info(f"Начата проверка {len(leads)} лидов на дубли (параллелизм: {max_parallel})")

        if not leads:
            return stats

        # Semaphore для ограничения параллелизма
        semaphore = asyncio.Semaphore(max_parallel)

        async def check_single_lead(lead: Lead) -> Tuple[int, str]:
            """
            Проверка одного лида с ограничением параллелизма

            Returns:
                (lead_id, result_type) где result_type: "duplicates", "unique", "error"
            """
            async with semaphore:
                try:
                    result = await self._check_single_lead_internal(lead, semaphore, session)
                    return result
                except Exception as e:
                    logger.error(f"Лид {lead.id}: критическая ошибка проверки: {type(e).__name__}: {e}")
                    stats["errors"] += 1
                    return lead.id, "error"

        # Запускаем параллельную проверку
        tasks = [check_single_lead(lead) for lead in leads]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Обрабатываем результаты
        for result in results:
            if isinstance(result, Exception):
                stats["errors"] += 1
            else:
                lead_id, result_type = result
                # Маппинг result_type в ключи статистики
                if result_type == "duplicates":
                    stats["duplicates"] += 1
                elif result_type == "unique":
                    stats["unique"] += 1
                else:
                    stats["errors"] += 1

        logger.info(f"Проверка завершена: {stats}")
        return stats

    async def _check_single_lead_internal(
        self,
        lead: Lead,
        semaphore: asyncio.Semaphore,
        session: AsyncSession
    ) -> Tuple[int, str]:
        """
        Внутренний метод проверки одного лида

        Args:
            lead: Лид для проверки
            semaphore: Семафор для ограничения параллелизма
            session: Сессия БД

        Returns:
            (lead_id, result_type)
        """
        # Собираем коммуникации для проверки
        phones_to_check = self._normalize_phones_for_lead(lead)

        # Guard clause: нет телефонов
        if not phones_to_check:
            logger.warning(f"Лид {lead.id}: нет телефона, помечен как уникальный")
            await crud.mark_lead_as_unique(session, lead.id)
            return lead.id, "unique"

        logger.debug(f"Лид {lead.id}: проверка телефонов {phones_to_check}, компании {lead.company_name}, адреса {lead.address}")

        # Проверяем дубли
        is_duplicate, reason, bitrix_id = await self._check_duplicates(
            lead, phones_to_check, session
        )

        # Обновляем статус лида
        if is_duplicate:
            await crud.mark_lead_as_duplicate(session, lead.id, bitrix_id)
            logger.info(f"Лид {lead.id}: найден дубль по {reason}")
            return lead.id, "duplicates"
        else:
            await crud.mark_lead_as_unique(session, lead.id)
            logger.info(f"Лид {lead.id}: уникален")
            return lead.id, "unique"

    def _normalize_phones_for_lead(self, lead: Lead) -> List[str]:
        """
        Нормализация телефонов лида для проверки

        Args:
            lead: Лид для проверки

        Returns:
            Список нормализованных телефонов
        """
        phones_to_check = []

        # Нормализуем основной телефон
        if lead.phone:
            phone_normalized = self._normalize_single_phone(lead.phone)
            if phone_normalized and len(phone_normalized) >= 11:
                phones_to_check.append(phone_normalized)

        # Нормализуем мобильный телефон (если отличается от основного)
        if lead.mobile_phone and lead.mobile_phone != lead.phone:
            mobile_normalized = self._normalize_single_phone(lead.mobile_phone)
            if mobile_normalized and len(mobile_normalized) >= 11:
                phones_to_check.append(mobile_normalized)

        return phones_to_check

    def _normalize_single_phone(self, phone: str) -> Optional[str]:
        """
        Нормализация одного телефонного номера

        Args:
            phone: Исходный номер

        Returns:
            Нормализованный номер или None
        """
        phone_normalized = re.sub(r'[^\d+]', '', phone)

        # Добавляем + если нет
        if not phone_normalized.startswith('+'):
            if phone_normalized.startswith('7') and len(phone_normalized) == 11:
                phone_normalized = '+' + phone_normalized
            elif len(phone_normalized) == 10:
                phone_normalized = '+7' + phone_normalized
            else:
                phone_normalized = '+' + phone_normalized

        # Проверяем минимальную длину
        return phone_normalized if len(phone_normalized) >= 11 else None

    async def _check_duplicates(
        self,
        lead: Lead,
        phones_to_check: List[str],
        session: AsyncSession
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Проверка лида на дубли по телефонам, компании и адресу
        
        Args:
            lead: Лид для проверки
            phones_to_check: Список нормализованных телефонов
            session: Сессия БД
            
        Returns:
            (is_duplicate, reason, bitrix24_lead_id)
        """
        email = lead.work_email
        
        # Проверяем каждый телефон
        for phone_to_check in phones_to_check:
            result = await self.client.find_duplicates_by_comm(
                phone=phone_to_check,
                email=email,
                entity_type=Bitrix24Client.DUPLICATE_TYPE_LEAD
            )
            
            if result.get("DUPLICATE", False):
                duplicate_data = result.get("DUBLICATE_ELEMENT_LIST", [])
                bitrix_id = duplicate_data[0].get("id") if duplicate_data else None
                logger.info(f"Лид {lead.id}: найден дубль по телефону {phone_to_check}")
                return True, f"PHONE ({phone_to_check})", bitrix_id
        
        # Если не найден по телефону, проверяем по компании
        if lead.company_name:
            try:
                company_leads = await self.client.find_leads_by_company_name(
                    company_name=lead.company_name,
                    limit=5
                )
                logger.info(f"Лид {lead.id}: поиск по компании '{lead.company_name}' → найдено {len(company_leads)} лидов")
                if company_leads:
                    logger.info(f"Лид {lead.id}: найден дубль по компании '{lead.company_name}'")
                    return True, "COMPANY", company_leads[0].get("id")
            except Exception as e:
                logger.error(f"Лид {lead.id}: ошибка проверки по компании: {e}")
        
        # Если не найден по телефону/компании, проверяем по адресу
        if lead.address:
            try:
                address_leads = await self.client.find_leads_by_address(
                    address=lead.address,
                    limit=5
                )
                logger.info(f"Лид {lead.id}: поиск по адресу '{lead.address}' → найдено {len(address_leads)} лидов")
                if address_leads:
                    logger.info(f"Лид {lead.id}: найден дубль по адресу '{lead.address}'")
                    return True, "ADDRESS", address_leads[0].get("id")
            except Exception as e:
                logger.error(f"Лид {lead.id}: ошибка проверки по адресу: {e}")
        
        return False, None, None

    async def _fetch_new_leads(
        self,
        session: AsyncSession,
        lead_ids: List[int]
    ) -> List[Lead]:
        """
        Получение новых лидов из БД

        Args:
            session: Сессия БД
            lead_ids: Список ID лидов

        Returns:
            Список лидов со статусом NEW
        """
        leads = []
        for lead_id in lead_ids:
            lead = await crud.get_lead_by_id(session, lead_id)
            if lead and lead.status == LeadStatus.NEW:
                leads.append(lead)
        return leads

    async def _check_single_lead(
        self,
        lead: Lead,
        session: AsyncSession,
        semaphore: asyncio.Semaphore
    ) -> Tuple[int, str]:
        """
        Проверка одного лида на дубли

        Args:
            lead: Лид для проверки
            session: Сессия БД
            semaphore: Семафор для ограничения параллелизма

        Returns:
            (lead_id, result_type) где result_type: "duplicates", "unique", "error"
        """
        async with semaphore:
            try:
                # Нормализуем телефоны
                phones_to_check = self._normalize_phones(lead.phone, lead.mobile_phone)

                # Если нет телефонов - помечаем как уникальный
                if not phones_to_check:
                    logger.warning(f"Лид {lead.id}: нет телефона, помечен как уникальный")
                    await crud.mark_lead_as_unique(session, lead.id)
                    return lead.id, "unique"

                logger.debug(
                    f"Лид {lead.id}: проверка телефонов {phones_to_check}, "
                    f"компании {lead.company_name}, адреса {lead.address}"
                )

                # Проверяем дубли
                is_duplicate, bitrix24_lead_id, duplicate_reason = await self._check_duplicate(
                    session,
                    lead.id,
                    phones_to_check,
                    lead.work_email,
                    lead.company_name,
                    lead.address
                )

                # Обновляем статус лида
                if is_duplicate:
                    await crud.mark_lead_as_duplicate(session, lead.id, bitrix24_lead_id)
                    logger.info(f"Лид {lead.id}: дубль ({duplicate_reason})")
                    return lead.id, "duplicates"
                else:
                    await crud.mark_lead_as_unique(session, lead.id)
                    logger.info(f"Лид {lead.id}: дублей не найдено")
                    return lead.id, "unique"

            except Exception as e:
                logger.error(f"Ошибка при проверке лида {lead.id}: {type(e).__name__}: {e}")
                return lead.id, "error"

    def _normalize_phones(
        self,
        phone: Optional[str],
        mobile_phone: Optional[str]
    ) -> List[str]:
        """
        Нормализация телефонов для проверки

        Args:
            phone: Рабочий телефон
            mobile_phone: Мобильный телефон

        Returns:
            Список нормализованных телефонов
        """
        phones_to_check = []

        if phone:
            phone_normalized = self._normalize_single_phone(phone)
            if phone_normalized and len(phone_normalized) >= 11:
                phones_to_check.append(phone_normalized)

        if mobile_phone and mobile_phone != phone:
            mobile_normalized = self._normalize_single_phone(mobile_phone)
            if mobile_normalized and len(mobile_normalized) >= 11:
                phones_to_check.append(mobile_normalized)

        return phones_to_check

    def _normalize_single_phone(self, phone: str) -> Optional[str]:
        """
        Нормализация одного телефона

        Args:
            phone: Телефон для нормализации

        Returns:
            Нормализованный телефон или None
        """
        phone_normalized = re.sub(r'[^\d+]', '', phone)
        
        if not phone_normalized.startswith('+'):
            if phone_normalized.startswith('7') and len(phone_normalized) == 11:
                phone_normalized = '+' + phone_normalized
            elif len(phone_normalized) == 10:
                phone_normalized = '+7' + phone_normalized
            else:
                phone_normalized = '+' + phone_normalized
        
        return phone_normalized

    async def _check_duplicate(
        self,
        session: AsyncSession,
        lead_id: int,
        phones_to_check: List[str],
        email: Optional[str],
        company_name: Optional[str],
        address: Optional[str]
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Проверка лида на дубли по всем критериям

        Args:
            session: Сессия БД
            lead_id: ID лида
            phones_to_check: Список телефонов для проверки
            email: Email лида
            company_name: Название компании
            address: Адрес

        Returns:
            (is_duplicate, bitrix24_lead_id, duplicate_reason)
        """
        is_duplicate = False
        bitrix24_lead_id = None
        duplicate_reason = None

        # Проверка по телефону
        for phone_to_check in phones_to_check:
            result = await self.client.find_duplicates_by_comm(
                phone=phone_to_check,
                email=email,
                entity_type=Bitrix24Client.DUPLICATE_TYPE_LEAD
            )

            if result.get("DUPLICATE", False):
                is_duplicate = True
                duplicate_reason = f"PHONE ({phone_to_check})"
                duplicate_data = result.get("DUBLICATE_ELEMENT_LIST", [])
                if duplicate_data and len(duplicate_data) > 0:
                    bitrix24_lead_id = duplicate_data[0].get("id")
                logger.info(f"Лид {lead_id}: найден дубль по телефону {phone_to_check}")
                break

        # Проверка по компании
        if not is_duplicate and company_name:
            is_duplicate, bitrix24_lead_id = await self._check_company_duplicate(
                lead_id, company_name
            )
            if is_duplicate:
                duplicate_reason = "COMPANY"

        # Проверка по адресу
        if not is_duplicate and address:
            is_duplicate, bitrix24_lead_id = await self._check_address_duplicate(
                lead_id, address
            )
            if is_duplicate:
                duplicate_reason = "ADDRESS"

        return is_duplicate, bitrix24_lead_id, duplicate_reason

    async def _check_company_duplicate(
        self,
        lead_id: int,
        company_name: str
    ) -> Tuple[bool, Optional[int]]:
        """
        Проверка дубля по названию компании

        Args:
            lead_id: ID лида
            company_name: Название компании

        Returns:
            (is_duplicate, bitrix24_lead_id)
        """
        try:
            company_leads = await self.client.find_leads_by_company_name(
                company_name=company_name,
                limit=5
            )
            logger.info(
                f"Лид {lead_id}: поиск по компании '{company_name}' → "
                f"найдено {len(company_leads)} лидов"
            )
            if company_leads:
                return True, company_leads[0].get("id")
        except Exception as e:
            logger.error(f"Лид {lead_id}: ошибка проверки по компании: {e}")
        
        return False, None

    async def _check_address_duplicate(
        self,
        lead_id: int,
        address: str
    ) -> Tuple[bool, Optional[int]]:
        """
        Проверка дубля по адресу

        Args:
            lead_id: ID лида
            address: Адрес

        Returns:
            (is_duplicate, bitrix24_lead_id)
        """
        try:
            address_leads = await self.client.find_leads_by_address(
                address=address,
                limit=5
            )
            logger.info(
                f"Лид {lead_id}: поиск по адресу '{address}' → "
                f"найдено {len(address_leads)} лидов"
            )
            if address_leads:
                return True, address_leads[0].get("id")
        except Exception as e:
            logger.error(f"Лид {lead_id}: ошибка проверки по адресу: {e}")
        
        return False, None

    def _process_check_results(
        self,
        results: List[Any],
        stats: Dict[str, int]
    ) -> Dict[str, int]:
        """
        Обработка результатов проверки лидов

        Args:
            results: Результаты задач
            stats: Текущая статистика

        Returns:
            Обновлённая статистика
        """
        logger.info(f"Получено результатов: {len(results)}")
        processed_count = 0

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Необработанное исключение в задаче: {type(result).__name__}: {result}")
                stats["errors"] += 1
            elif isinstance(result, tuple):
                lead_id, result_type = result
                log_type = "duplicate" if result_type == "duplicates" else result_type
                logger.info(f"Лид {lead_id}: результат {log_type}")
                if result_type in stats:
                    stats[result_type] += 1
                    processed_count += 1
            else:
                logger.warning(f"Неожиданный формат результата: {type(result)} = {result}")
                stats["errors"] += 1

        logger.info(f"Обработано лидов: {processed_count}")
        return stats

    async def _create_check_log(
        self,
        session: AsyncSession,
        lead_ids: List[int],
        total_leads: int,
        duplicates: int,
        unique: int,
        errors: int
    ) -> None:
        """
        Создание записи в логе о проверке на дубли

        Args:
            session: Сессия БД
            lead_ids: Список ID лидов
            total_leads: Всего проверено лидов
            duplicates: Количество дублей
            unique: Количество уникальных
            errors: Количество ошибок
        """
        await crud.create_log(
            session,
            event_type="DUPLICATE_CHECK",
            related_lead_ids=lead_ids,
            description=(
                f"Проверено лидов: {total_leads}. "
                f"Дубли: {duplicates}, Уникальные: {unique}, Ошибки: {errors}"
            )
        )
    
    async def check_new_leads(
        self,
        session: AsyncSession,
        limit: Optional[int] = None
    ) -> Dict[str, int]:
        """
        Проверка всех новых лидов на дубли
        
        Args:
            session: Сессия БД
            limit: Лимит лидов для проверки
            
        Returns:
            Статистика проверки
        """
        # Получаем все новые лиды
        new_leads = await crud.get_leads_by_status(
            session,
            LeadStatus.NEW,
            limit=limit
        )
        
        if not new_leads:
            logger.info("Нет новых лидов для проверки на дубли")
            return {"duplicates": 0, "unique": 0, "errors": 0}
        
        lead_ids = [lead.id for lead in new_leads]
        return await self.check_leads_batch(session, lead_ids)


async def run_duplicate_check(
    session: AsyncSession,
    bitrix24_client: Bitrix24Client,
    lead_ids: Optional[List[int]] = None,
    check_all_new: bool = False,
    limit: Optional[int] = None
) -> Dict[str, int]:
    """
    Запуск проверки на дубли
    
    Args:
        session: Сессия БД
        bitrix24_client: Клиент Bitrix24
        lead_ids: Список ID лидов для проверки
        check_all_new: Проверить все новые лиды
        limit: Лимит лидов
        
    Returns:
        Статистика проверки
    """
    checker = DuplicateChecker(bitrix24_client)
    
    if check_all_new:
        return await checker.check_new_leads(session, limit)
    elif lead_ids:
        return await checker.check_leads_batch(session, lead_ids)
    else:
        logger.warning("Не указаны лиды для проверки на дубли")
        return {"duplicates": 0, "unique": 0, "errors": 0}
