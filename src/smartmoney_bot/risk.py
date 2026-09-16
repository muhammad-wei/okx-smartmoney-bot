"""Position sizing and risk guardrails for mirrored trades.

Deliberately simple, conservative defaults - a starting point, not a
proprietary sizing model. Adjust via CLI flags (see cli.py).
"""
import math
from dataclasses import dataclass


@dataclass
class RiskLimits:
    allocation_pct: float = 0.02       # fraction of own equity per mirrored trade
    max_concurrent_positions: int = 5   # hard cap on this bot's open mirrored positions
    max_pct_per_trader: float = 0.10    # cap on total equity allocated to one tracked trader


class RiskLimitExceeded(Exception):
    """Raised when a guardrail blocks a mirrored trade. Callers should treat
    this as 'skip this delta', never retry-until-it-fits."""


def _round_down_to_lot(raw_size: float, lot_sz: float) -> float:
    if lot_sz <= 0:
        return raw_size
    lots = math.floor(raw_size / lot_sz + 1e-9)  # epsilon guards float-division rounding
    return lots * lot_sz


def _format_size(size: float, lot_sz: float) -> str:
    # Match lot_sz's own decimal precision (e.g. lot_sz "0.01" -> 2 decimals)
    # so we never emit more precision than the instrument accepts.
    lot_str = f"{lot_sz:.10f}".rstrip("0")
    decimals = len(lot_str.split(".")[1]) if "." in lot_str else 0
    return f"{size:.{decimals}f}"


def size_order(*, equity_usd: float, mark_price: float, ct_val: float,
               lot_sz: float, min_sz: float, limits: RiskLimits,
               open_position_count: int, allocated_to_trader_pct: float) -> str:
    """Return an order size in CONTRACTS (as a string) for a new mirrored SWAP
    position - not base-currency units. OKX swap order sizes are contract
    counts; converting a USD notional to contracts requires the instrument's
    ctVal (contract face value), and the result must be rounded down to a
    multiple of lotSz and be at least minSz - a raw notional/price division
    (this function's original implementation) silently produces an invalid
    size on almost every real instrument.

    Raises RiskLimitExceeded if a guardrail blocks the trade, including the
    case where the computed size rounds down below the instrument's minimum
    order size (a real, expected outcome for small accounts on expensive
    instruments at a small allocation_pct - not a bug to work around)."""
    if open_position_count >= limits.max_concurrent_positions:
        raise RiskLimitExceeded(
            f"max_concurrent_positions ({limits.max_concurrent_positions}) reached"
        )
    if allocated_to_trader_pct >= limits.max_pct_per_trader:
        raise RiskLimitExceeded(
            f"max_pct_per_trader ({limits.max_pct_per_trader:.0%}) reached for this trader"
        )
    if equity_usd <= 0 or mark_price <= 0 or ct_val <= 0:
        raise RiskLimitExceeded("non-positive equity, mark price, or contract value")

    notional_usd = equity_usd * limits.allocation_pct
    raw_contracts = notional_usd / (ct_val * mark_price)
    sized_contracts = _round_down_to_lot(raw_contracts, lot_sz)

    if sized_contracts < min_sz:
        raise RiskLimitExceeded(
            f"computed size ({sized_contracts}) for this trade is below the "
            f"instrument's minimum order size ({min_sz}) - increase "
            f"--allocation-pct or accept that this instrument gets skipped"
        )
    return _format_size(sized_contracts, lot_sz)
