import os
import sys
import time
import re
import yaml
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import telebot
from loguru import logger
import validators
from link_preview import get_link_preview, DB_PATH

def load_config(config_file):
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        sys.exit(1)

config = load_config("config.yaml")

# Get token from env
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN or TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
    logger.error("TELEGRAM_BOT_TOKEN environment variable not set or invalid.")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN)
url_pool = ThreadPoolExecutor(max_workers=5)
cooldowns = {}

def process_url_worker(url, chat_id):
    logger.info(f"Detected URL: {url}")
    if validators.url(url):
        try:
            preview_text = get_link_preview(url, force_heavy=False)
            if preview_text:
                bot.send_message(chat_id, preview_text)
        except Exception as e:
            logger.error(f"Error generating preview for {url}: {e}")
    else:
        logger.error(f"{url} is not a valid URL")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text
    if not text:
        return
        
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # We do NOT have a /heavy command as per user request. The bot only relays url scraped info.
    last_scrape = cooldowns.get(user_id, 0)
    if time.time() - last_scrape < 5:
        logger.warning(f"Rate limited URL scrape for user {user_id}")
        return

    url_regex = r"\b(https?:\/\/[^\s]+)"
    urls = re.findall(url_regex, text)
    
    if urls:
        cooldowns[user_id] = time.time()
        for url in urls:
            url_pool.submit(process_url_worker, url, chat_id)

def broadcast_monitor(interval=2):
    """Monitors the SQLite broadcast queue and sends messages to Telegram chats."""
    chat_ids = config.get("telegram", {}).get("chat_ids", [])
    if not chat_ids:
        logger.warning("No telegram chat_ids configured for broadcasting.")
        # We still need to mark them as done so the IRC bot can delete them
    
    while True:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, message FROM broadcast_queue WHERE tg_status = 0")
                rows = cursor.fetchall()
                for row in rows:
                    msg_id, message = row
                    
                    if chat_ids:
                        logger.info(f"Broadcasting message to Telegram (ID: {msg_id})")
                        for chat_id in chat_ids:
                            try:
                                bot.send_message(chat_id, message)
                            except Exception as e:
                                logger.error(f"Failed to broadcast to {chat_id}: {e}")
                                
                    cursor.execute("UPDATE broadcast_queue SET tg_status = 1 WHERE id = ?", (msg_id,))
                    cursor.execute("DELETE FROM broadcast_queue WHERE status = 1 AND tg_status = 1")
                conn.commit()
        except sqlite3.OperationalError:
            pass # Table might not exist yet
        except Exception as e:
            logger.error(f"Error in telegram broadcast monitor: {e}")
        time.sleep(interval)

if __name__ == "__main__":
    logger.info("Starting Telegram Bot...")
    broadcast_thread = threading.Thread(target=broadcast_monitor, daemon=True)
    broadcast_thread.start()
    
    # Increase timeout to avoid connection errors
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
