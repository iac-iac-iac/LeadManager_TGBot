# 🚀 БЫСТРАЯ НАСТРОЙКА ГЛОБАЛЬНОГО ДОСТУПА К GITHUB

**3 простых шага для постоянной работы с GitHub через AI**

---

## ⚡ БЫСТРЫЙ СТАРТ (2 МИНУТЫ)

### Шаг 1: Создайте токен

1. **Откройте:** https://github.com/settings/tokens/new
2. **Note:** `AI Assistant Global`
3. **Expiration:** `No expiration`
4. **Scopes:** Отметьте `repo` и `workflow`
5. **Нажмите:** "Generate token"
6. **Скопируйте:** `ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`

---

### Шаг 2: Запустите скрипт настройки

**Откройте PowerShell от имени администратора:**

```powershell
# Перейдите в директорию проекта
cd C:\Users\direct02\Documents\DIRECT-LINE\Lead_Telegram

# Запустите скрипт настройки
.\setup-github-global.ps1
```

**Скрипт спросит:**
1. Ваш GitHub токен (вставьте скопированный)
2. Ваше имя (например: `Ivan Petrov`)
3. Ваш email (например: `ivan@gmail.com`)
4. GitHub username (например: `iac-iac-iac`)

**Скрипт сделает:**
- ✅ Создаст папку `.ai-credentials`
- ✅ Сохранит токен
- ✅ Настроит Git config
- ✅ Установит переменные окружения
- ✅ Предложит войти в GitHub CLI

---

### Шаг 3: Проверьте

```powershell
# Проверка настроек
git config --list | Select-String "user|ai"

# Проверка токена
echo $env:GITHUB_TOKEN

# Тестовый пуш (опционально)
cd C:\Users\direct02\Documents\DIRECT-LINE\Lead_Telegram
git add .
git commit -m "Test: global GitHub setup"
git push
```

---

## 📁 ЧТО СОЗДАНО

### Файлы:

| Файл | Назначение |
|------|------------|
| `$env:USERPROFILE\.ai-credentials\github.token` | Токен GitHub |
| `$env:USERPROFILE\.ai-credentials\ai-config.json` | Конфиг AI |
| `$env:USERPROFILE\.gitconfig` | Глобальный Git config |
| `.\setup-github-global.ps1` | Скрипт настройки |

### Переменные окружения:

- `GITHUB_TOKEN` - ваш токен
- `GITHUB_USERNAME` - ваш username
- `GITHUB_EMAIL` - ваш email

---

## 🎯 ИСПОЛЬЗОВАНИЕ

### Теперь AI может:

**1. Делать коммиты в существующие проекты:**

> "Добавь новый файл README и закоммить"

```bash
git add README.md
git commit -m "Add README"
git push
```

**2. Создавать новые репозитории:**

> "Создай новый проект и загрузи на GitHub"

```bash
mkdir new-project
cd new-project
git init
# ... создание файлов ...
git commit -m "Initial commit"
gh repo create new-project --public --source=. --remote=origin
git push -u origin main
```

**3. Управлять Pull Request'ами:**

> "Создай PR с новыми изменениями"

```bash
git checkout -b feature/new-feature
# ... изменения ...
git commit -m "Feature: new feature"
git push -u origin feature/new-feature
gh pr create --title "New feature" --body "Description"
```

---

## 🔐 БЕЗОПАСНОСТЬ

### Где хранится токен:

```
C:\Users\YourName\.ai-credentials\github.token
```

**Защита:**
- ✅ Только для вашего пользователя (NTFS права)
- ✅ В .gitignore (не попадёт в Git)
- ✅ Отдельно от проекта

### Обновление токена:

**Каждые 90 дней (рекомендуется):**

1. Создайте новый токен: https://github.com/settings/tokens/new
2. Замените в файле `.ai-credentials\github.token`
3. Обновите переменную окружения:
   ```powershell
   $env:GITHUB_TOKEN = "ghp_NEW_TOKEN_HERE"
   ```

---

## 📊 ПРОВЕРКА СТАТУСА

```powershell
# Токен
echo $env:GITHUB_TOKEN

# GitHub CLI
gh auth status

# Git config
git config --global user.name
git config --global user.email

# Репозитории
gh repo list
```

---

## 🆘 ЕСЛИ ЧТО-ТО ПОШЛО НЕ ТАК

### Проблема: Токен не работает

```powershell
# Проверьте токен
curl -H "Authorization: token $env:GITHUB_TOKEN" https://api.github.com/user

# Если ошибка 401 - токен неверный
# Создайте новый: https://github.com/settings/tokens/new
```

### Проблема: Git не пушит

```powershell
# Проверьте remote
git remote -v

# Перенастройте:
git remote set-url origin https://$env:GITHUB_TOKEN@github.com/$env:GITHUB_USERNAME/repo.git
```

### Проблема: GitHub CLI не работает

```powershell
# Переаутентификация
gh auth logout
gh auth login
```

---

## 📚 ПОДРОБНАЯ ДОКУМЕНТАЦИЯ

- **Полная инструкция:** [`docs/GLOBAL_GITHUB_SETUP.md`](docs/GLOBAL_GITHUB_SETUP.md)
- **Настройка Git:** [`docs/GIT_SETUP_GUIDE.md`](docs/GIT_SETUP_GUIDE.md)
- **Загрузка проекта:** [`docs/GITHUB_UPLOAD_GUIDE.md`](docs/GITHUB_UPLOAD_GUIDE.md)

---

## ✅ ГОТОВО!

**Теперь AI имеет глобальный доступ к GitHub!**

**Используйте команды:**
- "Закоммить изменения"
- "Создай новый репозиторий"
- "Загрузи на GitHub"
- "Создай Pull Request"

**Всё будет работать автоматически!** 🎉

---

**Статус:** ✅ **ГОТОВО**  
**Действует для:** ВСЕХ проектов  
**Дата:** 20 марта 2026 г.
