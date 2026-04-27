"""Валидация обязательных полей конфигурации (ранний fail при старте)."""
import pytest
from pydantic import ValidationError

from src.config import TelegramConfig, Bitrix24Config


def test_telegram_bot_token_rejects_empty():
    with pytest.raises(ValidationError):
        TelegramConfig(bot_token="")


def test_bitrix_webhook_rejects_empty():
    with pytest.raises(ValidationError):
        Bitrix24Config(webhook_url="")

def test_bitrix_webhook_rejects_non_url():
    with pytest.raises(ValidationError):
        Bitrix24Config(webhook_url="not-a-url")
