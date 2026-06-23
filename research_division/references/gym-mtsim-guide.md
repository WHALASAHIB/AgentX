# gym-mtsim Integration Guide

**Repo:** [AminHP/gym-mtsim](https://github.com/AminHP/gym-mtsim) (⭐521, MIT)
**Our adapter:** `C:\Trading\research_division\gym_mtsim_adapter.py`

## What It Is

gym-mtsim provides an OpenAI Gym-compatible trading simulator using real MT5 data. It's positioned between backtesting and live trading — you can train RL agents, test strategies, and run simulations against actual market conditions.

## Integration Architecture

```
MT5 Terminal (on VM 10.10.10.100)
  │  mt5.copy_rates_range()
  ▼
load_mt5_data() in gym_mtsim_adapter.py
  │  Creates pandas DataFrame (Open, High, Low, Close, Volume)
  │  Caches to parquet for offline use
  ▼
MtSimulator (gym-mtsim core)
  │  Simulates balance, equity, margin, positions
  │  Steps through time series data
  ▼
MtSimTradingEnv (OpenAI Gym)
  │  Standard Gym interface: reset(), step(), render()
  │  Observation: OHLCV window
  │  Actions: Hold (0), Buy (1), Sell (2)
  ▼
Research Division Reports
  C:\Trading\research_division\reports\gym_mtsim_*.json
  C:\Trading\research_division\reports\gym_mtsim_*.md
```

## Usage

### CLI — via Research Division orchestrator

```bash
cd C:\Trading\research_division
python run.py --simulate
python run.py --simulate --symbol XAUUSD --days 90
python run.py --simulate --symbol EURUSD --days 30
```

### Python API

```python
from gym_mtsim_adapter import create_simulator, create_env, run_simulation

# Quick simulation
result = run_simulation(symbol="XAUUSD", days=60)
print(result["final_equity"], result["total_reward"])

# Custom simulator
sim = create_simulator(symbols=["XAUUSD", "EURUSD"], days=90)
env = create_env(sim, trading_symbols=["XAUUSD"], window_size=20)

# Use with stable-baselines3 for RL
from stable_baselines3 import PPO
model = PPO("MlpPolicy", env, verbose=1)
model.learn(total_timesteps=10000)
```

## RL Training Example

```python
from gym_mtsim_adapter import create_simulator, create_env
from stable_baselines3 import PPO

# Create environment
sim = create_simulator(symbols=["XAUUSD"], days=180, timeframe=60)  # H1 data
env = create_env(sim, trading_symbols=["XAUUSD"], window_size=20)

# Train PPO agent
model = PPO("MlpPolicy", env, verbose=1, learning_rate=0.0003, n_steps=2048)
model.learn(total_timesteps=50000)

# Save model
model.save("C:/Trading/research_division/models/xauusd_ppo_50k")
```

## Data Caching

OHLCV data fetched from MT5 is cached to parquet files:

```
C:\Trading\research_division\state\ohlcv_XAUUSD_60d_tf0.parquet
C:\Trading\research_division\state\ohlcv_EURUSD_30d_tf60.parquet
```

Future loads use cached data if MT5 is unavailable.

## Troubleshooting

### "MT5 init failed: IPC timeout"
MT5 terminal64.exe is not running or not responding. Fix:
1. Kill any stuck MT5 processes: `taskkill /F /IM terminal64.exe`
2. Launch MT5: `"C:\Program Files\MetaTrader 5\terminal64.exe"`
3. Wait 15s for it to initialize
4. Re-run the simulation

### Cache corruption
Delete the parquet file for the affected symbol and re-fetch:
```bash
del C:\Trading\research_division\state\ohlcv_XAUUSD_*.parquet
```

### No data returned
- Ensure the symbol is available in your MT5 account (Market Watch)
- Check MT5 has the required history (scroll back in the chart)
- Try a longer `days` parameter

## Files

| File | Purpose |
|------|---------|
| `gym_mtsim_adapter.py` | Main adapter module |
| `state/ohlcv_*.parquet` | Cached OHLCV data |
| `reports/gym_mtsim_*.json` | Simulation result reports |
| `reports/gym_mtsim_*.md` | Human-readable summaries |
| `gym_mtsim.log` | Integration log |
