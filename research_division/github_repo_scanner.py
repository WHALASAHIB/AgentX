#!/usr/bin/env python3
"""
AGENTX GitHub Repo Scanner — Research & Innovation Division.

Silent cron job that searches GitHub for repos useful to our stack.
Stays quiet (exit 0, no output) until it finds genuinely valuable repos.
When found, prints candidate repo info for CEO council evaluation.

State file tracks all repos ever seen so nothing is recommended twice.

Search categories:
  - Algorithmic trading / MT5 / MetaTrader
  - Trading dashboards / FastAPI / real-time
  - Prop firm / FTMO / risk management
  - Multi-agent AI trading
  - Backtesting frameworks
  - Portfolio management
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────
HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
STATE_DIR = Path(os.environ.get("RESEARCH_STATE_DIR", str(HERMES_HOME / "cron")))
STATE_FILE = STATE_DIR / "github_scanner_state.json"
SCRIPT_DIR = Path(__file__).resolve().parent

GITHUB_API = "https://api.github.com/search/repositories"
RESULTS_PER_QUERY = 10  # per search term
MAX_RESULTS_PER_RUN = 20  # total new repos to report in one cycle
RATE_LIMIT_SLEEP = 3  # seconds between API calls to avoid 403

# Search queries — organized by relevance to AGENTX
SEARCH_QUERIES = [
    # Core trading
    '"algorithmic trading" language:python stars:>50',
    '"MetaTrader 5" language:python stars:>20',
    '"prop firm" OR FTMO language:python stars:>10',
    
    # Infrastructure
    '"trading dashboard" fastapi language:python stars:>30',
    '"real-time dashboard" websocket trading stars:>30',
    '"trading platform" react nextjs stars:>50',
    
    # AI & Multi-agent
    '"multi-agent" trading language:python stars:>30',
    '"AI trading bot" language:python stars:>20',
    '"trading agent" large language model stars:>20',
    
    # Backtesting & Risk
    '"backtesting framework" python stars:>100',
    '"risk management" trading python stars:>30',
    '"portfolio optimization" python stars:>50',
    
    # Data & Visualization
    '"market data" python API free stars:>30',
    '"trading chart" react typescript stars:>50',
    '"real-time data" websocket python trading stars:>20',
]

# Languages to prioritize
PREFERRED_LANGS = {"Python", "TypeScript", "JavaScript", "Rust", "Go"}

# Keywords to exclude (noise)
EXCLUDE_KEYWORDS = [
    "bitcoin", "crypto", "nft", "memecoin", "meme", "shitcoin",
    "solana", "ethereum", "blockchain", "web3", "defi",
]


def load_state() -> dict:
    """Load previously seen repos from state file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "seen_repos": {},  # repo_full_name -> {first_seen, last_seen, score, name}
        "last_run": None,
        "total_runs": 0,
    }


def save_state(state: dict):
    """Persist state to disk."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def github_search(query: str, page: int = 1) -> list[dict]:
    """Execute a GitHub search query. Returns list of repo dicts."""
    params = urllib.parse.urlencode({
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": RESULTS_PER_QUERY,
        "page": page,
    })
    url = f"{GITHUB_API}?{params}"
    
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "AGENTX-ResearchBot/1.0")
    
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode())
        
        # Rate limit info
        remaining = resp.headers.get("X-RateLimit-Remaining", "0")
        reset_ts = resp.headers.get("X-RateLimit-Reset", "0")
        
        items = data.get("items", [])
        repos = []
        for item in items:
            full_name = item.get("full_name", "")
            lang = item.get("language") or ""
            desc = (item.get("description") or "")[:300]
            
            # Skip if description contains excluded keywords
            desc_lower = desc.lower() + full_name.lower()
            if any(kw in desc_lower for kw in EXCLUDE_KEYWORDS):
                continue
            
            repos.append({
                "full_name": full_name,
                "name": item.get("name", ""),
                "url": item.get("html_url", ""),
                "description": desc,
                "language": lang,
                "stars": item.get("stargazers_count", 0),
                "forks": item.get("forks_count", 0),
                "open_issues": item.get("open_issues_count", 0),
                "updated_at": item.get("updated_at", ""),
                "created_at": item.get("created_at", ""),
                "topics": item.get("topics", []),
                "license": (item.get("license") or {}).get("spdx_id", ""),
            })
        
        return repos, int(remaining), int(reset_ts)
    
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return [], 0, 0  # Rate limited
        return [], 0, 0
    except Exception:
        return [], 0, 0


def score_repo(repo: dict) -> int:
    """Score a repo for relevance to AGENTX (0-100)."""
    score = 0
    desc = (repo.get("description") or "").lower()
    name = repo.get("name", "").lower()
    topics = [t.lower() for t in repo.get("topics", [])]
    combined = desc + " " + name + " " + " ".join(topics)
    
    # ++ High-value keywords
    high_value = [
        "algorithmic trading", "quantitative trading", "meta trader", "mt5", "mt4",
        "trading bot", "trading strategy", "trading platform",
        "real-time trading", "live trading", "automated trading",
        "backtesting", "backtester", "prop firm", "ftmo",
    ]
    for kw in high_value:
        if kw in combined:
            score += 15
    
    # + Medium-value keywords
    med_value = [
        "fastapi", "websocket", "streaming", "real-time",
        "dashboard", "react", "next.js", "typescript",
        "multi-agent", "llm agent", "ai agent",
        "portfolio", "risk management", "position sizing",
        "gold trading", "forex", "xauusd",
    ]
    for kw in med_value:
        if kw in combined:
            score += 8
    
    # Language bonus
    lang = repo.get("language", "")
    if lang == "Python":
        score += 5
    elif lang in ("TypeScript", "Rust"):
        score += 3
    
    # Stars bonus
    stars = repo.get("stars", 0)
    if stars >= 1000:
        score += 10
    elif stars >= 500:
        score += 7
    elif stars >= 200:
        score += 4
    elif stars >= 100:
        score += 2
    
    # Recent activity bonus
    updated = repo.get("updated_at", "")
    if updated:
        try:
            updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            days_since = (datetime.now(timezone.utc) - updated_dt).days
            if days_since < 30:
                score += 5
            elif days_since < 90:
                score += 3
        except ValueError:
            pass
    
    return min(score, 100)


def format_repo(repo: dict) -> str:
    """Format a single repo for output."""
    score = repo.get("_score", 0)
    stars = repo["stars"]
    lang = repo.get("language", "N/A")
    desc = repo.get("description", "No description").strip()
    if desc and not desc.endswith("."):
        desc += "."
    
    score_bar = "🟢" if score >= 50 else "🟡" if score >= 30 else "⚪"
    
    return (
        f"{score_bar} **{repo['full_name']}** ⭐{stars}\n"
        f"   _{lang}_ — Score: {score}/100\n"
        f"   {desc}\n"
        f"   {repo['url']}"
    )


def main():
    state = load_state()
    state["total_runs"] = state.get("total_runs", 0) + 1
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    
    seen = state.setdefault("seen_repos", {})
    candidates = []
    remaining_quota = 60  # assume worst case
    
    for i, query in enumerate(SEARCH_QUERIES):
        # Check rate limit before each query
        if remaining_quota < 5:
            break
        
        repos, remaining, reset_ts = github_search(query)
        remaining_quota = remaining
        
        for repo in repos:
            full_name = repo["full_name"]
            
            # Skip if already seen
            if full_name in seen:
                continue
            
            # Score and rank
            repo["_score"] = score_repo(repo)
            
            # Skip low-value repos
            if repo["_score"] < 20:
                continue
            
            candidates.append(repo)
        
        # Be nice to GitHub API
        time.sleep(RATE_LIMIT_SLEEP)
    
    # Deduplicate by full_name (same repo may match multiple queries)
    seen_names = set()
    unique_candidates = []
    for repo in sorted(candidates, key=lambda r: r["_score"], reverse=True):
        if repo["full_name"] not in seen_names:
            seen_names.add(repo["full_name"])
            unique_candidates.append(repo)
    
    # Mark all as seen (even low-scoring ones — avoid re-scanning noise)
    for repo in candidates:
        seen[repo["full_name"]] = {
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "score": repo["_score"],
            "name": repo["full_name"],
        }
    
    save_state(state)
    
    # ── OUTPUT ─────────────────────────────────────────────────────────────
    if not unique_candidates:
        # Silent exit — nothing new worth reporting
        sys.exit(0)
    
    # Take top N
    top_candidates = unique_candidates[:MAX_RESULTS_PER_RUN]
    
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    hkt = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S HKT")
    
    print(f"🔍 **GitHub Discovery Report** — {now} / {hkt}")
    print(f"Found **{len(unique_candidates)} new candidate repo(s)** worth council review.")
    print()
    
    for repo in top_candidates:
        print(format_repo(repo))
        print()
    
    print("---")
    print(f"_Council will judge each repo before sending to Commander._")
    print(f"_Run #{state['total_runs']} | {len(seen)} repos tracked total._")


if __name__ == "__main__":
    main()
