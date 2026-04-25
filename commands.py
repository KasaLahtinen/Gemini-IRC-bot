# commands.py
"""This module contains the Command and CommandManager classes and related functions."""

import traceback

from loguru import logger


class Command:
    """Represents an IRC command."""

    def __init__(self, name, handler, help_text=None):
        self.name = name.lower()  # Store command name in lowercase
        self.handler = handler
        self.help_text = help_text

    def get_handler(self):
        """Returns the command handler."""
        return self.handler

    def execute(self, bot, target, sender, *args):
        """Executes the command handler."""
        try:
            self.handler(bot, target, sender, *args)
        except TypeError as e:
            logger.error(
                "Error executing command %s: %s. Check function signature.",
                self.name,
                e,
            )
        except (ValueError, IOError) as e:
            logger.error("An error occurred while executing command %s: %s", self.name, e)
        traceback.print_exc()


class CommandManager:
    """Manages IRC commands."""

    def __init__(self):
        self.commands = {}

    def register(self, command):
        """Registers a command."""
        if not isinstance(command, Command):
            raise TypeError("Expected a Command object")
        self.commands[command.name] = command

    def execute(self, bot, target, message, sender):
        """Executes a command from a message."""
        parts = message.split()
        if parts:
            command_name = parts[0].lower()
            args = parts[1:]
            if command_name in self.commands:
                self.commands[command_name].execute(bot, target, sender, *args)
            elif command_name.startswith("!"):
                logger.debug("Unknown command: %s", command_name)


# Example command functions (can be in separate files later)
def hello_command(bot, target, sender, *args):
    """Responds with a greeting."""
    if sender:
        bot.send_message(target, f"Hello, {sender}!")
    else:
        bot.send_message(target, "Hello!")
    logger.debug(args)


def join_command(bot, target, sender, *args):
    """Makes the bot join a channel."""
    if sender and args:
        channel_to_join = args[0]
        if not channel_to_join.startswith("#"):
            bot.send_message(target, "Channel names must start with #")
            return

        if channel_to_join in bot.channels:
            bot.send_message(target, f"I am already in {channel_to_join}")
            return

        bot.join_channel(channel_to_join)
        bot.send_message(target, f"Joining {channel_to_join} as requested by {sender}")
    else:
        bot.send_message(target, "Usage: !join #channel")
