# 🔧 Устранение проблем (Troubleshooting)

**Версия:** 1.0  
**Дата:** 20 марта 2026 г.  
**Статус:** ✅ Готово к использованию

---

## Оглавление

1. [Диагностика](#диагностика)
2. [Частые ошибки](#частые-ошибки)
3. [Проблемы с Telegram](#проблемы-с-telegram)
4. [Проблемы с Bitrix24](#проблемы-с-bitrix24)
5. [Проблемы с базой данных](#проблемы-с-базой-данных)
6. [Проблемы с CSV](#проблемы-с-csv)
7. [Проблемы с производительностью](#проблемы-с-производительностью)
8. [Восстановление данных](#восстановление-данных)
9. [Инструменты отладки](#инструменты-отладки)
10. [Логи и мониторинг](#логи-и-мониторинг)

---

## Диагностика

### Быстрая проверка статуса

```bash
# Проверка процесса
ps aux | grep python
# или
docker-compose ps

# Проверка логов
tail -f logs/bot.log
# или
docker-compose logs -f

# Проверка порта (если используете webhook)
netstat -tlnp | grep python
```

### Чек-лист диагностики

- [ ] Бот запущен (процесс активен)
- [ ] Логи записываются
- [ ] Файл `.env` существует
- [ ] База данных существует
- [ ] Директории `data/`, `uploads/`, `logs/` существуют
- [ ] Токен Telegram верный
- [ ] Вебхук Bitrix24 верный
- [ ] Прокси настроен (если нужен)

---

## Частые ошибки

### 1. Бот не запускается

**Симптомы:**
```
ModuleNotFoundError: No module named 'aiogram'
```

**Решение:**
```bash
# Активируйте виртуальное окружение
source venv/bin/activate  # Linux
venv\Scripts\activate     # Windows

# Переустановите зависимости
pip install -r requirements.txt
```

---

### 2. Ошибка токена Telegram

**Симптомы:**
```
Unauthorized: token is not valid
```

**Решение:**
1. Проверьте токен в `.env`
2. Получите новый токен у @BotFather
3. Перезапустите бота

```bash
# Проверка токена
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
```

---

### 3. Ошибка подключения к Bitrix24

**Симптомы:**
```
Bitrix24Error: Invalid webhook URL
```

**Решение:**
1. Проверьте URL вебхука в `.env`
2. Пересоздайте вебхук в Bitrix24
3. Проверьте права вебхука (`crm.*`, `user.*`)

```bash
# Проверка вебхука
curl "https://your-portal.bitrix24.ru/rest/1/your-webhook/user.current.json"
```

---

### 4. Ошибка миграции БД

**Симптомы:**
```
sqlite3.OperationalError: no such table: leads
```

**Решение:**
```bash
# Удалите старую базу (если данные не важны)
rm data/leads.db

# Запустите бота заново (миграции применятся автоматически)
python src/bot/main.py
```

**Если данные важны:**
```bash
# Сделайте бэкап
cp data/leads.db data/leads.backup.db

# Проверьте версию схемы
python -c "from src.database.migrations import *; import asyncio; asyncio.run(check_schema())"
```

---

### 5. Таймаут Telegram API

**Симптомы:**
```
TelegramNetworkError: Request timeout error
```

**Решение:**

**Вариант 1: Настройте прокси**
```env
TELEGRAM_PROXY_URL=http://username:password@proxy-server:port
TELEGRAM_PROXY_TYPE=HTTP
```

**Вариант 2: Увеличьте таймаут**
В `config/config.yaml`:
```yaml
telegram:
  request_timeout: 120
  retry_attempts: 10
  retry_delay: 10
```

---

### 6. Дублирование логов

**Симптомы:**
```
INFO:info:bot.main:Бот запущен
INFO:info:bot.main:Бот запущен
```

**Решение:**
Отключите `logging.basicConfig` в `src/logger.py`:
```python
# Закомментируйте или удалите
# logging.basicConfig(...)
```

---

### 7. Ошибка при импорте CSV

**Симптомы:**
```
CSVImportError: Invalid column 'phone'
```

**Решение:**
1. Проверьте заголовки CSV
2. Обязательные колонки:
   - `phone` или `Телефон`
   - `company_name` или `Название компании`
   - `city` или `Город`

**Пример правильного CSV:**
```csv
phone,company_name,city,address
+79991234567,ООО "Ромашка",Москва,ул. Ленина 1
```

---

## Проблемы с Telegram

### Бот не отвечает на команды

**Причины:**
1. Бот не запущен
2. Неправильный токен
3. Проблемы с сетью/прокси

**Диагностика:**
```bash
# Проверка процесса
ps aux | grep python

# Проверка логов
tail -f logs/bot.log

# Проверка токена
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
```

**Решение:**
```bash
# Перезапустите бота
sudo systemctl restart lead-telegram
# или
docker-compose restart
```

---

### Ошибка "Forbidden: bot was blocked by the user"

**Причина:** Пользователь заблокировал бота

**Решение:**
1. Попросите пользователя разблокировать бота
2. Отправьте команду `/start` заново

**Программная обработка:**
В логах будет:
```
WARNING:bot.handlers:Пользователь 123456789 заблокировал бота
```

---

### Ошибка "Too Many Requests" (429)

**Причина:** Превышен лимит запросов к Telegram API

**Решение:**
1. Увеличьте задержки в `config/config.yaml`:
```yaml
telegram:
  retry_delay: 5  # Увеличьте задержку
  retry_attempts: 10
```

2. Проверьте rate limiting в middleware:
```python
# src/bot/middleware/rate_limit.py
RATE_LIMIT = 10  # сообщений в минуту
```

---

## Проблемы с Bitrix24

### Ошибка "Webhook not found"

**Симптомы:**
```
Bitrix24Error: Webhook not found
```

**Решение:**
1. Проверьте URL вебхука в `.env`
2. Убедитесь, что URL заканчивается на `/`
3. Пересоздайте вебхук в Bitrix24

**Правильный формат:**
```env
BITRIX24_WEBHOOK_URL=https://your-portal.bitrix24.ru/rest/1/your-webhook/
```

---

### Ошибка "Insufficient privileges"

**Симптомы:**
```
Bitrix24Error: Access denied. Insufficient privileges
```

**Решение:**
1. Проверьте права вебхука в Bitrix24
2. Необходимые права:
   - `crm.lead.*`
   - `crm.duplicate.*`
   - `crm.contact.*`
   - `crm.company.*`
   - `user.*`

**Пересоздание вебхука:**
1. Откройте Bitrix24
2. Разработчикам → Другое → Входящий вебхук
3. Удалите старый вебхук
4. Создайте новый с правильными правами

---

### Ошибка "Duplicate not found"

**Симптомы:**
```
Bitrix24Error: Method crm.duplicate.findbycomm not found
```

**Решение:**
Метод может называться по-другому в вашей версии Bitrix24.

**Проверка доступных методов:**
```bash
curl "https://your-portal.bitrix24.ru/rest/1/your-webhook/methods.json"
```

**Альтернативный метод поиска дублей:**
```python
# Используйте crm.lead.list с фильтром
params = {
    "filter": {"PHONE": phone}
}
```

---

### Таймаут при импорте лида

**Симптомы:**
```
asyncio.TimeoutError: Bitrix24 request timeout
```

**Решение:**
1. Увеличьте таймаут в `src/bitrix24/client.py`:
```python
timeout = aiohttp.ClientTimeout(total=60)  # Увеличьте до 60-120 секунд
```

2. Проверьте скорость соединения с Bitrix24:
```bash
curl -w "@curl-format.txt" -o /dev/null -s "https://your-portal.bitrix24.ru/"
```

---

## Проблемы с базой данных

### Блокировка базы данных

**Симптомы:**
```
sqlite3.OperationalError: database is locked
```

**Решение:**
1. Найдите процессы, держащие блокировку:
```bash
lsof data/leads.db
```

2. Завершите процессы:
```bash
kill -9 <PID>
```

3. Проверьте целостность БД:
```bash
sqlite3 data/leads.db "PRAGMA integrity_check;"
```

4. Восстановите из бэкапа (если нужно):
```bash
cp data/leads.backup.db data/leads.db
```

---

### Повреждение базы данных

**Симптомы:**
```
sqlite3.DatabaseError: database disk image is malformed
```

**Решение:**
1. Сделайте бэкап повреждённой БД:
```bash
cp data/leads.db data/leads.corrupted.db
```

2. Попробуйте восстановить:
```bash
sqlite3 data/leads.db ".dump" | sqlite3 data/leads.recovered.db
```

3. Если не помогло, восстановите из бэкапа:
```bash
cp /opt/backups/lead-telegram/leads_20260320_120000.db data/leads.db
```

---

### Переполнение базы данных

**Симптомы:**
- Медленная работа
- Ошибки при записи

**Решение:**
1. Очистите старые логи:
```sql
DELETE FROM logs WHERE timestamp < datetime('now', '-30 days');
```

2. Очистите старые лиды:
```sql
DELETE FROM leads WHERE status = 'DUPLICATE' AND created_at < datetime('now', '-90 days');
DELETE FROM leads WHERE status = 'IMPORTED' AND created_at < datetime('now', '-180 days');
```

3. Сожмите базу:
```bash
sqlite3 data/leads.db "VACUUM;"
```

---

## Проблемы с CSV

### Неправильная кодировка

**Симптомы:**
```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc3
```

**Решение:**
1. Конвертируйте CSV в UTF-8:
```bash
iconv -f WINDOWS-1251 -t UTF-8 input.csv > output.csv
```

2. Или укажите кодировку в коде:
```python
with open(file, 'r', encoding='windows-1251') as f:
    # ...
```

---

### Неправильный разделитель

**Симптомы:**
```
CSVImportError: Expected 5 columns, got 1
```

**Решение:**
1. Проверьте разделитель в CSV (запятая, точка с запятой, табуляция)
2. Конвертируйте в правильный формат:
```bash
# Замена точки с запятой на запятую
sed 's/;/,/g' input.csv > output.csv
```

---

### Отсутствуют обязательные поля

**Симптомы:**
```
CSVImportError: Missing required column 'phone'
```

**Решение:**
1. Проверьте заголовки CSV
2. Обязательные поля:
   - `phone` или `Телефон`
   - `company_name` или `Название компании`

**Пример правильного CSV:**
```csv
phone,company_name,city,address,source
+79991234567,ООО "Ромашка",Москва,ул. Ленина 1,Холодный звонок
```

---

## Проблемы с производительностью

### Медленная проверка дублей

**Симптомы:**
- Проверка 1000 лидов занимает >30 минут

**Решение:**
1. Проверьте индексы:
```sql
.indexes leads
```

2. Создайте недостающие индексы:
```sql
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);
CREATE INDEX IF NOT EXISTS idx_leads_company ON leads(company_name);
```

3. Оптимизируйте запросы в `src/bitrix24/duplicates.py`

---

### Утечка памяти

**Симптомы:**
- Потребление памяти растёт со временем
- Бот зависает после нескольких часов работы

**Решение:**
1. Проверьте логи на ошибки:
```bash
grep -i memory logs/bot.log
```

2. Используйте profiler:
```bash
python -m memory_profiler src/bot/main.py
```

3. Увеличьте лимиты памяти в Docker:
```yaml
services:
  bot:
    deploy:
      resources:
        limits:
          memory: 512M
```

---

### Медленные запросы к БД

**Симптомы:**
- Запросы выполняются >5 секунд

**Решение:**
1. Включите логирование медленных запросов:
```python
# В src/database/models.py
engine = create_async_engine(
    DATABASE_URL,
    echo=True  # Логирование SQL запросов
)
```

2. Проверьте план запроса:
```sql
EXPLAIN QUERY PLAN SELECT * FROM leads WHERE status = 'UNIQUE';
```

3. Добавьте индексы:
```sql
CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_segment ON leads(segment);
```

---

## Восстановление данных

### Восстановление из бэкапа

```bash
# Остановите бота
sudo systemctl stop lead-telegram

# Восстановите базу данных
cp /opt/backups/lead-telegram/leads_20260320_120000.db data/leads.db

# Восстановите .env
cp /opt/backups/lead-telegram/.env.backup.20260320 .env

# Запустите бота
sudo systemctl start lead-telegram
```

### Экспорт данных вручную

```bash
# Экспорт лидов в CSV
sqlite3 data/leads.db ".headers on" ".mode csv" "SELECT * FROM leads;" > leads_export.csv

# Экспорт пользователей
sqlite3 data/leads.db ".headers on" ".mode csv" "SELECT * FROM users;" > users_export.csv

# Экспорт тикетов
sqlite3 data/leads.db ".headers on" ".mode csv" "SELECT * FROM tickets;" > tickets_export.csv
```

### Импорт данных вручную

```bash
# Импорт из CSV
sqlite3 data/leads.db ".mode csv" ".import leads_import.csv leads"
```

---

## Инструменты отладки

### Отладочный режим

В `.env`:
```env
LOG_LEVEL=DEBUG
```

В `config/config.yaml`:
```yaml
debug:
  enabled: true
  verbose_errors: true
```

### Профилирование

```bash
# Профилирование CPU
python -m cProfile -o profile.stats src/bot/main.py

# Анализ профиля
python -m pstats profile.stats
```

### Трассировка запросов

В `src/bitrix24/client.py` добавьте логирование:
```python
import logging

logger = logging.getLogger(__name__)

async def request(self, method, params=None):
    logger.debug(f"Bitrix24 request: {method}, params: {params}")
    start_time = time.time()
    # ...
    duration = time.time() - start_time
    logger.debug(f"Bitrix24 response: {method}, duration: {duration:.2f}s")
```

---

## Логи и мониторинг

### Просмотр логов

```bash
# В реальном времени
tail -f logs/bot.log

# Последние 100 строк
tail -n 100 logs/bot.log

# Поиск ошибок
grep ERROR logs/bot.log | tail -20

# Поиск по дате
grep "2026-03-20" logs/bot.log

# Подсчёт ошибок
grep -c ERROR logs/bot.log
```

### Уровни логирования

| Уровень | Описание | Пример |
|---------|----------|--------|
| `DEBUG` | Детальная отладка | SQL запросы, API вызовы |
| `INFO` | Обычные события | Запуск бота, импорт CSV |
| `WARNING` | Предупреждения | Таймауты, повторные попытки |
| `ERROR` | Ошибки | Ошибки API, БД |
| `CRITICAL` | Критические ошибки | Падение бота |

### Настройка логирования

В `.env`:
```env
LOG_LEVEL=INFO
LOG_FILE=./logs/bot.log
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

### Мониторинг метрик

```bash
# Использование CPU
top -p $(pgrep -f "python.*main.py")

# Использование памяти
ps -o pid,rss,command -p $(pgrep -f "python.*main.py")

# Размер базы данных
du -h data/leads.db

# Количество записей
sqlite3 data/leads.db "SELECT COUNT(*) FROM leads;"
```

---

## Скрипты для диагностики

### check_health.sh

```bash
#!/bin/bash

echo "=== Lead Telegram Bot Health Check ==="
echo ""

# Проверка процесса
echo "1. Процесс бота:"
ps aux | grep "[p]ython.*main.py" || echo "❌ Бот не запущен"
echo ""

# Проверка логов
echo "2. Последние логи:"
tail -n 10 logs/bot.log
echo ""

# Проверка базы данных
echo "3. База данных:"
if [ -f data/leads.db ]; then
    echo "✅ Файл БД существует"
    echo "   Размер: $(du -h data/leads.db | cut -f1)"
    echo "   Количество лидов: $(sqlite3 data/leads.db 'SELECT COUNT(*) FROM leads;')"
else
    echo "❌ Файл БД не найден"
fi
echo ""

# Проверка .env
echo "4. Файл .env:"
if [ -f .env ]; then
    echo "✅ Файл .env существует"
else
    echo "❌ Файл .env не найден"
fi
echo ""

echo "=== Health Check Complete ==="
```

### repair_database.sh

```bash
#!/bin/bash

DB_PATH="data/leads.db"
BACKUP_PATH="data/leads.backup.$(date +%Y%m%d_%H%M%S).db"

echo "=== Database Repair ==="
echo ""

# Бэкап
echo "1. Создание бэкапа..."
cp $DB_PATH $BACKUP_PATH
echo "✅ Бэкап создан: $BACKUP_PATH"
echo ""

# Проверка целостности
echo "2. Проверка целостности..."
INTEGRITY=$(sqlite3 $DB_PATH "PRAGMA integrity_check;")
if [ "$INTEGRITY" = "ok" ]; then
    echo "✅ База данных цела"
else
    echo "❌ База данных повреждена: $INTEGRITY"
    echo "   Попробуйте восстановить из бэкапа"
    exit 1
fi
echo ""

# Ваккуумирование
echo "3. Ваккуумирование..."
sqlite3 $DB_PATH "VACUUM;"
echo "✅ Ваккуумирование завершено"
echo ""

# Статистика
echo "4. Статистика:"
echo "   Лиды: $(sqlite3 $DB_PATH 'SELECT COUNT(*) FROM leads;')"
echo "   Пользователи: $(sqlite3 $DB_PATH 'SELECT COUNT(*) FROM users;')"
echo "   Тикеты: $(sqlite3 $DB_PATH 'SELECT COUNT(*) FROM tickets;')"
echo ""

echo "=== Database Repair Complete ==="
```

---

## Чек-лист устранения проблем

### Бот не запускается

- [ ] Проверьте логи (`tail -f logs/bot.log`)
- [ ] Проверьте `.env` (токены, пути)
- [ ] Проверьте зависимости (`pip list`)
- [ ] Проверьте права доступа к файлам
- [ ] Перезапустите бота

### Бот зависает

- [ ] Проверьте логи на таймауты
- [ ] Проверьте подключение к интернету
- [ ] Проверьте прокси (если используется)
- [ ] Проверьте лимиты API (Telegram, Bitrix24)
- [ ] Перезапустите бота

### Ошибки импорта CSV

- [ ] Проверьте формат CSV (UTF-8)
- [ ] Проверьте заголовки колонок
- [ ] Проверьте разделители
- [ ] Проверьте путь к файлу
- [ ] Попробуйте другой файл

### Ошибки Bitrix24

- [ ] Проверьте URL вебхука
- [ ] Проверьте права вебхука
- [ ] Проверьте подключение к Bitrix24
- [ ] Проверьте лимиты API
- [ ] Пересоздайте вебхук

### Ошибки базы данных

- [ ] Проверьте целостность БД
- [ ] Проверьте блокировки
- [ ] Проверьте место на диске
- [ ] Сделайте вакуумирование
- [ ] Восстановите из бэкапа

---

## Контакты и поддержка

По вопросам обращайтесь к документации:

- `README.md` — основная документация
- `QWEN.md` — контекст проекта
- `docs/DEPLOYMENT.md` — развёртывание
- `docs/AUDIT_REPORT_2026-03-20.md` — аудит проекта

**Последнее обновление:** 20 марта 2026 г.
