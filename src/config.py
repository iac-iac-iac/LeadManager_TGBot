"""
Конфигурация приложения
"""
import os
from pathlib import Path
from typing import List, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class TelegramConfig(BaseModel):
    bot_token: str
    proxy_url: Optional[str] = ""
    proxy_type: str = "HTTP"
    request_timeout: int = 30
    retry_attempts: int = 3
    retry_delay: int = 5


class Bitrix24Config(BaseModel):
    webhook_url: str
    proxy_url: Optional[str] = ""
    request_timeout: int = 30
    retry_attempts: int = 3
    retry_delay: int = 5
    duplicate_check_fields: List[str] = Field(default_factory=lambda: ["phone", "company_name", "address"])


class DatabaseConfig(BaseModel):
    path: str
    echo: bool = False


class UploadsConfig(BaseModel):
    folder: str
    allowed_extensions: List[str] = Field(default_factory=lambda: ["csv"])
    encoding: str = "utf-8"
    delimiter: str = ";"


class AdminConfig(BaseModel):
    telegram_ids: str  # Comma-separated list


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class CleanupConfig(BaseModel):
    logs_days: int = 30
    duplicate_leads_days: int = 90
    imported_leads_days: int = 180


class LeadsConfig(BaseModel):
    max_per_request: int = 200
    fifo_order: bool = True


class Config(BaseSettings):
    telegram: TelegramConfig
    bitrix24: Bitrix24Config
    database: DatabaseConfig
    uploads: UploadsConfig
    admin: AdminConfig
    logging: LoggingConfig
    cleanup: CleanupConfig
    leads: LeadsConfig
    
    @classmethod
    def load(cls) -> "Config":
        """Загрузка конфигурации из файла и переменных окружения"""
        load_dotenv()
        
        # Путь к config.yaml относительно корня проекта
        base_dir = Path(__file__).resolve().parent.parent
        config_path = base_dir / "config" / "config.yaml"
        
        if not config_path.exists():
            raise FileNotFoundError(f"Конфигурационный файл не найден: {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
        
        # Подстановка переменных окружения
        raw_config = cls._substitute_env(raw_config)
        
        return cls(**raw_config)
    
    @staticmethod
    def _substitute_env(config: dict) -> dict:
        """Рекурсивная подстановка переменных окружения"""
        result = {}
        for key, value in config.items():
            if isinstance(value, dict):
                result[key] = Config._substitute_env(value)
            elif isinstance(value, str) and value.startswith("${"):
                # Парсинг формата ${VAR:default}
                env_part = value[2:-1]
                if ":" in env_part:
                    env_var, default = env_part.split(":", 1)
                    result[key] = os.getenv(env_var, default)
                else:
                    result[key] = os.getenv(env_part, "")
            else:
                result[key] = value
        return result
    
    @property
    def database_path(self) -> Path:
        """Полный путь к базе данных"""
        db_path = Path(self.database.path)
        if not db_path.is_absolute():
            base_dir = Path(__file__).resolve().parent.parent
            return base_dir / db_path
        return db_path
    
    @property
    def uploads_folder(self) -> Path:
        """Полный путь к папке загрузок"""
        uploads_path = Path(self.uploads.folder)
        if not uploads_path.is_absolute():
            base_dir = Path(__file__).resolve().parent.parent
            return base_dir / uploads_path
        return uploads_path
    
    @property
    def log_file(self) -> Path:
        """Полный путь к файлу логов"""
        log_path = Path(self.logging.file)
        if not log_path.is_absolute():
            base_dir = Path(__file__).resolve().parent.parent
            return base_dir / log_path
        return log_path
    
    @property
    def admin_telegram_ids(self) -> List[int]:
        """Список Telegram ID админов"""
        return [int(x.strip()) for x in self.admin.telegram_ids.split(",") if x.strip()]


# =============================================================================
# Глобальный экземпляр конфигурации (ленивая инициализация)
# =============================================================================

_config_cache: Optional[Config] = None


def get_config(cached: bool = True) -> Config:
    """
    Получение конфигурации
    
    Args:
        cached: Если True, использует кэшированный экземпляр. 
                Если False, загружает конфигурацию заново.
    
    Returns:
        Конфигурация приложения
        
    Example:
        >>> config = get_config()
        >>> config.telegram.bot_token
    """
    global _config_cache
    
    if not cached or _config_cache is None:
        _config_cache = Config.load()
    
    return _config_cache


def reload_config() -> Config:
    """
    Принудительная перезагрузка конфигурации
    
    Returns:
        Обновлённая конфигурация
    """
    global _config_cache
    _config_cache = Config.load()
    return _config_cache
