"""
Тесты для модуля проверки дублей Bitrix24
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bitrix24.client import Bitrix24Client, Bitrix24Error
from src.bitrix24.duplicates import DuplicateChecker


class TestBitrix24Client:
    """Тесты Bitrix24 клиента"""
    
    @pytest.fixture
    def client(self):
        """Создание клиента"""
        return Bitrix24Client(
            webhook_url="https://test.bitrix24.ru/rest/1/test/",
            request_timeout=10,
            retry_attempts=2
        )
    
    @pytest.mark.asyncio
    async def test_find_duplicates_by_comm_success(self, client):
        """Успешный поиск дублей"""
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {
                "DUPLICATE": False,
                "DUBLICATE_ELEMENT_LIST": []
            }
            
            result = await client.find_duplicates_by_comm(phone="+74951234567")
            
            assert result["DUPLICATE"] is False
            assert len(result["DUBLICATE_ELEMENT_LIST"]) == 0
    
    @pytest.mark.asyncio
    async def test_find_duplicates_found(self, client):
        """Дубль найден"""
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            # Bitrix24 API возвращает формат: {"result": {"LEAD": [123, ...]}}
            mock_request.return_value = {
                "result": {
                    "LEAD": [123],
                    "CONTACT": [],
                    "COMPANY": []
                }
            }

            result = await client.find_duplicates_by_comm(phone="+74951234567")

            assert result["DUPLICATE"] is True
            assert len(result["DUBLICATE_ELEMENT_LIST"]) == 1
            assert result["DUBLICATE_ELEMENT_LIST"][0]["id"] == 123
    
    @pytest.mark.asyncio
    async def test_add_lead_success(self, client):
        """Успешное создание лида"""
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"id": 456}
            
            lead_id = await client.add_lead(
                title="Тестовый лид",
                company_title="Тест ООО",
                phone="+74951234567"
            )
            
            assert lead_id == 456
    
    @pytest.mark.asyncio
    async def test_add_lead_error(self, client):
        """Ошибка создания лида"""
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = Bitrix24Error("Ошибка API", error_code=403)
            
            with pytest.raises(Bitrix24Error):
                await client.add_lead(title="Тест")


class TestDuplicateChecker:
    """Тесты проверки дублей"""
    
    @pytest.fixture
    def mock_bitrix_client(self):
        """Mock Bitrix24 клиента"""
        client = MagicMock(spec=Bitrix24Client)
        client.find_duplicates_by_comm = AsyncMock()
        return client
    
    @pytest.fixture
    def checker(self, mock_bitrix_client):
        """Создание Checker'а"""
        return DuplicateChecker(mock_bitrix_client)
    
    @pytest.mark.asyncio
    async def test_check_lead_duplicate_found(self, checker, mock_bitrix_client):
        """Дубль найден"""
        mock_bitrix_client.find_duplicates_by_comm.return_value = {
            "DUPLICATE": True,
            "DUBLICATE_ELEMENT_LIST": [{"id": 123}]
        }

        # Mock сессии
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        with patch('src.bitrix24.duplicates.crud.mark_lead_as_duplicate', new_callable=AsyncMock):
            result = await checker.check_lead_duplicate(
                mock_session,
                lead_id=1,
                phone="+74951234567"
            )
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_check_lead_unique(self, checker, mock_bitrix_client):
        """Лид уникальный"""
        mock_bitrix_client.find_duplicates_by_comm.return_value = {
            "DUPLICATE": False,
            "DUBLICATE_ELEMENT_LIST": []
        }

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        with patch('src.bitrix24.duplicates.crud.mark_lead_as_unique', new_callable=AsyncMock):
            result = await checker.check_lead_duplicate(
                mock_session,
                lead_id=1,
                phone="+74951234567"
            )
            
            assert result is False
