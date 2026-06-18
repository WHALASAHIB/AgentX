from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional


class StaleDataCache:
    """
    Thread-safe cache that stores last-known-good snapshots per account.
    Returns cached data with stale=True when fresh data is unavailable.
    Never returns empty data if a prior fetch succeeded.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cache: dict[str, dict[str, Any]] = {}
        self._timestamps: dict[str, float] = {}
        self._stale_flags: set[tuple[str, str]] = set()

    def update(self, account_id: str, key: str, data: Any) -> None:
        with self._lock:
            self._cache[(account_id, key)] = data
            self._timestamps[(account_id, key)] = time.time()
            self._stale_flags.discard((account_id, key))

    def get(self, account_id: str, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._cache.get((account_id, key), default)

    def get_with_meta(self, account_id: str, key: str) -> dict[str, Any]:
        """
        Returns {data, stale, last_updated}.
        stale=True if no fresh data has ever been stored OR if mark_stale()
        was called since the last update.
        """
        with self._lock:
            data = self._cache.get((account_id, key))
            ts = self._timestamps.get((account_id, key))
            is_explicitly_stale = (account_id, key) in self._stale_flags
            if data is None:
                return {"data": None, "stale": True, "last_updated": None}
            last_dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
            return {"data": data, "stale": is_explicitly_stale, "last_updated": last_dt}

    def mark_stale(self, account_id: str, key: str) -> None:
        """
        Mark cached data as stale without removing it.
        Data remains available but consumers know it's from a prior session.
        """
        with self._lock:
            if (account_id, key) in self._cache:
                self._stale_flags.add((account_id, key))

    def clear_account(self, account_id: str) -> None:
        with self._lock:
            keys_to_remove = [k for k in self._cache if k[0] == account_id]
            for k in keys_to_remove:
                del self._cache[k]
                self._timestamps.pop(k, None)
                self._stale_flags.discard(k)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
            self._stale_flags.clear()


# Global cache instance
_cache = StaleDataCache()


def get_cache() -> StaleDataCache:
    return _cache
