import sqlite3
import time
import json
import threading
from typing import Optional, Any

class SQLiteCache:
    def __init__(self, db_path="movie_cache.db"):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()
        self.clear_expired()

    def _get_conn(self):
        """Get thread-local connection for connection pooling."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for concurrent reads
            conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes, still safe
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        try:
            conn = self._get_conn()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    expiry INTEGER
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_expiry ON cache(expiry)")
            conn.commit()
        except Exception as e:
            print(f"Cache Init Error: {e}")

    def clear_expired(self):
        """Remove all expired cache entries."""
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM cache WHERE expiry < ?", (int(time.time()),))
            conn.commit()
        except Exception as e:
            print(f"Cache Cleanup Error: {e}")

    def get(self, key: str) -> Optional[Any]:
        try:
            conn = self._get_conn()
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
                    conn.commit()
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
                
            conn = self._get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expiry) VALUES (?, ?, ?)",
                (key, storage_value, expiry)
            )
            conn.commit()
        except Exception as e:
            print(f"Cache Set Error: {e}")

    def clear_prefix(self, prefix: str):
        """Delete all cache entries whose key starts with the given prefix."""
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM cache WHERE key LIKE ?", (f"{prefix}%",))
            conn.commit()
        except Exception as e:
            print(f"Cache Clear Error: {e}")

# Global instance
db_cache = SQLiteCache()
