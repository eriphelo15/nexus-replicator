"""Descarga los mercados de Polymarket que pagan premios por dar liquidez."""
import json
import requests

U = "https://clob.polymarket.com/rewards/markets/current"
out, cur = [], ""
while True:
    d = requests.get(U, params={"next_cursor": cur} if cur else {}, timeout=30).json()
    out += d.get("data", [])
    cur = d.get("next_cursor")
    if not cur or cur == "LTE=" or not d.get("data"):
        break
json.dump(out, open("rewards_markets.json", "w"))
print(len(out))
