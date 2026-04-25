import sqlite3
import time
import urllib.parse
from urllib.parse import urlparse
import requests
from loguru import logger
import os

DB_PATH = os.environ.get("CACHE_DB_PATH", os.path.join(os.path.dirname(__file__), "cache.db"))

def update_threat_db(config):
    """Downloads threat sources and updates the SQLite cache."""
    threat_config = config.get("threats", {})
    sources = threat_config.get("sources", [])
    if not sources:
        return

    logger.info("Starting background threat database update...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        for source in sources:
            if not source.get("enabled", False):
                continue
                
            name = source.get("name")
            url = source.get("url")
            stype = source.get("type")
            
            logger.info(f"Fetching threat source: {name} from {url}")
            
            try:
                # Set a reasonable timeout
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                
                domains_to_insert = []
                
                if stype == "urlhaus":
                    # Parse URLhaus hostfile format (127.0.0.1 domain)
                    for line in response.iter_lines():
                        line = line.decode('utf-8').strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split()
                        if len(parts) >= 2:
                            domain = parts[1].strip().lower()
                            domains_to_insert.append((domain, name, "Flagged for malware distribution", time.time()))
                            
                elif stype == "phishtank":
                    # Example implementation for future PhishTank support
                    pass
                
                if domains_to_insert:
                    # Clear out the old domains for this source before inserting new ones
                    # to keep the list fresh and remove domains that are no longer flagged
                    cursor.execute("DELETE FROM threat_domains WHERE source = ?", (name,))
                    cursor.executemany(
                        "INSERT OR REPLACE INTO threat_domains (domain, source, reason, timestamp) VALUES (?, ?, ?, ?)",
                        domains_to_insert
                    )
                    conn.commit()
                    logger.info(f"Successfully loaded {len(domains_to_insert)} malicious domains from {name}")
                    
            except Exception as e:
                logger.error(f"Failed to update threat source {name}: {e}")

def get_threat_info(url):
    """
    Checks if a URL belongs to a malicious domain.
    Returns (True, reason) if it is a threat, or (False, None) if safe.
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain:
            return False, None
            
        # Strip port if present
        if ':' in domain:
            domain = domain.split(':')[0]
            
        # Check the exact domain and parent domains
        parts = domain.split('.')
        domains_to_check = []
        
        # Add the full domain
        domains_to_check.append(domain)
        
        # Add parent domains (e.g. for sub.malware.com, also check malware.com)
        # But don't check TLDs like .com or .co.uk (simplified: keep at least 2 parts)
        for i in range(1, len(parts) - 1):
            parent = '.'.join(parts[i:])
            domains_to_check.append(parent)
            
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Use placeholders for the IN clause
            placeholders = ','.join(['?'] * len(domains_to_check))
            cursor.execute(
                f"SELECT reason, source FROM threat_domains WHERE domain IN ({placeholders})",
                domains_to_check
            )
            
            row = cursor.fetchone()
            if row:
                reason, source = row
                return True, f"{reason} (Source: {source})"
                
    except Exception as e:
        logger.error(f"Error checking threat for URL {url}: {e}")
        
    return False, None
