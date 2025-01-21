# connection.py
"""Handles core IRC connection"""

import socket
from ssl import create_default_context


class Connection:
    """
    A class to handle IRC connections, supporting both SSL and non-SSL.
    """

    def __init__(self, server, port, nickname, use_ssl=False):
        self.server = server
        self.port = port
        self.nickname = nickname
        self.use_ssl = use_ssl
        self.sock = None

    def connect(self):
        """Connects to the IRC server using SSL (if specified)."""
        context = None
        if self.use_ssl:
            context = create_default_context()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(2)  # Set timeout to avoid hanging connections
        print(f"Connecting to {self.server}:{self.port}...")
        try:
            self.sock.connect((self.server, self.port))
            if self.use_ssl:
                self.sock = context.wrap_socket(self.sock)
            print("Connected!")
            self.sock.settimeout(None)
        except IOError as e:
            print(f"Connection failed: {e}")
            self.sock = None
            return False
        try:
            self.send_raw(f"NICK {self.nickname}\r\n")
            self.send_raw(f"USER {self.nickname} 0 * :{self.nickname}\r\n")
            # for channel in self.channels:
            # self.join_channel(channel)
        except IOError as e:
            print(e)
            return False
        return True

    def disconnect(self):
        """Disconnects from the IRC server."""
        if self.sock:
            print("Disconnecting...")
            try:
                self.sock.sendall(b"QUIT\r\n")
                self.sock.close()
            except IOError as e:
                print(f"Error disconnecting: {e}")
            self.sock = None

    def send_raw(self, data):
        """Sends raw data to the IRC server."""
        if self.sock:
            try:
                data_bytes = data.encode("utf-8")
                self.sock.sendall(data_bytes)
            except IOError as e:
                print(f"Error sending data: {e}")

    def recv_data(self):
        """Receives data from the IRC server."""
        if self.sock:
            try:
                data = self.sock.recv(4096)  # .decode("utf-8")
                return data
            except IOError as e:
                print(f"Error receiving data: {e}")
                return e
        return False
