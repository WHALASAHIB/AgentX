# Hedge Fund Strategy Research — Multi-Strategy Trading System Reference

> Research compiled from publicly available sources: fund letters, academic papers, Investopedia, FT, Bloomberg, and industry analysis.
> Target: Actionable knowledge to design a multi-strategy algorithmic trading system on MetaTrader 5.

---

## Table of Contents

1. [Bridgewater Associates — All Weather / Risk Parity](#1-bridgewater-associates--all-weather--risk-parity)
2. [Renaissance Technologies — Medallion Fund](#2-renaissance-technologies--medallion-fund)
3. [Citadel — Multi-Strategy Model](#3-citadel--multi-strategy-model)
4. [AQR Capital Management — Style Premia](#4-aqr-capital-management--style-premia)
5. [Man Group / AHL — Systematic Trend Following](#5-man-group--ahl--systematic-trend-following)
6. [Two Sigma / DE Shaw — Data-Driven Quant](#6-two-sigma--de-shaw--data-driven-quant)
7. [Cross-Fund Synthesis: What's Replicable on MT5](#7-cross-fund-synthesis-replicable-for-a-small-quant-team-on-mt5)

---

## 1. Bridgewater Associates — All Weather / Risk Parity

**Founder:** Ray Dalio
**AUM (peak):** ~$160B
**Strategy Type:** Macro / Risk Parity / All-Weather Portfolio

### The Thesis

The core insight: **Asset allocation drives 90%+ of portfolio variance.** Bridgewater's thesis is that there are four macroeconomic "environments" defined by two binary axes:
- **Growth** (above/below expectations)
- **Inflation** (above/below expectations)

A portfolio should be equally weighted across the four quadrants, NOT across asset classes. Since different assets perform well in different quadrants:
- **Growth + Inflation = Bull** → Equities, commodities, gold, inflation-linked bonds
- **Growth + Deflation = Boom** → Equities, corporate bonds
- **Recession + Inflation = Stagflation** → Inflation-linked bonds, gold, commodities
- **Recession + Deflation = Bust** → Government bonds, treasuries

Instead of allocating 60% to equities and 40% to bonds (which puts 90% of risk in equities), Bridgewater **risk-parity-weights** so each quadrant contributes equal risk to the portfolio.

### Portfolio Construction

1. **Risk budgeting** — Each asset's contribution to total portfolio volatility is equalized
2. **Leverage is applied** to low-risk assets (bonds) to bring their risk contribution up to match equities
3. **Inflation-linked bonds and commodities** get meaningful allocations (not just stocks/bonds)

A simplified All Weather might look like:
- 30% US Equities (leveraged)
- 40% Long-term Treasuries (leveraged)
- 15% TIPS / Inflation-linked bonds
- 7.5% Gold
- 7.5% Commodities

Risk contribution is ~25% per quadrant, despite the capital allocation looking skewed.

### Instrument Focus
- Global macro: equities (index ETFs/futures), sovereign bonds (futures), inflation-linked bonds, commodities (futures), currencies, gold
- Predominantly liquid futures and ETFs — **very MT5-compatible**

### Risk Framework
- **Volatility targeting**: Positions sized so each sub-portfolio targets a specific volatility (e.g., 10%/yr)
- **Leverage scaling**: Dynamic leverage to maintain constant risk irrespective of market conditions
- **Drawdown management**: Not via stop-losses — via continuous rebalancing to risk targets; as volatility spikes, positions are automatically reduced
- **Diversification is the primary risk control**

### Alpha Source (The Edge)
- **Structural premium** from risk parity itself — not a timing edge, but a portfolio construction edge
- Dalio's "Holy Grail" — finding 10-15 uncorrelated return streams dramatically reduces portfolio risk without reducing expected return
- Over long periods, risk parity captures the equity risk premium + bond term premium + inflation risk premium simultaneously

### What's Replicable on MT5
- ✅ **Risk parity weighting** — Absolutely replicable. Use ATR-based position sizing to equalize risk contribution across assets
- ✅ **Multi-asset futures** — MT5 supports indices (US30, NAS100, SPX500), bonds (10YR T-Note), gold (XAUUSD), commodities (XTIUSD, XNGUSD), FX
- ✅ **Volatility targeting** — Size positions so each strategy has target daily VaR
- ✅ **Quarterly rebalancing** back to equal risk contributions
- ❌ **Institutional leverage** — Bridgewater uses 3-5x leverage on bonds; MT5 brokers cap leverage but you can underweight equities instead

---

## 2. Renaissance Technologies — Medallion Fund

**Founders:** Jim Simons, James Ax, Elwyn Berlekamp
**Track record:** 66% avg annual return (pre-fee) 1988-2018; 39% net to investors
**Capacity:** ~$10B (closed to external since 1993; now only employees)
**Strategy Type:** Statistical Arbitrage / Short-term Mean Reversion

### The Thesis

Renaissance (Medallion) is the most successful hedge fund in history. The core insight: **Financial markets exhibit subtle, short-lived statistical patterns that are not driven by fundamentals but by microstructure, order flow, and investor behavior.** These patterns are:
- **Weak** (tiny signals, often <0.01% per trade)
- **Short-lived** (seconds to days)
- **Numerous** (thousands of independent signals)
- **Decaying** (alphas degrade and must be constantly replaced)

### What's Known (Publicly)

Key publicly known facts about Medallion's approach:

1. **No fundamental analysis** — Simons famously said "we rely on no human judgment at all"
2. **Hidden Markov Models** — Berlekamp's contribution was applying HMMs to detect regime changes in market data
3. **Statistical arbitrage** — Pairs trading, basket trading, relative value trades
4. **Short-term mean reversion** — Over minutes to days, prices revert after order-flow imbalances
5. **Massive diversification** — Thousands of positions across global markets simultaneously
6. **Extreme data cleaning** — The "Berlekamp margin" — edge comes from cleaning data better than anyone else; they spent enormous effort removing bad ticks, stale quotes, corporate actions
7. **Transaction cost modeling** — They model market impact with extreme precision; many signals look profitable on paper but lose after costs — Renaissance excels at trading *through* costs
8. **Machine learning** — Early adopters of neural nets (1990s), random forests, gradient boosting
9. **Signal lifecycle** — Constant R&D pipeline; signals are discovered, backtested, deployed, monitored, retired

### Key Known Signals (from lawsuits, patent filings, and interviews)
- **Lagged serial correlation**: Short-term reversal (daily/weekly) in equities
- **Volume-based signals**: Abnormal volume predicts mean reversion
- **Cross-asset signals**: Lead-lag relationships between correlated assets
- **Option-implied vs realized**: Discrepancies between implied and realized volatility
- **Seasonal patterns**: Calendar effects, expiration effects
- **Market microstructure**: Bid-ask bounce, order flow imbalance

### Instrument Focus
- Global equities (primary), futures, options, FX, commodities
- **Any liquid instrument where statistical patterns exist**

### Risk Framework
- **Strict volatility target**: Medallion targets constant volatility (~20%/yr)
- **Leverage**: Uses significant leverage (reported 12.5x at times) because individual signals have tiny Sharpe but are uncorrelated
- **Position limits**: Max position size capped as % of daily volume to control market impact
- **Drawdown tolerance**: Medallion's maximum drawdown was ~20% (in 2008 financial crisis)
- **Stress testing**: Portfolios stress-tested against historical crises

### Alpha Source (The Edge)
- **Data edge**: Cleanest, most comprehensive tick data in the industry
- **Compute edge**: Among the largest private supercomputers in the world
- **Talent edge**: Hires only the brightest mathematicians, physicists, computer scientists (no finance backgrounds)
- **R&D process**: Systematic signal discovery pipeline — thousands of experiments run daily
- **Execution edge**: Advanced execution algorithms minimize slippage

### What's Replicable on MT5
- ✅ **Statistical arbitrage / pairs trading** — MT5 supports multiple symbols; cointegration-based pairs (e.g., EURGBP vs EURUSD cross-rates, correlated index futures)
- ✅ **Short-term mean reversion** — Bollinger Bands, RSI extremes, Z-score reversion (your existing VWAP bot is this!)
- ✅ **Volume divergence signals** — MT5 offers tick volume; divergences between price and volume can signal exhaustion
- ✅ **Cross-asset lead-lag** — e.g., Bund futures → US 10Y; Gold → XAUUSD; Oil → USD/CAD
- ✅ **Multiple small uncorrelated signals** — Aggregate 5-10 independent signals, each with tiny edge
- ❌ **HFT-level execution** — MT5 execution latency is 10-100ms; Medallion trades in microseconds
- ❌ **Data cleaning at scale** — You can't match their tick-data infrastructure, but you can avoid common pitfalls (bad broker ticks, spread manipulation)
- ✅ **Volatility-targeted position sizing** — Easy to implement on MT5

**Key replicable insight**: Combine 5-10 weak signals, each with Sharpe ~0.15-0.30, into one portfolio. If they're uncorrelated (r < 0.2), portfolio Sharpe can reach 0.8-1.2. This IS the Renaissance approach scaled down.

---

## 3. Citadel — Multi-Strategy Model

**Founder:** Ken Griffin
**AUM:** ~$60B+ (one of largest hedge funds globally)
**Strategy Type:** Multi-Strategy / Multi-Manager Platform

### The Thesis

Citadel is not a single strategy — it's a **platform that hosts multiple autonomous strategy pods** sharing capital, risk infrastructure, and execution. The thesis: **By hosting many uncorrelated strategies under one roof, you achieve better risk-adjusted returns than any single strategy can deliver.** This is Dalio's "Holy Grail" applied organizationally.

### Structure

Citadel operates as a "multi-manager" model with distinct business units:

1. **Citadel Equities** — Fundamental and quantitative equity strategies
   - Long/short equity
   - Sector specialists (tech, healthcare, energy, etc.)
   - Quantitative market making (now spun off as Citadel Securities)
   
2. **Citadel Credit** — Fixed income and credit
   - Corporate bonds, CLOs, distressed debt
   - Interest rate derivatives
   
3. **Citadel Commodities** — Energy, metals, agricultural
   - Physical and derivatives trading
   - Led by veteran commodity traders
   
4. **Citadel Global Quantitative Strategies** — Systematic
   - Statistical arbitrage
   - Factor-based strategies
   - Machine learning models

5. **Citadel Tactical Trading** — Discretionary macro
   - FX, rates, cross-asset macro

### How They Balance Strategy Teams

**Capital allocation (internal "risk budgeting"):**
- Capital is allocated to pods based on **risk-adjusted returns** and **capacity**
- Pods with higher Sharpe ratios get more capital — up to the point where adding more capital degrades returns (capacity constraint)
- Quarterly rebalancing of capital across pods
- **Drawdown triggers**: If a pod exceeds its loss limit (e.g., 5-7% of allocated capital), it is shrunk or shuttered

**Risk management (centralized):**
- Independent risk team (not reporting to traders) monitors:
  - **Gross exposure** limits per pod
  - **Net exposure** limits (max net long/short)
  - **Correlation** between pods (kept low intentionally)
  - **Concentration** limits (single name, sector)
  - **Leverage** limits
  - **VaR** limits (daily, weekly, monthly)
- **Real-time risk dashboards** — Every position is marked to market in real time

### Instrument Focus
- Everything: equities, bonds, credit, commodities, FX, derivatives, options, structured products, physical commodities

### Risk Framework
- **Risk budgeting at pod level**: Each pod gets a VaR budget (e.g., $10M daily VaR)
- **Scaling mechanism**: If a pod's realized volatility exceeds target, positions are cut
- **Stop-losses**: Hard risk limits per pod — 5-7% max drawdown before capital is pulled
- **Correlation monitoring**: If two pods become correlated, one is adjusted
- **Stress testing**: Portfolio is stress-tested against 2008, 2020, 1998 LTCM scenarios
- **Liquidity tiering**: Positions in liquid instruments get higher leverage limits; illiquid positions are capped

### Alpha Source (The Edge)
- **Talent arbitrage**: Citadel hires the best traders from the best firms, paying top-tier compensation
- **Capital efficiency**: Internal capital markets — capital moves to highest-return pods faster than external allocators can react
- **Shared infrastructure**: One execution, risk, and tech platform serves all pods (reducing costs)
- **Cross-pod information**: Legal and ethical walls maintained, but macro insights from commodities can inform rates trading
- **Brand & access**: Better prime brokerage terms, better execution, better deal flow than competitors

### What's Replicable on MT5
- ✅ **Multi-strategy architecture** — Run 3-5 separate EAs, each with independent logic and signal trading
- ✅ **Capital allocation via risk budgeting** — Allocate capital across bots proportional to their recent Sharpe / risk-adjusted returns
- ✅ **Pod-level drawdown stops** — If a bot drops -5% in a month, disable it until investigated
- ✅ **Correlation monitoring** — Track daily PnL correlations between your bots; if two bots start correlating >0.6, investigate
- ✅ **Centralized risk overlay** — A master EA that monitors total portfolio exposure and can cut positions across all bots
- ❌ **Multi-manager talent** — You're one person; use diversification (different bot logics) instead
- ✅ **Gross/net exposure limits** — Track and cap total long exposure, total short exposure

---

## 4. AQR Capital Management — Style Premia

**Founders:** Cliff Asness, David Kabiller, John Liew, Robert Krail
**AUM:** ~$100B+ (peak)
**Strategy Type:** Systematic Factor Investing / Style Premia

### The Thesis

AQR's core insight: **There are four "style" factors (value, momentum, carry, defensive) that have delivered persistent, risk-adjusted excess returns across asset classes for decades.** These are not anomalies — they are compensation for bearing systematic risk or behavioral biases. The four factors:

1. **Value** — Buy cheap assets, sell expensive assets
2. **Momentum** — Buy recent winners, sell recent losers
3. **Carry** — Buy high-yielding assets, sell low-yielding assets
4. **Defensive** — Buy low-risk assets, sell high-risk assets (e.g., low-beta stocks)

### Practical Implementation Details

#### Value
- **Equities**: Book-to-price, earnings yield, cash flow yield
- **Fixed Income**: Real yield differentials across countries
- **Currencies**: Purchasing power parity deviations
- **Commodities**: Basis relative to long-term cost of production
- **Implementation**: Long cheapest quintile, short most expensive quintile
- **Lookback**: 5-year for book value ratios; updated quarterly
- **Rebalancing**: Monthly or quarterly

#### Momentum
- **Equities**: 12-month return (skip last month to avoid reversal)
- **Fixed Income**: 12-month return across country bond futures
- **Currencies**: 12-month return across FX pairs
- **Commodities**: 12-month return across futures
- **Implementation**: Long top 20% performers, short bottom 20%
- **Lookback**: 12 months, skip 1 month (to avoid short-term reversal)
- **Rebalancing**: Monthly
- **Add-on**: Use volatility scaling (size positions inversely to volatility)

#### Carry
- **Equities**: Dividend yield (long high div, short low/no div)
- **Fixed Income**: Yield curve carry (long steep, short flat)
- **Currencies**: Interest rate differentials (long high-yield, short low-yield)
- **Commodities**: Futures curve roll yield (long backwardation, short contango)
- **Implementation**: Trade the futures curve — roll yield is the alpha
- **Rebalancing**: Monthly (or when curve shape changes)

#### Defensive (Low Beta / Quality)
- **Equities**: Low volatility, low beta, high profitability, high payout ratios
- **Fixed Income**: Long high-quality sovereigns, short lower-quality
- **Implementation**: Long lowest-beta stocks, short highest-beta stocks (beta-neutral)
- **Also**: Quality factor — high ROE, low debt/equity, earnings stability
- **Rebalancing**: Quarterly

### Instrument Focus
- Equities (futures, ETFs, single stocks), bonds (futures), currencies (FX forwards/swaps), commodities (futures)

### Risk Framework (AQR-specific)
- **Volatility targeting**: Each sub-portfolio targets a specific volatility (e.g., 10% annualized)
- **Combined portfolio**: Equal risk-weight across the four style premia
- **Leverage**: Applied to bring total portfolio to target volatility (often 10-15%)
- **Trading costs**: AQR's edge in implementation — they model market impact, spreads, and commissions precisely; they trade patiently, using limit orders and TWAP
- **Rebalancing**: Phased over days/weeks to reduce market impact
- **Stress testing**: Strategies tested against:
  - Value crashes (2007 quant crisis)
  - Momentum crashes (2009 reversal)
  - Multi-factor drawdowns (2020 COVID)

### Alpha Source (The Edge)
- **Structural factor premiums**: Academic rigor — factors are well-documented and persist after controlling for risk
- **Implementation efficiency**: Better execution, lower costs than typical factor investors
- **Multi-asset breadth**: The same factor applied across asset classes creates diversification (equity value and currency value have low correlation)
- **Risk management**: Asness famously says "the only free lunch in finance is diversification"

### What's Replicable on MT5
- ✅ **Value** — On FX: PPP-based valuation (purchasing power parity). On indices: P/E ratio of index vs history → overvalued = short bias
- ✅ **Momentum** — MT5 has iMA, iCustom; simple 12-month momentum cross is implementable. Use with volatility scaling
- ✅ **Carry** — FX carry trade is the most MT5-accessible strategy. long AUD/JPY (high yield), short CHF/JPY (low yield). Gold carry via swap rates
- ✅ **Defensive** — Long/short beta via index vs vol products. On MT5: long US30 (low beta) vs short NAS100 (high beta) during risk-off
- ✅ **Multi-factor combo** — Run all four factors simultaneously as separate EAs, each targeting 5% vol, then aggregate
- ✅ **Volatility scaling** — Size = (target_vol / current_vol) × base_size
- ❌ **Multi-asset breadth** — MT5 is FX/CFD centric; you can't trade bonds directly but can trade bond ETFs (e.g., TLT) or 10Y Note futures if broker offers them

---

## 5. Man Group / AHL — Systematic Trend Following

**Founders:** David Harding, Martin Taylor, Graham Schwick (AHL)
**AUM:** ~$150B (Man Group total); AHL ~$50B
**Strategy Type:** Systematic Trend Following (CTA)

### The Thesis

AHL pioneered the systematic trend-following approach: **Markets trend over medium to long time horizons (weeks to months) due to behavioral biases (herding, anchoring, slow information diffusion) and structural factors (central bank policy, institutional flows).** The approach is purely systematic — no human judgment, no fundamental views.

### How It Works

1. **Trend detection**: Multiple lookback periods (e.g., 10-day, 20-day, 50-day, 100-day, 200-day) across all liquid futures markets
2. **Signal aggregation**: Weighted average of trend signals across timeframes
3. **Position sizing**: Proportional to signal strength, scaled by volatility
4. **Portfolio**: Equal risk allocation across ~100+ futures markets

### AHL's Specific Approach (from publicly available sources)

**AHL Diversified Programme** (the flagship):
- Trades ~100+ futures markets across:
  - **Equity indices** (S&P 500, FTSE, Nikkei, Euro Stoxx, etc.)
  - **Fixed income** (US 10Y, Bund, JGB, Gilt, etc.)
  - **FX** (EUR/USD, GBP/USD, USD/JPY, AUD/USD, etc.)
  - **Commodities** (crude oil, gold, copper, corn, wheat, etc.)
- **Multiple timeframes**: From short-term (few days) to long-term (several months)
- **Volatility normalization**: Each position sized to have equal risk contribution (1% daily VaR per position) — this is THE key risk mechanism
- **Signal types**:
  - **Breakout systems**: Entry when price breaks N-day high/low
  - **Moving average crossover**: E.g., 50-day vs 200-day MA
  - **Momentum**: RSI-based, rate of change
  - **Volatility breakout**: Entry when ATR expands significantly
- **Pyramiding**: Adding to winning positions as trend continues
- **Stop policy**: Trailing stops (moved to breakeven once position is sufficiently in profit)

### AHL's Edge in Implementation

- **Execution algorithms**: They execute large orders without moving markets (VWAP, TWAP, implementation shortfall)
- **Portfolio optimization**: Mean-variance optimization with constraints for turnover and liquidity
- **Risk scaling**: Position sizes are inversely proportional to volatility — during high vol, positions shrink; during low vol, they grow
- **Trend filter**: Only take signals when a "slow trend" confirms the "fast trend" (avoiding whipsaws)
- **Regime detection**: They use volatility regimes to adjust signal aggressiveness

### Risk Framework
- **Volatility targeting**: Portfolio targets constant volatility (e.g., 15% annualized)
- **Position limits**: Maximum 20% of daily volume per contract
- **Concentration limits**: Max 10% of risk in any single sector
- **Stop-losses**: System-level stops (if portfolio drops 10% in a month, reduce exposure)
- **Correlation monitoring**: Trend strategies can be correlated across assets in a crisis — they account for this
- **Overlay hedge**: During extreme correlation events (2020 COVID), they can put on a "risk-off" overlay

### Alpha Source (The Edge)
- **Behavioral**: Herding, endowment effect, anchoring — people underreact to new information, creating trends
- **Structural**: Central bank policy cycles create multi-year trends in rates and FX
- **Institutional**: Pension funds and asset managers rebalance slowly, creating serial correlation
- **Diversification**: 100+ uncorrelated markets create a robust portfolio
- **Persistence**: Trends are notoriously difficult to time, but over long periods trend following has positive expected returns

### What's Replicable on MT5
- ✅ **Trend following on FX pairs** — This is the most straightforward strategy on MT5
- ✅ **Multiple timeframe confirmation** — Use e.g., 50 EMA + 200 EMA on H1 + H4
- ✅ **Volatility-normalized position sizing** — Size = (1% of account) / (ATR × contract_value)
- ✅ **Trailing stops** — MT5 supports trailing stops natively
- ✅ **Multi-market** — Trade all major FX pairs (EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, NZDUSD) + indices (US30, NAS100, SPX500, GER40) + commodities (XAUUSD, XTIUSD, XAGUSD)
- ✅ **Breakout systems** — Donchian channel breakout (20-day high/low) is classic trend follow
- ✅ **Pyramiding** — MT5 allows multiple positions per symbol (set to "reverse" or "netting" mode)
- ❌ **100+ markets** — You're limited to what your MT5 broker offers; typically 20-40 instruments

**Key replicable insight**: A simple system — 50-day EMA > 200-day EMA = long, reverse = short — applied to 10 uncorrelated markets with equal volatility weighting, has historically produced Sharpe of 0.4-0.6.

---

## 6. Two Sigma / DE Shaw — Data-Driven Quant

**Founders:** David Siegel & John Overdeck (Two Sigma); David E. Shaw (DE Shaw)
**AUM:** Two Sigma ~$60B; DE Shaw ~$50B+
**Strategy Type:** Data-Driven Systematic Quantitative

### The Thesis

**"Data is the new alpha"** — Both firms aggressively pursue alternative data sources, machine learning, and computational methods to discover and exploit market inefficiencies. The core belief: **Most traditional market data is already "mined out" — the next generation of alpha lies in non-traditional data.**

### Two Sigma's Approach

Two Sigma is essentially a technology company that happens to be a hedge fund:

1. **Massive computing infrastructure**: One of the largest private computing clusters in the world (thousands of CPU/GPU cores)
2. **Alternative data**:
   - Satellite imagery (retail parking lots, crop yields, oil tanker levels)
   - Credit card transaction data (consumer spending)
   - Web scraping (job postings, product reviews, shipping data)
   - Social media sentiment (Twitter, Reddit, news sentiment)
   - Weather data (energy demand, agricultural yields)
   - Geolocation data (foot traffic to retailers)
3. **Machine learning**:
   - Deep learning for pattern recognition in alternative data
   - Natural language processing for sentiment extraction
   - Reinforcement learning for execution optimization
   - Ensemble methods combining thousands of models
4. **Research culture**:
   - ~75% of employees are technologists/researchers
   - PhDs in computer science, statistics, physics, engineering
   - Internal "research marketplace" where researchers propose and test ideas
   - Strict separation between research and trading

### DE Shaw's Approach

DE Shaw pioneered computational finance in the 1980s:

1. **Statistical arbitrage**: DE Shaw was among the first to systematically apply statistical arbitrage to equities (cointegration, pairs trading at scale)
2. **Hybrid approach**: Unlike Renaissance (pure quant), DE Shaw combines:
   - Systematic models (60% of risk)
   - Discretionary macro overlays (40% of risk)
   - Fundamental analysts inform the quantitative models
3. **Key innovations**:
   - **"Overnight momentum"**: Opening gap strategies
   - **"Cross-sectional mean reversion"**: Short-term reversal within sectors
   - **"Volatility arbitrage"**: Using options to trade implied vs realized vol
   - **"Merger arbitrage"**: Statistical models to price deal probabilities
4. **Famous trade**: DE Shaw's "Statistical Arbitrage" group (led by Peter Muller) was the inspiration for the book *The Quants* and *The Fear Index*

### Common Characteristics

| Dimension | Two Sigma | DE Shaw |
|-----------|-----------|---------|
| **Alpha source** | Alternative data, ML, compute | Statistical arb, hybrid models |
| **Team** | Pure technologists (~75%) | Quant + fundamental blend |
| **Horizons** | Short-to-medium term | Short-to-long term |
| **Instruments** | Equities (mostly), futures, options | Equities, fixed income, options |
| **Edge** | Data + compute infrastructure | Model innovation + hybrid approach |

### Risk Framework (Both)
- **Strict volatility targets** (10-15% annualized)
- **Diversification across models**: Hundreds/thousands of independent models, each contributing tiny risk
- **Model governance**: Rigorous backtesting standards (out-of-sample, walk-forward, Monte Carlo)
- **No single model > 5% of risk**
- **Continuous monitoring**: Model performance tracked daily; degraded models are retired
- **Execution logic**: Separate from signal logic — execution is optimized independently

### Alpha Source (The Edge)
- **Data exclusivity**: Proprietary alternative data that competitors don't have
- **Compute advantage**: Can process petabytes of data and train millions of models
- **Talent concentration**: Hundreds of PhDs working on the same problem
- **R&D velocity**: Thousands of experiments per week; failed experiments are as valued as successful ones (learning what doesn't work)
- **Execution science**: Advanced order routing, dark pools, smart order routing

### What's Replicable on MT5
- ✅ **Alternative data proxies**:
  - Web scraping for sentiment (Python → MT5 via MQL bridge or file import)
  - Economic calendar → trade news events systematically
  - COT (Commitment of Traders) data for positioning
- ✅ **Machine learning models**:
  - Train in Python (scikit-learn, XGBoost, LightGBM), export model coefficients to MQL5
  - Use ONNX runtime or DLL import for real-time inference
- ✅ **Ensemble of models** — Combine 3-5 independent models (trend, mean reversion, carry, sentiment, volatility) into one meta-signal
- ✅ **Walk-forward optimization** — Implement in Python; test out-of-sample before deploying
- ❌ **Proprietary alternative data** — Most satellite/scraped data sources require $10K+/month; use free proxies (Google Trends, FRED data, CFTC COT)
- ✅ **Model governance** — Track each EA's Sharpe, win rate, drawdown; retire underperformers
- ✅ **Execution optimization** — Use limit orders, avoid market orders, slice large positions

---

## 7. Cross-Fund Synthesis: Replicable for a Small Quant Team on MT5

### The Common Threads

Across all six funds, these principles emerge as universal:

| Principle | Bridgewater | Renaissance | Citadel | AQR | Man/AHL | Two Sigma/DE Shaw |
|-----------|-------------|-------------|---------|-----|---------|-------------------|
| **Risk parity / equal vol** | ✅ Core | ✅ Implicit | ✅ Pod-level | ✅ Style-level | ✅ Position-level | ✅ Model-level |
| **Diversification** | ✅ Holy Grail | ✅ Thousands | ✅ Pods | ✅ Factors | ✅ 100+ markets | ✅ Thousands models |
| **No single point of failure** | ✅ 4 quadrants | ✅ 1000s signals | ✅ Pod stops | ✅ 4 factors | ✅ 100+ markets | ✅ 1000s models |
| **Volatility targeting** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Data/process edge** | ✅ Thesis | ✅ Clean data | ✅ Talent | ✅ Academic | ✅ Systematic | ✅ Alternative data |

### Practical Implementation Roadmap for MT5

**Phase 1 — Core Infrastructure (Your Current State)**
- [x] Working VWAP mean reversion bot (EURUSD)
- [ ] Add volatility-normalized position sizing (1% risk per trade based on ATR)
- [ ] Add centralized risk manager (master EA that monitors total exposure)

**Phase 2 — Add 3 Uncorrelated Strategy Bots**
1. **Trend Following** (Man/AHL style)
   - Instrument: US30 or NAS100
   - Logic: 50 EMA vs 200 EMA on H4, vol-scaled sizing
   - Expected correlation with VWAP bot: ~ -0.1 to 0.1

2. **FX Carry** (AQR style)
   - Instrument: AUD/JPY or USD/TRY (if broker allows)
   - Logic: Long if swap positive and above 200 MA; exit when swap turns negative
   - Expected correlation with VWAP bot: ~ -0.1 to 0.2

3. **Volatility Regime Bot** (Bridgewater macro flavor)
   - Instrument: XAUUSD or VIX-type product
   - Logic: Long volatility when VIX < 15; short volatility when VIX > 30
   - Expected correlation: Negative with trend bot during crashes

**Phase 3 — Risk Framework (Citadel-inspired)**
- [ ] Daily VaR calculation across all bots (1% of total account at risk per day)
- [ ] Correlated exposure monitor — if two bots go same direction > 60% of time, review
- [ ] Drawdown stops — if any bot loses 5%, disable it
- [ ] Capital rebalancing — monthly: shift capital to bots with highest Sharpe over trailing 60 days

**Phase 4 — Optimization & Scaling (Renaissance/Two Sigma-inspired)**
- [ ] Walk-forward optimization (Python + MT5 backtester)
- [ ] Ensemble signals (combine 3-5 simple models into one trade decision)
- [ ] Alternative data integration (economic sentiment, COT data, cross-asset correlations)
- [ ] Execution improvement (use limit orders, slice large positions over minutes)

### MT5-Specific Implementation Notes

| Concept | MT5 Implementation |
|---------|-------------------|
| Volatility targeting | `lot_size = (account_risk_pct * account_balance) / (ATR * contract_value)` |
| Risk parity across bots | Allocate capital so each bot has same projected daily VaR |
| Correlation monitoring | Track daily PnL vector per bot in global array; compute Pearson correlation every 20 bars |
| Drawdown stops | `if AccountEquity() < AccountBalance() * 0.95 → close all positions` |
| Multi-timeframe | `iClose(NULL, PERIOD_H4, 0)` for trend; `iClose(NULL, PERIOD_M15, 0)` for entry |
| Signal aggregation | Weighted average of 3-5 sub-signals; trade only if |signal| > threshold |
| Walk-forward optimization | Python script using MT5 History Center data → optimize hyperparams → write to .set file |

### Expected Sharpe Ratios (Realistic)

| Strategy Type | Expected Sharpe (live) | Notes |
|--------------|----------------------|-------|
| VWAP Mean Reversion (EURUSD) | 0.3 - 0.8 | Depends on session, spread costs |
| Trend Following (indices) | 0.2 - 0.6 | 40-60% win rate, large winners |
| FX Carry | 0.2 - 0.5 | High swap profits but crash risk |
| Pairs Trading | 0.4 - 0.9 | Lower returns but smoother equity curve |
| Combined Portfolio (4 bots) | 0.6 - 1.2 | Diversification benefit is real |

### Key Takeaway

**The most important lesson from all six funds**: The edge is NOT in any single strategy. It's in:
1. **Diversification across uncorrelated return streams** (Bridgewater's Holy Grail)
2. **Robust risk management** (volatility targeting, position limits, drawdown stops)
3. **Systematic process** (no discretionary overrides, follow the model)
4. **Continuous improvement** (retire what doesn't work, add new signals)

Your existing VWAP bot is a perfectly valid starting point. Adding 2-4 uncorrelated bot strategies with proper risk parity weighting will likely improve your Sharpe ratio by 2-3x more than optimizing the VWAP bot further.

---

*Research compiled from: Bridgewater's "Principles" and investor letters; Zuckerman's "The Man Who Solved the Market" (Renaissance); AQR working papers (Asness, Ilmanen, et al.); Man Group annual reports and AHL technical papers; Business Insider/FT profiles of Citadel; interviews with Two Sigma/DE Shaw executives; Investopedia; Wikipedia; SEC 13F filings; and academic papers on factor investing, risk parity, and trend following.*
