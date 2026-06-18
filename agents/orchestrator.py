import random
import time
from datetime import datetime, timezone
from typing import Any

from agents.ta_agent import TechnicalAnalysisAgent
from agents.sentiment_agent import MarketSentimentAgent
from agents.risk_agent import RiskManagementAgent
from agents.order_execution_agent import OrderExecutionAgent
from agents.portfolio_allocator_agent import PortfolioAllocatorAgent
from agents.macro_event_agent import MacroeconomicEventAgent

# Initialize agents
ta_agent = TechnicalAnalysisAgent()
sentiment_agent = MarketSentimentAgent()
risk_agent = RiskManagementAgent()
exec_agent = OrderExecutionAgent()
portfolio_agent = PortfolioAllocatorAgent()
macro_agent = MacroeconomicEventAgent()

def run_orchestrator_cycle(state: Any):
    """
    Coordinates one execution pass of all backend agents.
    Updates the thread-safe state object with metrics and logs.
    """
    symbol = state.active_symbol
    lot_size = state.lot_size
    drawdown_limit = state.risk_drawdown_limit
    
    # 1. Simulate tick price based on active symbol
    if symbol == "XAUUSD":
        base_price = 2300.0
    elif symbol == "EURUSD":
        base_price = 1.0850
    else:
        base_price = 100.0
        
    current_price = base_price + random.uniform(-10.0, 10.0) if symbol == "XAUUSD" else base_price + random.uniform(-0.005, 0.005)
    
    state.log(f"Tick received: {symbol} @ {current_price:.4f}")

    # 2. Check Macroeconomic News Hazards
    news_hazards = macro_agent.check_news_hazards()
    if news_hazards:
        for hazard in news_hazards:
            state.log(
                f"⚠️ [MacroAgent] Active High-Impact Event: '{hazard['event']}' "
                f"in {hazard['minutes_remaining']}m. Blocking trading setups."
            )
        return

    # 3. Calculate Portfolio Allocation
    allocation = portfolio_agent.calculate_allocation(state.metrics["total_balance"], [symbol])
    alloc_info = allocation["allocations"].get(symbol, {})
    state.log(
        f"[PortfolioAgent] Calculated capital for {symbol}: "
        f"${alloc_info.get('allocated_capital', 0.0):,.2f} "
        f"(Max risk: ${alloc_info.get('max_risk_amount', 0.0):,.2f})"
    )

    # 4. Perform Technical Analysis Breakout Scan
    signal = ta_agent.scan_breakout(symbol, current_price)
    
    # 5. Evaluate Sentiment Analysis
    sentiment = sentiment_agent.analyze_sentiment(symbol)
    state.log(f"[SentimentAgent] Current news sentiment: {sentiment}")

    if signal:
        state.log(f"🔥 [TA_Agent] Signal found: {signal} breakout on {symbol}")
        
        # We check if sentiment aligns (e.g. BUY breakout needs POSITIVE/NEUTRAL, SELL needs NEGATIVE/NEUTRAL)
        sentiment_aligned = (
            (signal == "BUY" and sentiment in ["POSITIVE", "NEUTRAL"]) or
            (signal == "SELL" and sentiment in ["NEGATIVE", "NEUTRAL"])
        )
        
        if not sentiment_aligned:
            state.log(f"❌ [Orchestrator] Trade blocked: Sentiment ({sentiment}) conflicts with signal ({signal})")
            return
            
        # 6. Validate with Risk Management
        # Drawdown simulation
        simulated_drawdown = max(0.0, (10000.0 - state.metrics["total_balance"]) / 100.0)
        risk_passed, risk_reason = risk_agent.validate_trade(symbol, lot_size, simulated_drawdown, drawdown_limit)
        
        if not risk_passed:
            state.log(f"❌ [RiskAgent] Trade blocked: {risk_reason}")
            return
            
        state.log(f"✔️ [RiskAgent] Risk checks passed. Forwarding to Order Execution...")
        
        # 7. Execute Order
        execution = exec_agent.execute_order(symbol, signal, lot_size, current_price)
        
        if execution["status"] == "FILLED":
            state.log(
                f"💰 [ExecutionAgent] Trade Filled: {execution['direction']} {execution['volume']} lots "
                f"at {execution['executed_price']} | Ticket: {execution['ticket']} | "
                f"Slippage: {execution['slippage']} | Ping: {execution['execution_time_ms']}ms"
            )
            
            # Simulate a PnL outcome
            trade_pnl = random.uniform(-100.0, 180.0) if signal == "BUY" else random.uniform(-120.0, 150.0)
            
            # Update state metrics in thread-safe block
            with state.lock:
                state.metrics["total_balance"] += trade_pnl
                state.metrics["daily_pnl"] += trade_pnl
                
                # Dynamic win rate update
                wins = 1 if trade_pnl > 0 else 0
                state.metrics["win_rate"] = round((state.metrics["win_rate"] * 9 + wins * 100) / 10, 1)
                
                # Append to equity chart
                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                state.equity_history.append({
                    "time": now_str,
                    "equity": round(state.metrics["total_balance"], 2),
                    "is_trade": True,
                    "type": f"{signal}_FILL"
                })
                
                state.save_config()
                
            state.log(f"📈 Account Balance updated to: ${state.metrics['total_balance']:,.2f} (Daily PnL: ${state.metrics['daily_pnl']:+,.2f})")
    else:
        # Occasionally simulate small equity moves to make the chart look active even when no major trades are filled
        if random.random() < 0.2:
            micro_change = random.uniform(-5.0, 5.0)
            with state.lock:
                state.metrics["total_balance"] += micro_change
                state.metrics["daily_pnl"] += micro_change
                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                state.equity_history.append({
                    "time": now_str,
                    "equity": round(state.metrics["total_balance"], 2),
                    "is_trade": False,
                    "type": ""
                })
                # keep history size clean
                if len(state.equity_history) > 100:
                    state.equity_history.pop(0)
                state.save_config()
