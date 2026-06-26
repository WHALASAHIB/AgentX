from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

BRIDGE_BASE_URL = os.getenv("MT5_BRIDGE_URL", "http://127.0.0.1:5000")
REQUEST_TIMEOUT = 15.0


class BridgeClient:
    """
    HTTP client for the MT5 Bridge Service (localhost:5000).
    All methods raise HTTPException (503 or 404) on failure so the API
    layer can propagate them directly to the client.
    """

    def __init__(self, base_url: str = BRIDGE_BASE_URL):
        self.base_url = base_url.rstrip("/")

    async def _get(self, path: str) -> Any:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            try:
                resp = await client.get(f"{self.base_url}{path}")
                if resp.status_code == 404:
                    raise HTTPException(status_code=404, detail=resp.json().get("detail", "Not found"))
                if resp.status_code == 503:
                    raise HTTPException(status_code=503, detail=resp.json().get("detail", "Bridge: MT5 offline"))
                resp.raise_for_status()
                return resp.json()
            except httpx.RequestError as e:
                logger.warning("Bridge connection failed: %s", e)
                raise HTTPException(status_code=503, detail=f"Bridge unreachable: {e}")

    async def health(self) -> dict:
        return await self._get("/health")

    async def list_accounts(self) -> list[dict]:
        return await self._get("/api/v1/accounts")

    async def get_account(self, account_id: str) -> dict:
        result = await self._get(f"/api/v1/accounts/{account_id}")
        if isinstance(result, dict) and "login" in result:
            return result
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        return result

    async def get_positions(self, account_id: Optional[str] = None) -> list[dict]:
        if account_id:
            return await self._get(f"/api/v1/accounts/{account_id}/positions")
        accounts = await self.list_accounts()
        seen_tickets = set()
        all_positions = []
        for acct in accounts:
            try:
                pos = await self._get(f"/api/v1/accounts/{acct['id']}/positions")
                for p in pos:
                    tid = p.get("ticket") or p.get("id")
                    if tid is not None and tid not in seen_tickets:
                        seen_tickets.add(tid)
                        all_positions.append(p)
                    elif tid is None:
                        all_positions.append(p)
            except HTTPException:
                continue
        return all_positions

    async def get_trades(self, account_id: str, days: int = 30) -> list[dict]:
        return await self._get(f"/api/v1/accounts/{account_id}/history?days={days}")

    async def get_equity(self, account_id: str, days: int = 30) -> list[dict]:
        return await self._get(f"/api/v1/accounts/{account_id}/equity?days={days}")

    async def get_stats(self, account_id: str, days: int = 30) -> dict:
        return await self._get(f"/api/v1/accounts/{account_id}/stats?days={days}")

    async def get_tick(self, account_id: str, symbol: str) -> dict:
        return await self._get(f"/api/v1/accounts/{account_id}/tick/{symbol}")

    async def trade(self, request: dict) -> dict:
        """Execute a trade via the bridge's /api/v1/trade endpoint."""
        import httpx
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            try:
                resp = await client.post(f"{self.base_url}/api/v1/trade", json=request)
                if resp.status_code == 400:
                    return resp.json()
                resp.raise_for_status()
                return resp.json()
            except httpx.RequestError as e:
                logger.warning("Bridge trade failed: %s", e)
                raise HTTPException(status_code=503, detail=f"Bridge unreachable: {e}")


_bridge_client = BridgeClient()


def get_bridge() -> BridgeClient:
    return _bridge_client
