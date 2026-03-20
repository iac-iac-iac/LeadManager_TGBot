# 🚀 ИНСТРУКЦИЯ ПО ЗАГРУЗКЕ НА GITHUB

**Версия:** 2.2  
**Дата:** 20 марта 2026 г.  
**Статус:** ✅ ГОТОВО К ЗАГРУЗКЕ

---

## ✅ ПРОЕКТ ГОТОВ К ЗАГРУЗКЕ!

Все критические файлы защищены через `.gitignore`, чувствительные данные не попадут в репозиторий.

---

## 📋 ЧТО НЕ ПОПАДЁТ В GIT (защищено .gitignore)

### 🔒 Чувствительные данные

- ✅ **`.env`** - токены, секреты, пароли
- ✅ **`data/leads.db`** - база данных с лидами
- ✅ **`data/*.db-journal`**, **`data/*.db-wal`**, **`data/*.db-shm`** - файлы SQLite
- ✅ **`logs/`** - логи приложения
- ✅ **`uploads/`** - CSV файлы для импорта

### 🗑 Временные файлы

- ✅ **`__pycache__/`**, **`*.pyc`**, **`*.pyo`** - кэш Python
- ✅ **`*.egg-info/`** - информация о пакетах
- ✅ **`venv/`**, **`env/`** - виртуальные окружения
- ✅ **`.pytest_cache/`**, **`.coverage`**, **`htmlcov/`** - тесты
- ✅ **`tmp/`**, **`temp/`**, **`*.tmp`**, **`*.cache`** - временные файлы

### 💾 Резервные копии

- ✅ **`*.backup`**, **`*.bak`**, **`backups/`** - резервные копии БД
- ✅ **`*.log`** - файлы логов

### ⚙️ Конфигурация IDE

- ✅ **`.idea/`** - PyCharm
- ✅ **`.vscode/`** - VS Code
- ✅ **`*.iml`** - IntelliJ

---

## 🚀 ПОШАГОВАЯ ИНСТРУКЦИЯ

### Шаг 1: Проверка файлов

```bash
cd C:\Users\direct02\Documents\DIRECT-LINE\Lead_Telegram

# Проверяем что .env существует
dir .env

# Проверяем что .gitignore существует
dir .gitignore

# Проверяем что нет чувствительных файлов в корне
dir *.key *.pem *.secret 2>nul
```

### Шаг 2: Инициализация Git

```bash
# Инициализируем репозиторий
git init

# Проверяем статус
git status
```

**Ожидаемый результат:**
- ✅ В списке файлов НЕТ `.env`
- ✅ В списке файлов НЕТ `data/leads.db`
- ✅ В списке файлов НЕТ `logs/`
- ✅ В списке файлов НЕТ `uploads/`

### Шаг 3: Добавление файлов

```bash
# Добавляем все файлы
git add .

# Проверяем что добавлено
git status
```

**Что должно быть добавлено:**
- ✅ `src/` - исходный код
- ✅ `docs/` - документация
- ✅ `config/` - конфигурация (без секретов)
- ✅ `README.md`, `QWEN.md`, `PROXY_SETUP.md`
- ✅ `requirements.txt`, `docker-compose.yml`, `Dockerfile`
- ✅ `.gitignore`, `.env.example`

**Что НЕ должно быть добавлено:**
- ❌ `.env`
- ❌ `data/leads.db`
- ❌ `logs/`
- ❌ `uploads/`
- ❌ `__pycache__/`

### Шаг 4: Первый коммит

```bash
# Создаём коммит
git commit -m "Lead Telegram Bot v2.2 - Production Release

Основные изменения:
- Пакет утилит (phone, callback, file, datetime)
- Миграция v7 (23 индекса БД, ускорение 100x)
- Исправления безопасности (валидация webhook, backoff)
- Исправления багов админ-панели
- Полная документация

Изменения от 20 марта 2026 г."
```

### Шаг 5: Создание репозитория на GitHub

1. **Зайдите на GitHub:** https://github.com/new
2. **Создайте репозиторий:**
   - Название: `lead-telegram-bot` или ваше название
   - Описание: "Telegram-бот для раздачи холодных лидов с интеграцией в Bitrix24"
   - **Public** или **Private** (на ваше усмотрение)
   - ❌ **НЕ** инициализировать с README (уже есть)
   - ❌ **НЕ** добавлять .gitignore (уже есть)
   - ❌ **НЕ** добавлять лицензию (можно добавить позже)

3. **Скопируйте URL репозитория:**
   ```
   https://github.com/USERNAME/lead-telegram-bot.git
   ```

### Шаг 6: Загрузка на GitHub

```bash
# Добавляем удалённый репозиторий
git remote add origin https://github.com/USERNAME/lead-telegram-bot.git

# Переименовываем ветку в main
git branch -M main

# Загружаем на GitHub
git push -u origin main
```

### Шаг 7: Проверка на GitHub

1. Откройте ваш репозиторий на GitHub
2. Проверьте что файлы загрузились
3. Проверьте что **НЕТ** в репозитории:
   - ❌ `.env`
   - ❌ `data/leads.db`
   - ❌ `logs/`
   - ❌ `uploads/`

---

## 🔐 БЕЗОПАСНОСТЬ

### Что проверить перед загрузкой

```bash
# Ищем секреты в файлах
findstr /S /I "TOKEN" *.py *.yaml *.yml 2>nul
findstr /S /I "SECRET" *.py *.yaml *.yml 2>nul
findstr /S /I "PASSWORD" *.py *.yaml *.yml 2>nul
findstr /S /I "WEBHOOK" *.py *.yaml *.yml 2>nul

# Проверяем что секреты только в .env
findstr /S /I "8726467102:" *.py 2>nul  # Telegram токен
findstr /S /I "bitrix24.ru/rest" *.py 2>nul  # Bitrix24 webhook
```

**Если нашли секреты в коде:**
1. Удалите их из кода
2. Переместите в `.env`
3. Используйте `get_config()` для доступа

### .env.example

Создайте `.env.example` с шаблонными значениями:

```bash
# Копируем .env в .env.example
copy .env .env.example

# Открываем .env.example и заменяем секреты на шаблоны:
# TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN_HERE
# BITRIX24_WEBHOOK_URL=https://YOUR_PORTAL.bitrix24.ru/rest/YOUR_WEBHOOK_ID/
```

---

## 📊 ЧТО БУДЕТ НА GITHUB

### ✅ Файлы проекта (будут загружены)

```
Lead_Telegram/
├── .gitignore                     ✅
├── .env.example                   ✅ (создайте!)
├── README.md                      ✅
├── QWEN.md                        ✅
├── PROXY_SETUP.md                 ✅
├── requirements.txt               ✅
├── docker-compose.yml             ✅
├── Dockerfile                     ✅
├── run_bot.bat                    ✅
├── migrate_segments.bat           ✅
├── config/
│   └── config.yaml                ✅ (без секретов)
├── docs/
│   ├── CHANGELOG.md               ✅
│   ├── DEPLOYMENT.md              ✅
│   ├── TROUBLESHOOTING.md         ✅
│   ├── BUGFIX_ADMIN_ISSUES.md     ✅
│   └── ARCHIVE/
│       └── Project-telegram-ORIGINAL-TZ.md  ✅
└── src/
    ├── __init__.py                ✅
    ├── config.py                  ✅
    ├── logger.py                  ✅
    ├── bot/                       ✅
    ├── database/                  ✅
    ├── bitrix24/                  ✅
    ├── csv_import/                ✅
    ├── cleanup/                   ✅
    ├── analytics/                 ✅
    └── utils/                     ✅
```

### ❌ Файлы которые НЕ будут загружены

```
.env                             ❌ Конфигурация с секретами
data/leads.db                    ❌ База данных
data/*.db-journal                ❌ Файлы SQLite
data/*.db-wal                    ❌ Файлы SQLite
data/*.db-shm                    ❌ Файлы SQLite
logs/                            ❌ Логи приложения
uploads/*.csv                    ❌ CSV файлы
uploads/*.xlsx                   ❌ Excel файлы
__pycache__/                     ❌ Кэш Python
*.pyc                            ❌ Скомпилированный Python
*.backup                         ❌ Резервные копии БД
backups/                         ❌ Резервные копии
.venv/                           ❌ Виртуальное окружение
env/                             ❌ Виртуальное окружение
```

---

## 🎯 ФИНАЛЬНЫЙ ЧЕКЛИСТ

Перед загрузкой проверьте:

- [ ] **`.env` существует и содержит реальные секреты**
- [ ] **`.gitignore` существует и содержит все правила**
- [ ] **`.env.example` создан с шаблонными значениями**
- [ ] **Секреты не хардкодятся в коде** (только через `.env`)
- [ ] **`git status` не показывает `.env`, `data/`, `logs/`**
- [ ] **Все файлы проекта добавлены (`git add .`)**
- [ ] **Коммит создан с понятным сообщением**
- [ ] **Репозиторий создан на GitHub**
- [ ] **Загрузка выполнена (`git push`)**

---

## 📞 ЕСЛИ ЧТО-ТО ПОШЛО НЕ ТАК

### Проблема: `.env` попал в коммит

```bash
# Отменяем коммит
git reset HEAD~1

# Удаляем .env из индекса
git rm --cached .env

# Создаём новый коммит
git commit -m "Fix: removed .env from commit"

# Загружаем с force
git push -f origin main
```

**ВАЖНО:** После этого смените все секреты в `.env`!

### Проблема: База данных попала в коммит

```bash
# Отменяем коммит
git reset HEAD~1

# Удаляем data/ из индекса
git rm --cached -r data/

# Создаём новый коммит
git commit -m "Fix: removed database from commit"

# Загружаем с force
git push -f origin main
```

---

## ✅ ГОТОВО!

После успешной загрузки:

1. ✅ Проверьте репозиторий на GitHub
2. ✅ Добавьте описание и теги
3. ✅ Настройте GitHub Actions (опционально)
4. ✅ Добавьте collaborators (если нужно)
5. ✅ Настройте Wiki (опционально)

---

**Статус:** ✅ **ПРОЕКТ ГОТОВ К ЗАГРУЗКЕ**  
**Версия:** 2.2  
**Дата:** 20 марта 2026 г.
