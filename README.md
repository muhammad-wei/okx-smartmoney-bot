# smartmoney-bot

Mirrors OKX's top-performing "Smart Money" traders' positions into your own
OKX account — sized down to a small fraction of your equity, with your own
funds, under your own API key.

Every order this bot places carries an OKX AI Builder Code in the order's
`tag` field. If you run it unmodified, that's the original author's code —
running this tool is how the author earns AI Builder commission on the
trading volume it generates. See [docs/SAFETY.md](docs/SAFETY.md) for exactly
when that commission does and doesn't apply, and read it in full before using
`--live`.

## What it does

1. Polls OKX's Smart Money leaderboard for top traders matching your filter
   (win rate, drawdown, lookback period).
2. Polls each tracked trader's current positions and detects when one opens,
   resizes, or closes.
3. Mirrors that change into your own account at a configurable fraction of
   your equity, respecting position-count and per-trader allocation caps.
4. Defaults to simulated trading — no real funds move until you explicitly
   pass `--live --confirm-live-order`.

This is **not** a copy of OKX's official Copy Trading product. It reads OKX's
broader Smart Money analytics (a bigger trader pool, undocumented-but-real
endpoints — see [docs/SAFETY.md](docs/SAFETY.md)) and does its own mirroring
via ordinary spot/swap orders.

## Setup

Requires Python ≥ 3.10.

```bash
git clone https://github.com/muhammad-wei/okx-smartmoney-bot.git
cd okx-smartmoney-bot
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# Edit .env with your OWN OKX API key (read + trade only, never withdrawal).
# Start with a demo-trading key: https://www.okx.com/account/my-api?go-demo-trading=1
```

## Usage

```bash
# Simulated (default) — no real funds move
python -m smartmoney_bot run --traders 5 --allocation-pct 0.02

# Live — requires both flags, on purpose
python -m smartmoney_bot run --traders 5 --allocation-pct 0.02 --live --confirm-live-order
```

Key options (`python -m smartmoney_bot run --help` for the full list):

| Flag | Default | Meaning |
|---|---|---|
| `--traders` | `5` | How many top traders to track |
| `--sort-by` | `pnlRatio` | `pnl` or `pnlRatio` leaderboard ranking |
| `--period` | `30` | Leaderboard lookback window in days (`3`/`7`/`30`/`90`) |
| `--min-win-rate` | none | Filter traders below this win rate (0~1) |
| `--allocation-pct` | `0.02` | Fraction of your equity per mirrored trade |
| `--max-concurrent-positions` | `5` | Cap on this bot's open positions |
| `--max-pct-per-trader` | `0.10` | Cap on equity allocated to one tracked trader |
| `--ai-builder-code` | (author's code) | Override only if running your own fork |
| `--live` / `--confirm-live-order` | off | Both required to place real orders |

## Architecture

```
src/smartmoney_bot/
├── config.py             # credentials, AI Builder Code default + validation
├── exchanges/
│   ├── base.py           # ExchangeAdapter interface (see note below)
│   └── okx/
│       ├── client.py     # signed OKX REST calls (copied signing code + new
│       │                   Smart Money endpoints)
│       └── adapter.py    # binds client.py to this bot's config
├── signals/smart_money.py  # trader discovery + position-change detection
├── strategy/mirror.py      # delta -> sized, attributed order
├── risk.py                 # position sizing and guardrails
└── cli.py                  # `python -m smartmoney_bot run ...`
```

`ExchangeAdapter` is a pluggable interface — only OKX is implemented. Binance
was evaluated and deliberately not built: it has no public smart-money
signal API to track, and its commission/attribution program is gated to
institutional partners with 20,000+ users, so it wouldn't generate commission
at this project's scale. See [docs/SAFETY.md](docs/SAFETY.md) for the full
reasoning — the interface exists so an adapter could be added later without
reworking the strategy layer.

## Testing

```bash
pytest
```

All tests run offline against fixtures — no API key or network access needed.
`tests/test_signing.py` carries known-answer signing vectors so the copied
HMAC signing code can never silently drift.

## License

MIT — see [LICENSE](LICENSE).
