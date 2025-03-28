import asyncio
from loguru import logger
import os
import sys
import signal
from typing import Set
import traceback

# Import config first to ensure settings are loaded
from app.config.settings import settings
from app.config.logging_config import setup_logging


async def start_services():
    """Initialize and start all services"""
    # Setup logging
    setup_logging()
    
    logger.info("Starting Chat Manager...")
    
    try:
        # Import components here to avoid circular imports
        from app.api.bot import bot_instance
        from app.models.base import init_db
        from app.services.cache_service import cache_service
        from app.events.event_manager import event_manager
        from app.plugins.plugin_manager import plugin_manager
        
        # Initialize database
        await init_db()
        
        # Connect to Redis cache
        await cache_service.connect()
        
        # Connect to RabbitMQ
        await event_manager.connect_rabbitmq()
        
        # Load plugins
        await plugin_manager.init_plugins()
        
        # Run the bot
        bot_instance.run()
    except Exception as e:
        logger.error(f"Error starting services: {e}")
        logger.debug(traceback.format_exc())
        raise


def handle_exit(signum, frame):
    """Handle exit signals"""
    logger.info(f"Received exit signal {signum}")
    # Raise KeyboardInterrupt to trigger shutdown
    raise KeyboardInterrupt


def main():
    """Main entry point"""
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    try:
        # Start the event loop
        loop = asyncio.get_event_loop()
        loop.run_until_complete(start_services())
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        logger.debug(traceback.format_exc())
        sys.exit(1)
    finally:
        # Clean up resources
        logger.info("Cleanup complete")


if __name__ == "__main__":
    main()
