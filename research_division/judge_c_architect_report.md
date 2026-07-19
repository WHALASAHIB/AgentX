# Judge C (Architect) — Resource Evaluation Report

**Date**: 2026-07-19
**Context**: Algorithmic trading hedge fund, Python/MT5 stack, Windows 11, HK-based (US geo-blocked). Headroom proxy at 127.0.0.1:8787 → DeepSeek.

---

## 1. system_prompts_leaks

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Prod Readiness** | **9/10** | 59K⭐, CC0 license, actively maintained. Content is plain markdown — zero runtime risk. |
| **Integration Ease** | **10/10** | Zero dependencies. Clone or download a folder of .md files. Read and adapt. No install, no config, no API keys. |
| **Maintainability** | **10/10** | No deps, no upgrades, no breaking changes. Just files. If the repo vanishes, you lose nothing you can't re-derive. |
| **Recommendation** | **ADOPT** | |

**Reasoning**: Pre-built collection of real AI system prompts (OpenAI GPT-5.x, Claude Opus 4.6–4.8, Sonnet 5, DeepSeek, Gemini, Grok, etc.). Invaluable for:
- **Prompt engineering research**: Study how frontier labs structure system prompts, guardrails, personality instructions
- **Red-teaming/security**: Understand common prompt injection surfaces
- **Strategy agent prompts**: Reverse-engineer patterns for trading agent instructions

No integration cost whatsoever. Clone into the research repo and annotate. Only caveat: content is crowdsourced leak data — some prompts may be speculative or outdated. Cross-reference before production use. CC0 license means zero legal friction.

---

## 2. Scrapling

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Prod Readiness** | **8/10** | 70K⭐, BSD-3-Clause, actively maintained (4 open issues only). Proven anti-bot bypass. |
| **Integration Ease** | **7/10** | `pip install scrapling` works. Python 3.10+ (we have 3.12 ✓). Optional dependencies for fetchers/Playwright need consideration. |
| **Maintainability** | **6/10** | New dependency with potential churn (fast-moving project). Need to track updates. Optional fetchers add dependency surface. |
| **Recommendation** | **TRIAL** | |

**Reasoning**: Scrapling differentiates from our existing Crawl4AI (v0.9.1) in three key areas:

1. **Adaptive parsing** — Auto-relocates elements when site structure changes. Crawl4AI doesn't do this.
2. **Stealth/anti-bot** — Built-in Cloudflare Turnstile bypass, adaptive browser fingerprinting. Crawl4AI has basic stealth via playwright-stealth but is less sophisticated.
3. **Proxy rotation + spider framework** — Built-in concurrent crawling with pause/resume. Crawl4AI has async crawling but less mature proxy management.

**Where they overlap**: Both can fetch pages, parse HTML, extract content. For basic LLM-friendly crawling (markdown extraction, site mapping), Crawl4AI is already installed and working well.

**Verdict**: NOT redundant overall. Scrapling adds real value for:
- Scraping broker/data-sites with aggressive anti-bot protection (e.g. TradingView, Bloomberg, exchange data portals)
- Sites that change layout frequently (adaptive selectors reduce maintenance)
- Our US geo-block workaround needs (proxy rotation)

**Recommend TRIAL**: `pip install scrapling` on one machine, test against 2-3 broker sites that Crawl4AI struggles with. If it successfully bypasses protections Crawl4AI cannot, promote to ADOPT.

---

## 3. mattpocock/skills

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Prod Readiness** | **1/10** | Excellent repo (177K⭐) but built for TypeScript/JS ecosystem. Zero value to our Python stack. |
| **Integration Ease** | **2/10** | Would need Node.js + npm + TypeScript toolchain. Not installed. Could read .md skill files manually, but skills are about TS dev workflows. |
| **Maintainability** | **1/10** | Adding TypeScript to our Python stack creates a cross-language maintenance burden for zero benefit. |
| **Recommendation** | **REJECT** | |

**Reasoning**: Matt Pocock's "Skills for Real Engineers" is a high-quality collection of agent skills, but it targets TypeScript developers building coding agents. The `.agents/` directory contains markdown files for TypeScript/React tooling patterns (e.g. writing-docs.md, invocation.md, adr). The `skills/` directory is organized around engineering, productivity, and personal — all oriented toward TypeScript/JS development workflows.

Our org is Python-based algorithmic trading. We don't need:
- TypeScript linting/formatting skills
- React component design patterns
- Node.js dependency management skills

Could theoretically read the skill format for inspiration on structuring our own skills, but the content itself has zero applicability. Not worth the toolchain setup.

---

## 4. Kimi K3

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Prod Readiness** | **5/10** | Production API but significant cost barrier and uncertain routing path |
| **Integration Ease** | **4/10** | OpenAI-compatible API ✓. But requires: new API key, account setup (Chinese service), and either Headroom reconfig or new Hermes provider entry |
| **Maintainability** | **3/10** | Cost is 1000× DeepSeek. Context window (1M) is impressive but ¥100/1M output is extreme. Would need active cost monitoring. |
| **Recommendation** | **WATCH** | |

**Reasoning**:

**Pricing (per 1M tokens)**:
| | Input (cache hit) | Input (cache miss) | Output |
|---|---|---|---|
| Kimi K3 | ¥2 ($0.28) | ¥20 ($2.75) | ¥100 ($13.75) |
| DeepSeek (current) | ~$0.07 | ~$0.07 | ~$0.014 |

Kimi K3 output is ~**1000× more expensive** than DeepSeek. For a hedging firm doing heavy LLM calls, this is non-trivial.

**Headroom proxy compatibility**:
- Headroom v0.28.0 currently routes to DeepSeek via `HEADROOM_BACKEND=openai` / `HEADROOM_OPENAI_BASE_URL=https://api.deepseek.com/v1`
- Headroom supports separate flags for Gemini (`--gemini-api-url`), Bedrock (`--bedrock-api-url`), Vertex (`--vertex-api-url`), CloudCode (`--cloudcode-api-url`)
- But only ONE OpenAI-compatible backend at a time
- **Cannot** route to both DeepSeek and Kimi via the same Headroom instance without additional infrastructure

**Two integration paths**:

1. **Via Headroom (simple but exclusive)**: Change `HEADROOM_OPENAI_BASE_URL` to `https://api.moonshot.cn/v1`, set `HEADROOM_OPENAI_API_KEY` to Kimi key. **But this kills DeepSeek access** through the proxy.

2. **Via Hermes config directly (better)**: Add Kimi as a separate provider entry alongside `openai` (which routes through Headroom→DeepSeek) and `ollama`. Hermes config already shows a `providers:` structure — we could add:
   ```yaml
   providers:
     kimi:
       api_key: <KIMI_KEY>
       base_url: https://api.moonshot.cn/v1
   ```
   This keeps both providers available, switching via model name. No geo-block from HK.

**Geo**: Chinese service (api.moonshot.cn). Works fine from HK. No US geo-block issue.

**Capabilities**: 1M token context, reasoning, tool calling, JSON mode, context caching. Strong for long-context tasks like research/analysis. But cost makes it a niche tool, not a primary model.

**Verdict**: Only consider for specific tasks where 1M context or Chinese-language optimization matters. The cost premium over DeepSeek is too high for general use. **Watch** — re-evaluate if pricing drops or if a specific use case (e.g. analyzing Chinese financial documents) justifies the premium.

---

## Summary Table

| Resource | Prod Readiness | Integration Ease | Maintainability | Verdict | Key Deciding Factor |
|----------|:---:|:---:|:---:|:---:|:---|
| system_prompts_leaks | 9 🟢 | 10 🟢 | 10 🟢 | **ADOPT** | Zero cost, zero risk, immediate value for prompt research |
| Scrapling | 8 🟢 | 7 🟡 | 6 🟡 | **TRIAL** | Anti-bot + adaptive parsing fill Crawl4AI gaps |
| mattpocock/skills | 1 🔴 | 2 🔴 | 1 🔴 | **REJECT** | TypeScript content; zero fit for Python trading stack |
| Kimi K3 | 5 🟡 | 4 🟡 | 3 🔴 | **WATCH** | 1000× cost premium over DeepSeek; narrow niche value |
