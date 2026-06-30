"""
Post-Trade Critic — Last 2 Hours
Magic: 780012, Symbol: EURUSD
Run: cron job, 2026-06-30 ~09:26 UTC
"""
import MetaTrader5 as mt5
import json
from datetime import datetime, timedelta
import sys
import os

# --- Config ---
MAGIC = 780012
SYMBOL = "EURUSD"
LOOKBACK_HOURS = 2
CONFIG_PATH = "C:\\Trading\\mt5_config.json"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def main():
    config = load_config()
    login = config["login"]
    password = config["password"]
    server = config["server"]

    print(f"[CRITIC] Time (local): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[CRITIC] UTC time:    {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[CRITIC] Target: magic={MAGIC}, symbol={SYMBOL}, lookback={LOOKBACK_HOURS}h")

    # Step 1: Try bare initialize first
    print(f"[CRITIC] Attempting mt5.initialize()...")
    init_ok = mt5.initialize()
    if not init_ok:
        err = mt5.last_error()
        print(f"[CRITIC] Bare initialize failed: {err}")
        # Step 2: Try with path
        term_path = config.get("terminal_path", r"C:\Program Files\MetaTrader 5\terminal64.exe")
        print(f"[CRITIC] Trying with path: {term_path}")
        init_ok = mt5.initialize(path=term_path)
        if not init_ok:
            err = mt5.last_error()
            print(f"[CRITIC] Path-based initialize also failed: {err}")
            return False

    print(f"[CRITIC] MT5 initialized: {init_ok}")

    # Check account info
    acc = mt5.account_info()
    if acc is None:
        print(f"[CRITIC] account_info() returned None — no terminal connection?")
        mt5.shutdown()
        return False
    
    acc_dict = acc._asdict()
    print(f"[CRITIC] Active account: login={acc_dict.get('login')}, server={acc_dict.get('server')}")
    print(f"[CRITIC] Balance: {acc_dict.get('balance')}, Equity: {acc_dict.get('equity')}")

    expected_login = login
    actual_login = acc_dict.get('login')
    if actual_login != expected_login:
        print(f"[CRITIC] WARNING: Active account login {actual_login} != expected {expected_login}")
        print(f"[CRITIC] Trying to login to correct account...")
        login_ok = mt5.login(login=login, password=password, server=server)
        if not login_ok:
            err = mt5.last_error()
            print(f"[CRITIC] mt5.login() failed: {err}")
            # Check what account IS active
            acc2 = mt5.account_info()
            if acc2:
                print(f"[CRITIC] Active account after failed login: login={acc2.login}, server={acc2.server}")
            mt5.shutdown()
            return False
        print(f"[CRITIC] Login successful")
        acc = mt5.account_info()
        if acc:
            print(f"[CRITIC] Now active: login={acc.login}, server={acc.server}, balance={acc.balance}")

    # Calculate time range
    now = datetime.now()  # timezone-naive, as MT5 expects
    from_time = now - timedelta(hours=LOOKBACK_HOURS)
    
    print(f"[CRITIC] Fetching history deals from {from_time} to {now}")
    
    # Get deals
    deals = mt5.history_deals_get(from_time, now)
    
    if deals is None:
        err = mt5.last_error()
        print(f"[CRITIC] history_deals_get returned None — last_error: {err}")
        if err and isinstance(err, tuple) and err[0] == 1 and err[1] == 'Success':
            print(f"[CRITIC] No deals found in the period (None with error=Success = empty)")
        mt5.shutdown()
        return True  # Not an error, just no trades
    
    if len(deals) == 0:
        print(f"[CRITIC] No deals found in period (empty list)")
        mt5.shutdown()
        return True

    print(f"[CRITIC] Found {len(deals)} raw deals")

    # Filter by magic and symbol
    filtered = [d._asdict() for d in deals 
                if d.magic == MAGIC and d.symbol == SYMBOL]
    
    print(f"[CRITIC] Deals matching magic={MAGIC}, symbol={SYMBOL}: {len(filtered)}")

    if not filtered:
        print(f"[CRITIC] No matching trades for M{SYMBOL}/{MAGIC}")
        # Show what magics/symbols ARE present
        magics = set(d.magic for d in deals)
        symbols = set(d.symbol for d in deals)
        print(f"[CRITIC] Magics found in period: {magics}")
        print(f"[CRITIC] Symbols found in period: {symbols}")
        mt5.shutdown()
        return True

    # Group deals by position ID to pair entry/exit
    from collections import defaultdict
    by_position = defaultdict(list)
    for d in filtered:
        by_position[d['position_id']].append(d)

    trade_critiques = []
    total_pnl = 0.0
    wins = 0
    losses = 0

    print(f"\n[CRITIC] === Trade Analysis ===\n")

    for pos_id, deals_list in by_position.items():
        deals_list.sort(key=lambda x: x['time'])
        
        exit_deals = [d for d in deals_list if abs(d.get('profit', 0)) > 0.001]
        entry_deals = [d for d in deals_list if abs(d.get('profit', 0)) < 0.001 and d['deal_type'] in (0, 1)]
        
        print(f"  Position #{pos_id}:")
        for d in deals_list:
            dt = datetime.fromtimestamp(d['time']).strftime('%Y-%m-%d %H:%M:%S')
            profit_str = f"${d['profit']:.2f}" if abs(d.get('profit',0)) > 0.001 else "-"
            print(f"    [{dt}] type={d['deal_type']} entry={d['entry']} vol={d['volume']} price={d['price']} profit={profit_str}")
        
        if exit_deals:
            total_profit = sum(d['profit'] for d in exit_deals)
            entry_price = entry_deals[0]['price'] if entry_deals else 0
            exit_price = exit_deals[0]['price'] if exit_deals else 0
            volume = entry_deals[0]['volume'] if entry_deals else 0
            direction = "BUY" if (entry_deals and entry_deals[0]['deal_type'] == 0) else "SELL" if (entry_deals and entry_deals[0]['deal_type'] == 1) else "N/A"
            
            total_pnl += total_profit
            if total_profit > 0:
                wins += 1
                outcome = "win"
            else:
                losses += 1
                outcome = "loss"
            
            score = 5
            positives = []
            negatives = []
            root_cause = "N/A (winning trade)" if outcome == "win" else "N/A"
            fix = "N/A" if outcome == "win" else "N/A"
            prevention_rule = "N/A" if outcome == "win" else "N/A"
            
            if outcome == "win":
                positives.append(f"Winning trade: +${total_profit:.2f}")
                if len(deals_list) >= 2:
                    time_diff = deals_list[-1]['time'] - deals_list[0]['time']
                    if time_diff < 3600:
                        positives.append("Quick execution (< 1h hold)")
                    else:
                        positives.append(f"Held for {time_diff//60:.0f}m")
                if total_profit / (volume * 100000) > 0.001:
                    score = 8
                    positives.append("Good pip capture")
                else:
                    score = 6
            else:
                negatives.append(f"Losing trade: -${abs(total_profit):.2f}")
                if len(deals_list) >= 2:
                    time_diff = deals_list[-1]['time'] - deals_list[0]['time']
                    if time_diff > 3600:
                        negatives.append(f"Held too long ({time_diff//60:.0f}m)")
                        score = 3
                    else:
                        score = 4
                        negatives.append(f"Quick stop-out ({time_diff//60:.0f}m)")
                else:
                    score = 2
                    negatives.append("Incomplete trade data")
                
                root_cause = f"Direction: {direction}. Entry: {entry_price}, Exit: {exit_price}. PnL: ${total_profit:.2f}"
                fix = "Review entry timing and SL placement"
                prevention_rule = "Check VWAP deviation >= 10 pips + rejection candle before entry"
            
            quality = "good" if score >= 8 else "acceptable" if score >= 5 else "poor" if score >= 3 else "error"
            
            critique = {
                "ticket": pos_id,
                "symbol": SYMBOL,
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "volume": volume,
                "pnl": round(total_profit, 2),
                "score": score,
                "quality": quality,
                "outcome": outcome,
                "positives": positives,
                "negatives": negatives,
                "root_cause": root_cause,
                "fix": fix,
                "prevention_rule": prevention_rule
            }
            trade_critiques.append(critique)
            
            print(f"  => Outcome: {outcome.upper()}, PnL: ${total_profit:.2f}, Score: {score}/10 ({quality})")
            if positives:
                for p in positives:
                    print(f"     + {p}")
            if negatives:
                for n in negatives:
                    print(f"     - {n}")
            print()

    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    
    print(f"\n[CRITIC] === Summary ===")
    print(f"  Total trades: {wins + losses}")
    print(f"  Wins: {wins}, Losses: {losses}")
    print(f"  Win rate: {win_rate:.1f}%")
    print(f"  Total PnL: ${total_pnl:.2f}")

    patterns = []
    if win_rate < 40 and (wins + losses) >= 3:
        patterns.append({"pattern": "Low win rate", "severity": "CRITICAL", "detail": f"{win_rate:.1f}% across {wins+losses} trades"})
    elif win_rate < 50 and (wins + losses) >= 3:
        patterns.append({"pattern": "Below average WR", "severity": "WARNING", "detail": f"{win_rate:.1f}% across {wins+losses} trades"})
    if losses >= 3 and wins == 0:
        patterns.append({"pattern": "Consecutive losses", "severity": "CRITICAL", "detail": f"{losses} losses in a row"})
    
    if patterns:
        print(f"\n[CRITIC] === Patterns Detected ===")
        for p in patterns:
            print(f"  [{p['severity']}] {p['pattern']}: {p['detail']}")

    results = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "run_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "total_trades": wins + losses,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "per_symbol": {SYMBOL: {"wins": wins, "losses": losses, "total_pnl": round(total_pnl, 2)}},
        "patterns": patterns,
        "trade_critiques": trade_critiques
    }
    
    report_path = f"C:\\Trading\\bots\\analytics\\daily_critique_{datetime.now().strftime('%Y-%m-%d')}.json"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n[CRITIC] Report saved to {report_path}")

    mt5.shutdown()
    return True

if __name__ == "__main__":
    success = main()
    if success:
        print(f"\n[CRITIC] Done.")
    else:
        print(f"\n[CRITIC] FAILED — MT5 connection issue.")
        sys.exit(1)
