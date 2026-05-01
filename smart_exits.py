"""
Beast V6 — Smart Exit Engine & Post-Trade Learning
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fixes the #1 problem: selling too early.

Components:
1. PostSellTracker — tracks price 15m/1h/4h after every sell
2. SmartExitEngine — ATR-based scalp targets + TV-aware trailing stops  
3. OutcomeGrader   — grades every trade in trade_log (pnl_1h, 4h, lesson)
4. CatalystTracker — records WHY stocks run (for pattern learning)

Data flows to claude_daily_deep_learn at 3AM for self-improvement.
"""

import logging
import time
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from collections import defaultdict

log = logging.getLogger("Beast.V6")

# ══════════════════════════════════════════════════════════
#  1. POST-SELL PRICE TRACKER
# ══════════════════════════════════════════════════════════

class PostSellTracker:
    """After every sell, track what price does at +15m, +1h, +4h.
    This is how we detect 'sold too early' — the key learning signal."""

    _INIT_SQL = """
    CREATE TABLE IF NOT EXISTS sell_outcomes (
        id SERIAL PRIMARY KEY,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        symbol TEXT NOT NULL,
        sell_price NUMERIC NOT NULL,
        sell_qty INTEGER,
        sell_time TIMESTAMPTZ NOT NULL,
        sell_reason TEXT,
        sell_strategy TEXT,
        price_15m NUMERIC,
        price_1h NUMERIC,
        price_4h NUMERIC,
        max_price_after NUMERIC,
        min_price_after NUMERIC,
        pct_move_15m NUMERIC,
        pct_move_1h NUMERIC,
        pct_move_4h NUMERIC,
        pct_max_missed NUMERIC,
        was_premature BOOLEAN,
        optimal_action TEXT,
        graded_at TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_sell_outcomes_symbol ON sell_outcomes(symbol);
    CREATE INDEX IF NOT EXISTS idx_sell_outcomes_graded ON sell_outcomes(graded_at NULLS FIRST);
    """

    def __init__(self, db=None):
        self.db = db
        self._pending_sells = []  # [{symbol, price, time, qty, reason, strategy}]
        if db:
            self._init_db()

    def set_db(self, db):
        self.db = db
        self._init_db()

    def _init_db(self):
        try:
            for sql in self._INIT_SQL.split(";"):
                sql = sql.strip()
                if sql:
                    self.db._exec(sql)
            log.info("[V6] PostSellTracker: DB table ready")
        except Exception as e:
            log.warning(f"[V6] PostSellTracker DB init: {e}")

    def record_sell(self, symbol: str, price: float, qty: int = 0,
                    reason: str = "", strategy: str = ""):
        """Called immediately after any sell fill."""
        if not self.db:
            return
        try:
            self.db._exec(
                """INSERT INTO sell_outcomes 
                   (symbol, sell_price, sell_qty, sell_time, sell_reason, sell_strategy)
                   VALUES (%s, %s, %s, NOW(), %s, %s)""",
                (symbol, price, qty, reason[:200], strategy[:50])
            )
            log.info(f"[V6] PostSell: recorded {symbol} sell @${price:.2f}")
        except Exception as e:
            log.warning(f"[V6] PostSell record error: {e}")

    def grade_pending(self, get_price_fn) -> list:
        """Check ungraded sells and fill in 15m/1h/4h prices.
        get_price_fn(symbol) -> float (current price)
        Returns list of 'sold too early' findings."""
        if not self.db:
            return []

        findings = []
        try:
            ungraded = self.db._exec(
                """SELECT id, symbol, sell_price, sell_time, sell_qty, sell_reason
                   FROM sell_outcomes
                   WHERE graded_at IS NULL
                   AND sell_time < NOW() - interval '15 minutes'
                   ORDER BY sell_time ASC LIMIT 30""",
                fetch=True
            ) or []

            if not ungraded:
                return []

            now = datetime.now(timezone.utc)
            for row in ungraded:
                sid = row['id']
                sym = row['symbol']
                sell_price = float(row['sell_price'])
                sell_time = row['sell_time']
                if not sell_time.tzinfo:
                    sell_time = sell_time.replace(tzinfo=timezone.utc)

                elapsed = (now - sell_time).total_seconds()
                current = get_price_fn(sym)
                if not current or current <= 0:
                    continue

                updates = {}
                # Fill the appropriate time bucket
                if elapsed >= 15 * 60 and not row.get('price_15m'):
                    pct = (current - sell_price) / sell_price * 100
                    updates['price_15m'] = current
                    updates['pct_move_15m'] = round(pct, 2)

                if elapsed >= 60 * 60 and not row.get('price_1h'):
                    pct = (current - sell_price) / sell_price * 100
                    updates['price_1h'] = current
                    updates['pct_move_1h'] = round(pct, 2)

                if elapsed >= 4 * 3600 and not row.get('price_4h'):
                    pct = (current - sell_price) / sell_price * 100
                    updates['price_4h'] = current
                    updates['pct_move_4h'] = round(pct, 2)

                # Track max/min after sell
                max_after = float(row.get('max_price_after') or 0)
                min_after = float(row.get('min_price_after') or current)
                if current > max_after:
                    updates['max_price_after'] = current
                if current < min_after:
                    updates['min_price_after'] = current

                # Final grade at 4h+
                if elapsed >= 4 * 3600:
                    max_p = max(max_after, current)
                    pct_missed = (max_p - sell_price) / sell_price * 100
                    was_premature = pct_missed > 2.0  # Left >2% on table
                    
                    if was_premature:
                        optimal = "HOLD — stock ran higher"
                    elif current < sell_price:
                        optimal = "CORRECT SELL — price dropped"
                    else:
                        optimal = "NEUTRAL — small move"

                    updates['pct_max_missed'] = round(pct_missed, 2)
                    updates['was_premature'] = was_premature
                    updates['optimal_action'] = optimal
                    updates['graded_at'] = 'NOW()'

                    if was_premature:
                        findings.append({
                            'symbol': sym,
                            'sell_price': sell_price,
                            'max_after': max_p,
                            'pct_missed': round(pct_missed, 2),
                            'reason': row.get('sell_reason', ''),
                            'lesson': f"Sold {sym} @${sell_price:.2f}, ran to ${max_p:.2f} (+{pct_missed:.1f}%). {optimal}"
                        })
                        log.info(f"[V6] SOLD TOO EARLY: {sym} @${sell_price:.2f} → ${max_p:.2f} (+{pct_missed:.1f}%)")

                # Write updates
                if updates:
                    set_parts = []
                    vals = []
                    for k, v in updates.items():
                        if v == 'NOW()':
                            set_parts.append(f"{k} = NOW()")
                        else:
                            set_parts.append(f"{k} = %s")
                            vals.append(v)
                    vals.append(sid)
                    self.db._exec(
                        f"UPDATE sell_outcomes SET {', '.join(set_parts)} WHERE id = %s",
                        tuple(vals)
                    )

        except Exception as e:
            log.warning(f"[V6] PostSell grading error: {e}")

        return findings

    def get_premature_sells(self, days: int = 7) -> list:
        """Get recent 'sold too early' events for AI learning."""
        if not self.db:
            return []
        try:
            return self.db._exec(
                """SELECT symbol, sell_price, max_price_after, pct_max_missed, 
                          sell_reason, sell_strategy, optimal_action, sell_time
                   FROM sell_outcomes
                   WHERE was_premature = true
                   AND sell_time > NOW() - interval '%s days'
                   ORDER BY pct_max_missed DESC LIMIT 20""",
                (days,), fetch=True
            ) or []
        except Exception as e:
            log.warning(f"[V6] get_premature_sells: {e}")
            return []


# ══════════════════════════════════════════════════════════
#  2. SMART EXIT ENGINE
# ══════════════════════════════════════════════════════════

class SmartExitEngine:
    """ATR-based dynamic scalp targets and trailing stops.
    Replaces hardcoded +2% scalp and -0.0% trail triggers."""

    # Default tier thresholds (overridden by learning)
    SCALP_TIERS = [
        (0.33, 2.0),   # Sell 1/3 at +2%
        (0.33, 4.0),   # Sell 1/3 at +4%
        (0.34, 6.0),   # Keep 1/3 as runner with trail
    ]

    # ATR-based stop multipliers
    ATR_TRAIL_MULT = 2.0  # trail = 2× ATR
    MIN_TRAIL_PCT = 1.5   # never trail tighter than 1.5%
    MAX_TRAIL_PCT = 5.0   # never trail wider than 5%

    # Don't trail until position is this red
    MIN_RED_FOR_TRAIL = -1.0  # Don't trail at -0.1%, wait for -1%+

    def __init__(self, db=None):
        self.db = db
        self._atr_cache = {}  # symbol → (atr, timestamp)
        self._ATR_TTL = 300   # 5 min cache

    def set_db(self, db):
        self.db = db

    def get_atr(self, symbol: str, alpaca_data=None) -> float:
        """Get 14-period ATR. Uses Alpaca bars or falls back to estimate."""
        cached = self._atr_cache.get(symbol)
        if cached and time.time() - cached[1] < self._ATR_TTL:
            return cached[0]

        atr = 0.0
        try:
            if alpaca_data:
                from alpaca.data.requests import StockBarsRequest
                from alpaca.data.timeframe import TimeFrame
                req = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=TimeFrame.Day,
                    limit=15,
                    feed='iex'
                )
                bars = alpaca_data.get_stock_bars(req)
                if bars and symbol in bars:
                    bar_list = list(bars[symbol])
                    if len(bar_list) >= 2:
                        trs = []
                        for i in range(1, len(bar_list)):
                            h = float(bar_list[i].high)
                            l = float(bar_list[i].low)
                            pc = float(bar_list[i-1].close)
                            tr = max(h - l, abs(h - pc), abs(l - pc))
                            trs.append(tr)
                        atr = sum(trs) / len(trs)
        except Exception as e:
            log.debug(f"[V6] ATR fetch {symbol}: {e}")

        if atr <= 0:
            # Rough estimate: 2% of typical price
            atr = 5.0  # fallback

        self._atr_cache[symbol] = (atr, time.time())
        return atr

    def get_scalp_target(self, symbol: str, trade_style: str = "SCALP",
                         ai_confidence: float = 0, price: float = 0,
                         tv_signals: dict = None) -> dict:
        """Get dynamic scalp target for a position.
        
        Returns: {
            'scalp_pct': float,     # when to take first profit
            'sell_fraction': float,  # how much to sell (0.33 = 1/3)
            'reason': str,
            'hold_signal': bool,    # True = don't scalp yet
        }
        """
        tv = tv_signals or {}

        # Base targets by trade style (from ai_trends learning)
        if trade_style == 'CORE':
            return {'scalp_pct': 999, 'sell_fraction': 0, 'reason': 'CORE hold', 'hold_signal': True}
        elif trade_style == 'SWING':
            base_pct = 5.0
        else:
            base_pct = 2.5  # slightly wider than old 2.0

        # TV-aware: if signals are still bullish, RAISE the scalp target
        rsi = tv.get('rsi', 50)
        macd_h = tv.get('macd_hist', 0)
        above_vwap = tv.get('vwap_above', False)

        hold_signal = False
        if macd_h > 0 and rsi < 65 and above_vwap:
            # All three bullish — trend intact, don't scalp yet!
            base_pct = max(base_pct, 4.0)
            hold_signal = True
            reason = f"HOLD: MACD+, RSI={rsi:.0f}<65, above VWAP — trend intact"
        elif macd_h > 0 and rsi < 70:
            # MACD positive and RSI not extreme — raise target slightly
            base_pct = max(base_pct, 3.0)
            reason = f"WIDER TARGET: MACD+, RSI={rsi:.0f} — momentum continuing"
        elif rsi > 75:
            # Overbought — scalp soon
            base_pct = min(base_pct, 2.0)
            reason = f"SCALP NOW: RSI={rsi:.0f} overbought"
        elif macd_h < 0:
            # MACD turned negative — scalp before it drops more
            base_pct = min(base_pct, 1.5)
            reason = f"SCALP: MACD negative ({macd_h:.2f}) — momentum fading"
        else:
            reason = f"DEFAULT: {base_pct:.1f}% target"

        # High AI confidence = wider target
        if ai_confidence > 80:
            base_pct *= 1.3
            reason += f" +30% for high conf={ai_confidence}"

        # Sell fraction: scale out 1/3 at a time
        sell_fraction = 0.33 if not hold_signal else 0

        return {
            'scalp_pct': round(base_pct, 1),
            'sell_fraction': sell_fraction,
            'reason': reason,
            'hold_signal': hold_signal,
        }

    def get_trail_params(self, symbol: str, pct_from_entry: float,
                         price: float, tv_signals: dict = None,
                         is_blue_chip: bool = False,
                         alpaca_data=None) -> dict:
        """Get dynamic trailing stop parameters.
        
        Returns: {
            'should_trail': bool,
            'trail_pct': float,
            'reason': str,
        }
        """
        tv = tv_signals or {}

        # Rule 1: Don't trail tiny dips (was -0.0%, now require -1%+)
        if pct_from_entry > self.MIN_RED_FOR_TRAIL:
            return {
                'should_trail': False,
                'trail_pct': 0,
                'reason': f'Dip too small ({pct_from_entry:.1f}% > {self.MIN_RED_FOR_TRAIL}%) — hold'
            }

        # Rule 2: TV-aware — if signals bullish, don't trail
        rsi = tv.get('rsi', 50)
        macd_h = tv.get('macd_hist', 0)
        if macd_h > 0 and 35 < rsi < 65:
            return {
                'should_trail': False,
                'trail_pct': 0,
                'reason': f'TV still bullish (MACD={macd_h:.2f}, RSI={rsi:.0f}) — hold through dip'
            }

        # Rule 3: ATR-based trail width
        atr = self.get_atr(symbol, alpaca_data)
        atr_pct = (atr / price * 100) if price > 0 else 2.0
        trail_pct = max(self.MIN_TRAIL_PCT, min(self.MAX_TRAIL_PCT, atr_pct * self.ATR_TRAIL_MULT))

        # Blue chips get wider stops (they recover)
        if is_blue_chip:
            trail_pct = max(trail_pct, 4.0)

        return {
            'should_trail': True,
            'trail_pct': round(trail_pct, 1),
            'reason': f'Trail {trail_pct:.1f}% (ATR=${atr:.2f}, {atr_pct:.1f}%)'
        }


# ══════════════════════════════════════════════════════════
#  3. CATALYST TRACKER
# ══════════════════════════════════════════════════════════

class CatalystTracker:
    """When a stock runs +3%+, record the catalyst (why it moved).
    Fed to 3AM Claude for pattern learning."""

    def __init__(self, db=None):
        self.db = db

    def set_db(self, db):
        self.db = db

    def record_runner(self, symbol: str, pct_change: float, volume: int,
                      sentiment_score: int = 0, tv_signals: dict = None,
                      news_headlines: list = None):
        """Record a runner event with available catalyst data."""
        if not self.db:
            return
        try:
            catalyst = self._identify_catalyst(symbol, pct_change, volume,
                                                sentiment_score, news_headlines)
            self.db._exec(
                """INSERT INTO ai_trends (symbol, trend_type, insight, confidence, data, is_active)
                   VALUES (%s, 'catalyst', %s, %s, %s, true)""",
                (
                    symbol,
                    catalyst['summary'][:500],
                    catalyst['confidence'],
                    json.dumps(catalyst, default=str),
                )
            )
            log.info(f"[V6] Catalyst: {symbol} +{pct_change:.1f}% — {catalyst['type']}: {catalyst['summary'][:60]}")
        except Exception as e:
            log.debug(f"[V6] Catalyst record {symbol}: {e}")

    def _identify_catalyst(self, symbol: str, pct: float, volume: int,
                           sent: int, headlines: list = None) -> dict:
        """Best-effort catalyst identification from available data."""
        cat_type = "unknown"
        summary = f"{symbol} moved {pct:+.1f}%"
        confidence = 40

        # Volume spike = likely news/earnings
        if volume > 500000:
            cat_type = "high_volume"
            summary += f" on {volume:,} volume"
            confidence = 50

        # Strong sentiment = likely news-driven
        if abs(sent) >= 8:
            cat_type = "sentiment_driven"
            summary += f" with sentiment={sent:+d}"
            confidence = 60

        # Headlines available
        if headlines:
            cat_type = "news_catalyst"
            summary += f" | Headlines: {'; '.join(str(h)[:50] for h in headlines[:3])}"
            confidence = 70

        # Large moves are more likely earnings/event
        if abs(pct) > 5:
            if cat_type == "unknown":
                cat_type = "major_event"
            confidence = max(confidence, 65)

        return {
            'type': cat_type,
            'summary': summary,
            'confidence': confidence,
            'pct_change': pct,
            'volume': volume,
            'sentiment': sent,
            'headlines': headlines or [],
        }

    def get_recent_catalysts(self, days: int = 7) -> list:
        """Get recent catalyst events for AI learning."""
        if not self.db:
            return []
        try:
            return self.db._exec(
                """SELECT symbol, insight, confidence, data, created_at
                   FROM ai_trends
                   WHERE trend_type = 'catalyst'
                   AND created_at > NOW() - interval '%s days'
                   ORDER BY created_at DESC LIMIT 20""",
                (days,), fetch=True
            ) or []
        except Exception as e:
            log.debug(f"[V6] get_catalysts: {e}")
            return []


# ══════════════════════════════════════════════════════════
#  4. ENHANCED OUTCOME GRADER
# ══════════════════════════════════════════════════════════

def grade_trade_log(db, get_price_fn) -> int:
    """Grade trade_log entries that have no pnl_1h/4h yet.
    This was BROKEN before — pnl_1h/4h were never populated.
    
    Returns count of trades graded.
    """
    if not db:
        return 0

    try:
        # Get ungraded trades (have no pnl_1h AND are old enough)
        ungraded = db._exec(
            """SELECT id, symbol, side, price, created_at
               FROM trade_log
               WHERE pnl_1h IS NULL
               AND price > 0
               AND created_at < NOW() - interval '1 hour'
               AND created_at > NOW() - interval '48 hours'
               LIMIT 50""",
            fetch=True
        ) or []

        if not ungraded:
            return 0

        graded = 0
        for trade in ungraded:
            sym = trade['symbol']
            entry_price = float(trade['price'])
            trade_time = trade['created_at']
            side = trade['side']
            if not trade_time.tzinfo:
                trade_time = trade_time.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            elapsed_hrs = (now - trade_time).total_seconds() / 3600

            current = get_price_fn(sym)
            if not current or current <= 0:
                continue

            updates = []
            vals = []

            # pnl_1h (after 1+ hour)
            if elapsed_hrs >= 1:
                if side == 'buy':
                    pnl_1h = (current - entry_price) / entry_price * 100
                else:
                    pnl_1h = (entry_price - current) / entry_price * 100
                updates.append("pnl_1h = %s")
                vals.append(round(pnl_1h, 2))

            # pnl_4h (after 4+ hours)
            if elapsed_hrs >= 4:
                if side == 'buy':
                    pnl_4h = (current - entry_price) / entry_price * 100
                else:
                    pnl_4h = (entry_price - current) / entry_price * 100
                updates.append("pnl_4h = %s")
                vals.append(round(pnl_4h, 2))

            # pnl_eod (after 6+ hours or market close)
            if elapsed_hrs >= 6 and trade.get('pnl_eod') is None:
                if side == 'buy':
                    pnl_eod = (current - entry_price) / entry_price * 100
                else:
                    pnl_eod = (entry_price - current) / entry_price * 100
                updates.append("pnl_eod = %s")
                vals.append(round(pnl_eod, 2))
                updates.append("was_profitable = %s")
                vals.append(pnl_eod > 0)

            # Generate lesson
            if elapsed_hrs >= 4 and not trade.get('lesson_learned'):
                pnl = vals[0] if vals else 0  # pnl_1h
                if side == 'buy':
                    if pnl > 3:
                        lesson = f"Good buy: {sym} up {pnl:.1f}% in 1h"
                    elif pnl > 0:
                        lesson = f"OK buy: {sym} up {pnl:.1f}% — small gain"
                    elif pnl > -2:
                        lesson = f"Flat buy: {sym} {pnl:.1f}% — no edge found"
                    else:
                        lesson = f"Bad buy: {sym} down {pnl:.1f}% — entry was wrong"
                else:
                    if pnl > 0:
                        lesson = f"Good sell: {sym} dropped {pnl:.1f}% after exit"
                    elif pnl > -2:
                        lesson = f"OK sell: {sym} flat ({pnl:.1f}%) after exit"
                    else:
                        lesson = f"Premature sell: {sym} ran {abs(pnl):.1f}% after we sold"
                updates.append("lesson_learned = %s")
                vals.append(lesson[:200])

            if updates:
                vals.append(trade['id'])
                db._exec(
                    f"UPDATE trade_log SET {', '.join(updates)} WHERE id = %s",
                    tuple(vals)
                )
                graded += 1

        log.info(f"[V6] Outcome grader: graded {graded}/{len(ungraded)} trades in trade_log")
        return graded

    except Exception as e:
        log.warning(f"[V6] grade_trade_log error: {e}")
        return 0


def get_learning_data_for_claude(db) -> dict:
    """Gather ALL learning data for the 3AM Claude deep learning session.
    This is what makes the bot ACTUALLY self-improve."""
    if not db:
        return {}

    data = {}
    try:
        # 1. Premature sells (sold too early)
        data['premature_sells'] = db._exec(
            """SELECT symbol, sell_price, max_price_after, pct_max_missed,
                      sell_reason, sell_strategy, sell_time
               FROM sell_outcomes
               WHERE was_premature = true
               AND sell_time > NOW() - interval '7 days'
               ORDER BY pct_max_missed DESC LIMIT 10""",
            fetch=True
        ) or []

        # 2. Trade log with outcomes
        data['graded_trades'] = db._exec(
            """SELECT symbol, side, price, pnl_1h, pnl_4h, pnl_eod,
                      was_profitable, lesson_learned, strategy, source
               FROM trade_log
               WHERE pnl_1h IS NOT NULL
               AND created_at > NOW() - interval '7 days'
               ORDER BY created_at DESC LIMIT 30""",
            fetch=True
        ) or []

        # 3. Scalp performance (are we scalping too early?)
        data['scalp_stats'] = db._exec(
            """SELECT symbol, reason, price, 
                      created_at
               FROM activity_log
               WHERE action_type = 'SCALP SELL'
               AND created_at > NOW() - interval '7 days'
               ORDER BY created_at DESC LIMIT 20""",
            fetch=True
        ) or []

        # 4. Runner catalysts
        data['catalysts'] = db._exec(
            """SELECT symbol, insight, data, created_at
               FROM ai_trends
               WHERE trend_type = 'catalyst'
               AND created_at > NOW() - interval '7 days'
               ORDER BY created_at DESC LIMIT 15""",
            fetch=True
        ) or []

        # 5. Anti-buyback events (sold then rebought higher)
        data['rebuys'] = db._exec(
            """SELECT symbol, sell_price, 
                      (SELECT MIN(price) FROM activity_log a2 
                       WHERE a2.symbol = sell_outcomes.symbol 
                       AND a2.action_type = 'FILL' AND a2.side = 'buy'
                       AND a2.created_at > sell_outcomes.sell_time
                       AND a2.created_at < sell_outcomes.sell_time + interval '4 hours') as rebuy_price,
                      sell_time
               FROM sell_outcomes
               WHERE sell_time > NOW() - interval '7 days'
               AND EXISTS (SELECT 1 FROM activity_log a2 
                           WHERE a2.symbol = sell_outcomes.symbol 
                           AND a2.action_type = 'FILL' AND a2.side = 'buy'
                           AND a2.created_at > sell_outcomes.sell_time
                           AND a2.created_at < sell_outcomes.sell_time + interval '4 hours')
               ORDER BY sell_time DESC LIMIT 10""",
            fetch=True
        ) or []

        # 6. Win rate by strategy
        data['strategy_performance'] = db._exec(
            """SELECT strategy, 
                      COUNT(*) as total,
                      SUM(CASE WHEN was_profitable THEN 1 ELSE 0 END) as wins,
                      AVG(pnl_eod) as avg_pnl
               FROM trade_log
               WHERE was_profitable IS NOT NULL
               AND created_at > NOW() - interval '30 days'
               GROUP BY strategy ORDER BY total DESC""",
            fetch=True
        ) or []

    except Exception as e:
        log.warning(f"[V6] get_learning_data: {e}")

    return data
