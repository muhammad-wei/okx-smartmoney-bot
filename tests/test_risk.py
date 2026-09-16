import pytest

from smartmoney_bot.risk import RiskLimitExceeded, RiskLimits, size_order


def test_size_order_computes_contracts_rounded_to_lot_size():
    limits = RiskLimits(allocation_pct=0.02)
    # $10,000 equity * 2% = $200 notional. ctVal=0.01 ETH, mark=$2,000/ETH
    # -> raw contracts = 200 / (0.01 * 2000) = 10.0 exactly.
    size = size_order(
        equity_usd=10_000, mark_price=2_000, ct_val=0.01, lot_sz=0.01, min_sz=0.01,
        limits=limits, open_position_count=0, allocated_to_trader_pct=0.0,
    )
    assert float(size) == pytest.approx(10.0)


def test_size_order_rounds_down_to_lot_size():
    limits = RiskLimits(allocation_pct=0.02)
    # raw contracts = 200 / (0.01 * 2000) = 10.0, but lot_sz=3 -> round down to 9
    size = size_order(
        equity_usd=10_000, mark_price=2_000, ct_val=0.01, lot_sz=3, min_sz=1,
        limits=limits, open_position_count=0, allocated_to_trader_pct=0.0,
    )
    assert float(size) == pytest.approx(9.0)


def test_size_order_blocks_when_below_min_size():
    limits = RiskLimits(allocation_pct=0.02)
    # tiny equity -> raw contracts far below min_sz
    with pytest.raises(RiskLimitExceeded):
        size_order(
            equity_usd=10, mark_price=2_000, ct_val=0.01, lot_sz=0.01, min_sz=1,
            limits=limits, open_position_count=0, allocated_to_trader_pct=0.0,
        )


def test_size_order_blocks_at_max_concurrent_positions():
    limits = RiskLimits(max_concurrent_positions=3)
    with pytest.raises(RiskLimitExceeded):
        size_order(
            equity_usd=10_000, mark_price=100, ct_val=1, lot_sz=1, min_sz=1,
            limits=limits, open_position_count=3, allocated_to_trader_pct=0.0,
        )


def test_size_order_blocks_at_max_pct_per_trader():
    limits = RiskLimits(max_pct_per_trader=0.10)
    with pytest.raises(RiskLimitExceeded):
        size_order(
            equity_usd=10_000, mark_price=100, ct_val=1, lot_sz=1, min_sz=1,
            limits=limits, open_position_count=0, allocated_to_trader_pct=0.10,
        )


def test_size_order_blocks_on_non_positive_inputs():
    limits = RiskLimits()
    with pytest.raises(RiskLimitExceeded):
        size_order(
            equity_usd=0, mark_price=100, ct_val=1, lot_sz=1, min_sz=1,
            limits=limits, open_position_count=0, allocated_to_trader_pct=0.0,
        )
    with pytest.raises(RiskLimitExceeded):
        size_order(
            equity_usd=10_000, mark_price=0, ct_val=1, lot_sz=1, min_sz=1,
            limits=limits, open_position_count=0, allocated_to_trader_pct=0.0,
        )
    with pytest.raises(RiskLimitExceeded):
        size_order(
            equity_usd=10_000, mark_price=100, ct_val=0, lot_sz=1, min_sz=1,
            limits=limits, open_position_count=0, allocated_to_trader_pct=0.0,
        )
