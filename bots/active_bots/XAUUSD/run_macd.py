#!/usr/bin/env python3
"""
XAUUSD — MACD Crossover Bot
============================
Executes MACD Crossover strategy on XAUUSD (Gold).
Best-performing strategy across all backtested pairs.

Usage:
    python multi_symbol_bot.py --symbol XAUUSD --strategy macd
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from multi_symbol_bot import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--symbol", "XAUUSD", "--strategy", "macd"]
    main()
