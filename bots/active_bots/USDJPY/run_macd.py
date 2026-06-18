#!/usr/bin/env python3
"""
USDJPY — MACD Crossover Bot
============================
Note: Gold Phoenix failed on USDJPY. Using SMA Crossover as second strategy.
Risk: 21.9% max drawdown — use conservative lot sizing (0.8% risk default).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from multi_symbol_bot import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--symbol", "USDJPY", "--strategy", "macd"]
    main()
