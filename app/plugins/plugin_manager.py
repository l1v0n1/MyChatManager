import os
import importlib
import inspect
import pkgutil
from typing import Dict, List, Optional, Any, Callable, Type
from loguru import logger
import traceback
from pydantic import BaseModel

from app.config.settings import settings


class PluginMetadata(BaseModel):
    """Plugin metadata"""
    name: str
    version: str
    description: str
    author: str
    requires: List[str] = []
    conflicts: List[str] = []


class PluginBase:
    """Base class for all plugins"""
    
    # Plugin metadata
    metadata: PluginMetadata = PluginMetadata(
        name="base_plugin",
        version="0.1.0",
        description="Base plugin class",
        author="Plugin Developer",
    )
    
    def __init__(self, manager: 'PluginManager'):
        self.manager = manager
        self.is_active = False
    
    async def activate(self) -> bool:
        """Activate the plugin"""
        self.is_active = True
        logger.info(f"Plugin {self.metadata.name} v{self.metadata.version} activated")
        return True
    
    async def deactivate(self) -> bool:
        """Deactivate the plugin"""
        self.is_active = False
        logger.info(f"Plugin {self.metadata.name} deactivated")
        return True
    
    def get_handlers(self) -> Dict[str, Callable]:
        """Get plugin command handlers"""
        return {}
    
    def get_middlewares(self) -> List[Any]:
        """Get plugin middlewares"""
        return []
    
    def __str__(self) -> str:
        return f"{self.metadata.name} v{self.metadata.version}"


class PluginManager:
    """Manager for loading and managing plugins"""
    
    def __init__(self):
        """Initialize the plugin manager"""
        self.plugins: Dict[str, PluginBase] = {}
        self.active_plugins: Dict[str, PluginBase] = {}
        self.plugin_dirs = [
            os.path.join(os.path.dirname(__file__), "plugins"),  # Built-in plugins
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "plugins")  # External plugins
        ]
    
    async def discover_plugins(self) -> List[str]:
        """
        Discover available plugins in the plugin directories
        Returns list of plugin names found
        """
        plugin_names = []
        
        for plugin_dir in self.plugin_dirs:
            if not os.path.exists(plugin_dir):
                continue
            
            for _, name, is_pkg in pkgutil.iter_modules([plugin_dir]):
                if is_pkg:
                    plugin_names.append(name)
        
        logger.info(f"Discovered {len(plugin_names)} plugins: {', '.join(plugin_names)}")
        return plugin_names
    
    async def load_plugin(self, plugin_name: str) -> Optional[PluginBase]:
        """
        Load a plugin by name
        Returns the plugin instance if successful, None otherwise
        """
        if plugin_name in self.plugins:
            logger.warning(f"Plugin {plugin_name} is already loaded")
            return self.plugins[plugin_name]
        
        # Try to find and load the plugin module
        plugin_module = None
        plugin_class = None
        
        for plugin_dir in self.plugin_dirs:
            module_path = f"{plugin_dir}.{plugin_name}"
            try:
                plugin_module = importlib.import_module(module_path)
                break
            except ImportError:
                continue
        
        if not plugin_module:
            logger.error(f"Could not import plugin module {plugin_name}")
            return None
        
        # Find plugin class (must be a subclass of PluginBase)
        for name, obj in inspect.getmembers(plugin_module):
            if (inspect.isclass(obj) and 
                issubclass(obj, PluginBase) and 
                obj is not PluginBase):
                plugin_class = obj
                break
        
        if not plugin_class:
            logger.error(f"No plugin class found in module {plugin_name}")
            return None
        
        # Create plugin instance
        try:
            plugin = plugin_class(self)
            self.plugins[plugin_name] = plugin
            logger.info(f"Loaded plugin: {plugin}")
            return plugin
        except Exception as e:
            logger.error(f"Error creating plugin instance {plugin_name}: {e}")
            logger.debug(traceback.format_exc())
            return None
    
    async def activate_plugin(self, plugin_name: str) -> bool:
        """
        Activate a plugin by name
        Returns True if successful, False otherwise
        """
        # Load plugin if not already loaded
        if plugin_name not in self.plugins:
            plugin = await self.load_plugin(plugin_name)
            if not plugin:
                return False
        else:
            plugin = self.plugins[plugin_name]
        
        # Check if already active
        if plugin_name in self.active_plugins:
            logger.warning(f"Plugin {plugin_name} is already active")
            return True
        
        # Check dependencies
        for dependency in plugin.metadata.requires:
            if dependency not in self.active_plugins:
                # Try to activate dependency
                if not await self.activate_plugin(dependency):
                    logger.error(f"Could not activate required dependency {dependency} for plugin {plugin_name}")
                    return False
        
        # Check conflicts
        for conflict in plugin.metadata.conflicts:
            if conflict in self.active_plugins:
                logger.error(f"Plugin {plugin_name} conflicts with active plugin {conflict}")
                return False
        
        # Activate the plugin
        try:
            if await plugin.activate():
                self.active_plugins[plugin_name] = plugin
                logger.info(f"Activated plugin: {plugin}")
                return True
            else:
                logger.error(f"Plugin {plugin_name} activation failed")
                return False
        except Exception as e:
            logger.error(f"Error activating plugin {plugin_name}: {e}")
            logger.debug(traceback.format_exc())
            return False
    
    async def deactivate_plugin(self, plugin_name: str) -> bool:
        """
        Deactivate a plugin by name
        Returns True if successful, False otherwise
        """
        if plugin_name not in self.active_plugins:
            logger.warning(f"Plugin {plugin_name} is not active")
            return True
        
        plugin = self.active_plugins[plugin_name]
        
        # Check if any active plugins depend on this one
        for active_name, active_plugin in self.active_plugins.items():
            if plugin_name in active_plugin.metadata.requires:
                logger.error(f"Cannot deactivate {plugin_name}: Plugin {active_name} depends on it")
                return False
        
        # Deactivate the plugin
        try:
            if await plugin.deactivate():
                del self.active_plugins[plugin_name]
                logger.info(f"Deactivated plugin: {plugin}")
                return True
            else:
                logger.error(f"Plugin {plugin_name} deactivation failed")
                return False
        except Exception as e:
            logger.error(f"Error deactivating plugin {plugin_name}: {e}")
            logger.debug(traceback.format_exc())
            return False
    
    async def get_all_plugin_handlers(self) -> Dict[str, Callable]:
        """Get command handlers from all active plugins"""
        handlers = {}
        
        for plugin_name, plugin in self.active_plugins.items():
            plugin_handlers = plugin.get_handlers()
            
            # Add plugin name as a prefix to avoid conflicts
            for command, handler in plugin_handlers.items():
                handlers[f"{plugin_name}.{command}"] = handler
        
        return handlers
    
    async def get_all_plugin_middlewares(self) -> List[Any]:
        """Get middlewares from all active plugins"""
        middlewares = []
        
        for plugin_name, plugin in self.active_plugins.items():
            plugin_middlewares = plugin.get_middlewares()
            middlewares.extend(plugin_middlewares)
        
        return middlewares
    
    async def init_plugins(self) -> None:
        """Initialize plugins from settings"""
        plugins_to_load = settings.app.plugins_enabled
        
        if not plugins_to_load:
            logger.info("No plugins configured for loading")
            return
        
        for plugin_name in plugins_to_load:
            await self.activate_plugin(plugin_name)


# Create singleton instance
plugin_manager = PluginManager()
