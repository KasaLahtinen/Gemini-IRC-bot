"""This module contains the IRCBot class and its related functions."""

import sys
import socket
import ssl
import re
import threading
import queue
import traceback
import mimetypes
import time
import psutil
import chardet
import validators
from collections import deque
from blessed import Terminal
import yaml
import requests
from bs4 import BeautifulSoup


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
            sys.exit(1)
        except yaml.YAMLError as e: #Catch yaml errors
            print(term.red(f"Error: Invalid YAML in configuration file: {e}"))
            sys.exit(1)

    def __init__(self, config_file="config.yaml"): #Set default to yaml
        """Initializes the IRC bot from a configuration file."""
        self.config_file = config_file
        self.config = self._load_config()
        self.socket = None
        self.running = True
        self.command_handlers = {}
        self.nickname = self.config["bot"]["nickname"]
        self.channels = self.config["bot"]["channels"]
        self.ping_stats = {"count": 0, "total_time": 0.0, "times": deque()}

        # Get thread_pool_size with a default value
#        self.thread_pool_size = self.config.get("thread_pool_size", 4)

    def resource_monitor(self, interval=600):
        """ Resource monitoring """
        while self.running:
            log_resource_usage()
            time.sleep(interval)

    def connect(self):
        """Connects to the IRC server with enhanced error handling."""
        try:
            if self.config['connection']["use_ssl"]:
                context = ssl.create_default_context()
                context.verify_mode = ssl.CERT_REQUIRED
                context.check_hostname = True
                context.load_default_certs()

                raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket = context.wrap_socket(
                    raw_socket, server_hostname=self.config['connection']["server"]
                )
            else:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            self.socket.settimeout(10)  # Set a timeout for the connect operation
            self.socket.connect((
                self.config['connection']["server"], self.config['connection']["port"]
            ))
            self.socket.settimeout(None)  # Remove timeout after successful connection

            if self.config['connection']["password"]:
                self.send_raw(f"PASS {self.config['connection']['password']}\r\n")
            self.send_raw(f"NICK {self.nickname}\r\n")
            self.send_raw(f"USER {self.nickname} 0 * :{self.nickname}\r\n")

            for channel in self.channels:
                self.join_channel(channel)

        except ssl.SSLError as e:
            print(term.red(f"SSL error connecting to "
                           f"{self.config['connection']['server']}:"
                           f"{self.config['connection']['port']}: {e}"))
            return False
        except socket.timeout:
            print(term.red(f"Connection to {self.config['connection']['server']}:"
                           f"{self.config['connection']['port']} timed out."))
            return False
        except socket.error as e:
            print(term.red(f"Error connecting to {self.config['connection']['server']}:"
                           f"{self.config['connection']['port']}: {e}"))
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

    def _handle_ping_stats(self, line, start_time, processing_time):
        """Handles PING messages and updates statistics."""
        self.ping_stats["count"] += 1
        self.ping_stats["total_time"] += processing_time
        self.ping_stats["times"].append(processing_time)

        if self.ping_stats["count"] % 10 == 0:
            avg_ping_time = self.ping_stats["total_time"] / self.ping_stats["count"]
            print(term.yellow(f"Average ping processing time: {avg_ping_time:.4f} seconds"))
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
            print(term.red(f"{error_messages[reply_code]} {reply_text}"))

    def _get_url_info(self, url):
        """Fetches URL, determines file type, and extracts HTML metadata."""
        try:
            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/119.0.0.0 Safari/537.36'
                )
            }
            response = requests.get(
                url,
                stream=True,
                timeout=5,
                headers=headers
            )
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

            content_type = response.headers.get('Content-Type')
            file_type, encoding = mimetypes.guess_type(url)
            print(term.green(f"Encoding: {encoding}"))
            print(term.green(f"Content-Type: {content_type}"))
            print(term.green(f"Guessed File Type: {file_type}"))

            if content_type and "text/html" in content_type:
                chunk_size = 1024
                content = b""
                for chunk in response.iter_content(chunk_size=chunk_size):
                    content += chunk
                    if len(content) > 1024 * 1024: #Limit to 1MB
                        print(term.yellow("HTML content truncated (1MB limit reached)."))
                        break
                soup = BeautifulSoup(content, "html.parser")
                title = soup.title.string.strip() if soup.title else None
                description_meta = soup.find("meta", attrs={"name": "description"})
                if not description_meta:
                    description_meta = soup.find("meta", attrs={"property": "og:description"})
                if description_meta and description_meta.has_attr("content"):
                    description = description_meta["content"].strip()
                else:
                    description = None
                return file_type, title, description

            return file_type, None, None

        except requests.exceptions.RequestException as e:
            print(term.red(f"Error fetching URL {url}: {e}"))
            return None, None, None
        #except Exception as e:
        #    print(term.red(f"An unexpected error occurred while processing url {url}: {e}"))
        traceback.print_exc()
        return None, None, None

    def _handle_url(self, url, target=None): # Target now optional
        """Handles URL detection and validation."""
        print(term.green(f"Detected URL: {url}"))
        if validators.url(url):
            print(term.green(f"{url} is a valid URL"))
            file_type, title, description = self._get_url_info(url)
            if file_type:
                print(term.green(f"File Type: {file_type}"))
            if title and target: #Only send message if target is given
                self.send_message(target, f"Title: {title}")
            if description and target: #Only send message if target is given
                self.send_message(target, f"Description: {description}")
        else:
            print(term.red(f"{url} is not a valid URL"))

    def _is_ping(self, line):
        return line.startswith("PING")

    def _find_join_match(self, line):
        return re.search(r"^:([^!]+)!.* JOIN :(.+)$", line)

    def _find_numeric_match(self, line):
        return re.search(r"^:[^ ]+ ([0-9]{3}) .+ :(.+)$", line)

    def _find_privmsg_match(self, line):
        return re.search(r"^:([^!]+)!.* PRIVMSG ([^ ]+) :(.+)$", line)

    def _handle_privmsg(self, match_privmsg):
        sender, target, message = match_privmsg.groups()

        url_regex = r"\b(https?:\/\/[^\s]+)"
        url_match = re.findall(url_regex, message)
        if url_match:
            for url in url_match:
                self._handle_url(url, target)

        self._handle_privmsg_content(sender, target, message) #Handle the message content

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
                print(f"Received: {line}")

                if self._is_ping(line):
<<<<<<< HEAD
                    processing_time = time.time()
                    self._handle_ping(line)
                    processing_time = time.time() - start_time
                    self._handle_ping_stats(line, start_time, processing_time)
                    start_time = time.time()
                    continue 
=======
                    start_time = time.time()
                    self._handle_ping(line)
                    processing_time = time.time() - start_time
                    self._handle_ping_stats(line, start_time, processing_time)
>>>>>>> origin/IDX

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

        except (UnicodeDecodeError, IOError, Exception) as e:
            print(term.red(f"Error in process_data: {e}"))
            traceback.print_exc()
        finally:
            # Handle stats for non ping messages
            if not self._is_ping(line):
                processing_time = time.time() - start_time
                print(term.yellow(f"Processed message in {processing_time:.4f} seconds"))


    # ... (rest of the IRCBot class and other functions)
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
        resource_thread = threading.Thread(target=self.resource_monitor, daemon=True)
        resource_thread.start()

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

def log_resource_usage():
    """ Log resource usage """
    process = psutil.Process()
    memory_info = process.memory_info()
    cpu_percent = process.cpu_percent(interval=1)
    print(term.blue(f"Memory usage: {memory_info.rss / 1024 / 1024:.2f} MB"))
    print(term.blue(f"CPU usage: {cpu_percent:.2f}%"))

if __name__ == "__main__":
    Bot = IRCBot()
#    Bot.register_command("!hello", hello_command)
#    Bot.register_command("!join", join_command)
    print(term.green("Starting bot .."))
    Bot.run()
