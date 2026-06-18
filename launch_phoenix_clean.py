#!/usr/bin/env python3
"""Stub launcher — just clears caches and runs the bot."""
import os
import sys
import shutil

# Clean all bytecode caches
bot_dir = os.path.join(os.path.dirname(__file__), "bots")
for root, dirs, files in os.walk(bot_dir):
    for d in dirs:
        if d == "__pycache__":
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
    for f in files:
        if f.endswith(".pyc"):
            os.remove(os.path.join(root, f))

# Set PYTHONDONTWRITEBYTECODE
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

# Run the bot as a subprocess — fresh interpretation every time
bot_script = os.path.join(bot_dir, "gold_phoenix_bot.py")
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.execve(sys.executable, [sys.executable, "-B", bot_script], os.environ)
