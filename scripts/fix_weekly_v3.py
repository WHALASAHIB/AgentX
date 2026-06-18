import re, os

SCRIPTS_DIR = 'C:/Trading/scripts'

# Read token from working file
with open(os.path.join(SCRIPTS_DIR, 'create_notion.py')) as f:
    src = f.read()
m = re.search(r'TOKEN\s*=\s*"([^"]+)"', src)
MY_TOKEN=m.group(1)print(f"Token: {len(MY_TOKEN)} chars")

# Fix weekly report
path = os.path.join(SCRIPTS_DIR, 'notion_weekly_report.py')
with open(path) as f:
    content = f.read()

lines = content.split('\n')
for i, line in enumerate(lines):
    if re.match(r'^\s*NOTION_TOKEN\s*=', line):
        lines[i] = 'NOTION_TOKEN=*** + MY_TOKEN + '"'
        print(f"Fixed line {i+1}")
        # Add MT5_BRIDGE if missing on next line
        if i+1 < len(lines) and 'MT5_BRIDGE' not in lines[i+1]:
            lines.insert(i+1, 'MT5_BRIDGE = "http://localhost:5000"')
            print(f"Added MT5_BRIDGE line")
        break

with open(path, 'w') as f:
    f.write('\n'.join(lines))

# Verify
with open(path) as f:
    for line in f:
        ls = line.strip()
        if ls.startswith('NOTION_TOKEN') or ls.startswith('MT5_BRIDGE'):
            print(f"  {ls[:65]}")
print("Done!")
