import re, os

SCRIPTS_DIR = 'C:/Trading/scripts'

with open(os.path.join(SCRIPTS_DIR, 'create_notion.py')) as f:
    src = f.read()

m = re.search(r'TOKEN\s*=\s*"([^"]+)"', src)
TOKEN_v=m.group(1)

path = os.path.join(SCRIPTS_DIR, 'notion_weekly_report.py')
with open(path) as f:
    content = f.read()

# Build correct config block
old_config = re.search(r'^NOTION_TOKEN.*?ACCOUNT_ID = "default"', content, re.MULTILINE | re.DOTALL)
if old_config:
    new_config = 'NOTION_TOKEN=***r MT5_BRIDGE = "http://localhost:5000"\nACCOUNT_ID = "default"'
    content = content.replace(old_config.group(0), new_config)
    print("Replaced config block")
else:
    print("Could not find config block")

with open(path, 'w') as f:
    f.write(content)

print("Done!")
