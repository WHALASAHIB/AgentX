import random
from datetime import datetime, timezone
from typing import Dict, Any, List

class MacroeconomicEventAgent:
    def __init__(self):
        self.name = "MacroeconomicEventAgent"
        self.economic_calendar = [
            {"event": "US CPI MoM/YoY Inflation", "importance": "HIGH", "time_offset_min": 15},
            {"event": "FOMC Interest Rate Decision", "importance": "CRITICAL", "time_offset_min": 60},
            {"event": "US Non-Farm Payrolls (NFP)", "importance": "HIGH", "time_offset_min": 5},
            {"event": "ECB Press Conference", "importance": "MEDIUM", "time_offset_min": -30}
        ]

    def check_news_hazards(self) -> List[Dict[str, Any]]:
        """
        Scans economic calendars for high-impact announcements near the current time.
        Returns a list of warnings or hazards.
        """
        hazards = []
        # Simulate check
        for item in self.economic_calendar:
            # Let's say there is a 5% chance an event is active right now
            if random.random() < 0.05:
                hazards.append({
                    "event": item["event"],
                    "importance": item["importance"],
                    "active_hazard": True,
                    "minutes_remaining": item["time_offset_min"]
                })
        return hazards
