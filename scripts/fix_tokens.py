# Fix Notion tokens in scripts
import os

SCRIPTS_DIR = r'C:\Trading\scripts'

# Read token from the working source
with open(os.path.join(SCRIPTS_DIR, 'create_notion.py')) as f:
    for line in f:
        if 'TOKEN' in line and 'ntn_' in line and 'Authorization' not in line:
            start = line.index('"') + 1
            end = line.rindex('"')
            TOKEN = line[start:end]
            break

print(f"Token: {TOKEN[:8]}...{TOKEN[-4:]} (len={len(TOKEN)})")

for script_name in ['notion_autopush.py', 'notion_weekly_report.py']:
    path = os.path.join(SCRIPTS_DIR, script_name)
    with open(path) as f:
        content = f.read()
    
    # Collect all lines with NOTION_TOKEN assignments
    import re
    pattern = r'(NOTION_TOKEN\s*=\s*")([^"]*)(")'
    
    def replace_token(m):
        return f'{m.group(1)}{TOKEN}{m.group(3)}'
    
    new_content = re.sub(pattern, replace_token, content)
    
    if new_content != content:
        with open(path, 'w') as f:
            f.write(new_content)
        print(f"Fixed: {script_name}")
    else:
        print(f"No change: {script_name}")
    
    # Verify
    with open(path) as f:
        for line in f:
            if 'NOTION_TOKEN' in line and 'Authorization' not in line:
                s = line.index('"') + 1
                e = line.rindex('"')
                t = line[s:e]
                print(f"  Verified: {t[:8]}...{t[-4:]} (len={len(t)}, correct={len(t)==len(TOKEN)})")

print("\nDone!")
