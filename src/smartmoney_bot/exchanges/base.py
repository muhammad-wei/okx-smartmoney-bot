"""Exchange adapter interface.

Only OKX is implemented today. Binance has no public smart-money/leaderboard
API to build a strategy signal on (only an unofficial, reverse-engineered
internal endpoint), and its commission/attribution mechanism (the "Link
Program") is gated to institutional partners with 20,000+ existing users, not
self-serve like OKX's AI Builder Program - so a Binance adapter today would
have no signal source and earn no commission regardless.

This interface exists so a Binance (or other exchange) adapter *can* be added
later without reworking the strategy/signal layers above it. It is not itself
a half-built Binance integration - there is deliberately no BinanceAdapter
class anywhere in this project yet.
"""
from typing import Protocol


class ExchangeAdapter(Protocol):
    def get_account_config(self) -> dict: ...

    def get_account_balance(self, ccy: str = None) -> dict: ...

    def get_positions(self, inst_type: str = None, inst_id: str = None) -> dict: ...

    def get_ticker(self, inst_id: str) -> dict: ...

    def get_instruments(self, inst_type: str, inst_id: str = None) -> dict: ...

    def place_order(self, *, inst_id: str, td_mode: str, side: str, ord_type: str,
                     sz: str, px: str = None, pos_side: str = None,
                     reduce_only: bool = False, cl_ord_id: str = None) -> dict: ...

    def close_position(self, *, inst_id: str, mgn_mode: str, pos_side: str = None,
                        cl_ord_id: str = None) -> dict: ...
