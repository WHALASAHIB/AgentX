.PHONY: check health status setup research clean help

# ── AGENTX v3 — Makefile ──────────────────────────────────────────────
# Automation targets for the trading system.
# Shell: bash (MSYS2 on Windows)

# ── Configuration ──────────────────────────────────────────────────────
BACKEND_PORT    := 8005
BACKEND_URL     := http://localhost:$(BACKEND_PORT)
BRIDGE_URL      := http://10.10.10.1:5000
PYTHON          := python
PIP             := pip
REQUIREMENTS    := requirements.txt

# ── Help ──────────────────────────────────────────────────────────────
help:
	@echo "AGENTX v3 — Makefile"
	@echo "======================"
	@echo ""
	@echo "Targets:"
	@echo "  make check     Run health_check.py and report system status"
	@echo "  make health    Curl backend /api/health endpoint"
	@echo "  make status    Show status of all 23 trading bots"
	@echo "  make setup     Install Python deps and create required directories"
	@echo "  make research  Run the Research Division full cycle"
	@echo "  make clean     Remove __pycache__ directories, logs, and temp files"
	@echo "  make help      Show this message"
	@echo ""
	@echo "Quick checks:"
	@echo "  curl $(BACKEND_URL)/api/health"
	@echo "  curl $(BACKEND_URL)/api/bots"
	@echo "  curl $(BACKEND_URL)/api/stats"

# ── Health Check ──────────────────────────────────────────────────────────
check:
	@echo "=== AGENTX v3 — System Health Check ==="
	@echo ""
	@echo "1. Backend health..."
	@curl -s $(BACKEND_URL)/api/health 2>/dev/null || echo "   [FAIL] Backend not responding on port $(BACKEND_PORT)"
	@echo ""
	@echo "2. MT5 Bridge..."
	@curl -s $(BRIDGE_URL)/health 2>/dev/null || echo "   [FAIL] Bridge not responding on $(BRIDGE_URL)"
	@echo ""
	@echo "3. Bot processes (23 total)..."
	@curl -s $(BACKEND_URL)/api/bots 2>/dev/null | $(PYTHON) -c "\
import sys, json; data = json.load(sys.stdin); \
running = [b for b in data if b.get('running')]; \
stopped = [b for b in data if not b.get('running')]; \
print(f'   Running: {len(running)} | Stopped: {len(stopped)} | Total: {len(data)}'); \
if running: print(f'   Active: {', '.join(b[\"name\"] for b in running[:10])}...')" 2>/dev/null || echo "   [INFO] Bot endpoint unreachable (backend may be down)"
	@echo ""
	@echo "4. Python version..."
	@$(PYTHON) --version
	@echo ""
	@echo "5. Redis + Database..."
	@curl -s $(BACKEND_URL)/api/health 2>/dev/null | $(PYTHON) -c "\
import sys, json; data = json.load(sys.stdin); \
print(f'   DB connected: {data.get(\"database\",{}).get(\"connected\",\"?\")}'); \
print(f'   Redis connected: {data.get(\"redis\",{}).get(\"connected\",\"?\")}')" 2>/dev/null || echo "   [INFO] Health endpoint unreachable"
	@echo ""
	@echo "=== Check complete ==="

# ── Health (fast API ping) ─────────────────────────────────────────────────
health:
	@echo "=== Backend Health ==="
	@curl -s $(BACKEND_URL)/api/health | $(PYTHON) -m json.tool 2>/dev/null || \
		(echo "[FAIL] Backend not responding on port $(BACKEND_PORT)" && exit 1)
	@echo ""
	@echo "=== Bridge Health ==="
	@curl -s $(BRIDGE_URL)/health 2>/dev/null | $(PYTHON) -m json.tool 2>/dev/null || \
		echo "[FAIL] Bridge not responding on $(BRIDGE_URL)"

# ── Bot Status ─────────────────────────────────────────────────────────────
status:
	@echo "=== Bot Status (All 23) ==="
	@curl -s $(BACKEND_URL)/api/bots 2>/dev/null | $(PYTHON) -c "\
import sys, json; data = json.load(sys.stdin); \
print(f'{\"Bot Name\":<30s} {\"Status\":<10s} {\"PID\":<8s} {\"Uptime\":<12s}'); \
print('-'*60); \
for b in sorted(data, key=lambda x: (0 if x.get('running') else 1, x.get('name',''))): \
    name = b.get('name','?'); \
    running = 'RUN' if b.get('running') else 'STOP'; \
    pid = str(b.get('pid','-') or '-'); \
    uptime = b.get('uptime','-') or '-'; \
    if isinstance(uptime, (int,float)): uptime = f'{uptime:.0f}s'; \
    print(f'{name:<30s} {running:<10s} {pid:<8s} {uptime:<12s}')" 2>/dev/null || \
		(echo "[FAIL] Bot endpoint unreachable" && exit 1)

# ── Setup ──────────────────────────────────────────────────────────────────
setup:
	@echo "=== AGENTX v3 — Setup ==="
	@echo ""
	@echo "1. Installing Python dependencies..."
	$(PIP) install -r $(REQUIREMENTS)
	@echo ""
	@echo "2. Creating required directories..."
	@mkdir -p bots/logs
	@mkdir -p bots/active_bots
	@mkdir -p research_division/reports
	@mkdir -p research_division/state
	@mkdir -p backend/db
	@mkdir -p frontend/public
	@mkdir -p scripts
	@mkdir -p graphify-out
	@echo ""
	@echo "3. Checking Python version..."
	@$(PYTHON) -c "import sys; v=sys.version_info; assert v.major==3 and v.minor==12, f'Need Python 3.12, got {v.major}.{v.minor}'; print(f'Python {v.major}.{v.minor}.{v.micro} OK')"
	@echo ""
	@echo "=== Setup complete ==="

# ── Research Division ──────────────────────────────────────────────────────
research:
	@echo "=== Research Division — Full Cycle ==="
	@cd research_division && $(PYTHON) run.py --full
	@echo ""
	@echo "=== Latest report ==="
	@cat research_division/reports/latest.json 2>/dev/null | $(PYTHON) -c "\
import sys, json; \
try: \
    r = json.load(sys.stdin); \
    m = r.get('market_summary',{}); \
    print(f'Trades: {m.get(\"total_trades\",0)} | WR: {m.get(\"overall_win_rate\",0)}% | PF: {m.get(\"overall_profit_factor\",0)} | PnL: \${m.get(\"net_profit\",0):,.2f}'); \
    d = r.get('deployments',[]); \
    print(f'Deployments: {len(d)}'); \
except: print('No report data')" 2>/dev/null || echo "[INFO] No report yet (first run populates it)"

# ── Clean ──────────────────────────────────────────────────────────────────
clean:
	@echo "Cleaning __pycache__ directories..."
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Cleaning logs..."
	@rm -f bots/logs/*.log 2>/dev/null || true
	@rm -f research_division/division.log 2>/dev/null || true
	@echo "Cleaning temp files..."
	@rm -f *.bak 2>/dev/null || true
	@rm -f backend_response.html 2>/dev/null || true
	@echo "Clean complete."
