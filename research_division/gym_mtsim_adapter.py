#!/usr/bin/env python3
"""
AGENTX gym-mtsim Adapter — Research Division Module.

Integrates AminHP/gym-mtsim (OpenAI Gym + MetaTrader 5 Simulator) into our
research pipeline. Provides:

1. Data loading from live MT5 connection
2. MtSimulator creation with AGENTX symbols
3. MtSimTradingEnv for RL training / backtesting
4. Report generation to research_division/reports/
5. CLI mode:  python gym_mtsim_adapter.py --simulate --symbol XAUUSD --days 30

Usage (as module):
    from gym_mtsim_adapter import create_simulator, create_env, run_simulation
    sim = create_simulator(symbols=['XAUUSD', 'EURUSD'], days=60)
    env = create_env(sim, trading_symbols=['XAUUSD'], window_size=10)

Usage (CLI):
    python gym_mtsim_adapter.py --simulate        # Run 1 simulation cycle
    python gym_mtsim_adapter.py --simulate --symbol XAUUSD --days 90
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# Path setup
_SELF_DIR = Path(__file__).resolve().parent
_REPORTS_DIR = _SELF_DIR / "reports"
_STATE_DIR = _SELF_DIR / "state"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MT5SIM] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(_SELF_DIR / "gym_mtsim.log"), mode="a"),
    ],
)
logger = logging.getLogger("gym_mtsim_adapter")

HKT = timezone(timedelta(hours=8))
UTC = timezone.utc

# Symbols we trade
TRADED_SYMBOLS = [
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD", "NZDUSD",
]

MT5_CONFIG_PATH = Path("C:/Trading/mt5_config.json")


def load_mt5_data(symbol: str, days: int = 60, timeframe: int = 0) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data from live MT5 connection.

    Falls back to cached data on disk if MT5 is unavailable.
    Saves fetched data to cache for future offline use.

    Args:
        symbol: Trading symbol (e.g. 'XAUUSD')
        days: Days of historical data to fetch
        timeframe: MT5 timeframe constant (0 = M1, 5 = M5, 15 = M15, 60 = H1, etc.)

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume, or None on failure
    """
    # Check cache first
    cache_path = _STATE_DIR / f"ohlcv_{symbol}_{days}d_tf{timeframe}.parquet"
    _STATE_DIR.mkdir(parents=True, exist_ok=True)

    if cache_path.exists():
        try:
            df = pd.read_parquet(cache_path)
            logger.info(f"Loaded {len(df)} bars for {symbol} from cache ({cache_path})")
            return df
        except Exception as e:
            logger.warning(f"Cache read failed for {symbol}: {e}")

    try:
        import MetaTrader5 as mt5

        if not MT5_CONFIG_PATH.exists():
            logger.error(f"MT5 config not found: {MT5_CONFIG_PATH}")
            return None

        cfg = json.loads(MT5_CONFIG_PATH.read_text())
        initialized = mt5.initialize(
            path=cfg.get("terminal_path", "C:\\Program Files\\MetaTrader 5\\terminal64.exe"),
            login=int(cfg["login"]),
            password=cfg["password"],
            server=cfg["server"],
            timeout=30000,
        )
        if not initialized:
            err = mt5.last_error()
            logger.error(f"MT5 init failed for {symbol}: {err}")
            # Try without login params (use already-running terminal)
            mt5.shutdown()
            initialized = mt5.initialize(
                path=cfg.get("terminal_path", "C:\\Program Files\\MetaTrader 5\\terminal64.exe"),
                timeout=30000,
            )
            if not initialized:
                logger.error(f"MT5 init retry failed: {mt5.last_error()}")
                return None

        now = datetime.now()
        from_date = now - timedelta(days=days)
        rates = mt5.copy_rates_range(symbol, timeframe, from_date, now)
        mt5.shutdown()

        if rates is None or len(rates) == 0:
            logger.warning(f"No data for {symbol} from MT5")
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)

        df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "tick_volume": "Volume",
        }, inplace=True)

        # Save to cache
        try:
            df.to_parquet(cache_path)
            logger.info(f"Cached {len(df)} bars to {cache_path}")
        except Exception as e:
            logger.warning(f"Failed to cache {symbol}: {e}")

        logger.info(f"Loaded {len(df)} bars for {symbol} ({from_date.date()} to {now.date()})")
        return df[["Open", "High", "Low", "Close", "Volume"]]

    except ImportError:
        logger.error("MetaTrader5 package not installed")
        return None
    except Exception as e:
        logger.error(f"Failed to load {symbol}: {e}")
        return None


def create_simulator(
    symbols: list[str] = None,
    days: int = 60,
    timeframe: int = 0,
    balance: float = 10000.0,
    leverage: int = 100,
    hedge: bool = True,
    stop_out_level: float = 0.2,
):
    """Create an MtSimulator with live MT5 data.

    Requires gym-mtsim installed (pip install gym-mtsim).

    Args:
        symbols: List of symbols to include (default: AGENTX traded symbols)
        days: Days of historical data
        timeframe: MT5 timeframe constant
        balance: Starting balance
        leverage: Account leverage
        hedge: Enable hedging
        stop_out_level: Stop-out level %

    Returns:
        MtSimulator instance, or None if data loading fails
    """
    from gym_mtsim import MtSimulator

    symbols = symbols or TRADED_SYMBOLS
    sim = MtSimulator(
        balance=balance,
        leverage=leverage,
        hedge=hedge,
        stop_out_level=stop_out_level,
    )

    success_count = 0
    for symbol in symbols:
        df = load_mt5_data(symbol, days=days, timeframe=timeframe)
        if df is not None and len(df) > 100:
            # Create minimal SymbolInfo
            from gym_mtsim import SymbolInfo
            info = SymbolInfo(
                symbol=symbol,
                volume_min=0.01,
                volume_max=100.0,
                volume_step=0.01,
            )
            sim.symbols_info[symbol] = info
            sim.symbols_data[symbol] = df
            success_count += 1
            logger.info(f"Added {symbol} to simulator ({len(df)} bars)")
        else:
            logger.warning(f"Skipping {symbol}: insufficient data")

    if success_count == 0:
        logger.error("No symbols loaded — cannot create simulator")
        return None

    logger.info(f"Simulator ready: {success_count}/{len(symbols)} symbols, ${balance:,} balance")
    return sim


def create_env(sim, trading_symbols: list[str] = None, window_size: int = 20):
    """Create a gym-mtsim trading environment from an existing simulator.

    Args:
        sim: MtSimulator instance
        trading_symbols: Symbols to trade (must be a subset of sim.symbols_info)
        window_size: Observation window size

    Returns:
        MtSimTradingEnv instance
    """
    from gym_mtsim import MtSimTradingEnv

    trading_symbols = trading_symbols or list(sim.symbols_info.keys())

    env = MtSimTradingEnv(
        original_simulator=sim,
        trading_symbols=trading_symbols,
        window_size=window_size,
    )
    logger.info(f"Environment created: {trading_symbols}, window={window_size}")
    return env


def run_simulation(
    symbol: str = "XAUUSD",
    days: int = 60,
    window_size: int = 20,
) -> dict:
    """Run a full simulation cycle: load data, create simulator, step through environment.

    Args:
        symbol: Symbol to simulate
        days: Days of data
        window_size: Observation window

    Returns:
        Summary dict with results
    """
    logger.info(f"Starting simulation: {symbol} | {days}d | window={window_size}")

    # Phase 1: Create simulator with our data
    sim = create_simulator(symbols=[symbol], days=days)
    if sim is None:
        return {"status": "error", "error": "Failed to create simulator"}

    # Phase 2: Create environment
    env = create_env(sim, trading_symbols=[symbol], window_size=window_size)

    # Phase 3: Run a simple simulation (random actions — baseline)
    obs, info = env.reset()
    steps = min(len(env.simulator.symbols_data[symbol]) - window_size - 1, 500)
    done = False
    total_reward = 0.0
    trades_opened = 0

    for step in range(steps):
        if done:
            break
        # Simple strategy: alternate between hold (0), buy (1), sell (2)
        action = env.action_space.sample()  # random for baseline
        obs, reward, done, truncated, info = env.step(action)
        total_reward += reward
        if info.get("order_profits") and any(p != 0 for p in info["order_profits"]):
            trades_opened += 1

    # Phase 4: Collect results
    sim_data = env.simulator.symbols_data[symbol]
    start_price = sim_data.iloc[window_size]["Close"] if len(sim_data) > window_size else 0
    end_price = sim_data.iloc[-1]["Close"] if len(sim_data) > 0 else 0
    price_change_pct = ((end_price - start_price) / start_price * 100) if start_price else 0

    result = {
        "status": "completed",
        "symbol": symbol,
        "days": days,
        "steps": steps,
        "total_reward": round(total_reward, 2),
        "trades_opened": trades_opened,
        "start_price": round(start_price, 2),
        "end_price": round(end_price, 2),
        "price_change_pct": round(price_change_pct, 2),
        "final_balance": round(sim.balance, 2),
        "final_equity": round(sim.equity, 2),
        "timestamp": datetime.now(UTC).isoformat(),
        "timestamp_hkt": datetime.now(HKT).isoformat(),
    }

    env.close()
    logger.info(f"Simulation complete: reward={result['total_reward']}, "
                f"trades={result['trades_opened']}, equity=${result['final_equity']:,.2f}")
    return result


def _numpy_safe(obj):
    """Convert numpy types to native Python for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _numpy_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_numpy_safe(item) for item in obj]
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return _numpy_safe(obj.tolist())
    return obj


def save_report(result: dict):
    """Save simulation result as a report file."""
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(HKT).strftime("%Y%m%d_%H%M%S")
    report_path = _REPORTS_DIR / f"gym_mtsim_{result.get('symbol', 'all')}_{timestamp}.json"
    report_path.write_text(json.dumps(_numpy_safe(result), indent=2, default=str))
    logger.info(f"Report saved: {report_path}")

    # Also save a human-readable summary
    summary = (
        f"## gym-mtsim Simulation Report\n\n"
        f"**Symbol:** {result.get('symbol', 'N/A')}\n"
        f"**Period:** {result.get('days', 0)} days\n"
        f"**Steps:** {result.get('steps', 0)}\n\n"
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Total Reward | {result.get('total_reward', 0):+,.2f} |\n"
        f"| Trades Opened | {result.get('trades_opened', 0)} |\n"
        f"| Start Price | ${result.get('start_price', 0):,.2f} |\n"
        f"| End Price | ${result.get('end_price', 0):,.2f} |\n"
        f"| Price Change | {result.get('price_change_pct', 0):+.2f}% |\n"
        f"| Final Equity | ${result.get('final_equity', 0):,.2f} |\n\n"
        f"_Report generated: {result.get('timestamp_hkt', 'N/A')}_\n"
    )
    summary_path = _REPORTS_DIR / f"gym_mtsim_{result.get('symbol', 'all')}_{timestamp}.md"
    summary_path.write_text(summary)
    logger.info(f"Summary saved: {summary_path}")
    return summary_path


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="AGENTX gym-mtsim Adapter")
    parser.add_argument("--simulate", action="store_true", help="Run simulation")
    parser.add_argument("--symbol", default="XAUUSD", help="Symbol to simulate")
    parser.add_argument("--days", type=int, default=60, help="Days of data")
    parser.add_argument("--window", type=int, default=20, help="Observation window")
    parser.add_argument("--list-symbols", action="store_true", help="List available symbols")

    args = parser.parse_args()

    if args.list_symbols:
        print("Available symbols:")
        for s in TRADED_SYMBOLS:
            print(f"  {s}")
        return

    if args.simulate:
        result = run_simulation(
            symbol=args.symbol,
            days=args.days,
            window_size=args.window,
        )
        report_path = save_report(result)

        print(json.dumps(_numpy_safe(result), indent=2))
        print(f"\nReport: {report_path}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
