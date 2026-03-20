"""
Тесты для модуля импорта CSV
"""
import pytest
from pathlib import Path
from datetime import datetime

from src.csv_import.csv_importer import (
    extract_segment_from_lead_title,
    extract_city_from_address,
    normalize_phone,
    CSVImporter
)


class TestExtractSegmentFromLeadTitle:
    """Тесты извлечения сегмента из названия лида"""
    
    def test_extract_segment_standard(self):
        """Стандартный формат: 'Сегмент - Название'"""
        assert extract_segment_from_lead_title("Автосалон - Империя Авто") == "Автосалон"
        assert extract_segment_from_lead_title("Автосервис, автотехцентр - Реал") == "Автосервис, автотехцентр"
    
    def test_extract_segment_no_dash(self):
        """Без разделителя ' - '"""
        assert extract_segment_from_lead_title("Просто название") == "Просто название"
    
    def test_extract_segment_empty(self):
        """Пустая строка"""
        assert extract_segment_from_lead_title("") == "Без сегмента"
        assert extract_segment_from_lead_title(None) == "Без сегмента"
    
    def test_extract_segment_whitespace(self):
        """С пробелами"""
        assert extract_segment_from_lead_title("  Автосалон  -  Империя Авто  ") == "Автосалон"


class TestExtractCityFromAddress:
    """Тесты извлечения города из адреса"""
    
    def test_extract_city_with_region(self):
        """С областью/краем"""
        assert extract_city_from_address("Алтайский край, Барнаул, Автотранспортная улица, 49В") == "Барнаул"
        assert extract_city_from_address("Московская область, Химки, ул. Ленина") == "Химки"
    
    def test_extract_city_federal(self):
        """Города федерального значения"""
        assert extract_city_from_address("Москва, ул. Ленина, 10") == "Москва"
        assert extract_city_from_address("Санкт-Петербург, Невский проспект") == "Санкт-Петербург"
    
    def test_extract_city_only(self):
        """Только город"""
        assert extract_city_from_address("Казань, ул. Пушкина") == "Казань"
        assert extract_city_from_address("Екатеринбург, проспект Ленина") == "Екатеринбург"
    
    def test_extract_city_empty(self):
        """Пустая строка"""
        assert extract_city_from_address("") is None
        assert extract_city_from_address(None) is None
    
    def test_extract_city_cleaning(self):
        """Очистка от 'г.', 'город'"""
        assert extract_city_from_address("г. Москва") == "Москва"
        assert extract_city_from_address("город Санкт-Петербург") == "Санкт-Петербург"


class TestNormalizePhone:
    """Тесты нормализации телефона"""
    
    def test_normalize_phone_russia(self):
        """Российские номера"""
        assert normalize_phone("+7 495 123-45-67") == "+74951234567"
        assert normalize_phone("8 495 123-45-67") == "+74951234567"
        assert normalize_phone("7 495 123-45-67") == "+74951234567"
    
    def test_normalize_phone_mobile(self):
        """Мобильные номера"""
        assert normalize_phone("+7 999 123-45-67") == "+79991234567"
        assert normalize_phone("8 999 123-45-67") == "+79991234567"
    
    def test_normalize_phone_short(self):
        """Короткий формат (10 цифр)"""
        assert normalize_phone("9991234567") == "+79991234567"
    
    def test_normalize_phone_empty(self):
        """Пустая строка"""
        assert normalize_phone("") is None
        assert normalize_phone(None) is None
    
    def test_normalize_phone_invalid(self):
        """Невалидные номера"""
        assert normalize_phone("abc") is None
        # Короткие номера (3 цифры) возвращаются как есть
        assert normalize_phone("123") == "123"


class TestCSVImporter:
    """Тесты CSV импортера"""
    
    def test_parse_csv_file(self, tmp_path: Path):
        """Парсинг CSV файла"""
        # Создаем тестовый CSV
        csv_content = """Название лида;Название компании;Рабочий телефон;Адрес
Автосалон - Тест;Тест ООО;+7 495 123-45-67;Москва, ул. Ленина, 10"""
        
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content, encoding="utf-8")
        
        # Парсим
        importer = CSVImporter(delimiter=";", encoding="utf-8")
        records, total = importer.parse_csv_file(csv_file)
        
        assert total == 1
        assert len(records) == 1
        assert records[0]["segment"] == "Автосалон"
        assert records[0]["company_name"] == "Тест ООО"
        assert records[0]["phone"] == "+74951234567"
        assert records[0]["city"] == "Москва"
