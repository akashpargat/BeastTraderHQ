"""
Beast v2.0 — TradingView Integration (THE REAL WEAPON)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Uses TradingView Premium via MCP (78 tools) for ALL technical analysis.
This REPLACES the Alpaca-based technical_analyst.py for live trading.

WHY: Day 1 lesson — "We captured 10% of what TradingView told us was there."
  - TV has Premium data (not limited IEX)
  - TV has all indicators pre-loaded (RSI, MACD, VWAP, BB, EMA, SMA)
  - TV has custom Pine strategies (Guru Shopping Test, Monster Combo)
  - TV shows entry/exit labels (FVG, R2G, VWAP-σ, Mom Exit, RSI Crash)
  - TV has better exit signals than our manual trailing stops

ARCHITECTURE: This module wraps the TradingView MCP tools into
a clean interface that the Beast Engine can call. It cycles through
stocks on TV, reads all indicators, and returns TechnicalSignals.

REQUIRES: TradingView Desktop running with --remote-debugging-port=9222
"""
import logging
import time
from datetime import datetime
from typing import Optional

from models import TechnicalSignals

log = logging.getLogger('Beast.TradingView')

# How long to wait after switching symbols for data to load
SYMBOL_SWITCH_DELAY = 2.0  # seconds


class TradingViewAnalyst:
    """Reads live technical analysis from TradingView Premium via MCP.
    
    This is the PRIMARY technical analyst for the beast engine.
    Falls back to Alpaca-based TechnicalAnalyst if TV is unavailable.
    """

    def __init__(self):
        self._available = False
        self._current_symbol = None
        self._check_connection()

    def _check_connection(self):
        """Check if TradingView MCP is connected."""
        try:
            # This would be called via the MCP tools in the copilot session
            # For the standalone bot, we use CDP (Chrome DevTools Protocol) directly
            from tv_cdp_client import TVClient
            self._client = TVClient()
            self._available = self._client.health_check()
            if self._available:
                log.info("📺 TradingView Premium CONNECTED via CDP")
            else:
                log.warning("📺 TradingView not available — falling back to Alpaca technicals")
        except ImportError:
            # When running under Copilot CLI, we use MCP tools directly
            # The beast engine will call these methods which proxy to MCP
            self._available = True  # Assume available, will fail gracefully
            log.info("📺 TradingView integration loaded (MCP mode)")

    @property
    def is_available(self) -> bool:
        return self._available

    def analyze(self, symbol: str, mcp_tools: dict = None) -> Optional[TechnicalSignals]:
        """Analyze a stock using TradingView.
        
        In MCP mode (Copilot CLI), pass mcp_tools with pre-fetched data.
        In standalone mode, uses CDP client directly.
        
        Args:
            symbol: Stock ticker
            mcp_tools: Dict with pre-fetched TV data:
                {
                    'studies': [...],    # from data_get_study_values
                    'labels': [...],     # from data_get_pine_labels  
                    'tables': [...],     # from data_get_pine_tables
                    'quote': {...},      # from quote_get
                }
        """
        if mcp_tools:
            return self._parse_mcp_data(symbol, mcp_tools)
        return None

    def _parse_mcp_data(self, symbol: str, data: dict) -> TechnicalSignals:
        """Parse TradingView MCP tool outputs into TechnicalSignals."""
        studies = data.get('studies', [])
        labels = data.get('labels', [])
        tables = data.get('tables', [])
        quote = data.get('quote', {})

        signals = TechnicalSignals(symbol=symbol, timestamp=datetime.now())

        # Parse study values — use partial name matching (case-insensitive)
        for study in studies:
            name = study.get('name', '').lower()
            values = study.get('values', {})

            if 'relative strength' in name or name == 'rsi':
                signals.rsi = self._parse_float(values.get('RSI', '50'))

            elif 'macd' in name or 'convergence divergence' in name:
                signals.macd = self._parse_float(values.get('MACD', '0'))
                signals.macd_signal = self._parse_float(values.get('Signal', '0'))
                signals.macd_histogram = self._parse_float(values.get('Histogram', '0'))

            elif 'vwap' in name or 'volume weighted average' in name:
                signals.vwap = self._parse_float(values.get('VWAP', '0'))

            elif 'bollinger' in name:
                signals.bb_upper = self._parse_float(values.get('Upper', '0'))
                signals.bb_mid = self._parse_float(values.get('Basis', '0'))
                signals.bb_lower = self._parse_float(values.get('Lower', '0'))

            elif 'exponential' in name or 'ema' in name:
                ma = self._parse_float(values.get('MA', '0'))
                # Try to identify EMA length from the indicator's inputs
                length = values.get('length', values.get('Length', 0))
                if ma > 0:
                    if length and int(length) <= 10:
                        signals.ema_9 = ma
                    elif length and int(length) <= 15:
                        if signals.ema_9 == 0:
                            signals.ema_9 = ma
                        else:
                            signals.ema_13 = ma  # 13 EMA for ribbon
                    elif length and int(length) >= 20:
                        signals.ema_21 = ma
                    else:
                        # No length info — assign in order
                        if signals.ema_9 == 0:
                            signals.ema_9 = ma
                        elif signals.ema_21 == 0:
                            signals.ema_21 = ma

            elif 'ichimoku' in name:
                signals.ichimoku_tenkan = self._parse_float(
                    values.get('Tenkan-sen', values.get('Conversion Line', '0')))
                signals.ichimoku_kijun = self._parse_float(
                    values.get('Kijun-sen', values.get('Base Line', '0')))
                signals.ichimoku_span_a = self._parse_float(
                    values.get('Senkou Span A', values.get('Leading Span A', '0')))
                signals.ichimoku_span_b = self._parse_float(
                    values.get('Senkou Span B', values.get('Leading Span B', '0')))

            elif 'moving average' in name and 'exponential' not in name:
                signals.sma_20 = self._parse_float(values.get('MA', '0'))

            elif 'guru' in name:
                # Custom strategy indicator
                guru_vwap = self._parse_float(values.get('VWAP', '0'))
                if guru_vwap > 0:
                    signals.vwap = guru_vwap  # Guru VWAP may be more accurate

        # Get current price from quote
        price = quote.get('last', 0) or quote.get('close', 0)
        if price and signals.vwap > 0:
            # Skip VWAP comparison during extended hours (VWAP resets/stale after close)
            from zoneinfo import ZoneInfo
            et_now = datetime.now(ZoneInfo("America/New_York"))
            is_regular_hours = 9 <= et_now.hour < 16
            if is_regular_hours:
                signals.price_vs_vwap = price - signals.vwap
            else:
                signals.price_vs_vwap = 0  # Neutral during extended hours
                log.debug(f"VWAP skipped for {symbol} (extended hours)")

        # Parse Pine labels for strategy signals
        strategy_signals = self._parse_pine_labels(labels)

        # Parse Pine tables for additional data
        table_data = self._parse_pine_tables(tables)

        # Calculate confluence from TV data
        signals.confluence_score = self._calculate_tv_confluence(
            signals, price, strategy_signals, table_data
        )

        return signals

    def _parse_pine_labels(self, labels: list) -> dict:
        """Parse Pine Script labels for entry/exit signals.
        
        Labels from our strategies:
        - "FVG" = Fair Value Gap detected at price
        - "R2G" = Red to Green move detected
        - "Long +13" = ORB Breakout entry with confluence 13
        - "Mom Exit" = Momentum exit signal
        - "RSI Crash" = RSI crashed 15+ points
        - "VWAP-σ" = Price at VWAP lower band
        """
        signals = {
            'fvg_count': 0,
            'r2g_count': 0,
            'long_signals': [],
            'exit_signals': [],
            'vwap_sigma': False,
            'latest_signal': None,
            'latest_price': 0,
        }

        for label in labels:
            text = label.get('text', '')
            price = label.get('price', 0)

            if text == 'FVG':
                signals['fvg_count'] += 1
            elif text == 'R2G':
                signals['r2g_count'] += 1
            elif text.startswith('Long'):
                signals['long_signals'].append({'text': text, 'price': price})
            elif text in ('Mom Exit', 'RSI Crash', '11AM Close', 'Stop'):
                signals['exit_signals'].append({'text': text, 'price': price})
            elif 'VWAP' in text and 'σ' in text:
                signals['vwap_sigma'] = True

            signals['latest_signal'] = text
            signals['latest_price'] = price

        return signals

    def _parse_pine_tables(self, tables: list) -> dict:
        """Parse Pine Script table data."""
        data = {
            'prev_close': 0,
            'pmh': 0,  # Pre-market high
            'rsi': 0,
            'trades': '0/0',
            'vwap_band_low': 0,
            'vwap_band_high': 0,
        }

        for table in tables:
            rows = table.get('rows', [])
            for row in rows:
                if isinstance(row, str):
                    if 'Prev Close' in row:
                        parts = row.split('|')
                        if len(parts) >= 2:
                            data['prev_close'] = self._parse_float(parts[1].strip())
                    elif 'PMH' in row:
                        parts = row.split('|')
                        if len(parts) >= 2:
                            data['pmh'] = self._parse_float(parts[1].strip())
                    elif 'RSI' in row:
                        parts = row.split('|')
                        if len(parts) >= 2:
                            data['rsi'] = self._parse_float(parts[1].strip())
                    elif 'Trades' in row:
                        parts = row.split('|')
                        if len(parts) >= 2:
                            data['trades'] = parts[1].strip()
                    elif 'VWAP Band' in row:
                        parts = row.split('|')
                        if len(parts) >= 2:
                            band = parts[1].strip()
                            band_parts = band.split('/')
                            if len(band_parts) == 2:
                                data['vwap_band_low'] = self._parse_float(band_parts[0])
                                data['vwap_band_high'] = self._parse_float(band_parts[1])
        return data

    def _calculate_tv_confluence(self, signals: TechnicalSignals, price: float,
                                  strategy_signals: dict, table_data: dict) -> int:
        """Calculate confluence score using TradingView data.
        Score out of 15. Day 7 fix: was showing 1-2/10 on everything.
        Now properly weights all indicators including Ichimoku."""
        score = 0

        # Above VWAP (+2) — skip if extended hours (price_vs_vwap = 0)
        if signals.price_vs_vwap > 0:
            score += 2
        elif signals.price_vs_vwap < 0:
            score -= 1  # Penalty for below VWAP

        # RSI zones
        if 40 <= signals.rsi <= 60:
            score += 1  # Neutral = safe
        elif signals.rsi < 30:
            score += 2  # Oversold = strong bounce signal
        elif signals.rsi > 70:
            score -= 1  # Overbought = caution

        # MACD positive histogram
        if signals.macd_histogram > 0:
            score += 2
        elif signals.macd_histogram < 0:
            score -= 1

        # MACD above signal (momentum)
        if signals.macd > signals.macd_signal and signals.macd > 0:
            score += 1

        # Above Bollinger mid
        if price and signals.bb_mid > 0 and price > signals.bb_mid:
            score += 1
        # At or near BB lower (oversold bounce)
        if price and signals.bb_lower > 0 and price <= signals.bb_lower * 1.01:
            score += 2

        # EMA alignment (9 > 21 = uptrend)
        if signals.ema_9 > 0 and signals.ema_21 > 0:
            if signals.ema_9 > signals.ema_21:
                score += 2  # Bullish EMA cross
            else:
                score -= 1  # Bearish
        
        # Price above all EMAs
        if price and signals.ema_9 > 0 and price > signals.ema_9:
            score += 1

        # Price above 200 SMA (long-term uptrend)
        if price and signals.sma_20 > 0 and price > signals.sma_20:
            score += 1

        # Ichimoku Cloud (if available)
        if hasattr(signals, 'ichimoku_span_a') and signals.ichimoku_span_a > 0:
            cloud_top = max(signals.ichimoku_span_a, signals.ichimoku_span_b)
            cloud_bottom = min(signals.ichimoku_span_a, signals.ichimoku_span_b)
            if price and price > cloud_top:
                score += 2  # Above cloud = strong bullish
            elif price and price < cloud_bottom:
                score -= 2  # Below cloud = bearish

        # FVG signals from Pine (strategy F)
        if strategy_signals.get('fvg_count', 0) > 0:
            score += 1

        # R2G signals from Pine (strategy G)
        if strategy_signals.get('r2g_count', 0) > 0:
            score += 1

        # Long signals from Pine (direct entry)
        if strategy_signals.get('long_signals'):
            score += 2

        # VWAP band position (Guru script)
        if table_data.get('vwap_band_low', 0) > 0:
            if price and price > table_data['vwap_band_low']:
                score += 1

        return max(0, min(score, 15))  # Cap at 0-15

    def _parse_float(self, value) -> float:
        """Safely parse a float from TV output."""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # Remove unicode chars like − and formatting
            cleaned = value.replace('−', '-').replace(',', '').replace('—', '0').strip()
            try:
                return float(cleaned)
            except ValueError:
                return 0.0
        return 0.0

    def get_scan_sequence(self, regime: str, held_symbols: list[str]) -> list[str]:
        """Get the optimal stock scan sequence for TV cycling.
        From the skill file: cycle every 5 min during trading window."""
        offense = ['COIN', 'TSLA', 'META', 'MSTR']
        defense = ['CAT', 'ORCL', 'XOM', 'COST']
        mag7 = ['AAPL', 'AMZN', 'GOOGL', 'META', 'MSFT', 'NVDA', 'TSLA']

        if regime == 'BULL':
            base = offense + mag7
        elif regime == 'BEAR':
            base = defense
        else:
            base = defense + ['GOOGL', 'MSFT', 'AMZN']

        # Always include held positions first (priority)
        sequence = list(dict.fromkeys(held_symbols + base))
        return sequence

    def interpret_exit_signals(self, labels: list) -> list[dict]:
        """Check if TradingView shows any exit signals.
        
        Returns list of exit signals with action:
        - Mom Exit → EMA crossdown, EXIT NOW
        - RSI Crash → RSI dropped 15+ points, EXIT NOW
        - 11AM Close → Time's up, EXIT ALL
        - Stop → $10 stop hit
        """
        exits = []
        for label in labels:
            text = label.get('text', '')
            price = label.get('price', 0)

            if text == 'Mom Exit':
                exits.append({
                    'signal': 'MOM_EXIT',
                    'price': price,
                    'urgency': 'HIGH',
                    'reason': 'EMA crossdown confirmed — momentum dying'
                })
            elif text == 'RSI Crash':
                exits.append({
                    'signal': 'RSI_CRASH',
                    'price': price,
                    'urgency': 'HIGH',
                    'reason': 'RSI crashed 15+ points in 2 bars'
                })
            elif text == '11AM Close':
                exits.append({
                    'signal': 'TIME_EXIT',
                    'price': price,
                    'urgency': 'IMMEDIATE',
                    'reason': '11:00 AM hard close — exit everything'
                })
            elif text == 'Stop':
                exits.append({
                    'signal': 'STOP_HIT',
                    'price': price,
                    'urgency': 'IMMEDIATE',
                    'reason': '$10 stop loss triggered'
                })

        return exits

    def interpret_entry_signals(self, labels: list, rsi: float, 
                                 vwap_above: bool) -> list[dict]:
        """Check if TradingView shows any entry signals.
        
        Returns list of entry opportunities with strategy name.
        """
        entries = []
        for label in labels:
            text = label.get('text', '')
            price = label.get('price', 0)

            if text.startswith('Long'):
                # Extract confluence score from label
                try:
                    conf = int(text.split('+')[1]) if '+' in text else 0
                except:
                    conf = 0
                entries.append({
                    'signal': 'ORB_BREAKOUT',
                    'strategy': 'A',
                    'price': price,
                    'confluence': conf,
                    'reason': f'TV Long signal with confluence +{conf}'
                })
            elif text == 'FVG' and vwap_above:
                entries.append({
                    'signal': 'FAIR_VALUE_GAP',
                    'strategy': 'F',
                    'price': price,
                    'reason': f'Fair Value Gap at ${price:.2f} above VWAP'
                })
            elif text == 'R2G' and rsi < 50:
                entries.append({
                    'signal': 'RED_TO_GREEN',
                    'strategy': 'G',
                    'price': price,
                    'reason': f'Red to Green at ${price:.2f} with RSI {rsi}'
                })
            elif text == 'VWAP-σ':
                entries.append({
                    'signal': 'VWAP_BOUNCE',
                    'strategy': 'B',
                    'price': price,
                    'reason': f'At VWAP lower band (bounce zone)'
                })

        return entries
