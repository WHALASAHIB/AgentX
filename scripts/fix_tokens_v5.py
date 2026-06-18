import re, os

SCRIPTS_DIR = 'C:/Trading/scripts'

with open(os.path.join(SCRIPTS_DIR, 'create_notion.py')) as f:
    src = f.read()

m = re.search(r'TOKEN\s*=\s*"([^"]+)"', src)
TOKEN = m.group(1)
print(f"Token length: {len(TOKEN)}")

# Fix weekly report
path = os.path.join(SCRIPTS_DIR, 'notion_weekly_report.py')
with open(path) as f:
    lines = f.readlines()

# Build the replacement line without embedding the token literally in source
new_line_parts = ['NOTION_TOKEN=', '"', TOKEN, '"', '\n']
new_line = ''.join(new_line_parts)

for i, line in enumerate(lines):
    if re.match(r'^\s*NOTION_TOKEN\s*=', line):
        lines[i] = new_line
        print(f"Fixed line {i+1}: NOTION_TOKEN=***...")
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
                ok = "OK" if t == TOKEN else "MISMATCH"
                print(f"Verified: len={len(t)} {ok}")

# Also fix autopush if needed
path2 = os.path.join(SCRIPTS_DIR, 'notion_autopush.py')
with open(path2) as f:
    lines2 = f.readlines()

for i, line in enumerate(lines2):
    if re.match(r'^\s*NOTION_TOKEN\s*=', line):
        m2 = re.search(r'"([^"]+)"', line)
        if m2 and len(m2.group(1)) < 10:
            # Token is broken, fix it
            lines2[i] = ''.join(['NOTION_TOKEN=', '"', TOKEN, '"', '\n'])
            print(f"Fixed autopush line {i+1}")
        else:
            print(f"Autopush line {i+1} OK (len={len(m2.group(1)) if m2 else 0})")
        break

with open(path2, 'w') as f:
    f.writelines(lines2)

print("Done!")
