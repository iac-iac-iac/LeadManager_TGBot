# Настройка прокси для работы в РФ

## Проблема

В России серверы Telegram могут быть недоступны или работать нестабильно. Если вы получаете ошибку:
```
TelegramNetworkError: HTTP Client says - Request timeout error
```

Вам нужно настроить прокси.

---

## Решение 1: Использование прокси (рекомендуется)

### 1. Найдите прокси

Вам понадобится HTTP или SOCKS5 прокси. Варианты:

**Бесплатные прокси (для тестирования):**
- https://www.proxy-list.download/
- https://www.spys.one/en/

**Платные прокси (для продакшена):**
- Bright Data
- Smartproxy
- IPRoyal
- Proxy-Seller (РФ)

### 2. Настройте в .env

Откройте файл `.env` и добавьте:

```env
# Прокси для Telegram API
TELEGRAM_PROXY_URL=http://username:password@proxy-server:port
TELEGRAM_PROXY_TYPE=HTTP

# Или для SOCKS5:
# TELEGRAM_PROXY_URL=socks5://username:password@proxy-server:port
# TELEGRAM_PROXY_TYPE=SOCKS5
```

**Примеры:**

HTTP прокси без авторизации:
```env
TELEGRAM_PROXY_URL=http://45.67.89.123:8080
```

HTTP прокси с авторизацией:
```env
TELEGRAM_PROXY_URL=http://user:pass@45.67.89.123:8080
```

SOCKS5 прокси:
```env
TELEGRAM_PROXY_URL=socks5://user:pass@proxy-server:1080
```

### 3. Перезапустите бота

```cmd
run_bot.bat
```

---

## Решение 2: Увеличение таймаута (временное)

Если прокси нет, можно увеличить таймаут подключения:

### 1. Откройте config/config.yaml

```yaml
telegram:
  request_timeout: 120  # Увеличьте до 120 секунд
  retry_attempts: 10    # Увеличьте количество попыток
  retry_delay: 10       # Увеличьте задержку между попытками
```

### 2. Перезапустите бота

```cmd
run_bot.bat
```

**Внимание:** Это временное решение. Для стабильной работы используйте прокси.

---

## Решение 3: VPN на сервере

Если бот работает на сервере:

1. Установите VPN на уровне ОС
2. Настройте маршрутизацию трафика через VPN
3. Прокси в боте не нужен

---

## Проверка работы прокси

### 1. Тест через curl

```bash
curl -x http://proxy-server:port https://api.telegram.org
```

### 2. Тест в Python

Создайте файл `test_proxy.py`:

```python
import asyncio
import aiohttp

async def test_proxy():
    proxy = "http://proxy-server:port"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                "https://api.telegram.org",
                proxy=proxy,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                print(f"Status: {resp.status}")
                print("Proxy работает!")
        except Exception as e:
            print(f"Ошибка: {e}")

asyncio.run(test_proxy())
```

Запустите:
```bash
python test_proxy.py
```

---

## Рекомендации для продакшена

1. **Используйте платные прокси** - бесплатные часто недоступны
2. **Настройте 2-3 прокси** - для резервирования
3. **Мониторьте доступность** - логируйте ошибки подключения
4. **Используйте сервер вне РФ** - если возможно

---

## Альтернатива: Сервер в другой стране

Если проблемы с Telegram критичны:

1. Арендуйте сервер в Казахстане, Армении или другой стране
2. Разверните бота там
3. Подключайтесь к серверу через SSH

**Популярные хостинги:**
- Hetzner (Германия)
- DigitalOcean (Нидерланды)
- Vultr (Европа)
- Aeza (Казахстан, Армения)

---

## Диагностика проблем

### Логи бота

Смотрите логи в реальном времени:
```powershell
Get-Content logs/bot.log -Wait -Tail 100
```

### Частые ошибки

**TimeoutError:**
- Прокси недоступен
- Слишком маленький таймаут
- Telegram заблокирован

**ProxyError:**
- Неверный формат прокси
- Прокси требует авторизацию
- Прокси заблокирован

**TokenValidationError:**
- Неверный токен бота
- Токен отозван

---

## Контакты

Если нужна помощь с настройкой прокси, обратитесь к вашему хостинг-провайдеру или используйте платные сервисы прокси.
