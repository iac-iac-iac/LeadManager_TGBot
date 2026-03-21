# 🌍 ГЛОБАЛЬНАЯ НАСТРОЙКА GITHUB ДЛЯ AI АССИСТЕНТА

**Версия:** 1.0  
**Дата:** 20 марта 2026 г.  
**Статус:** ✅ ГЛОБАЛЬНАЯ КОНФИГУРАЦИЯ

---

## 📋 ЧТО БУДЕТ СДЕЛАНО

1. **Единый токен GitHub** для всех проектов
2. **Глобальная конфигурация Git**
3. **Централизованное хранилище токенов**
4. **Автоматизация для всех будущих проектов**

---

## 🔐 ШАГ 1: СОЗДАНИЕ ГЛОБАЛЬНОГО ТОКЕНА

### 1.1: Откройте настройки токенов

```
https://github.com/settings/tokens
```

### 1.2: Создайте новый токен (classic)

**Нажмите:** "Generate new token (classic)"

**Заполните:**

**Note (Название):**
```
AI Assistant - Global Access
```

**Expiration (Срок действия):**
- ✅ **No expiration** (для удобства)
- ИЛИ **90 days** (для безопасности, с автообновлением)

**Scopes (Разрешения) - ОТМЕТЬТЕ ВСЕ:**

```
✅ repo
  ✅ repo:status
  ✅ repo_deployment
  ✅ public_repo
  ✅ repo:invite
  ✅ security_events

✅ workflow

✅ read:org

✅ read:user

✅ user:email

✅ gist

✅ notifications

✅ delete_repo (опционально)

✅ admin:org (если работаете с организациями)

✅ admin:public_key

✅ admin:repo_hook

✅ admin:org_hook

✅ codespace

✅ project

✅ read:discussion

✅ read:package

✅ write:discussion

✅ write:package
```

**Нажмите:** "Generate token"

**СКОПИРУЙТЕ ТОКЕН:**
```
ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

**⚠️ ВАЖНО:** Сохраните токен в надёжное место! Больше не покажут.

---

## 🔧 ШАГ 2: ГЛОБАЛЬНАЯ НАСТРОЙКА GIT

### 2.1: Откройте глобальный конфиг Git

**Windows (PowerShell):**
```powershell
# Откройте глобальный .gitconfig
notepad $env:USERPROFILE\.gitconfig
```

**Или через Git:**
```bash
git config --global --edit
```

### 2.2: Добавьте настройки AI ассистента

**В конец файла `.gitconfig` добавьте:**

```ini
[user]
	name = Your Name
	email = your-email@example.com

[credential]
	helper = wincred

# Глобальные настройки для AI ассистента
[ai]
	github_token = ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
	github_username = iac-iac-iac
	github_email = your-email@example.com
	default_branch = main

# Автоматическая подстановка токена
[credential "https://github.com"]
	helper = wincred
```

**Пример заполненного `.gitconfig`:**

```ini
[core]
	editor = code
	autocrlf = true

[user]
	name = Ivan Petrov
	email = ivan.petrov@gmail.com

[credential]
	helper = wincred

[ai]
	github_token = ghp_1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r
	github_username = iac-iac-iac
	github_email = ivan.petrov@gmail.com
	default_branch = main

[alias]
	st = status
	co = checkout
	br = branch
	ci = commit
	last = log -1 HEAD
	unstage = reset HEAD --
```

### 2.3: Сохраните файл

**В Notepad:**
- File → Save (Ctrl+S)
- Закройте

---

## 📁 ШАГ 3: ЦЕНТРАЛИЗОВАННОЕ ХРАНИЛИЩЕ ТОКЕНОВ

### 3.1: Создайте директорию для токенов

**Windows:**
```powershell
# Создайте папку для токенов
mkdir $env:USERPROFILE\\.ai-credentials

# Перейдите в папку
cd $env:USERPROFILE\\.ai-credentials
```

### 3.2: Создайте файл с токенами

**Создайте файл:** `$env:USERPROFILE\.ai-credentials\github.token`

**Содержимое:**
```
# GitHub Personal Access Token для AI ассистента
# Создан: 2026-03-20
# Истекает: No expiration

GITHUB_TOKEN=ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
GITHUB_USERNAME=iac-iac-iac
GITHUB_EMAIL=your-email@example.com
DEFAULT_BRANCH=main

# Дополнительные репозитории (опционально)
# REPO_1=iac-iac-iac/project1
# REPO_2=iac-iac-iac/project2
```

### 3.3: Защитите файл (опционально)

**Windows - установите права:**
```powershell
# Разрешить только вашему пользователю
icacls $env:USERPROFILE\.ai-credentials\github.token /grant:r $env:USERNAME:(R)
```

---

## 🔗 ШАГ 4: ИНТЕГРАЦИЯ С AI АССИСТЕНТОМ

### 4.1: Создайте глобальный конфиг для AI

**Создайте файл:** `$env:USERPROFILE\.ai-credentials\ai-config.json`

**Содержимое:**

```json
{
  "github": {
    "token": "ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "username": "iac-iac-iac",
    "email": "your-email@example.com",
    "defaultBranch": "main",
    "tokenFile": "C:\\Users\\YourName\\.ai-credentials\\github.token"
  },
  "git": {
    "globalConfig": "C:\\Users\\YourName\\.gitconfig",
    "credentialHelper": "wincred",
    "editor": "code"
  },
  "defaults": {
    "commitConvention": "conventional",
    "autoPush": false,
    "requireConfirmation": true
  }
}
```

### 4.2: Настройте переменные окружения

**Windows - Постоянные переменные:**

```powershell
# Откройте редактор переменных окружения
[System.Environment]::SetEnvironmentVariable('GITHUB_TOKEN', 'ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX', 'User')
[System.Environment]::SetEnvironmentVariable('GITHUB_USERNAME', 'iac-iac-iac', 'User')
[System.Environment]::SetEnvironmentVariable('GITHUB_EMAIL', 'your-email@example.com', 'User')

# Проверьте
echo $env:GITHUB_TOKEN
```

**Или через PowerShell профиль:**

```powershell
# Откройте профиль
notepad $PROFILE

# Добавьте:
$env:GITHUB_TOKEN = "ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
$env:GITHUB_USERNAME = "iac-iac-iac"
$env:GITHUB_EMAIL = "your-email@example.com"
```

---

## 🚀 ШАГ 5: НАСТРОЙКА GITHUB CLI (ОПЦИОНАЛЬНО)

### 5.1: Установите GitHub CLI

**Windows:**
```powershell
winget install GitHub.cli
```

### 5.2: Аутентифицируйтесь

```bash
# Войдите в GitHub
gh auth login

# Выберите:
# 1. GitHub.com
# 2. HTTPS
# 3. Login with a web browser
# 4. Скопируйте код: XXXX-XXXX
# 5. Откройте: https://github.com/login/device
# 6. Введите код
# 7. Подтвердите доступ
```

### 5.3: Глобальная настройка CLI

**Откройте конфиг:**
```bash
# Windows
notepad $env:APPDATA\GitHub CLI\hosts.yml
```

**Добавьте:**
```yaml
github.com:
    user: iac-iac-iac
    oauth_token: ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    git_protocol: https
```

### 5.4: Проверьте

```bash
# Проверка аутентификации
gh auth status

# Ожидаемый результат:
# ✓ Logged in to github.com as iac-iac-iac
```

---

## 📝 ШАГ 6: АВТОМАТИЗАЦИЯ ДЛЯ НОВЫХ ПРОЕКТОВ

### 6.1: Создайте шаблон репозитория

**Создайте директорию шаблона:**
```powershell
mkdir $env:USERPROFILE\git-templates\default
cd $env:USERPROFILE\git-templates\default
```

**Создайте базовую структуру:**
```
git-templates/default/
├── .gitignore
├── .env.example
├── README.md
├── docs/
├── src/
├── tests/
└── config/
```

### 6.2: Скрипт инициализации нового проекта

**Создайте файл:** `$env:USERPROFILE\git-templates\init-repo.ps1`

**Содержимое:**

```powershell
# Скрипт инициализации нового Git репозитория
# Использование: .\init-repo.ps1 -ProjectName "MyProject" -Description "Description"

param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectName,
    
    [Parameter(Mandatory=$true)]
    [string]$Description,
    
    [string]$GitHubOrg = "iac-iac-iac",
    
    [switch]$Public
)

# Загрузка токена
$tokenFile = "$env:USERPROFILE\.ai-credentials\github.token"
if (Test-Path $tokenFile) {
    $token = (Get-Content $tokenFile | Select-String "GITHUB_TOKEN=").ToString().split('=')[1]
} else {
    $token = $env:GITHUB_TOKEN
}

if (-not $token) {
    Write-Error "GitHub токен не найден! Настройте .ai-credentials/github.token"
    exit 1
}

# Создание директории проекта
$projectPath = Join-Path $PWD $ProjectName
New-Item -ItemType Directory -Path $projectPath -Force | Out-Null
Set-Location $projectPath

# Инициализация Git
git init
git checkout -b main

# Копирование шаблонов
Copy-Item "$env:USERPROFILE\git-templates\default\*" -Destination . -Recurse -Force

# Создание README
$readme = @"
# $ProjectName

$Description

## Установка

` ` ` `bash
git clone https://github.com/$GitHubOrg/$ProjectName.git
cd $ProjectName
pip install -r requirements.txt
` ` ` `

## Лицензия

MIT
"@

Set-Content -Path "README.md" -Value $readme

# Первый коммит
git add .
git commit -m "Initial commit: $ProjectName"

# Создание на GitHub
$visibility = if ($Public) { "public" } else { "private" }
$headers = @{
    "Authorization" = "token $token"
    "Accept" = "application/vnd.github.v3+json"
}
$body = @{
    "name" = $ProjectName
    "description" = $Description
    "private" = (-not $Public)
    "auto_init" = $false
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "https://api.github.com/user/repos" -Method Post -Headers $headers -Body $body
$repoUrl = $response.html_url

Write-Host "✓ Репозиторий создан: $repoUrl"

# Подключение remote
git remote add origin $repoUrl
git push -u origin main

Write-Host "✓ Проект инициализирован!"
Write-Host "✓ URL: $repoUrl"
```

### 6.3: Использование

```powershell
# Инициализация нового проекта
.\init-repo.ps1 -ProjectName "NewBot" -Description "Новый Telegram бот" -Public

# Или приватный
.\init-repo.ps1 -ProjectName "PrivateProject" -Description "Закрытый проект"
```

---

## 🔐 ШАГ 7: БЕЗОПАСНОСТЬ

### 7.1: Проверка токена

```bash
# Проверьте токен
curl -H "Authorization: token ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX" \
     https://api.github.com/user
```

### 7.2: Мониторинг активности

**Откройте:**
```
https://github.com/settings/security-log
```

**Проверьте:**
- Последние входы
- Активные сессии
- Использование токенов

### 7.3: Обновление токена

**Каждые 90 дней:**

1. **Создайте новый токен:**
   ```
   https://github.com/settings/tokens/new
   ```

2. **Обновите файлы:**
   - `$env:USERPROFILE\.ai-credentials\github.token`
   - `$env:USERPROFILE\.gitconfig`
   - `$env:APPDATA\GitHub CLI\hosts.yml`

3. **Удалите старый токен:**
   ```
   https://github.com/settings/tokens
   ```

---

## 📊 ШАГ 8: ПРОВЕРКА НАСТРОЕК

### 8.1: Тестовая команда

```powershell
# Проверка Git
git config --list | Select-String "user|ai"

# Проверка токена
echo $env:GITHUB_TOKEN

# Проверка GitHub CLI
gh auth status

# Тестовый пуш (создайте тестовый файл)
echo "Test" > test.txt
git add test.txt
git commit -m "Test commit"
git push
```

### 8.2: Чеклист

- [ ] Токен создан и скопирован
- [ ] Токен сохранён в `.ai-credentials/github.token`
- [ ] Глобальный `.gitconfig` обновлён
- [ ] Переменные окружения настроены
- [ ] GitHub CLI установлен и настроен
- [ ] Шаблон проекта создан
- [ ] Скрипт инициализации работает
- [ ] Тестовый пуш успешен

---

## 🎯 ИСПОЛЬЗОВАНИЕ В БУДУЩИХ ПРОЕКТАХ

### Для AI ассистента:

**Просто скажите:**

> "Создай новый проект для Telegram бота и загрузи на GitHub"

**AI сделает:**

```bash
# 1. Создаст структуру проекта
mkdir new-bot
cd new-bot

# 2. Инициализирует Git
git init
git checkout -b main

# 3. Создаст файлы
# ... создание файлов проекта ...

# 4. Сдела коммит
git add .
git commit -m "Initial commit: new-bot"

# 5. Создаст репозиторий на GitHub
gh repo create new-bot --public --source=. --remote=origin

# 6. Загрузит
git push -u origin main
```

**Всё автоматически!** 🎉

---

## 📋 БЫСТРЫЙ СТАРТ (5 МИНУТ)

```powershell
# 1. Создайте токен
# Откройте: https://github.com/settings/tokens/new
# Note: AI Assistant Global
# Scopes: repo, workflow
# Copy: ghp_XXXXXXXX

# 2. Сохраните токен
mkdir $env:USERPROFILE\.ai-credentials
echo "GITHUB_TOKEN=ghp_XXXXXXXX" > $env:USERPROFILE\.ai-credentials\github.token

# 3. Настройте Git
git config --global user.name "Your Name"
git config --global user.email "your-email@example.com"
git config --global credential.helper wincred

# 4. Проверьте
gh auth status

# 5. Готово!
```

---

## 🔗 ССЫЛКИ

- **Токены:** https://github.com/settings/tokens
- **Безопасность:** https://github.com/settings/security
- **GitHub CLI:** https://cli.github.com/
- **Git Docs:** https://git-scm.com/doc

---

**Статус:** ✅ **ГЛОБАЛЬНАЯ НАСТРОЙКА ГОТОВА**  
**Действует для:** ВСЕХ проектов  
**Дата:** 20 марта 2026 г.
