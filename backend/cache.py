import sqlite3
import json
import time
from typing import Optional, Dict, Any

class SQLiteCache:
    def __init__(self, db_path="movie_cache.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS cache (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        expiry INTEGER
                    )
                """)
        except Exception as e:
            print(f"Cache Init Error: {e}")

    def get(self, key: str) -> Optional[Dict]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT value, expiry FROM cache WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    value, expiry = row
                    if expiry > time.time():
                        return json.loads(value)
                    else:
                        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        except Exception:
            pass
        return None

    def set(self, key: str, value: Any, ttl=86400): # Default 24h
        try:
            expiry = int(time.time() + ttl)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, expiry) VALUES (?, ?, ?)",
                    (key, json.dumps(value), expiry)
                )
        except Exception:
            pass

# Initialize global cache
db_cache = SQLiteCache()
