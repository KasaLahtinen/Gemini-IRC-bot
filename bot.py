import socket
import ssl
import re
import threading
import queue
import chardet
import traceback
import validators
from blessed import Terminal

term = Terminal()

class IRCBot:
    def __init__(self, server, port, nickname, channels, use_ssl=False, password=None):
        """Initializes the IRC bot."""
        self.server = server
        self.port = port
        self.nickname = nickname
        self.channels = channels
        self.use_ssl = use_ssl
        self.password = password
        self.socket = None
        self.running = True
        self.command_handlers = {}
    
    def connect(self):
        """Connects to the IRC server with enhanced error handling."""
        try:
            if self.use_ssl:
                raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket = ssl.wrap_socket(raw_socket)
            else:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            self.socket.settimeout(10)  # Set a timeout for the connect operation
            self.socket.connect((self.server, self.port))
            self.socket.settimeout(None)  # Remove timeout after successful connection

            if self.password:
                self.send_raw(f"PASS {self.password}\r\n")
            self.send_raw(f"NICK {self.nickname}\r\n")
            self.send_raw(f"USER {self.nickname} 0 * :{self.nickname}\r\n")

            for channel in self.channels:
                self.join_channel(channel)

        except socket.timeout:
            print(f"Connection to {self.server}:{self.port} timed out.")
            return False
        except socket.error as e:
            print(f"Error connecting to {self.server}:{self.port}: {e}")
            return False
        return True

    def disconnect(self):
        """Disconnects from the IRC server with error handling."""
        try:
            if self.socket:
                self.send_raw("QUIT :Goodbye\r\n")
                self.socket.close()
        except socket.error as e:
            print(f"Error during disconnection: {e}")
    def send_raw(self, message):
        """Sends a raw message with error handling."""
        try:
            if self.socket:
                self.socket.send(message.encode('utf-8'))
            else:
                print("Socket is not connected. Cannot send message.")
        except socket.error as e:
            print(f"Error sending message: {e}")
            self.reconnect()
        except Exception as e:
            print(f"An unexpected error occurred while sending: {e}")
            traceback.print_exc()

    def join_channel(self, channel):
        """Joins a channel with error handling."""
        try:
            self.send_raw(f"JOIN {channel}\r\n")
        except Exception as e:
            print(f"Error joining channel {channel}: {e}")

    def send_message(self, target, message):
        """Sends a message with error handling."""
        try:
            self.send_raw(f"PRIVMSG {target} :{message}\r\n")
        except Exception as e:
            print(f"Error sending message to {target}: {e}")

    def send_raw(self, message):
        """Sends a raw message with error handling."""
        try:
            if self.socket:
                self.socket.send(message.encode('utf-8'))
            else:
                print("Socket is not connected. Cannot send message.")
        except socket.error as e:
            print(f"Error sending message: {e}")
            self.reconnect()
        except Exception as e:
            print(f"An unexpected error occurred while sending: {e}")
            traceback.print_exc()

    def join_channel(self, channel):
        """Joins a specific channel."""
        try:
            self.send_raw(f"JOIN {channel}\r\n")
            return True # Assume the join command was sent successfully
        except Exception as e:
            print(f"Error sending JOIN command for {channel}: {e}")
            traceback.print_exc()
            return False

    def send_message(self, target, message):
        """Sends a message with error handling."""
        try:
            self.send_raw(f"PRIVMSG {target} :{message}\r\n")
        except Exception as e:
            print(f"Error sending message to {target}: {e}")

    def process_data(self, raw_data):
        """Processes incoming raw data, handles encoding errors, JOIN responses, and URLs."""
        try:
            try:
                data = raw_data.decode('utf-8')
            except UnicodeDecodeError:
                encoding_result = chardet.detect(raw_data)
                encoding = encoding_result['encoding']
                if encoding:
                    data = raw_data.decode(encoding)
                    print(f"Detected encoding: {encoding}")
                else:
                    data = raw_data.decode('latin-1', errors='replace')
                    print("Fallback to latin-1")
            except Exception as e:
                print(f"Error decoding data: {e}")
                traceback.print_exc()
                data = raw_data.decode('latin-1', errors='replace')
                print("Fallback to latin-1")

            for line in data.splitlines():
                line = line.strip()
                if not line:
                    continue
                print(f"Received: {line}")

                if line.startswith("PING"):
                    self.send_raw(f"PONG {line.split()[1]}\r\n")
                    continue

                match = re.search(r"^:([^!]+)!.* (JOIN) :(.+)$", line)
                if match:
                    nick = match.group(1)
                    command = match.group(2)
                    channel = match.group(3)
                    if nick == self.nickname:
                        if channel not in self.channels:
                            self.channels.append(channel)
                        print(f"Bot successfully joined {channel}")
                    continue

                match = re.search(r"^:[^ ]+ ([0-9]{3}) .+ :(.+)$", line)
                if match:
                    reply_code = match.group(1)
                    reply_text = match.group(2)
                    if reply_code == "473":
                        print(f"Error joining channel: Invite only. {reply_text}")
                    elif reply_code == "475":
                        print(f"Error joining channel: Bad channel key. {reply_text}")
                    elif reply_code == "471":
                        print(f"Error joining channel: Channel is full. {reply_text}")
                    elif reply_code == "403":
                        print(f"Error joining channel: No such channel. {reply_text}")
                    continue

                # Handle URL detection (HTTP/HTTPS only)
                url_match = re.findall(r"\b(https?:\/\/[^\s]+)", line)
                if url_match:
                    for url in url_match:
                        print(f"Detected URL: {url}")
                        if validators.url(url):
                            print(f"{url} is a valid URL")
                            # Example: Send a message to the channel
                            # self.send_message(target, f"Detected URL: {url}")
                        else:
                            print(f"{url} is not a valid URL")

                match = re.search(r"^:([^!]+)!.* PRIVMSG ([^ ]+) :(.+)$", line)
                if match:
                    sender = match.group(1)
                    target = match.group(2)
                    message = match.group(3)

                    if target == self.nickname:
                        print(f"Private message from {sender}: {message}")
                        self.handle_command(sender, message)
                    else:
                        print(f"Message in {target} from {sender}: {message}")
                        self.handle_command(target, message, sender)

        except Exception as e:
            print(f"Error in process_data: {e}")
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
                    print(f"Error executing command {command}: {e}. Check function signature.")
                except Exception as e:
                    print(f"An error occurred while executing command {command}: {e}")
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
                except Exception as e:
                    print(f"Error processing message in {channel}: {e}")
                    traceback.print_exc()
        except Exception as e:
            print(f"Error in channel worker for {channel}: {e}")
            traceback.print_exc()

    def reconnect(self):
        """Reconnects with enhanced error handling."""
        print("Reconnecting...")
        self.disconnect()
        if not self.connect():
            print("Reconnection failed.")
            self.running = False
            return

    def run(self):
        """Main bot loop with robust error handling and reconnection."""
        if not self.connect():
            print("Initial connection failed. Exiting.")
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
                        print("Connection lost.")
                        self.reconnect()
                        continue

                    for line in raw_data.split(b'\r\n'):
                        self.process_data(line)
                except socket.timeout:
                    print("Socket timed out while receiving data.")
                    self.reconnect()
                except socket.error as e:
                    print(f"Socket error: {e}")
                    self.reconnect()
                except Exception as e:
                    print(f"An unexpected error occurred in main loop: {e}")
                    traceback.print_exc()
                    self.running = False
                    break
        except KeyboardInterrupt:
            print("Disconnecting...")
            self.running = False
        finally:
            for thread in channel_threads.values():
                thread.join(timeout=2)
            self.disconnect()

def hello_command(bot, target, sender, *args):
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
    server = "10.0.3.11"  # Example server
    port = 6667  # Example SSL port, use 6667 for non-SSL
    nickname = "MyPythonBot"  # Change this
    channels = ["#hades"]  # Change this
    password = None  # Set if the server requires a password
    use_ssl = False

    bot = IRCBot(server, port, nickname, channels, use_ssl, password)
    bot.register_command("!hello", hello_command)
    bot.register_command("!join", join_command)
    print(term.green("Starting bot .."))
    bot.run()