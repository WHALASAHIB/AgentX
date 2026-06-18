#!/usr/bin/env python3
"""
BTCUSD — MACD Crossover Bot
============================
3 bots recommended due to crypto volatility and multiple valid strategies.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from multi_symbol_bot import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--symbol", "BTCUSD", "--strategy", "macd"]
    main()
