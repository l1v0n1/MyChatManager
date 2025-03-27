import os
from typing import Dict, List, Optional, Any
from pydantic import BaseSettings, Field
from dotenv import load_dotenv

load_dotenv()


class DatabaseSettings(BaseSettings):
    """Database connection settings."""
    url: str = Field(default=os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/chat_manager"))
    pool_size: int = Field(default=int(os.getenv("DB_POOL_SIZE", "5")))
    max_overflow: int = Field(default=int(os.getenv("DB_MAX_OVERFLOW", "10")))
    echo: bool = Field(default=os.getenv("DB_ECHO", "False").lower() == "true")


class RedisSettings(BaseSettings):
    """Redis connection settings."""
    url: str = Field(default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    timeout: int = Field(default=int(os.getenv("REDIS_TIMEOUT", "5")))
    ttl: int = Field(default=int(os.getenv("REDIS_TTL", "3600")))


class RabbitMQSettings(BaseSettings):
    """RabbitMQ connection settings."""
    url: str = Field(default=os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F"))
    queue_name: str = Field(default=os.getenv("RABBITMQ_QUEUE", "chat_manager_events"))
    exchange_name: str = Field(default=os.getenv("RABBITMQ_EXCHANGE", "chat_manager"))


class TelegramSettings(BaseSettings):
    """Telegram bot settings."""
    token: str = Field(default=os.getenv("TELEGRAM_BOT_TOKEN", ""))
    admin_ids: List[int] = Field(
        default_factory=lambda: [
            int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id
        ]
    )
    webhook_url: Optional[str] = Field(default=os.getenv("WEBHOOK_URL", None))
    webhook_path: str = Field(default=os.getenv("WEBHOOK_PATH", "/webhook"))


class AppSettings(BaseSettings):
    """Main application settings."""
    debug: bool = Field(default=os.getenv("DEBUG", "False").lower() == "true")
    workers: int = Field(default=int(os.getenv("WORKERS", os.cpu_count() or 1)))
    default_language: str = Field(default=os.getenv("DEFAULT_LANGUAGE", "en"))
    available_languages: List[str] = Field(
        default_factory=lambda: os.getenv("AVAILABLE_LANGUAGES", "en,ru").split(",")
    )
    plugins_enabled: List[str] = Field(
        default_factory=lambda: os.getenv("PLUGINS_ENABLED", "").split(",") if os.getenv("PLUGINS_ENABLED") else []
    )
    environment: str = Field(default=os.getenv("ENVIRONMENT", "development"))


class Settings(BaseSettings):
    """Root settings container."""
    app: AppSettings = AppSettings()
    telegram: TelegramSettings = TelegramSettings()
    database: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    rabbitmq: RabbitMQSettings = RabbitMQSettings()


# Create settings instance
settings = Settings()
