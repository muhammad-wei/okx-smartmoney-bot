"""Binds the copied OKX signing client (client.py) to this bot's credentials
and configuration, and always injects the configured AI Builder Code on every
order-producing call. Nothing outside this file constructs a raw client call
directly - the strategy layer only ever talks to an ExchangeAdapter.
"""
from smartmoney_bot.config import OkxCredentials
from smartmoney_bot.exchanges.okx import client


class OKXAdapter:
    def __init__(self, credentials: OkxCredentials, ai_builder_code: str,
                 base_url: str = "https://www.okx.com", simulated: bool = True):
        self._creds = credentials
        self._ai_builder_code = ai_builder_code
        self._base_url = base_url
        self._simulated = simulated

    # -- account / market data ------------------------------------------------

    def get_account_config(self) -> dict:
        return client.get_account_config(
            self._base_url, self._creds.api_key, self._creds.secret_key,
            self._creds.passphrase, simulated=self._simulated,
        )

    def get_account_balance(self, ccy: str = None) -> dict:
        return client.get_account_balance(
            self._base_url, self._creds.api_key, self._creds.secret_key,
            self._creds.passphrase, ccy=ccy, simulated=self._simulated,
        )

    def get_positions(self, inst_type: str = None, inst_id: str = None) -> dict:
        return client.get_positions(
            self._base_url, self._creds.api_key, self._creds.secret_key,
            self._creds.passphrase, inst_type=inst_type, inst_id=inst_id,
            simulated=self._simulated,
        )

    def get_ticker(self, inst_id: str) -> dict:
        return client.get_ticker(self._base_url, inst_id, simulated=self._simulated)

    def get_instruments(self, inst_type: str, inst_id: str = None) -> dict:
        return client.get_instruments(
            self._base_url, inst_type, inst_id, simulated=self._simulated,
        )

    # -- smart money (read-only) -----------------------------------------------

    def get_leaderboard(self, *, sort_by: str, period: str, min_pnl: str = None,
                         min_win_rate: str = None, max_drawdown: str = None,
                         min_aum: str = None, after: str = None,
                         before: str = None, limit: str = None) -> dict:
        return client.get_leaderboard(
            self._base_url, self._creds.api_key, self._creds.secret_key,
            self._creds.passphrase, sort_by=sort_by, period=period,
            min_pnl=min_pnl, min_win_rate=min_win_rate, max_drawdown=max_drawdown,
            min_aum=min_aum, after=after, before=before, limit=limit,
            simulated=self._simulated,
        )

    def get_trader_positions(self, *, author_id: str, inst_ccy: str = None) -> dict:
        return client.get_trader_positions(
            self._base_url, self._creds.api_key, self._creds.secret_key,
            self._creds.passphrase, author_id=author_id, inst_ccy=inst_ccy,
            simulated=self._simulated,
        )

    def get_trader_positions_history(self, *, author_id: str, inst_ccy: str = None,
                                      after: str = None, before: str = None,
                                      limit: str = None) -> dict:
        return client.get_trader_positions_history(
            self._base_url, self._creds.api_key, self._creds.secret_key,
            self._creds.passphrase, author_id=author_id, inst_ccy=inst_ccy,
            after=after, before=before, limit=limit, simulated=self._simulated,
        )

    # -- order-producing (attribution-mandatory) -------------------------------

    def place_order(self, *, inst_id: str, td_mode: str, side: str, ord_type: str,
                     sz: str, px: str = None, pos_side: str = None,
                     reduce_only: bool = False, cl_ord_id: str = None) -> dict:
        return client.place_order(
            self._base_url, self._creds.api_key, self._creds.secret_key,
            self._creds.passphrase, inst_id=inst_id, td_mode=td_mode, side=side,
            ord_type=ord_type, sz=sz, px=px, pos_side=pos_side,
            reduce_only=reduce_only, cl_ord_id=cl_ord_id,
            ai_builder_code=self._ai_builder_code, simulated=self._simulated,
        )

    def close_position(self, *, inst_id: str, mgn_mode: str, pos_side: str = None,
                        cl_ord_id: str = None) -> dict:
        return client.close_position(
            self._base_url, self._creds.api_key, self._creds.secret_key,
            self._creds.passphrase, inst_id=inst_id, mgn_mode=mgn_mode,
            pos_side=pos_side, cl_ord_id=cl_ord_id,
            ai_builder_code=self._ai_builder_code, simulated=self._simulated,
        )
