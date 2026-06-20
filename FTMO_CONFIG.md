# AGENTX — FTMO Challenge Configuration
# =======================================
# When starting a FTMO challenge, apply these settings.

## Account Size: $10,000 (Standard Challenge)
## Profit Target: $1,000 (10%)
## Max Daily Loss: $500 (5%)
## Max Drawdown: $1,000 (10%)
## Min Trading Days: 10

## Active Bots for FTMO Challenge
## (Disabled bots not listed)

| Bot                | Pairs        | Risk/Trade | Max/Day | Notes |
|--------------------|-------------|:---------:|:-------:|-------|
| MACD GBPUSD        | GBPUSD      | 0.15%     | 2       | ✅ PF 2.37 |
| MACD AUDUSD        | AUDUSD      | 0.15%     | 2       | ✅ PF 2.43 |
| MACD NZDUSD        | NZDUSD      | 0.15%     | 2       | ✅ PF 3.60 ⭐ |
| MACD USDCHF        | USDCHF      | 0.15%     | 2       | ✅ PF 2.93 |
| MACD USDCAD        | USDCAD      | 0.15%     | 2       | ✅ PF 2.02 |
| MACD USDJPY        | USDJPY      | 0.15%     | 2       | 😐 Breakeven |
| GoldPhoenix MP     | XAUUSD,BTCUSD,EURUSD,GBPUSD,USDCAD | 0.15% | 2 | 🛠️ Tuned |
| Bollinger          | AUDUSD,NZDUSD,USDCHF | 0.15%     | 2       | New |
| SMA                | BTCUSD,USDJPY | 0.15%     | 1       | New |

## Disabled Bots (Council Decision)
- ❌ Streaming Bot — Martingale pattern, -$8k drawdown risk
- ❌ MACD EURUSD — PF 0.04, 14.3% win rate
- ❌ MACD XAUUSD — ATR sizing broken on Gold, -$2.2k drawdown
- ❌ GoldBot — Catastrophic loss risk (83% WR but PF 0.34)
- ❌ Gold Phoenix Legacy — Replaced by GoldPhoenix MP
- ❌ Scalping Bot — Insufficient data, high variance

## To Start FTMO Challenge:
# 1. Set FTMO_MODE = True in multi_symbol_bot.py
# 2. Set FTMO_ACCOUNT_SIZE to challenge account size
# 3. Fund the challenge account
# 4. Update mt5_config.json with new account credentials
# 5. Restart bridge + backend
# 6. Monitor daily: daily P&L, total drawdown

## Risk per Trade Calculation (0.15%):
# $10K challenge: $15.00 max loss per trade
# $25K challenge: $37.50 max loss per trade
# $50K challenge: $75.00 max loss per trade
# $100K challenge: $150.00 max loss per trade
