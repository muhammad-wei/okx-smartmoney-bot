# Safety, risk, and how commission actually works

Read this before running with `--live`.

## What this bot does

It watches OKX's Smart Money leaderboard, tracks a configurable set of
top-performing traders, and when one of them opens, resizes, or closes a
position, mirrors that change (sized down to a small fraction of *your* own
account) into your own OKX account. Every order it places carries an AI
Builder Code in OKX's `tag` field.

**This executes real trades with your own funds, based on mirroring other
traders. It is not financial advice. There is no profitability guarantee.
Past performance of the traders it tracks is not indicative of future
results. You bear all risk for funds in the account you connect.**

## Setup safety

- **API key permissions: Read + Trade only. Never enable Withdrawal.** If a
  key with this bot's credentials is ever compromised, the blast radius should
  be "someone can trade with my funds," never "someone can move my funds out."
- **Start with a demo-trading key**
  (`https://www.okx.com/account/my-api?go-demo-trading=1`), not a live one.
  The bot defaults to simulated mode (`simulated=True`, sends
  `x-simulated-trading: 1`) regardless of which key you use — you must pass
  `--live` *and* `--confirm-live-order` before any real-money order is sent.
- Your `.env` file stays on your own machine. This bot has no server
  component and collects nothing from you — that's the whole point of the
  no-custody design.

## How AI Builder commission actually works (and when it doesn't)

Registering as an AI Builder or running this tool earns nothing by itself.
Commission only accrues on real OKX orders that carry a valid AI Builder Code
in the `tag` field, and even then, OKX's official Commission Rules (Section 7)
excludes several categories of transaction from counting at all:

1. **The counterparty is not on OKX** — no commission is available to
   allocate.
2. **Proprietary transactions of the AI Builder.** If you (the tool's author)
   run this on your own account, those trades likely don't count. Real
   commission requires *other people* running this on their *own* regular
   accounts — that's the entire design rationale below.
3. **Users on a special fee rate** (market-maker program, other preferential
   fee arrangement).
4. **Transactions using commission cards** or other ineligible fee-deduction
   methods.
5. **Transactions through managed trading sub-accounts.**
6. **Transactions not submitted through an approved integration**, or missing
   a valid Builder Code.
7. **Unexecuted transactions**, or transactions generating no net trading fee
   due to cancellation/reversal. This is also why **simulated/demo trades
   never generate commission** — they generate no real fee at all, a simpler
   and separate reason from #2. Simulated mode exists purely to prove
   attribution works (verify `tag` on a placed order), never to generate
   revenue.
8. **Transactions otherwise ineligible** under OKX Broker rules, the AI
   Builder agreement, risk controls, or applicable law.

Separately (not part of the Section 7 list): **trades from users at VIP 4 or
above don't count** toward AI Builder commission — only Regular and VIP 1–3
tier counterparties do.

## Why the default AI Builder Code is baked in

`config.py` ships `DEFAULT_AI_BUILDER_CODE` as a plain, visible constant — it
is not a secret (OKX's AI Builder Codes are plain order-tag identifiers, format
`^[A-Za-z0-9]{1,16}$`, unrelated to any NFT or on-chain product despite a
same-named but unrelated NFT collection existing on OKX's X Layer NFT
marketplace). Anyone who runs this tool unmodified attributes their trades to
its original author. `--ai-builder-code` overrides it if you're running your
own fork under your own code — this is open source, so nothing stops that,
and it's not meant to.

## Data source: what's verified, what isn't

The Smart Money leaderboard/position endpoints this bot depends on
(`GET /api/v5/orbit/public/leaderboard`, `.../position-current`,
`.../position-history`) are **not in OKX's official public API documentation**.
They were confirmed real via two independent sources — OKX's own open-source
`agent-trade-kit` repository, and a separately-installed, OKX-authored,
versioned skill package on the machine this bot was built on — and verified
live via an authenticated call before this code was written (real traders and
real open positions were returned). This is a real, currently-maintained OKX
capability, not a fragile scrape. That said, there's no published stability or
rate-limit guarantee on these specific paths, unlike the rest of OKX's v5 API.
If they ever break or change shape, OKX's officially-documented Copytrading
module (`GET /api/v5/copytrading/public-lead-traders`, confirmed public/no-auth,
5 requests/2s per IP) is a stable, documented fallback for trader discovery —
note that it's a different, curated pool of "Lead Traders" who opted into
OKX's own copy-trading product, not the same universe as Smart Money analytics.

**Confirmed live response envelopes** (each endpoint nests its row data
differently — verified against real responses, not assumed; see
`scripts/debug_leaderboard.py` and `tests/test_smart_money_parsing.py`):

| Endpoint | Row data is at | Notes |
|---|---|---|
| `get_leaderboard` | `resp["data"]["data"]` | outer `data` is a dict, not a list |
| `get_trader_positions` | `resp["data"][0]["posData"]` | one-element list wrapping `posData`; `resp["data"] == []` when the trader has no open positions |
| `get_trader_positions_history` | `resp["data"]` | flat list directly, no extra nesting |

None of these match the shape the MCP tool wrapper returns (which flattens all
three to a plain top-level list) — the raw REST envelope and the MCP tool's
processed output are genuinely different, so don't assume MCP-observed shapes
carry over to direct REST calls on any endpoint you haven't checked yourself.

## Order sizing (see `risk.py`, `strategy/mirror.py`)

OKX SWAP order sizes are **contract counts**, not base-currency units — sizing
by `notional_usd / mark_price` (an earlier version of this bot did exactly
that) produces an invalid size on almost every real instrument. Before sizing,
the bot fetches the instrument's `ctVal` (contract face value), `lotSz`, and
`minSz` via `get_instruments`, converts the target USD notional to contracts,
and rounds down to a multiple of `lotSz`. If the result is below `minSz` (a
real, expected outcome for small accounts on expensive instruments at a small
`--allocation-pct`), the delta is skipped rather than sent as an invalid
order. **Bookkeeping only records a position when OKX's response `code` is
`"0"`** — an HTTP call succeeding is not the same as an order being accepted;
an earlier version recorded a "position" even when OKX rejected the order
(e.g. lot-size errors), silently corrupting the bot's own risk-tracking state.

The strategy loop also treats missing/empty market data (e.g. an instrument
not listed in demo trading) as a per-delta skip, not a crash — and wraps each
delta's processing in a catch-all so one unexpected error can't take down a
long-running process. All of this was found and fixed via a real live run,
not anticipated in advance — see the conversation history for specifics if
you're debugging something similar.

## Risk controls this bot applies (see `risk.py`)

- A configurable fraction of your own equity per mirrored trade
  (`--allocation-pct`, default 2%) — it does not copy a tracked trader's
  absolute position size.
- A hard cap on concurrently open mirrored positions
  (`--max-concurrent-positions`, default 5).
- A cap on how much of your equity can go to mirroring any single trader
  (`--max-pct-per-trader`, default 10%).

These are starting points, not guarantees — adjust them, and understand that
tighter limits reduce both risk and how closely the mirror tracks the source
trader.
