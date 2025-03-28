from typing import AsyncGenerator
import os
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
import re
import importlib.util
from loguru import logger

from app.config.settings import settings


# Create base model
Base = declarative_base()

# Check if asyncpg is available
has_asyncpg = importlib.util.find_spec("asyncpg") is not None

# Use SQLite by default or if asyncpg is not installed and PostgreSQL URL is specified
if os.environ.get("USE_SQLITE", "False").lower() == "true" or (not has_asyncpg and "postgres" in settings.db.DATABASE_URL):
    # Set a default SQLite path
    sqlite_path = os.path.join(settings.app.BASE_DIR, "data", "bot.db")
    os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
    
    db_url = f"sqlite+aiosqlite:///{sqlite_path}"
    logger.info(f"Using SQLite database at: {sqlite_path}")
else:
    # Convert standard database URL to async version if needed
    def get_async_db_url(url: str) -> str:
        # If already using an async driver, return as is
        if "+asyncpg" in url or "+aiosqlite" in url:
            return url
        
        # Parse URL into components
        # Expected format: dialect+driver://username:password@host:port/database
        url_pattern = re.compile(r'^([\w]+)(\+[\w]+)?://(.*)$')
        match = url_pattern.match(url)
        
        if not match:
            return url  # Return original if doesn't match expected pattern
        
        dialect, driver, rest = match.groups()
        
        # Replace with appropriate async driver
        if dialect == 'postgresql' or dialect == 'postgres':
            if has_asyncpg:
                return f'postgresql+asyncpg://{rest}'
            else:
                # Fallback to SQLite if asyncpg not available
                logger.warning("asyncpg not installed, falling back to SQLite")
                sqlite_path = os.path.join(settings.app.BASE_DIR, "data", "bot.db")
                os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
                return f"sqlite+aiosqlite:///{sqlite_path}"
        elif dialect == 'sqlite':
            return f'sqlite+aiosqlite://{rest}'
        else:
            return url  # Return original for unsupported dialects

    # Get async database URL
    db_url = get_async_db_url(settings.db.DATABASE_URL)

# Create async engine for the database
engine = create_async_engine(
    db_url,
    echo=settings.DEBUG,
    future=True,
)

# Create session factory
async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session
    
    Usage:
        async with get_session() as session:
            result = await session.execute(...)
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise e


async def init_db() -> None:
    """Initialize the database"""
    # Create directory for SQLite database if needed
    if "sqlite" in db_url:
        db_path = re.sub(r'^sqlite(\+aiosqlite)?:///', '', db_url)
        if db_path.startswith('/'):
            # Absolute path
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        else:
            # Relative path
            os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else '.', exist_ok=True)
    
    # Create tables
    async with engine.begin() as conn:
        # Import models to ensure they're registered with Base
        from app.models.user import User
        from app.models.chat import Chat, ChatMember
        
        # Create tables if they don't exist
        await conn.run_sync(Base.metadata.create_all)