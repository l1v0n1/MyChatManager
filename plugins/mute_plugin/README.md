# Mute Plugin for MyChatManager

Enhanced muting functionality with scheduled unmute and reasons tracking.

## Features

- `/tempmute` command for muting users with preset durations
- Inline keyboard with common mute durations
- Custom duration input
- Automatic unmuting when the time expires
- Reason tracking for audit logs

## Usage

1. Reply to a user's message with `/tempmute`
2. Select a duration from the preset options or choose "Custom" for a specific duration
3. Enter the reason for the mute
4. The user will be muted for the specified duration and automatically unmuted when it expires

## Examples

- `/tempmute` - Displays inline keyboard with preset durations
- Custom duration examples: `1h`, `30m`, `1d`, `10m30s`

## Requirements

- Requires moderator permissions to use
- Only works in group and supergroup chats

## Installation

1. Place the `mute_plugin` folder in your `plugins` directory
2. Add `mute_plugin` to the `PLUGINS_ENABLED` list in your settings

```python
# In settings.py
PLUGINS_ENABLED = ["mute_plugin"]
```

## How to Create Your Own Plugins

To create your own plugin for MyChatManager:

1. Create a new directory in the `plugins` folder with your plugin name
2. Create an `__init__.py` file with a class that extends `PluginBase`
3. Define your plugin's metadata
4. Implement the required methods (`activate`, `deactivate`, `get_handlers`, etc.)
5. Add your plugin to the `PLUGINS_ENABLED` setting

### Plugin Structure Example

```python
from app.plugins.plugin_manager import PluginBase, PluginMetadata

class MyPlugin(PluginBase):
    # Define plugin metadata
    metadata = PluginMetadata(
        name="my_plugin",
        version="1.0.0",
        description="My custom plugin description",
        author="Your Name",
        requires=[],  # List other plugins this one requires
        conflicts=[]  # List plugins this one conflicts with
    )
    
    def __init__(self, manager):
        super().__init__(manager)
        # Initialize your plugin
        
    async def activate(self) -> bool:
        # Code to run when plugin is activated
        return await super().activate()
    
    async def deactivate(self) -> bool:
        # Code to run when plugin is deactivated
        return await super().deactivate()
    
    def get_handlers(self) -> Dict[str, Callable]:
        # Return a dictionary of command handlers
        return {"my_command": self.my_command_handler}
    
    def get_middlewares(self) -> List[Any]:
        # Return a list of middlewares
        return []
        
    async def my_command_handler(self, message, state, **kwargs):
        # Your command handler implementation
        await message.reply("Hello from my custom plugin!")
``` 