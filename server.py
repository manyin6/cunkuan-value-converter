#!/usr/bin/env python3
"""Static file server + /api/prices aggregator with 60s cache."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import hmac
import secrets
import re as _re

ROOT = Path(__file__).resolve().parent
PORT = 8765
SHARE_DEFAULT = "https://example.com/"
ADMIN_KEY = __import__("os").environ.get("ADMIN_KEY", "deposit2026")
SESSION_COOKIE = "admin_session"
SESSION_TTL_SEC = 12 * 3600  # 12h
STATS_PATH = ROOT / "data" / "stats.json"
VISITORS_PATH = ROOT / "data" / "visitors.json"
STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
TZ_SH = ZoneInfo("Asia/Shanghai")
BOT_UA_RE = _re.compile(
    r"bot|spider|crawl|slurp|facebookexternalhit|preview|HeadlessChrome|wget|curl|python-requests",
    _re.I,
)
VISITORS_CAP = 100_000
RATE_LIMIT_SEC = 2.0
CACHE_TTL = 60
# Public site origin(s) for CORS on /api/event. Nginx must forward X-Forwarded-For.
# Override via ALLOWED_ORIGINS env (comma-separated), e.g.:
#   ALLOWED_ORIGINS=https://example.com,https://www.example.com
# Default is a placeholder — forks must set their real HTTPS origin before production.
_os = __import__("os")
ALLOWED_ORIGINS = {
    o.strip().rstrip("/")
    for o in _os.environ.get("ALLOWED_ORIGINS", "https://example.com").split(",")
    if o.strip()
}
# Per-IP sliding window limits (in-process; multi-worker needs Nginx limit_req too)
IP_EVENT_MAX_PER_MIN = 30
IP_VIEW_MAX_PER_MIN = 10
IP_QR_MAX_PER_MIN = 20
UA = "DepositValueConverter/1.0 (+local preview)"

_cache_lock = threading.Lock()
_cache: dict = {"ts": 0.0, "payload": None}


def _fetch_json(url: str, timeout: float = 8.0) -> dict | list | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — aggregate; report per-source
        return {"__error__": str(exc)}


def _fetch_text(url: str, timeout: float = 8.0) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except Exception:
        return None


def gather_prices() -> dict:
    sources: dict[str, str] = {}
    out: dict = {
        "ok": True,
        "USD_CNY": None,
        "BTC_CNY": None,
        "BTC_USD": None,
        "ETH_CNY": None,
        "ETH_USD": None,
        "GOLD_CNY": None,  # CNY per gram (spot)
        "GOLD_USD_OZ": None,
        "TSLA_USD": None,
        "AAPL_USD": None,
        "TSLA_CNY": None,
        "AAPL_CNY": None,
        "sources": sources,
        "fetched_at": None,
        "cache_ttl": CACHE_TTL,
    }

    # FX — Frankfurter (ECB)
    fx = _fetch_json("https://api.frankfurter.app/latest?from=USD&to=CNY")
    usd_cny = None
    if isinstance(fx, dict) and "rates" in fx:
        rate = fx["rates"].get("CNY")
        if isinstance(rate, (int, float)) and rate > 0:
            usd_cny = float(rate)
            sources["fx"] = "frankfurter"
    if usd_cny is None:
        # exchangerate.host fallback
        fx2 = _fetch_json("https://api.exchangerate.host/latest?base=USD&symbols=CNY")
        if isinstance(fx2, dict) and fx2.get("rates", {}).get("CNY"):
            usd_cny = float(fx2["rates"]["CNY"])
            sources["fx"] = "exchangerate.host"
    out["USD_CNY"] = usd_cny

    # BTC — CoinGecko CNY first
    cg = _fetch_json(
        "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=cny,usd"
    )
    if isinstance(cg, dict) and isinstance(cg.get("bitcoin"), dict):
        b = cg["bitcoin"]
        if isinstance(b.get("cny"), (int, float)) and b["cny"] > 0:
            out["BTC_CNY"] = float(b["cny"])
            sources["btc"] = "coingecko"
        if isinstance(b.get("usd"), (int, float)) and b["usd"] > 0:
            out["BTC_USD"] = float(b["usd"])
            if out["BTC_CNY"] is None and usd_cny:
                out["BTC_CNY"] = out["BTC_USD"] * usd_cny
                sources["btc"] = "coingecko+fx"

    # Binance Vision / Coinbase / Blockchain.info fallbacks for BTC
    if out["BTC_CNY"] is None:
        bn = _fetch_json(
            "https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT"
        )
        if isinstance(bn, dict) and bn.get("price"):
            try:
                btc_usd = float(bn["price"])
                out["BTC_USD"] = btc_usd
                if usd_cny:
                    out["BTC_CNY"] = btc_usd * usd_cny
                    sources["btc"] = "binance.vision+fx"
                else:
                    sources["btc"] = "binance.vision_usd_only"
            except ValueError:
                pass

    if out["BTC_CNY"] is None:
        cb = _fetch_json("https://api.coinbase.com/v2/prices/BTC-USD/spot")
        if isinstance(cb, dict):
            try:
                btc_usd = float(cb.get("data", {}).get("amount", 0))
                if btc_usd > 0:
                    out["BTC_USD"] = btc_usd
                    if usd_cny:
                        out["BTC_CNY"] = btc_usd * usd_cny
                        sources["btc"] = "coinbase+fx"
            except (TypeError, ValueError):
                pass

    if out["BTC_CNY"] is None:
        bc = _fetch_json("https://blockchain.info/ticker")
        if isinstance(bc, dict):
            cny = bc.get("CNY") or {}
            usd = bc.get("USD") or {}
            try:
                if isinstance(cny.get("last"), (int, float)) and cny["last"] > 0:
                    out["BTC_CNY"] = float(cny["last"])
                    sources["btc"] = "blockchain.info"
                if isinstance(usd.get("last"), (int, float)) and usd["last"] > 0:
                    out["BTC_USD"] = float(usd["last"])
                    if out["BTC_CNY"] is None and usd_cny:
                        out["BTC_CNY"] = out["BTC_USD"] * usd_cny
                        sources["btc"] = "blockchain.info+fx"
            except (TypeError, ValueError, KeyError):
                pass

    # Stocks — Yahoo chart (server-side, no CORS)
    def yahoo_price(symbol: str) -> float | None:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            f"?interval=1d&range=1d"
        )
        data = _fetch_json(url)
        if not isinstance(data, dict):
            return None
        try:
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            if isinstance(price, (int, float)) and price > 0:
                return float(price)
        except (KeyError, IndexError, TypeError):
            return None
        return None

    tsla = yahoo_price("TSLA")
    aapl = yahoo_price("AAPL")
    if tsla:
        out["TSLA_USD"] = tsla
        sources["tsla"] = "yahoo"
        if usd_cny:
            out["TSLA_CNY"] = tsla * usd_cny
    if aapl:
        out["AAPL_USD"] = aapl
        sources["aapl"] = "yahoo"
        if usd_cny:
            out["AAPL_CNY"] = aapl * usd_cny

    # Stooq CSV fallback for stocks (often works without key)
    def stooq_price(symbol: str) -> float | None:
        # e.g. tsla.us
        text = _fetch_text(f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv")
        if not text:
            return None
        lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
        if len(lines) < 2:
            return None
        # header: Symbol,Date,Time,Open,High,Low,Close,Volume
        cols = lines[1].split(",")
        if len(cols) < 7:
            return None
        try:
            close = float(cols[6])
            return close if close > 0 else None
        except ValueError:
            return None

    if out["TSLA_USD"] is None:
        p = stooq_price("tsla.us")
        if p:
            out["TSLA_USD"] = p
            sources["tsla"] = "stooq"
            if usd_cny:
                out["TSLA_CNY"] = p * usd_cny
    if out["AAPL_USD"] is None:
        p = stooq_price("aapl.us")
        if p:
            out["AAPL_USD"] = p
            sources["aapl"] = "stooq"
            if usd_cny:
                out["AAPL_CNY"] = p * usd_cny

    # ETH — Binance Vision / Coinbase
    eth = _fetch_json(
        "https://data-api.binance.vision/api/v3/ticker/price?symbol=ETHUSDT"
    )
    if isinstance(eth, dict) and eth.get("price"):
        try:
            eth_usd = float(eth["price"])
            out["ETH_USD"] = eth_usd
            if usd_cny:
                out["ETH_CNY"] = eth_usd * usd_cny
                sources["eth"] = "binance.vision+fx"
        except ValueError:
            pass
    if out["ETH_CNY"] is None:
        cb_eth = _fetch_json("https://api.coinbase.com/v2/prices/ETH-USD/spot")
        if isinstance(cb_eth, dict):
            try:
                eth_usd = float(cb_eth.get("data", {}).get("amount", 0))
                if eth_usd > 0:
                    out["ETH_USD"] = eth_usd
                    if usd_cny:
                        out["ETH_CNY"] = eth_usd * usd_cny
                        sources["eth"] = "coinbase+fx"
            except (TypeError, ValueError):
                pass

    # Gold spot — Coinbase XAU-USD / troy oz → CNY per gram
    TROY_OZ_G = 31.1034768
    xau = _fetch_json("https://api.coinbase.com/v2/prices/XAU-USD/spot")
    if isinstance(xau, dict):
        try:
            oz = float(xau.get("data", {}).get("amount", 0))
            if oz > 0:
                out["GOLD_USD_OZ"] = oz
                if usd_cny:
                    out["GOLD_CNY"] = (oz / TROY_OZ_G) * usd_cny
                    sources["gold"] = "coinbase_xau+fx"
        except (TypeError, ValueError):
            pass
    if out["GOLD_CNY"] is None:
        ga = _fetch_json("https://api.gold-api.com/price/XAU")
        if isinstance(ga, dict) and isinstance(ga.get("price"), (int, float)) and ga["price"] > 0:
            oz = float(ga["price"])
            out["GOLD_USD_OZ"] = oz
            if usd_cny:
                out["GOLD_CNY"] = (oz / TROY_OZ_G) * usd_cny
                sources["gold"] = "gold-api+fx"

    out["fetched_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    # ok if at least one live market price landed
    out["ok"] = any(
        out[k] is not None
        for k in ("BTC_CNY", "GOLD_CNY", "TSLA_CNY", "AAPL_CNY", "BTC_USD")
    )
    return out


_ip_buckets: dict[str, list[float]] = {}
_ip_bucket_lock = threading.Lock()


def _client_ip_from_handler(handler: "Handler") -> str:
    """Prefer first X-Forwarded-For hop (Nginx must set it); else socket peer."""
    xff = handler.headers.get("X-Forwarded-For") or handler.headers.get("X-Real-IP") or ""
    if xff:
        # leftmost = original client when Nginx appends
        return xff.split(",")[0].strip()[:64] or "unknown"
    try:
        return handler.client_address[0]
    except Exception:
        return "unknown"


def _ip_rate_allow(bucket_key: str, limit: int, window_sec: float = 60.0) -> bool:
    """Return True if request is allowed under per-key sliding window."""
    now = time.monotonic()
    with _ip_bucket_lock:
        q = _ip_buckets.setdefault(bucket_key, [])
        cutoff = now - window_sec
        # drop old
        i = 0
        while i < len(q) and q[i] < cutoff:
            i += 1
        if i:
            del q[:i]
        if len(q) >= limit:
            return False
        q.append(now)
        # prune map if huge
        if len(_ip_buckets) > 20000:
            stale = [k for k, v in _ip_buckets.items() if not v or v[-1] < cutoff]
            for k in stale[:5000]:
                _ip_buckets.pop(k, None)
        return True


def _origin_allowed(origin: str | None) -> bool:
    if origin is None or origin == "" or origin == "null":
        # same-origin / opaque; allow (browser may omit Origin on same-site GET)
        return True
    return origin.rstrip("/") in ALLOWED_ORIGINS or origin in ALLOWED_ORIGINS



def get_cached_prices(force: bool = False) -> dict:
    """Serve cached prices; fetch outside the lock to avoid convoy under load."""
    now = time.time()
    with _cache_lock:
        if (
            not force
            and _cache["payload"] is not None
            and now - _cache["ts"] < CACHE_TTL
        ):
            payload = dict(_cache["payload"])
            payload["cached"] = True
            payload["age_s"] = round(now - _cache["ts"], 1)
            return payload
        # stale copy while we refresh (may be None)
        stale_ts = _cache["ts"]

    # Fetch WITHOUT holding lock
    payload = gather_prices()
    now2 = time.time()
    with _cache_lock:
        # if another thread refreshed meanwhile and we're not forcing, prefer fresher cache
        if (
            not force
            and _cache["payload"] is not None
            and _cache["ts"] > stale_ts
            and now2 - _cache["ts"] < CACHE_TTL
        ):
            out = dict(_cache["payload"])
            out["cached"] = True
            out["age_s"] = round(now2 - _cache["ts"], 1)
            return out
        _cache["ts"] = now2
        _cache["payload"] = payload
        out = dict(payload)
        out["cached"] = False
        out["age_s"] = 0
        return out


def _now_sh():
    return __import__("datetime").datetime.now(TZ_SH)


def _day_str(dt=None) -> str:
    return (dt or _now_sh()).strftime("%Y-%m-%d")


def _stamp(dt=None) -> str:
    return (dt or _now_sh()).strftime("%Y-%m-%d %H:%M:%S") + " Asia/Shanghai"


def _hash_vid(vid: str) -> str:
    return hashlib.sha256(vid.encode("utf-8")).hexdigest()[:32]


def _empty_stats() -> dict:
    return {
        "totals": {
            "view": 0,
            "save_image": 0,
            "copy": 0,
            "share": 0,
        },
        "unique_views": 0,  # permanent UV counter; only increments for new hashed vid
        "daily": {},  # YYYY-MM-DD -> counters + unique_views + visitors hashes
        "updated_at": None,
    }


_stats_lock = threading.Lock()
_rate_recent: dict[tuple[str, str], float] = {}  # (vid_hash_or_raw, type) -> monotonic ts
_visitors_set: set[str] | None = None  # hashed vids loaded from VISITORS_PATH


def _load_visitor_set() -> set[str]:
    global _visitors_set
    if _visitors_set is not None:
        return _visitors_set
    ids: set[str] = set()
    if VISITORS_PATH.exists():
        try:
            data = json.loads(VISITORS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                ids = {str(x) for x in data if x}
            elif isinstance(data, dict) and isinstance(data.get("ids"), list):
                ids = {str(x) for x in data["ids"] if x}
        except Exception:
            ids = set()
    _visitors_set = ids
    return _visitors_set


def _save_visitor_set(ids: set[str]) -> None:
    global _visitors_set
    _visitors_set = ids
    VISITORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    # store sorted for stable diffs; cap list length but NEVER decrease unique_views counter
    arr = sorted(ids)
    if len(arr) > VISITORS_CAP:
        arr = arr[-VISITORS_CAP:]
        _visitors_set = set(arr)
    tmp = VISITORS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(arr, ensure_ascii=False), encoding="utf-8")
    tmp.replace(VISITORS_PATH)


def _load_stats() -> dict:
    if not STATS_PATH.exists():
        return _empty_stats()
    try:
        data = json.loads(STATS_PATH.read_text(encoding="utf-8"))
        base = _empty_stats()
        base["totals"] = {**base["totals"], **(data.get("totals") or {})}
        for k in ("view", "save_image", "copy", "share"):
            base["totals"][k] = int(base["totals"].get(k, 0) or 0)
        base["unique_views"] = int(data.get("unique_views", 0) or 0)
        base["daily"] = data.get("daily") if isinstance(data.get("daily"), dict) else {}
        base["updated_at"] = data.get("updated_at")
        # migrate: if old file had visitors list and UV was derived from truncated list,
        # keep unique_views as stored (do not recompute downward)
        return base
    except Exception:
        return _empty_stats()


def _save_stats(data: dict) -> None:
    data["updated_at"] = _stamp()
    # strip legacy visitors array from stats.json if present
    data.pop("visitors", None)
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATS_PATH)


def _rate_limited(vid_key: str, event_type: str) -> bool:
    """Return True if this event should be IGNORED as duplicate."""
    now = time.monotonic()
    key = (vid_key, event_type)
    # prune occasionally
    if len(_rate_recent) > 5000:
        cutoff = now - RATE_LIMIT_SEC
        stale = [k for k, ts in _rate_recent.items() if ts < cutoff]
        for k in stale:
            _rate_recent.pop(k, None)
    prev = _rate_recent.get(key)
    if prev is not None and now - prev < RATE_LIMIT_SEC:
        return True
    _rate_recent[key] = now
    return False


def record_event(
    event_type: str,
    visitor_id: str | None = None,
    user_agent: str | None = None,
) -> dict:
    allowed = {"view", "save_image", "copy", "share"}
    if event_type not in allowed:
        raise ValueError("invalid event type")
    if not visitor_id or not str(visitor_id).strip():
        raise ValueError("vid required")
    visitor_id = str(visitor_id).strip()[:64]

    # Bot filter: only for view events
    if event_type == "view" and user_agent and BOT_UA_RE.search(user_agent):
        return {"ok": True, "ignored": "bot", "type": event_type}

    vid_h = _hash_vid(visitor_id)
    if _rate_limited(vid_h, event_type):
        return {"ok": True, "ignored": "rate_limit", "type": event_type}

    day = _day_str()
    with _stats_lock:
        stats = _load_stats()
        stats["totals"][event_type] = int(stats["totals"].get(event_type, 0)) + 1

        daily = stats["daily"].setdefault(
            day,
            {
                "view": 0,
                "save_image": 0,
                "copy": 0,
                "share": 0,
                "unique_views": 0,
                "visitors": [],
            },
        )
        for k in ("view", "save_image", "copy", "share"):
            daily.setdefault(k, 0)
        daily.setdefault("visitors", [])
        daily.setdefault("unique_views", int(daily.get("unique_views", 0) or 0))
        daily[event_type] = int(daily[event_type]) + 1

        if event_type == "view":
            vset = _load_visitor_set()
            if vid_h not in vset:
                vset.add(vid_h)
                stats["unique_views"] = int(stats.get("unique_views", 0) or 0) + 1
                _save_visitor_set(vset)
            # daily UV: permanent counter + membership list (hashed)
            dv = daily["visitors"]
            if not isinstance(dv, list):
                dv = []
                daily["visitors"] = dv
            if vid_h not in dv:
                dv.append(vid_h)
                daily["unique_views"] = int(daily.get("unique_views", 0) or 0) + 1
                # soft cap daily list only after UV already incremented
                if len(dv) > 20000:
                    daily["visitors"] = dv[-20000:]

        _save_stats(stats)
        return {
            "ok": True,
            "type": event_type,
            "totals": stats["totals"],
            "unique_views": stats.get("unique_views", 0),
        }


def stats_summary() -> dict:
    with _stats_lock:
        stats = _load_stats()
    days = []
    now = _now_sh()
    for i in range(6, -1, -1):
        d = (now - __import__("datetime").timedelta(days=i)).strftime("%Y-%m-%d")
        row = stats.get("daily", {}).get(d, {})
        days.append(
            {
                "date": d,
                "view": int(row.get("view", 0) or 0),
                "unique_views": int(row.get("unique_views", 0) or 0),
                "save_image": int(row.get("save_image", 0) or 0),
                "copy": int(row.get("copy", 0) or 0),
                "share": int(row.get("share", 0) or 0),
            }
        )
    return {
        "ok": True,
        "totals": stats.get("totals", {}),
        "unique_views": int(stats.get("unique_views", 0) or 0),
        "updated_at": stats.get("updated_at"),
        "timezone": "Asia/Shanghai",
        "last_7_days": days,
        "methodology": {
            "view": "页面打开 PV：同浏览器会话前端只上报 1 次",
            "unique_views": "独立访客 UV：按访客 ID（SHA256）永久去重计数",
            "save_image": "海报下载成功次数（不含系统分享）",
            "share": "系统分享成功次数",
            "copy": "复制结果成功次数",
        },
    }



def _session_token(exp: int | None = None) -> str:
    """HMAC-signed admin session: exp.hexsig (bound to ADMIN_KEY)."""
    if exp is None:
        exp = int(time.time()) + SESSION_TTL_SEC
    msg = f"admin:{exp}".encode("utf-8")
    sig = hmac.new(ADMIN_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def _verify_session_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    try:
        exp_s, sig = token.split(".", 1)
        exp = int(exp_s)
        if exp < int(time.time()):
            return False
        expected = hmac.new(
            ADMIN_KEY.encode("utf-8"),
            f"admin:{exp}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


def _parse_cookies(header: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not header:
        return out
    for part in header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _request_is_https(handler: "Handler") -> bool:
    proto = (handler.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    if proto == "https":
        return True
    if proto == "http":
        return False
    return False


def _is_admin_request(handler: "Handler") -> bool:
    """True if valid admin_session cookie OR Authorization / X-Admin-Key."""
    cookies = _parse_cookies(handler.headers.get("Cookie"))
    if _verify_session_token(cookies.get(SESSION_COOKIE)):
        return True
    auth = (handler.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if hmac.compare_digest(token, ADMIN_KEY) or _verify_session_token(token):
            return True
    xkey = (handler.headers.get("X-Admin-Key") or "").strip()
    if xkey and hmac.compare_digest(xkey, ADMIN_KEY):
        return True
    return False


def _set_admin_cookie_header(handler: "Handler", token: str) -> str:
    parts = [
        f"{SESSION_COOKIE}={token}",
        "Path=/",
        f"Max-Age={SESSION_TTL_SEC}",
        "HttpOnly",
        "SameSite=Lax",
    ]
    if _request_is_https(handler):
        parts.append("Secure")
    return "; ".join(parts)


def render_admin_login_html(error: str | None = None) -> bytes:
    err = f'<p class="err">{error}</p>' if error else ""
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="robots" content="noindex,nofollow"/>
<title>管理员登录 · 存款价值转换</title>
<style>
  body{{font-family:system-ui,sans-serif;background:#f7f6f3;color:#111;margin:0;padding:24px}}
  .wrap{{max-width:380px;margin:10vh auto;background:#fff;border:1px solid #e6e4df;border-radius:12px;padding:24px}}
  h1{{font-size:1.1rem;margin:0 0 .5rem}}
  .sub{{color:#666;font-size:.82rem;margin-bottom:1.25rem;line-height:1.5}}
  label{{display:block;font-size:.8rem;color:#555;margin-bottom:.35rem}}
  input[type=password]{{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #d4d1ca;border-radius:8px;font-size:1rem}}
  button{{margin-top:14px;width:100%;padding:10px 14px;border:0;border-radius:8px;background:#111;color:#fff;font-size:.95rem;cursor:pointer}}
  .err{{color:#b91c1c;font-size:.85rem;margin:0 0 .75rem}}
  .hint{{margin-top:1rem;font-size:.75rem;color:#888;line-height:1.5}}
</style>
</head>
<body>
<div class="wrap">
  <h1>管理员登录</h1>
  <p class="sub">请输入 ADMIN_KEY。密钥通过 POST 提交，不再使用 URL 查询参数（避免写入访问日志）。</p>
  {err}
  <form method="POST" action="/api/admin/login" autocomplete="current-password">
    <label for="key">管理员密钥</label>
    <input id="key" name="key" type="password" required autofocus />
    <button type="submit">登录</button>
  </form>
  <p class="hint">登录成功后写入 HttpOnly Cookie（约 12 小时）。也可用请求头 <code>Authorization: Bearer &lt;ADMIN_KEY&gt;</code> 或 <code>X-Admin-Key</code> 访问 <code>/api/stats</code>。</p>
</div>
</body>
</html>"""
    return html.encode("utf-8")


def render_admin_html() -> bytes:
    s = stats_summary()
    rows = "".join(
        f"<tr><td>{d['date']}</td><td>{d['view']}</td><td>{d['unique_views']}</td>"
        f"<td>{d['save_image']}</td><td>{d['copy']}</td><td>{d['share']}</td></tr>"
        for d in s["last_7_days"]
    )
    tot = s["totals"]
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>数据统计 · 存款价值转换</title>
<style>
  body{{font-family:system-ui,sans-serif;background:#f7f6f3;color:#111;margin:0;padding:24px}}
  .wrap{{max-width:760px;margin:0 auto}}
  h1{{font-size:1.25rem;margin:0 0 .25rem}}
  .sub{{color:#666;font-size:.85rem;margin-bottom:1rem}}
  .note{{font-size:.78rem;color:#666;line-height:1.6;background:#fff;border:1px solid #e6e4df;border-radius:10px;padding:12px 14px;margin-bottom:1.25rem}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:1.5rem}}
  .card{{background:#fff;border:1px solid #e6e4df;border-radius:10px;padding:14px}}
  .card b{{display:block;font-size:1.4rem;letter-spacing:-.02em}}
  .card span{{font-size:.72rem;color:#666;line-height:1.35;display:block;margin-top:4px}}
  table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e6e4df;border-radius:10px;overflow:hidden}}
  th,td{{padding:10px 12px;text-align:left;font-size:.85rem;border-bottom:1px solid #eee}}
  th{{background:#fafaf8;color:#555;font-weight:600}}
</style>
</head>
<body>
<div class="wrap">
  <h1>存款价值转换 · 数据</h1>
  <p class="sub">更新于 {s.get('updated_at') or '—'} · 时区 Asia/Shanghai · 仅管理员可访问</p>
  <div class="note">
    <strong>口径说明：</strong>
    打开次数 = 页面打开（PV，同会话前端只计 1 次）；
    独立访客 = 按浏览器访客 ID 去重（UV，永久计数）；
    保存图片 = 下载海报成功次数；
    系统分享 = 调起系统分享并成功；
    复制结果 = 复制成功。
    过滤爬虫 UA；同访客同事件 2 秒内去重。
  </div>
  <div class="cards">
    <div class="card"><b>{tot.get('view',0)}</b><span>打开次数<br/>页面打开（PV，同会话只计1次）</span></div>
    <div class="card"><b>{s.get('unique_views',0)}</b><span>独立访客<br/>按浏览器访客ID去重（UV）</span></div>
    <div class="card"><b>{tot.get('save_image',0)}</b><span>保存图片<br/>下载海报成功次数</span></div>
    <div class="card"><b>{tot.get('share',0)}</b><span>系统分享<br/>调起系统分享并成功</span></div>
    <div class="card"><b>{tot.get('copy',0)}</b><span>复制结果<br/>复制成功</span></div>
  </div>
  <h2 style="font-size:1rem;margin:0 0 .75rem">近 7 天</h2>
  <table>
    <thead><tr><th>日期</th><th>打开</th><th>独立</th><th>保存图</th><th>复制</th><th>分享</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
</body>
</html>"""
    return html.encode("utf-8")



class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        # quieter logs
        if args and str(args[0]).startswith("GET /api/"):
            super().log_message(fmt, *args)

    def end_headers(self) -> None:  # noqa: D102
        # Security headers on all responses
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        # Basic CSP for HTML pages; APIs ignore harmlessly
        if not hasattr(self, "_skip_csp"):
            path = urllib.parse.urlparse(getattr(self, "path", "") or "").path
            if path.endswith(".html") or path in ("/", "/admin", "/stats") or path == "":
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; "
                    "script-src 'self' https://cdn.jsdelivr.net; "
                    "style-src 'self' 'unsafe-inline'; "
                    "font-src 'self'; "
                    "img-src 'self' data: blob:; "
                    "connect-src 'self'; "
                    "frame-ancestors 'none'",
                )
        super().end_headers()

    def _client_ip(self) -> str:
        return _client_ip_from_handler(self)

    def _cors_origin_header(self) -> str | None:
        origin = self.headers.get("Origin")
        if origin and _origin_allowed(origin):
            return origin.rstrip("/") if origin != "null" else "null"
        # same-origin requests often omit Origin
        if not origin:
            return None
        return None

    def _set_cors_if_allowed(self) -> bool:
        """Set ACAO only for allowed origin. Returns False if Origin present but not allowed."""
        origin = self.headers.get("Origin")
        if origin and not _origin_allowed(origin):
            return False
        ao = self._cors_origin_header()
        if ao:
            self.send_header("Access-Control-Allow-Origin", ao)
            self.send_header("Vary", "Origin")
        return True

    def _site_soft_ok(self) -> bool:
        """Soft same-site check for /api/event: Origin or Referer should match if present."""
        origin = self.headers.get("Origin")
        if origin and not _origin_allowed(origin):
            return False
        ref = self.headers.get("Referer") or ""
        if ref:
            try:
                host = urllib.parse.urlparse(ref)
                origin_like = f"{host.scheme}://{host.netloc}"
                if host.netloc and not _origin_allowed(origin_like):
                    # allow empty scheme edge cases only if no netloc
                    return False
            except Exception:
                pass
        return True

    def _forbid(self, msg: bytes = b"Forbidden") -> None:
        self.send_response(403)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(msg)))
        self.end_headers()
        self.wfile.write(msg)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        # Deny sensitive paths that SimpleHTTPRequestHandler would otherwise serve from ROOT.
        # (Confirmed public on production: /.admin_key, /data/*, /server.py)
        req_path = urllib.parse.unquote(parsed.path or "/")
        norm = req_path.replace("\\", "/")
        while "//" in norm:
            norm = norm.replace("//", "/")
        low = norm.lower()
        blocked_exact = {
            "/.admin_key",
            "/server.py",
            "/stats.md",
            "/readme.md",
            "/promote.md",
            "/wechat.md",
        }
        if (
            low in blocked_exact
            or low.startswith("/data/")
            or low.startswith("/__pycache__/")
            or low.startswith("/.")
            or "/../" in norm
            or norm.endswith("/..")
        ):
            self._forbid()
            return
        if parsed.path in ("/admin", "/stats"):
            qs = urllib.parse.parse_qs(parsed.query)
            # Legacy ?key=… — never echo key; strip query and show login (or dashboard if cookie ok)
            if "key" in qs:
                self.send_response(302)
                self.send_header("Location", "/admin")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if not _is_admin_request(self):
                body = render_admin_login_html()
                self.send_response(401)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = render_admin_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/stats":
            if not _is_admin_request(self):
                body = json.dumps({"ok": False, "error": "unauthorized"}).encode()
                self.send_response(401)
            else:
                body = json.dumps(stats_summary(), ensure_ascii=False).encode()
                self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/qr":
            ip = self._client_ip()
            if not _ip_rate_allow(f"qr:{ip}", IP_QR_MAX_PER_MIN, 60.0):
                body = b"Too Many Requests"
                self.send_response(429)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Retry-After", "60")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            qs = urllib.parse.parse_qs(parsed.query)
            data = (qs.get("data") or qs.get("url") or [SHARE_DEFAULT])[0]
            if not data:
                data = SHARE_DEFAULT
            if len(data) > 2048:
                self._forbid(b"QR data too long")
                return
            # Proxy a public QR PNG API (no key)
            up = (
                "https://api.qrserver.com/v1/create-qr-code/"
                f"?size=224x224&ecc=M&margin=8&data={urllib.parse.quote(data, safe='')}"
            )
            try:
                req = urllib.request.Request(up, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    body = resp.read()
                    ctype = resp.headers.get("Content-Type", "image/png")
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc).encode()
                self.send_response(502)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
            return
        if self.path.startswith("/api/prices"):
            qs = urllib.parse.parse_qs(parsed.query)
            want_refresh = "refresh=1" in self.path or "force=1" in self.path
            # Public cannot force upstream refresh — requires admin session / header
            force = False
            if want_refresh and _is_admin_request(self):
                force = True
                # else ignore refresh flag and serve cache
            try:
                payload = get_cached_prices(force=force)
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:  # noqa: BLE001
                err = json.dumps({"ok": False, "error": str(exc)}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err)))
                self.end_headers()
                self.wfile.write(err)
            return
        return super().do_GET()



    def _handle_admin_login(self) -> None:
        """POST /api/admin/login — form or JSON {key}; sets HttpOnly session cookie."""
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            length = 0
        if length < 0 or length > 4096:
            body = render_admin_login_html("请求过大")
            self.send_response(413)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        raw = self.rfile.read(length) if length else b""
        ctype = (self.headers.get("Content-Type") or "").lower()
        key = ""
        if "application/json" in ctype:
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                key = str(payload.get("key") or payload.get("password") or "")
            except json.JSONDecodeError:
                key = ""
        else:
            form = urllib.parse.parse_qs(raw.decode("utf-8", errors="replace"))
            key = (form.get("key") or form.get("password") or [""])[0]
        key = key.strip()
        # Constant-time compare
        if not key or not hmac.compare_digest(key, ADMIN_KEY):
            # mild delay against brute force
            time.sleep(0.4 + secrets.randbelow(200) / 1000.0)
            accept = (self.headers.get("Accept") or "").lower()
            if "application/json" in accept or "application/json" in ctype:
                body = json.dumps({"ok": False, "error": "unauthorized"}).encode()
                self.send_response(401)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = render_admin_login_html("密钥错误，请重试")
            self.send_response(401)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        token = _session_token()
        cookie = _set_admin_cookie_header(self, token)
        accept = (self.headers.get("Accept") or "").lower()
        if "application/json" in accept or "application/json" in ctype:
            body = json.dumps({"ok": True, "expires_in": SESSION_TTL_SEC}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", cookie)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(303)
        self.send_header("Location", "/admin")
        self.send_header("Set-Cookie", cookie)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/event":
            self.send_error(404)
            return
        origin = self.headers.get("Origin")
        if origin and not _origin_allowed(origin):
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(204)
        ao = self._cors_origin_header()
        if ao:
            self.send_header("Access-Control-Allow-Origin", ao)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/admin/login":
            self._handle_admin_login()
            return
        if parsed.path != "/api/event":
            self.send_error(404)
            return

        # CORS: reject disallowed Origin
        origin = self.headers.get("Origin")
        if origin and not _origin_allowed(origin):
            body = json.dumps({"ok": False, "error": "origin not allowed"}).encode()
            self.send_response(403)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Soft same-site Referer/Origin check
        if not self._site_soft_ok():
            body = json.dumps({"ok": False, "error": "site check failed"}).encode()
            self.send_response(403)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            if origin and _origin_allowed(origin):
                self.send_header("Access-Control-Allow-Origin", origin.rstrip("/"))
                self.send_header("Vary", "Origin")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        ip = self._client_ip()
        # Peek type early for view-specific limit — need body first
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            length = 0
        if length < 0 or length > 4096:
            body = json.dumps({"ok": False, "error": "payload too large"}).encode()
            self.send_response(413)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            if origin and _origin_allowed(origin):
                self.send_header("Access-Control-Allow-Origin", origin.rstrip("/"))
                self.send_header("Vary", "Origin")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        event_type = str(payload.get("type") or "").strip()
        visitor_id = payload.get("vid") or payload.get("visitor_id")
        if isinstance(visitor_id, str):
            visitor_id = visitor_id.strip()[:64] or None
        else:
            visitor_id = None
        ua = self.headers.get("User-Agent") or ""

        # Per-IP limits
        if not _ip_rate_allow(f"event:{ip}", IP_EVENT_MAX_PER_MIN, 60.0):
            body = json.dumps({"ok": False, "error": "rate_limit", "ignored": "ip_event"}).encode()
            self.send_response(429)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Retry-After", "60")
            if origin and _origin_allowed(origin):
                self.send_header("Access-Control-Allow-Origin", origin.rstrip("/"))
                self.send_header("Vary", "Origin")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if event_type == "view" and not _ip_rate_allow(f"view:{ip}", IP_VIEW_MAX_PER_MIN, 60.0):
            body = json.dumps({"ok": False, "error": "rate_limit", "ignored": "ip_view"}).encode()
            self.send_response(429)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Retry-After", "60")
            if origin and _origin_allowed(origin):
                self.send_header("Access-Control-Allow-Origin", origin.rstrip("/"))
                self.send_header("Vary", "Origin")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        try:
            result = record_event(event_type, visitor_id, user_agent=ua)
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
        except ValueError as exc:
            body = json.dumps({"ok": False, "error": str(exc)}).encode()
            self.send_response(400)
        except Exception as exc:  # noqa: BLE001
            body = json.dumps({"ok": False, "error": str(exc)}).encode()
            self.send_response(500)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if origin and _origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin.rstrip("/"))
            self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    host = __import__("os").environ.get("HOST", "127.0.0.1")
    httpd = ThreadingHTTPServer((host, PORT), Handler)
    print(f"Serving {ROOT} on http://{host}:{PORT}/  (API: /api/prices /api/event /admin login)")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
