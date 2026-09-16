"""One-off diagnostic: print the RAW response shape from all three orbit/*
endpoints, so we fix parsing for all of them at once. Prints trader data only -
nothing sensitive. Run from the project root with the venv active and .env
filled in:
    python scripts/debug_leaderboard.py
"""
import json
import sys

sys.path.insert(0, "src")

from dotenv import load_dotenv

load_dotenv()

import os

from smartmoney_bot.exchanges.okx import client

api_key = os.environ["OKX_API_KEY"]
secret_key = os.environ["OKX_SECRET_KEY"]
passphrase = os.environ["OKX_PASSPHRASE"]
base_url = "https://www.okx.com"


def show(name, resp):
    print(f"\n=== {name} ===")
    print("top-level keys:", list(resp.keys()) if isinstance(resp, dict) else type(resp))
    print(json.dumps(resp, indent=2)[:1500])


leaderboard = client.get_leaderboard(
    base_url, api_key, secret_key, passphrase,
    sort_by="pnlRatio", period="30", limit="3", simulated=True,
)
show("get_leaderboard", leaderboard)

# Pull one authorId out of whatever shape leaderboard turned out to have, so we
# can test the other two endpoints against a real trader.
rows = leaderboard.get("data")
if isinstance(rows, dict):
    rows = rows.get("data", [])
author_id = rows[0]["authorId"] if rows else None
print(f"\nUsing authorId={author_id} for the position calls below")

if author_id:
    positions = client.get_trader_positions(
        base_url, api_key, secret_key, passphrase,
        author_id=author_id, simulated=True,
    )
    show("get_trader_positions", positions)

    history = client.get_trader_positions_history(
        base_url, api_key, secret_key, passphrase,
        author_id=author_id, limit="2", simulated=True,
    )
    show("get_trader_positions_history", history)
