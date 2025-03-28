#!/usr/bin/env python
import os
import sys
import subprocess
import time
import traceback
import asyncio
from loguru import logger

# Add the current directory to Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Check if we should use SQLite for development
os.environ["USE_SQLITE"] = "True"
# Set debug mode
os.environ["APP_DEBUG"] = "True"

def install_requirements():
    """Install required packages if not already installed"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("Requirements installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install requirements: {e}")
        sys.exit(1)

async def init_database():
    """Initialize database connection"""
    try:
        from app.database.session import init_db
        logger.info("Initializing database...")
        await init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        logger.error(traceback.format_exc())
        raise

async def init_cache():
    """Initialize cache service"""
    try:
        from app.services.cache_service import cache_service
        logger.info("Connecting to cache service...")
        await cache_service.connect()
        logger.info("Cache service connected successfully.")
        return cache_service
    except Exception as e:
        logger.error(f"Cache service connection error: {e}")
        logger.error(traceback.format_exc())
        raise

async def init_events():
    """Initialize event manager"""
    try:
        from app.events.event_manager import event_manager
        logger.info("Connecting to event manager...")
        await event_manager.connect()
        logger.info("Event manager connected successfully.")
        return event_manager
    except Exception as e:
        logger.error(f"Event manager connection error: {e}")
        logger.error(traceback.format_exc())
        raise

async def init_bot():
    """Initialize and start the bot"""
    try:
        from app.api.bot import setup_bot, start_bot
        logger.info("Setting up bot...")
        bot = await setup_bot()
        logger.info("Bot setup successfully.")
        
        logger.info("Starting bot polling...")
        await start_bot(skip_updates=True)
        return bot
    except Exception as e:
        logger.error(f"Bot initialization error: {e}")
        logger.error(traceback.format_exc())
        raise

async def startup():
    """Initialize app services before starting the bot"""
    cache_service = None
    event_manager = None
    bot = None
    
    try:
        # Initialize database
        await init_database()
        
        # Initialize cache service
        cache_service = await init_cache()
        
        # Initialize event manager
        event_manager = await init_events()
        
        # Start the bot
        bot = await init_bot()
        
        # Keep the bot running
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        logger.error(traceback.format_exc())
    finally:
        await shutdown(cache_service, event_manager, bot)

async def shutdown(cache_service=None, event_manager=None, bot=None):
    """Cleanup on shutdown"""
    try:
        # Stop the bot
        if bot:
            from app.api.bot import stop_bot
            logger.info("Stopping bot...")
            await stop_bot()
            logger.info("Bot stopped successfully.")
        
        # Disconnect from cache
        if cache_service:
            logger.info("Disconnecting from cache service...")
            await cache_service.disconnect()
            logger.info("Cache service disconnected.")
        
        # Disconnect event manager
        if event_manager:
            logger.info("Disconnecting from event manager...")
            await event_manager.disconnect()
            logger.info("Event manager disconnected.")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    try:
        # Configure logging
        logger.remove()
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level="DEBUG"  # Changed to DEBUG for more detailed logs
        )
        
        # Ensure logs directory exists
        os.makedirs("logs", exist_ok=True)
        
        logger.add(
            "logs/bot.log",
            rotation="10 MB",
            retention="1 week",
            compression="zip",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG"  # Changed to DEBUG for more detailed logs
        )
        
        logger.info("Starting MyChatManager Bot in DEBUG mode")
        
        # Run the bot
        asyncio.run(startup())
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        sys.exit(1) 