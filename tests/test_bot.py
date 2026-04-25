"""Unit tests for the IRCBot class."""

import queue
import re
import socket
import ssl
import unittest
from unittest.mock import patch

import chardet
import requests
import validators
from bot import IRCBot, hello_command, join_command, log_resource_usage  # Assuming bot.py is in the same directory


class TestIRCBot(unittest.TestCase):
    """Test cases for the IRCBot class."""

    def setUp(self):
        """Set up for test methods."""
        self.bot = IRCBot("config.yaml")  # Assuming config.yaml is in the same directory

    def test_load_config(self):
        """Test that the config loads correctly."""
        self.bot._load_config()

    def test_connect(self):
        """Test connection to a server."""
        with patch.object(socket.socket, 'connect') as mock_connect:
            mock_connect.return_value = None  # Simulate successful connection
            self.assertTrue(self.bot.connect())

        with patch.object(ssl.SSLContext, 'wrap_socket') as mock_wrap_socket:
            mock_wrap_socket.return_value = None # Simulate SSL wraping
            self.bot.connect()

    def test_disconnect(self):
        """Test disconnection from a server."""
        with patch.object(socket.socket, "close") as mock_close:
            mock_close.return_value = None # Simulate disconnection
            self.assertTrue(self.bot.disconnect())

    def test_send_raw(self):
        """Test sending raw messages."""
        with patch.object(socket.socket, 'send') as mock_send:
            mock_send.return_value = None # Simulate sending a raw message
            self.bot.send_raw("TEST MESSAGE")

    def test_join_channel(self):
        """Test joining a channel."""
        with patch.object(socket.socket, 'send') as mock_send:
            mock_send.return_value = None # Simulate sending a raw message
            self.bot.join_channel("TESTCHANNEL")

    def test_send_message(self):
        """Test sending a message."""
        with patch.object(socket.socket, 'send') as mock_send:
            mock_send.return_value = None # Simulate sending a message
            self.bot.send_message("TEST", "TEST MESSAGE")

    def test_decode_data(self):
        """Test decoding data."""
        with patch.object(chardet, 'detect') as mock_detect:
            mock_detect.return_value = {'encoding': "utf-8", 'confidence': 1} # Simulate encoding detection
            self.bot._decode_data(b"TEST".decode("utf-8"))

    def test_handle_ping(self):
        """Test handling of PING messages."""
        with patch.object(socket.socket, 'send') as mock_send:
            mock_send.return_value = None # Simulate handling PING message
            self.bot._handle_ping("PING :TEST\r\n")
            self.assertEqual(self.bot.socket.send.call_count, 1)
            self.assertEqual(self.bot.socket.send.call_args, "PONG :TEST")

    def test_handle_join(self):
        """Test handling of JOIN messages."""
        self.bot.channels = ["#TEST"]
        self.bot._handle_join("TEST", "#TEST")
        self.assertEqual(self.bot.channels, ["#TEST"])

    def test_handle_ping_stats(self):
        """Test handling of PING message statistics."""
        self.bot._handle_ping_stats("PING :TEST\r\n", 0, 0)

    def test_handle_numeric_reply(self):
        """Test handling of numeric replies."""
        with patch.object(socket.socket, 'send') as mock_send:
            mock_send.return_value = None # Simulate sending a numeric message
            self.bot._handle_numeric_reply("473", "TEST")

    def test_get_url_info(self):
        """Test getting URL info."""
        with patch.object(requests, "get") as mock_get_url:
            mock_get_url.return_value = None # Simulate fetching URL
            self.bot._get_url_info("http://test.com")

    def test_handle_url(self):
        """Test handling of URLs."""
        with patch.object(validators, "url") as mock_url:
            mock_url.return_value = True # Simulate url validation
            self.bot._handle_url("http://test.com")

    def test_is_ping(self):
        """Test if a line is considered PING"""
        self.assertTrue(self.bot._is_ping("PING"))

    def test_find_join_match(self):
        """Test finding a JOIN match"""
        self.assertIsNotNone(self.bot._find_join_match(":TEST!USER@ TEST JOIN #TEST\r\n"))

    def test_find_numeric_match(self):
        """Test finding a numeric match"""
        self.assertIsNotNone(self.bot._find_numeric_match(":TEST!USER@ TEST 123 TEST\r\n"))

    def test_find_privmsg_match(self):
        """Test finding a PRIVMSG match"""
        self.assertIsNotNone(self.bot._find_privmsg_match(":TEST!USER@ TEST PRIVMSG #TEST :TEST\r\n"))

    def test_handle_privmsg(self):
        """Test handling of PRIVMSG messages."""
        with patch.object(re, "findall") as mock_findall:
            mock_findall.return_value = None # Simulate findall
            self.bot._handle_privmsg(":TEST!USER@ TEST PRIVMSG #TEST :TEST\r\n")

    def test_handle_privmsg_content(self):
        """Test handling of PRIVMSG content."""
        self.bot._handle_privmsg_content("TEST", "#TEST", "TEST")

    def test_process_data(self):
        """Test processing data."""
        with patch.object(IRCBot, "send_message") as mock_send_message, \
                patch.object(socket.socket, 'send') as mock_send:
            mock_send_message.return_value = None # Simulate sending a message
            mock_send.return_value = None # Simulate processing data
            self.bot.process_data(b"TEST")

    def test_register_command(self):
        """Test registering a command."""
        self.bot.register_command("TEST", lambda x: None)
        self.assertEqual(self.bot.command_handlers["test"], lambda x: None)

    def test_handle_command(self):
        """Test handling of commands."""
        self.bot.register_command("TEST", lambda x: None)
        self.bot.handle_command("TEST", "TEST", "TEST")

    def test_channel_worker(self):
        """Test the channel worker."""
        self.bot.running = False # Simulate working
        self.bot.channel_worker("TEST", queue.Queue())

    def test_run(self):
        """Test the main bot loop."""
        with patch.object(socket.socket, 'recv') as mock_recv, \
                patch.object(socket.socket, 'send') as mock_send:
            mock_recv.side_effect = ["TEST"] # Simulate receving data
            mock_send.return_value = None # Simulate sending data
            self.bot.running = False # Simulate working
            self.bot.run()

    def test_hello_command(self):
        """Test the hello command."""
        hello_command(self.bot, "TEST", "TEST")

    def test_join_command(self):
        """Test the join command."""
        join_command(self.bot, "TEST", "TEST", "#TEST")

    def test_log_resource_usage(self):
        """Test log resource usage"""
        log_resource_usage()

