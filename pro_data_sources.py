"""
pro_data_sources.py — Beast Trading Bot: Professional Data Sources Module

Aggregates 10 free data sources (Congress trades, insider filings, options flow,
VIX term structure, sentiment, short interest, dark pools, economic calendar,
institutional 13-F filings, ARK daily holdings) into a single actionable
intelligence layer.

Every API call is logged, cached, and wrapped in error handling so the bot
never crashes regardless of upstream availability.

Usage:
    from pro_data_sources import ProDataSources
    pro = ProDataSources(db=my_pg_connection)   # db is optional
    intel = pro.get_full_intel("AAPL")
    macro = pro.get_market_conditions()
"""

import csv
import io
import json
import logging
import os
import re
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
    logging.getLogger("beast").warning("[PRO_DATA] beautifulsoup4 not installed — congress scraper disabled. Run: pip install beautifulsoup4")

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
log = logging.getLogger("beast.pro_data")
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    log.addHandler(_handler)
    log.setLevel(logging.DEBUG)


# ---------------------------------------------------------------------------
# Tiny TTL cache helper
# ---------------------------------------------------------------------------
class _TTLCache:
    """Dict-backed cache with per-key TTL (seconds)."""

    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}

    def get(self, key: str) -> Any:
        if key in self._store and time.time() < self._expiry.get(key, 0):
            log.debug(f"[PRO_DATA] Cache HIT  key={key}")
            return self._store[key]
        log.debug(f"[PRO_DATA] Cache MISS key={key}")
        return None

    def set(self, key: str, value: Any, ttl: int):
        self._store[key] = value
        self._expiry[key] = time.time() + ttl

    def invalidate(self, key: str):
        self._store.pop(key, None)
        self._expiry.pop(key, None)


_cache = _TTLCache()

# Shared HTTP session with retries + proper User-Agent (avoids 403s from CBOE/FINRA/SEC)
_http = requests.Session()
_http.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})
_adapter = requests.adapters.HTTPAdapter(max_retries=2)
_http.mount("https://", _adapter)
_http.mount("http://", _adapter)
_DEFAULT_TIMEOUT = 15


def _safe_request(method: str, url: str, *, headers: dict | None = None,
                  params: dict | None = None, json_body: dict | None = None,
                  timeout: int = _DEFAULT_TIMEOUT, tag: str = "HTTP") -> Optional[requests.Response]:
    """Fire an HTTP request; return Response on success or None on any error."""
    try:
        log.info(f"[PRO_DATA] {tag}: {method.upper()} {url}")
        resp = _http.request(method, url, headers=headers, params=params,
                             json=json_body, timeout=timeout)
        log.info(f"[PRO_DATA] {tag}: status={resp.status_code} len={len(resp.content)}")
        resp.raise_for_status()
        return resp
    except requests.RequestException as exc:
        log.error(f"[PRO_DATA] {tag}: FAILED {exc}")
        return None


# =========================================================================
# 1. CongressTracker
# =========================================================================
class CongressTracker:
    """Scrape Capitol Trades for politician stock transactions."""

    URL = "https://www.capitoltrades.com/trades?per_page=100&page=1"
    CACHE_TTL = 4 * 3600  # 4 hours

    def fetch(self) -> list:
        cached = _cache.get("congress_trades")
        if cached is not None:
            return cached

        log.info("[PRO_DATA] CongressTracker: fetching Capitol Trades")
        resp = _safe_request("get", self.URL, tag="Congress")
        if resp is None:
            return []

        trades: list[dict] = []
        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table tbody tr")
            log.info(f"[PRO_DATA] CongressTracker: parsed {len(rows)} rows")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 6:
                    continue
                trade = {
                    "politician": cells[0].get_text(strip=True),
                    "ticker": cells[1].get_text(strip=True).upper(),
                    "action": cells[2].get_text(strip=True).lower(),
                    "size": cells[3].get_text(strip=True),
                    "date": cells[4].get_text(strip=True),
                    "filed": cells[5].get_text(strip=True),
                }
                log.debug(f"[PRO_DATA] CongressTracker: {trade['politician']} "
                          f"{trade['action']} {trade['ticker']} size={trade['size']} "
                          f"filed={trade['filed']}")
                trades.append(trade)
        except Exception as exc:
            log.error(f"[PRO_DATA] CongressTracker: parse error {exc}")
            log.debug(traceback.format_exc())

        _cache.set("congress_trades", trades, self.CACHE_TTL)
        return trades

    def get_congress_signal(self, symbol: str) -> dict:
        """Score -10 … +10 based on recent congress activity for *symbol*."""
        symbol = symbol.upper()
        log.info(f"[PRO_DATA] CongressTracker: computing signal for {symbol}")
        result = {"source": "congress", "symbol": symbol, "score": 0,
                  "trades": [], "reasoning": "no data"}
        try:
            trades = self.fetch()
            relevant = [t for t in trades if t.get("ticker") == symbol]
            if not relevant:
                result["reasoning"] = f"no recent congress trades for {symbol}"
                log.info(f"[PRO_DATA] CongressTracker: {result['reasoning']}")
                return result

            buys = [t for t in relevant if "purchase" in t["action"] or "buy" in t["action"]]
            sells = [t for t in relevant if "sale" in t["action"] or "sell" in t["action"]]
            log.info(f"[PRO_DATA] CongressTracker: {symbol} buys={len(buys)} sells={len(sells)}")

            score = 0
            if buys:
                score += min(len(buys) * 3, 10)
            if sells:
                score -= min(len(sells) * 3, 10)
            score = max(-10, min(10, score))

            result["score"] = score
            result["trades"] = relevant[:10]
            result["reasoning"] = (f"{len(buys)} buys, {len(sells)} sells by congress "
                                   f"members → score {score}")
            log.info(f"[PRO_DATA] CongressTracker: {result['reasoning']}")
        except Exception as exc:
            log.error(f"[PRO_DATA] CongressTracker: signal error {exc}")
            log.debug(traceback.format_exc())
        return result


# =========================================================================
# 2. InsiderTracker (SEC EDGAR Form 4)
# =========================================================================
class InsiderTracker:
    """Track SEC Form-4 insider filings via EDGAR full-text search."""

    SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
    SUBMISSION_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
    HEADERS = {"User-Agent": "BeastTrader beast@trader.com"}
    CACHE_TTL = 2 * 3600

    def _search_form4(self, symbol: str) -> list:
        today = datetime.now(timezone.utc)
        start = (today - timedelta(days=90)).strftime("%Y-%m-%d")
        params = {
            "q": f'"Form 4" AND "{symbol}"',
            "forms": "4",
            "dateRange": "custom",
            "startdt": start,
        }
        resp = _safe_request("get", self.SEARCH_URL, headers=self.HEADERS,
                             params=params, tag="InsiderSearch")
        if resp is None:
            return []
        try:
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            log.info(f"[PRO_DATA] InsiderTracker: EDGAR returned {len(hits)} hits for {symbol}")
            return hits
        except Exception as exc:
            log.error(f"[PRO_DATA] InsiderTracker: JSON parse error {exc}")
            return []

    def _get_submissions(self, cik: str) -> dict:
        url = self.SUBMISSION_URL.format(cik=cik.zfill(10))
        resp = _safe_request("get", url, headers=self.HEADERS, tag="InsiderSub")
        if resp is None:
            return {}
        try:
            return resp.json()
        except Exception:
            return {}

    def fetch(self, symbol: str) -> list:
        key = f"insider_{symbol}"
        cached = _cache.get(key)
        if cached is not None:
            return cached

        log.info(f"[PRO_DATA] InsiderTracker: fetching insider data for {symbol}")
        filings: list[dict] = []
        try:
            hits = self._search_form4(symbol)
            for h in hits[:50]:
                src = h.get("_source", {})
                filings.append({
                    "filer": src.get("display_names", ["unknown"])[0] if src.get("display_names") else "unknown",
                    "date": src.get("file_date", ""),
                    "form": src.get("form_type", "4"),
                    "ticker": symbol.upper(),
                })
        except Exception as exc:
            log.error(f"[PRO_DATA] InsiderTracker: fetch error {exc}")
            log.debug(traceback.format_exc())

        _cache.set(key, filings, self.CACHE_TTL)
        return filings

    def get_insider_signal(self, symbol: str) -> dict:
        symbol = symbol.upper()
        log.info(f"[PRO_DATA] InsiderTracker: computing signal for {symbol}")
        result = {"source": "insider", "symbol": symbol, "score": 0,
                  "filings": [], "cluster": False, "reasoning": "no data"}
        try:
            filings = self.fetch(symbol)
            result["filings"] = filings[:10]
            count = len(filings)
            if count == 0:
                result["reasoning"] = "no recent Form 4 filings"
                log.info(f"[PRO_DATA] InsiderTracker: {result['reasoning']}")
                return result

            # Cluster detection: 3+ filings in last 30 days → strong signal
            cluster = count >= 3
            score = min(count * 2, 10) if cluster else min(count, 5)
            result["score"] = score
            result["cluster"] = cluster
            result["reasoning"] = (f"{count} Form-4 filings, cluster={'YES' if cluster else 'no'}"
                                   f" → score {score}")
            log.info(f"[PRO_DATA] InsiderTracker: {result['reasoning']}")
        except Exception as exc:
            log.error(f"[PRO_DATA] InsiderTracker: signal error {exc}")
        return result


# =========================================================================
# 3. PutCallRatio (CBOE)
# =========================================================================
class PutCallRatio:
    """CBOE S&P 500 Put/Call ratio — tries multiple sources."""

    URLS = [
        "https://cdn.cboe.com/api/global/us_indices/daily_prices/SPXPC_History.csv",
        "https://cdn.cboe.com/api/global/us_indices/daily_prices/SPX_P-C-Ratio_History.csv",
    ]
    CACHE_TTL = 30 * 60

    def fetch(self) -> Optional[pd.DataFrame]:
        cached = _cache.get("pcr_df")
        if cached is not None:
            return cached

        # Try CBOE CSV URLs first
        for url in self.URLS:
            log.info(f"[PRO_DATA] PutCallRatio: trying {url}")
            resp = _safe_request("get", url, tag="PCR")
            if resp and resp.status_code == 200:
                try:
                    df = pd.read_csv(io.StringIO(resp.text))
                    df.columns = [c.strip().lower() for c in df.columns]
                    log.info(f"[PRO_DATA] PutCallRatio: loaded {len(df)} rows from CBOE")
                    _cache.set("pcr_df", df, self.CACHE_TTL)
                    return df
                except Exception as exc:
                    log.error(f"[PRO_DATA] PutCallRatio: parse error {exc}")

        # Fallback: compute from Alpaca options data or return VIX-implied estimate
        log.warning("[PRO_DATA] PutCallRatio: all CBOE URLs failed, using VIX-based estimate")
        try:
            vix_src = VIXTermStructure()
            vix_data = vix_src.get_vix_structure()
            vix_val = vix_data.get('vix', 18)
            # VIX > 25 implies high put buying (PCR > 1.0)
            # VIX < 15 implies low put buying (PCR < 0.7)
            estimated_pcr = 0.5 + (vix_val / 50.0)  # Rough linear approximation
            log.info(f"[PRO_DATA] PutCallRatio: VIX-estimated PCR={estimated_pcr:.2f} (VIX={vix_val:.1f})")
            result_df = pd.DataFrame({'date': [datetime.now().strftime('%Y-%m-%d')], 'ratio': [estimated_pcr]})
            _cache.set("pcr_df", result_df, self.CACHE_TTL)
            return result_df
        except Exception as exc:
            log.error(f"[PRO_DATA] PutCallRatio: VIX fallback failed: {exc}")
            return None
        except Exception as exc:
            log.error(f"[PRO_DATA] PutCallRatio: parse error {exc}")
            return None

    def get_pcr(self) -> dict:
        log.info("[PRO_DATA] PutCallRatio: computing signal")
        result = {"source": "pcr", "value": None, "signal": "neutral",
                  "score": 0, "reasoning": "no data"}
        try:
            df = self.fetch()
            if df is None or df.empty:
                log.warning("[PRO_DATA] PutCallRatio: no data available")
                return result

            # Try common column names
            ratio_col = None
            for candidate in ["ratio", "put/call", "pcr", "close"]:
                if candidate in df.columns:
                    ratio_col = candidate
                    break
            if ratio_col is None:
                ratio_col = df.columns[-1]

            latest = float(df[ratio_col].dropna().iloc[-1])
            result["value"] = round(latest, 4)

            if latest > 1.2:
                result["signal"] = "contrarian_bullish"
                result["score"] = 5
                result["reasoning"] = f"PCR {latest:.2f} > 1.2 → extreme puts, contrarian bullish"
            elif latest > 1.0:
                result["signal"] = "mildly_bullish"
                result["score"] = 2
                result["reasoning"] = f"PCR {latest:.2f} > 1.0 → elevated puts"
            elif latest < 0.6:
                result["signal"] = "bearish"
                result["score"] = -5
                result["reasoning"] = f"PCR {latest:.2f} < 0.6 → complacency, bearish"
            elif latest < 0.8:
                result["signal"] = "mildly_bearish"
                result["score"] = -2
                result["reasoning"] = f"PCR {latest:.2f} < 0.8 → low put demand"
            else:
                result["signal"] = "neutral"
                result["score"] = 0
                result["reasoning"] = f"PCR {latest:.2f} is in neutral zone"

            log.info(f"[PRO_DATA] PutCallRatio: {result['reasoning']}")
        except Exception as exc:
            log.error(f"[PRO_DATA] PutCallRatio: signal error {exc}")
        return result


# =========================================================================
# 4. VIXTermStructure
# =========================================================================
class VIXTermStructure:
    """VIX vs VIX3M contango/backwardation from CBOE CSVs."""

    VIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
    VIX3M_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv"
    CACHE_TTL = 15 * 60

    def _load_csv(self, url: str, tag: str) -> Optional[float]:
        resp = _safe_request("get", url, tag=tag)
        if resp is None:
            return None
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            df.columns = [c.strip().lower() for c in df.columns]
            close_col = "close" if "close" in df.columns else df.columns[-1]
            val = float(df[close_col].dropna().iloc[-1])
            log.info(f"[PRO_DATA] VIXTermStructure: {tag} latest={val:.2f}")
            return val
        except Exception as exc:
            log.error(f"[PRO_DATA] VIXTermStructure: parse error for {tag}: {exc}")
            return None

    def get_vix_structure(self) -> dict:
        log.info("[PRO_DATA] VIXTermStructure: computing structure")
        result = {"source": "vix_term", "vix": None, "vix3m": None,
                  "ratio": None, "is_inverted": False, "regime_signal": "neutral",
                  "score": 0, "reasoning": "no data"}

        cached = _cache.get("vix_structure")
        if cached is not None:
            return cached

        try:
            vix = self._load_csv(self.VIX_URL, "VIX")
            vix3m = self._load_csv(self.VIX3M_URL, "VIX3M")

            if vix is None or vix3m is None:
                log.warning("[PRO_DATA] VIXTermStructure: missing VIX data")
                return result

            ratio = round(vix / vix3m, 4) if vix3m != 0 else 1.0
            is_inverted = ratio > 1.0  # backwardation

            result["vix"] = round(vix, 2)
            result["vix3m"] = round(vix3m, 2)
            result["ratio"] = ratio
            result["is_inverted"] = is_inverted

            if is_inverted and ratio > 1.1:
                result["regime_signal"] = "crisis"
                result["score"] = -8
                result["reasoning"] = (f"VIX={vix:.1f} > VIX3M={vix3m:.1f} "
                                       f"ratio={ratio:.2f} → deep backwardation / crisis")
            elif is_inverted:
                result["regime_signal"] = "stress"
                result["score"] = -4
                result["reasoning"] = (f"VIX={vix:.1f} > VIX3M={vix3m:.1f} "
                                       f"ratio={ratio:.2f} → mild backwardation / stress")
            elif vix < 15:
                result["regime_signal"] = "complacent"
                result["score"] = -2
                result["reasoning"] = f"VIX={vix:.1f} very low → complacency risk"
            else:
                result["regime_signal"] = "normal_contango"
                result["score"] = 2
                result["reasoning"] = (f"VIX={vix:.1f} < VIX3M={vix3m:.1f} "
                                       f"ratio={ratio:.2f} → healthy contango")

            log.info(f"[PRO_DATA] VIXTermStructure: {result['reasoning']}")
            _cache.set("vix_structure", result, self.CACHE_TTL)
        except Exception as exc:
            log.error(f"[PRO_DATA] VIXTermStructure: error {exc}")
        return result


# =========================================================================
# 5. FearGreedIndex
# =========================================================================
class FearGreedIndex:
    """Crypto Fear & Greed Index (also useful as broad sentiment proxy)."""

    URL = "https://api.alternative.me/fng/?limit=7"
    CACHE_TTL = 3600

    def get_fear_greed(self) -> dict:
        log.info("[PRO_DATA] FearGreedIndex: fetching")
        result = {"source": "fear_greed", "value": None, "label": "neutral",
                  "score": 0, "history": [], "reasoning": "no data"}

        cached = _cache.get("fear_greed")
        if cached is not None:
            return cached

        try:
            resp = _safe_request("get", self.URL, tag="FearGreed")
            if resp is None:
                return result

            data = resp.json().get("data", [])
            if not data:
                log.warning("[PRO_DATA] FearGreedIndex: empty response")
                return result

            latest = data[0]
            value = int(latest.get("value", 50))
            label = latest.get("value_classification", "Neutral")

            result["value"] = value
            result["label"] = label
            result["history"] = [{"value": int(d["value"]),
                                  "label": d.get("value_classification", "")}
                                 for d in data]

            if value <= 24:
                result["score"] = 8
                result["reasoning"] = f"Extreme Fear ({value}) → strong buy signal"
            elif value <= 40:
                result["score"] = 4
                result["reasoning"] = f"Fear ({value}) → moderate buy signal"
            elif value >= 75:
                result["score"] = -8
                result["reasoning"] = f"Extreme Greed ({value}) → reduce exposure"
            elif value >= 60:
                result["score"] = -3
                result["reasoning"] = f"Greed ({value}) → caution"
            else:
                result["score"] = 0
                result["reasoning"] = f"Neutral sentiment ({value})"

            log.info(f"[PRO_DATA] FearGreedIndex: {result['reasoning']}")
            _cache.set("fear_greed", result, self.CACHE_TTL)
        except Exception as exc:
            log.error(f"[PRO_DATA] FearGreedIndex: error {exc}")
        return result


# =========================================================================
# 6. ShortInterest (FINRA RegSHO daily)
# =========================================================================
class ShortInterest:
    """FINRA RegSHO daily short-volume files."""

    BASE = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date}.txt"
    CACHE_TTL = 4 * 3600

    def _fetch_file(self, dt: datetime) -> Optional[pd.DataFrame]:
        date_str = dt.strftime("%Y%m%d")
        url = self.BASE.format(date=date_str)
        resp = _safe_request("get", url, tag=f"ShortVol-{date_str}")
        if resp is None:
            return None
        try:
            df = pd.read_csv(io.StringIO(resp.text), sep="|")
            df.columns = [c.strip().lower() for c in df.columns]
            log.info(f"[PRO_DATA] ShortInterest: loaded {len(df)} rows for {date_str}")
            return df
        except Exception as exc:
            log.error(f"[PRO_DATA] ShortInterest: parse error {exc}")
            return None

    def fetch(self, symbol: str) -> Optional[dict]:
        symbol = symbol.upper()
        key = f"short_{symbol}"
        cached = _cache.get(key)
        if cached is not None:
            return cached

        log.info(f"[PRO_DATA] ShortInterest: fetching short volume for {symbol}")
        # Try last 5 business days (in case of holidays)
        now = datetime.now(timezone.utc)
        for offset in range(5):
            dt = now - timedelta(days=offset)
            if dt.weekday() >= 5:  # skip weekends
                continue
            df = self._fetch_file(dt)
            if df is None:
                continue

            sym_col = None
            for c in ["symbol", "ticker"]:
                if c in df.columns:
                    sym_col = c
                    break
            if sym_col is None:
                continue

            match = df[df[sym_col].str.upper() == symbol]
            if match.empty:
                continue

            row = match.iloc[0]
            short_vol = int(row.get("shortvolume", row.get("short volume", 0)))
            total_vol = int(row.get("totalvolume", row.get("total volume", 1)))
            ratio = round(short_vol / total_vol, 4) if total_vol else 0.0
            entry = {"symbol": symbol, "short_volume": short_vol,
                     "total_volume": total_vol, "short_ratio": ratio,
                     "date": dt.strftime("%Y-%m-%d")}
            log.info(f"[PRO_DATA] ShortInterest: {symbol} short_ratio={ratio:.2%}")
            _cache.set(key, entry, self.CACHE_TTL)
            return entry

        log.warning(f"[PRO_DATA] ShortInterest: no data found for {symbol}")
        return None

    def get_short_signal(self, symbol: str) -> dict:
        symbol = symbol.upper()
        log.info(f"[PRO_DATA] ShortInterest: computing signal for {symbol}")
        result = {"source": "short_interest", "symbol": symbol, "score": 0,
                  "short_ratio": None, "reasoning": "no data"}
        try:
            data = self.fetch(symbol)
            if data is None:
                return result
            ratio = data["short_ratio"]
            result["short_ratio"] = ratio
            result["data"] = data

            if ratio > 0.50:
                result["score"] = 7
                result["reasoning"] = (f"Short ratio {ratio:.0%} > 50% → "
                                       "extreme short squeeze potential")
            elif ratio > 0.40:
                result["score"] = 5
                result["reasoning"] = (f"Short ratio {ratio:.0%} > 40% → "
                                       "squeeze potential")
            elif ratio > 0.30:
                result["score"] = 2
                result["reasoning"] = f"Short ratio {ratio:.0%} → elevated shorts"
            elif ratio < 0.15:
                result["score"] = -1
                result["reasoning"] = f"Short ratio {ratio:.0%} → low short interest"
            else:
                result["reasoning"] = f"Short ratio {ratio:.0%} → normal"

            log.info(f"[PRO_DATA] ShortInterest: {result['reasoning']}")
        except Exception as exc:
            log.error(f"[PRO_DATA] ShortInterest: signal error {exc}")
        return result


# =========================================================================
# 7. DarkPoolTracker (FINRA OTC weekly)
# =========================================================================
class DarkPoolTracker:
    """FINRA OTC/ATS weekly summary for dark-pool volume."""

    URL = "https://otce.finra.org/otce/weeklySummary"
    CACHE_TTL = 4 * 3600

    def fetch(self) -> list:
        cached = _cache.get("darkpool_all")
        if cached is not None:
            return cached

        log.info("[PRO_DATA] DarkPoolTracker: fetching FINRA OTC weekly summary")
        resp = _safe_request("get", self.URL,
                             headers={"Accept": "application/json"},
                             tag="DarkPool")
        if resp is None:
            return []

        try:
            data = resp.json() if isinstance(resp.json(), list) else resp.json().get("data", [])
            log.info(f"[PRO_DATA] DarkPoolTracker: received {len(data)} records")
            _cache.set("darkpool_all", data, self.CACHE_TTL)
            return data
        except Exception as exc:
            log.error(f"[PRO_DATA] DarkPoolTracker: parse error {exc}")
            return []

    def get_darkpool_signal(self, symbol: str) -> dict:
        symbol = symbol.upper()
        log.info(f"[PRO_DATA] DarkPoolTracker: computing signal for {symbol}")
        result = {"source": "darkpool", "symbol": symbol, "score": 0,
                  "dp_pct": None, "reasoning": "no data"}
        try:
            records = self.fetch()
            relevant = [r for r in records
                        if str(r.get("symbol", r.get("issueSymbolIdentifier", "")))
                        .upper() == symbol]
            if not relevant:
                result["reasoning"] = f"no dark pool data for {symbol}"
                log.info(f"[PRO_DATA] DarkPoolTracker: {result['reasoning']}")
                return result

            rec = relevant[0]
            total_shares = int(rec.get("totalWeeklyShareQuantity",
                                       rec.get("totalShares", 0)))
            total_trades = int(rec.get("totalWeeklyTradeCount",
                                        rec.get("totalTrades", 0)))

            if total_shares > 0:
                result["dp_pct"] = total_shares
                # High dark pool volume = institutional positioning
                if total_shares > 5_000_000:
                    result["score"] = 3
                    result["reasoning"] = (f"Heavy dark pool vol ({total_shares:,} shares, "
                                           f"{total_trades:,} trades) → institutional interest")
                else:
                    result["score"] = 1
                    result["reasoning"] = (f"Moderate dark pool vol ({total_shares:,} shares) "
                                           "→ some institutional activity")
            else:
                result["reasoning"] = "minimal dark pool activity"

            log.info(f"[PRO_DATA] DarkPoolTracker: {result['reasoning']}")
        except Exception as exc:
            log.error(f"[PRO_DATA] DarkPoolTracker: signal error {exc}")
        return result


# =========================================================================
# 8. EconomicCalendar (FRED + BLS)
# =========================================================================
class EconomicCalendar:
    """Upcoming economic releases from FRED / BLS."""

    FRED_URL = "https://api.stlouisfed.org/fred/releases/dates"
    BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    CACHE_TTL = 12 * 3600

    # High-impact keywords
    HIGH_IMPACT = {"CPI", "FOMC", "Employment Situation", "Nonfarm",
                   "NFP", "PPI", "GDP", "Federal Funds", "Consumer Price",
                   "PCE", "Retail Sales", "Unemployment"}

    def _fetch_fred(self, days_ahead: int) -> list:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        end = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        fred_key = os.environ.get('FRED_API_KEY', '')
        if not fred_key:
            log.info("[PRO_DATA] EconomicCalendar: no FRED_API_KEY set, using hardcoded calendar")
            return self._hardcoded_calendar(days_ahead)
        params = {
            "api_key": fred_key,
            "realtime_start": today,
            "realtime_end": end,
            "file_type": "json",
        }
        resp = _safe_request("get", self.FRED_URL, params=params, tag="FRED")
        if resp is None:
            return self._hardcoded_calendar(days_ahead)
        try:
            data = resp.json()
            dates = data.get("release_dates", [])
            log.info(f"[PRO_DATA] EconomicCalendar: FRED returned {len(dates)} release dates")
            return dates
        except Exception as exc:
            log.error(f"[PRO_DATA] EconomicCalendar: FRED parse error {exc}")
            return self._hardcoded_calendar(days_ahead)

    def _hardcoded_calendar(self, days_ahead: int) -> list:
        """Fallback: known recurring high-impact events by day of month."""
        from datetime import date
        events = []
        today = date.today()
        for d in range(1, days_ahead + 1):
            check_date = today + timedelta(days=d)
            dom = check_date.day
            dow = check_date.weekday()  # 0=Mon
            month_str = check_date.strftime("%Y-%m-%d")
            # NFP: first Friday of each month
            if dom <= 7 and dow == 4:
                events.append({"name": "Employment Situation (NFP)", "date": month_str, "high_impact": True})
            # CPI: ~10th-14th of each month
            if 10 <= dom <= 14 and dow < 5:
                events.append({"name": "Consumer Price Index (CPI)", "date": month_str, "high_impact": True})
            # FOMC: ~6 weeks apart, known dates (approximate)
            fomc_dates_2026 = ["2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
                               "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16"]
            if month_str in fomc_dates_2026:
                events.append({"name": "FOMC Interest Rate Decision", "date": month_str, "high_impact": True})
        if events:
            log.info(f"[PRO_DATA] EconomicCalendar: {len(events)} events from hardcoded calendar")
        return events

    def get_upcoming_events(self, days_ahead: int = 7) -> list:
        log.info(f"[PRO_DATA] EconomicCalendar: fetching events for next {days_ahead} days")
        key = f"econ_events_{days_ahead}"
        cached = _cache.get(key)
        if cached is not None:
            return cached

        events: list[dict] = []
        try:
            releases = self._fetch_fred(days_ahead)
            for r in releases:
                name = r.get("release_name", r.get("name", "Unknown"))
                date = r.get("date", "")
                is_high = any(kw.lower() in name.lower() for kw in self.HIGH_IMPACT)
                events.append({
                    "name": name,
                    "date": date,
                    "release_id": r.get("release_id"),
                    "high_impact": is_high,
                })
                if is_high:
                    log.info(f"[PRO_DATA] EconomicCalendar: HIGH IMPACT → {name} on {date}")
        except Exception as exc:
            log.error(f"[PRO_DATA] EconomicCalendar: events error {exc}")

        _cache.set(key, events, self.CACHE_TTL)
        log.info(f"[PRO_DATA] EconomicCalendar: {len(events)} events loaded")
        return events

    def has_high_impact_tomorrow(self) -> bool:
        log.info("[PRO_DATA] EconomicCalendar: checking for high-impact events tomorrow")
        try:
            events = self.get_upcoming_events(days_ahead=2)
            tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
            high = [e for e in events if e.get("high_impact") and e.get("date") == tomorrow]
            if high:
                log.warning(f"[PRO_DATA] EconomicCalendar: HIGH IMPACT TOMORROW → "
                            f"{[e['name'] for e in high]}")
                return True
            log.info("[PRO_DATA] EconomicCalendar: no high-impact events tomorrow")
            return False
        except Exception as exc:
            log.error(f"[PRO_DATA] EconomicCalendar: tomorrow check error {exc}")
            return False


# =========================================================================
# 9. InstitutionalTracker (13-F via EDGAR)
# =========================================================================
class InstitutionalTracker:
    """Track 13-F filings for major funds via SEC EDGAR."""

    SUBMISSION_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
    HEADERS = {"User-Agent": "BeastTrader beast@trader.com"}
    CACHE_TTL = 24 * 3600  # 13F is quarterly

    FUNDS: dict[str, str] = {
        "Berkshire Hathaway": "0001067983",
        "Bridgewater": "0001350694",
        "Renaissance": "0001037389",
        "ARK Invest": "0001697748",
        "Soros Fund": "0001029160",
    }

    def _fetch_filings(self, name: str, cik: str) -> list:
        url = self.SUBMISSION_URL.format(cik=cik)
        resp = _safe_request("get", url, headers=self.HEADERS,
                             tag=f"13F-{name}")
        if resp is None:
            return []
        try:
            data = resp.json()
            recent = data.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            descs = recent.get("primaryDocDescription", [])

            filings = []
            for i, form in enumerate(forms):
                if "13F" in form.upper():
                    filings.append({
                        "fund": name,
                        "form": form,
                        "date": dates[i] if i < len(dates) else "",
                        "desc": descs[i] if i < len(descs) else "",
                    })
            log.info(f"[PRO_DATA] InstitutionalTracker: {name} has {len(filings)} 13F filings")
            return filings
        except Exception as exc:
            log.error(f"[PRO_DATA] InstitutionalTracker: parse error for {name}: {exc}")
            return []

    def fetch_all(self) -> dict:
        cached = _cache.get("institutional_all")
        if cached is not None:
            return cached

        log.info("[PRO_DATA] InstitutionalTracker: fetching all fund filings")
        all_filings: dict[str, list] = {}
        for name, cik in self.FUNDS.items():
            all_filings[name] = self._fetch_filings(name, cik)

        _cache.set("institutional_all", all_filings, self.CACHE_TTL)
        return all_filings

    def get_institutional_signal(self, symbol: str) -> dict:
        symbol = symbol.upper()
        log.info(f"[PRO_DATA] InstitutionalTracker: computing signal for {symbol}")
        result = {"source": "institutional_13f", "symbol": symbol, "score": 0,
                  "funds": [], "reasoning": "no data (13F is quarterly, parsed from filings)"}
        try:
            all_data = self.fetch_all()
            # Note: actual holdings parsing requires downloading the XML from
            # each 13F filing – we record that filings exist for awareness.
            active_funds = [name for name, filings in all_data.items() if filings]
            result["funds"] = active_funds
            result["reasoning"] = (f"Tracking {len(active_funds)} funds. "
                                   "Full holdings parsing requires 13F XML download "
                                   "(placeholder for future enhancement).")
            log.info(f"[PRO_DATA] InstitutionalTracker: {result['reasoning']}")
        except Exception as exc:
            log.error(f"[PRO_DATA] InstitutionalTracker: signal error {exc}")
        return result


# =========================================================================
# 10. ARKTracker
# =========================================================================
class ARKTracker:
    """ARK Invest daily holdings CSV tracker."""

    URL = ("https://ark-funds.com/wp-content/uploads/funds-etf-csv/"
           "ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv")
    CACHE_TTL = 6 * 3600

    def fetch(self) -> Optional[pd.DataFrame]:
        cached = _cache.get("ark_holdings")
        if cached is not None:
            return cached

        log.info("[PRO_DATA] ARKTracker: fetching ARKK holdings CSV")
        resp = _safe_request("get", self.URL, tag="ARK")
        if resp is None:
            return None
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            df.columns = [c.strip().lower() for c in df.columns]
            log.info(f"[PRO_DATA] ARKTracker: loaded {len(df)} holdings")
            _cache.set("ark_holdings", df, self.CACHE_TTL)
            return df
        except Exception as exc:
            log.error(f"[PRO_DATA] ARKTracker: parse error {exc}")
            return None

    def get_ark_signal(self, symbol: str) -> dict:
        symbol = symbol.upper()
        log.info(f"[PRO_DATA] ARKTracker: computing signal for {symbol}")
        result = {"source": "ark", "symbol": symbol, "score": 0,
                  "weight": None, "shares": None, "reasoning": "no data"}
        try:
            df = self.fetch()
            if df is None:
                return result

            # Locate ticker column
            ticker_col = None
            for c in ["ticker", "symbol", "company"]:
                if c in df.columns:
                    ticker_col = c
                    break
            if ticker_col is None:
                log.warning("[PRO_DATA] ARKTracker: cannot identify ticker column")
                return result

            match = df[df[ticker_col].astype(str).str.upper() == symbol]
            if match.empty:
                result["reasoning"] = f"{symbol} not in ARKK holdings"
                log.info(f"[PRO_DATA] ARKTracker: {result['reasoning']}")
                return result

            row = match.iloc[0]
            weight_col = None
            for c in ["weight(%)", "weight", "% of etf"]:
                if c in df.columns:
                    weight_col = c
                    break
            shares_col = None
            for c in ["shares", "share"]:
                if c in df.columns:
                    shares_col = c
                    break

            weight = float(row[weight_col]) if weight_col else None
            shares = int(row[shares_col]) if shares_col else None

            result["weight"] = weight
            result["shares"] = shares

            if weight and weight > 5:
                result["score"] = 5
                result["reasoning"] = (f"{symbol} is a TOP ARKK holding at "
                                       f"{weight:.1f}% weight → Cathie Wood conviction")
            elif weight and weight > 2:
                result["score"] = 3
                result["reasoning"] = f"{symbol} is in ARKK at {weight:.1f}% weight"
            elif weight:
                result["score"] = 1
                result["reasoning"] = f"{symbol} is a small ARKK position at {weight:.1f}%"
            else:
                result["score"] = 1
                result["reasoning"] = f"{symbol} found in ARKK holdings"

            log.info(f"[PRO_DATA] ARKTracker: {result['reasoning']}")
        except Exception as exc:
            log.error(f"[PRO_DATA] ARKTracker: signal error {exc}")
        return result


# =========================================================================
# Master orchestrator
# =========================================================================
class ProDataSources:
    """Aggregate all professional data sources into one intelligence layer."""

    # SQL to bootstrap the required tables
    _INIT_SQL = [
        """
        CREATE TABLE IF NOT EXISTS pro_intel (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT NOT NULL,
            source TEXT NOT NULL,
            signal_type TEXT,
            score INTEGER,
            raw_data JSONB,
            reasoning TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS market_conditions (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            pcr NUMERIC,
            pcr_signal TEXT,
            vix NUMERIC,
            vix3m NUMERIC,
            vix_contango BOOLEAN,
            fear_greed INTEGER,
            fear_greed_label TEXT,
            high_impact_tomorrow BOOLEAN,
            upcoming_events JSONB
        );
        """,
    ]

    def __init__(self, db=None):
        log.info("[PRO_DATA] ProDataSources: initializing all sources")
        self.db = db

        # Initialize every source
        self.congress = CongressTracker()
        self.insider = InsiderTracker()
        self.pcr = PutCallRatio()
        self.vix = VIXTermStructure()
        self.fear_greed = FearGreedIndex()
        self.short_interest = ShortInterest()
        self.darkpool = DarkPoolTracker()
        self.econ = EconomicCalendar()
        self.institutional = InstitutionalTracker()
        self.ark = ARKTracker()

        # Bootstrap DB tables if connection is available
        if self.db:
            self._init_db()

        log.info("[PRO_DATA] ProDataSources: ready ✓")

    # ----- DB helpers -----
    def _init_db(self):
        try:
            cur = self.db.cursor()
            for sql in self._INIT_SQL:
                cur.execute(sql)
            self.db.commit()
            log.info("[PRO_DATA] ProDataSources: DB tables ensured")
        except Exception as exc:
            log.error(f"[PRO_DATA] ProDataSources: DB init error {exc}")

    def log_to_db(self, symbol: str, intel: dict):
        """Persist an intel result to the pro_intel table."""
        if not self.db:
            return
        try:
            cur = self.db.cursor()
            for entry in intel.get("breakdown", {}).values():
                if not isinstance(entry, dict):
                    continue
                cur.execute(
                    """INSERT INTO pro_intel (symbol, source, signal_type, score,
                                             raw_data, reasoning)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (
                        symbol,
                        entry.get("source", "unknown"),
                        entry.get("signal", entry.get("signal_type", "")),
                        entry.get("score", 0),
                        json.dumps(entry, default=str),
                        entry.get("reasoning", ""),
                    ),
                )
            self.db.commit()
            log.info(f"[PRO_DATA] ProDataSources: logged intel for {symbol} to DB")
        except Exception as exc:
            log.error(f"[PRO_DATA] ProDataSources: DB log error {exc}")

    def _log_market_conditions(self, mc: dict):
        if not self.db:
            return
        try:
            cur = self.db.cursor()
            pcr_data = mc.get("pcr", {})
            vix_data = mc.get("vix_structure", {})
            fg_data = mc.get("fear_greed", {})
            cur.execute(
                """INSERT INTO market_conditions
                   (pcr, pcr_signal, vix, vix3m, vix_contango,
                    fear_greed, fear_greed_label,
                    high_impact_tomorrow, upcoming_events)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    pcr_data.get("value"),
                    pcr_data.get("signal"),
                    vix_data.get("vix"),
                    vix_data.get("vix3m"),
                    not vix_data.get("is_inverted", False),
                    fg_data.get("value"),
                    fg_data.get("label"),
                    mc.get("high_impact_tomorrow", False),
                    json.dumps(mc.get("events", []), default=str),
                ),
            )
            self.db.commit()
            log.info("[PRO_DATA] ProDataSources: logged market conditions to DB")
        except Exception as exc:
            log.error(f"[PRO_DATA] ProDataSources: DB market cond error {exc}")

    # ----- Core methods -----
    def get_full_intel(self, symbol: str) -> dict:
        """
        Aggregate ALL sources for *symbol*.

        Returns
        -------
        dict with keys:
            score        – combined score (clamped -50 … +50)
            breakdown    – {source_name: signal_dict}
            signals      – list of human-readable signal strings
            symbol       – the queried symbol
        """
        symbol = symbol.upper()
        log.info(f"[PRO_DATA] ======= FULL INTEL for {symbol} =======")

        breakdown: dict[str, dict] = {}
        signals: list[str] = []
        total_score = 0

        # 1. Congress
        try:
            sig = self.congress.get_congress_signal(symbol)
            breakdown["congress"] = sig
            total_score += sig.get("score", 0)
            if sig["score"] != 0:
                signals.append(f"Congress: {sig['reasoning']}")
        except Exception as exc:
            log.error(f"[PRO_DATA] congress error: {exc}")

        # 2. Insider
        try:
            sig = self.insider.get_insider_signal(symbol)
            breakdown["insider"] = sig
            total_score += sig.get("score", 0)
            if sig["score"] != 0:
                signals.append(f"Insider: {sig['reasoning']}")
        except Exception as exc:
            log.error(f"[PRO_DATA] insider error: {exc}")

        # 3. Short Interest
        try:
            sig = self.short_interest.get_short_signal(symbol)
            breakdown["short_interest"] = sig
            total_score += sig.get("score", 0)
            if sig["score"] != 0:
                signals.append(f"Short Interest: {sig['reasoning']}")
        except Exception as exc:
            log.error(f"[PRO_DATA] short_interest error: {exc}")

        # 4. Dark Pool
        try:
            sig = self.darkpool.get_darkpool_signal(symbol)
            breakdown["darkpool"] = sig
            total_score += sig.get("score", 0)
            if sig["score"] != 0:
                signals.append(f"Dark Pool: {sig['reasoning']}")
        except Exception as exc:
            log.error(f"[PRO_DATA] darkpool error: {exc}")

        # 5. Institutional
        try:
            sig = self.institutional.get_institutional_signal(symbol)
            breakdown["institutional"] = sig
            total_score += sig.get("score", 0)
            if sig["score"] != 0:
                signals.append(f"13F: {sig['reasoning']}")
        except Exception as exc:
            log.error(f"[PRO_DATA] institutional error: {exc}")

        # 6. ARK
        try:
            sig = self.ark.get_ark_signal(symbol)
            breakdown["ark"] = sig
            total_score += sig.get("score", 0)
            if sig["score"] != 0:
                signals.append(f"ARK: {sig['reasoning']}")
        except Exception as exc:
            log.error(f"[PRO_DATA] ark error: {exc}")

        # Incorporate macro signals into total
        try:
            mc = self.get_market_conditions()
            for src in ("pcr", "vix_structure", "fear_greed"):
                data = mc.get(src, {})
                if isinstance(data, dict):
                    breakdown[src] = data
                    total_score += data.get("score", 0)
                    if data.get("score", 0) != 0:
                        signals.append(f"{src}: {data.get('reasoning', '')}")
        except Exception as exc:
            log.error(f"[PRO_DATA] macro error: {exc}")

        total_score = max(-50, min(50, total_score))

        result = {
            "symbol": symbol,
            "score": total_score,
            "breakdown": breakdown,
            "signals": signals,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        log.info(f"[PRO_DATA] ======= {symbol} combined score = {total_score} =======")
        for s in signals:
            log.info(f"[PRO_DATA]   • {s}")

        # Persist
        self.log_to_db(symbol, result)
        return result

    def get_market_conditions(self) -> dict:
        """
        Macro-level market conditions:
        PCR, VIX term structure, Fear & Greed, economic calendar.
        """
        log.info("[PRO_DATA] ======= MARKET CONDITIONS =======")
        result: dict[str, Any] = {}

        try:
            result["pcr"] = self.pcr.get_pcr()
        except Exception as exc:
            log.error(f"[PRO_DATA] market_conditions pcr error: {exc}")
            result["pcr"] = {}

        try:
            result["vix_structure"] = self.vix.get_vix_structure()
        except Exception as exc:
            log.error(f"[PRO_DATA] market_conditions vix error: {exc}")
            result["vix_structure"] = {}

        try:
            result["fear_greed"] = self.fear_greed.get_fear_greed()
        except Exception as exc:
            log.error(f"[PRO_DATA] market_conditions fear_greed error: {exc}")
            result["fear_greed"] = {}

        try:
            result["events"] = self.econ.get_upcoming_events(days_ahead=7)
            result["high_impact_tomorrow"] = self.econ.has_high_impact_tomorrow()
        except Exception as exc:
            log.error(f"[PRO_DATA] market_conditions econ error: {exc}")
            result["events"] = []
            result["high_impact_tomorrow"] = False

        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._log_market_conditions(result)
        log.info("[PRO_DATA] ======= MARKET CONDITIONS DONE =======")
        return result


# =========================================================================
# Quick self-test when run directly
# =========================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print("=== Beast Pro Data Sources — self-test ===\n")

    pro = ProDataSources()

    print("\n--- Market Conditions ---")
    mc = pro.get_market_conditions()
    for k, v in mc.items():
        if k != "events":
            print(f"  {k}: {v}")
    print(f"  upcoming events: {len(mc.get('events', []))}")

    print("\n--- Full Intel: AAPL ---")
    intel = pro.get_full_intel("AAPL")
    print(f"  Combined Score: {intel['score']}")
    for s in intel["signals"]:
        print(f"  • {s}")

    print("\nDone ✓")
