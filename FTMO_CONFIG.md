# AGENTX — FTMO Challenge Configuration
# =======================================

## 🔄 Dynamic Percentage-Based Sizing (ALL BOTS)
**Every bot now uses percentage-based position sizing.** No fixed lot sizes anywhere.

### How It Works
```
risk_amount = current_account_balance × (RISK_PERCENT / 100)
volume = risk_amount / (SL_distance_in_points × contract_value_per_point)
```

### Balance Examples (RISK_PERCENT = 0.15%)

| Account Balance | Risk Per Trade | Account Size | Example |
|:--------------:|:--------------:|:------------:|---------|
| $10,000        | **$15.00**     | Standard     | ~0.03 lots XAUUSD |
| $25,000        | **$37.50**     | Challenger   | ~0.08 lots XAUUSD |
| $50,000        | **$75.00**     | Pro          | ~0.15 lots XAUUSD |
| $100,000       | **$150.00**    | Funded       | ~0.30 lots XAUUSD |

### Dynamic Adjustments
- **Balance drops to $9,000** → risk = $13.50 → smaller lot size automatically
- **Balance grows to $12,000** → risk = $18.00 → larger lot size automatically
- **Never trails up or down from a starting value** — every trade reads real-time balance
- You do NOT need to change any code if account size changes

---

## Active Bots for FTMO Challenge

| Bot | Pairs | Risk/Trade | Max/Day | Notes |
|-----|-------|:---------:|:-------:|-------|
| MACD GBPUSD | GBPUSD | 0.15% | 2 | ✅ PF 2.37 |
| MACD AUDUSD | AUDUSD | 0.15% | 2 | ✅ PF 2.43 |
| MACD NZDUSD | NZDUSD | 0.15% | 2 | ✅ PF 3.60 ⭐ |
| MACD USDCHF | USDCHF | 0.15% | 2 | ✅ PF 2.93 |
| MACD USDCAD | USDCAD | 0.15% | 2 | ✅ PF 2.02 |
| MACD USDJPY | USDJPY | 0.15% | 2 | 😐 Breakeven |
| GoldPhoenix MP 🔧 | XAUUSD,BTCUSD,EURUSD,GBPUSD,USDCAD | 0.15% | 2 | 🛠️ Now dynamic! Was fixed 0.10 lots |
| Bollinger | AUDUSD,NZDUSD,USDCHF | 0.15% | 2 | New |
| SMA | BTCUSD,USDJPY | 0.15% | 1 | New |

## Disabled Bots (Council Decision)
- ❌ Streaming Bot — Martingale pattern, -$8k drawdown risk
- ❌ MACD EURUSD — PF 0.04, 14.3% win rate
- ❌ MACD XAUUSD — ATR sizing broken on Gold, -$2.2k drawdown
- ❌ GoldBot — Catastrophic loss risk (83% WR but PF 0.34)
- ❌ Gold Phoenix Legacy — Replaced by GoldPhoenix MP
- ❌ Scalping Bot — Insufficient data, high variance

## 💡 Why Percentage Beats Fixed Lots

| Scenario | Fixed 0.10 lots | 0.15% Dynamic | Winner |
|----------|:--------------:|:--------------:|:------:|
| $10K account, normal trade | 0.10 lots | 0.03 lots | ✅ Dynamic (less risk) |
| $10K account, after $1K loss | 0.10 lots (same!) | 0.027 lots (less!) | ✅ Dynamic |
| $10K account, after $1K gain | 0.10 lots (same!) | 0.033 lots (more!) | ✅ Dynamic |
| $100K funded account | 0.10 lots (way too small) | 0.30 lots (correct scale) | ✅ Dynamic |

---

## To Start FTMO Challenge:
1. Set `FTMO_MODE = True` and `FTMO_ACCOUNT_SIZE = 10000` in `multi_symbol_bot.py`
2. Update credentials in `mt5_config.json` to FTMO demo account
3. Restart bridge + backend
4. Monitor daily: daily P&L, total drawdown
5. Profit target: 10% ($1,000 on $10K)
6. No position size changes needed — 0.15% works at ANY account size
