import MetaTrader5 as mt5
import json
from datetime import datetime, timedelta

# Initialize
print("=== MT5 Connection Test ===")
init_result = mt5.initialize()
print(f"initialize(): {init_result}")

if init_result:
    info = mt5.account_info()
    if info:
        print(f"Account: {info.login} | Server: {info.server} | Balance: {info.balance}")
        print(f"Terminal path: {mt5.terminal_info().path}")
    else:
        print(f"account_info() failed: {mt5.last_error()}")
    
    # Check time range - last 2 hours
    now = datetime.now()
    from_time = now - timedelta(hours=2)
    print(f"\nCurrent time: {now}")
    print(f"Looking back from: {from_time}")
    
    # Get history deals for magic 780012
    deals = mt5.history_deals_get(from_time, now, group="*EURUSD*")
    last_error = mt5.last_error()
    print(f"\nHistory deals result type: {type(deals).__name__}")
    print(f"Last error: {last_error}")
    
    if deals is not None and len(deals) > 0:
        magic_deals = [d for d in deals if d.magic == 780012]
        print(f"\nTotal EURUSD deals: {len(deals)}")
        print(f"Magic 780012 deals: {len(magic_deals)}")
        
        for d in magic_deals:
            print(f"\n  Ticket: {d.ticket}")
            print(f"  Symbol: {d.symbol}")
            print(f"  Type: {'BUY' if d.type == 0 else 'SELL' if d.type == 1 else d.type}")
            print(f"  Volume: {d.volume}")
            print(f"  Price: {d.price}")
            print(f"  Profit: {d.profit}")
            print(f"  Time: {datetime.fromtimestamp(d.time)}")
            print(f"  Position ID: {d.position_id}")
            print(f"  Comment: {d.comment}")
    elif deals is None:
        if last_error and last_error[0] == 1:
            print("\nNo deals in time range (None returned, error=1=Success = no deals found)")
        else:
            print(f"\nError or None: {last_error}")
    else:
        print("\nNo deals in time range (empty list)")
    
    mt5.shutdown()
else:
    err = mt5.last_error()
    print(f"\nInit failed: {err}")
    mt5.shutdown()
