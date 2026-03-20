"""
Middleware для rate limiting (ограничение частоты запросов)

Защищает бота от:
- DoS атак через спам командами
- Brute force атак на регистрацию
- Чрезмерной нагрузки на БД и API
"""
import asyncio
import re
from typing import Callable, Dict, Any, Awaitable, Optional
from collections import defaultdict
from datetime import datetime, timedelta

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from ...logger import get_logger

logger = get_logger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """
    Middleware для ограничения частоты запросов от пользователей

    Использует sliding window алгоритм для подсчёта запросов
    """

    def __init__(
        self,
        message_limit: int = 10,
        message_window: int = 60,
        callback_limit: int = 20,
        callback_window: int = 60,
        skip_admins: bool = True
    ):
        """
        Инициализация middleware

        Args:
            message_limit: Максимальное количество сообщений в окно
            message_window: Окно времени для сообщений (секунды)
            callback_limit: Максимальное количество callback'ов в окно
            callback_window: Окно времени для callback'ов (секунды)
            skip_admins: Пропускать ли админов без ограничений
        """
        super().__init__()

        self.message_limit = message_limit
        self.message_window = message_window
        self.callback_limit = callback_limit
        self.callback_window = callback_window
        self.skip_admins = skip_admins

        # Хранилище запросов: {user_id: [timestamp1, timestamp2, ...]}
        self._message_requests: Dict[int, list] = defaultdict(list)
        self._callback_requests: Dict[int, list] = defaultdict(list)

        # Блокировка для потокобезопасности
        self._lock = asyncio.Lock()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Вызов middleware

        Args:
            handler: Обработчик
            event: Событие
            data: Данные контекста

        Returns:
            Результат обработчика или None
        """
        # Получаем пользователя
        if isinstance(event, Message):
            user_id = event.from_user.id
            request_type = 'message'
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            request_type = 'callback'
        else:
            return await handler(event, data)

        # Проверяем, админ ли (если включена опция пропуска)
        is_admin = data.get("is_admin", False)
        if self.skip_admins and is_admin:
            return await handler(event, data)

        # Проверяем rate limit
        async with self._lock:
            if request_type == 'message':
                allowed = await self._check_rate_limit(
                    user_id,
                    self._message_requests,
                    self.message_limit,
                    self.message_window
                )
            else:
                allowed = await self._check_rate_limit(
                    user_id,
                    self._callback_requests,
                    self.callback_limit,
                    self.callback_window
                )

        if not allowed:
            # Превышен лимит
            if isinstance(event, Message):
                await event.answer(
                    "⚠️ Слишком много запросов. Пожалуйста, подождите немного."
                )
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "⚠️ Слишком много запросов. Пожалуйста, подождите немного.",
                    show_alert=True
                )
            logger.warning(
                f"Rate limit превышен для пользователя {user_id} "
                f"({'message' if request_type == 'message' else 'callback'})"
            )
            return None

        # Продолжаем обработку
        return await handler(event, data)

    async def _check_rate_limit(
        self,
        user_id: int,
        request_store: Dict[int, list],
        limit: int,
        window: int
    ) -> bool:
        """
        Проверка соблюдения лимита запросов

        Args:
            user_id: ID пользователя
            request_store: Хранилище запросов
            limit: Максимальное количество запросов
            window: Окно времени (секунды)

        Returns:
            True если запрос разрешён
        """
        now = datetime.now()
        cutoff = now - timedelta(seconds=window)

        # Получаем историю запросов
        requests = request_store[user_id]

        # Удаляем старые запросы за пределами окна
        requests = [ts for ts in requests if ts > cutoff]
        request_store[user_id] = requests

        # Проверяем лимит
        if len(requests) >= limit:
            return False

        # Добавляем текущий запрос
        requests.append(now)
        return True

    def cleanup(self, older_than: int = 3600) -> None:
        """
        Очистка старых записей

        Args:
            older_than: Удалять записей старше этого времени (секунды)
        """
        cutoff = datetime.now() - timedelta(seconds=older_than)

        for store in [self._message_requests, self._callback_requests]:
            for user_id in list(store.keys()):
                store[user_id] = [
                    ts for ts in store[user_id] if ts > cutoff
                ]
                if not store[user_id]:
                    del store[user_id]


class SpamFilterMiddleware(BaseMiddleware):
    """
    Middleware для фильтрации спама

    Блокирует:
    - Сообщения с чрезмерным количеством символов
    - Сообщения с подозрительными ссылками
    - Частые одинаковые сообщения
    """

    MAX_MESSAGE_LENGTH = 1000
    SUSPICIOUS_PATTERNS = [
        r'http[s]?://\S+',  # URL
        r'@\w+',  # Telegram username
        r'\b\d{10,}\b',  # Длинные числа (возможно телефоны)
    ]

    def __init__(self, max_same_messages: int = 5, window: int = 60):
        """
        Инициализация

        Args:
            max_same_messages: Максимальное количество одинаковых сообщений
            window: Окно времени (секунды)
        """
        self.max_same_messages = max_same_messages
        self.window = window
        self._message_history: Dict[int, list] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Вызов middleware"""
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id
        text = event.text or ""

        # Проверяем длину
        if len(text) > self.MAX_MESSAGE_LENGTH:
            logger.warning(
                f"Спам от пользователя {user_id}: сообщение слишком длинное "
                f"({len(text)} символов)"
            )
            await event.answer(
                "⚠️ Сообщение слишком длинное. Пожалуйста, сократите его."
            )
            return None

        # Проверяем подозрительные паттерны
        for pattern in self.SUSPICIOUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                # Разрешаем админам
                if not data.get("is_admin", False):
                    logger.warning(
                        f"Подозрительное сообщение от {user_id}: {text[:100]}"
                    )

        # Проверяем одинаковые сообщения
        async with self._lock:
            now = datetime.now()
            cutoff = now - timedelta(seconds=self.window)

            # Очищаем старые
            self._message_history[user_id] = [
                (ts, msg) for ts, msg in self._message_history[user_id]
                if ts > cutoff
            ]

            # Считаем одинаковые
            same_count = sum(
                1 for _, msg in self._message_history[user_id]
                if msg == text
            )

            if same_count >= self.max_same_messages:
                logger.warning(
                    f"Спам от пользователя {user_id}: {same_count + 1} "
                    f"одинаковых сообщений за {self.window}с"
                )
                await event.answer(
                    "⚠️ Не отправляйте одинаковые сообщения многократно."
                )
                return None

            # Добавляем в историю
            self._message_history[user_id].append((now, text))

        return await handler(event, data)
