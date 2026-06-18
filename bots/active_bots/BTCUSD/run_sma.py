#!/usr/bin/env python3
"""
BTCUSD — SMA Crossover Bot
===========================
BTCUSD benefits from trend-following SMA crossover.
SMA Crossover was weak on forex pairs but effective on BTCUSD.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from multi_symbol_bot import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--symbol", "BTCUSD", "--strategy", "sma"]
    main()
