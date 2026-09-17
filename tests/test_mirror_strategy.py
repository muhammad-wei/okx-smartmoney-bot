from smartmoney_bot.risk import RiskLimitExceeded, RiskLimits
from smartmoney_bot.signals.smart_money import Position, PositionDelta, PositionTracker
from smartmoney_bot.strategy.mirror import MirrorContext, mirror_delta, pos_side_for, side_for


def make_position(inst_id="BTC-USDT-SWAP", pos_side="long", size="1.0", avg_px="100"):
    return Position(
        pos_id="p1", inst_id=inst_id, pos_side=pos_side,
        size=float(size), avg_px=float(avg_px), lever="3",
    )


# -- PositionTracker diffing -------------------------------------------------

class FakeAdapter:
    def __init__(self, position_rows, ticker_last="100", orders=None,
                 ct_val="1", lot_sz="1", min_sz="1"):
        self._position_rows = position_rows
        self._ticker_last = ticker_last
        self._ct_val = ct_val
        self._lot_sz = lot_sz
        self._min_sz = min_sz
        self.orders = orders if orders is not None else []

    def get_trader_positions(self, author_id):
        # Real OKX shape (verified live): a one-element list wrapping "posData",
        # or an empty list when the trader has no open positions.
        if not self._position_rows:
            return {"code": "0", "data": []}
        return {"code": "0", "data": [{"posData": self._position_rows}]}

    def get_ticker(self, inst_id):
        return {"data": [{"last": self._ticker_last}]}

    def get_instruments(self, inst_type, inst_id=None):
        return {"code": "0", "data": [
            {"instId": inst_id, "ctVal": self._ct_val, "lotSz": self._lot_sz,
             "minSz": self._min_sz},
        ]}

    def place_order(self, **kwargs):
        self.orders.append(("place", kwargs))
        return {"code": "0", "data": [{"ordId": "1", "tag": "TEST123"}]}

    def close_position(self, **kwargs):
        self.orders.append(("close", kwargs))
        return {"code": "0", "data": [{}]}


def test_tracker_detects_opened_resized_closed():
    tracker = PositionTracker()

    row_v1 = {"posId": "p1", "instId": "BTC-USDT-SWAP", "posSide": "long",
              "pos": "1.0", "avgPx": "100", "lever": "3"}
    adapter1 = FakeAdapter([row_v1])
    deltas1 = tracker.poll(adapter1, "trader-1")
    assert len(deltas1) == 1 and deltas1[0].kind == "opened"

    row_v2 = dict(row_v1, pos="2.0")
    adapter2 = FakeAdapter([row_v2])
    deltas2 = tracker.poll(adapter2, "trader-1")
    assert len(deltas2) == 1 and deltas2[0].kind == "resized"

    adapter3 = FakeAdapter([])
    deltas3 = tracker.poll(adapter3, "trader-1")
    assert len(deltas3) == 1 and deltas3[0].kind == "closed"


# -- side_for -----------------------------------------------------------------

def test_side_for_open_long_is_buy():
    delta = PositionDelta("t1", "BTC-USDT-SWAP", "opened", make_position(pos_side="long"), None)
    assert side_for(delta) == "buy"


def test_side_for_open_short_is_sell():
    delta = PositionDelta("t1", "BTC-USDT-SWAP", "opened", make_position(pos_side="short"), None)
    assert side_for(delta) == "sell"


def test_side_for_close_long_is_sell():
    delta = PositionDelta("t1", "BTC-USDT-SWAP", "closed", None, make_position(pos_side="long"))
    assert side_for(delta) == "sell"


# -- pos_side_for ---------------------------------------------------------------
# Regression tests for the bug found on a real live run: forwarding the SOURCE
# trader's raw posSide into MY OWN order produced OKX error 51000 "Parameter
# posSide error" on almost every mirrored trade, because my account's position
# mode differed from theirs. pos_side_for must derive the value from MY OWN
# account_pos_mode, never from delta.position.pos_side directly.

def test_pos_side_for_net_mode_is_always_net_regardless_of_source_trader():
    for pos_side in ("long", "short", "net"):
        delta = PositionDelta("t1", "BTC-USDT-SWAP", "opened", make_position(pos_side=pos_side), None)
        assert pos_side_for(delta, "net_mode") == "net"


def test_pos_side_for_long_short_mode_open_long():
    delta = PositionDelta("t1", "BTC-USDT-SWAP", "opened", make_position(pos_side="long"), None)
    assert pos_side_for(delta, "long_short_mode") == "long"


def test_pos_side_for_long_short_mode_open_short():
    delta = PositionDelta("t1", "BTC-USDT-SWAP", "opened", make_position(pos_side="short"), None)
    assert pos_side_for(delta, "long_short_mode") == "short"


def test_pos_side_for_long_short_mode_close():
    delta = PositionDelta("t1", "BTC-USDT-SWAP", "closed", None, make_position(pos_side="long"))
    assert pos_side_for(delta, "long_short_mode") == "long"


# -- mirror_delta ---------------------------------------------------------------

def test_mirror_delta_opened_places_order_with_computed_size_and_net_pos_side():
    delta = PositionDelta("t1", "BTC-USDT-SWAP", "opened", make_position(pos_side="long"), None)
    adapter = FakeAdapter([], ticker_last="100")
    limits = RiskLimits(allocation_pct=0.02)
    context = MirrorContext(
        equity_usd=10_000, open_position_count=0, allocated_to_trader_pct=0.0,
        account_pos_mode="net_mode",
    )

    result = mirror_delta(adapter, delta, context, limits)

    assert result["code"] == "0"
    assert len(adapter.orders) == 1
    kind, kwargs = adapter.orders[0]
    assert kind == "place"
    assert kwargs["side"] == "buy"
    assert kwargs["pos_side"] == "net"  # never the source trader's raw "long"
    assert float(kwargs["sz"]) == 2.0  # 2% of 10,000 / 100


def test_mirror_delta_opened_uses_long_short_pos_side_in_that_account_mode():
    delta = PositionDelta("t1", "BTC-USDT-SWAP", "opened", make_position(pos_side="short"), None)
    adapter = FakeAdapter([], ticker_last="100")
    limits = RiskLimits(allocation_pct=0.02)
    context = MirrorContext(
        equity_usd=10_000, open_position_count=0, allocated_to_trader_pct=0.0,
        account_pos_mode="long_short_mode",
    )

    result = mirror_delta(adapter, delta, context, limits)

    assert result["code"] == "0"
    kind, kwargs = adapter.orders[0]
    assert kwargs["side"] == "sell"
    assert kwargs["pos_side"] == "short"


def test_mirror_delta_closed_calls_close_position_not_place_order():
    delta = PositionDelta("t1", "BTC-USDT-SWAP", "closed", None, make_position(pos_side="long"))
    adapter = FakeAdapter([])
    limits = RiskLimits()
    context = MirrorContext(equity_usd=10_000, open_position_count=1, allocated_to_trader_pct=0.05)

    result = mirror_delta(adapter, delta, context, limits)

    assert result["code"] == "0"
    assert adapter.orders[0][0] == "close"


def test_mirror_delta_respects_risk_limits():
    delta = PositionDelta("t1", "BTC-USDT-SWAP", "opened", make_position(pos_side="long"), None)
    adapter = FakeAdapter([], ticker_last="100")
    limits = RiskLimits(max_concurrent_positions=1)
    context = MirrorContext(equity_usd=10_000, open_position_count=1, allocated_to_trader_pct=0.0)

    try:
        mirror_delta(adapter, delta, context, limits)
        assert False, "expected RiskLimitExceeded"
    except RiskLimitExceeded:
        pass
    assert adapter.orders == []
