from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Redis pub/sub client for real-time data distribution.
    Gracefully degrades when Redis is unavailable.
    """

    def __init__(self):
        self.host = os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", "6379"))
        self.password = os.getenv("REDIS_PASSWORD", "")
        self._client: Any = None
        self._pubsub: Any = None
        self._connected = False
        self._init()

    def _init(self):
        try:
            import redis.asyncio as aioredis
            self._client = aioredis.Redis(
                host=self.host,
                port=self.port,
                password=self.password or None,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            # Test the connection with a ping
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Already inside an async context — schedule the ping
                    asyncio.ensure_future(self._test_connection())
                    self._connected = True
                else:
                    loop.run_until_complete(self._client.ping())
                    self._connected = True
            except Exception:
                self._connected = False
                logger.warning("Redis server unreachable at %s:%s", self.host, self.port)
        except ImportError:
            logger.info("redis package not installed — running without Redis pub/sub")
        except Exception as e:
            logger.warning("Redis unavailable (%s) — running without Redis pub/sub", e)

    async def _test_connection(self):
        """Test Redis connection from within an async context."""
        try:
            await self._client.ping()
            self._connected = True
            logger.info("Redis connected: %s:%s", self.host, self.port)
        except Exception as e:
            self._connected = False
            logger.warning("Redis unreachable at %s:%s — %s", self.host, self.port, e)

    @property
    def connected(self) -> bool:
        return self._connected

    # ── Channels ──────────────────────────────────────────────────────────────
    # tick:{symbol}        — live price updates
    # positions:{account}  — position open/close/modify
    # bots:{name}          — bot status changes
    # events               — system-wide events

    async def publish(self, channel: str, message: dict) -> None:
        if not self._connected:
            return
        try:
            await asyncio.wait_for(self._client.publish(channel, json.dumps(message)), timeout=1)
        except asyncio.TimeoutError:
            logger.warning("Redis publish timeout on %s (server may be down)", channel)
            self._connected = False
        except Exception as e:
            logger.warning("Redis publish failed: %s", e)

    async def publish_tick(self, account_id: str, symbol: str, tick: dict) -> None:
        if not self._connected:
            return
        try:
            channel = f"tick:{symbol}:{account_id}"
            await asyncio.wait_for(self._client.publish(channel, json.dumps(tick)), timeout=1)
        except asyncio.TimeoutError:
            logger.warning("Redis tick publish timeout")
            self._connected = False
        except Exception as e:
            logger.warning("Redis tick publish failed: %s", e)
    async def publish_position_update(self, account_id: str, positions: list[dict]) -> None:
        await self.publish(f"positions:{account_id}", {
            "type": "position_update",
            "account_id": account_id,
            "data": positions,
        })

    async def publish_bot_status(self, bot_name: str, status: str, extra: dict = None) -> None:
        msg = {"type": "bot_status", "bot_name": bot_name, "status": status}
        if extra:
            msg.update(extra)
        await self.publish(f"bots:{bot_name}", msg)

    async def publish_system_event(self, event_type: str, severity: str, message: str) -> None:
        await self.publish("events", {
            "type": "system_event",
            "event_type": event_type,
            "severity": severity,
            "message": message,
        })

    async def subscribe(self, channels: list[str]) -> Any:
        """Returns an async pubsub object for the caller to iterate."""
        if not self._connected:
            return None
        try:
            pubsub = self._client.pubsub()
            await pubsub.subscribe(*channels)
            return pubsub
        except Exception as e:
            logger.warning("Redis subscribe failed: %s", e)
            return None

    async def close(self) -> None:
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
            self._connected = False


_redis = RedisClient()


def get_redis() -> RedisClient:
    return _redis
