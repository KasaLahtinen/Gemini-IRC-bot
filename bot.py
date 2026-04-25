# bot.py
"""This module contains the IRCBot class and its related functions."""

import queue

# import ssl
import re
import socket
import sys
import threading
import time
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import chardet
import psutil
import validators
import yaml
from commands import (
    Command,
    CommandManager,
    heavy_command,
    hello_command,
)  # Import the command classes
from connection import Connection
from link_preview import get_link_preview
from loguru import logger


class IRCBot:
    """IRC Bot class"""

    def _load_config(self, config_file):
        """Loads the configuration from the YAML file."""
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)  # Use yaml.safe_load()
        except FileNotFoundError:
            logger.error(f"Error: Configuration file '{config_file}' not found.")
            sys.exit(1)
        except yaml.YAMLError as e:  # Catch yaml errors
            logger.error(f"Error: Invalid YAML in configuration file: {e}")
            sys.exit(1)

    def __init__(self):  # Set default to yaml
        """Initializes the IRC bot from a configuration file."""
        #        self.config_file = config_file
        self.config = self._load_config("config.yaml")
        use_ssl = self.config.get("use_ssl", False)
        self.connection = Connection(
            self.config["connection"]["server"],
            self.config["connection"]["port"],
            self.config["bot"]["nickname"],
            use_ssl=use_ssl,
        )
        #        self.socket = None
        self.running = True
        #        self.command_handlers = {}
        self.nickname = self.config["bot"]["nickname"]
        self.channels = self.config["bot"]["channels"]
        self.ping_stats = {"count": 0, "total_time": 0.0, "times": deque()}
        self.cooldowns = {}
        self.heavy_cooldowns = {}
        self.command_manager = CommandManager()  # Create CommandManager instance
        self.register_commands()

        self.url_pool = ThreadPoolExecutor(max_workers=5)

        # Get thread_pool_size with a default value

    #        self.thread_pool_size = self.config.get("thread_pool_size", 4)

    def register_commands(self):
        """Registers the commands through CommandManager"""
        self.command_manager.register(Command("!hello", hello_command, "Says hello"))
        self.command_manager.register(Command("!heavy", heavy_command, "Force heavy crawler for URL"))

    #        self.command_manager.register(Command("!join", join_command, "Joins a channel"))

    def handle_command(self, target, message, sender):
        """Calls the registered command from CommandManager"""
        self.command_manager.execute(self, target, message, sender)  # Use command manager to execute commands

    def resource_monitor(self, interval=600):
        """Resource monitoring"""
        while self.running:
            log_resource_usage()
            time.sleep(interval)

    def broadcast_monitor(self, interval=2):
        """Monitors the SQLite broadcast queue and sends messages to channels."""
        import sqlite3
        from link_preview import DB_PATH
        while self.running:
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, message FROM broadcast_queue WHERE status = 0")
                    rows = cursor.fetchall()
                    for row in rows:
                        msg_id, message = row
                        logger.info(f"Broadcasting message from queue (ID: {msg_id})")
                        for channel in self.channels:
                            self.send_message(channel, message)
                        cursor.execute("UPDATE broadcast_queue SET status = 1 WHERE id = ?", (msg_id,))
                        cursor.execute("DELETE FROM broadcast_queue WHERE status = 1 AND tg_status = 1")
                    conn.commit()
            except sqlite3.OperationalError:
                pass # Table might not exist yet
            except Exception as e:
                logger.error(f"Error in broadcast monitor: {e}")
            time.sleep(interval)

    def connect(self):
        """Connects to the IRC server."""
        self.connection.connect()
        # Removed immediate join_channel calls; we will join upon 001 RPL_WELCOME.
        return self.connection.sock

    def disconnect(self):
        """Disconnects from the IRC server."""
        self.connection.disconnect()

    def send_raw(self, data):
        """Sends raw data to the IRC server."""
        self.connection.send_raw(data)

    def join_channel(self, channel):
        """Joins a channel with error handling."""
        try:
            self.send_raw(f"JOIN {channel}\r\n")
        except socket.error as e:
            logger.error(f"Error joining channel {channel}: {e}")

    def send_message(self, target, message):
        """Sends a message with error handling."""
        try:
            self.send_raw(f"PRIVMSG {target} :{message}\r\n")
        except (UnicodeEncodeError, IOError) as e:
            logger.error(f"Error sending message to {target}: {e}")

    def _decode_data(self, raw_data):
        """Decodes raw data, handling encoding errors."""
        try:
            return raw_data.decode("utf-8")
        except UnicodeDecodeError:
            encoding_result = chardet.detect(raw_data)
            encoding = encoding_result["encoding"]
            if encoding:
                decoded_data = raw_data.decode(encoding)
                logger.info(f"Detected encoding: {encoding}")
                return decoded_data
            decoded_data = raw_data.decode("latin-1", errors="replace")
            logger.info("Fallback to latin-1")
            return decoded_data
        except IOError as e:
            logger.error(f"Error decoding data: {e}")
            traceback.print_exc()
            decoded_data = raw_data.decode("latin-1", errors="replace")
            logger.info("Fallback to latin-1")
            return decoded_data

    def _handle_ping(self, line):
        """Handles PING messages."""
        self.send_raw(f"PONG {line.split()[1]}\r\n")

    def _handle_join(self, nick, channel):
        """Handles JOIN messages."""
        if nick == self.nickname:
            if channel not in self.channels:
                self.channels.append(channel)
            logger.info(f"Bot successfully joined {channel}")

    def _handle_ping_stats(self, processing_time):
        """Handles PING messages and updates statistics."""
        self.ping_stats["count"] += 1
        self.ping_stats["total_time"] += processing_time
        self.ping_stats["times"].append(processing_time)

        if self.ping_stats["count"] % 10 == 0:
            avg_ping_time = self.ping_stats["total_time"] / self.ping_stats["count"]
            logger.warning(f"Average ping processing time: {avg_ping_time:.4f} seconds")
            self.ping_stats["count"] = 0
            self.ping_stats["total_time"] = 0.0
            self.ping_stats["times"].clear()

    def _handle_numeric_reply(self, reply_code, reply_text):
        """Handles numeric replies (error codes)."""
        error_messages = {
            "473": "Error joining channel: Invite only.",
            "475": "Error joining channel: Bad channel key.",
            "471": "Error joining channel: Channel is full.",
            "403": "Error joining channel: No such channel.",
        }
        if reply_code in error_messages:
            logger.error(f"{error_messages[reply_code]} {reply_text}")

        # 433: Nickname is already in use
        # 437: Nick/channel is temporarily unavailable
        if reply_code in ["433", "437"]:
            alt_nick = self.config["bot"].get("alt_nickname")
            if alt_nick and self.nickname != alt_nick and not self.nickname.endswith("_"):
                self.nickname = alt_nick
            else:
                self.nickname += "_"
            logger.warning(f"Nickname unavailable ({reply_code}). Trying new nick: {self.nickname}")
            self.send_raw(f"NICK {self.nickname}\r\n")

        # 001: RPL_WELCOME (Registration successful)
        if reply_code == "001":
            logger.info("Successfully registered with server. Joining channels...")
            for channel in self.channels:
                self.join_channel(channel)

    def _handle_url(self, url, target=None, sender=None):  # Target and sender optional
        """Handles URL detection and validation by delegating to a thread pool."""
        if sender:
            # We assume sender is just the nickname part.
            sender_nick = sender.split("!")[0]
            last_scrape = self.cooldowns.get(sender_nick, 0)
            if time.time() - last_scrape < 5:
                logger.warning(f"Rate limited URL scrape for {sender_nick}")
                return
            self.cooldowns[sender_nick] = time.time()
        self.url_pool.submit(self._process_url_worker, url, target)

    def _handle_heavy_url(self, url, target=None, sender=None):
        """Forces heavy crawler for a URL."""
        if sender:
            sender_nick = sender.split("!")[0]
            last_scrape = self.heavy_cooldowns.get(sender_nick, 0)
            if time.time() - last_scrape < 30:
                logger.warning(f"Rate limited heavy scrape for {sender_nick}")
                return
            self.heavy_cooldowns[sender_nick] = time.time()
        self.url_pool.submit(self._process_heavy_url_worker, url, target)

    def _process_heavy_url_worker(self, url, target=None):
        """Worker method for heavy URL parsing to avoid blocking."""
        logger.info(f"Detected heavy URL: {url}")
        if validators.url(url):
            logger.info(f"{url} is a valid URL")
            preview_text = get_link_preview(url, force_heavy=True)
            if preview_text and target:
                for line in preview_text.splitlines():
                    if line.strip():
                        self.send_message(target, line.strip())
        else:
            logger.error(f"{url} is not a valid URL")

    def _process_url_worker(self, url, target=None):
        """Worker method for URL parsing to avoid blocking."""
        logger.info(f"Detected URL: {url}")
        if validators.url(url):
            logger.info(f"{url} is a valid URL")
            preview_text = get_link_preview(url)
            if preview_text and target:  # Only send message if target is given
                for line in preview_text.splitlines():
                    if line.strip():
                        self.send_message(target, line.strip())
        else:
            logger.error(f"{url} is not a valid URL")

    def _is_ping(self, line):
        return line.startswith("PING")

    def _is_pong(self, line):
        return line.startswith("PONG")

    def _find_join_match(self, line):
        return re.search(r"^:([^!]+)!.* JOIN :(.+)$", line)

    def _find_numeric_match(self, line):
        return re.search(r"^:[^ ]+ ([0-9]{3}) .+ :(.+)$", line)

    def _find_privmsg_match(self, line):
        return re.search(r"^:([^!]+)!.* PRIVMSG ([^ ]+) :(.+)$", line)

    def _handle_privmsg(self, match_privmsg):
        sender, target, message = match_privmsg.groups()

        # Ignore messages sent by the bot itself to prevent loops
        if sender == self.nickname:
            return

        # If the bot is PM'd directly, reply to the sender instead of the bot's own nick
        reply_target = sender if target == self.nickname else target

        url_regex = r"\b(https?:\/\/[^\s]+)"
        url_match = re.findall(url_regex, message)
        
        # Prevent default scraper from firing if the user explicitly used !heavy
        is_heavy_command = message.strip().lower().startswith("!heavy")
        
        if url_match and not is_heavy_command:
            for url in url_match:
                self._handle_url(url, reply_target, sender)

        self._handle_privmsg_content(sender, reply_target, message)  # Handle the message content

    def _handle_privmsg_content(self, sender, target, message):
        """Handles the actual content of a PRIVMSG (commands, etc.)."""
        self.handle_command(target, message, sender)

    def process_data(self, raw_data):
        """Processes incoming raw data and process URL. It also handle PING messages."""
        start_time = time.time()
        try:
            data = self._decode_data(raw_data)
            line = ""
            for line in data.splitlines():
                line = line.strip()
                if not line:
                    continue
                logger.info(f"Received: {line}")

                if self._is_ping(line):
                    processing_time = time.time()
                    self._handle_ping(line)
                    processing_time = time.time() - start_time
                    self._handle_ping_stats(processing_time)
                    start_time = time.time()
                    continue

                if match_join := self._find_join_match(line):
                    nick, channel = match_join.groups()
                    self._handle_join(nick, channel)
                    continue

                if match_numeric := self._find_numeric_match(line):
                    self._handle_numeric_reply(match_numeric.group(1), match_numeric.group(2))
                    continue

                if match_privmsg := self._find_privmsg_match(line):
                    self._handle_privmsg(match_privmsg)
                    continue

                # Handle other message types or URL detection in other messages
                url_match = re.findall(r"\b(https?:\/\/[^\s]+)", line)
                if url_match:
                    for url in url_match:
                        self._handle_url(url)

        except (UnicodeDecodeError, IOError) as e:
            logger.error(f"Error in process_data: {e}")
            traceback.print_exc()
        finally:
            # Handle stats for non ping messages
            if not self._is_ping(line) and not self._is_pong(line):
                processing_time = time.time() - start_time
                logger.warning(f"Processed message in {processing_time:.4f} seconds")

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
                    logger.error(f"Error processing message in {channel}: {e}")
                    traceback.print_exc()
        except (UnicodeDecodeError, IOError) as e:
            logger.error(f"Error in channel worker for {channel}: {e}")
            traceback.print_exc()

    def reconnect(self):
        """Reconnects with enhanced error handling."""
        logger.info("Reconnecting...")
        self.disconnect()
        if not self.connect():
            logger.error("Reconnection failed.")
            self.running = False

    def run(self):
        """Main bot loop with robust error handling and reconnection."""
        if not self.connect():
            logger.error("Initial connection failed. Exiting.")
            return

        channel_queues = {channel: queue.Queue() for channel in self.channels}
        channel_threads = {}

        for channel, q in channel_queues.items():
            thread = threading.Thread(target=self.channel_worker, args=(channel, q))
            channel_threads[channel] = thread
            thread.daemon = True
            thread.start()
        resource_thread = threading.Thread(target=self.resource_monitor, daemon=True)
        resource_thread.start()
        
        broadcast_thread = threading.Thread(target=self.broadcast_monitor, daemon=True)
        broadcast_thread.start()

        try:
            while self.running:
                try:
                    raw_data = self.connection.recv_data()
                    if not raw_data:
                        logger.error("Connection lost.")
                        self.reconnect()
                        continue

                    for line in raw_data.split(b"\r\n"):
                        self.process_data(line)
                except socket.timeout:
                    logger.error("Socket timed out while receiving data.")
                    self.reconnect()
                except socket.error as e:
                    logger.error(f"Socket error: {e}")
                    self.reconnect()
                except UnicodeDecodeError as e:
                    logger.error(f"An unexpected error occurred in main loop: {e}")
                    traceback.print_exc()
                    self.running = False
                    break
        except KeyboardInterrupt:
            logger.error("Disconnecting...")
            self.running = False
        finally:
            for thread in channel_threads.values():
                thread.join(timeout=2)
            self.disconnect()


def log_resource_usage():
    """Log resource usage"""
    process = psutil.Process()
    memory_info = process.memory_info()
    cpu_percent = process.cpu_percent(interval=1)
    logger.info(f"Memory usage: {memory_info.rss / 1024 / 1024:.2f} MB")
    logger.info(f"CPU usage: {cpu_percent:.2f}%")


if __name__ == "__main__":
    Bot = IRCBot()
    #    Bot.register_command("!hello", hello_command)
    #    Bot.register_command("!join", join_command)
    logger.info("Starting bot ..")
    Bot.run()
