# Judge A (Practitioner) — Resource Evaluation Report

**Role:** Practitioner — rating on practical utility & integration ease for our org  
**Org:** Algorithmic trading hedge fund | Python/MT5 stack | Hermes Agent | HK-based (US geo-blocked) | Crawl4AI already installed  
**Current model baseline:** DeepSeek V4 Flash via Headroom proxy (free, but HK geo-blocking uncertain)

---

## 1. system_prompts_leaks (asgeirtj/system_prompts_leaks)

**GitHub:** github.com/asgeirtj/system_prompts_leaks  
**Vitals:** 58.9k ★ | 9.6k forks | 662 commits | Actively maintained (latest commit: 1 hour ago)

**What it is:** Curated collection of leaked/verbatim system prompts from virtually every major AI company — OpenAI (GPT-5.6, Codex), Anthropic (Claude Fable 5, Opus 4.8, Claude Code, Claude Design, Claude Cowork), Google (Gemini 3.5 Flash, 3.1 Pro, Antigravity), xAI (Grok), DeepSeek, Kimi, Meta, Microsoft (Copilot, VS Code), Perplexity, Cursor, Zed, Pi, and dozens more. Includes Claude Code subagent prompts, bundled skills, slash commands, MCP server prompts, injected reminders (hidden mid-conversation instructions), and research artifacts.

**Practical Utility: 8/10**
- Directly applicable to improving our Hermes agent system prompts — we can study how Anthropic/OpenAI structure tool-using agents (Claude Code subagents, tool definitions, skill-based dispatch) and apply those patterns to our trading agents
- The injected reminders section shows how runtime behavioral adjustments work — useful for our guardrail/trade-critic agents
- The Claude Code subagent prompts are particularly relevant: they show how to structure agents with distinct roles (Explore, Plan, general-purpose, teammate) — directly applicable to our multi-agent trading architecture
- Contains Kimi K3's prompt — gives us insight into a model we might adopt
- Heavily cited by real organizations (Washington Post, CEPS AI World)
- Major con: These are leaks — no guarantees of completeness or accuracy. Some prompts may be outdated or partial

**Integration Ease: 9/10**
- It's a GitHub repo of markdown files — zero integration needed
- `git clone` and read. Use as research/inspiration, not a dependency
- No code to merge, no API to configure
- Can directly reference patterns when crafting/skilling our Hermes trading agents

**Recommendation: ADOPT**

> Worth pulling the repo into our research division immediately. Direct, low-effort value for anyone writing Hermes agent prompts or building multi-agent workflows. Study Claude Code's subagent patterns as reference for our agent hierarchy.

---

## 2. Scrapling (D4Vinci/Scrapling)

**GitHub:** github.com/D4Vinci/Scrapling  
**Vitals:** 70k ★ | 6.9k forks | 1,532 commits | Actively maintained | 49 releases | Python 3.x

**What it is:** Modern Python web scraping framework. Async, adaptive parsing that auto-relocates elements when target pages restructure. Bypasses Cloudflare Turnstile and other anti-bot systems out of the box. Spider framework with concurrent multi-session crawling, pause/resume, automatic proxy rotation. Has CLI, MCP server, and AI agent-skill integration.

**Practical Utility: 4/10**
- We already have **Crawl4AI** installed and working. Scrapling is solving the same problem class — web scraping for AI agents
- Scrapling's main differentiators (Cloudflare bypass, adaptive parsing, proxy rotation) aren't relevant to our core trading workflow. We scrape market data from MT5/broker APIs, not random websites behind Cloudflare
- If we ever need to scrape financial data from sites with anti-bot protection (e.g., news sites, exchange dashboards), Scrapling would be useful — but that's an edge case for our org
- Its spider framework is well-designed but we already have our orchestration layer
- The agent-skill directory and MCP integration is nice but we'd be building on top of a second scraping library when Crawl4AI already works

**Integration Ease: 7/10**
- `pip install scrapling` — standard Python package
- Well-documented (readthedocs), multi-language READMEs, active Discord
- Clean API, async-native
- But: we'd have to maintain a parallel scraping stack alongside Crawl4AI, which adds cognitive overhead

**Recommendation: WATCH**

> Keep on radar. If we ever hit a concrete anti-bot problem that Crawl4AI can't handle (Cloudflare Turnstile, for instance), Scrapling is the obvious fallback. Not worth adopting now — we'd just be maintaining redundant infrastructure. Revisit only if a specific scraping need arises that Crawl4AI cannot solve.

---

## 3. mattpocock/skills

**GitHub:** github.com/mattpocock/skills  
**Vitals:** 177k ★ | 15.2k forks | 313 commits | Very actively maintained | 58 branches

**What it is:** Collection of AI coding agent skills by Matt Pocock (TypeScript educator). Skills include: `/grill-me` (requirements clarification), `/grill-with-docs`, `/triage`, `/to-spec`, `/to-tickets`, engineering workflows, planning/estimation skills. Designed for Claude Code primarily, supports Codex and other agent-skills-standard harnesses. Has skills.sh installer and Claude Code plugin.

**Practical Utility: 3/10**
- The skills are **general software engineering** focused — TypeScript ecosystem, issue tracking, spec writing, code review
- Zero trading domain knowledge. No finance, no algorithmic trading patterns
- The methodology concepts (grill-me for requirements gathering, triage, spec writing) are solid engineering practices but don't require this repo — they're well-known patterns
- The TypeScript/Node.js focus is irrelevant — our stack is Python/MT5
- These are skills for **coding agents** (Claude Code, Codex), not our Hermes trading agents. The skill format is different from Hermes skills
- 177k stars is impressive but reflects popularity in the frontend/TypeScript dev community, not trading

**Integration Ease: 2/10**
- Designed for Claude Code's plugin system and Agent-Skills standard — not directly compatible with Hermes Agent's skill format
- Even if we manually adapted the concepts, the content is so engineering-focused that the ROI is near zero
- The skills.sh installer requires npx (Node.js) — irrelevant to our Python stack
- Would need significant adaptation to work with Hermes, and the result would be generic

**Recommendation: REJECT**

> Not applicable to our org. TypeScript engineering skills have no crossover with algorithmic trading in Python. The methodology patterns (grill-me, triage) are standard engineering practices we can source from anywhere if needed. Skip.

---

## 4. Kimi K3 (Moonshot AI)

**Provider:** Moonshot AI (api.moonshot.cn)  
**Model:** kimi-k3 | 2.8T parameters | 1M token context | Open source (weights due July 27)  
**Pricing:** ¥20/1M tokens input (cache miss), ¥2/1M (cache hit), ¥100/1M tokens output  
**USD equivalent:** ~$2.76 input / $13.80 output per 1M tokens (at ~¥7.25/USD)  
**Region:** Chinese service — no US geo-blocking concerns from HK

**What it is:** Kimi's flagship model. 2.8T parameter MoE (896 experts, 16 active per token). Based on Kimi Delta Attention (KDA) + Attention Residuals architecture. Reasoning, tool calls, JSON mode, structured output, vision, web search, automatic context caching. OpenAI-compatible API. **Explicitly lists Hermes Agent in its supported ecosystem integrations.**

**Practical Utility: 7/10**
- **Critically: works from HK without geo-blocking concerns** — this is a major advantage over US API providers (OpenAI, Anthropic) and possibly DeepSeek via Headroom proxy
- Native Hermes Agent support (listed on their official integrations page alongside Claude Code, Codex, OpenCode) — means configuration is documented and tested
- 1M context window is genuinely useful for our trading analysis (we process large strategy backtest logs, market data windows)
- Supports everything we need: tool calls, JSON mode, reasoning, structured output
- Open source (weights coming) — potential for self-hosting
- **BUT: pricing is steep.** At ¥100/1M output tokens ($13.80), heavy trading analysis workloads could get expensive fast. DeepSeek V4 Flash via Headroom is currently free
- No benchmark data specific to trading/coding tasks compared to DeepSeek V4 Flash — we'd need to test

**Integration Ease: 8/10**
- OpenAI-compatible API — just change `base_url` and `api_key` in existing code
- Hermes Agent supports Kimi as a provider (listed in their ecosystem page)
- Standard pip/Chat Completions SDK usage
- Chinese documentation only — may need translation for non-Chinese-speaking team members
- Need a Chinese phone number/WeChat for account registration? (Potential friction point)
- Rate limits and latency unknown for heavy trading workloads

**Recommendation: TRIAL**

> Strong secondary/fallback model candidate. The HK-friendly access alone justifies a trial. Start with a small trial budget (~¥500/~$70) to benchmark against DeepSeek V4 Flash on our actual trading agent tasks (strategy analysis, code generation, backtest interpretation). If quality matches or exceeds DeepSeek and latency is acceptable, adopt as our primary Hermes provider. The 1M context is a genuine differentiator for large-window analysis. The pricing, while non-trivial, is manageable for moderate usage — just don't use it for high-volume batch jobs.

---

## Summary Table

| Resource | Utility (1-10) | Integration (1-10) | Recommendation | Key Reason |
|---|---|---|---|---|
| **system_prompts_leaks** | **8** | **9** | **ADOPT** | Directly improves our Hermes agent prompts; zero integration cost |
| **Scrapling** | **4** | **7** | **WATCH** | Redundant with Crawl4AI; keep for anti-bot edge cases |
| **mattpocock/skills** | **3** | **2** | **REJECT** | TypeScript engineering skills, not applicable to trading/Python |
| **Kimi K3** | **7** | **8** | **TRIAL** | HK-friendly, Hermes-integrated, 1M context; expensive but promising |

## Action Items

1. **Immediately:** `git clone system_prompts_leaks` into `C:\Trading\research_division\references\` — start using Claude Code subagent patterns to refine our trading agent prompts
2. **This week:** Set up a Kimi K3 trial account (api.moonshot.cn) with ¥500 credit. Configure Hermes to use `kimi-k3` as an alternate provider. Run our standard agent benchmark suite (strategy analysis prompt, code gen task, backtest interpretation) comparing DeepSeek V4 Flash vs Kimi K3 on output quality, latency, and token cost
3. **On radar:** If we hit any anti-bot scraping issues that Crawl4AI can't handle, revisit Scrapling immediately
4. **No action:** mattpocock/skills — skip entirely
