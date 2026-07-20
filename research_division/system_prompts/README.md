# System Prompts for Hermes Trading Agent

> Extracted from [system_prompts_leaks](https://github.com/asgeirtj/system_prompts_leaks) — verbatim captures of system prompts from Claude Code, Cursor, OpenCode, and other major AI coding agents.
>
> **Source repo hash:** Clone of `asgeirtj/system_prompts_leaks` (July 2026)
> **Target:** Improving our Hermes agent prompts for algo trading (Python/MT5, HK-based hedge fund)

---

## Relevance to Our Algo Trading Hedge Fund

We operate a multi-agent trading platform (AGENTX) using Hermes Agent as the orchestration layer. These system prompts from production-grade AI coding agents provide proven patterns for:

- **Subagent architecture** — how to delegate research, backtesting, execution, and monitoring to specialized agents
- **Autonomous operation** — patterns for agents that run unattended (market monitoring, overnight batch jobs)
- **Verification methodology** — rigorous validation of trading strategies (backtesting correctness)
- **Multi-agent coordination** — how specialized agents communicate and hand off work
- **Reasoning patterns** — structured thinking for analysis agents evaluating market conditions

---

## Extracted Prompts — Quick Reference

### Category 1: Agent Architecture & Subagent Patterns

| # | File | Source | Relevance |
|---|------|--------|-----------|
| 01 | `01-worker-agent.md` | Claude Code Worker | **Delegate pattern for trading subagents.** Perfect template for spawning focused research, backtesting, or execution agents. Defines scope (don't fix unrelated issues), output format (structured summary + result line), and error handling (stop on impossibility, note assumptions). |
| 02 | `02-workflow-subagent.md` | Claude Code Workflow | **Pipeline orchestration pattern.** For trading workflows where each step (data fetch → indicator calc → signal gen → order placement) is a subagent call. Teaches JSON-structured returns and verbatim string pass-through. |
| 03 | `03-general-purpose-agent.md` | Claude Code GP Agent | **General-purpose analysis agent.** For researching complex trading questions, searching codebases (strategy parameters, configs), and multi-step research tasks across many files. |
| 04 | `04-plan-agent.md` | Claude Code Plan | **Strategy design & system architecture agent.** Read-only planning mode for designing implementation plans before coding. Step-by-step architecture, trade-off analysis, dependency sequencing — ideal for designing new trading strategies or system components. |
| 05 | `05-explore-agent.md` | Claude Code Explore | **Fast codebase search agent.** For rapidly finding strategy parameters, config files, MT5 symbol references, or Python utility functions across a large codebase. Read-only, fast, broad searches. |
| 06 | `06-teammate-agent.md` | Claude Code Teammate | **Multi-agent team communication.** Defines how agents on a team communicate via SendMessage. For our strategy-engine → risk-agent → executor-agent pipeline. |
| 07 | `07-observer-agent.md` | Claude Code Observer | **Background monitoring agent.** Spawned to watch another agent's activity and report intervention-worthy events (missed constraints, compounding mistakes). Perfect for a risk guardrail agent that watches the trading agent and intervenes when risk limits are approached. |
| 08 | `08-background-job-agent.md` | Claude Code Default | **Autonomous job agent.** Pattern for agents running as background jobs with result/needs-input/failed status reporting. For overnight batch processing (end-of-day reconciliation, portfolio rebalancing calc). |

### Category 2: Autonomous Operation & Rigor Patterns

| # | File | Source | Relevance |
|---|------|--------|-----------|
| 09 | `09-autonomous-loop.md` | Claude Code Loop | **Recurring autonomous operation.** The template for our market monitoring loop. Defines how to self-pace, what to act on (in-progress work, PRs, CI), and when to stop. Directly applicable to a trading bot that runs on a schedule and reports. |
| 10 | `10-verification-methodology.md` | Claude Code Verify | **Runtime observation-driven validation.** A complete methodology for verifying code changes work — not by running tests, but by exercising the actual surface. For validating backtesting results, strategy performance, and trading bot changes. |
| 11 | `11-debug-methodology.md` | Claude Code Debug | **Structured debugging approach.** For troubleshooting trading bot issues — reading logs, identifying errors, suggesting fixes. |
| 12 | `12-code-review-methodology.md` | Claude Code Code Review | **Multi-angle code review methodology.** 8 analysis angles (line-by-line, removed-behavior, cross-file, reuse, simplification, efficiency, altitude, conventions) with verification. For reviewing trading strategy code and system changes. |

### Category 3: Multi-Agent Coordination

| # | File | Source | Relevance |
|---|------|--------|-----------|
| 13 | `13-multiagent-coordination.md` | Claude Managed Agents API | **Production multi-agent architecture.** The official Anthropic Managed Agents multi-agent pattern — coordinator, roster of up to 20 agents, thread-per-agent, event-driven communication. This is the production blueprint for our AGENTX multi-agent platform. |

### Category 4: Full Coding Agent System Prompts (Reference)

| # | File | Source | Relevance |
|---|------|--------|-----------|
| 14 | `14-cursor-agent-prompt.md` | Cursor IDE | **Full Cursor agent system prompt.** 322 lines covering tool definitions, code citation format, MCP file system, mode selection, git/PR workflow. Excellent reference for tool-use conventions and coding standards. |
| 15 | `15-opencode-agent-prompt.md` | OpenCode CLI | **Full OpenCode agent system prompt.** 329 lines with emphasis on conciseness, code style (no comments unless asked), task delegation patterns. Good reference for minimal-verbosity agent design. |
| 16 | `16-claude-code-opus-4.8-system-prompt.md` | Claude Code Opus 4.8 | **The full Claude Code system prompt** (2451 lines). The most comprehensive reference: memory system, artifact publishing, agent spawning, skills, tools, session context management. Source of truth for many patterns above. |
| 17 | `17-hermes-agent-system-prompt.md` | Hermes Agent (this repo!) | **Our own Hermes Agent system prompt** — included for cross-reference. Shows how Hermes structures its persona, skills, tool access, and session memory. Useful for comparing how other agents approach the same problems. |

---

## How to Use These Prompts

### For Agent Prompt Engineering
Reference the numbered files above when designing or refining Hermes agent prompts. Key patterns to adopt:

1. **Worker subagent pattern** (01) — scope enforcement, output format, error handling
2. **Observer pattern** (07) — background monitoring without interference
3. **Verification methodology** (10) — validate backtesting by exercising the real runtime surface
4. **Multi-agent coordination** (13) — coordinator roster, thread isolation, cross-thread messaging

### For Code Review & Debugging
Use **12 (code-review)** and **11 (debug)** as agent system prompts for review/debug tasks — they encode rigorous, multi-angle investigation patterns.

### For Autonomous Trading Operations
Use **09 (loop)** as the template for agents that monitor markets, check positions, and run batch jobs while the team is away.

---

## Repo Structure (Original)

```
system_prompts_leaks/
├── Anthropic/           # Claude, Claude Code, Claude integrations
│   ├── Claude Code/agents/         # Subagent system prompts (12 agents)
│   ├── Claude Code/bundled-skills/ # Claude Code skill definitions
│   ├── Claude Code/bundled-skills/claude-api/  # Claude API / Managed Agents docs
│   ├── Claude Code/bundled-skills/code-review/ # Code review methodology
│   ├── Official/        # Published official prompts by model version
│   └── old/             # Historical/archived prompts
├── Cursor/              # Cursor IDE system prompt
├── DeepSeek/            # DeepSeek chat prompt
├── Google/              # Gemini system prompts (various models)
├── Microsoft/           # GitHub Copilot, VS Code Copilot, Copilot CLI
├── Misc/                # Hermes, OpenCode, Devin, Docker Gordon, etc.
├── OpenAI/              # ChatGPT, Codex, API prompts
├── OpenCode/            # OpenCode CLI system prompt
├── Perplexity/          # Perplexity AI, Deep Research, Voice
├── xAI/                 # Grok system prompts
└── README.md            # Full repo index
```

---

*Last updated: 2026-07-19*
*Target: Hermes Agent for AGENTX algo trading platform*
