"""Turns a smart-money position delta into a sized, attributed order on the
runner's own OKX account. This is the bot's actual value-add over trading on
OKX directly - everything below it (signal reading, order attribution) is
plumbing; this is the decision logic.
"""
from dataclasses import dataclass

from smartmoney_bot.risk import RiskLimits, size_order
from smartmoney_bot.signals.smart_money import PositionDelta


class MirrorSkipped(Exception):
    """Raised when a delta can't be mirrored right now because required
    market data (ticker, instrument spec) is unavailable - e.g. the
    instrument isn't listed in demo trading, or a call transiently returned
    no data. Callers should treat this the same as RiskLimitExceeded: skip
    this one delta and keep the poll loop running, never crash the process
    over one instrument."""


@dataclass
class MirrorContext:
    equity_usd: float
    open_position_count: int
    allocated_to_trader_pct: float


def side_for(delta: PositionDelta) -> str:
    """OKX order side: buy to open/increase a long or close a short position,
    sell for the opposite."""
    if delta.kind == "closed":
        was_long = delta.previous is not None and delta.previous.pos_side in ("long", "net")
        return "sell" if was_long else "buy"
    is_long = delta.position is not None and delta.position.pos_side in ("long", "net")
    return "buy" if is_long else "sell"


def _first_row(resp: dict, what: str, inst_id: str) -> dict:
    rows = resp.get("data") or []
    if not rows:
        raise MirrorSkipped(f"no {what} data for {inst_id}: {resp}")
    return rows[0]


def mirror_delta(adapter, delta: PositionDelta, context: MirrorContext,
                  limits: RiskLimits, td_mode: str = "cross") -> dict:
    """Places (or closes) an order mirroring one detected position delta.
    Returns the adapter's response dict. Raises RiskLimitExceeded or
    MirrorSkipped without calling place_order/close_position if the trade
    can't or shouldn't be placed - callers should catch both and continue."""
    if delta.kind == "closed":
        return adapter.close_position(inst_id=delta.inst_id, mgn_mode=td_mode)

    ticker_row = _first_row(adapter.get_ticker(delta.inst_id), "ticker", delta.inst_id)
    mark_price = float(ticker_row["last"])

    inst_row = _first_row(
        adapter.get_instruments(inst_type="SWAP", inst_id=delta.inst_id),
        "instrument", delta.inst_id,
    )
    ct_val = float(inst_row["ctVal"])
    lot_sz = float(inst_row["lotSz"])
    min_sz = float(inst_row["minSz"])

    size = size_order(
        equity_usd=context.equity_usd,
        mark_price=mark_price,
        ct_val=ct_val,
        lot_sz=lot_sz,
        min_sz=min_sz,
        limits=limits,
        open_position_count=context.open_position_count,
        allocated_to_trader_pct=context.allocated_to_trader_pct,
    )

    return adapter.place_order(
        inst_id=delta.inst_id,
        td_mode=td_mode,
        side=side_for(delta),
        ord_type="market",
        sz=size,
        pos_side=delta.position.pos_side if delta.position else None,
    )
