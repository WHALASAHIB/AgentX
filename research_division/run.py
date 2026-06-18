"""
AGENTX Research & Invocation Division — Main Orchestrator
=========================================================
Cron entry point. Runs the full analysis-sprint-innovate-deploy cycle.

Execution modes:
  --full      : Full cycle (collect → analyze → sprint → innovate → deploy → report)
  --collect   : Data collection + cache only
  --analyze   : Analytics only (requires cached data)
  --standup   : Generate daily standup report only
  --sprint    : Run sprint lifecycle (plan → innovate → deploy on top items)
  --status    : Quick status report (no data collection)
  --once      : Full cycle, then exit (for initial seed run)

Scheduled via cron:
  - Every 4 hours: --full (08:00, 12:00, 16:00, 20:00, 00:00, 04:00 HKT)
  - 08:00 HKT: Sprint planning + daily standup
  - 20:00 HKT: Sprint review + deployment
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure we can import from research_division
_SELF_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF_DIR))
sys.path.insert(0, str(_SELF_DIR.parent))  # For backtester imports

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [RD] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(_SELF_DIR / "division.log"), mode="a"),
    ],
)
logger = logging.getLogger("research_division")

# ── HKT time helper ──────────────────────────────────────────────────────
HKT = timezone(timedelta(hours=8))
UTC = timezone.utc


def now_hkt() -> datetime:
    return datetime.now(HKT)


def is_sprint_planning_time() -> bool:
    """Sprint planning at 08:00 HKT"""
    return now_hkt().hour == 8


def is_sprint_review_time() -> bool:
    """Sprint review at 20:00 HKT"""
    return now_hkt().hour == 20


def is_deep_research_time() -> bool:
    """Deep research runs at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 HKT"""
    return now_hkt().hour in [0, 4, 8, 12, 16, 20]


# ── Import resolution ────────────────────────────────────────────────────
def _import_module(name: str):
    """Import a research_division module with error handling."""
    try:
        return __import__(name)
    except ImportError as e:
        logger.error(f"Failed to import {name}: {e}")
        return None


# Lazy-loaded modules
_data_collector = None
_analytics_engine = None
_strategy_innovation = None
_sprint_manager = None
_deployment_engine = None


def _get_modules():
    global _data_collector, _analytics_engine, _strategy_innovation, _sprint_manager, _deployment_engine
    if _data_collector is None:
        _data_collector = _import_module("data_collector")
    if _analytics_engine is None:
        _analytics_engine = _import_module("analytics_engine")
    if _strategy_innovation is None:
        _strategy_innovation = _import_module("strategy_innovation")
    if _sprint_manager is None:
        _sprint_manager = _import_module("sprint_manager")
    if _deployment_engine is None:
        _deployment_engine = _import_module("deployment_engine")
    return _data_collector, _analytics_engine, _strategy_innovation, _sprint_manager, _deployment_engine


# ── Phase 1: Data Collection ─────────────────────────────────────────────
def phase_collect() -> Dict[str, Any]:
    """Collect all trading data from APIs and cache it."""
    logger.info("=== Phase 1: Data Collection ===")
    data_collector, _, _, _, _ = _get_modules()
    if not data_collector:
        return {"status": "error", "error": "data_collector not available"}

    try:
        # Fetch all data
        trades = data_collector.fetch_trade_history(days=30)
        positions = data_collector.fetch_open_positions()
        equity = data_collector.fetch_equity_curve(days=30)
        stats = data_collector.fetch_account_stats(days=30)
        dashboard_stats = data_collector.fetch_dashboard_stats()
        bots = data_collector.fetch_bots_status()
        sentiment = data_collector.fetch_sentiment()

        # Get live ticks for all 9 pairs
        PAIRS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
                 "USDCAD", "AUDUSD", "NZDUSD", "BTCUSD"]
        ticks = {}
        for pair in PAIRS:
            tick = data_collector.get_live_tick(pair)
            if tick:
                ticks[pair] = tick

        # Cache the data
        cache_result = data_collector.cache_trade_data()

        result = {
            "status": "ok",
            "timestamp": now_hkt().isoformat(),
            "trade_count": len(trades),
            "position_count": len(positions),
            "equity_points": len(equity),
            "bots_count": len(bots),
            "sentiment_available": bool(sentiment),
            "cache_written": cache_result,
            "ticks": ticks,
        }
        logger.info(f"Collected: {len(trades)} trades, {len(positions)} positions, {len(bots)} bots")
        return result
    except Exception as e:
        logger.error(f"Data collection failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


# ── Phase 2: Analytics ──────────────────────────────────────────────────
def phase_analyze() -> Dict[str, Any]:
    """Run analytics on cached trade data."""
    logger.info("=== Phase 2: Analytics ===")
    _, analytics, _, _, _ = _get_modules()
    if not analytics:
        return {"status": "error", "error": "analytics_engine not available"}

    try:
        # Try to load cached data first, fall back to fresh fetch
        dc, _, _, _, _ = _get_modules()
        cached = dc.load_cached_data() if dc else None

        if cached and cached.get("trades"):
            trades = cached["trades"]
            logger.info(f"Using {len(trades)} cached trades")
        else:
            logger.warning("No cached data, fetching fresh...")
            collection = phase_collect()
            if collection.get("status") != "ok":
                return {"status": "error", "error": "Cannot collect data"}
            cached = dc.load_cached_data() if dc else None
            trades = cached.get("trades", []) if cached else []

        # Get positions and equity
        positions = dc.fetch_open_positions() if dc else []
        equity = dc.fetch_equity_curve(days=30) if dc else []

        # Generate reports
        reports = analytics.generate_all_reports({"trades": trades}, equity, positions)

        # Get overall KPIs
        overall = reports.get("overall", {})
        pair_reports = {k: v for k, v in reports.items() if k != "overall"}

        # Save analytics history
        analytics.save_analytics(reports)

        result = {
            "status": "ok",
            "timestamp": now_hkt().isoformat(),
            "overall": overall.get("kpis", {}),
            "pairs_analyzed": list(pair_reports.keys()),
            "pair_count": len(pair_reports),
            "reports": reports,
        }

        # Log key metrics
        kpis = overall.get("kpis", {})
        logger.info(
            f"Analytics: {kpis.get('total_trades', 0)} trades, "
            f"{kpis.get('win_rate', 0):.1f}% WR, "
            f"PF={kpis.get('profit_factor', 0):.2f}, "
            f"DD={kpis.get('max_drawdown_pct', 0):.1f}%"
        )
        return result
    except Exception as e:
        logger.error(f"Analytics failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


# ── Phase 3: Sprint Management ───────────────────────────────────────────
def phase_sprint(analytics_result: Dict[str, Any]) -> Dict[str, Any]:
    """Run sprint lifecycle: backlog → innovate → deploy."""
    logger.info("=== Phase 3: Sprint Management ===")
    _, _, innovation, sprint_mgr, deployment = _get_modules()
    if not sprint_mgr:
        return {"status": "error", "error": "sprint_manager not available"}

    try:
        reports = analytics_result.get("reports", {})
        if not reports:
            return {"status": "error", "error": "No analytics reports available"}

        # Load innovation history if available
        innovation_results = []
        if innovation:
            try:
                innovation_results = innovation.load_innovation_history(limit=20)
            except Exception:
                pass

        # Run sprint lifecycle
        lifecycle = sprint_mgr.run_sprint_lifecycle(reports, innovation_results)

        # Detect blockers
        dc, _, _, _, _ = _get_modules()
        open_positions = dc.fetch_open_positions() if dc else []
        blockers = sprint_mgr.detect_blockers(reports, open_positions)

        # Generate standup
        sprint = sprint_mgr.get_sprint() if hasattr(sprint_mgr, 'get_sprint') else None
        standup_text = sprint_mgr.daily_standup(reports, sprint) if sprint else "No active sprint"

        result = {
            "status": "ok",
            "timestamp": now_hkt().isoformat(),
            "sprint": lifecycle.get("sprint", {}),
            "backlog_count": lifecycle.get("backlog_count", 0),
            "blockers": blockers,
            "standup": standup_text,
        }
        logger.info(
            f"Sprint: {result['backlog_count']} backlog items, "
            f"{len(blockers)} blockers detected"
        )
        return result
    except Exception as e:
        logger.error(f"Sprint management failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


# ── Phase 4: Innovation & Deployment ─────────────────────────────────────
def phase_innovate_deploy(sprint_result: Dict[str, Any]) -> Dict[str, Any]:
    """Run innovation sprints on top backlog items and deploy winners."""
    logger.info("=== Phase 4: Innovation & Deployment ===")
    _, analytics, innovation, sprint_mgr, deployment = _get_modules()
    if not innovation or not deployment:
        return {"status": "error", "error": "innovation or deployment unavailable"}

    try:
        sprint = sprint_result.get("sprint", {})
        items = sprint.get("items", []) if sprint else []
        in_progress = [i for i in items if i.get("status") in ("pending", "in_progress")]

        if not in_progress:
            logger.info("No items in progress for innovation sprint")
            return {"status": "ok", "message": "No items to innovate", "deployments": []}

        # Load trade data
        dc, _, _, _, _ = _get_modules()
        cached = dc.load_cached_data() if dc else {}
        trades = cached.get("trades", []) if cached else []

        deployments = []
        for item in in_progress[:3]:  # Max 3 per cycle
            pair = item.get("pair", "")
            strategy = item.get("strategy", "")
            issue = item.get("issue", "")

            logger.info(f"Innovating: {pair}/{strategy} — {issue}")

            # Mark item as in_progress
            if hasattr(sprint_mgr, 'update_sprint_item'):
                sprint_mgr.update_sprint_item(item.get("id"), "in_progress")

            # Get KPIs for this pair/strategy
            reports = analytics.generate_all_reports(
                {"trades": trades},
                dc.fetch_equity_curve(days=30) if dc else [],
                dc.fetch_open_positions() if dc else [],
            ) if analytics else {}

            pair_kpis = reports.get(pair, {}).get("kpis", {})

            try:
                # Run innovation sprint
                if hasattr(innovation, 'innovation_sprint'):
                    innovation_result = innovation.innovation_sprint(
                        pair, strategy, trades, pair_kpis
                    )
                else:
                    innovation_result = None

                if innovation_result and innovation_result.get("best_variant"):
                    best = innovation_result["best_variant"]
                    logger.info(f"Best variant score: {best.get('composite_score', 0):.2f}")

                    # Deploy if improvement is meaningful
                    current_score = pair_kpis.get("win_rate", 0) * 0.3 + \
                                    pair_kpis.get("profit_factor", 0) * 0.2
                    new_score = best.get("composite_score", 0)

                    if new_score > current_score * 1.05:  # At least 5% improvement
                        if hasattr(deployment, 'safe_deploy'):
                            deploy_result = deployment.safe_deploy(
                                {"pair": pair, "strategy": strategy,
                                 "new_params": best.get("params", {}),
                                 "expected_improvement": new_score - current_score},
                                sprint
                            )
                        else:
                            deploy_result = deployment.deploy_improvement(
                                {"pair": pair, "strategy": strategy,
                                 "new_params": best.get("params", {})},
                                sprint
                            )

                        deploy_success = deploy_result.get("success", False)
                        deployments.append({
                            "pair": pair,
                            "strategy": strategy,
                            "variant_score": new_score,
                            "current_score": current_score,
                            "deploy_result": deploy_result,
                        })

                        # Mark sprint item as deployed or failed
                        if hasattr(sprint_mgr, 'update_sprint_item'):
                            new_status = "deployed" if deploy_success else "failed"
                            sprint_mgr.update_sprint_item(item.get("id"), new_status, {"score": new_score})

                        if deploy_success:
                            logger.info(f"Deployed improvement for {pair}/{strategy}")
                        else:
                            logger.warning(f"Deploy failed for {pair}/{strategy}: {deploy_result.get('error', 'unknown')}")
                    else:
                        logger.info(f"Skipping {pair}/{strategy}: improvement too small")
                        # Mark as completed even if skipped (improvement too small)
                        if hasattr(sprint_mgr, 'update_sprint_item'):
                            sprint_mgr.update_sprint_item(item.get("id"), "failed", {"reason": "improvement_too_small"})
            except Exception as e:
                logger.error(f"Innovation failed for {pair}/{strategy}: {e}")
                # Mark sprint item as failed on exception
                if hasattr(sprint_mgr, 'update_sprint_item'):
                    sprint_mgr.update_sprint_item(item.get("id"), "failed", {"error": str(e)})

        return {
            "status": "ok",
            "timestamp": now_hkt().isoformat(),
            "deployments": deployments,
            "items_processed": len(in_progress),
            "deployments_made": len(deployments),
        }
    except Exception as e:
        logger.error(f"Innovate/deploy failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


# ── Phase 5: Report Generation ───────────────────────────────────────────
def phase_report(analytics_result: Dict[str, Any],
                 sprint_result: Dict[str, Any],
                 deploy_result: Dict[str, Any]) -> Dict[str, Any]:
    """Generate formatted report for the dashboard and logging."""
    logger.info("=== Phase 5: Report Generation ===")

    now = now_hkt()
    reports = analytics_result.get("reports", {})
    overall = reports.get("overall", {})
    kpis = overall.get("kpis", {})
    pair_reports = {k: v for k, v in reports.items() if k != "overall"}

    # Build structured report
    report = {
        "generated_at": now.isoformat(),
        "sprint_number": sprint_result.get("sprint", {}).get("sprint_number", 0),
        "market_summary": {
            "total_trades": kpis.get("total_trades", 0),
            "overall_win_rate": round(kpis.get("win_rate", 0) or 0, 1),
            "overall_profit_factor": round(kpis.get("profit_factor", 0) or 0, 2),
            "net_profit": round(kpis.get("net_profit", 0) or 0, 2),
            "max_drawdown": round(kpis.get("max_drawdown_pct", 0) or 0, 1),
            "accounts_balance": kpis.get("balance", 0) or 0,
        },
        "pairs": {},
        "sprint_status": {
            "items_in_progress": len(sprint_result.get("sprint", {}).get("items", [])),
            "blockers": len(sprint_result.get("blockers", [])),
            "backlog": sprint_result.get("backlog_count", 0),
        },
        "deployments": deploy_result.get("deployments", []),
        "blockers": sprint_result.get("blockers", []),
        "standup": sprint_result.get("standup", ""),
    }

    # Per-pair summary
    for pair, preport in pair_reports.items():
        pk = preport.get("kpis", {})
        report["pairs"][pair] = {
            "trades": pk.get("total_trades", 0),
            "win_rate": round(pk.get("win_rate", 0) or 0, 1),
            "profit_factor": round(pk.get("profit_factor", 0) or 0, 2),
            "net_profit": round(pk.get("net_profit", 0) or 0, 2),
            "max_drawdown": round(pk.get("max_drawdown_pct", 0) or 0, 1),
            "consecutive_losses": preport.get("kpis", {}).get("max_consecutive_losses", 0),
        }

    # Save to date-stamped report file
    report_dir = _SELF_DIR / "reports"
    report_dir.mkdir(exist_ok=True)
    report_file = report_dir / f"division_report_{now.strftime('%Y-%m-%d_%H')}.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Also save as latest.json
    latest_file = report_dir / "latest.json"
    with open(latest_file, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"Report saved to {report_file}")
    return report


# ── Full Cycle ───────────────────────────────────────────────────────────
def run_full_cycle() -> Dict[str, Any]:
    """Execute the complete Research Division cycle."""
    logger.info("=" * 60)
    logger.info("RESEARCH & INVOCATION DIVISION — FULL CYCLE START")
    logger.info(f"Time (HKT): {now_hkt().isoformat()}")
    logger.info("=" * 60)

    start = time.time()

    # Phase 1: Collect
    collection = phase_collect()
    if collection.get("status") != "ok":
        logger.error(f"Aborting: Data collection failed — {collection.get('error')}")
        return {"status": "error", "phase": "collect", "error": collection.get("error")}

    # Phase 2: Analyze
    analytics_result = phase_analyze()
    if analytics_result.get("status") != "ok":
        logger.error(f"Analytics failed — {analytics_result.get('error')}")
        analytics_result = {"status": "partial", "reports": {}}

    # Phase 3: Sprint
    sprint_result = phase_sprint(analytics_result)
    if sprint_result.get("status") != "ok":
        logger.warning(f"Sprint management failed — {sprint_result.get('error')}")
        sprint_result = {"status": "partial", "sprint": {}, "blockers": []}

    # Phase 4: Innovate & Deploy (only on deep research hours)
    deploy_result = {"status": "skipped", "deployments": []}
    if is_deep_research_time():
        deploy_result = phase_innovate_deploy(sprint_result)
        if deploy_result.get("status") != "ok":
            logger.warning(f"Innovate/deploy failed — {deploy_result.get('error')}")
            deploy_result = {"status": "partial", "deployments": []}

    # Phase 5: Report
    report = phase_report(analytics_result, sprint_result, deploy_result)

    elapsed = time.time() - start
    logger.info(f"Full cycle completed in {elapsed:.1f}s")

    return {
        "status": "ok",
        "cycle_time_seconds": round(elapsed, 1),
        "collection": collection,
        "analytics": {
            "status": analytics_result.get("status"),
            "pairs_analyzed": analytics_result.get("pairs_analyzed", []),
            "trade_count": analytics_result.get("overall", {}).get("total_trades", 0),
        },
        "sprint": {
            "status": sprint_result.get("status"),
            "backlog_count": sprint_result.get("backlog_count", 0),
            "blocker_count": len(sprint_result.get("blockers", [])),
        },
        "deployments": deploy_result.get("deployments", []),
        "report": report,
    }


# ── Helper: Status Snapshot ──────────────────────────────────────────────
def status_snapshot() -> Dict[str, Any]:
    """Quick status snapshot without data collection."""
    _, _, _, sprint_mgr, deployment = _get_modules()

    sprint = {}
    if sprint_mgr and hasattr(sprint_mgr, 'load_sprint'):
        try:
            sprint = sprint_mgr.load_sprint()
        except Exception:
            pass

    deploy_stats = {}
    if deployment and hasattr(deployment, 'get_deployment_stats'):
        try:
            deploy_stats = deployment.get_deployment_stats()
        except Exception:
            pass

    # Check latest report
    report_file = _SELF_DIR / "reports" / "latest.json"
    latest_report = {}
    if report_file.exists():
        try:
            latest_report = json.loads(report_file.read_text())
        except Exception:
            pass

    return {
        "status": "ok",
        "timestamp": now_hkt().isoformat(),
        "division_version": "1.0.0",
        "sprint": sprint,
        "deployment_stats": deploy_stats,
        "latest_report": latest_report,
        "module_status": {
            "data_collector": _data_collector is not None,
            "analytics_engine": _analytics_engine is not None,
            "strategy_innovation": _strategy_innovation is not None,
            "sprint_manager": _sprint_manager is not None,
            "deployment_engine": _deployment_engine is not None,
        },
    }


# ── CLI Entry Point ──────────────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]

    if "--status" in args:
        result = status_snapshot()
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0)

    if "--once" in args or "--full" in args:
        result = run_full_cycle()
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0)

    if "--collect" in args:
        result = phase_collect()
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0)

    if "--analyze" in args:
        result = phase_analyze()
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0)

    if "--standup" in args:
        dc, analytics, _, sprint_mgr, _ = _get_modules()
        cached = dc.load_cached_data() if dc else {}
        trades = cached.get("trades", []) if cached else []
        positions = dc.fetch_open_positions() if dc else []
        equity = dc.fetch_equity_curve(days=30) if dc else []
        reports = analytics.generate_all_reports({"trades": trades}, equity, positions) if analytics else {}
        sprint = sprint_mgr.load_sprint() if sprint_mgr else {}
        standup = sprint_mgr.daily_standup(reports, sprint) if sprint_mgr else "Cannot generate standup"
        print(standup)
        sys.exit(0)

    if "--sprint" in args:
        analytics_result = phase_analyze()
        sprint_result = phase_sprint(analytics_result)
        print(json.dumps(sprint_result, indent=2, default=str))
        sys.exit(0)

    # Default: run full cycle
    print("Running full Research Division cycle...")
    result = run_full_cycle()
    print(json.dumps(result, indent=2, default=str))
