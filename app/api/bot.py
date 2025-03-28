from typing import Optional, Union, Dict, Any
import asyncio
from loguru import logger
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from app.config.settings import settings
from app.api.handlers import register_handlers
from app.api.middlewares import (
    UserContextMiddleware,
    RateLimitMiddleware,
    LoggingMiddleware
)


# Global bot instance
bot: Optional[Bot] = None
dp: Optional[Dispatcher] = None


async def setup_bot() -> Bot:
    """Initialize and configure the bot"""
    global bot, dp
    
    # Create storage
    try:
        if settings.redis.REDIS_URL:
            # Try to connect to Redis first
            import redis.asyncio
            try:
                # Test the connection
                redis_client = redis.asyncio.from_url(settings.redis.REDIS_URL, decode_responses=True)
                await redis_client.ping()
                
                # If successful, use Redis storage
                storage = RedisStorage.from_url(
                    url=settings.redis.REDIS_URL,
                    connection_kwargs={
                        "decode_responses": True
                    }
                )
                logger.info("Using Redis storage for FSM")
                await redis_client.close()
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}. Using in-memory storage instead.")
                storage = MemoryStorage()
                logger.info("Using in-memory storage for FSM")
        else:
            storage = MemoryStorage()
            logger.info("Using in-memory storage for FSM")
    except Exception as e:
        logger.error(f"Error configuring storage: {e}")
        storage = MemoryStorage()
        logger.info("Fallback to in-memory storage for FSM due to error")
    
    # Create bot instance
    bot = Bot(
        token=settings.bot.TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Create dispatcher
    dp = Dispatcher(storage=storage)
    
    # Register middlewares
    dp.update.middleware(LoggingMiddleware())
    dp.update.middleware(UserContextMiddleware())
    dp.message.middleware(RateLimitMiddleware())
    
    # Register core handlers
    register_handlers(dp)
    
    # Initialize plugin manager and register plugin handlers
    try:
        from app.plugins.plugin_manager import PluginManager
        
        # Create plugin manager
        plugin_manager = PluginManager()
        
        # Initialize plugins
        await plugin_manager.init_plugins()
        
        # Register plugin routers if available
        for plugin_name, plugin in plugin_manager.active_plugins.items():
            if hasattr(plugin, 'router'):
                dp.include_router(plugin.router)
                logger.info(f"Registered router for plugin: {plugin_name}")
            
        logger.info(f"Loaded {len(plugin_manager.active_plugins)} plugins: {', '.join(plugin_manager.active_plugins.keys())}")
    except Exception as e:
        logger.error(f"Error loading plugins: {e}")
    
    # Set commands
    await setup_bot_commands(bot)
    
    return bot


async def setup_bot_commands(bot: Bot) -> None:
    """Setup bot commands in the menu"""
    from aiogram.types import BotCommand
    
    commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="help", description="Show available commands"),
        BotCommand(command="rules", description="Show chat rules"),
        BotCommand(command="report", description="Report a message (reply to it)"),
    ]
    
    await bot.set_my_commands(commands)
    logger.info("Bot commands have been set")


async def start_bot(skip_updates: bool = True) -> None:
    """Start the bot polling for updates"""
    global bot, dp
    
    if not bot or not dp:
        bot = await setup_bot()
    
    logger.info("Starting bot polling...")
    
    try:
        # Start polling
        await dp.start_polling(
            bot,
            skip_updates=skip_updates,
            allowed_updates=[
                "message",
                "edited_message",
                "callback_query",
                "chat_member",
                "my_chat_member",
            ],
        )
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise
    finally:
        # Close bot session
        if bot:
            await bot.session.close()


async def stop_bot() -> None:
    """Stop the bot gracefully"""
    global bot
    
    logger.info("Stopping bot...")
    
    if bot:
        await bot.session.close()
        
    logger.info("Bot stopped")
