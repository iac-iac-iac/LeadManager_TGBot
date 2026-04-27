"""
Загрузка лидов админом: сборка FSM «на менеджера» + «по Bitrix24 ID».
"""
from aiogram import Router

# Сначала bitrix_flow (без зависимости от manager), затем manager (импортирует коллбэки Bitrix)
from .bitrix_flow import router as bitrix_router
from .manager_flow import router as manager_router

router = Router()
router.include_router(bitrix_router)
router.include_router(manager_router)
