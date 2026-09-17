"""CLI entrypoint: python -m smartmoney_bot run [options]"""
import argparse
import sys
import time
from collections import defaultdict
from typing import Dict

from smartmoney_bot.config import (
    DEFAULT_AI_BUILDER_CODE,
    load_okx_credentials,
    validate_ai_builder_code,
)
from smartmoney_bot.exchanges.okx.adapter import OKXAdapter
from smartmoney_bot.risk import RiskLimitExceeded, RiskLimits
from smartmoney_bot.signals.smart_money import PositionTracker, TraderFilter, select_traders
from smartmoney_bot.strategy.mirror import MirrorContext, MirrorSkipped, mirror_delta


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="smartmoney_bot")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the smart-money mirror strategy loop")
    run.add_argument("--traders", type=int, default=5, help="Number of top traders to track")
    run.add_argument("--sort-by", choices=["pnl", "pnlRatio"], default="pnlRatio")
    run.add_argument("--period", choices=["3", "7", "30", "90"], default="30")
    run.add_argument("--min-win-rate", default=None, help="0~1, e.g. 0.6")
    run.add_argument("--max-drawdown", default=None, help="0~1, e.g. 0.4")
    run.add_argument("--allocation-pct", type=float, default=0.02,
                      help="Fraction of own equity to allocate per mirrored trade")
    run.add_argument("--max-concurrent-positions", type=int, default=5)
    run.add_argument("--max-pct-per-trader", type=float, default=0.10)
    run.add_argument("--poll-interval", type=int, default=60, help="Seconds between polls")
    run.add_argument("--ai-builder-code", default=DEFAULT_AI_BUILDER_CODE,
                      help="Not a secret - override only if you're running your own fork "
                           "under your own AI Builder Code.")
    run.add_argument("--live", action="store_true",
                      help="Place real orders. Without this flag, every order is simulated "
                           "(x-simulated-trading header) and touches no real funds.")
    run.add_argument("--confirm-live-order", action="store_true",
                      help="Required together with --live before any real-money order is sent.")
    return parser


def get_equity_usd(adapter: OKXAdapter) -> float:
    resp = adapter.get_account_balance()
    if resp.get("code") != "0" or not resp.get("data"):
        raise RuntimeError(f"account balance call failed: {resp}")
    return float(resp["data"][0].get("totalEq", 0) or 0)


def get_account_pos_mode(adapter: OKXAdapter) -> str:
    """This account's OWN position mode - never assume, and never copy a
    source trader's posSide directly (their account's mode can differ from
    ours; forwarding their raw value caused OKX error 51000 in practice)."""
    resp = adapter.get_account_config()
    rows = resp.get("data") or []
    if resp.get("code") != "0" or not rows:
        raise RuntimeError(f"account config call failed: {resp}")
    return rows[0].get("posMode", "net_mode")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "run":
        return 1

    try:
        ai_builder_code = validate_ai_builder_code(args.ai_builder_code)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.live and not args.confirm_live_order:
        print(
            "Refusing to run with --live but without --confirm-live-order. "
            "This exists so you can't accidentally place real-money orders.",
            file=sys.stderr,
        )
        return 1

    simulated = not args.live
    try:
        credentials = load_okx_credentials()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    adapter = OKXAdapter(credentials, ai_builder_code, simulated=simulated)

    trader_filter = TraderFilter(
        sort_by=args.sort_by,
        period=args.period,
        min_win_rate=args.min_win_rate,
        max_drawdown=args.max_drawdown,
        trader_count=args.traders,
    )
    limits = RiskLimits(
        allocation_pct=args.allocation_pct,
        max_concurrent_positions=args.max_concurrent_positions,
        max_pct_per_trader=args.max_pct_per_trader,
    )

    print(f"Mode: {'LIVE' if args.live else 'SIMULATED'} | AI Builder Code: {ai_builder_code}")

    account_pos_mode = get_account_pos_mode(adapter)
    print(f"Account position mode: {account_pos_mode}")

    author_ids = select_traders(adapter, trader_filter)
    print(f"Tracking {len(author_ids)} traders: {author_ids}")

    tracker = PositionTracker()
    # In-memory bookkeeping of this bot's own mirrored notional per source trader.
    # OKX doesn't tag which trader a position mirrors, so this process is the only
    # record of that mapping - it resets on restart (see PositionTracker's note).
    mirrored_notional_by_trader: Dict[str, Dict[str, float]] = defaultdict(dict)

    def open_position_count() -> int:
        return sum(len(v) for v in mirrored_notional_by_trader.values())

    try:
        while True:
            try:
                equity_usd = get_equity_usd(adapter)
            except Exception as exc:  # noqa: BLE001 - a network blip must not kill the process
                print(f"Could not fetch account equity this cycle, skipping: {exc}")
                time.sleep(args.poll_interval)
                continue

            for author_id in author_ids:
                try:
                    deltas = tracker.poll(adapter, author_id)
                except Exception as exc:  # noqa: BLE001 - same: one trader's poll failing
                    print(f"[{author_id}] could not poll positions, skipping this cycle: {exc}")
                    continue

                for delta in deltas:
                    print(f"[{author_id}] {delta.kind} {delta.inst_id}")
                    trader_notional = sum(mirrored_notional_by_trader[author_id].values())
                    context = MirrorContext(
                        equity_usd=equity_usd,
                        open_position_count=open_position_count(),
                        allocated_to_trader_pct=(
                            (trader_notional / equity_usd) if equity_usd else 1.0
                        ),
                        account_pos_mode=account_pos_mode,
                    )
                    try:
                        result = mirror_delta(adapter, delta, context, limits)
                        print(f"  -> order result: {result}")
                        if result.get("code") != "0":
                            # OKX rejected the order (e.g. lot size, insufficient
                            # margin) - the call succeeded, the trade didn't.
                            # Bookkeeping must not record a position that was
                            # never actually opened.
                            print("  -> order rejected by OKX, not recording a position")
                        elif delta.kind == "closed":
                            mirrored_notional_by_trader[author_id].pop(delta.inst_id, None)
                        else:
                            mirrored_notional_by_trader[author_id][delta.inst_id] = (
                                equity_usd * limits.allocation_pct
                            )
                    except (RiskLimitExceeded, MirrorSkipped) as exc:
                        print(f"  -> skipped: {exc}")
                    except Exception as exc:  # noqa: BLE001 - one bad delta must not kill the loop
                        print(f"  -> unexpected error mirroring this delta, skipping it: {exc}")
            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        print("\nStopping (Ctrl+C) - no new mirrored trades will be placed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
