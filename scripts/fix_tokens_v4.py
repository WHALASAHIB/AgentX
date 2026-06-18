import re, os

SCRIPTS_DIR = 'C:/Trading/scripts'

with open(os.path.join(SCRIPTS_DIR, 'create_notion.py')) as f:
    src = f.read()

m = re.search(r'TOKEN\s*=\s*"([^\"]+)"', src)
if not m:
    print("ERROR: Could not find token!")
    exit(1)

TOKEN=m.grou...int(f"Token read: starts ns={TOKEN[-4:]} len={len(TOKEN)}")

# Fix weekly report
path = os.path.join(SCRIPTS_DIR, 'notion_weekly_report.py')
with open(path) as f:
    lines = f.readlines()

new_line = 'NOTION_TOKEN="' + TOKEN + '"\n'

for i, line in enumerate(lines):
    if re.match(r'^\s*NOTION_TOKEN\s*=', line):
        old = line.rstrip()
        lines[i] = new_line
        print(f"Line {i+1}: {old[:50]}... -> {new_line[:50]}...")
        break

with open(path, 'w') as f:
    f.writelines(lines)

# Verify
with open(path) as f:
    for line in f:
        if 'NOTION_TOKEN' in line and 'Authorization' not in line:
            m2 = re.search(r'"([^\"]+)"', line)
            if m2:
                t = m2.group(1)
                ok = "OK" if t == TOKEN else "MISMATCH"
                print(f"Verified: starts={t[:8]} ends={t[-4:]} len={len(t)} {ok}")

print("Done!")
