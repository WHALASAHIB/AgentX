# Judge B (Academic) — Resource Ratings

**Evaluator:** Judge B (Academic Lens)
**Date:** 2026-07-19
**Org Context:** Algorithmic trading hedge fund, Python/MT5 stack, Hermes agent, HK-based (US geo-blocked)

---

## 1. system_prompts_leaks

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Educational Depth** | 9/10 | Leaked system prompts from frontier models (Claude Fable 5, Opus 4.8, ChatGPT 5.6/5.5, Gemini 3.5 Flash, Grok 4.3, DeepSeek, Kimi K3, Codex, Copilot, etc.). Each prompt is a masterclass in prompt engineering — structuring agent behavior, tool definitions, communication guidelines, safety constraints, and output formatting. The Kimi K3 prompt alone is 611 lines of detailed system architecture. Invaluable for anyone writing production agent prompts. |
| **Documentation Quality** | 8/10 | README is outstanding: organized by vendor with nested tables, recent-updates table, links to official published prompts, categorized by model family, and even a "Recently Updated" section. Directory structure mirrors vendor org. Lacks formal API-style docs, but the repo is inherently self-documenting. |
| **Completeness** | 8/10 | Covers Anthropic (8+ Claude models, Claude Code variants, Claude Design, integrations), OpenAI (ChatGPT 5.x series, Codex, API prompts, deprecated features), Google (Gemini 3.x, 2.x, CLI, Jules, Workspace), xAI (Grok 4.x), DeepSeek, Kimi, Microsoft (Copilot, VS Code), Meta, GLM, and 30+ more. 662 commits, updated hourly. Very comprehensive but some older models may have drifted from current deployed versions. |

**Recommendation: ADOPT**

**Reasoning:** Directly applicable to improving Hermes agent prompts. The structural patterns — how frontier models define tool calling, subagent dispatch, communication protocols, and safety guardrails — are immediately transferable to our Hermes agent skills and system prompts. For an algorithmic trading fund using agentic patterns, understanding how the best models structure their own behavior is a force multiplier. No equivalent resource exists elsewhere.

---

## 2. Scrapling

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Educational Depth** | 7/10 | Comprehensive library covering adaptive parsing, multiple fetcher types (Stealthy, Dynamic, Async), spider framework with concurrent crawling, proxy rotation, MCP server integration, and CLI tools. The adaptive parsing (auto-re-locating elements after site structure changes) is genuinely innovative. Code examples are clean and instructive. Missing deeper theoretical explanations of anti-bot bypass mechanics. |
| **Documentation Quality** | 8/10 | ReadTheDocs-hosted docs with sections on parsing/selection, fetchers, spiders, proxy/blocking handling, CLI, and MCP. Has migration guides (BeautifulSoup → Scrapling), interactive shell docs, tutorials. README in 9 languages. Agent-skill directory for AI integration. Active Discord community. Good but not exhaustive — some advanced features lack deep treatment. |
| **Completeness** | 7/10 | Covers the full scraping lifecycle: fetching → parsing → crawling → data extraction. Has adaptivity, stealth, proxy rotation, Docker support, CI/CD. But still in Beta (v0.4.11). Some features (MCP server, AI extras) are newer and less battle-tested. Good breadth, moderate depth per feature. |

**Recommendation: TRIAL**

**Reasoning:** Viable alternative/complement to Crawl4AI. Scrapling's strengths are adaptive parsing (auto-adjusts to site changes — useful for scraping financial data portals that change layouts) and stealth fetchers (bypasses Cloudflare Turnstile out of the box — useful since we're HK-based and many US financial sites are geo-blocked). However, Crawl4AI is more mature for LLM-oriented extraction (clean markdown output). Recommend a 2-week trial on a scraping task (e.g., HK exchange data or financial news) to compare against Crawl4AI head-to-head. Lower priority than system_prompts_leaks.

---

## 3. mattpocock/skills

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Educational Depth** | 6/10 | Excellent software engineering philosophy (GSD alternative, pragmatic programmer principles, DDD, TDD). Skills like `/grill-me`, `/tdd`, `/code-review`, `/diagnosing-bugs` are well-conceived and practically useful. The README essay on why these skills exist (misalignment, verbosity, code quality, ball-of-mud) shows deep thinking. However, the content is entirely TypeScript/JavaScript — our stack is Python. |
| **Documentation Quality** | 7/10 | Each skill has its own SKILL.md with clear instructions, trigger conditions, and workflow steps. The main README is a thorough engineering manifesto. Has docs/ directory, ADR records, changelog, and plugin documentation. However, the actual skill files are designed for Claude Code/Codex agent consumption, not human academic study. |
| **Completeness** | 7/10 | 25+ skills across engineering, productivity, personal, and misc categories. Covers the full development lifecycle: triage → spec → tickets → implement → review → deploy. Has plugin ecosystem, Claude Code integration, CLI installer (skills.sh), newsletter with 60k+ subscribers. Well-rounded but the skills format (markdown files for AI agents) is not a traditional "course" or "tutorial." |

**Recommendation: WATCH**

**Reasoning:** High-quality content from a respected TypeScript educator (177k stars speaks for itself). The **engineering philosophy** (grill sessions for alignment, TDD loops, code review discipline, domain modeling) is language-agnostic and worth studying. However, the actual skills are TypeScript-specific, and our org runs Python/MT5. The concepts are valuable but require translation. Put on watch for: (a) if Matt publishes Python-equivalent skills, (b) if we need to improve our agent development workflow and want to borrow patterns. Not an immediate adopt.

---

## 4. Kimi K3 (Moonshot AI)

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Educational Depth** | 5/10 | As an LLM, K3 itself is not an "educational resource" — it's a tool. The educational value comes from its leaked system prompt (611 lines, extremely detailed internal architecture) and its novel training approaches (Muon optimizer, MoBA hybrid block attention). K3's architecture is interesting academically: reasoning-on-always model with 1M context, comparable to DeepSeek V4 Flash. However, the model itself is closed-source with limited published technical papers. |
| **Documentation Quality** | 7/10 | Kimi API platform has professional Mintlify-hosted docs: quickstart guides, model capabilities (thinking mode, streaming, JSON mode, vision, tool calling, context caching), API reference with OpenAPI spec, pricing tables, integration guides (Claude Code, Codex, Hermes Agent, OpenCode), and best practices. Well-structured but Chinese-language primary with partial English support. |
| **Completeness** | 4/10 | The API is well-documented but the model itself has limited public information. Few technical papers, no open-source weights, no benchmarks vs competing models from independent evaluators. We know: 1M context, visual capabilities, reasoning-on-always, ¥20-100/1M tokens. We don't know: training methodology details, architectural specifics beyond "MoBA attention," benchmark scores, or how it compares to DeepSeek V4 Flash on specific coding/finance tasks. |

**Recommendation: TRIAL**

**Reasoning:** Potentially valuable for our HK-based org. Three unique selling points against DeepSeek V4 Flash: (1) **1M context** — capable of ingesting entire strategy research papers or full codebases in one pass; (2) **Chinese-language strength** — superior on Chinese financial news analysis, HK exchange filings, and Mandarin-language quant research that DeepSeek may handle less naturally; (3) **HK proximity** — lower latency than US-hosted models, and Kimi is not US geo-blocked (we're HK-based, so the block on OpenAI/Anthropic doesn't apply to Chinese LLMs). However, we already have DeepSeek V4 Flash which is a strong baseline. Recommend a targeted trial: compare Kimi K3 vs DeepSeek V4 Flash on 3 tasks — (a) Chinese financial document analysis, (b) long-context strategy research summarization (>100K tokens), (c) Python/MT5 code generation for trading strategies.

---

## Summary Table

| Resource | Depth | Docs | Completeness | Rec | Key Context for Our Org |
|----------|-------|------|-------------|-----|------------------------|
| **system_prompts_leaks** | 9 | 8 | 8 | **ADOPT** | Directly improves Hermes agent prompt engineering |
| **Scrapling** | 7 | 8 | 7 | **TRIAL** | Compare vs Crawl4AI for HK financial data scraping |
| **mattpocock/skills** | 6 | 7 | 7 | **WATCH** | TypeScript-specific; borrow engineering philosophy only |
| **Kimi K3** | 5 | 7 | 4 | **TRIAL** | Chinese content + 1M context; trial vs DeepSeek V4 Flash |

---

## Priority Actions

1. **IMMEDIATE (ADOPT)** — `system_prompts_leaks`: Clone repo, study Claude Code and Codex system prompts for structuring our Hermes agent skills. Focus on tool definition patterns, subagent dispatch, and communication guardrails.

2. **THIS WEEK (TRIAL)** — `Kimi K3`: Set up API key, run 3-task comparison against DeepSeek V4 Flash on Chinese financial analysis, long-context processing, and code generation.

3. **THIS WEEK (TRIAL)** — `Scrapling`: Install and run a side-by-side scrape of an HK financial data source (e.g., HKEX announcements) comparing against Crawl4AI.

4. **BACKLOG (WATCH)** — `mattpocock/skills`: Study the engineering methodology (grill-me, tdd, code-review patterns) for potential adaptation to our Python stack, but no immediate implementation.
