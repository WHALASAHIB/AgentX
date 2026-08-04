import json

ARCHIVE = "C:/Trading/research_division/state/research_hypotheses.json"
a = json.load(open(ARCHIVE))
all_i = {i["name"]: i for i in a["active"] + a["archived"]}

targets = [
    "Gold_Calendar_Spread_Physical_Demand_Proxy",
    "Futures_Spot_Convergence_Arbitrage",
    "FOMC_Blackout_Volatility_RangeTrade",
    "Central_Bank_Calendar_Dovish_Hawkish_Window",
    "NFP_Week_Mean_Reversion_Bias",
    "PostEvent_VolRiskPremium_Collapse",
    "News_Impact_Volatility_Decay",
    "Event_Window_Seasonal_Compression",
]
for n in targets:
    i = all_i.get(n)
    if not i:
        print(f"=== {n}: MISSING ===")
        continue
    print(f"=== {n} [{i['family']} | {i.get('self_grade','?')}] ===")
    print("DESC:", i.get("description", "")[:200])
    print("MECH:", (i.get("market_behaviour") or i.get("description") or "")[:400])
    print()
