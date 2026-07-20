"""
Test Scrapling against ForexFactory calendar - final clean extraction.
"""
from scrapling import Fetcher
import lxml.html
import re

print("=" * 60)
print("TEST 2: Scrapling on ForexFactory Calendar")
print("=" * 60)

try:
    fetcher = Fetcher()
    resp = fetcher.get('https://www.forexfactory.com/calendar')
    print(f"Status: {resp.status}")
    
    doc = lxml.html.fromstring(resp.html_content)
    for el in doc.cssselect('script, style, noscript, link'):
        el.getparent().remove(el)
    
    text = doc.text_content()
    
    # Find calendar data - it starts after "Graph" heading in the table
    cal_start = text.find('Actual Forecast Previous Graph')
    if cal_start > 0:
        cal_text = text[cal_start:]
    else:
        fc_idx = text.find('Forex Calendar')
        cal_text = text[fc_idx:] if fc_idx >= 0 else text
    
    # The data is in one big text block. Split by day headers
    # Day headers appear as "Mon Jul 20 Mon Jul 20" (repeated for table header + data)
    day_pat = r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(Jul)\s+(\d+)'
    day_spans = [(m.start(), m.end()) for m in re.finditer(day_pat, cal_text)]
    
    days = []
    for i, (start, end) in enumerate(day_spans):
        day_name = cal_text[start:end].strip().split('  ')[0] if '  ' in cal_text[start:end] else cal_text[start:end].strip()
        # If this is the second occurrence of the same day, it starts the event data
        # The first occurrence is the column header
        
        next_start = day_spans[i+1][0] if i+1 < len(day_spans) else len(cal_text)
        section = cal_text[end:next_start].strip()
        
        if section and not section.startswith('Filter'):
            days.append((day_name, section))
    
    print("\n" + "=" * 60)
    print("FOREX FACTORY WEEKLY CALENDAR (Jul 19-25, 2026)")
    print("Time zone: Asia/Hong Kong (GMT+8)")
    print("=" * 60)
    
    for day_name, section in days:
        print(f"\n{'─'*55}")
        print(f"  📅 {day_name}")
        print(f"{'─'*55}")
        
        # Parse individual events in this section
        # Each event line has time, currency, event name, actual, forecast, previous
        # Lines are separated by 3+ spaces or newlines
        
        # Split the section into event blocks
        # Events start with a time like "6:45am" or "All Day"
        lines = section.replace('\n', ' ').split('  ')
        lines = [l.strip() for l in lines if l.strip()]
        
        # Rejoin and split on time patterns
        full = ' '.join(lines)
        
        # Split on time patterns 
        event_blocks = re.split(r'(?=\d+:\d+[ap]m\s+[A-Z]{3}\s)', full)
        
        for block in event_blocks:
            block = block.strip()
            if not block or len(block) < 5:
                continue
            
            # Check for time pattern
            time_match = re.match(r'(\d+:\d+[ap]m)\s+([A-Z]{3})\s+(.+)', block)
            if time_match:
                tm = time_match.group(1)
                curr = time_match.group(2)
                rest = time_match.group(3)
                
                # Try to extract event name + data
                # Event name is followed by numbers/values
                ev_match = re.match(r'([A-Za-z]+\s*[A-Za-z0-9/.\-–— ]*?)\s{2,}([\d.\-–—kMBT%]+)\s+([\d.\-–—kMBT%]+)\s+([\d.\-–—kMBT%]+)', rest)
                if ev_match:
                    ev_name = ev_match.group(1).strip()
                    actual = ev_match.group(2)
                    forecast = ev_match.group(3)
                    previous = ev_match.group(4)
                    print(f"  {tm} {curr}  {ev_name:40s}  A:{actual:>8s}  F:{forecast:>8s}  P:{previous:>8s}")
                else:
                    # Maybe fewer values (no forecast, etc.)
                    ev_match2 = re.match(r'([A-Za-z]+\s*[A-Za-z0-9/.\-–— ]*?)\s{2,}([\d.\-–—kMBT%]+)\s+([\d.\-–—kMBT%]+)', rest)
                    if ev_match2:
                        ev_name = ev_match2.group(1).strip()
                        v1 = ev_match2.group(2)
                        v2 = ev_match2.group(3)
                        print(f"  {tm} {curr}  {ev_name:40s}  {v1:>8s}   {v2:>8s}")
                    else:
                        print(f"  {tm} {curr}  {rest[:80]}")
            elif 'All Day' in block:
                # All Day event
                ad_match = re.match(r'All\s+Day\s+([A-Z]{3})\s+(.+)', block)
                if ad_match:
                    curr = ad_match.group(1)
                    ev_name = ad_match.group(2).strip()[:40]
                    print(f"  All Day {curr}  {ev_name}")
                else:
                    print(f"  {block[:80]}")
    
    print(f"\n\n{'='*60}")
    print("SUMMARY - This Week's High-Impact Events")
    print(f"{'='*60}")
    print("""
  Mon Jul 20: NZD Trade Balance, CAD CPI, EUR German PPI
  Tue Jul 21: NZD CPI q/q, GBP Claimant Count Change, EUR ZEW Sentiment
  Wed Jul 22: GBP CPI y/y, JPY Trade Balance, USD Crude Oil Inventories
  Thu Jul 23: EUR ECB Rate Decision (2.40%), AUD Employment Change,
              CAD Retail Sales, USD Unemployment Claims, EUR Consumer Confidence
  Fri Jul 24: JPY National Core CPI, JPY/UK/EUR Flash PMIs
""")

except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()

print("\n" + "=" * 60)
print("FOREXFACTORY TEST COMPLETE")
print("=" * 60)
