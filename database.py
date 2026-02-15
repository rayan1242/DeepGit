import sqlite3
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_FILE = Path(__file__).resolve().parent / "deepgit.db"

def init_db():
    """Initialize the SQLite database and create tables if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Create key-value store for user config (e.g. auth tokens, client_id)
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_FILE}")

def get_config(key: str):
    """Retrieve a value by key."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT value FROM user_config WHERE key = ?', (key,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def set_config(key: str, value: str):
    """Store or update a value by key."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO user_config (key, value, updated_at)
        VALUES (?, ?, datetime('now'))
    ''', (key, value))
    conn.commit()
    conn.close()
    logger.info(f"Config '{key}' updated.")

def delete_config(key: str):
    """Delete a configuration key."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM user_config WHERE key = ?', (key,))
    conn.commit()
    conn.close()
    logger.info(f"Config '{key}' deleted.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
