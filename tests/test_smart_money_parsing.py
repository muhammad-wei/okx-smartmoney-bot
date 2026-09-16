# Regression tests for the three OKX Smart Money response envelopes. Each
# fixture below is trimmed from a REAL live response captured while debugging
# (see docs/SAFETY.md) - not guessed. Each endpoint nests its row data
# differently; these tests exist so that never gets silently reassumed wrong.
from smartmoney_bot.signals.smart_money import (
    _unwrap_leaderboard_rows,
    _unwrap_position_rows,
    select_traders,
)

# GET /api/v5/orbit/public/leaderboard - rows nested under data.data
LEADERBOARD_RESPONSE = {
    "code": "0",
    "msg": "",
    "data": {
        "data": [
            {
                "authorId": "872836768625012736",
                "nickName": "tal***@proton.me",
                "pnl": "12779011.72",
                "pnlRatio": "0.6214",
                "asset": "33344826.84",
                "winRate": "0.5959",
                "maxDrawdown": "-0.3591",
            },
        ],
        "updateTime": "202609142340",
    },
}

# GET /api/v5/orbit/public/position-current - rows nested under data[0].posData
POSITION_CURRENT_RESPONSE = {
    "code": "0",
    "msg": "",
    "data": [
        {
            "posData": [
                {
                    "posId": "1707481186861387777",
                    "instId": "BTC-USD-SWAP",
                    "instType": "SWAP",
                    "posSide": "net",
                    "pos": "202083.8",
                    "avgPx": "76304.1707800507073451",
                    "lever": "4.5",
                },
            ],
        },
    ],
}

POSITION_CURRENT_EMPTY_RESPONSE = {"code": "0", "msg": "", "data": []}


def test_unwrap_leaderboard_rows_reaches_nested_data():
    rows = _unwrap_leaderboard_rows(LEADERBOARD_RESPONSE)
    assert len(rows) == 1
    assert rows[0]["authorId"] == "872836768625012736"


def test_unwrap_position_rows_reaches_posdata():
    rows = _unwrap_position_rows(POSITION_CURRENT_RESPONSE)
    assert len(rows) == 1
    assert rows[0]["posId"] == "1707481186861387777"
    assert rows[0]["instId"] == "BTC-USD-SWAP"


def test_unwrap_position_rows_handles_no_open_positions():
    assert _unwrap_position_rows(POSITION_CURRENT_EMPTY_RESPONSE) == []


class FakeLeaderboardAdapter:
    def __init__(self, response):
        self._response = response

    def get_leaderboard(self, **kwargs):
        return self._response


def test_select_traders_parses_real_leaderboard_shape():
    from smartmoney_bot.signals.smart_money import TraderFilter

    adapter = FakeLeaderboardAdapter(LEADERBOARD_RESPONSE)
    author_ids = select_traders(adapter, TraderFilter(trader_count=1))
    assert author_ids == ["872836768625012736"]
