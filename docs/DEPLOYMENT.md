# 🚀 Развёртывание в Production

**Версия:** 1.0  
**Дата:** 20 марта 2026 г.  
**Статус:** ✅ Готово к production

---

## Оглавление

1. [Требования](#требования)
2. [Подготовка сервера](#подготовка-сервера)
3. [Установка приложения](#установка-приложения)
4. [Настройка окружения](#настройка-окружения)
5. [Настройка прокси](#настройка-прокси)
6. [Запуск в Docker](#запуск-в-docker)
7. [Запуск без Docker](#запуск-без-docker)
8. [Настройка вебхука](#настройка-вебхука)
9. [Мониторинг и логи](#мониторинг-и-логи)
10. [Безопасность](#безопасность)
11. [Резервное копирование](#резервное-копирование)
12. [Обновление](#обновление)
13. [Восстановление после сбоев](#восстановление-после-сбоев)

---

## Требования

### Минимальные

- **CPU:** 1 ядро
- **RAM:** 512 MB
- **Disk:** 5 GB
- **OS:** Linux (Ubuntu 20.04+), Windows Server 2019+

### Рекомендуемые

- **CPU:** 2 ядра
- **RAM:** 1 GB
- **Disk:** 10 GB SSD
- **OS:** Linux (Ubuntu 22.04 LTS)

### Программное обеспечение

- **Python:** 3.10+
- **Docker:** 20.10+ (опционально)
- **Docker Compose:** 2.0+ (опционально)
- **Git:** для клонирования репозитория

---

## Подготовка сервера

### Linux (Ubuntu 20.04+)

```bash
# Обновление пакетов
sudo apt update && sudo apt upgrade -y

# Установка Python и зависимостей
sudo apt install -y python3.10 python3.10-venv python3-pip git

# Установка Docker (опционально)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose (опционально)
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Перелогиньтесь для применения изменений
exit
```

### Windows Server

1. Установите Python 3.10+ с [python.org](https://www.python.org/downloads/)
2. Установите Git с [git-scm.com](https://git-scm.com/download/win)
3. Установите Docker Desktop с [docker.com](https://www.docker.com/products/docker-desktop)

---

## Установка приложения

### Клонирование репозитория

```bash
# Создайте директорию для приложения
mkdir -p /opt/lead-telegram
cd /opt/lead-telegram

# Клонируйте репозиторий (или скопируйте файлы)
git clone <repository-url> .
# ИЛИ скопируйте файлы вручную
```

### Установка зависимостей

```bash
# Создание виртуального окружения
python3 -m venv venv

# Активация виртуального окружения
source venv/bin/activate  # Linux
# или
venv\Scripts\activate     # Windows

# Установка зависимостей
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Настройка окружения

### Создание файла .env

```bash
# Скопируйте пример
cp .env.example .env

# Отредактируйте файл
nano .env  # Linux
notepad .env  # Windows
```

### Обязательные параметры

```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Bitrix24 Webhook
BITRIX24_WEBHOOK_URL=https://your-portal.bitrix24.ru/rest/1/your-webhook/

# Database
DATABASE_PATH=./data/leads.db

# Uploads Folder
UPLOADS_FOLDER=./uploads

# Admin Telegram IDs (список админов через запятую)
ADMIN_TELEGRAM_IDS=123456789,987654321

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/bot.log
```

### Опциональные параметры

```env
# Proxy для работы в РФ
TELEGRAM_PROXY_URL=http://username:password@proxy-server:port
TELEGRAM_PROXY_TYPE=HTTP

# Bitrix24 Proxy
BITRIX24_PROXY_URL=http://proxy-server:port

# Расширенное логирование
LOG_LEVEL=DEBUG
```

---

## Настройка прокси

### Для работы в РФ

Telegram API может быть недоступен в России. Настройте прокси:

#### Вариант 1: HTTP прокси

```env
TELEGRAM_PROXY_URL=http://username:password@45.67.89.123:8080
TELEGRAM_PROXY_TYPE=HTTP
```

#### Вариант 2: SOCKS5 прокси

```env
TELEGRAM_PROXY_URL=socks5://username:password@proxy-server:1080
TELEGRAM_PROXY_TYPE=SOCKS5
```

#### Вариант 3: VPN на сервере

Настройте VPN на уровне ОС (OpenVPN, WireGuard).

**Проверка работы прокси:**

```bash
python test_proxy.py
```

---

## Запуск в Docker

### Сборка образа

```bash
docker-compose build
```

### Запуск контейнера

```bash
docker-compose up -d
```

### Проверка статуса

```bash
docker-compose ps
docker-compose logs -f
```

### Остановка

```bash
docker-compose down
```

### Перезапуск

```bash
docker-compose restart
```

### Структура docker-compose.yml

```yaml
version: '3.8'

services:
  bot:
    build: .
    container_name: lead_telegram_bot
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./uploads:/app/uploads
      - ./logs:/app/logs
    networks:
      - lead_network

networks:
  lead_network:
    driver: bridge
```

---

## Запуск без Docker

### Создание systemd сервиса (Linux)

```bash
# Создайте файл сервиса
sudo nano /etc/systemd/system/lead-telegram.service
```

**Содержимое файла:**

```ini
[Unit]
Description=Lead Telegram Bot
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/lead-telegram
Environment="PATH=/opt/lead-telegram/venv/bin"
ExecStart=/opt/lead-telegram/venv/bin/python src/bot/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Активация сервиса:**

```bash
# Перезагрузите systemd
sudo systemctl daemon-reload

# Включите автозапуск
sudo systemctl enable lead-telegram

# Запустите сервис
sudo systemctl start lead-telegram

# Проверьте статус
sudo systemctl status lead-telegram

# Просмотр логов
sudo journalctl -u lead-telegram -f
```

### Запуск в Windows

**Создайте файл `start_bot.bat`:**

```batch
@echo off
cd /d %~dp0
call venv\Scripts\activate
python src/bot/main.py
pause
```

**Настройка автозапуска:**

1. Откройте `Task Scheduler`
2. Создайте задачу
3. Укажите запуск `start_bot.bat`
4. Настройте триггер "At startup"

---

## Настройка вебхука

### Bitrix24 Incoming Webhook

1. Откройте ваш портал Bitrix24
2. Перейдите в **Разработчикам** → **Другое** → **Входящий вебхук**
3. Создайте новый вебхук с правами:
   - `crm.lead.*`
   - `crm.duplicate.*`
   - `crm.contact.*`
   - `crm.company.*`
   - `user.*`
4. Сохраните URL вебхука
5. Добавьте в `.env`:

```env
BITRIX24_WEBHOOK_URL=https://your-portal.bitrix24.ru/rest/1/your-webhook/
```

### Проверка подключения

```bash
# Тест подключения к Bitrix24
curl "https://your-portal.bitrix24.ru/rest/1/your-webhook/user.current.json"
```

---

## Мониторинг и логи

### Просмотр логов

```bash
# В реальном времени
tail -f logs/bot.log

# Последние 100 строк
tail -n 100 logs/bot.log

# Поиск ошибок
grep ERROR logs/bot.log

# Docker логи
docker-compose logs -f
```

### Уровни логирования

| Уровень | Описание | Когда использовать |
|---------|----------|-------------------|
| `DEBUG` | Детальная отладка | Разработка |
| `INFO` | Обычные события | Production (рекомендуется) |
| `WARNING` | Предупреждения | Production |
| `ERROR` | Ошибки | Production |

### Настройка логирования

В `.env`:

```env
LOG_LEVEL=INFO
LOG_FILE=./logs/bot.log
```

### Логирование в systemd

```bash
# Просмотр логов сервиса
sudo journalctl -u lead-telegram -f

# Логи за сегодня
sudo journalctl -u lead-telegram --since today

# Логи с указанием времени
sudo journalctl -u lead-telegram --since "2026-03-20 00:00:00"
```

---

## Безопасность

### Хранение секретов

- ✅ Токены в `.env` (не в git)
- ✅ Файл `.env` в `.gitignore`
- ✅ Ограниченный доступ к файлам (chmod 600)

```bash
# Установите правильные права
chmod 600 .env
chmod 700 data/
chmod 700 uploads/
chmod 700 logs/
```

### Сетевая безопасность

- ✅ Ограничьте доступ к серверу по IP
- ✅ Используйте HTTPS для всех внешних соединений
- ✅ Настройте firewall (UFW, iptables)

```bash
# Пример настройки UFW
sudo ufw allow 22/tcp    # SSH
sudo ufw enable
```

### Обновление зависимостей

```bash
# Проверка устаревших пакетов
pip list --outdated

# Обновление зависимостей
pip install --upgrade -r requirements.txt
```

### Аудит безопасности

```bash
# Установка safety
pip install safety

# Проверка уязвимостей
safety check
```

---

## Резервное копирование

### Автоматическое резервное копирование БД

**Скрипт `backup.sh`:**

```bash
#!/bin/bash

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/backups/lead-telegram"
DB_PATH="/opt/lead-telegram/data/leads.db"

# Создайте директорию для бэкапов
mkdir -p $BACKUP_DIR

# Скопируйте базу данных
cp $DB_PATH $BACKUP_DIR/leads_$DATE.db

# Удалите бэкапы старше 30 дней
find $BACKUP_DIR -name "leads_*.db" -mtime +30 -delete

echo "Backup completed: leads_$DATE.db"
```

**Настройка cron (ежедневно в 3:00):**

```bash
crontab -e

# Добавьте строку:
0 3 * * * /opt/lead-telegram/backup.sh >> /var/log/lead-telegram-backup.log 2>&1
```

### Ручное резервное копирование

```bash
# База данных
cp data/leads.db data/leads.backup.$(date +%Y%m%d).db

# Логи (опционально)
tar -czf logs.backup.$(date +%Y%m%d).tar.gz logs/

# .env файл
cp .env .env.backup.$(date +%Y%m%d)
```

### Восстановление из бэкапа

```bash
# Остановите бота
sudo systemctl stop lead-telegram
# или
docker-compose down

# Восстановите базу данных
cp /opt/backups/lead-telegram/leads_20260320_120000.db data/leads.db

# Запустите бота
sudo systemctl start lead-telegram
# или
docker-compose up -d
```

---

## Обновление

### Обновление кода

```bash
# Перейдите в директорию проекта
cd /opt/lead-telegram

# Остановите бота
sudo systemctl stop lead-telegram
# или
docker-compose down

# Обновите код (если используете git)
git pull origin main

# Обновите зависимости
source venv/bin/activate
pip install --upgrade -r requirements.txt

# Примените миграции БД (автоматически при запуске)

# Запустите бота
sudo systemctl start lead-telegram
# или
docker-compose up -d
```

### Проверка после обновления

```bash
# Проверьте статус
sudo systemctl status lead-telegram
# или
docker-compose ps

# Проверьте логи
tail -f logs/bot.log
# или
docker-compose logs -f

# Проверьте версию схемы БД
# В логах должно быть: "Миграции применены. Версия: 6"
```

---

## Восстановление после сбоев

### Бот не запускается

**Проверьте логи:**

```bash
sudo journalctl -u lead-telegram -n 50
# или
docker-compose logs --tail=50
```

**Частые причины:**

1. **Неверный токен Telegram:**
   - Проверьте `TELEGRAM_BOT_TOKEN` в `.env`
   - Получите новый токен у @BotFather

2. **Неверный вебхук Bitrix24:**
   - Проверьте `BITRIX24_WEBHOOK_URL` в `.env`
   - Пересоздайте вебхук в Bitrix24

3. **Проблемы с прокси:**
   - Проверьте доступность прокси
   - Временно отключите прокси для теста

4. **Ошибки миграции БД:**
   - Проверьте права доступа к `data/`
   - Удалите `data/leads.db` и запустите заново (потеря данных!)

### Бот зависает

**Перезапустите:**

```bash
sudo systemctl restart lead-telegram
# или
docker-compose restart
```

**Проверьте логи на таймауты:**

```bash
grep -i timeout logs/bot.log | tail -20
```

**Увеличьте таймауты в `config/config.yaml`:**

```yaml
telegram:
  request_timeout: 120
  retry_attempts: 10
  retry_delay: 10
```

### Проблемы с Bitrix24

**Проверьте подключение:**

```bash
curl "https://your-portal.bitrix24.ru/rest/1/your-webhook/user.current.json"
```

**Проверьте права вебхука:**

- Убедитесь, что вебхук имеет права `crm.*` и `user.*`
- Пересоздайте вебхук при необходимости

**Проверьте лимиты API:**

- Bitrix24 имеет лимиты на количество запросов
- Проверьте логи на ошибки `429 Too Many Requests`

---

## Чек-лист перед запуском

### Подготовка

- [ ] Python 3.10+ установлен
- [ ] Зависимости установлены (`pip install -r requirements.txt`)
- [ ] Файл `.env` создан и заполнен
- [ ] Токен Telegram получен у @BotFather
- [ ] Вебхук Bitrix24 создан с правильными правами
- [ ] Прокси настроен (для работы в РФ)

### Безопасность

- [ ] Файл `.env` добавлен в `.gitignore`
- [ ] Права на файлы установлены (chmod 600)
- [ ] Firewall настроен
- [ ] Резервное копирование настроено

### Запуск

- [ ] Бот запущен (`systemctl start` или `docker-compose up -d`)
- [ ] Автозапуск настроен (`systemctl enable`)
- [ ] Логи записываются
- [ ] Бот отвечает на `/start`

### Тестирование

- [ ] Регистрация менеджера работает
- [ ] Импорт CSV работает
- [ ] Выдача лидов работает
- [ ] Проверка дублей работает
- [ ] Статистика отображается
- [ ] Админские команды работают

### Мониторинг

- [ ] Логи проверяются регулярно
- [ ] Резервные копии создаются
- [ ] Метрики сервера отслеживаются
- [ ] План восстановления протестирован

---

## Контакты и поддержка

По вопросам развёртывания обращайтесь к документации:

- `README.md` — основная документация
- `QWEN.md` — контекст проекта
- `PROXY_SETUP.md` — настройка прокси
- `docs/TROUBLESHOOTING.md` — устранение проблем

**Последнее обновление:** 20 марта 2026 г.
