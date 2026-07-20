"""
Test Scrapling against FTMO trading objectives page.
Extract challenge rules properly using lxml text extraction.
"""
from scrapling import Fetcher
import lxml.html
import re

print("=" * 60)
print("TEST 1: Scrapling on FTMO Trading Objectives")
print("=" * 60)

try:
    fetcher = Fetcher()
    resp = fetcher.get('https://ftmo.com/en/trading-objectives/')
    print(f"Status: {resp.status}")
    
    doc = lxml.html.fromstring(resp.html_content)
    
    # Step 1: Find the actual content area — skip scripts, styles, nav
    # Check what's in the main content area
    main = doc.cssselect('main, .main, #main, .content, .entry-content, article, [role="main"]')
    if main:
        text = main[0].text_content()
    else:
        text = doc.text_content()
    
    print(f"\nTotal text length: {len(text)} chars")
    
    # Extract H2 sections (these are the rule categories)
    print("\n" + "=" * 60)
    print("FTMO CHALLENGE RULES")
    print("=" * 60)
    
    # Find all H2 headings to identify rule sections
    sections = doc.cssselect('h2')
    rule_sections = []
    for s in sections:
        h2_text = s.text_content().strip()
        rule_sections.append(h2_text)
    
    print(f"\nRule sections found: {rule_sections}")
    
    # Extract rules by finding each section's content
    print("\n--- DETAILED RULES ---")
    
    # Use regex on cleaned text
    # Remove script and style sections
    for script in doc.cssselect('script, style, noscript'):
        script.getparent().remove(script)
    
    clean_text = doc.text_content()
    
    # Find each section
    rule_labels = [
        'Profit Target',
        'Maximum Daily Loss', 
        'Maximum Loss',
        'Best Day Rule',
        'Minimum Trading Days'
    ]
    
    for label in rule_labels:
        # Find the H2, then get text until next H2 or end
        h2s = doc.cssselect('h2')
        target_h2 = None
        for h2 in h2s:
            if label.lower() in h2.text_content().lower():
                target_h2 = h2
                break
        
        if target_h2 is not None:
            # Get all text until next h2 or next h1
            el = target_h2.getnext()
            content_parts = []
            while el is not None and el.tag != 'h2' and el.tag != 'h1':
                if el.tag in ('p', 'div', 'ul', 'ol', 'li', 'span', 'section'):
                    txt = el.text_content().strip()
                    if txt:
                        content_parts.append(txt)
                el = el.getnext()
            
            print(f"\n  [{label}]:")
            for part in content_parts:
                # Clean whitespace
                cleaned = re.sub(r'\s+', ' ', part).strip()
                if cleaned:
                    print(f"    {cleaned[:250]}")
        else:
            print(f"\n  [{label}]: (not found as standalone section)")
    
    # Extract scaling/payout info
    print("\n\n--- SCALING PLAN & PAYOUT ---")
    for pattern in [
        r'([^.]*scale[^.]{0,100}\.)',
        r'([^.]*payout[^.]{0,100}\.)',
        r'([^.]*split\s*account[^.]{0,100}\.)',
        r'([^.]*refund[^.]{0,100}\.)'
    ]:
        for match in re.finditer(pattern, clean_text, re.IGNORECASE):
            ctx = re.sub(r'\s+', ' ', match.group(1)).strip()
            if len(ctx) > 20:
                print(f"    {ctx[:300]}")
    
    # Summary table of key numbers
    print("\n\n--- KEY METRICS SUMMARY ---")
    metrics = {}
    
    # Profit targets
    pt_match = re.search(r'Profit Target[^.]*?(\d+\s*%)', clean_text)
    if pt_match:
        for m in re.findall(r'Profit\s*Target[^.]*?(\d+\s*%[^.]*?(?:step|phase|challenge|verification)[^.]*\.)', clean_text, re.IGNORECASE):
            print(f"  Profit Target: {re.sub(r'\s+', ' ', m).strip()}")
    
    # Drawdown numbers
    dd_matches = re.findall(r'(Maximum\s*(?:Daily\s*)?(?:Loss|Drawdown)[^.]*?(\d+\s*%)[^.]*\.)', clean_text, re.IGNORECASE)
    for m in dd_matches:
        print(f"  Drawdown: {re.sub(r'\s+', ' ', m[0]).strip()}")
    
    # Trading days
    td_matches = re.findall(r'(Minimum\s*Trading\s*Days[^.]*?(\d+)[^.]*\.)', clean_text, re.IGNORECASE)
    for m in td_matches:
        print(f"  Trading Days: {re.sub(r'\s+', ' ', m[0]).strip()}")
    
    # Phase structure
    print(f"\n  Phase structure from page:")
    for m in re.finditer(r'(Step|Phase)\s*(\d+|One|Two)[^.]*?(?:profit|target|trading|days?|drawdown|trade)[^.]*\.', clean_text, re.IGNORECASE):
        print(f"    {re.sub(r'\s+', ' ', m.group(0)).strip()[:300]}")
    
    # Account sizes
    print(f"\n  Account Sizes mentioned:")
    for m in re.finditer(r'\$[\d,]+(?:\s*[kK])?', text):
        ctx_start = max(0, m.start() - 40)
        ctx_end = min(len(text), m.end() + 40)
        ctx = re.sub(r'\s+', ' ', text[ctx_start:ctx_end]).strip()
        if any(kw in ctx.lower() for kw in ['account', 'challenge', 'size', 'capital', '$', 'simulated']):
            print(f"    ...{ctx}...")

except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()

print("\n" + "=" * 60)
print("FTMO TEST COMPLETE")
print("=" * 60)
