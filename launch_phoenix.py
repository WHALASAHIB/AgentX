#!/usr/bin/env python3
"""
Gold Phoenix Launcher — runs the bot with clean bytecode.
Uses importlib to force fresh load of the module, avoiding any .pyc cache.
"""
import sys
import os
import traceback

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

# Force fresh import — no cached bytecode
import importlib.util

spec = importlib.util.spec_from_file_location(
    "phoenix_bot",
    os.path.join(os.getcwd(), "bots", "gold_phoenix_bot.py")
)
mod = importlib.util.module_from_spec(spec)

try:
    spec.loader.exec_module(mod)
    # Call the bot's main entry point
    mod.main()
except Exception:
    with open("bots/logs/phoenix_crash.log", "w") as f:
        traceback.print_exc(file=f)
    # Also print to stdout so background process captures it
    traceback.print_exc()
