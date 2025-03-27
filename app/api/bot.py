from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.utils.executor import start_webhook, start_polling
import asyncio
from loguru import logger
import sys
from typing import Dict, Any, List, Optional, Union

from app.config.settings import settings
from app.api.handlers import register_handlers
from app.api.middlewares import UserUpdateMiddleware, ModerationMiddleware, MetricsMiddleware
from app.services.cache_service import cache_service
from app.events.event_manager import event_manager
from app.models.base import init_db


class Bot:
    """Main bot class"""
    
    def __init__(self):
        """Initialize bot"""
        self.token = settings.telegram.token
        
        # Create bot and dispatcher
        self.bot = Bot(token=self.token, parse_mode=types.ParseMode.HTML)
        
        # Choose storage depending on settings
        if settings.redis.url and not settings.app.debug:
            # Use Redis for production
            self.storage = RedisStorage2(
                host=settings.redis.url.split("://")[1].split(":")[0],
                port=int(settings.redis.url.split("://")[1].split(":")[1].split("/")[0]),
                db=int(settings.redis.url.split("://")[1].split("/")[1])
            )
            logger.info("Using Redis storage for FSM")
        else:
            # Use memory storage for development
            self.storage = MemoryStorage()
            logger.info("Using memory storage for FSM")
        
        self.dp = Dispatcher(self.bot, storage=self.storage)
        
        # Register middlewares
        self.setup_middlewares()
        
        # Register handlers
        register_handlers(self.dp)
    
    def setup_middlewares(self):
        """Set up middlewares"""
        # Add user update middleware
        self.dp.middleware.setup(UserUpdateMiddleware())
        
        # Add moderation middleware
        self.dp.middleware.setup(ModerationMiddleware())
        
        # Add metrics middleware (if not in debug mode)
        if not settings.app.debug:
            self.dp.middleware.setup(MetricsMiddleware())
    
    async def on_startup(self, dp: Dispatcher):
        """Startup actions"""
        logger.info("Starting up...")
        
        # Initialize database
        await init_db()
        
        # Connect to Redis for caching
        await cache_service.connect()
        
        # Connect to RabbitMQ for events
        await event_manager.connect_rabbitmq()
        
        # Set webhook if configured
        if settings.telegram.webhook_url:
            await self.bot.set_webhook(settings.telegram.webhook_url + settings.telegram.webhook_path)
            logger.info(f"Webhook set to {settings.telegram.webhook_url + settings.telegram.webhook_path}")
        
        logger.info("Bot startup complete")
    
    async def on_shutdown(self, dp: Dispatcher):
        """Shutdown actions"""
        logger.info("Shutting down...")
        
        # Close webhook if it was set
        if settings.telegram.webhook_url:
            await self.bot.delete_webhook()
        
        # Close Redis connections
        await cache_service.disconnect()
        
        # Close bot session
        await self.bot.close()
        
        logger.info("Bot shutdown complete")
    
    def run(self):
        """Run the bot"""
        if settings.telegram.webhook_url:
            # Webhook mode
            start_webhook(
                dispatcher=self.dp,
                webhook_path=settings.telegram.webhook_path,
                on_startup=self.on_startup,
                on_shutdown=self.on_shutdown,
                skip_updates=True,
                host='0.0.0.0',
                port=8443
            )
        else:
            # Polling mode
            start_polling(
                dispatcher=self.dp,
                on_startup=self.on_startup,
                on_shutdown=self.on_shutdown,
                skip_updates=True
            )


# Create bot instance
bot_instance = Bot()
