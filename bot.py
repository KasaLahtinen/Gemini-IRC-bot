"""This module contains the IRCBot class and its related functions."""

import socket
import ssl
import re
import threading
import queue
import traceback
import chardet
import validators
from blessed import Terminal
import yaml
#import os

term = Terminal()


class IRCBot:
    """IRC Bot class"""

    def _load_config(self):
        """Loads the configuration from the YAML file."""
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)  # Use yaml.safe_load()
        except FileNotFoundError:
            print(term.red(f"Error: Configuration file '{self.config_file}' not found."))
            exit(1)
        except yaml.YAMLError as e: #Catch yaml errors
            print(term.red(f"Error: Invalid YAML in configuration file: {e}"))
            exit(1)

    def __init__(self, config_file="config.yaml"): #Set default to yaml
        """Initializes the IRC bot from a configuration file."""
        self.config_file = config_file
        self.config = self._load_config()
        self.socket = None
        self.running = True
        self.command_handlers = {}
        self.nickname = self.config["bot"]["nickname"]
        self.channels = self.config["bot"]["channels"]
        # Get thread_pool_size with a default value
        self.thread_pool_size = self.config.get("thread_pool_size", 4)

    def connect(self):
        """Connects to the IRC server with enhanced error handling."""
        try:
            if self.config["connection"]["use_ssl"]:
                context = ssl.create_default_context()
                context.verify_mode = ssl.CERT_REQUIRED
                context.check_hostname = True
                context.load_default_certs()

                raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket = context.wrap_socket(
                    raw_socket, server_hostname=self.config["connection"]["server"]
                )
            else:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            self.socket.settimeout(10)  # Set a timeout for the connect operation
            self.socket.connect((
                self.config["connection"]["server"], self.config["connection"]["port"]
            ))
            self.socket.settimeout(None)  # Remove timeout after successful connection

            if self.config["connection"]["password"]:
                self.send_raw(f"PASS {self.config['connection']['password']}\r\n")
            self.send_raw(f"NICK {self.nickname}\r\n")
            self.send_raw(f"USER {self.nickname} 0 * :{self.nickname}\r\n")

            for channel in self.channels:
                self.join_channel(channel)

        except ssl.SSLError as e:
            print(term.red(f"SSL error connecting to "
                           f"{self.config["connection"]['server']}:"
                           f"{self.config["connection"]['port']}: {e}"))
            return False
        except socket.timeout:
            print(term.red(f"Connection to {self.config["connection"]['server']}:"
                           f"{self.config["connection"]['port']} timed out."))
            return False
        except socket.error as e:
            print(term.red(f"Error connecting to {self.config["connection"]['server']}:"
                           f"{self.config["connection"]['port']}: {e}"))
            return False
        return True

    def disconnect(self):
        """Disconnects from the IRC server with error handling."""
        try:
            if self.socket:
                self.send_raw("QUIT :Goodbye\r\n")
                self.socket.close()
        except socket.error as e:
            print(term.red(f"Error during disconnection: {e}"))

    def send_raw(self, message):
        """Sends a raw message with error handling."""
        try:
            if self.socket:
                self.socket.send(message.encode("utf-8"))
            else:
                print(term.red("Socket is not connected. Cannot send message."))
        except socket.error as e:
            print(term.red(f"Error sending message: {e}"))
            self.reconnect()
        except UnicodeEncodeError as e:
            print(term.red(f"An unexpected error occurred while sending: {e}"))
            traceback.print_exc()

    def join_channel(self, channel):
        """Joins a channel with error handling."""
        try:
            self.send_raw(f"JOIN {channel}\r\n")
        except socket.error as e:
            print(term.red(f"Error joining channel {channel}: {e}"))

    def send_message(self, target, message):
        """Sends a message with error handling."""
        try:
            self.send_raw(f"PRIVMSG {target} :{message}\r\n")
        except (UnicodeEncodeError, IOError) as e:
            print(term.red(f"Error sending message to {target}: {e}"))

    def _decode_data(self, raw_data):
        """Decodes raw data, handling encoding errors."""
        try:
            return raw_data.decode("utf-8")
        except UnicodeDecodeError:
            encoding_result = chardet.detect(raw_data)
            encoding = encoding_result["encoding"]
            if encoding:
                decoded_data = raw_data.decode(encoding)
                print(term.green(f"Detected encoding: {encoding}"))
                return decoded_data
            decoded_data = raw_data.decode("latin-1", errors="replace")
            print(term.green("Fallback to latin-1"))
            return decoded_data
        except IOError as e:
            print(term.red(f"Error decoding data: {e}"))
            traceback.print_exc()
            decoded_data = raw_data.decode("latin-1", errors="replace")
            print(term.green("Fallback to latin-1"))
            return decoded_data

    def _handle_ping(self, line):
        """Handles PING messages."""
        self.send_raw(f"PONG {line.split()[1]}\r\n")

    def _handle_join(self, nick, channel):
        """Handles JOIN messages."""
        if nick == self.nickname:
            if channel not in self.channels:
                self.channels.append(channel)
            print(term.green(f"Bot successfully joined {channel}"))

    def _handle_numeric_reply(self, reply_code, reply_text):
        """Handles numeric replies (error codes)."""
        error_messages = {
            "473": "Error joining channel: Invite only.",
            "475": "Error joining channel: Bad channel key.",
            "471": "Error joining channel: Channel is full.",
            "403": "Error joining channel: No such channel.",
        }
        if reply_code in error_messages:
            print(term.red(f"{error_messages[reply_code]} {reply_text}"))

    def _handle_url(self, url):
        """Handles URL detection and validation."""
        print(term.green(f"Detected URL: {url}"))
        if validators.url(url):
            print(term.green(f"{url} is a valid URL"))
        else:
            print(term.red(f"{url} is not a valid URL"))

    def _handle_privmsg(self, sender, target, message):
        """Handles PRIVMSG (chat messages)."""
        if target == self.nickname:
            print(term.green(f"Private message from {sender}: {message}"))
            self.handle_command(sender, message)
        else:
            print(term.green(f"Message in {target} from {sender}: {message}"))
            self.handle_command(target, message, sender)

    def process_data(self, raw_data):
        """Processes incoming raw data."""
        try:
            data = self._decode_data(raw_data)

            for line in data.splitlines():
                line = line.strip()
                if not line:
                    continue
                print(f"Received: {line}")

                if line.startswith("PING"):
                    self._handle_ping(line)
                    continue

                match = re.search(r"^:([^!]+)!.* (JOIN) :(.+)$", line)
                if match:
                    nick = match.group(1)
                    channel = match.group(3)
                    self._handle_join(nick, channel)
                    continue

                match = re.search(r"^:[^ ]+ ([0-9]{3}) .+ :(.+)$", line)
                if match:
                    reply_code = match.group(1)
                    reply_text = match.group(2)
                    self._handle_numeric_reply(reply_code, reply_text)
                    continue

                url_match = re.findall(r"\b(https?:\/\/[^\s]+)", line)
                if url_match:
                    for url in url_match:
                        self._handle_url(url)

                match = re.search(r"^:([^!]+)!.* PRIVMSG ([^ ]+) :(.+)$", line)
                if match:
                    sender = match.group(1)
                    target = match.group(2)
                    message = match.group(3)
                    self._handle_privmsg(sender, target, message)

        except (UnicodeDecodeError, IOError) as e:
            print(term.red(f"Error in process_data: {e}"))
            traceback.print_exc()

    def handle_command(self, target, message, sender=None):
        """Handles user commands."""
        parts = message.split()
        if parts:
            command = parts[0].lower()
            args = parts[1:]
            if command in self.command_handlers:
                try:
                    self.command_handlers[command](self, target, sender, *args)
                except TypeError as e:
                    print(
                        term.red(
                            f"Error executing command {command}: {e}. Check function signature."
                        )
                    )
                except (ValueError, IOError) as e:
                    print(
                        term.red(
                            f"An error occurred while executing command {command}: {e}"
                        )
                    )
                    traceback.print_exc()

    def register_command(self, command, handler):
        """Registers a command handler."""
        self.command_handlers[command.lower()] = handler

    def channel_worker(self, channel, message_queue):
        """Worker thread for handling a specific channel."""
        try:
            while self.running:
                try:
                    message = message_queue.get(timeout=1.0)
                    self.process_data(message)
                except queue.Empty:
                    continue
                except (UnicodeDecodeError, IOError) as e:
                    print(term.red(f"Error processing message in {channel}: {e}"))
                    traceback.print_exc()
        except (UnicodeDecodeError, IOError) as e:
            print(term.red(f"Error in channel worker for {channel}: {e}"))
            traceback.print_exc()

    def reconnect(self):
        """Reconnects with enhanced error handling."""
        print(term.green("Reconnecting..."))
        self.disconnect()
        if not self.connect():
            print(term.red("Reconnection failed."))
            self.running = False

    def run(self):
        """Main bot loop with robust error handling and reconnection."""
        if not self.connect():
            print(term.red("Initial connection failed. Exiting."))
            return

        channel_queues = {channel: queue.Queue() for channel in self.channels}
        channel_threads = {}

        for channel, q in channel_queues.items():
            thread = threading.Thread(target=self.channel_worker, args=(channel, q))
            channel_threads[channel] = thread
            thread.daemon = True
            thread.start()

        try:
            while self.running:
                try:
                    raw_data = self.socket.recv(4096)
                    if not raw_data:
                        print(term.red("Connection lost."))
                        self.reconnect()
                        continue

                    for line in raw_data.split(b"\r\n"):
                        self.process_data(line)
                except socket.timeout:
                    print(term.red("Socket timed out while receiving data."))
                    self.reconnect()
                except socket.error as e:
                    print(term.red(f"Socket error: {e}"))
                    self.reconnect()
                except UnicodeDecodeError as e:
                    print(term.red(f"An unexpected error occurred in main loop: {e}"))
                    traceback.print_exc()
                    self.running = False
                    break
        except KeyboardInterrupt:
            print(term.red("Disconnecting..."))
            self.running = False
        finally:
            for thread in channel_threads.values():
                thread.join(timeout=2)
            self.disconnect()


def hello_command(bot, target, sender):
    """Responds with a greeting."""
    if sender:
        bot.send_message(target, f"Hello, {sender}!")
    else:
        bot.send_message(target, "Hello!")


def join_command(bot, target, sender, *args):
    """Makes the bot join a channel."""
    if sender and len(args) > 0:
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


if __name__ == "__main__":
    Bot = IRCBot()
    Bot.register_command("!hello", hello_command)
    Bot.register_command("!join", join_command)
    print(term.green("Starting bot .."))
    Bot.run()
