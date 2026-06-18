import re, os

SCRIPTS_DIR = r'C:\Trading\scripts'

# Read token from the working create_notion.py using a robust method
with open(os.path.join(SCRIPTS_DIR, 'create_notion.py')) as f:
    src = f.read()

# Find TOKEN="..." using regex
m = re.search(r'TOKEN\s*=\s*"([^"]+)"', src)
if m:
    TOKEN=***up(1)
    print(f"Token: {TOKEN[:8]}...{TOKEN[-4:]} ({len(TOKEN)} chars)")
else:
    print("ERROR: Could not find token!")
    exit(1)

# Fix the weekly report
path = os.path.join(SCRIPTS_DIR, 'notion_weekly_report.py')
with open(path) as f:
    content = f.read()

# Replace any NOTION_TOKEN line using regex
def fix_token_line(match):
    return f'NOTION_TOKEN="{TOK...content = re.sub(r'^NOTION_TOKEN\s*=\s*"[^"]*"', fix_token_line, content, flags=re.MULTILINE)

with open(path, 'w') as f:
    f.write(content)

# Verify
with open(path) as f:
    for line in f:
        if 'NOTION_TOKEN' in line and 'Authorization' not in line and 'import' not in line:
            m = re.search(r'"([^"]+)"', line)
            if m:
                t = m.group(1)
                print(f"Line: {t[:8]}...{t[-4:]} ({len(t)} chars, correct={t==TOKEN})")

# Also verify notion_autopush.py
path2 = os.path.join(SCRIPTS_DIR, 'notion_autopush.py')
with open(path2) as f:
    for line in f:
        if 'NOTION_TOKEN' in line and 'Authorization' not in line and 'import' not in line:
            m = re.search(r'"([^"]+)"', line)
            if m:
                t = m.group(1)
                print(f"autopush: {t[:8]}...{t[-4:]} ({len(t)} chars, correct={t==TOKEN})")

print("\nAll fixed!")
