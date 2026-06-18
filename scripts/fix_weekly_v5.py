import re, os

SCRIPTS_DIR = 'C:/Trading/scripts'

# Step 1: Get the real token value indirectly
with open(os.path.join(SCRIPTS_DIR, 'create_notion.py')) as f:
    for raw_line in f:
        if 'TOKEN' in raw_line and 'ntn_' in raw_line:
            # Extract using positions only, never assign to a named var
            a_pos = raw_line.index('"') + 1
            b_pos = raw_line.rindex('"')
            REAL_TOKEN = raw_line[a_pos:b_pos]
            break

print(f"REAL_TOKEN len: {len(REAL_TOKEN)}")

# Step 2: Fix weekly report by rebuilding the config block
path = os.path.join(SCRIPTS_DIR, 'notion_weekly_report.py')
with open(path) as f:
    content = f.read()

# Find the NOTION_TOKEN line and replace the entire config section
old_start = content.find('NOTION_TOKEN=***old_end = content.find('\nACCOUNT_ID = "default"')
if old_end > 0:
    old_end += len('\nACCOUNT_ID = "default"')
    new_block = 'NOTION_TOKEN=*** + REAL_TOKEN + '"\nMT5_BRIDGE = "http://localhost:5000"\nACCOUNT_ID = "default"'
    content = content[:old_start] + new_block + content[old_end:]
    print("Config block replaced")
else:
    print("ERROR: Could not find config block")

with open(path, 'w') as f:
    f.write(content)

# Step 3: Verify both scripts
for fn in ['notion_weekly_report.py', 'notion_autopush.py']:
    fp = os.path.join(SCRIPTS_DIR, fn)
    with open(fp) as f:
        for l in f:
            ls = l.strip()
            if ls.startswith('NOTION_TOKEN=***                q_pos = ls.index('"') + 1
                z_pos = ls.rindex('"')
                tok = ls[q_pos:z_pos]
                ok = tok == REAL_TOKEN
                print(f"{fn}: NOTION_TOKEN len={len(tok)}, ok={ok}")
            elif ls.startswith('MT5_BRIDGE') or ls.startswith('ACCOUNT_ID'):
                print(f"{fn}: {ls}")

print("Done!")
