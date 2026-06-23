#!/usr/bin/env python3
"""
AUDUSD — Bollinger Bands Bot
=============================
Gold Phoenix only UNCERTAIN on AUDUSD. Using Bollinger Bands as mean reversion backup.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from multi_symbol_bot import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--symbol", "AUDUSD", "--strategy", "bollinger"]
    main()
