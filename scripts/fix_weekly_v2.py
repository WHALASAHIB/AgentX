import re, os

SCRIPTS_DIR = 'C:/Trading/scripts'

# Read token from working file
with open(os.path.join(SCRIPTS_DIR, 'create_notion.py')) as f:
    src = f.read()
m = re.search(r'TOKEN\s*=\s*"([^"]+)"', src)
GOOD_TOKEN=m.grou...ading token: {len(GOOD_TOKEN)} chars")

# Fix weekly report - add MT5_BRIDGE line after NOTION_TOKEN
path = os.path.join(SCRIPTS_DIR, 'notion_weekly_report.py')
with open(path) as f:
    content = f.read()

lines = content.split('\n')

# Find the NOTION_TOKEN line index and what's after it
for i, line in enumerate(lines):
    if re.match(r'^\s*NOTION_TOKEN\s*=', line):
        # Ensure line has correct token
        lines[i] = 'NOTION_TOKEN=' + '"' + GOOD_TOKEN + '"'
        # Check if next line has MT5_BRIDGE
        if i+1 < len(lines) and 'MT5_BRIDGE' not in lines[i+1]:
            lines.insert(i+1, 'MT5_BRIDGE = "http://localhost:5000"')
        print(f"Fixed line {i+1}: {lines[i][:40]}...")
        break

# Also fix any MT5_BRIDGE line that might be on the same line
new_content = '\n'.join(lines)

# Final safety: ensure MT5_BRIDGE is defined
if 'MT5_BRIDGE' not in new_content.split('\n')[i+1]:
    # Already inserted above, but double check
    pass

with open(path, 'w') as f:
    f.write(new_content)

# Verify
with open(path) as f:
    for line in f:
        line_s = line.strip()
        if line_s.startswith('NOTION_TOKEN=') or line_s.startswith('MT5_BRIDGE'):
            print(f"  {line_s[:60]}")

print("Done!")
