"""
Bitrix24 REST API клиент
"""
import asyncio
import re
import random
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from urllib.parse import urlparse

import aiohttp
from aiohttp import ClientTimeout

from ..logger import get_logger

logger = get_logger(__name__)


class Bitrix24Error(Exception):
    """Исключение Bitrix24 API"""
    def __init__(self, message: str, error_code: Optional[int] = None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class Bitrix24Client:
    """
    Асинхронный клиент Bitrix24 REST API
    
    Поддерживает:
    - Retry logic при ошибках
    - Обработку таймаутов
    - Работу через прокси
    """
    
    # Методы API
    METHOD_DUPLICATE_FIND = "crm.duplicate.findbycomm"
    METHOD_LEAD_ADD = "crm.lead.add"
    METHOD_LEAD_UPDATE = "crm.lead.update"
    METHOD_LEAD_GET = "crm.lead.get"
    METHOD_USER_GET = "user.get"
    
    # Типы дублей
    DUPLICATE_TYPE_LEAD = "lead"
    DUPLICATE_TYPE_CONTACT = "contact"
    DUPLICATE_TYPE_COMPANY = "company"
    
    # Максимальное количество попыток
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # секунды
    
    def __init__(
        self,
        webhook_url: str,
        request_timeout: int = 30,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
        proxy_url: Optional[str] = None
    ):
        """
        Инициализация клиента

        Args:
            webhook_url: URL входящего вебхука Bitrix24
            request_timeout: Таймаут запроса в секундах
            retry_attempts: Количество попыток при ошибках
            retry_delay: Задержка между попытками в секундах
            proxy_url: URL прокси (опционально)

        Raises:
            ValueError: Если webhook_url некорректный
        """
        # ✅ Валидация Bitrix24 webhook URL
        if not self._validate_bitrix24_webhook(webhook_url):
            raise ValueError("Неверный формат Bitrix24 webhook URL. Ожидается https://<portal>.bitrix24.<domain>/rest/<user_id>/<webhook_hash>/")

        self.webhook_url = webhook_url.rstrip("/")
        self.request_timeout = request_timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.proxy_url = proxy_url

        self._session: Optional[aiohttp.ClientSession] = None

    def _validate_bitrix24_webhook(self, url: str) -> bool:
        """
        Валидация Bitrix24 webhook URL

        Проверяет:
        - HTTPS протокол
        - Домен Bitrix24 (.bitrix24.ru, .com, .eu, .by, .kz)
        - Структуру пути (/rest/{user_id}/{webhook_hash}/)

        Args:
            url: URL для проверки

        Returns:
            True если URL корректный
        """
        try:
            parsed = urlparse(url)

            # Проверка HTTPS
            if parsed.scheme != 'https':
                logger.error("Bitrix24 webhook должен использовать HTTPS")
                return False

            # Проверка домена Bitrix24
            bitrix_domains = [
                '.bitrix24.ru', '.bitrix24.com', '.bitrix24.eu',
                '.bitrix24.by', '.bitrix24.kz', '.bitrix24.ua',
                '.bitrix24.ge', '.bitrix24.am', '.bitrix24.md'
            ]
            domain = parsed.netloc.lower()
            if not any(domain.endswith(d) for d in bitrix_domains):
                logger.error(f"Недоверенный домен Bitrix24: {domain}")
                return False

            # Проверка структуры пути (/rest/{user_id}/{webhook_hash}/)
            path_pattern = r'^/rest/\d+/[a-zA-Z0-9]+/?$'
            if not re.match(path_pattern, parsed.path):
                logger.error("Неверная структура пути webhook (ожидается /rest/{user_id}/{webhook_hash}/)")
                return False

            return True
        except Exception as e:
            logger.error(f"Ошибка валидации webhook URL: {e}")
            return False
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получение HTTP сессии"""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=self.request_timeout)
            # Включаем SSL проверку для безопасности
            # Для production с самоподписанными сертификатами можно отключить через параметр
            connector = aiohttp.TCPConnector(
                ssl=True,
                limit=100,  # Лимит соединений
                limit_per_host=20
            )

            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
            )

        return self._session
    
    async def close(self):
        """Закрытие сессии"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Выполнение запроса к API
        
        Args:
            method: Метод API (например, "crm.lead.add")
            params: Параметры запроса
            
        Returns:
            Ответ от API
            
        Raises:
            Bitrix24Error: При ошибке API
        """
        url = f"{self.webhook_url}/{method}.json"
        
        proxy = self.proxy_url if self.proxy_url else None
        
        for attempt in range(self.retry_attempts):
            try:
                session = await self._get_session()
                
                async with session.post(url, json=params, proxy=proxy) as response:
                    # Проверяем HTTP статус перед парсингом JSON
                    if response.status >= 400:
                        text = await response.text()
                        raise Bitrix24Error(
                            f"HTTP {response.status}: {text[:200]}",
                            response.status
                        )

                    result = await response.json(content_type=None)
                    
                    # Проверяем на ошибки API
                    if "error" in result:
                        error_msg = result.get("error_description", result.get("error", "Unknown error"))
                        raise Bitrix24Error(error_msg, result.get("error_code"))
                    
                    return result.get("result", {})
                    
            except aiohttp.ClientError as e:
                logger.warning(f"Попытка {attempt + 1}/{self.retry_attempts} не удалась: {e}")
                if attempt < self.retry_attempts - 1:
                    # ✅ Exponential backoff с jitter: 2s, 4s, 8s + random(0-1s)
                    delay = (2 ** (attempt + 1)) + random.uniform(0, 1)
                    logger.debug(f"Ожидание {delay:.2f}с перед следующей попыткой")
                    await asyncio.sleep(delay)
                else:
                    raise Bitrix24Error(f"Ошибка соединения: {e}")

            except asyncio.TimeoutError:
                logger.warning(f"Попытка {attempt + 1}/{self.retry_attempts} таймаут")
                if attempt < self.retry_attempts - 1:
                    # ✅ Exponential backoff с jitter
                    delay = (2 ** (attempt + 1)) + random.uniform(0, 1)
                    logger.debug(f"Ожидание {delay:.2f}с перед следующей попыткой")
                    await asyncio.sleep(delay)
                else:
                    raise Bitrix24Error("Таймаут запроса к Bitrix24 API")
        
        raise Bitrix24Error("Превышено количество попыток")
    
    async def find_duplicates_by_comm(
        self,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        entity_type: str = DUPLICATE_TYPE_LEAD
    ) -> Dict[str, Any]:
        """
        Поиск дублей по коммуникациям

        Args:
            phone: Телефон для поиска
            email: Email для поиска
            entity_type: Тип сущности (lead, contact, company)

        Returns:
            Результат поиска с дублями

        Example:
            result = await client.find_duplicates_by_comm(phone="+74951234567")
            if result.get("DUPLICATE"):
                # Дубль найден
        """
        # Если нет коммуникаций, возвращаем пустой результат
        if not phone and not email:
            return self._create_empty_duplicate_result()

        result = self._create_empty_duplicate_result()

        # Проверяем телефон
        if phone:
            await self._check_phone_duplicates(phone, result)

        # Проверяем email
        if email:
            await self._check_email_duplicates(email, result)

        return result

    def _create_empty_duplicate_result(self) -> Dict[str, Any]:
        """
        Создание пустого результата проверки на дубли

        Returns:
            Словарь с пустыми результатами
        """
        return {
            "DUPLICATE": False,
            "DUBLICATE_ELEMENT_LIST": [],
            "ELEMENT_LIST": []
        }

    async def _check_phone_duplicates(self, phone: str, result: Dict[str, Any]) -> None:
        """
        Проверка дублей по телефону

        Args:
            phone: Телефон для проверки
            result: Словарь результатов (модифицируется)
        """
        try:
            phone_for_search = self._normalize_phone_for_search(phone)
            logger.info(f"Bitrix24 API запрос: type=PHONE, values=[{phone_for_search}] (исходный: {phone})")

            phone_result = await self._request_with_retry(
                self.METHOD_DUPLICATE_FIND,
                {"type": "PHONE", "values": [phone_for_search]},
                method_name="find_duplicates_by_comm (PHONE)"
            )

            logger.debug(f"Bitrix24 API ответ на запрос телефона {phone_for_search}: {phone_result}")

            lead_ids, contact_ids, company_ids = self._parse_duplicate_response(phone_result)
            logger.debug(f"Разобранный ответ: LEAD={lead_ids}, CONTACT={contact_ids}, COMPANY={company_ids}")

            if lead_ids or contact_ids or company_ids:
                result["DUPLICATE"] = True
                all_ids = lead_ids + contact_ids + company_ids
                result["DUBLICATE_ELEMENT_LIST"] = [{"id": id} for id in all_ids[:10]]
                logger.info(
                    f"Найдены дубли по телефону {phone_for_search}: "
                    f"LEAD={lead_ids}, CONTACT={contact_ids}, COMPANY={company_ids}"
                )
            else:
                logger.info(f"Дублей не найдено по телефону {phone_for_search}")

        except Exception as e:
            logger.error(f"Ошибка поиска дублей по телефону {phone}: {e}")
            raise

    async def _check_email_duplicates(self, email: str, result: Dict[str, Any]) -> None:
        """
        Проверка дублей по email

        Args:
            email: Email для проверки
            result: Словарь результатов (модифицируется)
        """
        try:
            email_result = await self._request_with_retry(
                self.METHOD_DUPLICATE_FIND,
                {"type": "EMAIL", "values": [email]},
                method_name="find_duplicates_by_comm (EMAIL)"
            )

            lead_ids, contact_ids, company_ids = self._parse_duplicate_response(email_result)

            if lead_ids or contact_ids or company_ids:
                result["DUPLICATE"] = True
                all_ids = lead_ids + contact_ids + company_ids
                result["DUBLICATE_ELEMENT_LIST"].extend([{"id": id} for id in all_ids[:10]])

        except Exception as e:
            logger.error(f"Ошибка поиска дублей по email {email}: {e}")
            raise

    def _normalize_phone_for_search(self, phone: str) -> str:
        """
        Нормализация телефона для поиска в Bitrix24

        Bitrix24 хранит телефоны без + (например: 73432472960)

        Args:
            phone: Исходный телефон

        Returns:
            Нормализованный телефон
        """
        phone_for_search = re.sub(r'[^\d]', '', phone)
        
        if phone_for_search.startswith('8') and len(phone_for_search) == 11:
            phone_for_search = '7' + phone_for_search[1:]
        
        return phone_for_search

    def _parse_duplicate_response(
        self,
        response: Any
    ) -> Tuple[List[int], List[int], List[int]]:
        """
        Разбор ответа Bitrix24 API на запрос дублей

        Поддерживает разные форматы ответа:
        - Список ID
        - Словарь с result
        - Вложенная структура

        Args:
            response: Ответ от API

        Returns:
            Кортеж (lead_ids, contact_ids, company_ids)
        """
        if isinstance(response, list):
            lead_ids = response if (len(response) > 0 and isinstance(response[0], int)) else []
            return lead_ids, [], []

        if isinstance(response, dict):
            result_data = response.get("result", response)
            
            if isinstance(result_data, list):
                lead_ids = result_data if (len(result_data) > 0 and isinstance(result_data[0], int)) else []
                return lead_ids, [], []
            
            if isinstance(result_data, dict):
                return (
                    result_data.get("LEAD", []),
                    result_data.get("CONTACT", []),
                    result_data.get("COMPANY", [])
                )

        return [], [], []

    async def _request_with_retry(
        self,
        method: str,
        params: Dict[str, Any],
        method_name: str = "",
        max_retries: int = 3,
        base_delay: float = 2.0
    ) -> Dict[str, Any]:
        """
        Запрос к Bitrix24 API с обработкой Too many requests

        Args:
            method: Метод API
            params: Параметры запроса
            method_name: Название метода для логирования
            max_retries: Максимальное количество попыток
            base_delay: Базовая задержка между попытками (секунды)

        Returns:
            Результат запроса
        """
        for attempt in range(max_retries):
            try:
                return await self._request(method, params)

            except Bitrix24Error as e:
                # Проверяем, является ли ошибка "Too many requests"
                if "Too many requests" in str(e) or "quota" in str(e).lower():
                    if attempt < max_retries - 1:
                        # Экспоненциальная задержка: 2s, 4s, 8s
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"{method_name}: Too many requests. "
                            f"Попытка {attempt + 1}/{max_retries}. Ожидание {delay}с..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"{method_name}: Превышено количество попыток ({max_retries})")
                        raise
                else:
                    # Другая ошибка — пробрасываем сразу
                    raise

        # Не должно произойти, но на всякий случай
        raise Bitrix24Error(f"{method_name}: Не удалось выполнить запрос после {max_retries} попыток")
    
    async def add_lead(
        self,
        title: str,
        company_title: Optional[str] = None,
        phone: Optional[str] = None,
        mobile_phone: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        website: Optional[str] = None,
        comment: Optional[str] = None,
        assigned_by_id: Optional[int] = None,
        status_id: str = "NEW",
        source_id: str = "TELEGRAM",
        currency_id: str = "RUB",
        opportunity: Optional[str] = None,
        service_type: Optional[str] = None,  # Тип услуги
        phone_source: Optional[str] = None,  # Источник телефона
        additional_fields: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Создание лида в Bitrix24
        
        Args:
            title: Название лида (обязательно)
            company_title: Название компании
            phone: Рабочий телефон
            mobile_phone: Мобильный телефон
            email: Email
            address: Адрес
            city: Город
            website: Сайт
            comment: Комментарий
            assigned_by_id: ID ответственного в Bitrix24
            status_id: Статус лида
            source_id: Источник
            currency_id: Валюта
            opportunity: Сумма лида
            additional_fields: Дополнительные поля
            
        Returns:
            ID созданного лида

        Raises:
            Bitrix24Error: При ошибке создания
        """
        fields = self._build_lead_fields(
            title=title,
            company_title=company_title,
            phone=phone,
            mobile_phone=mobile_phone,
            email=email,
            address=address,
            city=city,
            website=website,
            comment=comment,
            assigned_by_id=assigned_by_id,
            status_id=status_id,
            source_id=source_id,
            currency_id=currency_id,
            opportunity=opportunity,
            service_type=service_type,
            phone_source=phone_source,
            additional_fields=additional_fields
        )

        logger.info(f"Bitrix24 API запрос: {self.METHOD_LEAD_ADD}, fields={fields}")
        result = await self._request(self.METHOD_LEAD_ADD, {"fields": fields})
        logger.info(f"Bitrix24 API ответ: {result} (тип: {type(result)})")

        lead_id = self._parse_lead_id(result)
        logger.info(f"Создан лид ID: {lead_id}")
        return lead_id

    def _build_lead_fields(
        self,
        title: str,
        company_title: Optional[str] = None,
        phone: Optional[str] = None,
        mobile_phone: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        website: Optional[str] = None,
        comment: Optional[str] = None,
        assigned_by_id: Optional[int] = None,
        status_id: str = "NEW",
        source_id: str = "TELEGRAM",
        currency_id: str = "RUB",
        opportunity: Optional[str] = None,
        service_type: Optional[str] = None,
        phone_source: Optional[str] = None,
        additional_fields: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Построение полей для создания лида

        Args:
            Все параметры аналогичны add_lead

        Returns:
            Словарь полей для API запроса
        """
        fields = {
            "TITLE": title,
            "STATUS_ID": status_id,
            "SOURCE_ID": source_id,
            "CURRENCY_ID": currency_id,
        }

        self._add_contact_fields(fields, phone, mobile_phone, email, website)
        self._add_company_fields(fields, company_title)
        self._add_address_fields(fields, address, city)
        self._add_responsible_fields(fields, assigned_by_id)
        self._add_optional_fields(fields, comment, opportunity, additional_fields)
        self._add_custom_fields(fields, service_type, phone_source)

        return fields

    def _add_contact_fields(
        self,
        fields: Dict[str, Any],
        phone: Optional[str],
        mobile_phone: Optional[str],
        email: Optional[str],
        website: Optional[str]
    ) -> None:
        """
        Добавление контактных данных

        Args:
            fields: Словарь полей (модифицируется)
            phone: Рабочий телефон
            mobile_phone: Мобильный телефон
            email: Email
            website: Сайт
        """
        if phone:
            fields["PHONE"] = [{"VALUE": phone, "VALUE_TYPE": "WORK"}]
        
        if mobile_phone:
            if "PHONE" not in fields:
                fields["PHONE"] = []
            fields["PHONE"].append({"VALUE": mobile_phone, "VALUE_TYPE": "MOBILE"})
        
        if email:
            fields["EMAIL"] = [{"VALUE": email, "VALUE_TYPE": "WORK"}]
        
        if website:
            fields["WEB"] = [{"VALUE": website, "VALUE_TYPE": "OTHER"}]

    def _add_company_fields(
        self,
        fields: Dict[str, Any],
        company_title: Optional[str]
    ) -> None:
        """Добавление полей компании."""
        if company_title:
            fields["COMPANY_TITLE"] = company_title

    def _add_address_fields(
        self,
        fields: Dict[str, Any],
        address: Optional[str],
        city: Optional[str]
    ) -> None:
        """Добавление полей адреса."""
        if address:
            fields["ADDRESS"] = [{"VALUE": address, "VALUE_TYPE": "WORK"}]
        if city:
            fields["ADDRESS_CITY"] = city

    def _add_responsible_fields(
        self,
        fields: Dict[str, Any],
        assigned_by_id: Optional[int]
    ) -> None:
        """Добавление ответственного."""
        if assigned_by_id:
            fields["ASSIGNED_BY_ID"] = assigned_by_id

    def _add_optional_fields(
        self,
        fields: Dict[str, Any],
        comment: Optional[str],
        opportunity: Optional[str],
        additional_fields: Optional[Dict[str, Any]]
    ) -> None:
        """Добавление необязательных полей."""
        if comment:
            fields["COMMENTS"] = comment
        if opportunity:
            fields["OPPORTUNITY"] = opportunity
        if additional_fields:
            fields.update(additional_fields)

    def _add_custom_fields(
        self,
        fields: Dict[str, Any],
        service_type: Optional[str],
        phone_source: Optional[str]
    ) -> None:
        """
        Добавление кастомных полей Bitrix24.

        Args:
            fields: Словарь полей (модифицируется)
            service_type: Тип услуги
            phone_source: Источник телефона
        """
        if service_type:
            fields["UF_CRM_1745433492760"] = service_type
        if phone_source:
            fields["UF_CRM_1768999878619"] = phone_source

    def _parse_lead_id(self, result: Any) -> int:
        """
        Разбор ID созданного лида из ответа API.

        Args:
            result: Ответ от API

        Returns:
            ID лида (0 если не удалось распарсить)
        """
        if isinstance(result, int):
            return result
        
        if isinstance(result, dict):
            lead_id = result.get("id", result.get("result", {}).get("id", 0))
            return int(lead_id) if lead_id else 0
        
        return 0
    
    async def update_lead(
        self,
        lead_id: int,
        fields: Dict[str, Any]
    ) -> bool:
        """
        Обновление лида
        
        Args:
            lead_id: ID лида
            fields: Поля для обновления
            
        Returns:
            True при успехе
        """
        result = await self._request(
            self.METHOD_LEAD_UPDATE,
            {"id": lead_id, "fields": fields}
        )
        return result is True
    
    async def get_lead(self, lead_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение лида по ID
        
        Args:
            lead_id: ID лида
            
        Returns:
            Данные лида или None
        """
        try:
            result = await self._request(self.METHOD_LEAD_GET, {"id": lead_id})
            return result
        except Bitrix24Error:
            return None
    
    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение пользователя Bitrix24 по ID
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Данные пользователя или None
        """
        try:
            result = await self._request(
                self.METHOD_USER_GET,
                {"ID": user_id}
            )
            # Возвращаем первого пользователя из списка
            if isinstance(result, list) and len(result) > 0:
                return result[0]
            return result
        except Bitrix24Error:
            return None
    
    async def search_user(self, name: str) -> List[Dict[str, Any]]:
        """
        Поиск пользователя по имени

        Args:
            name: Имя для поиска

        Returns:
            Список найденных пользователей
        """
        try:
            result = await self._request(
                self.METHOD_USER_GET,
                {"FILTER": {"NAME": name}}
            )
            return result if isinstance(result, list) else []
        except Bitrix24Error:
            return []

    async def find_leads_by_company_name(
        self,
        company_name: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Поиск лидов по названию компании

        Args:
            company_name: Название компании для поиска
            limit: Максимальное количество результатов

        Returns:
            Список найденных лидов
        """
        try:
            result = await self._request_with_retry(
                "crm.lead.list",
                {
                    "filter": {"=COMPANY_TITLE": company_name},
                    "select": ["ID", "TITLE", "COMPANY_TITLE", "PHONE"],
                    "limit": limit
                },
                method_name="find_leads_by_company_name"
            )
            return result if isinstance(result, list) else []
        except Bitrix24Error:
            return []

    async def find_leads_by_address(
        self,
        address: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Поиск лидов по адресу

        Args:
            address: Адрес для поиска
            limit: Максимальное количество результатов

        Returns:
            Список найденных лидов
        """
        try:
            result = await self._request_with_retry(
                "crm.lead.list",
                {
                    "filter": {"=ADDRESS": address},
                    "select": ["ID", "TITLE", "COMPANY_TITLE", "ADDRESS"],
                    "limit": limit
                },
                method_name="find_leads_by_address"
            )
            return result if isinstance(result, list) else []
        except Bitrix24Error:
            return []


# =============================================================================
# Фабрика Bitrix24 клиентов
# =============================================================================

_client_cache: Dict[str, Bitrix24Client] = {}


def get_bitrix24_client(
    webhook_url: str,
    cached: bool = True,
    **kwargs
) -> Bitrix24Client:
    """
    Получение или создание клиента Bitrix24
    
    Args:
        webhook_url: URL вебхука
        cached: Если True, использует кэшированный экземпляр для данного webhook_url
        **kwargs: Дополнительные параметры
    
    Returns:
        Клиент Bitrix24
        
    Example:
        >>> client = get_bitrix24_client("https://portal.bitrix24.ru/rest/1/webhook/")
        >>> client.get_lead(123)
    """
    global _client_cache
    
    # Используем webhook_url как ключ для кэша
    cache_key = webhook_url
    
    if not cached or cache_key not in _client_cache:
        _client_cache[cache_key] = Bitrix24Client(webhook_url, **kwargs)
    
    return _client_cache[cache_key]


def clear_bitrix24_client_cache(webhook_url: Optional[str] = None) -> None:
    """
    Очистка кэша клиентов Bitrix24
    
    Args:
        webhook_url: Если указан, очищает только клиент для данного webhook_url.
                     Если None, очищает весь кэш.
    """
    global _client_cache
    
    if webhook_url:
        _client_cache.pop(webhook_url, None)
    else:
        _client_cache.clear()
