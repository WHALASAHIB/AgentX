#!/usr/bin/env python3
"""
XAUUSD — Volatility Contraction Breakout Bot
=============================================
Bollinger Squeeze volatility pattern exploitation on Gold.
Standalone bot — does not use multi_symbol_bot.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from volatility_breakout_bot import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--symbol", "XAUUSD", "--strategy", "volatilitybreakout"]
    main()
