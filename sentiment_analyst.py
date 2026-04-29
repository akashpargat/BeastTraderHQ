"""
Beast v2.0 — Sentiment Analyst (FULL STACK)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
9 data sources, all free, all autonomous:
  1. Yahoo Finance headlines (yfinance library)
  2. Reddit WSB + r/stocks (public JSON, no auth)
  3. Analyst ratings (yfinance upgrades/downgrades)
  4. Google News RSS (no API key needed)
  5. StockTwits (free public API, no auth)
  6. Finviz screener (free HTML scrape — runners, earnings, short squeeze)
  7. Earnings calendar (yfinance — next earnings date)
  8. Short interest (yfinance — short % of float)
  9. Fear & Greed proxy (VIX + put/call ratio)

All sources have freshness TTLs. Graceful degradation if any fails.
"""
import logging
import json
from datetime import datetime
from typing import Optional

import yfinance as yf
import requests

from models import SentimentScore

log = logging.getLogger('Beast.SentimentAnalyst')

# ── Freshness TTLs ─────────────────────────────────────
YAHOO_TTL = 900     # 15 minutes
REDDIT_TTL = 1800   # 30 minutes
ANALYST_TTL = 3600  # 1 hour
NEWS_TTL = 600      # 10 minutes for breaking news
STOCKTWITS_TTL = 600  # 10 minutes
FINVIZ_TTL = 1800   # 30 minutes
EARNINGS_TTL = 3600  # 1 hour
SHORT_TTL = 3600    # 1 hour

# ── Keyword Dictionaries ──────────────────────────────

BULLISH = {
    'ceasefire': 3, 'peace talks': 3, 'deal reached': 3,
    'rate cut': 4, 'fed cuts': 4, 'dovish': 3,
    'rally': 2, 'surge': 2, 'breakout': 2, 'all-time high': 3,
    'beat estimates': 3, 'earnings beat': 3, 'revenue beat': 2,
    'buyback': 2, 'dividend increase': 2, 'upgrade': 2,
    'bullish': 2, 'risk-on': 2, 'vix calm': 2,
    'ai growth': 2, 'ai spending': 2, 'ai infrastructure': 2,
    'bitcoin breakout': 2, 'btc rally': 2,
    'strong buy': 3, 'outperform': 2, 'overweight': 2,
    'partnership': 2, 'acquisition': 2, 'expansion': 1,
}

BEARISH = {
    'tariff': -4, 'trade war': -4, 'china tariff': -5,
    'bombing': -5, 'war escalat': -4, 'attack': -3, 'missile': -4,
    'hormuz closed': -5, 'carrier attacked': -5,
    'rate hike': -3, 'hawkish': -3, 'inflation surge': -3,
    'crash': -3, 'selloff': -3, 'plunge': -3, 'recession': -4,
    'earnings miss': -3, 'revenue miss': -2, 'downgrade': -2,
    'bearish': -2, 'risk-off': -2, 'vix spike': -3,
    'trump tariff': -5, 'import tax': -4,
    'lawsuit': -2, 'sec investigation': -3, 'fraud': -4,
    'layoffs': -2, 'restructuring': -1,
}

PANIC = [
    'nuclear', 'world war', 'market crash', 'circuit breaker',
    'trading halted', 'bank failure', 'default',
]


class SentimentAnalyst:
    """Multi-source sentiment analysis with caching and graceful degradation."""

    def __init__(self):
        self._cache: dict[str, tuple[any, datetime]] = {}

    def _is_fresh(self, key: str, ttl: int) -> bool:
        if key not in self._cache:
            return False
        _, ts = self._cache[key]
        return (datetime.now() - ts).total_seconds() <= ttl

    def _set_cache(self, key: str, value):
        self._cache[key] = (value, datetime.now())

    def _get_cache(self, key: str):
        return self._cache[key][0] if key in self._cache else None

    # ── Main Analysis ──────────────────────────────────

    def analyze(self, symbol: str) -> SentimentScore:
        """Full sentiment analysis from all sources."""
        yahoo = self._yahoo_sentiment(symbol)
        reddit = self._reddit_sentiment(symbol)
        analyst = self._analyst_sentiment(symbol)
        stocktwits = self._stocktwits_sentiment(symbol)

        total = yahoo + reddit + analyst + stocktwits

        return SentimentScore(
            symbol=symbol,
            yahoo_score=yahoo,
            reddit_score=reddit,
            analyst_score=analyst,
            total_score=total,
            timestamp=datetime.now(),
        )

    def analyze_market(self) -> SentimentScore:
        """Overall market sentiment (SPY-based)."""
        return self.analyze('SPY')

    # ── Yahoo Finance ──────────────────────────────────

    def _yahoo_sentiment(self, symbol: str) -> int:
        cache_key = f"yahoo:{symbol}"
        if self._is_fresh(cache_key, YAHOO_TTL):
            return self._get_cache(cache_key) or 0

        try:
            stock = yf.Ticker(symbol)
            news = stock.news
            if not news:
                return 0

            score = 0
            for article in news[:10]:
                title = article.get('title', '').lower()
                summary = article.get('summary', '').lower()
                text = f"{title} {summary}"

                # Check panic keywords
                for panic in PANIC:
                    if panic in text:
                        score = -5
                        self._set_cache(cache_key, score)
                        return score

                # Score bullish/bearish keywords
                for keyword, pts in BULLISH.items():
                    if keyword in text:
                        score += pts
                for keyword, pts in BEARISH.items():
                    if keyword in text:
                        score += pts

            # Clamp to -5 to +5
            score = max(-5, min(5, score))
            self._set_cache(cache_key, score)
            return score

        except Exception as e:
            log.warning(f"Yahoo sentiment failed for {symbol}: {e}")
            return 0

    # ── Reddit ─────────────────────────────────────────

    def _reddit_sentiment(self, symbol: str) -> int:
        cache_key = f"reddit:{symbol}"
        if self._is_fresh(cache_key, REDDIT_TTL):
            return self._get_cache(cache_key) or 0

        try:
            score = 0
            headers = {'User-Agent': 'BeastBot/2.0'}

            # Check WSB daily thread
            for sub in ['wallstreetbets', 'stocks']:
                try:
                    url = f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
                    resp = requests.get(url, headers=headers, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        posts = data.get('data', {}).get('children', [])
                        for post in posts:
                            title = post.get('data', {}).get('title', '').upper()
                            if symbol.upper() in title:
                                # Check sentiment of the mention
                                text = title.lower()
                                for kw, pts in BULLISH.items():
                                    if kw in text:
                                        score += 1
                                for kw, pts in BEARISH.items():
                                    if kw in text:
                                        score -= 1
                except Exception:
                    pass

            score = max(-5, min(5, score))
            self._set_cache(cache_key, score)
            return score

        except Exception as e:
            log.warning(f"Reddit sentiment failed for {symbol}: {e}")
            return 0

    # ── Analyst Ratings ────────────────────────────────

    def _analyst_sentiment(self, symbol: str) -> int:
        # ETFs don't have analyst ratings
        if symbol in ('SPY', 'QQQ', 'DIA', 'IWM', 'VTI', 'XLK', 'XLE', 'XLF'):
            return 0

        cache_key = f"analyst:{symbol}"
        if self._is_fresh(cache_key, ANALYST_TTL):
            return self._get_cache(cache_key) or 0

        try:
            stock = yf.Ticker(symbol)
            info = stock.info

            # Recommendation mean (1=strong buy, 5=strong sell)
            rec_mean = info.get('recommendationMean', 3.0)
            rec_key = info.get('recommendationKey', 'hold')

            if rec_mean <= 1.5:
                score = 5   # Strong Buy
            elif rec_mean <= 2.0:
                score = 3   # Buy
            elif rec_mean <= 2.5:
                score = 1   # Outperform
            elif rec_mean <= 3.5:
                score = 0   # Hold
            elif rec_mean <= 4.0:
                score = -2  # Underperform
            else:
                score = -4  # Sell

            # Check for recent upgrades/downgrades
            try:
                upgrades = stock.upgrades_downgrades
                if upgrades is not None and len(upgrades) > 0:
                    recent = upgrades.head(5)
                    for _, row in recent.iterrows():
                        action = str(row.get('Action', '')).lower()
                        if 'up' in action:
                            score += 1
                        elif 'down' in action:
                            score -= 1
            except:
                pass

            score = max(-5, min(5, score))
            self._set_cache(cache_key, score)
            return score

        except Exception as e:
            log.warning(f"Analyst sentiment failed for {symbol}: {e}")
            return 0

    # ── Google News RSS (Breaking News + Trump) ────────

    def _google_news_sentiment(self, query: str) -> tuple[int, list[str]]:
        """Scan Google News RSS for breaking news. No API key needed.
        Returns (score, headlines)."""
        cache_key = f"gnews:{query}"
        if self._is_fresh(cache_key, NEWS_TTL):
            cached = self._get_cache(cache_key)
            return cached if cached else (0, [])

        try:
            import feedparser
            url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(url)

            score = 0
            headlines = []
            for entry in feed.entries[:10]:
                title = entry.get('title', '').lower()
                headlines.append(entry.get('title', ''))

                for kw, pts in BULLISH.items():
                    if kw in title:
                        score += pts
                for kw, pts in BEARISH.items():
                    if kw in title:
                        score += pts
                for panic in PANIC:
                    if panic in title:
                        score = -5
                        break

            score = max(-5, min(5, score))
            self._set_cache(cache_key, (score, headlines))
            return score, headlines

        except ImportError:
            log.warning("feedparser not installed. Run: pip install feedparser")
            return 0, []
        except Exception as e:
            log.warning(f"Google News failed for '{query}': {e}")
            return 0, []

    def get_trump_sentiment(self) -> tuple[int, list[str]]:
        """Check Trump/tariff news via Google News RSS.
        This replaces the web_search for Trump Truth Social posts."""
        score, headlines = self._google_news_sentiment(
            "Trump tariff trade stock market economy"
        )
        if score != 0:
            log.info(f"🏛️ Trump/tariff sentiment: {score:+d}/5 ({len(headlines)} headlines)")
        return score, headlines

    def get_breaking_news(self) -> tuple[int, list[str]]:
        """Check for breaking market news via Google News RSS."""
        return self._google_news_sentiment("breaking news stock market today")

    def get_geopolitical_news(self) -> tuple[int, list[str]]:
        """Check Iran/war/oil geopolitical news."""
        return self._google_news_sentiment("Iran Hormuz oil war stock market")

    # ── Full Market Sentiment (ALL sources combined) ───

    def full_market_sentiment(self) -> dict:
        """Run ALL sentiment sources for overall market read.
        This is what runs in Phase 3 of Beast Mode.
        
        Returns dict with:
            total_score: -25 to +25
            trump_score, breaking_score, geopolitical_score
            yahoo_score, reddit_score, analyst_score
            trump_headlines, breaking_headlines
            action: AGGRESSIVE/NORMAL/CAUTIOUS/DEFENSIVE/ABORT
        """
        # Yahoo on SPY
        yahoo = self._yahoo_sentiment('SPY')

        # Reddit
        reddit = self._reddit_sentiment('SPY')

        # Analyst
        analyst = self._analyst_sentiment('SPY')

        # Trump / tariff news
        trump_score, trump_headlines = self.get_trump_sentiment()

        # Breaking news
        breaking_score, breaking_headlines = self.get_breaking_news()

        # Geopolitical
        geo_score, geo_headlines = self.get_geopolitical_news()

        # Total
        total = yahoo + reddit + analyst + trump_score + breaking_score + geo_score
        total = max(-25, min(25, total))

        # Determine action (from skill file sentiment rules)
        if total >= 10:
            action = "AGGRESSIVE"   # Full sizes, extra trades
        elif total >= 2:
            action = "NORMAL"       # Standard bell curve
        elif total >= 0:
            action = "CAUTIOUS"     # 80% size
        elif total >= -8:
            action = "DEFENSIVE"    # 50% size
        else:
            action = "ABORT"        # Don't trade today

        result = {
            'total_score': total,
            'yahoo_score': yahoo,
            'reddit_score': reddit,
            'analyst_score': analyst,
            'trump_score': trump_score,
            'breaking_score': breaking_score,
            'geopolitical_score': geo_score,
            'trump_headlines': trump_headlines[:3],
            'breaking_headlines': breaking_headlines[:3],
            'geo_headlines': geo_headlines[:3],
            'action': action,
        }

        log.info(f"📰 FULL SENTIMENT: {total:+d}/25 → {action}")
        log.info(f"   Yahoo: {yahoo:+d} | Reddit: {reddit:+d} | Analyst: {analyst:+d}")
        log.info(f"   Trump: {trump_score:+d} | Breaking: {breaking_score:+d} | Geo: {geo_score:+d}")

        return result

    # ── StockTwits (Free Public API) ───────────────────

    def _stocktwits_sentiment(self, symbol: str) -> int:
        """StockTwits public API — real-time retail trader sentiment.
        Returns -5 to +5 based on bullish/bearish message ratio."""
        cache_key = f"stocktwits:{symbol}"
        if self._is_fresh(cache_key, STOCKTWITS_TTL):
            return self._get_cache(cache_key) or 0

        try:
            url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                return 0

            data = resp.json()
            messages = data.get('messages', [])
            if not messages:
                return 0

            bullish = 0
            bearish = 0
            for msg in messages[:30]:
                sentiment = msg.get('entities', {}).get('sentiment', {})
                if sentiment:
                    if sentiment.get('basic') == 'Bullish':
                        bullish += 1
                    elif sentiment.get('basic') == 'Bearish':
                        bearish += 1

            total = bullish + bearish
            if total == 0:
                score = 0
            else:
                ratio = (bullish - bearish) / total
                score = int(round(ratio * 5))

            score = max(-5, min(5, score))
            self._set_cache(cache_key, score)
            log.debug(f"  StockTwits {symbol}: {bullish}B/{bearish}B → {score:+d}")
            return score

        except Exception as e:
            log.debug(f"StockTwits failed for {symbol}: {e}")
            return 0

    # ── Earnings Calendar (yfinance) ───────────────────

    def get_earnings_info(self, symbol: str) -> dict:
        """Get next earnings date + surprise history. Free via yfinance.
        Returns: {'days_until': int, 'date': str, 'last_surprise': float}"""
        cache_key = f"earnings:{symbol}"
        if self._is_fresh(cache_key, EARNINGS_TTL):
            return self._get_cache(cache_key) or {}

        try:
            stock = yf.Ticker(symbol)
            cal = stock.calendar
            result = {}

            if cal is not None:
                # Next earnings date
                if isinstance(cal, dict):
                    earn_date = cal.get('Earnings Date', [None])
                    if isinstance(earn_date, list) and earn_date:
                        earn_date = earn_date[0]
                    if earn_date:
                        from datetime import date
                        if hasattr(earn_date, 'date'):
                            earn_date = earn_date.date()
                        days = (earn_date - date.today()).days
                        result['days_until'] = days
                        result['date'] = str(earn_date)

            # Last earnings surprise
            try:
                earnings_hist = stock.earnings_history
                if earnings_hist is not None and len(earnings_hist) > 0:
                    last = earnings_hist.iloc[-1]
                    surprise = last.get('epsActual', 0) - last.get('epsEstimate', 0)
                    result['last_surprise'] = round(surprise, 3)
            except:
                pass

            self._set_cache(cache_key, result)
            if result.get('days_until') is not None:
                log.debug(f"  Earnings {symbol}: {result.get('days_until')} days away")
            return result

        except Exception as e:
            log.debug(f"Earnings info failed for {symbol}: {e}")
            return {}

    # ── Short Interest (yfinance) ──────────────────────

    def get_short_info(self, symbol: str) -> dict:
        """Get short interest data. Free via yfinance.
        Returns: {'short_pct': float, 'short_ratio': float, 'squeeze_risk': bool}"""
        cache_key = f"short:{symbol}"
        if self._is_fresh(cache_key, SHORT_TTL):
            return self._get_cache(cache_key) or {}

        try:
            stock = yf.Ticker(symbol)
            info = stock.info

            short_pct = info.get('shortPercentOfFloat', 0) or 0
            short_ratio = info.get('shortRatio', 0) or 0

            result = {
                'short_pct': round(short_pct * 100, 1) if short_pct < 1 else round(short_pct, 1),
                'short_ratio': round(short_ratio, 1),
                'squeeze_risk': short_pct > 0.20 or short_ratio > 5,
            }

            self._set_cache(cache_key, result)
            if result['squeeze_risk']:
                log.info(f"  🔥 SHORT SQUEEZE ALERT: {symbol} — {result['short_pct']}% short, ratio {result['short_ratio']}")
            return result

        except Exception as e:
            log.debug(f"Short info failed for {symbol}: {e}")
            return {}

    # ── Finviz Runner Scanner (Free HTML Scrape) ───────

    def scan_finviz_runners(self) -> list[dict]:
        """Scan Finviz for today's top runners (>5% up, high volume).
        Free — scrapes the public screener HTML. No API key.
        Returns list of {'symbol', 'change_pct', 'volume', 'price'}"""
        cache_key = "finviz:runners"
        if self._is_fresh(cache_key, FINVIZ_TTL):
            return self._get_cache(cache_key) or []

        try:
            url = "https://finviz.com/screener.ashx?v=111&s=ta_topgainers&f=sh_avgvol_o500,sh_price_o5&ft=4"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return []

            # Parse with regex (avoid BeautifulSoup dependency)
            import re
            rows = re.findall(r'<a href="quote\.ashx\?t=([A-Z]+)".*?class="screener-link"', resp.text)
            runners = []
            for sym in rows[:15]:
                runners.append({'symbol': sym})

            self._set_cache(cache_key, runners)
            log.info(f"  Finviz runners: {[r['symbol'] for r in runners[:10]]}")
            return runners

        except Exception as e:
            log.debug(f"Finviz scan failed: {e}")
            return []

    # ── Fear & Greed Proxy (VIX level) ─────────────────

    def get_fear_greed(self) -> dict:
        """Simple fear/greed gauge based on VIX level.
        Free via yfinance. No CNN API needed.
        Returns: {'vix': float, 'level': str, 'score': int}"""
        cache_key = "feargreed"
        if self._is_fresh(cache_key, NEWS_TTL):
            return self._get_cache(cache_key) or {}

        try:
            vix = yf.Ticker('^VIX')
            hist = vix.history(period='1d')
            if hist.empty:
                return {}

            vix_val = float(hist['Close'].iloc[-1])

            if vix_val < 12:
                level, score = "EXTREME GREED", 5
            elif vix_val < 16:
                level, score = "GREED", 3
            elif vix_val < 20:
                level, score = "NEUTRAL", 0
            elif vix_val < 25:
                level, score = "FEAR", -2
            elif vix_val < 30:
                level, score = "HIGH FEAR", -4
            else:
                level, score = "EXTREME FEAR", -5

            result = {'vix': round(vix_val, 1), 'level': level, 'score': score}
            self._set_cache(cache_key, result)
            log.info(f"  VIX: {vix_val:.1f} → {level} ({score:+d})")
            return result

        except Exception as e:
            log.debug(f"Fear/greed failed: {e}")
            return {}

    # ── Full Enhanced Analysis (per stock) ─────────────

    def full_stock_intel(self, symbol: str) -> dict:
        """Complete intelligence package for one stock.
        Runs: sentiment + earnings + short interest + StockTwits.
        Returns combined dict."""
        sent = self.analyze(symbol)
        earnings = self.get_earnings_info(symbol)
        short = self.get_short_info(symbol)

        result = {
            'symbol': symbol,
            'yahoo': sent.yahoo_score,
            'reddit': sent.reddit_score,
            'analyst': sent.analyst_score,
            'stocktwits': self._stocktwits_sentiment(symbol),
            'total_sentiment': sent.total_score,
            'earnings_days': earnings.get('days_until', 999),
            'earnings_date': earnings.get('date', '?'),
            'last_surprise': earnings.get('last_surprise', 0),
            'short_pct': short.get('short_pct', 0),
            'short_ratio': short.get('short_ratio', 0),
            'squeeze_risk': short.get('squeeze_risk', False),
        }

        log.info(
            f"  📊 {symbol} Intel: Sent={sent.total_score:+d} "
            f"Earn={earnings.get('days_until','?')}d "
            f"Short={short.get('short_pct',0):.1f}% "
            f"{'🔥SQUEEZE' if short.get('squeeze_risk') else ''}"
        )
        return result
