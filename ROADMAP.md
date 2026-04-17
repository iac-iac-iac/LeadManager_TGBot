# Роадмап развития Lead Telegram Bot

> Текущая версия завершила полный рефакторинг (этапы 1–8).  
> Ниже — следующие шаги в порядке приоритета.

---

## Приоритет 1: Инфраструктура базы данных

### Alembic — управление миграциями
**Проблема**: Текущий `src/database/migrations.py` — самописный runner без rollback-сценариев,  
без autogenerate и без защиты от divergence.

**Что сделать**:
```bash
pip install alembic
alembic init alembic
# В alembic/env.py подключить src.database.models.Base
```
- Перевести все `v1_*..v7_*` скрипты в Alembic-ревизии
- Добавить `alembic upgrade head` в `docker-compose` entrypoint
- Включить `alembic check` в CI для обнаружения незафиксированных изменений моделей

**Выгода**: Безопасные деплои, rollback одной командой, autogenerate diff.

---

### PostgreSQL + SKIP LOCKED — устранение SQLite-bottleneck
**Проблема**: SQLite блокирует таблицу при массовом импорте CSV, конкурентные  
запросы к `leads` ждут.

**Что сделать**:
1. Заменить `DATABASE_URL` на `postgresql+asyncpg://...`
2. В `crud.leads.get_available_leads` добавить `FOR UPDATE SKIP LOCKED`:
```python
select(Lead)
    .where(Lead.status == LeadStatus.UNIQUE, ...)
    .limit(count)
    .with_for_update(skip_locked=True)
```
3. Перевести docker-compose на postgres-сервис

**Выгода**: Конкурентная выдача лидов без гонок; масштабируемость до нескольких воркеров.

---

## Приоритет 2: Кэширование и очередь

### Redis — кэш и очередь импорта
**Проблема**: `import_queue.py` использует asyncio.Queue — не персистентна,  
теряется при перезапуске. Счётчики статистики запрашиваются из БД при каждом вызове.

**Что сделать**:
1. Добавить `redis[asyncio]` / `aioredis` в зависимости
2. Перевести `ImportQueue` на Redis List (`LPUSH` / `BRPOP`)
3. Кэшировать агрегаты (`count_leads_by_segment`) с TTL 60 с

```python
# Пример кэша через redis
cache_key = f"leads_count:{segment}:{city}"
cached = await redis.get(cache_key)
if cached:
    return int(cached)
count = await session.execute(...)
await redis.setex(cache_key, 60, count)
```

**Выгода**: Отказоустойчивая очередь; кратное снижение нагрузки на БД в часы-пик.

---

## Приоритет 3: Observability

### Prometheus + метрики
**Что добавить**:
- `prometheus_client` + `aioprometheus` или middleware для aiogram
- Метрики: `leads_issued_total`, `leads_imported_total`, `bitrix_api_errors_total`,  
  `handler_latency_seconds` (histogram)
- `/metrics` endpoint через aiohttp (отдельный порт, не через бота)

### JSON-структурированное логирование
**Проблема**: `python-json-logger` уже подключён, но часть логов — plain text  
(f-строки в handler'ах без контекстных полей).

**Что сделать**:
- Добавить `extra={"telegram_id": ..., "handler": ...}` в ключевых log-вызовах
- Настроить Loki + Grafana для парсинга JSON-логов

---

## Приоритет 4: Качество кода

### mypy strict + pre-commit
```bash
pip install mypy types-aiofiles
# mypy.ini
[mypy]
strict = true
plugins = sqlalchemy.ext.mypy.plugin
```

**Pre-commit хуки**:
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.9.0
    hooks:
      - id: mypy
```

### Повышение coverage до 60%+
**Текущий coverage**: ~10% (из-за большого кол-ва непокрытых handler'ов).

**Что добавить**:
- Интеграционные тесты для `registration.py` с мок-ботом (aiogram `MockBot`)
- Тесты для `LeadAssignmentService` (assign, assign_and_import)
- Тесты для `DatabaseSessionMiddleware` с реальной in-memory БД

---

## Приоритет 5: CI/CD

### GitHub Actions
```yaml
# .github/workflows/test.yml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/ --cov=src --cov-fail-under=40
      - run: mypy src/ --ignore-missing-imports
```

### Docker multi-stage build
```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY src/ ./src/
CMD ["python", "-m", "src.bot.main"]
```

---

## Приоритет 6: Архитектурные улучшения

### Webhook вместо polling
**Проблема**: Long polling создаёт постоянное TCP-соединение, не масштабируется горизонтально.

**Что сделать**:
```python
# src/bot/main.py
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
import aiohttp.web as web

async def on_startup(bot):
    await bot.set_webhook(f"{WEBHOOK_HOST}/webhook/{BOT_TOKEN}")

app = web.Application()
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook/{token}")
web.run_app(app, port=8080)
```

### Dependency Injection (DI контейнер)
Текущий подход: зависимости передаются через `data["session"]`, `data["bitrix24_client"]`.  
Предлагается: `dishka` или `punq` для явного DI.

```python
# Пример с dishka
from dishka import make_container, provide, Scope, Provider

class AppProvider(Provider):
    @provide(scope=Scope.REQUEST)
    async def get_session(self, factory: async_sessionmaker) -> AsyncSession:
        async with factory() as session:
            yield session
```

**Выгода**: Тестируемость без patch, явные зависимости, нет глобальных состояний.

---

## Быстрые победы (1–2 дня)

| Задача | Усилие | Выгода |
|--------|--------|--------|
| `alembic init` + перенести миграции | 4 ч | Безопасные деплои |
| pre-commit + ruff | 1 ч | Автоматический lint в CI |
| `FOR UPDATE SKIP LOCKED` в `get_available_leads` | 2 ч | Нет race condition при конкурентной выдаче |
| Redis для ImportQueue | 4 ч | Персистентная очередь |
| Prometheus middleware | 3 ч | Мониторинг в реальном времени |
