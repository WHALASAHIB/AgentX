#!/usr/bin/env python3
"""
USDCHF — MACD Crossover Bot
============================
Gold Phoenix only CAUTIOUS on USDCHF. Using Bollinger Bands as second strategy.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from multi_symbol_bot import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--symbol", "USDCHF", "--strategy", "macd"]
    main()
