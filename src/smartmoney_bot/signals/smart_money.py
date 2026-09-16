"""Smart-money trader discovery and position-change detection.

Polls OKX's Smart Money leaderboard to select a tracked-trader set, then polls
each tracked trader's current positions and reports deltas (opened / resized /
closed) against the last-seen snapshot. No push/WS support is documented for
these endpoints, so this is intentionally a simple poll loop, not a streaming
client - don't build one until there's evidence OKX supports it here.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class TraderFilter:
    sort_by: str = "pnlRatio"          # "pnl" or "pnlRatio"
    period: str = "30"                 # "3" | "7" | "30" | "90" (days)
    min_win_rate: Optional[str] = None  # 0~1
    max_drawdown: Optional[str] = None  # 0~1 (negative in OKX's response, e.g. "-0.35")
    min_aum: Optional[str] = None      # USD
    trader_count: int = 5


@dataclass
class Position:
    pos_id: str
    inst_id: str
    pos_side: str
    size: float
    avg_px: float
    lever: str

    @classmethod
    def from_api(cls, row: dict) -> "Position":
        return cls(
            pos_id=row["posId"],
            inst_id=row["instId"],
            pos_side=row.get("posSide", "net"),
            size=float(row["pos"]),
            avg_px=float(row["avgPx"]),
            lever=row.get("lever", "1"),
        )


@dataclass
class PositionDelta:
    author_id: str
    inst_id: str
    kind: str  # "opened" | "resized" | "closed"
    position: Optional[Position]
    previous: Optional[Position]


def _unwrap_leaderboard_rows(resp: dict) -> List[dict]:
    """The raw REST response nests rows one level deeper than you'd guess:
    {"code": "0", "data": {"data": [...rows...], "updateTime": ..., "pagination": ...}}
    (verified live - see docs/SAFETY.md). Not resp["data"] directly."""
    data = resp.get("data")
    if isinstance(data, dict):
        return data.get("data") or []
    return data or []


def _unwrap_position_rows(resp: dict) -> List[dict]:
    """The raw REST response wraps rows in a one-element list containing a
    "posData" key: {"code": "0", "data": [{"posData": [...rows...]}]}
    (verified live - see docs/SAFETY.md). Not resp["data"] directly."""
    outer = resp.get("data") or []
    if not outer:
        return []
    first = outer[0] if isinstance(outer, list) else outer
    if isinstance(first, dict):
        if "posData" in first:
            return first.get("posData") or []
        return [first]  # already a bare row, not a wrapper
    return outer if isinstance(outer, list) else []


def select_traders(adapter, trader_filter: TraderFilter) -> List[str]:
    """Return authorIds matching the configured filter, ranked by the API."""
    resp = adapter.get_leaderboard(
        sort_by=trader_filter.sort_by,
        period=trader_filter.period,
        min_win_rate=trader_filter.min_win_rate,
        max_drawdown=trader_filter.max_drawdown,
        min_aum=trader_filter.min_aum,
        limit=str(trader_filter.trader_count),
    )
    if resp.get("code") != "0":
        raise RuntimeError(f"leaderboard call failed: {resp}")
    return [row["authorId"] for row in _unwrap_leaderboard_rows(resp)]


class PositionTracker:
    """Keeps last-seen positions per trader and yields deltas on each poll.
    All state is in-process memory - it resets if the bot restarts, which is
    fine (a restart just re-baselines against each trader's current book;
    it won't retroactively mirror positions opened while the bot was down)."""

    def __init__(self):
        self._last_seen: Dict[str, Dict[str, Position]] = {}

    def poll(self, adapter, author_id: str) -> List[PositionDelta]:
        resp = adapter.get_trader_positions(author_id=author_id)
        if resp.get("code") != "0":
            raise RuntimeError(f"trader-positions call failed for {author_id}: {resp}")

        current = {row["posId"]: Position.from_api(row) for row in _unwrap_position_rows(resp)}
        previous = self._last_seen.get(author_id, {})

        deltas: List[PositionDelta] = []
        for pos_id, pos in current.items():
            prev = previous.get(pos_id)
            if prev is None:
                deltas.append(PositionDelta(author_id, pos.inst_id, "opened", pos, None))
            elif prev.size != pos.size:
                deltas.append(PositionDelta(author_id, pos.inst_id, "resized", pos, prev))
        for pos_id, prev in previous.items():
            if pos_id not in current:
                deltas.append(PositionDelta(author_id, prev.inst_id, "closed", None, prev))

        self._last_seen[author_id] = current
        return deltas
