#!/usr/bin/env python3
"""Test MT5 connection."""
import json
import time
import sys

cfg_path = r'C:\Trading\mt5_config.json'
cfg = json.loads(open(cfg_path).read())
print('Config keys:', list(cfg.keys()))
print('Login:', cfg.get('login'))
print('Server:', cfg.get('server'))

import MetaTrader5 as mt5
print('MT5 package version:', mt5.__version__)

# Try with login params
print('Initializing MT5...')
start = time.time()
init = mt5.initialize(
    path=cfg.get('terminal_path', r'C:\Program Files\MetaTrader 5\terminal64.exe'),
    login=int(cfg['login']),
    password=cfg['password'],
    server=cfg['server'],
    timeout=30000,
)
elapsed = time.time() - start
print(f'Init result: {init}, took {elapsed:.1f}s')
if not init:
    err = mt5.last_error()
    print(f'Error: {err}')

if init:
    acc = mt5.account_info()
    print(f'Account login: {acc.login}')
    print(f'Server: {acc.server}')
    print(f'Balance: ${acc.balance:,.2f}')
    print(f'Equity: ${acc.equity:,.2f}')
    
    # Test data fetch
    from datetime import datetime, timedelta
    rates = mt5.copy_rates_range('XAUUSD', mt5.TIMEFRAME_H1, datetime.now() - timedelta(days=30), datetime.now())
    print(f'XAUUSD H1 bars: {len(rates) if rates is not None else 0}')

mt5.shutdown()
print('MT5 shutdown OK')
