"""
AGENTX Backtester — Strategy Loader
Discovers built-in and custom strategy modules.
"""
import importlib
import inspect
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Absolute path to the backtester directory
BACKTESTER_DIR = Path(__file__).resolve().parent

# Built-in strategies are imported from here
BUILTIN_MODULES = ["strategies.sma_crossover", "strategies.bollinger_bands",
                   "strategies.macd_crossover", "strategies.ema_rsi_crossover",
                   "strategies.gold_phoenix"]


def list_strategies() -> dict:
    """
    Scan all available strategies (built-in + custom).
    
    Returns:
        dict mapping strategy_key -> strategy_class
    """
    strategies = {}

    # 1. Built-in strategies
    for mod_name in BUILTIN_MODULES:
        try:
            module = importlib.import_module(mod_name)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and (attr_name.lower().endswith("_strategy") or attr_name.lower().endswith("strategy")):
                    # Derive key: strip trailing _strategy OR just strategy
                    key = attr_name.lower()
                    for suffix in ["_strategy", "strategy"]:
                        if key.endswith(suffix):
                            key = key[: -len(suffix)]
                            break
                    strategies[key] = attr
        except ImportError:
            logger.debug("Built-in strategy module not available: %s", mod_name)
        except Exception as e:
            logger.warning("Error loading strategy %s: %s", mod_name, e)

    # 2. Custom strategies from the custom_strategies directory
    custom_dir = BACKTESTER_DIR / "custom_strategies"
    if custom_dir.exists():
        sys.path.insert(0, str(custom_dir))
        for f in sorted(custom_dir.iterdir()):
            if f.suffix == ".py" and not f.name.startswith("_"):
                mod_name = f.stem
                try:
                    module = importlib.import_module(mod_name)
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and (attr_name.lower().endswith("_strategy") or attr_name.lower().endswith("strategy")):
                            strategies[mod_name] = attr
                except Exception as e:
                    logger.warning("Error loading custom strategy %s: %s", mod_name, e)

    # 3. Fallback: if no strategies found, create a simple built-in default
    if not strategies:
        from strategies.default import DefaultStrategy
        strategies["default"] = DefaultStrategy

    logger.info("Loaded %d strategies: %s", len(strategies), list(strategies.keys()))
    return strategies


def get_default_params(strategy_class) -> dict:
    """Extract default init params from a strategy class."""
    try:
        sig = inspect.signature(strategy_class.__init__)
        params = {}
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.default is not inspect.Parameter.empty:
                params[name] = param.default
        return params
    except (ValueError, TypeError):
        return {}
