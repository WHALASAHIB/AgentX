# TradingAgents Coordination Pattern — Reference for Bot Fleet Redesign

**Source:** github.com/TauricResearch/TradingAgents (evaluated Jun 26, 2026)
**Verdict:** Extract patterns, do NOT deploy as-is
**Assigned Division:** 🤖 AI & Automation (lead), 💹 Trading & Financial

## Architecture Overview

TradingAgents uses a **LangGraph-based state machine** where agents share a common state dictionary and communicate through structured Pydantic schemas:

```
Analysts (Market, Social, News, Fundamentals)
    │  parallel → each writes reports to shared state
    ▼
Bull/Bear Researchers (debate)
    │  sequential rounds → investment_debate_state
    ▼
Research Manager (synthesizes debate → ResearchPlan)
    │  structured output: recommendation, rationale, strategic_actions
    ▼
Trader (ResearchPlan → TraderProposal)
    │  structured output: action, reasoning, entry_price, stop_loss, position_sizing
    ▼
Risk Debate (Aggressive/Conservative/Neutral) (LLM-driven debate)
    │  3 analysts argue in rounds → risk_debate_state
    ▼
Portfolio Manager (final decision → PortfolioDecision)
    │  structured output: rating, executive_summary, investment_thesis, price_target
    ▼
Signal Processor → Memory Log (reflection on outcomes)
```

## Key Patterns Worth Adopting

### 1. Shared State Architecture
All agents read/write to a single `state` dict. No direct agent-to-agent calls — they communicate via state keys.

**In AGENTX terms:** Our bots currently work independently. This pattern would let us build a shared `BotState` dict that a Strategy Supervisor reads/writes, replacing the current individual bot state files.

### 2. Structured Schema as Agent Contracts
Agents don't pass free text — they pass Pydantic models with explicit fields:
```python
class TraderProposal(BaseModel):
    action: TraderAction       # Buy/Hold/Sell
    reasoning: str             # justification
    entry_price: float | None  # entry target
    stop_loss: float | None    # stop level
    position_sizing: str | None # sizing guidance
```

**For AGENTX:** Replace the current ad-hoc JSON trade signals with typed schemas:
```python
class BotSignal(BaseModel):
    symbol: str
    direction: Literal["BUY", "SELL", "HOLD"]
    confidence: float  # 0.0-1.0
    entry_zone: tuple[float, float]
    stop_loss: float | None
    take_profit: float | None
    lot_size: float | None
    strategy: str  # which strategy generated this
```

### 3. Debate + Judge Pattern
Instead of one agent making a call, 3 analysts debate (Bull/Bear or Aggressive/Conservative/Neutral), then a Judge/Manager synthesizes.

**For AGENTX:** Replace the current single-bot signal decision with a lightweight debate between signal sources (e.g., MACD vs Bollinger vs SMA for the same symbol). Each votes, a manager weighs confidence scores.

### 4. Reflection Cycle
After a trade, Reflector reviews the decision vs outcome and saves lessons. Next run, those lessons are injected as `past_context`.

**For AGENTX:** We already have a Post-Trade Critic — this would formalize the feedback loop into our bot state.

### 5. Memory Log
Structured SQLite log of every decision with: ticker, date, decision text, outcome (resolved lazily when price data becomes available), and reflection.

**For AGENTX:** Upgrade our current flat-file logs to a structured memory that bots query before signaling (e.g., "last 5 trades on XAUUSD were losers — reduce confidence").

## Mapping to AGENTX Divisions

| TradingAgents Component | AGENTX Equivalent | Division | Priority |
|------------------------|-------------------|----------|----------|
| Analyst node pipeline | Multi-symbol bots per pair | 💹 Trading | Already exists |
| Shared state dict | Replace individual bot state files with unified BotState | 🤖 AI | P3 |
| Pydantic schema contracts | BotSignal schema for trade messages | 🤖 AI + 🏗️ SE | P1 ✅ done |
| Risk debate (LLM round-robin) | Replace with mathematical position sizing (risk_sizing.py) | 💹 Trading | P1 ✅ done |
| Reflection + Memory Log | Enhance Post-Trade Critic with structured memory | 📊 DS + 💹 Trading | P3 |
| LangGraph orchestration | Consider for Strategy Supervisor rewrite | 🤖 AI | Future |

## Files Created

- `C:\Trading\bots\risk_sizing.py` — Standalone position sizing module (3 methods: fixed_pct, kelly, equal_risk) + FTMO limit validation
- `C:\Trading\_repo_eval\TradingAgents\` — Cloned repo for reference (read-only, do not modify)
