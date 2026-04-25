"""Module for generating link previews and communicating with the heavy crawler."""

import mimetypes
import os
import sqlite3
import time
import traceback

import requests
from bs4 import BeautifulSoup
from loguru import logger

DB_PATH = os.path.join(os.path.dirname(__file__), "cache.db")


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS url_cache (
                url TEXT PRIMARY KEY,
                preview TEXT,
                timestamp REAL
            )
            """
        )
        conn.commit()


init_db()


def trigger_heavy_crawler(url):
    """Helper to invoke the Selenium AI heavy crawler."""
    logger.warning(f"Triggering heavy crawler for {url}...")
    try:
        crawler_url = os.environ.get("CRAWLER_API_URL", "http://127.0.0.1:8000/resolve")
        heavy_response = requests.post(crawler_url, json={"url": url}, timeout=60)
        heavy_response.raise_for_status()
        if heavy_response.json().get("summary"):
            return heavy_response.json()["summary"]
    except Exception as heavy_err:
        logger.error(f"Heavy crawler failed: {heavy_err}")
    return None


def get_link_preview(url, force_heavy=False) -> str | None:
    """Fetches URL, determines file type, extracts HTML metadata, and returns a formatted preview."""

    if not force_heavy:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT preview, timestamp FROM url_cache WHERE url = ?", (url,))
                row = cursor.fetchone()
                if row:
                    preview, timestamp = row
                    if time.time() - timestamp < 86400:  # 24 hours
                        logger.info("Returning cached preview.")
                        return preview
        except Exception as e:
            logger.error(f"Error reading from cache: {e}")

    file_type = None
    title = None
    description = None

    try:
        if force_heavy:
            summary = trigger_heavy_crawler(url)
            if summary:
                title = "AI Summary"
                description = summary
        else:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/119.0.0.0 Safari/537.36"
                )
            }
            response = requests.get(url, stream=True, timeout=5, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

            content_type = response.headers.get("Content-Type")
            file_type, encoding = mimetypes.guess_type(url)
            logger.info(f"Encoding: {encoding}")
            logger.info(f"Content-Type: {content_type}")
            logger.info(f"Guessed File Type: {file_type}")

            if content_type and "text/html" in content_type:
                chunk_size = 1024
                content = b""
                for chunk in response.iter_content(chunk_size=chunk_size):
                    content += chunk
                    if len(content) > 1024 * 1024:  # Limit to 1MB
                        logger.warning("HTML content truncated (1MB limit reached).")
                        break
                soup = BeautifulSoup(content, "html.parser")

                title_tag = soup.title
                if title_tag and title_tag.string:
                    title = title_tag.string.strip()

                description_meta = soup.find("meta", attrs={"name": "description"})
                if not description_meta:
                    description_meta = soup.find("meta", attrs={"property": "og:description"})
                if description_meta and description_meta.has_attr("content"):
                    description = description_meta["content"].strip()

                title_lower = title.lower() if title else ""
                cookie_walls = [
                    "just a moment...",
                    "accept cookies",
                    "attention required!",
                    "ennen kuin jatkat",
                    "before you continue",
                ]

                if not title or any(wall in title_lower for wall in cookie_walls):
                    logger.warning("Possible cookie wall or missing title.")
                    summary = trigger_heavy_crawler(url)
                    if summary:
                        title = "AI Summary"
                        description = summary

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching URL {url}: {e}")
        if hasattr(e, "response") and e.response is not None and e.response.status_code in [401, 403, 406, 429, 503]:
            logger.warning(f"Blocked by server ({e.response.status_code}). Falling back to heavy crawler...")
            summary = trigger_heavy_crawler(url)
            if summary:
                title = "AI Summary"
                description = summary
    except Exception:
        traceback.print_exc()

    # Format the response
    parts = []
    if title:
        parts.append(title)
    if description:
        parts.append(description)

    final_preview = "\n".join(parts) if parts else None

    if final_preview:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO url_cache (url, preview, timestamp) VALUES (?, ?, ?)",
                    (url, final_preview, time.time()),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error writing to cache: {e}")

    return final_preview
