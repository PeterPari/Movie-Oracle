import sqlite3
import time
import json
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

    def get(self, key: str) -> Optional[Any]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT value, expiry FROM cache WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    value, expiry = row
                    if expiry > time.time():
                        try:
                            return json.loads(value)
                        except json.JSONDecodeError:
                            return value 
                    else:
                        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        except Exception:
            pass
        return None

    def set(self, key: str, value: Any, ttl=86400): # Default 24h
        try:
            expiry = int(time.time() + ttl)
            if isinstance(value, (dict, list)):
                storage_value = json.dumps(value)
            else:
                storage_value = str(value)
                
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, expiry) VALUES (?, ?, ?)",
                    (key, storage_value, expiry)
                )
        except Exception as e:
            print(f"Cache Set Error: {e}")

    def clear_prefix(self, prefix: str):
        """Delete all cache entries whose key starts with the given prefix."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM cache WHERE key LIKE ?", (f"{prefix}%",))
        except Exception as e:
            print(f"Cache Clear Error: {e}")

# Global instance
db_cache = SQLiteCache()
