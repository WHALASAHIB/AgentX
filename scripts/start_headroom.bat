@echo off
REM Start Headroom proxy for AgentX
REM Reads DEEPSEEK_API_KEY from Hermes .env and starts proxy on port 8787

python -c "
import os, subprocess
with open(os.path.expanduser('~/.hermes/.env')) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k, _, v = line.partition('=')
        os.environ[k.strip()] = v.strip()
os.environ['OPENAI_API_KEY'] = os.environ.get('DEEPSEEK_API_KEY', '')
os.environ['OPENAI_BASE_URL'] = 'https://api.deepseek.com/v1'
print('Starting Headroom proxy on :8787 (backend=openai, memory+learn enabled)')
proc = subprocess.Popen(['headroom','proxy','--port','8787','--backend','openai','--disable-kompress','--memory','--learn'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
print('PID: ' + str(proc.pid))
with open(os.path.expanduser('~/.headroom/headroom.pid'), 'w') as pf:
    pf.write(str(proc.pid))
for line in iter(proc.stdout.readline, b''):
    print(line.decode().strip())
"
