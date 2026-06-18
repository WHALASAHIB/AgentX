import re, os

SCRIPTS_DIR = 'C:/Trading/scripts'

# Read token from the working create_notion.py
with open(os.path.join(SCRIPTS_DIR, 'create_notion.py')) as f:
    src = f.read()

# Find TOKEN="..." using regex
m = re.search(r'TOKEN\s*=\s*"([^"]+)"', src)
if not m:
    print("ERROR: Could not find token!")
    exit(1)

TOKEN = m.group(1)
print(f"Token read: starts={TOKEN[:8]} ends={TOKEN[-4:]} len={len(TOKEN)}")

# Fix the weekly report - replace entire NOTION_TOKEN line
path = os.path.join(SCRIPTS_DIR, 'notion_weekly_report.py')
with open(path) as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if re.match(r'^\s*NOTION_TOKEN\s*=', line):
        old = line.rstrip()
        lines[i] = f'NOTION_TOKEN="{TOKETEN}"\n'
        print(f"Line {i+1}: {old[:50]}... -> {lines[i][:50]}...")
        break

with open(path, 'w') as f:
    f.writelines(lines)

# Verify
with open(path) as f:
    for line in f:
        if 'NOTION_TOKEN' in line and 'Authorization' not in line:
            m2 = re.search(r'"([^"]+)"', line)
            if m2:
                t = m2.group(1)
                print(f"Verified: starts={t[:8]} ends={t[-4:]} len={len(t)} ok={t==TOKEN}")

print("Done!")
