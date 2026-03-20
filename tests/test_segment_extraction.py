"""
Тесты функции извлечения сегмента из phone_source

Проверяет:
- Извлечение с разделителем "!"
- Извлечение без "!" (по первому слову)
- Пустой phone_source с fallback
- Пустой phone_source без fallback
"""
import pytest
import sys
from pathlib import Path

# Добавляем корень проекта в path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.csv_import.csv_importer import extract_segment_from_phone_source, extract_segment_from_lead_title


class TestExtractSegmentFromPhoneSource:
    """Тесты функции extract_segment_from_phone_source"""

    def test_extract_with_exclamation(self):
        """Тест извлечения с разделителем "!" """
        phone_source = "быстровозводимые здания!СБП_КраснЯр_Казань__2026-03-18_14_17_02.json"
        result = extract_segment_from_phone_source(phone_source)
        assert result == "быстровозводимые здания"

    def test_extract_with_exclamation_short(self):
        """Тест извлечения с "!" короткий вариант"""
        phone_source = "Автосалоны!Тестовые данные"
        result = extract_segment_from_phone_source(phone_source)
        assert result == "Автосалоны"

    def test_extract_without_exclamation_with_space(self):
        """Тест извлечения без "!" — первое слово по пробелу"""
        phone_source = "Строительство Москва Центр"
        result = extract_segment_from_phone_source(phone_source)
        assert result == "Строительство"

    def test_extract_without_exclamation_single_word(self):
        """Тест извлечения без "!" — одно слово"""
        phone_source = "Производство"
        result = extract_segment_from_phone_source(phone_source)
        assert result == "Производство"

    def test_extract_empty_phone_source_with_fallback(self):
        """Тест с пустым phone_source и fallback"""
        phone_source = ""
        fallback = "Резервный сегмент"
        result = extract_segment_from_phone_source(phone_source, fallback_segment=fallback)
        assert result == fallback

    def test_extract_empty_phone_source_without_fallback(self):
        """Тест с пустым phone_source без fallback"""
        phone_source = ""
        result = extract_segment_from_phone_source(phone_source)
        assert result == "Без сегмента"

    def test_extract_none_phone_source_with_fallback(self):
        """Тест с None phone_source и fallback"""
        phone_source = None
        fallback = "Резервный сегмент"
        result = extract_segment_from_phone_source(phone_source, fallback_segment=fallback)
        assert result == fallback

    def test_extract_none_phone_source_without_fallback(self):
        """Тест с None phone_source без fallback"""
        phone_source = None
        result = extract_segment_from_phone_source(phone_source)
        assert result == "Без сегмента"

    def test_extract_whitespace_only(self):
        """Тест с пробелами вместо значения"""
        phone_source = "   "
        result = extract_segment_from_phone_source(phone_source)
        assert result == "Без сегмента"

    def test_extract_with_leading_trailing_spaces(self):
        """Тест с пробелами в начале и конце"""
        phone_source = "  Автосервис!Данные  "
        result = extract_segment_from_phone_source(phone_source)
        assert result == "Автосервис"

    def test_extract_complex_segment_name(self):
        """Тест со сложным названием сегмента"""
        phone_source = "Грузовые автомобили!СБП_Тест__2026-03-18.json"
        result = extract_segment_from_phone_source(phone_source)
        assert result == "Грузовые автомобили"

    def test_extract_segment_with_special_chars(self):
        """Тест с сегментом содержащим спецсимволы"""
        phone_source = "B2B_Партнёры!Тест"
        result = extract_segment_from_phone_source(phone_source)
        assert result == "B2B_Партнёры"

    def test_extract_only_exclamation_no_segment(self):
        """Тест когда "!" есть, но перед ним пусто"""
        phone_source = "!Только данные"
        result = extract_segment_from_phone_source(phone_source)
        # Должен вернуть часть после "!" (первое слово)
        assert result == "Только"

    def test_extract_fallback_from_lead_title(self):
        """Тест fallback на lead_title"""
        phone_source = ""
        fallback = extract_segment_from_lead_title("Автосалон - Компания")
        result = extract_segment_from_phone_source(phone_source, fallback_segment=fallback)
        assert result == "Автосалон"


class TestExtractSegmentFromLeadTitle:
    """Тесты функции extract_segment_from_lead_title (fallback)"""

    def test_extract_standard_format(self):
        """Тест стандартного формата "Сегмент - Компания" """
        lead_title = "Автосалон - Империя Авто"
        result = extract_segment_from_lead_title(lead_title)
        assert result == "Автосалон"

    def test_extract_no_dash(self):
        """Тест без разделителя " - " """
        lead_title = "Просто название"
        result = extract_segment_from_lead_title(lead_title)
        assert result == "Просто название"

    def test_extract_empty(self):
        """Тест пустого значения"""
        lead_title = ""
        result = extract_segment_from_lead_title(lead_title)
        assert result == "Без сегмента"

    def test_extract_with_multiple_dashes(self):
        """Тест с несколькими " - " """
        lead_title = "Сегмент - Компания - Филиал"
        result = extract_segment_from_lead_title(lead_title)
        assert result == "Сегмент"

    def test_extract_with_spaces_around_dash(self):
        """Тест с пробелами вокруг " - " """
        lead_title = "  Строительство  -  Компания  "
        result = extract_segment_from_lead_title(lead_title)
        assert result == "Строительство"


class TestIntegration:
    """Интеграционные тесты"""

    def test_full_workflow_phone_source_priority(self):
        """Тест приоритета phone_source над lead_title"""
        phone_source = "Приоритетный!Данные"
        lead_title = "Вторичный сегмент - Компания"

        # Извлекаем из phone_source
        segment_from_phone = extract_segment_from_phone_source(phone_source)

        # Если не удалось, используем fallback из lead_title
        if segment_from_phone == "Без сегмента":
            segment = extract_segment_from_lead_title(lead_title)
        else:
            segment = segment_from_phone

        assert segment == "Приоритетный"

    def test_full_workflow_fallback_to_lead_title(self):
        """Тест fallback на lead_title при пустом phone_source"""
        phone_source = ""
        lead_title = "Резервный сегмент - Компания"

        # Извлекаем из phone_source
        segment_from_phone = extract_segment_from_phone_source(phone_source)

        # Если не удалось, используем fallback из lead_title
        if segment_from_phone == "Без сегмента":
            segment = extract_segment_from_lead_title(lead_title)
        else:
            segment = segment_from_phone

        assert segment == "Резервный сегмент"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
