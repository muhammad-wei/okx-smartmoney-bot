# Copied verbatim from okx/builder-integration-demo, demos/openapi-user/okx_openapi_client.py
# (ref github-main). Do not hand-roll HMAC signing - this is the demo's own signing client.
# The three orbit/* functions at the bottom are NEW, not part of the demo: they follow the
# exact same request/signing pattern to reach OKX's Smart Money endpoints (verified live via
# the account's own OKX MCP connection before this file was written - see docs/SAFETY.md).
import base64
import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

GET_RETRY_ATTEMPTS = 3
GET_RETRY_BACKOFF_SECONDS = 0.5

PATH_ACCOUNT_BALANCE = "/api/v5/account/balance"
PATH_ACCOUNT_CONFIG = "/api/v5/account/config"
PATH_ACCOUNT_POSITIONS = "/api/v5/account/positions"
PATH_MARKET_TICKER = "/api/v5/market/ticker"
PATH_PUBLIC_INSTRUMENTS = "/api/v5/public/instruments"
PATH_TRADE_CLOSE_POSITION = "/api/v5/trade/close-position"
PATH_TRADE_ORDER = "/api/v5/trade/order"
AI_BUILDER_CODE_PATTERN = re.compile(r"^[A-Za-z0-9]{1,16}$")


def _now_iso_ms() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _sign(secret_key: str, timestamp: str, method: str, request_path: str, body: str) -> str:
    prehash = f"{timestamp}{method.upper()}{request_path}{body}"
    digest = hmac.new(secret_key.encode(), prehash.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _get_with_retry(url: str, headers: dict, timeout: int) -> requests.Response:
    """GET only - place_order/close_position never retry automatically, so a
    lost response can never risk a duplicate real-money order. Retries a
    short, bounded number of times on a dropped connection (ConnectionError,
    which includes requests' SSLError - a dropped SSL connection killed an
    earlier run entirely; see docs/SAFETY.md) or a timeout, so one blip
    doesn't cost a full --poll-interval wait before the next attempt."""
    last_exc = None
    for attempt in range(GET_RETRY_ATTEMPTS):
        try:
            return requests.get(url, headers=headers, timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_exc = exc
            if attempt < GET_RETRY_ATTEMPTS - 1:
                time.sleep(GET_RETRY_BACKOFF_SECONDS * (attempt + 1))
    raise last_exc


def _parse(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {"_http_status": resp.status_code, "_non_json_body": resp.text[:300]}


def _headers(api_key: str, secret_key: str, passphrase: str, method: str,
             request_path: str, body: str, simulated: bool) -> dict:
    ts = _now_iso_ms()
    headers = {
        "OK-ACCESS-KEY": api_key,
        "OK-ACCESS-SIGN": _sign(secret_key, ts, method, request_path, body),
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": passphrase,
        "Content-Type": "application/json",
    }
    if simulated:
        headers["x-simulated-trading"] = "1"
    return headers


def _public_headers(simulated: bool) -> dict:
    headers = {"Content-Type": "application/json"}
    if simulated:
        headers["x-simulated-trading"] = "1"
    return headers


def _compact(obj: dict) -> dict:
    return {key: value for key, value in obj.items() if value not in (None, "", [])}


def _require_ai_builder_code(ai_builder_code: str) -> str:
    code = ai_builder_code or ""
    if not code or code.startswith("<"):
        raise ValueError("missing AI Builder Code")
    if not AI_BUILDER_CODE_PATTERN.match(code):
        raise ValueError("AI Builder Code must be 1-16 alphanumeric characters")
    return code


def _with_query(path: str, params: dict) -> str:
    compacted = _compact(params)
    return path + ("?" + urlencode(compacted) if compacted else "")


def _build_attach_algo_ords(tp_trigger_px: str = None, tp_ord_px: str = None,
                            tp_ord_kind: str = None, tp_trigger_px_type: str = None,
                            sl_trigger_px: str = None, sl_ord_px: str = None,
                            sl_trigger_px_type: str = None) -> list:
    attach_order = _compact({
        "tpTriggerPx": tp_trigger_px,
        "tpOrdPx": tp_ord_px,
        "tpOrdKind": tp_ord_kind,
        "tpTriggerPxType": tp_trigger_px_type,
        "slTriggerPx": sl_trigger_px,
        "slOrdPx": sl_ord_px,
        "slTriggerPxType": sl_trigger_px_type,
    })
    return [attach_order] if attach_order else []


def get_account_balance(base_url: str, api_key: str, secret_key: str, passphrase: str,
                        ccy: str = None, simulated: bool = True) -> dict:
    request_path = _with_query(PATH_ACCOUNT_BALANCE, {"ccy": ccy})
    body = ""
    headers = _headers(api_key, secret_key, passphrase, "GET", request_path, body, simulated)
    return _parse(_get_with_retry(base_url + request_path, headers, 10))


def get_account_config(base_url: str, api_key: str, secret_key: str, passphrase: str,
                       simulated: bool = True) -> dict:
    request_path = PATH_ACCOUNT_CONFIG
    body = ""
    headers = _headers(api_key, secret_key, passphrase, "GET", request_path, body, simulated)
    return _parse(_get_with_retry(base_url + request_path, headers, 10))


def get_positions(base_url: str, api_key: str, secret_key: str, passphrase: str,
                  inst_type: str = None, inst_id: str = None,
                  simulated: bool = True) -> dict:
    request_path = _with_query(PATH_ACCOUNT_POSITIONS, {
        "instType": inst_type,
        "instId": inst_id,
    })
    body = ""
    headers = _headers(api_key, secret_key, passphrase, "GET", request_path, body, simulated)
    return _parse(_get_with_retry(base_url + request_path, headers, 10))


def get_ticker(base_url: str, inst_id: str, simulated: bool = True) -> dict:
    request_path = _with_query(PATH_MARKET_TICKER, {"instId": inst_id})
    return _parse(_get_with_retry(
        base_url + request_path, _public_headers(simulated), 10,
    ))


def get_instruments(base_url: str, inst_type: str, inst_id: str,
                    simulated: bool = True) -> dict:
    request_path = _with_query(PATH_PUBLIC_INSTRUMENTS, {
        "instType": inst_type,
        "instId": inst_id,
    })
    return _parse(_get_with_retry(
        base_url + request_path, _public_headers(simulated), 10,
    ))


def place_order(base_url: str, api_key: str, secret_key: str, passphrase: str,
                inst_id: str, td_mode: str, side: str, ord_type: str, sz: str,
                px: str = None, tgt_ccy: str = None, cl_ord_id: str = None,
                tp_trigger_px: str = None, tp_ord_px: str = None,
                tp_ord_kind: str = None, tp_trigger_px_type: str = None,
                sl_trigger_px: str = None, sl_ord_px: str = None,
                sl_trigger_px_type: str = None, stp_mode: str = None,
                trade_quote_ccy: str = None, ban_amend: bool = False,
                px_amend_type: str = None,
                pos_side: str = None, reduce_only: bool = False,
                ai_builder_code: str = "",
                simulated: bool = True) -> dict:
    ai_builder_code = _require_ai_builder_code(ai_builder_code)
    attach_algo_ords = _build_attach_algo_ords(
        tp_trigger_px=tp_trigger_px,
        tp_ord_px=tp_ord_px,
        tp_ord_kind=tp_ord_kind,
        tp_trigger_px_type=tp_trigger_px_type,
        sl_trigger_px=sl_trigger_px,
        sl_ord_px=sl_ord_px,
        sl_trigger_px_type=sl_trigger_px_type,
    )
    body_obj = _compact({
        "instId": inst_id,
        "tdMode": td_mode,
        "side": side,
        "ordType": ord_type,
        "sz": sz,
        "tgtCcy": tgt_ccy,
        "px": px,
        "clOrdId": cl_ord_id,
        "stpMode": stp_mode,
        "tradeQuoteCcy": trade_quote_ccy,
        "banAmend": "true" if ban_amend else None,
        "pxAmendType": px_amend_type,
        "posSide": pos_side,
        "reduceOnly": "true" if reduce_only else None,
        "tag": ai_builder_code,
        "attachAlgoOrds": attach_algo_ords,
    })

    # Compact JSON: the same serialized string is used for both signing and sending.
    body = json.dumps(body_obj, separators=(",", ":"))
    headers = _headers(api_key, secret_key, passphrase, "POST", PATH_TRADE_ORDER, body, simulated)
    return _parse(requests.post(base_url + PATH_TRADE_ORDER, headers=headers, data=body, timeout=10))


def close_position(base_url: str, api_key: str, secret_key: str, passphrase: str,
                   inst_id: str, mgn_mode: str, pos_side: str = None,
                   auto_cxl: bool = True, cl_ord_id: str = None,
                   ai_builder_code: str = "",
                   simulated: bool = True) -> dict:
    ai_builder_code = _require_ai_builder_code(ai_builder_code)
    body_obj = _compact({
        "instId": inst_id,
        "mgnMode": mgn_mode,
        "posSide": pos_side,
        "autoCxl": str(auto_cxl).lower(),
        "clOrdId": cl_ord_id,
        "tag": ai_builder_code,
    })
    # Compact JSON: the same serialized string is used for both signing and sending.
    body = json.dumps(body_obj, separators=(",", ":"))
    headers = _headers(
        api_key, secret_key, passphrase,
        "POST", PATH_TRADE_CLOSE_POSITION, body, simulated,
    )
    return _parse(requests.post(
        base_url + PATH_TRADE_CLOSE_POSITION,
        headers=headers,
        data=body,
        timeout=10,
    ))


# ---------------------------------------------------------------------------
# NEW (not part of the demo): OKX Smart Money read endpoints.
#
# Not in OKX's official public API docs - confirmed via OKX's own open-source
# agent-trade-kit repo and this machine's bundled okx-cex-smartmoney skill,
# and verified live (via the OKX MCP connection) to return the fields parsed
# below, before this file was written. Despite "public" in the path, OKX's own
# wrapper signs these as private requests - same signing pattern as everything
# above, no new auth mechanism.
# ---------------------------------------------------------------------------

PATH_ORBIT_LEADERBOARD = "/api/v5/orbit/public/leaderboard"
PATH_ORBIT_POSITION_CURRENT = "/api/v5/orbit/public/position-current"
PATH_ORBIT_POSITION_HISTORY = "/api/v5/orbit/public/position-history"


def get_leaderboard(base_url: str, api_key: str, secret_key: str, passphrase: str,
                    sort_by: str, period: str, min_pnl: str = None,
                    min_win_rate: str = None, max_drawdown: str = None,
                    min_aum: str = None, update_time: str = None,
                    after: str = None, before: str = None, limit: str = None,
                    simulated: bool = True) -> dict:
    """sort_by: 'pnl' or 'pnlRatio'. period: '3', '7', '30', or '90' (days)."""
    request_path = _with_query(PATH_ORBIT_LEADERBOARD, {
        "sortBy": sort_by,
        "period": period,
        "pnl": min_pnl,
        "winRate": min_win_rate,
        "maxDrawdown": max_drawdown,
        "asset": min_aum,
        "updateTime": update_time,
        "after": after,
        "before": before,
        "limit": limit,
    })
    body = ""
    headers = _headers(api_key, secret_key, passphrase, "GET", request_path, body, simulated)
    return _parse(_get_with_retry(base_url + request_path, headers, 10))


def get_trader_positions(base_url: str, api_key: str, secret_key: str, passphrase: str,
                         author_id: str, inst_ccy: str = None,
                         simulated: bool = True) -> dict:
    request_path = _with_query(PATH_ORBIT_POSITION_CURRENT, {
        "authorId": author_id,
        "instCcy": inst_ccy,
    })
    body = ""
    headers = _headers(api_key, secret_key, passphrase, "GET", request_path, body, simulated)
    return _parse(_get_with_retry(base_url + request_path, headers, 10))


def get_trader_positions_history(base_url: str, api_key: str, secret_key: str, passphrase: str,
                                 author_id: str, inst_ccy: str = None,
                                 after: str = None, before: str = None,
                                 limit: str = None, simulated: bool = True) -> dict:
    request_path = _with_query(PATH_ORBIT_POSITION_HISTORY, {
        "authorId": author_id,
        "instCcy": inst_ccy,
        "after": after,
        "before": before,
        "limit": limit,
    })
    body = ""
    headers = _headers(api_key, secret_key, passphrase, "GET", request_path, body, simulated)
    return _parse(_get_with_retry(base_url + request_path, headers, 10))
