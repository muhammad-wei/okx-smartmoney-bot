# Known-answer signing vectors copied from okx/builder-integration-demo,
# demos/openapi-user/test_strategy_demo.py (ref github-main). This is the only
# regression net on the signing code copied verbatim into exchanges/okx/client.py -
# if this ever fails, the copied client was altered in transcription.
import json
from unittest.mock import patch

from smartmoney_bot.exchanges.okx import client


class FakeResponse:
    status_code = 200
    text = "{}"

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def test_known_answer_signing_vectors():
    secret = "mock-secret"
    timestamp = "2020-12-08T09:08:57.715Z"
    path = "/api/v5/account/balance"

    assert client._sign(secret, timestamp, "GET", path, "") == (
        "tpQYvXdaAfU8ae6zI1rJ2xVcyMIk9BKWK/fysaanweQ="
    )
    assert client._sign(secret, timestamp, "GET", path + "?ccy=BTC", "") == (
        "pS6nHuBl6Qc9S0h+soCkCVHaVHZzS19KqFpeI/doTlE="
    )


def test_signature_is_computed_over_the_body_actually_sent():
    captured = {}

    def fake_post(url, headers=None, data=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = data
        return FakeResponse({"code": "0", "data": [{"ordId": "1"}]})

    timestamp = "2026-08-06T00:00:00.000Z"
    with patch.object(client, "_now_iso_ms", return_value=timestamp):
        with patch.object(client.requests, "post", side_effect=fake_post):
            result = client.place_order(
                "https://www.okx.com",
                "demo-key",
                "demo-secret",
                "demo-pass",
                "BTC-USDT",
                "cash",
                "buy",
                "limit",
                "0.001",
                px="60000",
                ai_builder_code="ABC123",
                simulated=True,
            )

    sent_body = json.loads(captured["body"])
    assert result["code"] == "0"
    assert captured["headers"]["x-simulated-trading"] == "1"
    assert sent_body["tag"] == "ABC123"

    expected_sign = client._sign(
        "demo-secret", timestamp, "POST", client.PATH_TRADE_ORDER, captured["body"],
    )
    assert captured["headers"]["OK-ACCESS-SIGN"] == expected_sign


def test_place_order_rejects_missing_ai_builder_code():
    try:
        client.place_order(
            "https://www.okx.com", "k", "s", "p",
            "BTC-USDT", "cash", "buy", "limit", "0.001",
            ai_builder_code="",
        )
        assert False, "expected ValueError for missing AI Builder Code"
    except ValueError:
        pass


def test_ai_builder_code_format_validation():
    assert client._require_ai_builder_code("53461cb5b603ABDE") == "53461cb5b603ABDE"
    for bad in ("", "has-a-dash", "x" * 17, "<AI_BUILDER_CODE>"):
        try:
            client._require_ai_builder_code(bad)
            assert False, f"expected ValueError for {bad!r}"
        except ValueError:
            pass


# -- GET retry ----------------------------------------------------------------
# A dropped SSL connection (requests.exceptions.SSLError, a subclass of
# ConnectionError) killed an earlier run entirely (see docs/SAFETY.md). These
# lock in the fix: bounded retry on read-only GETs, and confirm it never
# extends to order-producing POSTs, where retrying a lost response risks a
# duplicate real-money order.

def test_get_with_retry_recovers_after_transient_connection_errors():
    calls = {"n": 0}

    def flaky_get(url, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise client.requests.exceptions.ConnectionError("dropped")
        return FakeResponse({"code": "0", "data": [{"totalEq": "100"}]})

    with patch.object(client, "time") as fake_time:
        with patch.object(client.requests, "get", side_effect=flaky_get):
            resp = client._get_with_retry("https://www.okx.com/x", {}, 10)

    assert resp.json()["code"] == "0"
    assert calls["n"] == 3
    assert fake_time.sleep.call_count == 2  # slept between the 2 failed attempts only


def test_get_with_retry_raises_after_exhausting_attempts():
    def always_fails(url, headers=None, timeout=None):
        raise client.requests.exceptions.ConnectionError("still dropped")

    with patch.object(client, "time"):
        with patch.object(client.requests, "get", side_effect=always_fails):
            try:
                client._get_with_retry("https://www.okx.com/x", {}, 10)
                assert False, "expected ConnectionError to propagate"
            except client.requests.exceptions.ConnectionError:
                pass


def test_place_order_never_retries_on_connection_error():
    calls = {"n": 0}

    def always_fails(url, headers=None, data=None, timeout=None):
        calls["n"] += 1
        raise client.requests.exceptions.ConnectionError("dropped")

    with patch.object(client.requests, "post", side_effect=always_fails):
        try:
            client.place_order(
                "https://www.okx.com", "k", "s", "p",
                "BTC-USDT", "cash", "buy", "limit", "0.001",
                ai_builder_code="ABC123",
            )
            assert False, "expected ConnectionError to propagate"
        except client.requests.exceptions.ConnectionError:
            pass
    assert calls["n"] == 1  # never retried - a lost response must never risk a duplicate order
