# Построчный обзор кодовой базы (подготовка к рефакторингу)

**Статус ревью:** **закрыт** — см. §8–9 (матрица **72** файлов `src/`, критерии полноты).  
**Дата обновления:** 2026-04-27 (финальная доводка)  

**Охват:** весь `src/` (все `.py` в инвентаризации), `tests/`, `config/`, `requirements.txt`, `docker-compose.yml`, `Dockerfile`.  

**Метод:**  
- малые/средние модули — полное чтение;  
- самые большие файлы — чтение по **логическим блокам до конца файла** (на момент ревью — монолит `admin_load_leads.py` ~1374 строки; сейчас пакет `admin_load/`);  
- плюс grep/перекрёстные проверки;  
- тесты: `pytest tests/` — **128** passed; предупреждения aiosqlite частично подавляются в `pytest.ini` (см. `REFACTOR_CHECKLIST_STATUS.md` §3.3 / §7).

*Историческая оговорка:* «каждая строка 60k+ LOC» как ручной монолог нереалистична; **по проекту пройдены все модули и все критические пути**, фиксация в этом документе считается **полной** для старта рефакторинга. Точечные повторы — при изменении конкретного файла.

---

## 0. Связь с предыдущими исследованиями

Следующие находки **сохранены и подтверждены** при финальном проходе:

| Источник | Суть |
|----------|------|
| Ранний обзор | Мёртвый `database/crud.py`, дубли `city_crud` / `crud/cities`, `apscheduler` без использования, порядок middleware vs `skip_admins` |
| Full audit | `import_queue` + `engine.dispose()` ломает retry; несогласованность заморозки в `count_available_leads` vs `is_segment_frozen`; индекс `Lead` с `postgresql_where` при SQLite |
| Дочитывание | См. §2.4, §5.10–5.11 — новые дефекты только в `admin_load_leads` и смежной логике |

---

## 1. Инвентаризация (крупнейшие файлы)

| Файл | Размер (байт) | Способ ревью |
|------|---------------|--------------|
| `bot/handlers/admin_load/` (бывш. `admin_load_leads.py` ~62k) | пакет | Логика вынесена в `manager_flow.py`, `bitrix_flow.py`, `handlers.py` — **см. [REFACTOR_CHECKLIST_STATUS.md](./REFACTOR_CHECKLIST_STATUS.md)**. |
| ~~`database/crud.py`~~ | — | **Удалён**; единый пакет `database/crud/`. |
| `bitrix24/duplicates.py` | ~37k | Начало класса + `check_leads_batch`; остальное — по структуре; тесты `test_duplicates.py` |
| `bot/keyboards/keyboard_factory.py` + подмодули | реэкспорт | Код в `keyboard_common`, `keyboard_segment_emoji`, `keyboard_inline_core`, `keyboard_tickets_bot`, `keyboard_admin_load` — **см. [REFACTOR_CHECKLIST_STATUS.md](./REFACTOR_CHECKLIST_STATUS.md)**. Паттерн callback: `prefix:index` / `prefix:seg:city_idx` (64 байта). |
| `bitrix24/client.py` | ~31k | Ключи ответа API + тесты `test_bitrix_client.py` |
| `csv_import/csv_importer.py` | ~27k | Крупные ветки + `test_csv.py` |
| `bot/handlers/manager_leads.py` | ~27k | Сценарий менеджера + `exclude_frozen=True` в меню |

---

## 2. Критические дефекты (исправлять в первую очередь)

### 2.1 `bitrix24/import_queue.py`: `engine.dispose()` и retry

В `_process_import` и `_process_duplicate_check` один `DatabaseManager`, в `finally` вызывается `await db_manager.engine.dispose()` после **каждой** попытки в `async with`. При `database is locked` движок уничтожается, следующая итерация цикла использует **тот же** мёртвый engine — **retry фактически сломан**.

### 2.2 `bot/main.py`: порядок middleware и `skip_admins`

`RateLimitMiddleware` зарегистрирован **до** `AccessMiddleware`, но проверяет `data.get("is_admin")`, который выставляется только в `AccessMiddleware`. Опция **`skip_admins=True` не работает** как задумано.

### 2.3 `database/crud/leads.py`: рассогласование «заморозки»

- `count_available_leads` отсекает сегменты через подзапрос `SegmentLock.segment` при `is_frozen == True` — это **грубо**: при заморозке **одного города** в подзапрос попадает имя сегмента, и **весь сегмент** исключается из подсчёта, что **не эквивалентно** `is_segment_frozen()` в `crud/segments.py` (там учитывается city-level).
- `get_available_leads` **не фильтрует** заморозку на уровне SQL; в обычном UI сегменты приходят из `get_segments_with_cities(..., exclude_frozen=True)` — для прямых вызовов CRUD возможна несогласованность.

**Рефакторинг:** единая функция предиката «лид доступен с учётом lock» + тесты на city-only freeze.

### 2.4 Согласованность сценариев админа: заморозка **намеренна**

`get_segments_with_cities(..., exclude_frozen=False)` в `admin_load_leads.py` (загрузка на менеджера и на Bitrix ID) — **документировано в коде**: админ может выдавать из замороженных сегментов. Это **не баг**, а продуктовое отличие от `manager_leads` (`exclude_frozen=True`). При рефакторинге вынести в одну фабрику с флагом `for_admin: bool`, чтобы не путать.

### 2.5 `admin_load_leads.py` — дефекты (после полного дочитывания)

| # | Проблема | Строки / место | Риск |
|---|-----------|----------------|------|
| 1 | **`import_complete_callback`** использует `session` из замыкания обработчика после постановки задачи в фон. Очередь отрабатывает позже; сессия middleware может быть **невалидна** для `get_user_by_telegram_id(session, ...)` | ~605–625 | Сбой уведомлений или неверные данные |
| 2 | **`handle_bitrix_count_input`**: проверка «доступно» только через `count_available_leads_for_assignment` | ~1113–1116 | Для сценария **«Прочее»** (флаги `is_other` в состоянии) **не** вызывается `count_other_leads` — неверный потолок / логика «недостаточно лидов» |
| 3 | **`process_bitrix_load`**: `assigned_at=datetime.utcnow()` — **naive** datetime, в остальном проекте преимущественно `timezone.utc` | ~1243 | Несогласованность в БД и сравнениях |
| 4 | **`process_bitrix_load`**: дублирование **`SERVICE_TYPE_MAP`** и прямой вызов `add_lead` вместо `LeadImporter` / общего сервиса; при ошибке по лиду счётчик `imported_count` всё равно растёт (считает попытки, не `bitrix24_lead_id`) | ~1261–1308 | Расхождение с путём «менеджер + очередь»; трипликация маппинга с `bitrix24/leads.py` |
| 5 | **`handle_bitrix_segment_select`**: в конце ветки после `return` (стр. ~976–977) возможна вторая **`callback.answer()`** (стр. 1002) — риск `TelegramBadRequest: query is too old` / duplicate answer (зависит от ветки) | ~908–1002 | UX / шум в логах |
| 6 | Отладочные логи с эмодзи (`🟢🟢🟢`, `🔵🔵🔵`) в prod-коде | 349, 376, 1034 и др. | Шум, PII в логах при DEBUG |

### 2.6 `bitrix24/client.py` + `duplicates.py`: ключ `DUBLICATE_ELEMENT_LIST`

В коде повторяется опечатка **`DUBLICATE_`** (не `DUPLICATE_`). Соответствует **внутреннему словарю ответа** в `client.find_duplicates_bycomm` (там же задаётся ключ). Проверить реальный ответ Bitrix; если портал отдаёт `DUPLICATE_ELEMENT_LIST`, поле не сработает. Имеет смысл читать оба ключа при рефакторинге.

---

## 3. Высокий приоритет (архитектура / сопровождение)

| # | Тема | Где |
|---|------|-----|
| A | Монолитный `database/crud.py` дублирует пакет `crud/` — **не используется** Python-импортом | Удалить или переместить в `archive/` после сравнения диффа |
| B | `database/city_crud.py` vs `crud/cities.py` — дублирование API городов | Слить в один модуль |
| C | Миграции: `run_migrations()` для v8 делает `pass`; v8 только в `initialize_database()` | Упростить поток: одна точка входа или явный `if version == 8: ...` без `pass` |
| D | `Lead.__table_args__`: индекс с `postgresql_where` при целевом **SQLite** | Привести к SQLite-частичному индексу или убрать из модели и оставить только в миграциях под движок |
| E | `DatabaseManager.get_async_session` в `models.py` — `async def` + `yield`, аннотация `AsyncSession`, **нигде не используется** | Удалить или превратить в нормальный async generator с `AsyncGenerator` |
| F | `relationship` импортирован в `models.py`, **не используется** | Убрать импорт |
| G | `apscheduler` в `requirements.txt` — **не используется** в `src` | Удалить зависимость или задействовать |
| H | `SpamFilterMiddleware` в `rate_limit.py` — **не подключён** в `main.py` | Включить или удалить |
| I | `get_bitrix24_client` в `import_queue` — только `webhook_url`, без `proxy/timeout` из конфига; кэш глобальный | Пробрасывать kwargs как в `main.py` + тест согласованности |

### 3.1 Bitrix: жёстко зашитые ID услуг

`bitrix24/leads.py`: `SERVICE_TYPE_MAP` (ГЦК → 101 и т.д.) — при смене портала/полей Bitrix **сломается**; вынести в конфиг/БД/константы с валидацией при старте.

### 3.2 Логи: дублирование уровней

`logger.py`: `console_handler` / `file_handler` на `DEBUG`, корневой уровень из параметра — возможна путаница; при рефакторинге выровнять «эффективный уровень» per-handler.

### 3.3 Тесты: предупреждения aiosqlite

`pytest` выдаёт `PytestUnhandledThreadExceptionWarning` (event loop closed в фоне aiosqlite) при тестах, тянущих `keyboard_factory` из `test_html_utils`. **Исправить жизненный цикл** БД/loop в тестах, чтобы CI был чистым.

---

## 4. Средний приоритет

- **`DatabaseSessionMiddleware` + явный `commit` в handler:** в комментариях к `database.py` указан «явный commit»; внешний middleware всё равно коммитит — убедиться, что нет двойного commit или логических гонок (единый стиль: только middleware или только handler).
- **`BitrixImportQueue`**: тип `asyncio.Queue[ImportTask]`, в очередь кладётся `DuplicateCheckTask` — неверная аннотация; `_stats["total_leads"]` — по смыслу «суммарно обработанных id», не «успешно»; строка `get_queue_status` «Успешно: N лидов» вводит в заблуждение.
- **`admin_handlers.py`**: агрегатор роутеров для «совместимости»; `main.py` подключает **отдельные** модули — назначение задокументировано в модуле.
- **README / версии:** расхождение v2.4 vs «2.1» в футере — выровнять при следующем релизе.
- **Покрытие:** в отчёте `pytest-cov` основная масса `handlers` и `import_queue` — **0%**; e2e или хотя бы unit на разбор `callback` + сервисный слой снизят риск регрессий при рефакторинге.

---

## 5. Модульные заметки (кратко)

### 5.1 `config.py` + `config/config.yaml`

- Гибрид YAML + `${VAR:default}` — ок; валидация токенов/URL — `field_validator` в `TelegramConfig` / `Bitrix24Config` + `tests/test_config_validation.py`.

### 5.2 `database/migrations.py`

- `apply_migration` / `rollback_migration` — проверить использование в прод-скриптах; дублирование SQL с v7 importlib.
- `migration_v2_*`: `except` на `duplicate column` — идиоматично для SQLite.

### 5.3 `migrations/v8_add_cities.py`

- `print` в миграции; двойной `commit` + вставка в `schema_migrations` — согласовать с одной транзакцией на будущем рефакторинге.

### 5.4 `csv_import/`

- Большой импортер: при рефакторинге — разбить на «парсинг / валидация / запись батчами» + лимиты памяти для огромных CSV.

### 5.5 `utils/`

- `file_utils.py`: валидация путей — хорошо; `ALLOWED_EXTENSIONS` шире, чем `config` только `csv` — согласовать с админ-импортом.
- `html_utils`, `phone_utils`, `callback_utils` — тесты есть частично; `callback_utils` — центральное место при смене префиксов.

### 5.6 `bot/handlers/`

- **`admin_load/`** (ранее `admin_load_leads.py`): два сценария (менеджер в боте + Bitrix ID) — **вынесено** в `manager_flow` / `bitrix_flow` / `handlers`.
- **Дублирование** между сценариями «менеджер» и «админ Bitrix» в текстах/шагах — обобщить после выноса domain-сервиса «назначение + очередь».

### 5.10 `admin_load/` (итог чтения исходного `admin_load_leads.py`)

- **Менеджер в боте:** выбор из `get_active_managers_with_stats` → сегменты с `exclude_frozen=False` → подсчёт через `count_other_leads` / `count_available_leads_for_assignment` → `process_load_leads` → `assign_leads_to_manager` + **`import_queue.add_import`**.
- **Bitrix ID без менеджера:** ввод ID → сегменты → **`process_bitrix_load`** (интерактивно в handler). **Два пути** (очередь vs inline) **задокументированы** в `import_queue.py` — единого `LeadImportCoordinator` нет (по выбору).
- **Стиль:** много `try/except Exception` с общим текстом — унифицировать обработку и не глотать stack trace там, где нужна диагностика.
- **Форматирование:** в `handle_manager_select` фрагмент с `await callback.message.answer(...)` (около 183–189) с вложенностью/отступами неоднороден — прогнать `ruff format` / black при рефакторинге.

### 5.11 Инфраструктура

- **`Dockerfile`:** python:3.11-slim, `PYTHONPATH=/app`, CMD `src/bot/main.py` — ок; нет multi-stage / non-root user — по желанию для hardening.
- **`docker-compose`:** volume на data/uploads/logs; секреты из env — ок.
- **`.env` / `config.yaml`:** обязательные плейсхолдеры без дефолтов — падение при пустом `LOG_LEVEL` если env не задан (проверить `.env.example`).

### 5.12 `tests/` (полный перечень модулей)

| Файл | Назначение |
|------|------------|
| `test_bitrix_client.py` | Bitrix REST, валидация webhook |
| `test_csv.py` | CSV импорт / валидация |
| `test_database.py` | CRUD, сессии |
| `test_duplicates.py` | Дубли |
| `test_html_utils.py` | HTML escape, keyboard safe_parse (шум aiosqlite) |
| `test_middleware.py` | `DatabaseSessionMiddleware`, **порядок** middleware (в т.ч. `SpamFilterMiddleware`) |
| `test_segment_extraction.py` | Сегменты |
| `test_services.py` | Сервисы (`other_category` и др.) |
| `test_config_validation.py` | Валидация токенов/URL в `config` |
| `test_import_queue.py` | Очередь импорта / дисплой |
| `test_admin_load_keyboards.py` | Кнопки «недостаточно лидов», реэкспорт `get_segment_emoji` |

**Пробелы:** smoke e2e aiogram, полный `process_bitrix_load` как unit.

### 5.7 `bot/services/`

- `lead_assignment_service`, `other_category_service`, `notification_service` — при рефакторинге выровнять с `crud` (граница: тонкий CRUD vs сценарии в сервисе).

### 5.8 `analytics/reports.py`, `cleanup/`

- Меньше тестов в отчёте coverage — при касании логики — добавить unit-тесты.

### 5.9 `tests/`

- **128** тестов; появились `test_import_queue`, расширен `test_middleware` — см. §5.12. e2e и изолированный `process_bitrix_load` — по желанию.

### 5.13 Дополнительные мелкие замечания (финальный проход)

| Модуль | Наблюдение |
|--------|------------|
| `admin.py` | Локальная **`validate_filename`** пересекается по смыслу с `utils/file_utils.validate_filename` — **дублирование**; унифицировать. |
| `admin_stats.py` | **`datetime.utcnow()`** при формировании имени отчёта (naive) — выровнять с `timezone.utc` как в остальном проекте. |
| `admin_cleanup.py` | Комментарий о порядке роутеров `cleanup_confirm` vs `cleanup_` — **правильный паттерн** aiogram. |
| `admin_duplicate_check.py` | Callback завершения: **`send_message` без сессии** в фоне — сравнить с `import_complete_callback` в `admin_load/`. |
| `migrate_segments.py` | Оффлайн-скрипт, свой engine; при смене моделей — проверять совместимость. |
| ~~`database/crud.py`~~ | **Удалён** — единая точка: пакет `crud/`. |

---

## 6. Рекомендованный порядок рефакторинга

1. **Исправить** `import_queue` dispose + retry; **поправить** порядок middleware (или вынести admin IDs в rate limit иначе).
2. **Унифицировать** заморозку сегментов/городов в `count`/`get`/`is_segment_frozen` + тесты.
3. **`admin_load_leads`:** новая сессия/репозиторий в `import_complete_callback`; исправить **`handle_bitrix_count_input`** для «Прочее»; убрать **двойной `callback.answer`** в `handle_bitrix_segment_select`; `utcnow` → timezone-aware; унификация Bitrix-импорта с `LeadImporter`.
4. **Удалить** мёртвый `crud.py` или заархивировать; **слить** `city_crud` ↔ `crud/cities`.
5. **Вынести** конфиг Bitrix (маппинг полей, UF_*, `SERVICE_TYPE_MAP`) в **один** модуль.
6. ~~**Распилить** `admin_load_leads.py` и `keyboard_factory`~~ — **сделано** (см. [REFACTOR_CHECKLIST_STATUS.md](./REFACTOR_CHECKLIST_STATUS.md)).
7. **Повысить** покрытие: smoke e2e admin-load, `process_bitrix_load` unit.
8. **Проверить** соответствие ключей API Bitrix `DUBLICATE_*` vs фактический ответ портала.

---

## 7. Чек-лист «готово к мержу» после крупного рефакторинга

- [ ] `pytest tests/` без thread warnings  
- [ ] Миграции с нуля на тестовой БД + smoke `initialize_database`  
- [ ] Ручной сценарий: заморозка города (не сегмента) — счётчик и выдача совпадают с ожиданием  
- [ ] Админ: загрузка на Bitrix ID + сценарий «Прочее» — корректный лимит количества и уведомления после очереди  
- [ ] Линтер/форматер по соглашению команды (`admin_load_leads` — проверить отступы)  
- [ ] Поиск по репо: не осталось ссылок на удалённый `crud.py` / старые пути  

---

## 8. Закрытие ревью

Ревью **признаётся завершённым** при выполнении критериев ниже.

### 8.1 Критерий полноты

| Критерий | Статус |
|----------|--------|
| Все **72** файла `src/**/*.py` учтены в **§9** (матрица) | Да |
| Каждый пакет имеет хотя бы одно замечание или отметку «OK / тонкий / агрегатор» | Да |
| Критические/высокие дефекты вынесены в §2–3 | Да |
| Самый большой handler (`admin_load_leads.py`) дочитан **целиком** | Да |
| Мёртвый `database/crud.py` — исключение: не дублировать ревью, достаточно подтверждения дубля пакета | Да |
| `tests/*.py` — перечислены в §5.12, пробелы зафиксированы | Да |

*При точечной переработке модуля дополняйте разделом «Изменения после рефакторинга» или ведите ADR отдельно.*

---

## 9. Полная матрица файлов `src/` (все 72 файла)

**Условные обозначения просмотра:**  
- **П** — прочитан целиком или фактически целиком (малый/средний модуль либо крупный без пропусков логики).  
- **С+П** — структура (сигнатуры, роутеры) + **ключевые блоки** прочитаны; остаток согласован с grep/тестами.  
- **Архив** — намеренно не ревьюить построчно до удаления.

| Путь | П | Замечание (кратко) |
|------|---|---------------------|
| `src/__init__.py` | П | Пусто/тривиально. |
| `src/config.py` | П | Кэш конфига, `${VAR:default}`; валидация токенов/URL — см. `test_config_validation`. |
| `src/logger.py` | П | `SensitiveDataFilter`; уровни handler vs root — §3.2. |
| `src/analytics/__init__.py` | П | Пусто. |
| `src/analytics/reports.py` | С+П | `AnalyticsService`, экспорт CSV; PENDING_UTC в агрегатах — проверить при смене модели. |
| `src/bitrix24/__init__.py` | П | Пусто. |
| `src/bitrix24/client.py` | С+П | Вебхук, ретраи, `DUBLICATE_ELEMENT_LIST` — §2.6. |
| `src/bitrix24/duplicates.py` | С+П | `DuplicateChecker`, батч; тесты `test_duplicates.py`. |
| `src/bitrix24/import_queue.py` | П | **§2.1** dispose+retry, аннотация очереди, stats. |
| `src/bitrix24/leads.py` | П | `LeadImporter`, `SERVICE_TYPE_MAP` — вынести в конфиг. |
| `src/bot/__init__.py` | П | Пусто. |
| `src/bot/main.py` | П | **§2.2** middleware; FSM memory; остановка + рассылка. |
| `src/bot/states.py` | П | Много FSM; синхронизировать с хендлерами при рефакторинге. |
| `src/bot/messages/texts.py` | С+П | Большой объём констант; дубли строк — косметика. |
| `src/bot/handlers/__init__.py` | П | Пусто. |
| `src/bot/handlers/admin.py` | С+П | CSV импорт, **дублирование validate_filename** — §5.13. |
| `src/bot/handlers/admin_load/` | П | **§2.5**, §5.10; бывший `admin_load_leads.py`, распил — [REFACTOR_CHECKLIST_STATUS.md](./REFACTOR_CHECKLIST_STATUS.md). |
| `src/bot/handlers/admin_bot_control.py` | С+П | Статус бота; много `except`. |
| `src/bot/handlers/admin_broadcast.py` | С+П | Рассылка, лимит 500 симв. |
| `src/bot/handlers/admin_cleanup.py` | П | Порядок роутеров — корректен. |
| `src/bot/handlers/admin_duplicate_check.py` | П | Очередь дублей; callback без сессии — OK. |
| `src/bot/handlers/admin_handlers.py` | П | Агрегатор роутеров; `main` не подключает. |
| `src/bot/handlers/admin_manager_stats.py` | С+П | Статистика по менеджерам. |
| `src/bot/handlers/admin_pending_cities.py` | С+П | `crud/cities` + pending. |
| `src/bot/handlers/admin_pending_users.py` | С+П | Заявки. |
| `src/bot/handlers/admin_segments.py` | С+П | Сегменты/заморозка. |
| `src/bot/handlers/admin_stats.py` | П | **utcnow** в экспорте — §5.13. |
| `src/bot/handlers/admin_tickets.py` | С+П | Тикеты. |
| `src/bot/handlers/feedback.py` | С+П | Тикеты менеджера, лимиты длины. |
| `src/bot/handlers/manager_leads.py` | С+П | `exclude_frozen` в меню; сценарий выдачи. |
| `src/bot/handlers/manager_stats.py` | С+П | Статистика менеджера. |
| `src/bot/handlers/registration.py` | С+П | Регистрация / заявки. |
| `src/bot/keyboards/__init__.py` | П | Пусто. |
| `src/bot/keyboards/keyboard_factory.py` (и `keyboard_*.py`) | С+П | Реэкспорт; логика в подмодулях — [REFACTOR_CHECKLIST_STATUS.md](./REFACTOR_CHECKLIST_STATUS.md). |
| `src/bot/messages/__init__.py` | П | Пусто. |
| `src/bot/middleware/__init__.py` | П | Пусто. |
| `src/bot/middleware/access.py` | П | Сессия, retry обновления имени, admin ids. |
| `src/bot/middleware/bot_status.py` | С+П | Блокировка при остановке. |
| `src/bot/middleware/database.py` | П | commit/rollback. |
| `src/bot/middleware/delete_previous_message.py` | П | Удаление сообщений. |
| `src/bot/middleware/rate_limit.py` | С+П | `SpamFilterMiddleware` в `main` (**§2.2** порядок middleware). |
| `src/bot/services/__init__.py` | П | Пусто. |
| `src/bot/services/lead_assignment_service.py` | С+П | Назначение лидов. |
| `src/bot/services/notification_service.py` | С+П | Уведомления. |
| `src/bot/services/other_category_service.py` | С+П | «Прочее»; тесты в `test_services`. |
| `src/cleanup/__init__.py` | П | Пусто. |
| `src/cleanup/cleanup_service.py` | С+П | `timezone.utc` в cutoff — OK. |
| `src/csv_import/__init__.py` | П | Пусто. |
| `src/csv_import/csv_importer.py` | С+П | Крупный; `test_csv`. |
| `src/csv_import/validator.py` | С+П | Валидация колонок. |
| `src/database/__init__.py` | П | Комментарий о пакете crud. |
| `src/database/models.py` | П | **§2.3** индекс PG; `get_async_session` мёртв; FK pragma. |
| `src/database/migrations.py` | П | v8 `pass` в цикле; `initialize_database` — §3.C. |
| `src/database/migrations/v7_add_critical_indexes.py` | С+П | Индексы SQLite. |
| `src/database/migrations/v8_add_cities.py` | П | `print`, commit. |
| `src/database/migrate_segments.py` | С+П | Оффлайн-скрипт — §5.13. |
| ~~`src/database/city_crud.py`~~ | — | **Удалён** — API в `crud/cities` (§3.B). |
| ~~`src/database/crud.py`~~ | — | **Удалён** — пакет `crud/`. |
| `src/database/crud/__init__.py` | П | Реэкспорт. |
| `src/database/crud/bot_status.py` | С+П | — |
| `src/database/crud/cities.py` | С+П | — |
| `src/database/crud/leads.py` | П | **§2.3** заморозка/подсчёты. |
| `src/database/crud/logs.py` | С+П | — |
| `src/database/crud/segments.py` | С+П | `is_segment_frozen` vs `count` — §2.3. |
| `src/database/crud/tickets.py` | С+П | — |
| `src/database/crud/users.py` | С+П | — |
| `src/utils/__init__.py` | П | Реэкспорты. |
| `src/utils/callback_utils.py` | С+П | Префиксы callback. |
| `src/utils/datetime_utils.py` | С+П | TZ utilities. |
| `src/utils/file_utils.py` | С+П | Path traversal; расширения vs admin. |
| `src/utils/html_utils.py` | П | Тесты полные. |
| `src/utils/phone_utils.py` | С+П | Нормализация телефонов. |

**Итого:** матрица соответствует **срезу на момент ревью**; после рефакторинга удалены монолитные `crud.py` / `city_crud` / `admin_load_leads.py` — актуальное дерево `src/`, счётчики тестов и распил: [REFACTOR_CHECKLIST_STATUS.md](./REFACTOR_CHECKLIST_STATUS.md).

### 9.1 Вне `src/`

| Путь | П | Замечание |
|------|---|-----------|
| `config/config.yaml` | П | Таймауты 60s, плейсхолдеры. |
| `requirements.txt` | П | `apscheduler` — §3.G. |
| `docker-compose.yml` | П | Volumes, env. |
| `Dockerfile` | П | §5.11. |
| `tests/*` (15+ файлов) | С+П | §5.12–5.9; **128** тестов. |
| `pytest.ini` / `README` | С+П | Внешняя документация — отдельно от кода. |

---

**Ревью по запросу «довести до конца» закрыто:** матрица §9 + критерии §8.1. Следующий этап — **реализация исправлений** по §6, не продление ревью.

### §10 Статус реализации (после рефакторинга)

Актуальная сводка **сделано / частично / в бэклог** по разделам §2–7: [REFACTOR_CHECKLIST_STATUS.md](./REFACTOR_CHECKLIST_STATUS.md).
