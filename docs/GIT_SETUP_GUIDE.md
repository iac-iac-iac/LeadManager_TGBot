# 📘 ПОЛНОЕ РУКОВОДСТВО ПО УСТАНОВКЕ GIT И НАСТРОЙКЕ GITHUB

**Версия:** 1.0  
**Дата:** 20 марта 2026 г.  
**Для:** Windows 10/11  
**Статус:** ✅ ПОДРОБНАЯ ИНСТРУКЦИЯ

---

## 📋 СОДЕРЖАНИЕ

1. [Установка Git на Windows](#1-установка-git-на-windows)
2. [Настройка Git](#2-настройка-git)
3. [Создание аккаунта GitHub](#3-создание-аккаунта-github)
4. [Настройка аутентификации](#4-настройка-аутентификации)
5. [Подключение репозитория](#5-подключение-репозитория)
6. [Работа с репозиторием](#6-работа-с-репозиторием)
7. [Совместная работа](#7-совместная-работа)
8. [Решение проблем](#8-решение-проблем)

---

## 1. УСТАНОВКА GIT НА WINDOWS

### Шаг 1.1: Скачивание Git

1. **Откройте официальный сайт Git:**
   ```
   https://git-scm.com/download/win
   ```

2. **Скачайте установщик:**
   - Нажмите **"Click here to download"** (последняя версия)
   - Или выберите версию вручную (рекомендуется 64-bit Git for Windows Setup)

### Шаг 1.2: Установка Git

1. **Запустите установщик** (`Git-2.x.x-64-bit.exe`)

2. **Настройте установку** (важные моменты):

   **Выбор компонентов:**
   - ✅ Git Bash Here
   - ✅ Git GUI Here
   - ✅ Associate .git* configuration files with the default text editor
   - ✅ Associate .sh files to be run with Bash
   - ✅ Add a Git Bash Profile menu to Explorer
   - ✅ Check daily for Git for Windows updates

   **Выбор редактора:**
   - Выберите **"Use Visual Studio Code as Git's default editor"** (или ваш редактор)

   **Настройка PATH (ВАЖНО!):**
   - Выберите **"Git from the command line and also from 3rd-party software"**
   - Это позволит использовать git из любой командной строки

   **Настройка HTTPS:**
   - Выберите **"Use the OpenSSL library"**

   **Настройка окончаний строк:**
   - Выберите **"Checkout Windows-style, commit Unix-style line endings"**
   - (CRLF при загрузке, LF при коммите)

   **Настройка эмуляции терминала:**
   - Выберите **"Use MinTTY"** (рекомендуется)

   **Дополнительные настройки:**
   - ✅ Enable file system caching
   - ✅ Enable symbolic links (если есть права администратора)

3. **Завершите установку:**
   - Нажмите **"Install"**
   - Дождитесь завершения
   - Нажмите **"Finish"**

### Шаг 1.3: Проверка установки

```bash
# Откройте PowerShell или Command Prompt
git --version

# Ожидаемый результат:
git version 2.x.x.windows.1
```

---

## 2. НАСТРОЙКА GIT

### Шаг 2.1: Базовая настройка

```bash
# Установите ваше имя (будет в коммитах)
git config --global user.name "Ваше Имя"

# Установите ваш email (должен совпадать с GitHub)
git config --global user.email "your-email@example.com"

# Проверьте настройки
git config --list
```

**Пример:**
```bash
git config --global user.name "Ivan Petrov"
git config --global user.email "ivan.petrov@gmail.com"
```

### Шаг 2.2: Настройка редактора по умолчанию

```bash
# Для VS Code
git config --global core.editor "code --wait"

# Для Notepad++
git config --global core.editor "'C:/Program Files/Notepad++/notepad++.exe' -multiInst"

# Для Visual Studio
git config --global core.editor "devenv"
```

### Шаг 2.3: Настройка аутентификации

```bash
# Использовать HTTPS с токеном (рекомендуется)
git config --global credential.helper wincred

# Или использовать SSH (более безопасно)
# См. раздел "Настройка SSH"
```

### Шаг 2.4: Проверка настроек

```bash
# Показать все настройки
git config --list

# Показать настройки пользователя
git config user.name
git config user.email
```

---

## 3. СОЗДАНИЕ АККАУНТА GITHUB

### Шаг 3.1: Регистрация

1. **Откройте GitHub:**
   ```
   https://github.com/signup
   ```

2. **Заполните данные:**
   - Email (реальный, для подтверждения)
   - Пароль (надёжный, 12+ символов)
   - Username (уникальное имя, например `yourname-dev`)

3. **Подтвердите email:**
   - Проверьте почту
   - Нажмите ссылку подтверждения

4. **Настройте профиль:**
   - Добавьте фото (опционально)
   - Укажите имя и компанию (опционально)

### Шаг 3.2: Настройка безопасности

1. **Включите 2FA (Two-Factor Authentication):**
   - Settings → Password and authentication
   - Enable two-factor authentication
   - Используйте приложение (Authy, Google Authenticator)

2. **Сохраните recovery codes:**
   - Скачайте или распечатайте
   - Храните в безопасном месте

---

## 4. НАСТРОЙКА АУТЕНТИФИКАЦИИ

### Вариант 1: HTTPS с Personal Access Token (РЕКОМЕНДУЕТСЯ)

#### Шаг 4.1.1: Создание токена

1. **Откройте настройки токенов:**
   ```
   https://github.com/settings/tokens
   ```

2. **Нажмите "Generate new token (classic)"**

3. **Настройте токен:**
   - **Note:** `Lead Telegram Bot Token`
   - **Expiration:** `No expiration` (или выберите срок)
   - **Scopes (разрешения):**
     - ✅ `repo` (Full control of private repositories)
     - ✅ `workflow` (Update GitHub Action workflows)
     - ✅ `read:org` (Read org membership)

4. **Скопируйте токен:**
   - Нажмите **"Generate token"**
   - **СКОПИРУЙТЕ ТОКЕН СРАЗУ!** (больше не покажут)
   - Сохраните в надёжное место (менеджер паролей)

#### Шаг 4.1.2: Использование токена

**При первом push:**
```bash
git push -u origin main
```

**GitHub запросит:**
- Username: ваш username GitHub
- Password: **вставьте ТОКЕН** (не пароль!)

**Или используйте URL с токеном:**
```bash
git remote add origin https://YOUR_TOKEN@github.com/USERNAME/repo.git
```

**Или сохраните токен:**
```bash
# Windows (сохранит токен в Credential Manager)
git config --global credential.helper wincred

# При первом вводе токена он сохранится
```

---

### Вариант 2: SSH ключи (БОЛЕЕ БЕЗОПАСНО)

#### Шаг 4.2.1: Генерация SSH ключа

```bash
# Откройте Git Bash или PowerShell
ssh-keygen -t ed25519 -C "your-email@example.com"

# Или для старых систем (RSA)
ssh-keygen -t rsa -b 4096 -C "your-email@example.com"
```

**Нажмите Enter для:**
- Файл: оставьте по умолчанию (`~/.ssh/id_ed25519`)
- Passphrase: можно оставить пустым (или задайте пароль)

#### Шаг 4.2.2: Добавление ключа в SSH agent

```bash
# Запустите agent
eval "$(ssh-agent -s)"

# Добавьте ключ
ssh-add ~/.ssh/id_ed25519

# Проверьте
ssh-add -l
```

#### Шаг 4.2.3: Добавление ключа в GitHub

1. **Скопируйте публичный ключ:**
   ```bash
   cat ~/.ssh/id_ed25519.pub | clip
   ```
   Или откройте файл `C:\Users\YourName\.ssh\id_ed25519.pub` и скопируйте содержимое

2. **Добавьте в GitHub:**
   - Откройте: https://github.com/settings/keys
   - Нажмите **"New SSH key"**
   - Title: `My Windows PC`
   - Key: вставьте скопированный ключ
   - Нажмите **"Add SSH key"**

#### Шаг 4.2.4: Проверка подключения

```bash
# Проверьте соединение
ssh -T git@github.com

# Ожидаемый результат:
# Hi username! You've successfully authenticated, but GitHub does not provide shell access.
```

#### Шаг 4.2.5: Использование SSH

```bash
# При добавлении remote используйте SSH URL:
git remote add origin git@github.com:USERNAME/repo.git

# Вместо HTTPS:
# git remote add origin https://github.com/USERNAME/repo.git
```

---

## 5. ПОДКЛЮЧЕНИЕ РЕПОЗИТОРИЯ

### Шаг 5.1: Создание репозитория на GitHub

1. **Откройте GitHub:**
   ```
   https://github.com/new
   ```

2. **Заполните данные:**
   - **Repository name:** `lead-telegram-bot`
   - **Description:** "Telegram-бот для раздачи холодных лидов с интеграцией в Bitrix24"
   - **Public** или **Private** (Private - платно для организаций)
   - ❌ **НЕ** инициализировать с README
   - ❌ **НЕ** добавлять .gitignore
   - ❌ **НЕ** добавлять лицензию

3. **Нажмите "Create repository"**

### Шаг 5.2: Подключение локального репозитория

```bash
# Перейдите в директорию проекта
cd C:\Users\direct02\Documents\DIRECT-LINE\Lead_Telegram

# Инициализируйте Git
git init

# Добавьте все файлы
git add .

# Создайте первый коммит
git commit -m "Lead Telegram Bot v2.2 - Production Release"

# Добавьте удалённый репозиторий

# ДЛЯ HTTPS:
git remote add origin https://github.com/YOUR_USERNAME/lead-telegram-bot.git

# ДЛЯ SSH:
git remote add origin git@github.com:YOUR_USERNAME/lead-telegram-bot.git

# Переименуйте ветку в main
git branch -M main

# Загрузите на GitHub
git push -u origin main
```

### Шаг 5.3: Проверка подключения

```bash
# Показать удалённые репозитории
git remote -v

# Ожидаемый результат:
# origin  https://github.com/USERNAME/lead-telegram-bot.git (fetch)
# origin  https://github.com/USERNAME/lead-telegram-bot.git (push)
```

---

## 6. РАБОТА С РЕПОЗИТОРИЕМ

### Шаг 6.1: Ежедневная работа

```bash
# 1. Проверить изменения
git status

# 2. Добавить изменения
git add .

# Или выборочно:
git add src/bot/handlers/admin_handlers.py
git add docs/

# 3. Создать коммит
git commit -m "Описание изменений"

# 4. Загрузить на GitHub
git push
```

### Шаг 6.2: Получение изменений

```bash
# Скачать изменения с GitHub (но не применять)
git fetch origin

# Скачать и применить изменения
git pull origin main

# Если есть конфликты:
# 1. Решите конфликты в файлах
# 2. git add <файлы>
# 3. git commit
# 4. git push
```

### Шаг 6.3: Работа с ветками

```bash
# Создать новую ветку
git checkout -b feature/new-feature

# Переключиться на ветку
git checkout feature/new-feature

# Вернуться на main
git checkout main

# Удалить ветку
git branch -d feature/new-feature

# Загрузить ветку на GitHub
git push -u origin feature/new-feature
```

### Шаг 6.4: Просмотр истории

```bash
# Показать последние коммиты
git log --oneline -10

# Показать изменения в последнем коммите
git show HEAD

# Показать изменения в файле
git diff src/bot/main.py
```

---

## 7. СОВМЕСТНАЯ РАБОТА

### Шаг 7.1: Добавление collaborators

1. **Откройте репозиторий на GitHub**

2. **Settings → Collaborators:**
   ```
   https://github.com/USERNAME/lead-telegram-bot/settings/access
   ```

3. **Нажмите "Add people":**
   - Введите username или email collaborator'а
   - Выберите уровень доступа (Read, Write, Admin)
   - Нажмите "Add [username] to this repository"

4. **Collaborator получит приглашение:**
   - По email
   - Или в уведомлениях GitHub

### Шаг 7.2: Работа в команде

```bash
# Перед началом работы
git pull origin main

# Создайте свою ветку
git checkout -b feature/your-feature

# Работайте в ветке
# ... изменения ...

# Закоммитьте изменения
git add .
git commit -m "Feature: описание функционала"

# Загрузите ветку
git push -u origin feature/your-feature

# Создайте Pull Request на GitHub
# 1. Откройте https://github.com/USERNAME/lead-telegram-bot/pulls
# 2. Нажмите "New pull request"
# 3. Выберите вашу ветку
# 4. Добавьте описание
# 5. Нажмите "Create pull request"
```

### Шаг 7.3: Code Review

1. **Collaborator открывает ваш PR**

2. **Оставляет комментарии:**
   - Выделите строку кода
   - Нажмите "+"
   - Напишите комментарий

3. **Исправьте замечания:**
   ```bash
   # Внесите изменения
   git add .
   git commit -m "Fix: исправления по code review"
   git push
   ```

4. **Approve и Merge:**
   - Collaborator нажимает "Review changes" → "Approve"
   - Нажмите "Merge pull request"

---

## 8. РЕШЕНИЕ ПРОБЛЕМ

### Проблема 1: Git не найден

```bash
# Проверьте установку
git --version

# Если не работает:
# 1. Переустановите Git
# 2. При установке выберите "Git from the command line and also from 3rd-party software"
# 3. Перезапустите терминал
```

### Проблема 2: Ошибка аутентификации

```bash
# Для HTTPS:
# 1. Проверьте токен (Settings → Developer settings → Personal access tokens)
# 2. Создайте новый токен
# 3. Обновите remote:
git remote set-url origin https://YOUR_NEW_TOKEN@github.com/USERNAME/repo.git

# Для SSH:
# 1. Проверьте ключ:
ssh -T git@github.com

# 2. Если ошибка, добавьте ключ заново в GitHub
```

### Проблема 3: Конфликты при merge

```bash
# Отмените merge
git merge --abort

# Обновите main
git checkout main
git pull origin main

# Попробуйте снова
git checkout feature/your-feature
git rebase main

# Решите конфликты в файлах
# ... редактирование ...

# Продолжите rebase
git add <файлы>
git rebase --continue

# Загрузите
git push -f origin feature/your-feature
```

### Проблема 4: Случайно закоммитил .env

```bash
# Если .env ещё не загружен:
git reset HEAD .env
git rm --cached .env
git commit -m "Remove .env from tracking"

# Если .env уже на GitHub:
# 1. Удалите файл из репозитория через GitHub UI
# 2. Локально:
git rm .env
git commit -m "Remove .env"
git push

# 3. Смените все секреты в .env!
```

### Проблема 5: Большой файл попал в git

```bash
# Отмените последний коммит
git reset HEAD~1

# Удалите файл из индекса
git rm --cached large_file.zip

# Закоммитьте заново
git commit -m "Remove large file"

# Если файл уже загружен:
# Используйте BFG Repo-Cleaner или git filter-branch
```

---

## 📊 ШПАРГАЛКА

### Основные команды

```bash
# Начало работы
git init
git add .
git commit -m "Message"
git remote add origin https://github.com/USER/REPO.git
git push -u origin main

# Ежедневная работа
git status
git add <файлы>
git commit -m "Message"
git push

# Получение изменений
git pull origin main
git fetch origin

# Ветки
git checkout -b feature/name
git checkout main
git branch -d feature/name
```

### URLs для подключения

**HTTPS (с токеном):**
```
https://github.com/USERNAME/lead-telegram-bot.git
```

**SSH:**
```
git@github.com:USERNAME/lead-telegram-bot.git
```

---

## 🔗 ПОЛЕЗНЫЕ ССЫЛКИ

- **Git для Windows:** https://git-scm.com/download/win
- **GitHub:** https://github.com
- **Git Documentation:** https://git-scm.com/doc
- **GitHub Docs:** https://docs.github.com
- **Git Cheat Sheet:** https://education.github.com/git-cheat-sheet-education.pdf
- **Learn Git Branching:** https://learngitbranching.js.org/ (интерактивное обучение)

---

## ✅ ЧЕКЛИСТ НАСТРОЙКИ

- [ ] Git установлен (`git --version`)
- [ ] Настроено имя (`git config user.name`)
- [ ] Настроен email (`git config user.email`)
- [ ] Аккаунт GitHub создан
- [ ] Включён 2FA на GitHub
- [ ] Создан Personal Access Token ИЛИ SSH ключ
- [ ] Ключ добавлен в GitHub (для SSH)
- [ ] Репозиторий создан на GitHub
- [ ] Локальный репозиторий подключён (`git remote -v`)
- [ ] Первый коммит загружен (`git push`)

---

**Статус:** ✅ **ПОДРОБНАЯ ИНСТРУКЦИЯ ГОТОВА**  
**Версия:** 1.0  
**Дата:** 20 марта 2026 г.
