from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func
from sqlalchemy import Column, DateTime, Integer, create_engine
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from loguru import logger
import os

from app.config.settings import settings

# Create SQLAlchemy Base
Base = declarative_base()

# Check if we're in development mode with SQLite
if os.environ.get("USE_SQLITE", "False").lower() == "true":
    # Use SQLite for development if specified
    db_url = "sqlite:///./chat_manager.db"
    sync_engine = create_engine(db_url, echo=settings.DEBUG)
    # Create async engine with special SQLite handling
    engine = create_async_engine(
        "sqlite+aiosqlite:///./chat_manager.db",
        echo=settings.DEBUG,
    )
    logger.info(f"Using SQLite for development: {db_url}")
else:
    # Use the configured database URL
    try:
        engine = create_async_engine(
            settings.db.DATABASE_URL,
            echo=settings.DEBUG,
        )
        logger.info(f"Connected to database: {settings.db.DATABASE_URL}")
    except Exception as e:
        # Fallback to SQLite if connection fails
        logger.warning(f"Failed to connect to database, falling back to SQLite: {e}")
        db_url = "sqlite:///./chat_manager.db"
        sync_engine = create_engine(db_url, echo=settings.DEBUG)
        engine = create_async_engine(
            "sqlite+aiosqlite:///./chat_manager.db",
            echo=settings.DEBUG,
        )
        logger.info(f"Using SQLite as fallback: {db_url}")

# Create async session factory
async_session_factory = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class BaseModel(Base):
    """Base model for all database models."""
    __abstract__ = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional scope around a series of operations."""
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        await session.close()


async def init_db() -> None:
    """Initialize database."""
    logger.info("Initializing the database...")
    try:
        async with engine.begin() as conn:
            # await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        # Try to create tables synchronously if using SQLite fallback
        if "sqlite" in str(engine.url):
            from sqlalchemy import text
            sync_engine = create_engine(str(engine.url).replace("+aiosqlite", ""))
            Base.metadata.create_all(sync_engine)
            logger.info("Database initialized with SQLite fallback.")
