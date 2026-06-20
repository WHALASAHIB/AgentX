.PHONY: check health status setup research clean help init e2e sre validate deploy rollback sec-check sec-migrate sec-audit sec-list agent-decisions agent-failures agent-costs aiops-scan git-sync deploy-force deploy-status sre-daemon

# AGENTX v3 — Makefile
# Automation targets for the trading system.
# Shell: bash (MSYS2 on Windows)

# Configuration
BACKEND_PORT    := 8005
BACKEND_URL     := http://localhost:$(BACKEND_PORT)
BRIDGE_URL      := http://10.10.10.1:5000
PYTHON          := python
PIP             := pip
REQUIREMENTS    := requirements.txt

# ── Harness: Init Phase (must run before any work) ────────────────────────────
init:
	@echo "=== HARNESS: INITIALIZATION PHASE ==="
	@echo ""
	@echo "1. Reading harness files..."
	@echo "   - AGENTS.md (entry point, constraints)"
	@echo "   - PROGRESS.md (current state)"
	@echo "   - ARCHITECTURE.md (system overview)"
	@echo ""
	@echo "2. Checking environment readiness..."
	@$(PYTHON) --version
	@echo "   Requirements installed:"
	@pip list --format=columns 2>/dev/null | head -5 || echo "   [pip not available]"
	@echo ""
	@echo "3. Checking system state..."
	@echo "   - Backend: $$(curl -s -o /dev/null -w '%{http_code}' $(BACKEND_URL)/api/health 2>/dev/null || echo 'DOWN')"
	@echo "   - Bridge:  $$(curl -s -o /dev/null -w '%{http_code}' $(BRIDGE_URL)/health 2>/dev/null || echo 'DOWN')"
	@echo ""
	@echo "4. Checking git status..."
	@git status --short 2>/dev/null || echo "   [Not a git repo or git not available]"
	@echo ""
	@echo "5. Plan: Read PROGRESS.md for current state."
	@echo "   Read docs/*.md for any topic you need."
	@echo "   Create a plan BEFORE modifying any code."
	@echo ""
	@echo "=== Init complete. Proceed with analysis. ==="

# ── Harness: E2E Verification (must pass before declaring done) ──────────────
e2e:
	@echo "=== HARNESS: FULL VERIFICATION SUITE ==="
	@echo ""
	errors=0; \
	echo "[1/5] Backend health..."; \
	code=$$(curl -s -o /dev/null -w '%{http_code}' $(BACKEND_URL)/api/health 2>/dev/null); \
	if [ "$$code" = "200" ]; then echo "  $(color_green)Backend OK$(color_reset)"; else echo "  $(color_red)Backend DOWN ($$code)$(color_reset)"; errors=$$((errors+1)); fi; \
	echo "[2/5] Bridge health..."; \
	code=$$(curl -s -o /dev/null -w '%{http_code}' $(BRIDGE_URL)/health 2>/dev/null); \
	if [ "$$code" = "200" ]; then echo "  $(color_green)Bridge OK$(color_reset)"; else echo "  $(color_yellow)Bridge DOWN ($$code) — may be expected$(color_reset)"; fi; \
	echo "[3/5] Python syntax validation..."; \
	syntax_errs=0; \
	for f in $$(find . -name '*.py' -not -path '*/__pycache__/*' -not -path '*/.git/*' -not -path '*/node_modules/*'); do \
		result=$$($(PYTHON) -m py_compile "$$f" 2>&1); \
		if echo "$$result" | grep -qE "(Error|SyntaxError)"; then \
			echo "  $(color_red)FAIL$$(color_reset) $$f"; \
			echo "    $$result"; \
			syntax_errs=$$((syntax_errs+1)); \
		fi; \
	done; \
	if [ $$syntax_errs -eq 0 ]; then echo "  $(color_green)All Python files pass$(color_reset)"; \
	else echo "  $(color_red)$$syntax_errs file(s) failed$(color_reset)"; errors=$$((errors+1)); fi; \
	echo "[4/5] Git status check..."; \
	if git status --porcelain 2>/dev/null | grep -q .; then echo "  $(color_yellow)Uncommitted changes exist$(color_reset)"; else echo "  $(color_green)Clean working tree$(color_reset)"; fi; \
	echo "[5/5] Harness file integrity..."; \
	for f in AGENTS.md ARCHITECTURE.md PROGRESS.md Makefile; do \
		if [ -f "$$f" ]; then echo "  $(color_green)$$f exists$(color_reset)"; else echo "  $(color_red)$$f MISSING$(color_reset)"; errors=$$((errors+1)); fi; \
	done; \
	for f in docs/architecture.md docs/trading-bots.md docs/research-division.md docs/dashboard.md docs/operations.md docs/clean-state-protocol.md; do \
		if [ -f "$$f" ]; then echo "  $(color_green)$$f exists$(color_reset)"; else echo "  $(color_yellow)$$f missing$(color_reset)"; fi; \
	done; \
	if [ -f FEATURES_TEMPLATE.md ]; then echo "  $(color_green)FEATURES_TEMPLATE.md exists$(color_reset)"; else echo "  $(color_yellow)FEATURES_TEMPLATE.md missing$(color_reset)"; fi; \
	echo ""; \
	if [ $$errors -eq 0 ]; then echo "$(color_green)ALL CHECKS PASSED — You may declare done.$(color_reset)"; \
	else echo "$(color_red)$$errors check(s) failed — Fix before declaring done.$(color_reset)"; fi

# ── DevOps / SRE Targets ───────────────────────────────────────────────────
sre:
	@echo "=== SRE Engine — System Health ==="
	@$(PYTHON) devops/sre.py --check-only 2>/dev/null || echo "Run from C:\\Trading directory"

sre-daemon:
	@echo "Starting SRE daemon (Ctrl+C to stop)..."
	@$(PYTHON) devops/sre.py --daemon

validate:
	@echo "=== Validating all Python files ==="
	@errors=0; \
	for f in $$(find . -name '*.py' -not -path '*/__pycache__/*' -not -path '*/.git/*'); do \
		result=$$($(PYTHON) -m py_compile "$$f" 2>&1 | grep -v "SyntaxWarning\|invalid escape"); \
		if [ -n "$$result" ]; then \
			echo "  $$f"; echo "     $$result"; errors=$$((errors+1)); \
		fi; \
	done; \
	if [ $$errors -eq 0 ]; then echo "All Python files pass"; \
	else echo "$$errors file(s) failed"; fi

deploy:
	@echo "=== CI/CD Deploy Pipeline ==="
	@$(PYTHON) devops/deploy.py

deploy-force:
	@echo "=== CI/CD Deploy (skip validation) ==="
	@$(PYTHON) devops/deploy.py --skip-validate

rollback:
	@echo "=== Rolling back last deployment ==="
	@$(PYTHON) devops/deploy.py --rollback

deploy-status:
	@echo "=== Deployment State ==="
	@$(PYTHON) devops/deploy.py --status

git-sync:
	@echo "=== Syncing with GitHub ==="
	@git fetch origin && git pull origin main

# ── DevSecOps Targets ──────────────────────────────────────────────────────
sec-check:
	@echo "=== DevSecOps — Security Posture ==="
	@$(PYTHON) devops/credentials.py --check

sec-migrate:
	@echo "=== DevSecOps — Migrating .env to secure storage ==="
	@$(PYTHON) devops/credentials.py --migrate

sec-audit:
	@echo "=== DevSecOps — Credential Access Log ==="
	@$(PYTHON) devops/credentials.py --audit

sec-list:
	@$(PYTHON) devops/credentials.py --list

# ── AgentOps Targets ───────────────────────────────────────────────────────
agent-decisions:
	@echo "=== AgentOps — Recent Decisions ==="
	@$(PYTHON) devops/agentops.py --decisions

agent-failures:
	@echo "=== AgentOps — Failure Statistics ==="
	@$(PYTHON) devops/agentops.py --failures

agent-costs:
	@echo "=== AgentOps — LLM Cost Estimates ==="
	@$(PYTHON) devops/agentops.py --costs --hours 168

# ── AIOps Targets ──────────────────────────────────────────────────────────
aiops-scan:
	@echo "=== AIOps — Anomaly Scan ==="
	@$(PYTHON) devops/aiops.py

# ── Standard Targets ────────────────────────────────────────────────────────
help:
	@echo "AGENTX v3 — Makefile"
	@echo "====================="
	@echo ""
	@echo "HARNESS TARGETS:"
	@echo "  make init       Init phase — read harness, check env, create plan"
	@echo "  make check      System health (backend, bridge, bots)"
	@echo "  make e2e        Full verification suite (must pass before done)"
	@echo ""
	@echo "STANDARD TARGETS:"
	@echo "  make health     Curl backend /api/health endpoint"
	@echo "  make status     Show bot status"
	@echo "  make setup      Install deps + create required dirs"
	@echo "  make research   Run Research Division full cycle"
	@echo "  make clean      Remove __pycache__, logs, temp files"
	@echo ""
	@echo "DEVOPS TARGETS:"
	@echo "  make sre        SRE engine health check"
	@echo "  make validate   Python syntax validation across all files"
	@echo "  make deploy     CI/CD deploy pipeline"
	@echo "  make rollback   Rollback last deployment"
	@echo "  make git-sync   Git pull from GitHub"
	@echo ""
	@echo "SECURITY TARGETS:"
	@echo "  make sec-check  Check for plaintext credentials"
	@echo "  make sec-migrate Encrypt .env files"
	@echo "  make sec-audit  View credential access log"
	@echo ""
	@echo "OBSERVABILITY TARGETS:"
	@echo "  make aiops-scan  Anomaly detection scan"
	@echo "  make agent-decisions  Recent agent decision log"
	@echo "  make agent-failures   Agent failure statistics"
	@echo "  make agent-costs      LLM cost estimates"
	@echo ""
	@echo "Quick API checks:"
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
	@echo "3. Bot processes..."
	@curl -s $(BACKEND_URL)/api/bots 2>/dev/null | $(PYTHON) -c "import sys,json;data=json.load(sys.stdin);running=[b for b in data if b.get('running')];stopped=[b for b in data if not b.get('running')];print(f'   Running: {len(running)} | Stopped: {len(stopped)} | Total: {len(data)}');" 2>/dev/null || echo "   [INFO] Bot endpoint unreachable"
	@echo ""
	@echo "4. Python version..."
	@$(PYTHON) --version
	@echo ""
	@echo "5. DB + Redis..."
	@curl -s $(BACKEND_URL)/api/health 2>/dev/null | $(PYTHON) -c "import sys,json;d=json.load(sys.stdin);print(f'   DB: {d.get(\"database\",{}).get(\"connected\",\"?\")}');print(f'   Redis: {d.get(\"redis\",{}).get(\"connected\",\"?\")}')" 2>/dev/null || echo "   [INFO] Health endpoint unreachable"
	@echo ""
	@echo "=== Check complete ==="

# ── Health (fast API ping) ─────────────────────────────────────────────────
health:
	@echo "=== Backend Health ==="
	@curl -s $(BACKEND_URL)/api/health | python -m json.tool 2>/dev/null || (echo "[FAIL] Backend not responding" && exit 1)
	@echo ""
	@echo "=== Bridge Health ==="
	@curl -s $(BRIDGE_URL)/health 2>/dev/null | python -m json.tool 2>/dev/null || echo "[FAIL] Bridge not responding"

# ── Bot Status ─────────────────────────────────────────────────────────────
status:
	@echo "=== Bot Status ==="
	@curl -s $(BACKEND_URL)/api/bots 2>/dev/null | $(PYTHON) -c "import sys,json;data=json.load(sys.stdin);print(f'{\"Bot Name\":<30s} {\"Status\":<10s}');print('-'*40);[print(f'{b.get(\"name\",\"?\"):<30s} {\"RUN\" if b.get(\"running\") else \"STOP\":<10s}') for b in sorted(data, key=lambda x: (0 if x.get('running') else 1, x.get('name','')))]" 2>/dev/null || (echo "[FAIL] Bot endpoint unreachable" && exit 1)

# ── Setup ──────────────────────────────────────────────────────────────────
setup:
	@echo "=== AGENTX v3 — Setup ==="
	@echo ""
	@echo "1. Installing Python dependencies..."
	$(PIP) install -r $(REQUIREMENTS)
	@echo ""
	@echo "2. Creating required directories..."
	@mkdir -p bots/logs bots/active_bots research_division/reports research_division/state backend/db frontend/public scripts graphify-out
	@echo ""
	@echo "3. Checking Python version..."
	@$(PYTHON) -c "import sys;v=sys.version_info;assert v.major==3 and v.minor==12,f'Need 3.12, got {v.major}.{v.minor}';print(f'Python {v.major}.{v.minor}.{v.micro} OK')"
	@echo ""
	@echo "4. Verifying harness files..."
	@for f in AGENTS.md ARCHITECTURE.md PROGRESS.md FEATURES_TEMPLATE.md; do \
		if [ -f "$$f" ]; then echo "   $$f OK"; else echo "   $$f MISSING"; fi; \
	done
	@echo ""
	@echo "=== Setup complete ==="

# ── Research Division ──────────────────────────────────────────────────────
research:
	@echo "=== Research Division — Full Cycle ==="
	@cd research_division && $(PYTHON) run.py --full
	@echo ""
	@echo "=== Latest report ==="
	@cat research_division/reports/latest.json 2>/dev/null | $(PYTHON) -c "import sys,json;r=json.load(sys.stdin);m=r.get('market_summary',{});print(f'Trades: {m.get(\"total_trades\",0)} | WR: {m.get(\"overall_win_rate\",0)}% | PF: {m.get(\"overall_profit_factor\",0)}');" 2>/dev/null || echo "[INFO] No report yet"

# ── Clean ──────────────────────────────────────────────────────────────────
clean:
	@echo "Cleaning __pycache__..."
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -name '*.pyc' -delete 2>/dev/null || true
	@echo "Cleaning logs..."
	@rm -f bots/logs/*.log 2>/dev/null || true
	@rm -f research_division/division.log 2>/dev/null || true
	@echo "Cleaning temp files..."
	@rm -f *.bak backend_response.html 2>/dev/null || true
	@echo "Clean complete."
