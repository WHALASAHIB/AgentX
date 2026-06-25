#!/usr/bin/env python3
"""
Run script for Propfirm Pass Strategy — EURUSD London Open VWAP Mean Reversion.
"""

import sys
import os

# Add bot directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from propfirm_pass_bot import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--symbol", "EURUSD", "--strategy", "propfirmpass"]
    main()
