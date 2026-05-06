"""Тесты сервиса очистки данных (парсинг типа из callback)."""
import pytest

from src.cleanup.cleanup_service import normalize_cleanup_type


def test_normalize_cleanup_type_strips_prefix():
    assert normalize_cleanup_type("cleanup_logs") == "logs"
    assert normalize_cleanup_type("cleanup_duplicates") == "duplicates"
    assert normalize_cleanup_type("cleanup_imported") == "imported"


def test_normalize_cleanup_type_accepts_short_form():
    assert normalize_cleanup_type("logs") == "logs"


def test_normalize_cleanup_type_rejects_unknown():
    with pytest.raises(ValueError):
        normalize_cleanup_type("cleanup_all_wrong")
