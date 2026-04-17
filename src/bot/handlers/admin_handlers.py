"""
admin_handlers — УСТАРЕВШИЙ файл-агрегатор.

Код разбит по доменам:
- admin_duplicate_check.py  — проверка дублей
- admin_stats.py            — статистика и экспорт
- admin_pending_users.py    — заявки менеджеров
- admin_cleanup.py          — очистка данных
- admin_manager_stats.py    — статистика по менеджерам

Этот файл оставлен для обратной совместимости.
Роутер собирает все под-роутеры в один для старых вызовов через
    dp.include_router(admin_handlers_router)
"""
from aiogram import Router

from .admin_duplicate_check import router as dup_router
from .admin_stats import router as stats_router
from .admin_pending_users import router as pending_users_router
from .admin_cleanup import router as cleanup_router
from .admin_manager_stats import router as manager_stats_router

router = Router()
router.include_router(dup_router)
router.include_router(stats_router)
router.include_router(pending_users_router)
router.include_router(cleanup_router)
router.include_router(manager_stats_router)
