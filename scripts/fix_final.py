import re, os

SCRIPTS_DIR = 'C:/Trading/scripts'

# Read token from known-good file
with open(os.path.join(SCRIPTS_DIR, 'create_notion.py')) as f:
    for line in f:
        if 'TOKEN' in line and 'ntn_' in line:
            start = line.index('"') + 1
            end = line.rindex('"')
            TOKEN=***            break

print(f"Token loaded: {len(TOKEN)} chars")

# Fix weekly report
path = os.path.join(SCRIPTS_DIR, 'notion_weekly_report.py')
with open(path) as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.strip().startswith('NOTION_TOKEN='):
        old_line = line.rstrip()
        new_line = 'NOTION_TOKEN="' + TOKEN + '"\n'
        lines[i] = new_line
        print(f"Line {i+1}: Fixed NOTION_TOKEN")
        # Check if next line has MT5_BRIDGE
        if i+1 < len(lines):
            nxt = lines[i+1].strip()
            if 'MT5_BRIDGE' not in nxt and nxt.startswith('ACCOUNT_ID'):
                # Insert MT5_BRIDGE between NOTION_TOKEN and ACCOUNT_ID
                lines.insert(i+1, 'MT5_BRIDGE = "http://localhost:5000"\n')
                print(f"Inserted MT5_BRIDGE after line {i+1}")
            elif 'MT5_BRIDGE' in nxt:
                # Just fix the MT5_BRIDGE value
                lines[i+1] = 'MT5_BRIDGE = "http://localhost:5000"\n'
                print(f"Fixed MT5_BRIDGE on line {i+2}")
        break

with open(path, 'w') as f:
    f.writelines(lines)

# Verify weekly report config lines
print("\nWeekly report config:")
with open(path) as f:
    for line in f:
        ls = line.strip()
        if ls.startswith('NOTION_TOKEN') or ls.startswith('MT5_BRIDGE') or ls.startswith('ACCOUNT_ID'):
            if ls.startswith('NOTION_TOKEN'):
                s = ls.index('"') + 1
                e = ls.rindex('"')
                t = ls[s:e]
                print(f'  NOTION_TOKEN: len={len(t)} correct={t==TOKEN}')
            else:
                print(f'  {ls}')

# Verify autopush
print("\nAutopush config:")
path2 = os.path.join(SCRIPTS_DIR, 'notion_autopush.py')
with open(path2) as f:
    for line in f:
        ls = line.strip()
        if ls.startswith('NOTION_TOKEN') or ls.startswith('MT5_BRIDGE') or ls.startswith('ACCOUNT_ID'):
            if ls.startswith('NOTION_TOKEN'):
                s = ls.index('"') + 1
                e = ls.rindex('"')
                t = ls[s:e]
                print(f'  NOTION_TOKEN: len={len(t)} correct={t==TOKEN}')
            else:
                print(f'  {ls}')

print("\nDone!")
