@echo off
REM Скрипт запуска бота для Windows

echo Запуск Telegram бота...
echo.

REM Установка PYTHONPATH
set PYTHONPATH=%~dp0

REM Запуск бота
python src\bot\main.py

pause
