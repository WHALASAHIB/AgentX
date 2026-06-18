# Multi-Pair Backtest Summary

Generated: 2026-06-18 10:36:31
Period: 2026-03-18 to 2026-06-18 | Timeframe: 1h | Capital: 0,000 | FTMO Mode: On
Total: 45 | Errors: 0 | 8.0s

---

## 1. Strategy vs Pair Performance Matrix

Format: [return% | winrate% | profit_factor | maxdd% | score] verdict

| Strategy | XAUUSD | EURUSD | GBPUSD | USDJPY | USDCHF | USDCAD | AUDUSD | NZDUSD | BTCUSD |
|---|---|---|---|---|---|---|---|---||
| SMA Crossover (EMA 9/21) | -4.7%|30.3%|0.78|7.1%|5.0 CAUTIOUS | -0.5%|26.1%|0.52|0.6%|4.0 UNCERTAIN | -0.8%|23.2%|0.52|0.8%|4.5 UNCERTAIN | -24.8%|29.8%|0.81|48.1%|3 UNCERTAIN | -0.2%|35.6%|0.76|0.3%|4.5 UNCERTAIN | -0.0%|34.4%|0.98|0.3%|5.0 CAUTIOUS | -0.4%|25.4%|0.58|0.5%|4.5 UNCERTAIN | -0.2%|27.9%|0.76|0.2%|4.5 UNCERTAIN | 2.7%|39.1%|1.16|0.8%|8.0 STRONG |
| Bollinger Bands + RSI | -1.3%|1.6%|0.03|2.0%|4.5 UNCERTAIN | -0.4%|42.4%|0.42|0.5%|5.0 CAUTIOUS | -0.3%|50.0%|0.64|0.5%|5.0 CAUTIOUS | -100.0%|20.0%|0.02|100.0%|0 NO | 0.1%|59.4%|1.11|0.2%|6.0 CAUTIOUS | -0.4%|35.0%|0.43|0.6%|4.0 UNCERTAIN | -0.5%|48.5%|0.42|0.6%|5.0 CAUTIOUS | -0.1%|52.9%|0.84|0.2%|5.0 CAUTIOUS | -2.4%|3.3%|0.06|2.4%|4.5 UNCERTAIN |
| MACD Crossover | 1.4%|55.6%|2.25|2.3%|11.0 STRONG | 1.0%|50.5%|2.15|0.2%|11.0 STRONG | 1.3%|44.4%|2.28|0.2%|11.0 STRONG | 94.4%|40.7%|1.78|21.9%|10.0 STRONG | 0.8%|51.9%|2.13|0.2%|11.0 STRONG | 0.4%|49.5%|1.55|0.2%|11.0 STRONG | 0.9%|55.8%|2.25|0.1%|11.0 STRONG | 0.8%|50.0%|2.18|0.3%|11.0 STRONG | 2.7%|63.0%|3.05|0.2%|11.0 STRONG |
| EMA+RSI Momentum | -4.6%|29.9%|0.77|6.6%|4.5 UNCERTAIN | -0.4%|26.7%|0.57|0.5%|4.5 UNCERTAIN | -0.6%|26.6%|0.60|0.7%|4.5 UNCERTAIN | -22.4%|34.7%|0.81|47.3%|3.5 UNCERTAIN | -0.2%|35.9%|0.68|0.3%|4.5 UNCERTAIN | 0.0%|34.9%|1.00|0.3%|5.0 CAUTIOUS | -0.2%|27.4%|0.78|0.3%|4.5 UNCERTAIN | -0.2%|28.1%|0.74|0.3%|4.5 UNCERTAIN | 2.3%|38.7%|1.14|0.8%|6.0 CAUTIOUS |
| Gold Phoenix FTMO | 1.1%|70.4%|4.28|1.4%|11.0 STRONG | 0.4%|52.0%|2.66|0.2%|11.0 STRONG | 0.7%|47.8%|3.35|0.3%|11.0 STRONG | -44.8%|33.3%|0.42|58.4%|2.5 NO | -0.0%|48.0%|0.92|0.4%|5.0 CAUTIOUS | 0.5%|57.9%|2.48|0.2%|9.0 STRONG | -0.1%|37.0%|0.86|0.4%|4.5 UNCERTAIN | -0.2%|43.5%|0.65|0.3%|5.0 CAUTIOUS | 1.7%|73.7%|5.05|0.1%|11.0 STRONG |

---

## 2. Best Strategy Per Pair

Ranked by deploy_score then total_return_pct:

### XAUUSD

- **#1** MACD Crossover - Score: 11, Return: 1.4%, WR: 55.6%, PF: 2.25, DD: 2.3%, Trades: 117, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#2** Gold Phoenix FTMO - Score: 11, Return: 1.1%, WR: 70.4%, PF: 4.28, DD: 1.4%, Trades: 54, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#3** SMA Crossover (EMA 9/21) - Score: 5, Return: -4.7%, WR: 30.3%, PF: 0.78, DD: 7.1%, Trades: 1437, FTMO: False, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**
- **#4** Bollinger Bands + RSI - Score: 4, Return: -1.3%, WR: 1.6%, PF: 0.03, DD: 2.0%, Trades: 62, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**
- **#5** EMA+RSI Momentum - Score: 4, Return: -4.6%, WR: 29.9%, PF: 0.77, DD: 6.6%, Trades: 1337, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**

### EURUSD

- **#1** MACD Crossover - Score: 11, Return: 1.0%, WR: 50.5%, PF: 2.15, DD: 0.2%, Trades: 103, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#2** Gold Phoenix FTMO - Score: 11, Return: 0.4%, WR: 52.0%, PF: 2.66, DD: 0.2%, Trades: 25, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#3** Bollinger Bands + RSI - Score: 5, Return: -0.4%, WR: 42.4%, PF: 0.42, DD: 0.5%, Trades: 33, FTMO: False, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**
- **#4** EMA+RSI Momentum - Score: 4, Return: -0.4%, WR: 26.7%, PF: 0.57, DD: 0.5%, Trades: 60, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**
- **#5** SMA Crossover (EMA 9/21) - Score: 4, Return: -0.5%, WR: 26.1%, PF: 0.52, DD: 0.6%, Trades: 69, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**

### GBPUSD

- **#1** MACD Crossover - Score: 11, Return: 1.3%, WR: 44.4%, PF: 2.28, DD: 0.2%, Trades: 99, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#2** Gold Phoenix FTMO - Score: 11, Return: 0.7%, WR: 47.8%, PF: 3.35, DD: 0.3%, Trades: 23, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#3** Bollinger Bands + RSI - Score: 5, Return: -0.3%, WR: 50.0%, PF: 0.64, DD: 0.5%, Trades: 28, FTMO: False, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**
- **#4** EMA+RSI Momentum - Score: 4, Return: -0.6%, WR: 26.6%, PF: 0.60, DD: 0.7%, Trades: 64, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**
- **#5** SMA Crossover (EMA 9/21) - Score: 4, Return: -0.8%, WR: 23.2%, PF: 0.52, DD: 0.8%, Trades: 69, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**

### USDJPY

- **#1** MACD Crossover - Score: 10, Return: 94.4%, WR: 40.7%, PF: 1.78, DD: 21.9%, Trades: 118, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#2** EMA+RSI Momentum - Score: 4, Return: -22.4%, WR: 34.7%, PF: 0.81, DD: 47.3%, Trades: 49, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**
- **#3** SMA Crossover (EMA 9/21) - Score: 3, Return: -24.8%, WR: 29.8%, PF: 0.81, DD: 48.1%, Trades: 57, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**
- **#4** Gold Phoenix FTMO - Score: 2, Return: -44.8%, WR: 33.3%, PF: 0.42, DD: 58.4%, Trades: 21, FTMO: False, Verdict: **NO — Do not deploy, revisit strategy logic**
- **#5** Bollinger Bands + RSI - Score: 0, Return: -100.0%, WR: 20.0%, PF: 0.02, DD: 100.0%, Trades: 15, FTMO: False, Verdict: **NO — Do not deploy, revisit strategy logic**

### USDCHF

- **#1** MACD Crossover - Score: 11, Return: 0.8%, WR: 51.9%, PF: 2.13, DD: 0.2%, Trades: 104, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#2** Bollinger Bands + RSI - Score: 6, Return: 0.1%, WR: 59.4%, PF: 1.11, DD: 0.2%, Trades: 32, FTMO: False, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**
- **#3** Gold Phoenix FTMO - Score: 5, Return: -0.0%, WR: 48.0%, PF: 0.92, DD: 0.4%, Trades: 25, FTMO: False, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**
- **#4** SMA Crossover (EMA 9/21) - Score: 4, Return: -0.2%, WR: 35.6%, PF: 0.76, DD: 0.3%, Trades: 59, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**
- **#5** EMA+RSI Momentum - Score: 4, Return: -0.2%, WR: 35.9%, PF: 0.68, DD: 0.3%, Trades: 53, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**

### USDCAD

- **#1** MACD Crossover - Score: 11, Return: 0.4%, WR: 49.5%, PF: 1.55, DD: 0.2%, Trades: 95, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#2** Gold Phoenix FTMO - Score: 9, Return: 0.5%, WR: 57.9%, PF: 2.48, DD: 0.2%, Trades: 19, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#3** EMA+RSI Momentum - Score: 5, Return: 0.0%, WR: 34.9%, PF: 1.00, DD: 0.3%, Trades: 63, FTMO: False, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**
- **#4** SMA Crossover (EMA 9/21) - Score: 5, Return: -0.0%, WR: 34.4%, PF: 0.98, DD: 0.3%, Trades: 64, FTMO: False, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**
- **#5** Bollinger Bands + RSI - Score: 4, Return: -0.4%, WR: 35.0%, PF: 0.43, DD: 0.6%, Trades: 20, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**

### AUDUSD

- **#1** MACD Crossover - Score: 11, Return: 0.9%, WR: 55.8%, PF: 2.25, DD: 0.1%, Trades: 95, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#2** Bollinger Bands + RSI - Score: 5, Return: -0.5%, WR: 48.5%, PF: 0.42, DD: 0.6%, Trades: 33, FTMO: False, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**
- **#3** Gold Phoenix FTMO - Score: 4, Return: -0.1%, WR: 37.0%, PF: 0.86, DD: 0.4%, Trades: 27, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**
- **#4** EMA+RSI Momentum - Score: 4, Return: -0.2%, WR: 27.4%, PF: 0.78, DD: 0.3%, Trades: 62, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**
- **#5** SMA Crossover (EMA 9/21) - Score: 4, Return: -0.4%, WR: 25.4%, PF: 0.58, DD: 0.5%, Trades: 71, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**

### NZDUSD

- **#1** MACD Crossover - Score: 11, Return: 0.8%, WR: 50.0%, PF: 2.18, DD: 0.3%, Trades: 94, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#2** Bollinger Bands + RSI - Score: 5, Return: -0.1%, WR: 52.9%, PF: 0.84, DD: 0.2%, Trades: 34, FTMO: False, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**
- **#3** Gold Phoenix FTMO - Score: 5, Return: -0.2%, WR: 43.5%, PF: 0.65, DD: 0.3%, Trades: 23, FTMO: False, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**
- **#4** SMA Crossover (EMA 9/21) - Score: 4, Return: -0.2%, WR: 27.9%, PF: 0.76, DD: 0.2%, Trades: 61, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**
- **#5** EMA+RSI Momentum - Score: 4, Return: -0.2%, WR: 28.1%, PF: 0.74, DD: 0.3%, Trades: 57, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**

### BTCUSD

- **#1** MACD Crossover - Score: 11, Return: 2.7%, WR: 63.0%, PF: 3.05, DD: 0.2%, Trades: 165, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#2** Gold Phoenix FTMO - Score: 11, Return: 1.7%, WR: 73.7%, PF: 5.05, DD: 0.1%, Trades: 76, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#3** SMA Crossover (EMA 9/21) - Score: 8, Return: 2.7%, WR: 39.1%, PF: 1.16, DD: 0.8%, Trades: 1338, FTMO: False, Verdict: **STRONG YES — Deploy to live**
- **#4** EMA+RSI Momentum - Score: 6, Return: 2.3%, WR: 38.7%, PF: 1.14, DD: 0.8%, Trades: 1299, FTMO: False, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**
- **#5** Bollinger Bands + RSI - Score: 4, Return: -2.4%, WR: 3.3%, PF: 0.06, DD: 2.4%, Trades: 121, FTMO: False, Verdict: **UNCERTAIN — Optimise further or use as filter only**

---

## 3. Overall Strategy Ranking

### SMA Crossover (EMA 9/21)
- Average Deploy Score: **4.8**
- Average Return: **-3.21%**
- STRONG YES on **1** pairs, CAUTIOUS on **2** pairs
- Best pair: **BTCUSD** (Score: 8, Return: 2.7%)

### Bollinger Bands + RSI
- Average Deploy Score: **4.3**
- Average Return: **-11.71%**
- STRONG YES on **0** pairs, CAUTIOUS on **5** pairs
- Best pair: **USDCHF** (Score: 6, Return: 0.1%)

### MACD Crossover
- Average Deploy Score: **10.9**
- Average Return: **11.51%**
- STRONG YES on **9** pairs, CAUTIOUS on **0** pairs
- Best pair: **BTCUSD** (Score: 11, Return: 2.7%)

### EMA+RSI Momentum
- Average Deploy Score: **4.6**
- Average Return: **-2.92%**
- STRONG YES on **0** pairs, CAUTIOUS on **2** pairs
- Best pair: **BTCUSD** (Score: 6, Return: 2.3%)

### Gold Phoenix FTMO
- Average Deploy Score: **7.8**
- Average Return: **-4.51%**
- STRONG YES on **5** pairs, CAUTIOUS on **2** pairs
- Best pair: **BTCUSD** (Score: 11, Return: 1.7%)

### Overall Ranking Table

| Rank | Strategy | Avg Score | Avg Return | STRONG YES | CAUTIOUS | Best Pair |
|---|---------|----------|-----------|------------|---------|----------|
| 1 | MACD Crossover | 10.9 | 11.51% | 9/9 | 0/9 | BTCUSD |
| 2 | Gold Phoenix FTMO | 7.8 | -4.51% | 5/9 | 2/9 | BTCUSD |
| 3 | SMA Crossover (EMA 9/21) | 4.8 | -3.21% | 1/9 | 2/9 | BTCUSD |
| 4 | EMA+RSI Momentum | 4.6 | -2.92% | 0/9 | 2/9 | BTCUSD |
| 5 | Bollinger Bands + RSI | 4.3 | -11.71% | 0/9 | 5/9 | USDCHF |

---

## 4. Recommended Strategy Assignments

Top 1-3 strategies per pair (prioritizing STRONG YES deploy verdicts):

### XAUUSD

- **MACD Crossover** - Score: 11, Return: 1.4%, WR: 55.6%, PF: 2.25, DD: 2.3%, Verdict: **STRONG YES — Deploy to live**
- **Gold Phoenix FTMO** - Score: 11, Return: 1.1%, WR: 70.4%, PF: 4.28, DD: 1.4%, Verdict: **STRONG YES — Deploy to live**
- **SMA Crossover (EMA 9/21)** - Score: 5, Return: -4.7%, WR: 30.3%, PF: 0.78, DD: 7.1%, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**

### EURUSD

- **MACD Crossover** - Score: 11, Return: 1.0%, WR: 50.5%, PF: 2.15, DD: 0.2%, Verdict: **STRONG YES — Deploy to live**
- **Gold Phoenix FTMO** - Score: 11, Return: 0.4%, WR: 52.0%, PF: 2.66, DD: 0.2%, Verdict: **STRONG YES — Deploy to live**
- **Bollinger Bands + RSI** - Score: 5, Return: -0.4%, WR: 42.4%, PF: 0.42, DD: 0.5%, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**

### GBPUSD

- **MACD Crossover** - Score: 11, Return: 1.3%, WR: 44.4%, PF: 2.28, DD: 0.2%, Verdict: **STRONG YES — Deploy to live**
- **Gold Phoenix FTMO** - Score: 11, Return: 0.7%, WR: 47.8%, PF: 3.35, DD: 0.3%, Verdict: **STRONG YES — Deploy to live**
- **Bollinger Bands + RSI** - Score: 5, Return: -0.3%, WR: 50.0%, PF: 0.64, DD: 0.5%, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**

### USDJPY

- **MACD Crossover** - Score: 10, Return: 94.4%, WR: 40.7%, PF: 1.78, DD: 21.9%, Verdict: **STRONG YES — Deploy to live**
- **EMA+RSI Momentum** - Score: 4, Return: -22.4%, WR: 34.7%, PF: 0.81, DD: 47.3%, Verdict: **UNCERTAIN — Optimise further or use as filter only**
- **SMA Crossover (EMA 9/21)** - Score: 3, Return: -24.8%, WR: 29.8%, PF: 0.81, DD: 48.1%, Verdict: **UNCERTAIN — Optimise further or use as filter only**

### USDCHF

- **MACD Crossover** - Score: 11, Return: 0.8%, WR: 51.9%, PF: 2.13, DD: 0.2%, Verdict: **STRONG YES — Deploy to live**
- **Bollinger Bands + RSI** - Score: 6, Return: 0.1%, WR: 59.4%, PF: 1.11, DD: 0.2%, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**
- **Gold Phoenix FTMO** - Score: 5, Return: -0.0%, WR: 48.0%, PF: 0.92, DD: 0.4%, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**

### USDCAD

- **MACD Crossover** - Score: 11, Return: 0.4%, WR: 49.5%, PF: 1.55, DD: 0.2%, Verdict: **STRONG YES — Deploy to live**
- **Gold Phoenix FTMO** - Score: 9, Return: 0.5%, WR: 57.9%, PF: 2.48, DD: 0.2%, Verdict: **STRONG YES — Deploy to live**
- **EMA+RSI Momentum** - Score: 5, Return: 0.0%, WR: 34.9%, PF: 1.00, DD: 0.3%, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**

### AUDUSD

- **MACD Crossover** - Score: 11, Return: 0.9%, WR: 55.8%, PF: 2.25, DD: 0.1%, Verdict: **STRONG YES — Deploy to live**
- **Bollinger Bands + RSI** - Score: 5, Return: -0.5%, WR: 48.5%, PF: 0.42, DD: 0.6%, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**
- **Gold Phoenix FTMO** - Score: 4, Return: -0.1%, WR: 37.0%, PF: 0.86, DD: 0.4%, Verdict: **UNCERTAIN — Optimise further or use as filter only**

### NZDUSD

- **MACD Crossover** - Score: 11, Return: 0.8%, WR: 50.0%, PF: 2.18, DD: 0.3%, Verdict: **STRONG YES — Deploy to live**
- **Bollinger Bands + RSI** - Score: 5, Return: -0.1%, WR: 52.9%, PF: 0.84, DD: 0.2%, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**
- **Gold Phoenix FTMO** - Score: 5, Return: -0.2%, WR: 43.5%, PF: 0.65, DD: 0.3%, Verdict: **CAUTIOUS YES — Paper trade first, monitor closely**

### BTCUSD

- **MACD Crossover** - Score: 11, Return: 2.7%, WR: 63.0%, PF: 3.05, DD: 0.2%, Verdict: **STRONG YES — Deploy to live**
- **Gold Phoenix FTMO** - Score: 11, Return: 1.7%, WR: 73.7%, PF: 5.05, DD: 0.1%, Verdict: **STRONG YES — Deploy to live**
- **SMA Crossover (EMA 9/21)** - Score: 8, Return: 2.7%, WR: 39.1%, PF: 1.16, DD: 0.8%, Verdict: **STRONG YES — Deploy to live**
