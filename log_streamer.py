"""
log_streamer.py — Real-time log file tail reader
Streams actual bot log files (gold_execution.log, streaming_bot output)
line-by-line into the dashboard terminal panel.
"""
from __future__ import annotations
import os
import time
import threading
from pathlib import Path
from collections import deque

LOG_FILES = {
    "Gold Bot (M5 Breakout)":     Path("logs/gold_execution.log"),
    "Streaming Bot (M1 Breakout)": Path("logs/streaming_bot.log"),
}

MAX_LINES = 200  # Keep last 200 lines in buffer per log


class LogStreamer:
    """
    Tails a log file in a background thread.
    Thread-safe line buffer accessible by the dashboard.
    """

    def __init__(self, log_path: Path, max_lines: int = MAX_LINES):
        self.log_path = log_path
        self.max_lines = max_lines
        self._buffer: deque[str] = deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._tail, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def get_lines(self) -> list[str]:
        with self._lock:
            return list(self._buffer)

    def _tail(self):
        """Tail the file from the end, pushing new lines into the buffer."""
        # First, load last MAX_LINES of existing content if file exists
        if self.log_path.exists():
            try:
                with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                    existing = f.readlines()
                    for line in existing[-self.max_lines:]:
                        with self._lock:
                            self._buffer.append(line.rstrip())
            except OSError:
                pass

        # Now tail for new lines
        while not self._stop.is_set():
            if not self.log_path.exists():
                time.sleep(1.0)
                continue
            try:
                with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(0, 2)  # Seek to end
                    while not self._stop.is_set():
                        line = f.readline()
                        if line:
                            with self._lock:
                                self._buffer.append(line.rstrip())
                        else:
                            time.sleep(0.2)
            except OSError:
                time.sleep(1.0)


# ── Global streamer instances ─────────────────────────────────────────────────

_streamers: dict[str, LogStreamer] = {}


def get_streamer(bot_name: str) -> LogStreamer:
    global _streamers
    if bot_name not in _streamers:
        log_path = LOG_FILES.get(bot_name, Path(f"logs/{bot_name}.log"))
        _streamers[bot_name] = LogStreamer(log_path)
        _streamers[bot_name].start()
    return _streamers[bot_name]


def get_log_lines(bot_name: str) -> list[str]:
    return get_streamer(bot_name).get_lines()


def get_available_logs() -> list[str]:
    return list(LOG_FILES.keys())
