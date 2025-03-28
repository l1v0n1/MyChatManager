import os
from typing import List, Optional, Dict, Any, Union
from pydantic import Field, BaseModel, field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from pathlib import Path
import re

# Load environment variables from .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class BotSettings(BaseModel):
    """Bot settings"""
    TOKEN: str = ""
    ADMINS: List[int] = []
    SKIPS: List[int] = []
    USE_REDIS: bool = False


class APISettings(BaseModel):
    """API settings"""
    ENABLED: bool = False
    HOST: str = "127.0.0.1"
    PORT: int = 8080


class AppSettings(BaseModel):
    """Application settings"""
    DEBUG: bool = False
    BASE_DIR: Path = BASE_DIR
    PLUGINS_ENABLED: List[str] = ["mute_plugin", "admin_tools", "antispam", "notes", "welcome"]
    PLUGINS_DIRS: List[Path] = []
    

class DatabaseSettings(BaseModel):
    """Database settings"""
    DATABASE_URL: str = "sqlite:///bot.db"
    USE_SQLITE: str = "false"


class LoggingSettings(BaseModel):
    """Logging settings"""
    LOG_LEVEL: str = "INFO"
    LOG_FILE: Optional[str] = None


class RedisSettings(BaseModel):
    """Redis settings"""
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None


class Settings(BaseModel):
    """Application settings"""
    bot: BotSettings = BotSettings()
    api: APISettings = APISettings()
    app: AppSettings = AppSettings()
    db: DatabaseSettings = DatabaseSettings()
    logging: LoggingSettings = LoggingSettings()
    redis: RedisSettings = RedisSettings()
    DEBUG: bool = False
    
    # Special method to handle environment variables
    @field_validator('*', mode='before')
    def check_env(cls, v, info):
        env_val = os.getenv(info.field_name.upper())
        if env_val is not None:
            # Handle different types of fields
            if isinstance(v, bool):
                return env_val.lower() in ['true', '1', 'yes']
            elif isinstance(v, int):
                return int(env_val)
            elif isinstance(v, list):
                return env_val.split(',')
            return env_val
        return v


# Create settings instance
settings = Settings()

# Update plugin directories to include both built-in and custom plugins
settings.app.PLUGINS_DIRS = [
    BASE_DIR / "app" / "plugins",  # Built-in plugins
    BASE_DIR / "plugins"           # Custom plugins
]

# Environment variable overrides
if os.getenv("BOT_TOKEN"):
    settings.bot.TOKEN = os.getenv("BOT_TOKEN")

if os.getenv("ADMINS"):
    settings.bot.ADMINS = [int(admin) for admin in os.getenv("ADMINS").split(",") if admin.strip()]

if os.getenv("PLUGINS_ENABLED"):
    settings.app.PLUGINS_ENABLED = os.getenv("PLUGINS_ENABLED").split(",")

if os.getenv("DATABASE_URL"):
    settings.db.DATABASE_URL = os.getenv("DATABASE_URL")

if os.getenv("USE_SQLITE"):
    settings.db.USE_SQLITE = os.getenv("USE_SQLITE").lower()

# Debug mode
settings.DEBUG = settings.app.DEBUG
