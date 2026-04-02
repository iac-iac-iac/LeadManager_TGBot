"""
Очередь импорта лидов в Bitrix24

Предназначена для:
- Последовательного импорта лидов (чтобы не блокировать SQLite)
- Обработки массовых загрузок в фоне
- Уведомления пользователей о завершении импорта
- Проверки дублей в фоне
"""
import asyncio
from typing import Optional, Callable, Awaitable, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import crud
from src.bitrix24.leads import import_assigned_leads
from src.bitrix24.client import get_bitrix24_client
from src.bitrix24.duplicates import DuplicateChecker
from src.config import get_config
from src.logger import get_logger

logger = get_logger(__name__)


class ImportTask:
    """
    Задача импорта лидов

    Attributes:
        lead_ids: Список ID лидов для импорта
        manager_id: Telegram ID менеджера
        bitrix_user_id: Bitrix24 ID менеджера
        callback: Функция обратного вызова (уведомление о завершении)
    """

    def __init__(
        self,
        lead_ids: List[int],
        manager_id: str,
        bitrix_user_id: Optional[int],
        callback: Optional[Callable[[Dict[str, int]], Awaitable[None]]] = None
    ):
        self.lead_ids = lead_ids
        self.manager_id = manager_id
        self.bitrix_user_id = bitrix_user_id
        self.callback = callback


class DuplicateCheckTask:
    """
    Задача проверки дублей

    Attributes:
        lead_ids: Список ID лидов для проверки
        callback: Функция обратного вызова (уведомление о завершении)
    """

    def __init__(
        self,
        lead_ids: List[int],
        callback: Optional[Callable[[Dict[str, int]], Awaitable[None]]] = None
    ):
        self.lead_ids = lead_ids
        self.callback = callback


class BitrixImportQueue:
    """
    Очередь импорта лидов в Bitrix24
    
    Особенности:
    - Один worker обрабатывает импорты последовательно
    - Не блокирует основную базу данных
    - Уведомляет о завершении импорта
    """
    
    def __init__(self, max_queue_size: int = 100):
        """
        Инициализация очереди
        
        Args:
            max_queue_size: Максимальный размер очереди
        """
        self._queue: asyncio.Queue[ImportTask] = asyncio.Queue(maxsize=max_queue_size)
        self._worker_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._current_task: Optional[ImportTask] = None
        
        # Статистика
        self._stats = {
            "processed": 0,
            "failed": 0,
            "total_leads": 0
        }
    
    async def start_worker(self):
        """Запуск обработчика очереди"""
        if self._worker_task is not None:
            logger.warning("Worker уже запущен")
            return
        
        self._is_running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("🔄 Очередь импорта запущена")
    
    async def stop(self):
        """Остановка обработчика очереди"""
        self._is_running = False
        
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        logger.info("⏹️ Очередь импорта остановлена")
    
    async def add_duplicate_check(
        self,
        lead_ids: List[int],
        callback: Optional[Callable[[Dict[str, int]], Awaitable[None]]] = None
    ) -> bool:
        """
        Добавление проверки дублей в очередь

        Args:
            lead_ids: Список ID лидов для проверки
            callback: Функция обратного вызова

        Returns:
            True если успешно добавлено, False если очередь переполнена
        """
        if not self._is_running:
            logger.error("Очередь не запущена")
            return False

        try:
            task = DuplicateCheckTask(lead_ids, callback)
            await asyncio.wait_for(self._queue.put(task), timeout=5.0)

            queue_size = self._queue.qsize()
            logger.info(f"🔍 Проверка дублей добавлена в очередь ({queue_size} в очереди)")

            return True

        except asyncio.TimeoutError:
            logger.error("❌ Очередь переполнена, проверка отклонена")
            return False

    async def add_import(
        self,
        lead_ids: List[int],
        manager_id: str,
        bitrix_user_id: Optional[int],
        callback: Optional[Callable[[Dict[str, int]], Awaitable[None]]] = None
    ) -> bool:
        """
        Добавление импорта в очередь

        Args:
            lead_ids: Список ID лидов
            manager_id: Telegram ID менеджера
            bitrix_user_id: Bitrix24 ID менеджера
            callback: Функция обратного вызова

        Returns:
            True если успешно добавлено, False если очередь переполнена
        """
        if not self._is_running:
            logger.error("Очередь не запущена")
            return False
        
        try:
            task = ImportTask(lead_ids, manager_id, bitrix_user_id, callback)
            await asyncio.wait_for(self._queue.put(task), timeout=5.0)
            
            queue_size = self._queue.qsize()
            logger.info(f"📦 Импорт добавлен в очередь ({queue_size} в очереди)")
            
            return True
            
        except asyncio.TimeoutError:
            logger.error("❌ Очередь переполнена, импорт отклонён")
            return False
    
    async def _worker(self):
        """
        Обработчик очереди
        
        Выполняет импорты последовательно, по одному за раз
        """
        logger.info("🔄 Worker очереди запущен")
        
        while self._is_running:
            try:
                # Получаем задачу из очереди
                self._current_task = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )
                
                if self._current_task is None:
                    continue

                # Проверяем тип задачи
                if isinstance(self._current_task, DuplicateCheckTask):
                    # Проверка дублей
                    logger.info(f"🔍 Начало проверки {len(self._current_task.lead_ids)} лидов на дубли")
                    stats = await self._process_duplicate_check(self._current_task)
                else:
                    # Импорт лидов
                    logger.info(
                        f"🚀 Начало импорта {len(self._current_task.lead_ids)} лидов "
                        f"для менеджера {self._current_task.manager_id}"
                    )
                    stats = await self._process_import(self._current_task)

                # Обновляем статистику
                self._stats["processed"] += 1
                if hasattr(self._current_task, 'lead_ids'):
                    self._stats["total_leads"] += len(self._current_task.lead_ids)

                if stats.get("errors", 0) > 0:
                    self._stats["failed"] += 1

                logger.info(
                    f"✅ Задача завершена: {stats.get('imported', 0)} успешно, "
                    f"{stats.get('errors', 0)} ошибок"
                )

                # Вызываем callback если есть
                if self._current_task.callback:
                    try:
                        await self._current_task.callback(stats)
                    except Exception as e:
                        logger.error(f"Ошибка callback: {type(e).__name__}: {e}")

                # Помечаем задачу как выполненную
                self._queue.task_done()
                self._current_task = None
                
            except asyncio.TimeoutError:
                # Нет задач в очереди
                continue
            except asyncio.CancelledError:
                logger.info("⏹️ Worker остановлен по запросу")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в worker: {type(e).__name__}: {e}")
                if self._current_task:
                    self._queue.task_done()
                    self._current_task = None
    
    async def _process_import(self, task: ImportTask) -> Dict[str, int]:
        """
        Обработка одной задачи импорта
        
        Args:
            task: Задача импорта
            
        Returns:
            Статистика импорта
        """
        # Создаём новую сессию для импорта (чтобы не блокировать основную)
        from src.database.models import DatabaseManager
        import asyncio

        # Получаем путь к базе из конфига
        config = get_config()
        db_path = config.database_path

        # Создаём временную сессию с retry логикой
        db_manager = DatabaseManager(db_path)

        for attempt in range(5):  # 5 попыток при блокировке
            try:
                async with db_manager.async_session_factory() as session:
                    try:
                        # Назначаем лиды менеджеру (если ещё не назначены)
                        await crud.assign_leads_to_manager(
                            session,
                            task.lead_ids,
                            task.manager_id,
                            loaded_by_admin=True
                        )

                        # Получаем Bitrix24 клиента
                        bitrix_client = get_bitrix24_client(config.bitrix24.webhook_url)

                        # Импортируем в Bitrix24
                        stats = await import_assigned_leads(
                            session,
                            bitrix_client,
                            task.manager_id,
                            task.bitrix_user_id
                        )

                        # Коммитим транзакцию
                        await session.commit()

                        return stats

                    except Exception as e:
                        await session.rollback()
                        raise e
                    finally:
                        await db_manager.engine.dispose()

            except Exception as e:
                if "database is locked" in str(e) and attempt < 4:
                    wait_time = 0.5 * (2 ** attempt)  # 0.5с, 1с, 2с, 4с, 8с
                    logger.warning(f"БД заблокирована, попытка {attempt+1}/5 через {wait_time}с")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ Ошибка импорта: {type(e).__name__}: {e}")
                    return {"imported": 0, "errors": 1}

        return {"imported": 0, "errors": 1}

    async def _process_duplicate_check(self, task: 'DuplicateCheckTask') -> Dict[str, int]:
        """
        Обработка одной задачи проверки дублей
        Используем retry логику при блокировке БД

        Args:
            task: Задача проверки дублей

        Returns:
            Статистика проверки
        """
        # Создаём новую сессию для проверки (чтобы не блокировать основную)
        from src.database.models import DatabaseManager
        import asyncio

        # Получаем путь к базе из конфига
        config = get_config()
        db_path = config.database_path

        # Создаём временную сессию с retry логикой
        db_manager = DatabaseManager(db_path)

        for attempt in range(5):  # 5 попыток при блокировке
            try:
                async with db_manager.async_session_factory() as session:
                    try:
                        # Создаём checker и запускаем проверку
                        bitrix_client = get_bitrix24_client(config.bitrix24.webhook_url)
                        checker = DuplicateChecker(bitrix_client)

                        stats = await checker.check_leads_batch(session, task.lead_ids)

                        # Коммитим транзакцию
                        await session.commit()

                        return stats

                    except Exception as e:
                        await session.rollback()
                        raise e
                    finally:
                        await db_manager.engine.dispose()

            except Exception as e:
                if "database is locked" in str(e) and attempt < 4:
                    wait_time = 0.5 * (2 ** attempt)  # 0.5с, 1с, 2с, 4с, 8с
                    logger.warning(f"БД заблокирована, попытка {attempt+1}/5 через {wait_time}с")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ Ошибка проверки дублей: {type(e).__name__}: {e}")
                    return {"duplicates": 0, "unique": 0, "errors": 1}

        return {"duplicates": 0, "unique": 0, "errors": 1}

    def get_stats(self) -> Dict[str, Any]:
        """
        Получение статистики очереди
        
        Returns:
            Статистика: {processed, failed, total_leads, queue_size}
        """
        return {
            **self._stats,
            "queue_size": self._queue.qsize(),
            "is_running": self._is_running,
            "current_task": len(self._current_task.lead_ids) if self._current_task else None
        }
    
    async def get_queue_status(self) -> str:
        """
        Получение статуса очереди для отображения
        
        Returns:
            Строка со статусом
        """
        stats = self.get_stats()
        
        if not stats["is_running"]:
            return "⏹️ Очередь остановлена"
        
        status = f"🔄 Очередь импорта\n\n"
        status += f"📊 Обработано: {stats['processed']}\n"
        status += f"✅ Успешно: {stats['total_leads']} лидов\n"
        status += f"⚠️ Ошибки: {stats['failed']}\n"
        
        if stats["queue_size"] > 0:
            status += f"\n📦 В очереди: {stats['queue_size']}\n"
        
        if stats["current_task"]:
            status += f"\n⏳ Импортируется: {stats['current_task']} лидов"
        
        return status


# Singleton экземпляр очереди
_import_queue: Optional[BitrixImportQueue] = None


def get_import_queue() -> BitrixImportQueue:
    """
    Получение экземпляра очереди
    
    Returns:
        Экземпляр BitrixImportQueue
    """
    global _import_queue
    if _import_queue is None:
        _import_queue = BitrixImportQueue()
    return _import_queue
