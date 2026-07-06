"""
OpenBB Data Server — standalone FastAPI server providing market data
via OpenBB + yfinance. Runs independently of the main AgentX backend.

Start:   python openbb_server.py
API:     http://localhost:8101/api/openbb/prices
         http://localhost:8101/api/openbb/prices/{symbol}
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Ensure backend module is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.openbb_provider import get_all_forex_prices, get_forex_ohlc, ALL_PAIRS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("openbb_server")

app = FastAPI(title="OpenBB Data Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/openbb/prices")
async def list_prices():
    """Get latest prices for all tracked pairs/assets."""
    try:
        prices = get_all_forex_prices()
        return {
            "status": "ok",
            "source": "openbb + yfinance",
            "count": len(prices),
            "prices": prices,
        }
    except Exception as e:
        logger.error("Error fetching prices: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/openbb/prices/{symbol}")
async def get_price(symbol: str):
    """Get historical OHLC for a specific symbol (60 days)."""
    symbol = symbol.upper()
    if symbol not in ALL_PAIRS:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")
    try:
        data = get_forex_ohlc(symbol, days=60)
        if not data:
            raise HTTPException(status_code=502, detail=f"No data for {symbol}")
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching %s: %s", symbol, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok", "source": "openbb-server", "pairs": len(ALL_PAIRS)}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8101
    print(f"Starting OpenBB Data Server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
