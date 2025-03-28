# MyChatManager - Telegram Bot

MyChatManager is a powerful Telegram bot for managing chat groups with advanced moderation features.

## Features

- 👮‍♀️ **Moderation Tools**: Warn, mute, kick, and ban users with reason tracking
- 🔍 **Spam Detection**: Automatically detect and remove spam messages
- 🤖 **Automated Tasks**: Schedule announcements, purge old messages, and more
- 🌐 **Multi-language Support**: Interact with users in their preferred language
- 📊 **Analytics**: Track chat activity and user statistics
- 🔌 **Plugin System**: Extend functionality with custom plugins

## Commands

The bot offers a variety of commands for different user roles:

### General Commands
- `/start` - Start the bot and get welcome message
- `/help` - Show help message with available commands
- `/rules` - Show chat rules and guidelines
- `/report` - Report a message (reply to it)

### Moderator Commands
- `/warn` - Warn a user (reply to their message)
- `/mute` - Temporarily mute a user
- `/unmute` - Unmute a user
- `/kick` - Remove user from chat

### Admin Commands
- `/ban` - Ban a user permanently
- `/unban` - Remove a ban
- `/promote` - Promote user to moderator
- `/demote` - Demote moderator to regular user
- `/settings` - Configure chat settings

## Installation

1. Clone the repository:
```bash
git clone https://github.com/l1v0n1/MyChatManager.git
cd MyChatManager
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
```
Edit the `.env` file and add your Telegram Bot Token and other settings.

4. Run the bot:
```bash
python run.py
```

## Plugin System

MyChatManager supports a plugin system that allows you to extend its functionality without modifying the core code.

### Available Plugins

- **Mute Plugin**: Enhanced muting functionality with preset durations and scheduled unmutes
  - Adds `/tempmute` command with inline keyboard for duration selection

### Enabling Plugins

Add the plugins you want to enable in your `.env` file:

```
PLUGINS_ENABLED=mute_plugin,your_plugin_name
```

Or set it directly in the settings:

```python
# In app/config/settings.py
PLUGINS_ENABLED = ["mute_plugin", "your_plugin_name"]
```

### Creating Custom Plugins

To create your own plugin:

1. Create a directory in the `plugins` folder with your plugin name
2. Create an `__init__.py` file with a class that extends `PluginBase`
3. Define your plugin's metadata and implement required methods
4. Add your plugin to the `PLUGINS_ENABLED` setting

See the [full plugin documentation](plugins/mute_plugin/README.md) for a detailed guide and example.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
