# AgentX — Website Router for AI Agents

This repo contains ONLY the AgentX trading **website** (frontend + backend).
All bot logic, research, DevOps, and system intelligence live in the **Hermess** repo.

**→ [Hermess Repo](https://github.com/WHALASAHIB/Hermess.git)**

---

## Quick Reference

```
📁 AgentX/
├── backend/          # FastAPI server (port 8005)
│   ├── app.py        # Main app with all routes
│   ├── auth.py       # Google OAuth
│   ├── db/           # SQLite + connection pool
│   └── backtest/     # Backtesting API routes
├── frontend/         # SPA Dashboard
│   └── public/
│       └── index.html  # 12-section SPA (~2,800 lines)
├── README.md         # This file
├── requirements.txt  # Python deps
└── .gitignore
```

## First Time Here?
1. Read `README.md` — system overview
2. Check `backend/app.py` for API routes
3. Check `frontend/public/index.html` for dashboard sections
4. For bot/research/DevOps questions → see the **Hermess** repo

## Makefile Targets
- `make check` — Health check (backend + bridge)
- `make e2e` — Full verification
- `make setup` — Install deps + create dirs
- `make validate` — Python syntax check
