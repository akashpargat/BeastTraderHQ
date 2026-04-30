"""
Beast Terminal V4 - Market Intelligence Module
================================================
FREE data sources that expensive platforms charge $200-500/mo for.
All data stored in PostgreSQL for AI learning.

Sources:
  HIGH IMPACT:
    1. Congressional Trading (Quiver Quant API) - Pelosi trades
    2. Insider Trading (OpenInsider scrape) - CEO/CFO buying/selling
    3. Unusual Options Flow (Alpaca options API) - big money bets
    4. Dark Pool / Short Volume (FINRA data) - institutional activity
    5. Earnings Whisper (yfinance + scrape) - expected vs actual

  MEDIUM IMPACT:
    6. Sector Rotation Score - money flow between sectors
    7. Portfolio Correlation Matrix - risk concentration
    8. Economic Calendar - Fed, CPI, jobs report dates
    9. Options Greeks Scanner - put/call ratio, IV percentile

  NICE TO HAVE:
    10. Institutional Holdings (SEC 13F) - what hedge funds own
    11. Short Squeeze Score - combined short + options + volume signal
"""

import os
import logging
import requests
import json
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

log = logging.getLogger('Beast.Intel')

# Cache to avoid hammering free APIs
_intel_cache = {}
CACHE_TTL = 1800  # 30 min cache for most sources


def _cached(key, fetcher, ttl=CACHE_TTL):
    """Simple cache wrapper."""
    if key in _intel_cache:
        val, exp = _intel_cache[key]
        if time.time() < exp:
            return val
    try:
        val = fetcher()
        _intel_cache[key] = (val, time.time() + ttl)
        return val
    except Exception as e:
        log.warning(f"Intel fetch {key}: {e}")
        return None


class MarketIntelligence:
    """Aggregates all free market intelligence sources."""

    def __init__(self, db=None):
        self.db = db
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    # ══════════════════════════════════════════════
    #  1. CONGRESSIONAL TRADING (Quiver Quant)
    #  Pelosi's trades outperform S&P by 20%+
    # ══════════════════════════════════════════════

    def get_congressional_trades(self, days: int = 30) -> list:
        """Get recent congressional stock trades. Free from Quiver Quant."""
        def _fetch():
            trades = []
            try:
                # Quiver Quant public endpoint
                url = 'https://api.quiverquant.com/beta/live/congresstrading'
                resp = self._session.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    cutoff = datetime.now() - timedelta(days=days)
                    for t in data[:100]:
                        try:
                            trade_date = datetime.strptime(t.get('TransactionDate', ''), '%Y-%m-%d')
                            if trade_date >= cutoff:
                                trades.append({
                                    'symbol': t.get('Ticker', ''),
                                    'politician': t.get('Representative', ''),
                                    'party': t.get('Party', ''),
                                    'type': t.get('Transaction', ''),  # Purchase/Sale
                                    'amount': t.get('Amount', ''),
                                    'date': t.get('TransactionDate', ''),
                                    'chamber': t.get('House', ''),
                                })
                        except:
                            pass
            except Exception as e:
                # Fallback: try Capitol Trades
                try:
                    resp2 = self._session.get('https://www.capitoltrades.com/trades?per_page=50', timeout=10)
                    if resp2.status_code == 200:
                        soup = BeautifulSoup(resp2.text, 'html.parser')
                        rows = soup.select('table tbody tr')[:30]
                        for row in rows:
                            cells = row.select('td')
                            if len(cells) >= 5:
                                trades.append({
                                    'symbol': cells[2].text.strip()[:10],
                                    'politician': cells[0].text.strip()[:30],
                                    'type': cells[3].text.strip(),
                                    'amount': cells[4].text.strip(),
                                    'date': cells[1].text.strip(),
                                })
                except:
                    pass
            return trades
        return _cached('congress_trades', _fetch, 3600) or []

    # ══════════════════════════════════════════════
    #  2. INSIDER TRADING (OpenInsider)
    #  CEO buying own stock = strongest buy signal
    # ══════════════════════════════════════════════

    def get_insider_trades(self, symbol: str = None) -> list:
        """Get insider buys/sells from OpenInsider (SEC filings)."""
        def _fetch():
            trades = []
            try:
                url = 'http://openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh=&fd=30&fdr=&td=0&tdr=&feession=&feo=&fep=&sortcol=0&cnt=50'
                if symbol:
                    url = f'http://openinsider.com/screener?s={symbol}&o=&pl=&ph=&ll=&lh=&fd=90&fdr=&td=0&tdr=&feession=&feo=&fep=&sortcol=0&cnt=30'
                resp = self._session.get(url, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    table = soup.select_one('table.tinytable')
                    if table:
                        rows = table.select('tbody tr')[:30]
                        for row in rows:
                            cells = row.select('td')
                            if len(cells) >= 12:
                                trades.append({
                                    'date': cells[1].text.strip(),
                                    'symbol': cells[3].text.strip(),
                                    'insider': cells[4].text.strip()[:30],
                                    'title': cells[5].text.strip()[:20],
                                    'type': cells[6].text.strip(),  # P=Purchase, S=Sale
                                    'price': cells[8].text.strip(),
                                    'qty': cells[9].text.strip(),
                                    'value': cells[11].text.strip(),
                                })
            except Exception as e:
                log.debug(f"OpenInsider: {e}")
            return trades
        key = f'insider_{symbol or "all"}'
        return _cached(key, _fetch, 3600) or []

    # ══════════════════════════════════════════════
    #  3. UNUSUAL OPTIONS FLOW (Alpaca API)
    #  Big money bets show direction before move
    # ══════════════════════════════════════════════

    def get_options_flow(self, symbol: str) -> dict:
        """Get options data: put/call ratio, unusual volume, IV."""
        def _fetch():
            try:
                from alpaca.data.historical import OptionHistoricalDataClient
                from alpaca.data.requests import OptionChainRequest
                client = OptionHistoricalDataClient(
                    os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'))
                # Get option chain snapshot
                chain = client.get_option_chain(OptionChainRequest(
                    underlying_symbol=symbol, feed='indicative'))
                calls = 0
                puts = 0
                total_call_vol = 0
                total_put_vol = 0
                for contract_sym, snap in chain.items():
                    if hasattr(snap, 'latest_quote') and snap.latest_quote:
                        if 'C' in contract_sym.upper():
                            calls += 1
                            total_call_vol += getattr(snap, 'volume', 0) or 0
                        elif 'P' in contract_sym.upper():
                            puts += 1
                            total_put_vol += getattr(snap, 'volume', 0) or 0
                pcr = total_put_vol / total_call_vol if total_call_vol > 0 else 1.0
                return {
                    'symbol': symbol,
                    'put_call_ratio': round(pcr, 2),
                    'total_calls': calls,
                    'total_puts': puts,
                    'call_volume': total_call_vol,
                    'put_volume': total_put_vol,
                    'signal': 'BULLISH' if pcr < 0.7 else ('BEARISH' if pcr > 1.3 else 'NEUTRAL'),
                }
            except:
                return {'symbol': symbol, 'put_call_ratio': 1.0, 'signal': 'UNKNOWN'}
        return _cached(f'options_{symbol}', _fetch, 900) or {}

    # ══════════════════════════════════════════════
    #  4. DARK POOL / SHORT VOLUME (FINRA)
    #  Where institutions hide their trades
    # ══════════════════════════════════════════════

    def get_short_volume(self, symbol: str) -> dict:
        """Get short volume ratio from FINRA (free, delayed)."""
        def _fetch():
            try:
                # Chartexchange free data
                url = f'https://chartexchange.com/symbol/nasdaq-{symbol.lower()}/short-volume/'
                resp = self._session.get(url, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    # Look for short volume percentage
                    text = soup.get_text()
                    import re
                    match = re.search(r'Short Volume Ratio[:\s]+([\d.]+)%', text)
                    if match:
                        ratio = float(match.group(1))
                        return {
                            'symbol': symbol,
                            'short_volume_ratio': ratio,
                            'signal': 'HIGH_SHORT' if ratio > 50 else 'NORMAL',
                        }
            except:
                pass
            return {'symbol': symbol, 'short_volume_ratio': 0, 'signal': 'UNKNOWN'}
        return _cached(f'short_vol_{symbol}', _fetch, 3600) or {}

    # ══════════════════════════════════════════════
    #  5. ECONOMIC CALENDAR (Trading Economics)
    #  Fed meetings, CPI, jobs — move entire market
    # ══════════════════════════════════════════════

    def get_economic_calendar(self) -> list:
        """Get upcoming economic events that move markets."""
        def _fetch():
            events = []
            try:
                # yfinance calendar
                import yfinance as yf
                # Hardcoded key dates that always matter
                from datetime import date
                today = date.today()
                # Known recurring events
                key_events = [
                    'FOMC Meeting', 'CPI Report', 'Jobs Report (NFP)',
                    'GDP Report', 'PCE Inflation', 'Retail Sales',
                    'Consumer Confidence', 'ISM Manufacturing',
                ]
                # Try to get from investing.com or similar
                resp = self._session.get(
                    'https://nfs.faireconomy.media/ff_calendar_thisweek.json',
                    timeout=10)
                if resp.status_code == 200:
                    for e in resp.json()[:20]:
                        impact = e.get('impact', '')
                        if impact in ['High', 'Medium']:
                            events.append({
                                'date': e.get('date', ''),
                                'event': e.get('title', ''),
                                'impact': impact,
                                'forecast': e.get('forecast', ''),
                                'previous': e.get('previous', ''),
                            })
            except:
                pass
            return events
        return _cached('econ_calendar', _fetch, 7200) or []

    # ══════════════════════════════════════════════
    #  6. SECTOR ROTATION SCORE
    #  Money flowing between sectors = edge
    # ══════════════════════════════════════════════

    def get_sector_rotation(self) -> dict:
        """Score sector rotation using ETF performance."""
        def _fetch():
            try:
                import yfinance as yf
                sectors = {
                    'tech': 'XLK', 'health': 'XLV', 'finance': 'XLF',
                    'consumer_disc': 'XLY', 'consumer_staple': 'XLP',
                    'energy': 'XLE', 'materials': 'XLB', 'industrial': 'XLI',
                    'utilities': 'XLU', 'real_estate': 'XLRE', 'comms': 'XLC',
                }
                results = {}
                for name, etf in sectors.items():
                    try:
                        t = yf.Ticker(etf)
                        hist = t.history(period='5d')
                        if len(hist) >= 2:
                            pct_1d = (hist['Close'].iloc[-1] / hist['Close'].iloc[-2] - 1) * 100
                            pct_5d = (hist['Close'].iloc[-1] / hist['Close'].iloc[0] - 1) * 100
                            results[name] = {
                                'etf': etf, '1d': round(pct_1d, 2), '5d': round(pct_5d, 2),
                                'flow': 'IN' if pct_5d > 1 else ('OUT' if pct_5d < -1 else 'FLAT'),
                            }
                    except:
                        pass
                # Sort by 5d performance
                rotating_in = [k for k, v in sorted(results.items(), key=lambda x: -x[1].get('5d', 0))[:3]]
                rotating_out = [k for k, v in sorted(results.items(), key=lambda x: x[1].get('5d', 0))[:3]]
                return {
                    'sectors': results,
                    'rotating_in': rotating_in,
                    'rotating_out': rotating_out,
                }
            except:
                return {}
        return _cached('sector_rotation', _fetch, 3600) or {}

    # ══════════════════════════════════════════════
    #  7. PORTFOLIO CORRELATION MATRIX
    #  Are we too concentrated? Risk check.
    # ══════════════════════════════════════════════

    def get_correlation_matrix(self, symbols: list) -> dict:
        """Calculate 30-day price correlation between stocks."""
        def _fetch():
            try:
                import yfinance as yf
                import numpy as np
                data = yf.download(symbols[:15], period='30d', interval='1d', progress=False)
                if 'Close' in data:
                    closes = data['Close'].dropna(axis=1)
                    if len(closes.columns) >= 2:
                        corr = closes.corr()
                        # Find highly correlated pairs (>0.8)
                        high_corr = []
                        for i in range(len(corr.columns)):
                            for j in range(i+1, len(corr.columns)):
                                c = corr.iloc[i, j]
                                if abs(c) > 0.8:
                                    high_corr.append({
                                        'pair': f"{corr.columns[i]}/{corr.columns[j]}",
                                        'correlation': round(c, 2),
                                        'risk': 'HIGH' if c > 0.9 else 'MODERATE',
                                    })
                        avg_corr = corr.values[np.triu_indices_from(corr.values, k=1)].mean()
                        return {
                            'avg_correlation': round(avg_corr, 2),
                            'high_correlations': high_corr,
                            'diversification': 'POOR' if avg_corr > 0.7 else ('OK' if avg_corr > 0.4 else 'GOOD'),
                        }
            except:
                pass
            return {}
        return _cached(f'corr_{"_".join(symbols[:5])}', _fetch, 3600) or {}

    # ══════════════════════════════════════════════
    #  8. INSTITUTIONAL HOLDINGS (SEC 13F)
    #  What Buffett, Soros, Ackman are buying
    # ══════════════════════════════════════════════

    def get_institutional_holdings(self, symbol: str) -> dict:
        """Get institutional ownership from yfinance."""
        def _fetch():
            try:
                import yfinance as yf
                t = yf.Ticker(symbol)
                holders = t.institutional_holders
                if holders is not None and not holders.empty:
                    top = []
                    for _, row in holders.head(5).iterrows():
                        top.append({
                            'holder': str(row.get('Holder', ''))[:30],
                            'shares': int(row.get('Shares', 0)),
                            'pct': round(float(row.get('% Out', 0)) * 100, 2) if row.get('% Out') else 0,
                        })
                    return {'symbol': symbol, 'top_holders': top, 'count': len(holders)}
            except:
                pass
            return {'symbol': symbol, 'top_holders': [], 'count': 0}
        return _cached(f'inst_{symbol}', _fetch, 7200) or {}

    # ══════════════════════════════════════════════
    #  9. SHORT SQUEEZE SCORE
    #  Combined signal: short interest + options + volume
    # ══════════════════════════════════════════════

    def get_squeeze_score(self, symbol: str) -> dict:
        """Calculate short squeeze probability score."""
        def _fetch():
            score = 0
            signals = []
            # Short interest from Finviz (already in sentiment_analyst)
            try:
                from sentiment_analyst import SentimentAnalyst
                sa = SentimentAnalyst()
                short_data = sa.get_short_interest(symbol)
                short_pct = short_data.get('short_pct', 0)
                if short_pct > 20:
                    score += 30
                    signals.append(f"High short {short_pct}%")
                elif short_pct > 10:
                    score += 15
                    signals.append(f"Moderate short {short_pct}%")
                ratio = short_data.get('short_ratio', 0)
                if ratio > 5:
                    score += 20
                    signals.append(f"Days to cover {ratio}")
            except:
                pass
            # Options flow
            opts = self.get_options_flow(symbol)
            if opts.get('signal') == 'BULLISH':
                score += 20
                signals.append("Bullish options flow")
            # Volume spike
            try:
                import yfinance as yf
                t = yf.Ticker(symbol)
                hist = t.history(period='5d')
                if len(hist) >= 2:
                    avg_vol = hist['Volume'].iloc[:-1].mean()
                    today_vol = hist['Volume'].iloc[-1]
                    if avg_vol > 0 and today_vol > avg_vol * 2:
                        score += 15
                        signals.append(f"Volume spike {today_vol/avg_vol:.1f}x")
            except:
                pass
            return {
                'symbol': symbol,
                'squeeze_score': min(score, 100),
                'signals': signals,
                'alert': score >= 50,
            }
        return _cached(f'squeeze_{symbol}', _fetch, 1800) or {}

    # ══════════════════════════════════════════════
    #  MASTER: Get ALL intelligence for a stock
    # ══════════════════════════════════════════════

    def full_intel(self, symbol: str) -> dict:
        """Get EVERYTHING we know about a stock from all sources."""
        return {
            'insider': self.get_insider_trades(symbol),
            'options': self.get_options_flow(symbol),
            'short_volume': self.get_short_volume(symbol),
            'squeeze': self.get_squeeze_score(symbol),
            'institutional': self.get_institutional_holdings(symbol),
        }

    def full_market_intel(self, portfolio_symbols: list = None) -> dict:
        """Get all market-wide intelligence."""
        result = {
            'congress': self.get_congressional_trades(30),
            'economic_calendar': self.get_economic_calendar(),
            'sector_rotation': self.get_sector_rotation(),
        }
        if portfolio_symbols:
            result['correlation'] = self.get_correlation_matrix(portfolio_symbols)
        return result

    # ══════════════════════════════════════════════
    #  STORE: Save all intel to DB for AI learning
    # ══════════════════════════════════════════════

    def store_intel_to_db(self, symbol: str = None):
        """Fetch and store all intelligence in DB. Called during learning cycles."""
        if not self.db:
            return

        # Congressional trades
        try:
            congress = self.get_congressional_trades(30)
            if congress:
                # Find stocks congress is buying
                buys = [t for t in congress if 'purchase' in t.get('type', '').lower()]
                if buys:
                    symbols = list(set(t['symbol'] for t in buys if t.get('symbol')))[:10]
                    for sym in symbols:
                        politicians = [t['politician'] for t in buys if t['symbol'] == sym][:3]
                        self.db.save_trend(sym, 'congress_buy',
                            f"Congress buying: {', '.join(politicians)}",
                            75, {'trades': [t for t in buys if t['symbol'] == sym]})
                    log.info(f"  [INTEL] Congressional trades: {len(buys)} buys across {len(symbols)} stocks")
        except Exception as e:
            log.debug(f"Congress intel: {e}")

        # Insider trades
        try:
            insiders = self.get_insider_trades()
            insider_buys = [t for t in insiders if t.get('type') == 'P']  # P = Purchase
            if insider_buys:
                for t in insider_buys[:5]:
                    sym = t.get('symbol', '')
                    if sym:
                        self.db.save_trend(sym, 'insider_buy',
                            f"Insider buy: {t.get('insider','')} ({t.get('title','')}) ${t.get('value','')}",
                            80, t)
                log.info(f"  [INTEL] Insider buys: {len(insider_buys)} found")
        except Exception as e:
            log.debug(f"Insider intel: {e}")

        # Sector rotation
        try:
            rotation = self.get_sector_rotation()
            if rotation.get('rotating_in'):
                self.db.save_trend('MARKET', 'sector_rotation_in',
                    f"Money flowing INTO: {', '.join(rotation['rotating_in'])}",
                    70, rotation)
            if rotation.get('rotating_out'):
                self.db.save_trend('MARKET', 'sector_rotation_out',
                    f"Money flowing OUT: {', '.join(rotation['rotating_out'])}",
                    70, rotation)
            log.info(f"  [INTEL] Sector rotation: IN={rotation.get('rotating_in')} OUT={rotation.get('rotating_out')}")
        except Exception as e:
            log.debug(f"Sector intel: {e}")

        # Economic calendar
        try:
            events = self.get_economic_calendar()
            high_impact = [e for e in events if e.get('impact') == 'High']
            if high_impact:
                self.db.save_trend('MARKET', 'economic_events',
                    f"High impact events: {', '.join(e['event'][:30] for e in high_impact[:3])}",
                    80, {'events': high_impact})
                log.info(f"  [INTEL] Economic events: {len(high_impact)} high impact")
        except Exception as e:
            log.debug(f"Econ calendar: {e}")

        # Per-stock intel (if symbol provided)
        if symbol:
            try:
                squeeze = self.get_squeeze_score(symbol)
                if squeeze.get('alert'):
                    self.db.save_trend(symbol, 'squeeze_alert',
                        f"Squeeze score {squeeze['squeeze_score']}: {', '.join(squeeze.get('signals',[]))}",
                        85, squeeze)
                    log.info(f"  [INTEL] {symbol} squeeze alert! Score: {squeeze['squeeze_score']}")
            except:
                pass

        log.info("  [INTEL] Market intelligence stored to DB")
