import re

SCRIPTS_DIR = r'C:\Trading\scripts'

# Read token from working source
with open(f'{SCRIPTS_DIR}/create_notion.py') as f:
    for line in f:
        if 'TOKEN' in line and 'ntn_' in line and 'Authorization' not in line:
            start = line.index('"') + 1
            end = line.rindex('"')
            TOKEN=***            break

print(f"Token: {TOKEN[:8]}...{TOKEN[-4:]} ({len(TOKEN)} chars)")

path = f'{SCRIPTS_DIR}/notion_weekly_report.py'

# Read the file and find line 14 - completely replace it
with open(path) as f:
    lines = f.readlines()

# Line 14 (0-indexed: 13) should be the NOTION_TOKEN line
target_line = 13
print(f"Original line {target_line+1}: {repr(lines[target_line].rstrip())}")

# Replace with correct format
lines[target_line] = f'NOTION_TOKEN="{TOKEN}"\n'

with open(path, 'w') as f:
    f.writelines(lines)

# Verify
with open(path) as f:
    for line in f:
        if 'NOTION_TOKEN' in line and 'Authorization' not in line:
            s = line.index('"') + 1
            e = line.rindex('"')
            t = line[s:e]
            print(f"Fixed: {t[:8]}...{t[-4:]} ({len(t)} chars, correct={t==TOKEN})")

print("Done!")
