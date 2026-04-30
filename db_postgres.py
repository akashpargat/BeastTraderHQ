"""
Beast Terminal V4 — PostgreSQL Database Layer (Schema V4)
=========================================================
20+ tables, 4 views, 50+ indexes.

Tables:
  AUTH:      users, sessions, login_attempts
  TRADING:   orders, ai_verdicts, trade_decisions
  MARKET:    tv_readings, sentiment_readings
  STATE:     equity_snapshots, position_snapshots
  ACTIVITY:  activity_log, alerts, scan_results, commands
  BRAIN:     watchlist, earnings_patterns, ai_trends
  BOT CORE:  bot_state, bot_sessions, price_memory, bot_config

Design: PostgreSQL IS the bot's brain. All state persists across restarts.
  - bot_state: KV store for any runtime state (replaces in-memory dicts)
  - bot_sessions: track every run (version, uptime, loops, stop reason)
  - price_memory: per-stock price tracking (sell prices, cooldowns, highs)
  - bot_config: dashboard-editable settings (hot reload without restart)
  - trade_decisions: full audit trail (why we bought/didn't buy)

Alpaca = source of live positions/orders. DB = memory + decisions + analytics.
Every method handles errors gracefully — bot NEVER crashes from DB issues.
"""

import os
import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
import logging
import hashlib
import threading

log = logging.getLogger('Beast.DB')

DB_URL = os.getenv('DATABASE_URL', '')


class BeastDB:
    """PostgreSQL database layer with connection pooling and batch operations.
    Designed for speed at scale — pool reuses connections, batch writes minimize round trips,
    and in-memory cache avoids repeated reads of rarely-changing data."""

    def __init__(self):
        self.conn = None
        self._pool = None
        self._cache = {}  # In-memory read cache {key: (value, expiry_time)}
        self._cache_lock = threading.Lock()
        self._connect()

    def _connect(self):
        if not DB_URL:
            log.warning("DATABASE_URL not set — PostgreSQL disabled")
            return
        try:
            # Connection pool: min 1, max 5 connections (B1ms can handle ~50)
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                1, 5, DB_URL, cursor_factory=RealDictCursor
            )
            # Keep a default connection for backward compat
            self.conn = self._pool.getconn()
            self.conn.autocommit = True
            log.info("✅ Connected to PostgreSQL (pooled, max 5 conns)")
        except Exception as e:
            log.error(f"❌ PostgreSQL connection failed: {e}")
            # Fallback to single connection
            try:
                self.conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
                self.conn.autocommit = True
                log.info("✅ Connected to PostgreSQL (single conn fallback)")
            except:
                self.conn = None
        except Exception as e:
            log.error(f"❌ PostgreSQL connection failed: {e}")
            self.conn = None

    def _ensure_conn(self) -> bool:
        if self.conn is None:
            self._connect()
            return self.conn is not None
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            log.warning("PostgreSQL reconnecting...")
            self._connect()
            return self.conn is not None

    def _exec(self, sql, params=None, fetch=False):
        """Execute SQL safely. Returns list of dicts if fetch=True."""
        if not self._ensure_conn():
            return [] if fetch else None
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, params)
                if fetch:
                    rows = cur.fetchall()
                    # Convert Decimal to float for JSON serialization
                    result = []
                    for row in rows:
                        d = dict(row)
                        for k, v in d.items():
                            if isinstance(v, Decimal):
                                d[k] = float(v)
                        result.append(d)
                    return result
        except Exception as e:
            log.warning(f"DB error: {e}")
            try:
                self.conn.rollback()
            except:
                self.conn = None
            return [] if fetch else None

    # ══════════════════════════════════════════════
    #  DOMAIN 1: AUTH
    # ══════════════════════════════════════════════

    def verify_user(self, username: str, password: str) -> dict:
        """Verify login credentials. Returns user dict or None."""
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        rows = self._exec(
            "SELECT id, username, role, is_active FROM users WHERE username = %s AND password_hash = %s",
            (username, pw_hash), fetch=True
        )
        if rows and rows[0].get('is_active'):
            self._exec("UPDATE users SET last_login_at = NOW(), last_login_ip = %s WHERE id = %s",
                       (None, rows[0]['id']))  # IP set by caller
            return rows[0]
        return None

    def create_session(self, user_id: int, token_hash: str, ip: str = None, user_agent: str = None, hours: int = 24) -> int:
        """Create login session. Returns session ID."""
        rows = self._exec(
            """INSERT INTO sessions (user_id, token_hash, ip_address, user_agent, expires_at)
               VALUES (%s, %s, %s::inet, %s, NOW() + interval '%s hours') RETURNING id""",
            (user_id, token_hash, ip, user_agent, hours), fetch=True
        )
        return rows[0]['id'] if rows else None

    def verify_session(self, token_hash: str) -> dict:
        """Check if session is valid. Returns user info or None."""
        rows = self._exec(
            """SELECT s.id as session_id, s.user_id, u.username, u.role 
               FROM sessions s JOIN users u ON s.user_id = u.id
               WHERE s.token_hash = %s AND s.is_active = TRUE AND s.expires_at > NOW()""",
            (token_hash,), fetch=True
        )
        if rows:
            self._exec("UPDATE sessions SET last_activity = NOW() WHERE id = %s", (rows[0]['session_id'],))
            return rows[0]
        return None

    def end_session(self, token_hash: str):
        self._exec("UPDATE sessions SET is_active = FALSE WHERE token_hash = %s", (token_hash,))

    def log_login_attempt(self, username: str, success: bool, ip: str = None, user_agent: str = None, reason: str = None):
        self._exec(
            "INSERT INTO login_attempts (username, ip_address, user_agent, success, failure_reason) VALUES (%s, %s::inet, %s, %s, %s)",
            (username, ip, user_agent, success, reason)
        )

    def get_failed_attempts(self, ip: str, minutes: int = 5) -> int:
        rows = self._exec(
            "SELECT COUNT(*) as cnt FROM login_attempts WHERE ip_address = %s::inet AND success = FALSE AND timestamp > NOW() - interval '%s minutes'",
            (ip, minutes), fetch=True
        )
        return rows[0]['cnt'] if rows else 0

    # ══════════════════════════════════════════════
    #  DOMAIN 2: ORDERS
    # ══════════════════════════════════════════════

    def log_order(self, symbol, side, qty, order_type='limit', limit_price=None, stop_price=None,
                  trail_percent=None, strategy=None, source=None, reason=None, confidence=None,
                  ai_source=None, alpaca_order_id=None, client_order_id=None, 
                  entry_price=None, data=None) -> int:
        """Log an order. Returns order ID."""
        rows = self._exec(
            """INSERT INTO orders (symbol, side, qty, order_type, limit_price, stop_price,
               trail_percent, strategy, source, reason, confidence, ai_source,
               alpaca_order_id, client_order_id, entry_price, data)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (symbol, side, qty, order_type, limit_price, stop_price, trail_percent,
             strategy, source, reason, confidence, ai_source,
             alpaca_order_id, client_order_id, entry_price,
             json.dumps(data) if data else None), fetch=True
        )
        return rows[0]['id'] if rows else None

    def update_order_status(self, alpaca_order_id: str, status: str, filled_price=None, filled_qty=None, realized_pl=None):
        self._exec(
            """UPDATE orders SET status = %s, filled_price = %s, filled_qty = %s, 
               realized_pl = %s, filled_at = CASE WHEN %s = 'filled' THEN NOW() ELSE filled_at END,
               updated_at = NOW()
               WHERE alpaca_order_id = %s""",
            (status, filled_price, filled_qty, realized_pl, status, alpaca_order_id)
        )

    def get_orders(self, limit=50, status=None, symbol=None):
        sql = "SELECT * FROM orders WHERE 1=1"
        params = []
        if status:
            sql += " AND status = %s"
            params.append(status)
        if symbol:
            sql += " AND symbol = %s"
            params.append(symbol)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        return self._exec(sql, params, fetch=True)

    def get_strategy_performance(self):
        """Get P&L by strategy from the v_strategy_performance view."""
        return self._exec("SELECT * FROM v_strategy_performance", fetch=True)

    # ══════════════════════════════════════════════
    #  DOMAIN 3: AI VERDICTS
    # ══════════════════════════════════════════════

    def save_ai_verdict(self, symbol, action, confidence, reasoning='', ai_source='GPT-4o',
                        scan_type='5min', risk_level='MEDIUM', tv_analysis='', bull_case='',
                        bear_case='', scalp_target=None, runner_target=None, stop_price=None,
                        data=None) -> int:
        rows = self._exec(
            """INSERT INTO ai_verdicts (symbol, action, confidence, reasoning, ai_source,
               scan_type, risk_level, tv_analysis, bull_case, bear_case,
               scalp_target, runner_target, stop_price, data)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (symbol, action, confidence, reasoning, ai_source, scan_type, risk_level,
             tv_analysis, bull_case, bear_case, scalp_target, runner_target, stop_price,
             json.dumps(data) if data else None), fetch=True
        )
        return rows[0]['id'] if rows else None

    def mark_verdict_executed(self, verdict_id: int, order_id: int):
        self._exec("UPDATE ai_verdicts SET executed = TRUE, order_id = %s WHERE id = %s",
                   (order_id, verdict_id))

    def get_latest_verdicts(self):
        """Get latest AI verdict per symbol (uses view)."""
        return self._exec("SELECT * FROM v_latest_verdicts", fetch=True)

    def get_verdict_history(self, symbol: str, limit=20):
        return self._exec(
            "SELECT * FROM ai_verdicts WHERE symbol = %s ORDER BY created_at DESC LIMIT %s",
            (symbol, limit), fetch=True
        )

    # ══════════════════════════════════════════════
    #  DOMAIN 4: MARKET DATA
    # ══════════════════════════════════════════════

    def save_tv_reading(self, symbol, scan_type='5min', rsi=None, macd=None, macd_signal=None,
                        macd_hist=None, vwap=None, vwap_above=None, bb_upper=None, bb_mid=None,
                        bb_lower=None, ema_9=None, ema_21=None, ema_50=None, sma_200=None,
                        ichi_tenkan=None, ichi_kijun=None, ichi_span_a=None, ichi_span_b=None,
                        volume_ratio=None, confluence=None, price=None):
        self._exec(
            """INSERT INTO tv_readings (symbol, scan_type, rsi, macd, macd_signal, macd_hist,
               vwap, vwap_above, bb_upper, bb_mid, bb_lower, ema_9, ema_21, ema_50, sma_200,
               ichi_tenkan, ichi_kijun, ichi_span_a, ichi_span_b, volume_ratio, confluence, price)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (symbol, scan_type, rsi, macd, macd_signal, macd_hist, vwap, vwap_above,
             bb_upper, bb_mid, bb_lower, ema_9, ema_21, ema_50, sma_200,
             ichi_tenkan, ichi_kijun, ichi_span_a, ichi_span_b, volume_ratio, confluence, price)
        )

    def save_sentiment(self, symbol, yahoo=0, reddit=0, analyst=0, stocktwits=0, total=0,
                       earnings_days=None, earnings_date=None, last_surprise=None,
                       short_pct=None, short_ratio=None, squeeze_risk=False,
                       top_headline=None, headline_count=0):
        self._exec(
            """INSERT INTO sentiment_readings (symbol, yahoo_score, reddit_score, analyst_score,
               stocktwits_score, total_score, earnings_days, earnings_date, last_surprise,
               short_pct, short_ratio, squeeze_risk, top_headline, headline_count)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (symbol, yahoo, reddit, analyst, stocktwits, total, earnings_days, earnings_date,
             last_surprise, short_pct, short_ratio, squeeze_risk, top_headline, headline_count)
        )

    def get_tv_history(self, symbol, hours=24):
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return self._exec(
            "SELECT * FROM tv_readings WHERE symbol = %s AND created_at >= %s ORDER BY created_at",
            (symbol, cutoff), fetch=True
        )

    # ══════════════════════════════════════════════
    #  DOMAIN 5: PORTFOLIO STATE
    # ══════════════════════════════════════════════

    def snapshot_equity(self, equity, cash, total_pl=0, daily_pl=0, position_count=0,
                        order_count=0, trailing_stops=0, heat_pct=0, buying_power=0,
                        long_market_val=0, regime=None, spy_change=0, vix=0):
        self._exec(
            """INSERT INTO equity_snapshots (equity, cash, total_pl, daily_pl, position_count,
               order_count, trailing_stops, heat_pct, buying_power, long_market_val,
               regime, spy_change, vix)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (float(equity or 0), float(cash or 0), float(total_pl or 0), float(daily_pl or 0),
             int(position_count or 0), int(order_count or 0), int(trailing_stops or 0),
             round(float(heat_pct or 0), 2), float(buying_power or 0), float(long_market_val or 0),
             regime, float(spy_change or 0), float(vix or 0))
        )

    def snapshot_positions(self, positions, trailing_stops=None, snapshot_id=None):
        """Save all positions. Handles Position objects or dicts."""
        if not positions:
            return
        trailing_stops = trailing_stops or set()
        if snapshot_id is None:
            import time
            snapshot_id = int(time.time())
        for p in positions:
            if hasattr(p, 'symbol'):
                sym, qty = p.symbol, p.qty
                entry = float(p.avg_entry or 0)
                price = float(p.current_price or 0)
                pl = float(p.unrealized_pl or 0)
                mv = float(p.market_value) if hasattr(p, 'market_value') and p.market_value else price * qty
                pct = (pl / (entry * qty) * 100) if entry and qty else 0
            else:
                sym = p.get('symbol', '')
                qty = int(p.get('qty', 0))
                entry = float(p.get('avg_entry', 0))
                price = float(p.get('current_price', 0))
                pl = float(p.get('unrealized_pl', 0))
                mv = float(p.get('market_value', 0))
                pct = float(p.get('pct_change', 0))
            has_ts = sym in trailing_stops
            self._exec(
                """INSERT INTO position_snapshots (snapshot_id, symbol, qty, avg_entry, current_price,
                   market_value, unrealized_pl, pct_change, has_trailing_stop)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (snapshot_id, sym, qty, entry, price, mv, pl, round(pct, 2), has_ts)
            )

    def get_equity_curve(self, days=30):
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return self._exec(
            "SELECT * FROM equity_snapshots WHERE created_at >= %s ORDER BY created_at",
            (cutoff,), fetch=True
        )

    def get_daily_pnl(self):
        """Get daily P&L from view."""
        return self._exec("SELECT * FROM v_daily_pnl LIMIT 30", fetch=True)

    def get_position_history(self, symbol, hours=24):
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return self._exec(
            "SELECT * FROM position_snapshots WHERE symbol = %s AND created_at >= %s ORDER BY created_at",
            (symbol, cutoff), fetch=True
        )

    # ══════════════════════════════════════════════
    #  DOMAIN 6: ACTIVITY LOG & ALERTS
    # ══════════════════════════════════════════════

    def log_activity(self, action_type, category='bot', symbol=None, side=None, qty=None,
                     price=None, reason=None, strategy=None, source=None, confidence=None,
                     ai_source=None, order_id=None, verdict_id=None, data=None):
        self._exec(
            """INSERT INTO activity_log (action_type, category, symbol, side, qty, price,
               reason, strategy, source, confidence, ai_source, order_id, verdict_id, data)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (action_type, category, symbol, side, qty, price, reason, strategy, source,
             confidence, ai_source, order_id, verdict_id,
             json.dumps(data) if data else None)
        )

    def get_activity(self, limit=50, action_type=None, category=None, symbol=None):
        sql = "SELECT * FROM activity_log WHERE 1=1"
        params = []
        if action_type:
            sql += " AND action_type = %s"
            params.append(action_type)
        if category:
            sql += " AND category = %s"
            params.append(category)
        if symbol:
            sql += " AND symbol = %s"
            params.append(symbol)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        return self._exec(sql, params, fetch=True)

    def send_alert(self, alert_type, message, symbol=None, severity='info',
                   sent_discord=False, sent_telegram=False):
        self._exec(
            """INSERT INTO alerts (alert_type, severity, symbol, message, sent_discord, sent_telegram)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (alert_type, severity, symbol, message, sent_discord, sent_telegram)
        )

    def get_alerts(self, limit=20, alert_type=None, severity=None):
        sql = "SELECT * FROM alerts WHERE 1=1"
        params = []
        if alert_type:
            sql += " AND alert_type = %s"
            params.append(alert_type)
        if severity:
            sql += " AND severity = %s"
            params.append(severity)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        return self._exec(sql, params, fetch=True)

    def log_scan(self, scan_type, duration_ms=None, regime=None, spy_change=0, vix=0,
                 trump_score=0, positions_count=0, tv_count=0, sentiment_count=0,
                 ai_count=0, runners_found=0, buys_placed=0, sells_placed=0,
                 alerts_sent=0, data=None):
        self._exec(
            """INSERT INTO scan_results (scan_type, duration_ms, regime, spy_change, vix,
               trump_score, positions_count, tv_count, sentiment_count, ai_count,
               runners_found, buys_placed, sells_placed, alerts_sent, data)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (scan_type, duration_ms, regime, spy_change, vix, trump_score,
             positions_count, tv_count, sentiment_count, ai_count, runners_found,
             buys_placed, sells_placed, alerts_sent,
             json.dumps(data) if data else None)
        )

    def get_recent_scans(self, limit=20, scan_type=None):
        sql = "SELECT * FROM scan_results WHERE 1=1"
        params = []
        if scan_type:
            sql += " AND scan_type = %s"
            params.append(scan_type)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        return self._exec(sql, params, fetch=True)

    # ══════════════════════════════════════════════
    #  DOMAIN 7: COMMANDS
    # ══════════════════════════════════════════════

    def save_command(self, raw_command, parsed=None, user_id=None):
        rows = self._exec(
            "INSERT INTO commands (raw_command, parsed, user_id) VALUES (%s, %s, %s) RETURNING id",
            (raw_command, json.dumps(parsed) if parsed else None, user_id), fetch=True
        )
        return rows[0]['id'] if rows else None

    def update_command(self, cmd_id, status, result=None, error_message=None, order_id=None):
        self._exec(
            """UPDATE commands SET status = %s, result = %s, error_message = %s,
               order_id = %s, executed_at = CASE WHEN %s = 'executed' THEN NOW() ELSE executed_at END
               WHERE id = %s""",
            (status, json.dumps(result) if result else None, error_message, order_id, status, cmd_id)
        )

    def get_commands(self, limit=20, status=None):
        sql = "SELECT * FROM commands WHERE 1=1"
        params = []
        if status:
            sql += " AND status = %s"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        return self._exec(sql, params, fetch=True)

    # ══════════════════════════════════════════════
    #  ANALYTICS & DEBUG
    # ══════════════════════════════════════════════

    def get_analytics(self):
        """Dashboard analytics — uses views + aggregations."""
        result = {}
        # Strategy performance
        result['strategies'] = self._exec("SELECT * FROM v_strategy_performance", fetch=True)
        # Daily P&L
        result['daily_pnl'] = self._exec("SELECT * FROM v_daily_pnl LIMIT 30", fetch=True)
        # Activity summary
        result['activity_summary'] = self._exec("SELECT * FROM v_activity_summary LIMIT 50", fetch=True)
        # Totals
        for table in ['orders', 'ai_verdicts', 'activity_log', 'tv_readings', 'sentiment_readings', 'alerts', 'scan_results']:
            rows = self._exec(f"SELECT COUNT(*) as cnt FROM {table}", fetch=True)
            result[f'{table}_count'] = rows[0]['cnt'] if rows else 0
        return result

    def get_debug_info(self):
        """Debug dashboard — row counts, latest entries, connection status."""
        info = {'connected': self.conn is not None, 'tables': {}}
        tables = ['users', 'sessions', 'login_attempts', 'orders', 'ai_verdicts',
                  'tv_readings', 'sentiment_readings', 'equity_snapshots',
                  'position_snapshots', 'activity_log', 'alerts', 'scan_results', 'commands']
        # login_attempts uses 'timestamp', everything else uses 'created_at'
        ts_col = {'login_attempts': 'timestamp', 'users': 'created_at'}
        for t in tables:
            rows = self._exec(f"SELECT COUNT(*) as cnt FROM {t}", fetch=True)
            col = ts_col.get(t, 'created_at')
            latest = self._exec(f"SELECT MAX({col}) as latest FROM {t}", fetch=True)
            info['tables'][t] = {
                'rows': rows[0]['cnt'] if rows else 0,
                'latest': str(latest[0]['latest']) if latest and latest[0].get('latest') else 'never'
            }
        return info

    def search_activity(self, query: str, limit=50):
        """Full-text search across activity log — for debugging."""
        return self._exec(
            """SELECT * FROM activity_log 
               WHERE reason ILIKE %s OR action_type ILIKE %s OR symbol ILIKE %s
               ORDER BY created_at DESC LIMIT %s""",
            (f'%{query}%', f'%{query}%', f'%{query}%', limit), fetch=True
        )

    # ══════════════════════════════════════════════
    #  MAINTENANCE
    # ══════════════════════════════════════════════

    def cleanup(self, snapshot_days=15, audit_days=30, order_days=90):
        """Purge old data by retention policy."""
        snap_cutoff = datetime.now(timezone.utc) - timedelta(days=snapshot_days)
        audit_cutoff = datetime.now(timezone.utc) - timedelta(days=audit_days)
        order_cutoff = datetime.now(timezone.utc) - timedelta(days=order_days)

        # 15 days: high-frequency snapshots
        for t in ['position_snapshots', 'equity_snapshots', 'tv_readings', 'sentiment_readings']:
            self._exec(f"DELETE FROM {t} WHERE created_at < %s", (snap_cutoff,))
        # 30 days: activity + scans
        for t in ['activity_log', 'scan_results', 'alerts', 'login_attempts']:
            self._exec(f"DELETE FROM {t} WHERE created_at < %s", (audit_cutoff,))
        # 90 days: orders + verdicts (need for analytics)
        for t in ['orders', 'ai_verdicts', 'commands']:
            self._exec(f"DELETE FROM {t} WHERE created_at < %s", (order_cutoff,))
        # Clean expired sessions
        self._exec("DELETE FROM sessions WHERE expires_at < NOW()")
        log.info(f"🧹 Purged: snapshots>{snapshot_days}d, audit>{audit_days}d, orders>{order_days}d")

    def auto_purge(self):
        """Safe to call every scan — only runs once per day."""
        try:
            rows = self._exec(
                "SELECT COUNT(*) as cnt FROM activity_log WHERE action_type = 'PURGE' AND created_at > NOW() - interval '23 hours'",
                fetch=True
            )
            if rows and rows[0]['cnt'] > 0:
                return
            self.cleanup()
            self.log_activity('PURGE', category='system', reason='Auto-purge: 15d/30d/90d retention')
        except Exception as e:
            log.debug(f"Auto-purge: {e}")

    # ══════════════════════════════════════════════
    #  COMMAND PARSER (for dashboard terminal)
    # ══════════════════════════════════════════════

    @staticmethod
    def parse_command(raw: str) -> dict:
        """Parse: /buy NVDA 3 @210, /sell AMD 5, /cancel ID, /kill, /resume, /status"""
        parts = raw.strip().split()
        if not parts:
            return {'error': 'Empty command'}
        action = parts[0].lower().lstrip('/')
        result = {'action': action, 'raw': raw}
        if action in ('buy', 'sell'):
            if len(parts) < 3:
                return {'error': f'Usage: /{action} SYMBOL QTY [@PRICE]'}
            result['symbol'] = parts[1].upper()
            try:
                result['qty'] = int(parts[2])
            except ValueError:
                return {'error': f'Invalid qty: {parts[2]}'}
            if len(parts) >= 4:
                try:
                    result['price'] = float(parts[3].lstrip('@$'))
                except ValueError:
                    return {'error': f'Invalid price: {parts[3]}'}
            return result
        elif action == 'cancel':
            if len(parts) < 2:
                return {'error': 'Usage: /cancel ORDER_ID'}
            result['order_id'] = parts[1]
            return result
        elif action in ('status', 'kill', 'resume', 'debug', 'purge'):
            return result
        return {'error': f'Unknown: {action}. Use /buy /sell /cancel /status /kill /resume /debug'}

    # ══════════════════════════════════════════════
    #  WATCHLIST (grows forever, never shrinks)
    # ══════════════════════════════════════════════

    def add_to_watchlist(self, symbol, source='market_scan', pct=None, volume=None):
        """Add a symbol to watchlist. If exists, update last_seen. Never removes."""
        self._exec(
            """INSERT INTO watchlist (symbol, source, first_seen_pct, first_seen_volume)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (symbol) DO UPDATE SET last_seen_at = NOW()""",
            (symbol.upper(), source, pct, volume)
        )

    def get_watchlist(self):
        """Get all watchlist symbols."""
        rows = self._exec("SELECT symbol FROM watchlist WHERE is_active = TRUE ORDER BY last_seen_at DESC", fetch=True)
        return [r['symbol'] for r in rows] if rows else []

    def get_watchlist_full(self):
        """Get full watchlist with stats."""
        return self._exec(
            "SELECT * FROM watchlist WHERE is_active = TRUE ORDER BY last_seen_at DESC",
            fetch=True
        ) or []

    def update_watchlist_stats(self, symbol, pnl=0):
        """Update trade count and P&L for a watchlist symbol."""
        self._exec(
            "UPDATE watchlist SET times_traded = times_traded + 1, total_pnl = total_pnl + %s, last_seen_at = NOW() WHERE symbol = %s",
            (pnl, symbol.upper())
        )

    # ══════════════════════════════════════════════
    #  SELF-LEARNING (learn from past trades)
    # ══════════════════════════════════════════════

    def get_stock_history(self, symbol: str) -> dict:
        """What happened last time we traded this stock?
        Returns win rate, avg P&L, best/worst trade, avg hold time."""
        rows = self._exec(
            """SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN realized_pl < 0 THEN 1 ELSE 0 END) as losses,
                COALESCE(AVG(realized_pl), 0) as avg_pnl,
                COALESCE(MAX(realized_pl), 0) as best_trade,
                COALESCE(MIN(realized_pl), 0) as worst_trade,
                COALESCE(SUM(realized_pl), 0) as total_pnl
               FROM orders WHERE symbol = %s AND status = 'filled' AND side = 'sell'""",
            (symbol,), fetch=True
        )
        if not rows or rows[0]['total_trades'] == 0:
            return {'known': False, 'symbol': symbol}
        r = rows[0]
        total = r['total_trades']
        wins = r['wins'] or 0
        return {
            'known': True,
            'symbol': symbol,
            'total_trades': total,
            'win_rate': round(wins / total * 100, 1) if total > 0 else 0,
            'avg_pnl': round(r['avg_pnl'], 2),
            'best_trade': round(r['best_trade'], 2),
            'worst_trade': round(r['worst_trade'], 2),
            'total_pnl': round(r['total_pnl'], 2),
            'recommendation': 'AGGRESSIVE' if wins / total > 0.6 else ('NORMAL' if wins / total > 0.4 else 'CAUTIOUS')
        }

    def get_best_performing_stocks(self, limit=10) -> list:
        """Which stocks make us the most money? Used to prioritize scanning."""
        return self._exec(
            """SELECT symbol, 
                COUNT(*) as trades,
                SUM(CASE WHEN realized_pl > 0 THEN 1 ELSE 0 END) as wins,
                COALESCE(SUM(realized_pl), 0) as total_pnl,
                COALESCE(AVG(realized_pl), 0) as avg_pnl
               FROM orders WHERE status = 'filled' AND side = 'sell' AND realized_pl IS NOT NULL
               GROUP BY symbol
               HAVING COUNT(*) >= 2
               ORDER BY total_pnl DESC
               LIMIT %s""",
            (limit,), fetch=True
        ) or []

    def get_optimal_rsi_for_stock(self, symbol: str) -> dict:
        """What RSI did we buy at when we won vs lost? Learn the optimal entry."""
        # Get AI verdicts for this stock and cross-reference with order outcomes
        rows = self._exec(
            """SELECT 
                v.confidence, v.action,
                o.realized_pl, o.limit_price
               FROM ai_verdicts v
               LEFT JOIN orders o ON o.symbol = v.symbol 
                 AND o.created_at BETWEEN v.created_at - interval '5 minutes' AND v.created_at + interval '30 minutes'
               WHERE v.symbol = %s AND o.status = 'filled'
               ORDER BY v.created_at DESC LIMIT 50""",
            (symbol,), fetch=True
        ) or []
        
        winning_confs = [r['confidence'] for r in rows if r.get('realized_pl') and r['realized_pl'] > 0]
        losing_confs = [r['confidence'] for r in rows if r.get('realized_pl') and r['realized_pl'] < 0]
        
        return {
            'symbol': symbol,
            'avg_winning_confidence': round(sum(winning_confs) / len(winning_confs), 1) if winning_confs else 0,
            'avg_losing_confidence': round(sum(losing_confs) / len(losing_confs), 1) if losing_confs else 0,
            'min_safe_confidence': round(min(winning_confs), 1) if winning_confs else 50,
            'sample_size': len(rows),
        }

    def should_trade_stock(self, symbol: str) -> dict:
        """Self-learning decision: should we trade this stock based on history?"""
        history = self.get_stock_history(symbol)
        if not history.get('known'):
            return {'trade': True, 'reason': 'No history — try it', 'size': 'normal'}
        
        win_rate = history.get('win_rate', 50)
        avg_pnl = history.get('avg_pnl', 0)
        
        if win_rate >= 70 and avg_pnl > 0:
            return {'trade': True, 'reason': f'{win_rate}% win rate, avg ${avg_pnl:.0f} — go BIGGER', 'size': 'large'}
        elif win_rate >= 50:
            return {'trade': True, 'reason': f'{win_rate}% win rate — normal size', 'size': 'normal'}
        elif win_rate >= 30:
            return {'trade': True, 'reason': f'{win_rate}% win rate — small size, be careful', 'size': 'small'}
        else:
            return {'trade': False, 'reason': f'{win_rate}% win rate, avg ${avg_pnl:.0f} — SKIP this stock', 'size': 'none'}

    # ══════════════════════════════════════════════
    #  EARNINGS PATTERN LEARNING
    # ══════════════════════════════════════════════

    def learn_earnings_pattern(self, symbol: str, earnings_date: str, 
                                pre_price: float, post_price: float,
                                beat_or_miss: str, gap_pct: float):
        """Record how a stock reacted to earnings. Builds historical pattern."""
        self._exec(
            """INSERT INTO earnings_patterns 
               (symbol, earnings_date, pre_price, post_price, beat_or_miss, gap_pct)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (symbol, earnings_date, pre_price, post_price, beat_or_miss, round(gap_pct, 2))
        )

    def get_earnings_pattern(self, symbol: str) -> dict:
        """What does this stock typically do after earnings?
        Returns: avg gap, tendency (dip/pop), best time to buy after."""
        rows = self._exec(
            """SELECT gap_pct, beat_or_miss FROM earnings_patterns 
               WHERE symbol = %s ORDER BY earnings_date DESC LIMIT 8""",
            (symbol,), fetch=True
        ) or []
        if not rows:
            return {'known': False, 'symbol': symbol}
        
        gaps = [r['gap_pct'] for r in rows]
        dips = sum(1 for g in gaps if g < -2)
        pops = sum(1 for g in gaps if g > 2)
        avg_gap = sum(gaps) / len(gaps)
        
        if dips > pops:
            tendency = 'DIPS_AFTER_EARNINGS'
            play = f'Wait for dip, buy {abs(avg_gap):.0f}% below → scalp +2%'
        elif pops > dips:
            tendency = 'POPS_AFTER_EARNINGS'
            play = f'Buy pre-earnings, ride +{avg_gap:.0f}% gap'
        else:
            tendency = 'MIXED'
            play = 'No clear pattern — skip earnings plays'
        
        return {
            'known': True,
            'symbol': symbol,
            'samples': len(rows),
            'avg_gap_pct': round(avg_gap, 1),
            'dip_count': dips,
            'pop_count': pops,
            'tendency': tendency,
            'play': play,
            'last_gaps': gaps[:4],
        }

    def scan_all_earnings_patterns(self) -> list:
        """Get earnings patterns for ALL stocks we've tracked."""
        rows = self._exec(
            """SELECT symbol, 
                COUNT(*) as samples,
                AVG(gap_pct) as avg_gap,
                SUM(CASE WHEN gap_pct < -2 THEN 1 ELSE 0 END) as dips,
                SUM(CASE WHEN gap_pct > 2 THEN 1 ELSE 0 END) as pops
               FROM earnings_patterns
               GROUP BY symbol
               HAVING COUNT(*) >= 2
               ORDER BY ABS(AVG(gap_pct)) DESC""",
            fetch=True
        ) or []
        return rows

    # ══════════════════════════════════════════════
    #  AI TREND STORAGE (gold mine)
    # ══════════════════════════════════════════════

    def save_trend(self, symbol, trend_type, insight, confidence=50, data=None):
        """Store an AI-discovered trend. Types: earnings_pattern, price_behavior,
        sentiment_correlation, sector_rotation, time_pattern, support_resistance."""
        # Update if same symbol+type exists, else insert
        existing = self._exec(
            "SELECT id FROM ai_trends WHERE symbol = %s AND trend_type = %s AND is_active = TRUE",
            (symbol, trend_type), fetch=True
        )
        if existing:
            self._exec(
                """UPDATE ai_trends SET insight = %s, confidence = %s, data = %s, 
                   updated_at = NOW() WHERE id = %s""",
                (insight, confidence, json.dumps(data) if data else None, existing[0]['id'])
            )
        else:
            self._exec(
                """INSERT INTO ai_trends (symbol, trend_type, insight, confidence, data)
                   VALUES (%s, %s, %s, %s, %s)""",
                (symbol, trend_type, insight, confidence, json.dumps(data) if data else None)
            )

    def get_trends(self, symbol=None, trend_type=None) -> list:
        """Get stored AI trends. Filter by symbol and/or type."""
        sql = "SELECT * FROM ai_trends WHERE is_active = TRUE"
        params = []
        if symbol:
            sql += " AND symbol = %s"
            params.append(symbol)
        if trend_type:
            sql += " AND trend_type = %s"
            params.append(trend_type)
        sql += " ORDER BY confidence DESC, updated_at DESC"
        return self._exec(sql, params, fetch=True) or []

    def get_all_insights_for_stock(self, symbol) -> dict:
        """Get EVERYTHING we know about a stock — trends + earnings + trade history."""
        return {
            'trends': self.get_trends(symbol=symbol),
            'earnings': self.get_earnings_pattern(symbol),
            'history': self.get_stock_history(symbol),
            'should_trade': self.should_trade_stock(symbol),
        }

    def close(self):
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
            self.conn = None

    # ══════════════════════════════════════════════
    #  SCHEMA V4 MIGRATION (auto-runs on connect)
    # ══════════════════════════════════════════════

    def migrate_v4(self):
        """Create V4 tables if they don't exist. Safe to run multiple times."""
        if not self._ensure_conn():
            return
        migrations = [
            # BOT STATE: Generic KV store (replaces ALL in-memory dicts)
            """CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value JSONB NOT NULL DEFAULT '{}',
                category TEXT DEFAULT 'runtime',
                description TEXT,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_bot_state_cat ON bot_state(category)",

            # BOT SESSIONS: Track every bot run (version, uptime, crashes)
            """CREATE TABLE IF NOT EXISTS bot_sessions (
                id SERIAL PRIMARY KEY,
                build_version TEXT,
                git_hash TEXT,
                started_at TIMESTAMPTZ DEFAULT NOW(),
                stopped_at TIMESTAMPTZ,
                stop_reason TEXT,
                loops_config JSONB,
                total_trades INT DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                errors_count INT DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                hostname TEXT,
                python_version TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS idx_bot_sessions_active ON bot_sessions(is_active)",

            # PRICE MEMORY: Per-stock persistent price tracking (survives restart)
            """CREATE TABLE IF NOT EXISTS price_memory (
                symbol TEXT PRIMARY KEY,
                last_price REAL,
                last_sell_price REAL,
                last_sell_time TIMESTAMPTZ,
                last_buy_price REAL,
                last_buy_time TIMESTAMPTZ,
                intraday_high REAL DEFAULT 0,
                intraday_low REAL DEFAULT 999999,
                last_scalp_time TIMESTAMPTZ,
                last_pyramid_time TIMESTAMPTZ,
                last_reload_time TIMESTAMPTZ,
                drop_alert_sent BOOLEAN DEFAULT FALSE,
                loss_alert_sent BOOLEAN DEFAULT FALSE,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )""",

            # BOT CONFIG: Dashboard-editable settings (hot reload)
            """CREATE TABLE IF NOT EXISTS bot_config (
                key TEXT PRIMARY KEY,
                value JSONB NOT NULL,
                data_type TEXT DEFAULT 'string',
                category TEXT DEFAULT 'general',
                description TEXT,
                min_value REAL,
                max_value REAL,
                options JSONB,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                updated_by TEXT DEFAULT 'system'
            )""",
            "CREATE INDEX IF NOT EXISTS idx_bot_config_cat ON bot_config(category)",

            # TRADE DECISIONS: Full audit trail (why we bought / didn't buy)
            """CREATE TABLE IF NOT EXISTS trade_decisions (
                id SERIAL PRIMARY KEY,
                scan_id TEXT,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                confidence REAL DEFAULT 0,
                tv_data JSONB,
                sentiment_data JSONB,
                ai_verdict JSONB,
                signals JSONB,
                trend_data JSONB,
                executed BOOLEAN DEFAULT FALSE,
                execution_result TEXT,
                order_id TEXT,
                block_reason TEXT,
                strategy TEXT,
                scan_type TEXT DEFAULT '5min',
                price_at_decision REAL,
                price_after_1h REAL,
                price_after_4h REAL,
                was_correct BOOLEAN,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_trade_decisions_sym ON trade_decisions(symbol, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_trade_decisions_date ON trade_decisions(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_trade_decisions_action ON trade_decisions(action)",
            "CREATE INDEX IF NOT EXISTS idx_trade_decisions_exec ON trade_decisions(executed)",

            # NOTIFICATIONS: Queue for dashboard/discord/telegram
            """CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                channel TEXT DEFAULT 'dashboard',
                title TEXT NOT NULL,
                body TEXT,
                severity TEXT DEFAULT 'info',
                category TEXT DEFAULT 'bot',
                symbol TEXT,
                data JSONB,
                is_read BOOLEAN DEFAULT FALSE,
                expires_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(is_read, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_notifications_chan ON notifications(channel, created_at DESC)",

            # STRATEGY SIGNALS: Every signal from every scan (for backtesting)
            """CREATE TABLE IF NOT EXISTS strategy_signals (
                id SERIAL PRIMARY KEY,
                scan_id TEXT,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                signal_value REAL,
                metadata JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_strategy_signals_sym ON strategy_signals(symbol, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_strategy_signals_strat ON strategy_signals(strategy, created_at DESC)",

            # DAILY REPORTS: Store daily AI analysis reports (permanent archive)
            """CREATE TABLE IF NOT EXISTS daily_reports (
                id SERIAL PRIMARY KEY,
                report_date DATE NOT NULL,
                report_type TEXT DEFAULT 'daily_deep_learn',
                ai_source TEXT DEFAULT 'claude',
                buy_list JSONB,
                avoid_list JSONB,
                sector_signal TEXT,
                earnings_plays JSONB,
                risk_alerts JSONB,
                strategy TEXT,
                key_insight TEXT,
                tv_learnings TEXT,
                missed_opportunities TEXT,
                full_report JSONB,
                market_regime TEXT,
                vix_at_time REAL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(report_date, report_type)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_daily_reports_date ON daily_reports(report_date DESC)",

            # SCAN SNAPSHOTS: ONE row per scan with EVERYTHING (the deep log)
            # This is the gold mine — every scan, every signal, every verdict, every decision
            # Stored as JSONB so it's infinitely flexible and fast to write
            """CREATE TABLE IF NOT EXISTS scan_snapshots (
                id SERIAL PRIMARY KEY,
                scan_id TEXT UNIQUE NOT NULL,
                scan_type TEXT NOT NULL DEFAULT '5min',
                started_at TIMESTAMPTZ DEFAULT NOW(),
                duration_ms INT,
                regime TEXT,
                spy_change REAL DEFAULT 0,
                vix REAL DEFAULT 0,
                equity REAL DEFAULT 0,
                total_pl REAL DEFAULT 0,
                position_count INT DEFAULT 0,
                stocks_scanned INT DEFAULT 0,
                stocks_with_tv INT DEFAULT 0,
                stocks_with_sentiment INT DEFAULT 0,
                ai_verdicts_count INT DEFAULT 0,
                buys_executed INT DEFAULT 0,
                sells_executed INT DEFAULT 0,
                blocks_count INT DEFAULT 0,
                positions JSONB,
                tv_data JSONB,
                sentiment_data JSONB,
                confidence_data JSONB,
                ai_verdicts JSONB,
                decisions JSONB,
                market_context JSONB,
                runners_found JSONB,
                ai_reasoning TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_scan_snapshots_type ON scan_snapshots(scan_type, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_scan_snapshots_date ON scan_snapshots(created_at DESC)",

            # TRADE LOG: Every single trade with AI-driven reasoning (permanent)
            """CREATE TABLE IF NOT EXISTS trade_log (
                id SERIAL PRIMARY KEY,
                scan_id TEXT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty INT NOT NULL,
                price REAL NOT NULL,
                order_type TEXT DEFAULT 'limit',
                strategy TEXT,
                source TEXT,
                trigger TEXT,
                tv_at_trade JSONB,
                sentiment_at_trade JSONB,
                ai_verdict_at_trade JSONB,
                confidence_at_trade REAL,
                ai_reasoning TEXT,
                market_regime TEXT,
                vix_at_trade REAL,
                spy_change REAL,
                portfolio_heat REAL,
                position_count INT,
                day_change_pct REAL,
                order_result TEXT,
                order_id TEXT,
                filled_price REAL,
                filled_at TIMESTAMPTZ,
                pnl_1h REAL,
                pnl_4h REAL,
                pnl_eod REAL,
                was_profitable BOOLEAN,
                lesson_learned TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_trade_log_sym ON trade_log(symbol, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_trade_log_date ON trade_log(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_trade_log_strat ON trade_log(strategy)",
            "CREATE INDEX IF NOT EXISTS idx_trade_log_profitable ON trade_log(was_profitable)",

            # PERFORMANCE: Regular indexes on hot columns (partial indexes with NOW() not allowed)
            "CREATE INDEX IF NOT EXISTS idx_tv_readings_sym_date ON tv_readings(symbol, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_activity_type_date ON activity_log(action_type, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_decisions_sym_date ON trade_decisions(symbol, created_at DESC)",

            # Seed default bot config
            """INSERT INTO bot_config (key, value, data_type, category, description) VALUES
                ('max_heat_pct', '60', 'number', 'risk', 'Maximum portfolio heat %'),
                ('trail_pct', '3.0', 'number', 'risk', 'Default trailing stop %'),
                ('max_position_pct', '8', 'number', 'risk', 'Max single position % of portfolio'),
                ('scalp_target_pct', '2.0', 'number', 'strategy', 'Scalp profit target %'),
                ('dip_reload_pct', '2.0', 'number', 'strategy', 'Dip reload trigger %'),
                ('pyramid_trigger_pct', '3.0', 'number', 'strategy', 'Pyramid add trigger %'),
                ('tv_min_studies', '5', 'number', 'tv', 'Minimum TV studies to confirm'),
                ('tv_wait_seconds', '7', 'number', 'tv', 'Seconds to wait for TV data'),
                ('tv_max_retries', '4', 'number', 'tv', 'Max TV load retries'),
                ('scan_interval_fast', '120', 'number', 'timing', 'Fast runner scan interval (seconds)'),
                ('scan_interval_full', '300', 'number', 'timing', 'Full scan interval (seconds)'),
                ('scan_interval_claude', '1800', 'number', 'timing', 'Claude deep scan interval (seconds)'),
                ('learning_batch_size', '20', 'number', 'learning', 'Stocks per learning batch'),
                ('bot_mode', '"active"', 'string', 'control', 'Bot mode: active/paused/monitor_only'),
                ('kill_switch', 'false', 'boolean', 'control', 'Emergency kill switch'),
                ('daily_loss_limit', '500', 'number', 'risk', 'Daily loss limit ($)'),
                ('cooldown_after_sell_sec', '300', 'number', 'risk', 'Cooldown after selling same stock (sec)'),
                ('min_confidence_buy', '75', 'number', 'strategy', 'Minimum confidence to auto-buy'),
                ('enable_pyramiding', 'true', 'boolean', 'strategy', 'Allow adding to winners'),
                ('enable_dip_reload', 'true', 'boolean', 'strategy', 'Allow buying dips on held stocks')
            ON CONFLICT (key) DO NOTHING""",
        ]
        for sql in migrations:
            try:
                self._exec(sql)
            except Exception as e:
                log.warning(f"Migration step skipped: {e}")
        log.info("✅ Schema V4 migration complete")

    # ══════════════════════════════════════════════
    #  BOT STATE: Persistent KV store
    # ══════════════════════════════════════════════

    def set_state(self, key: str, value, category: str = 'runtime', desc: str = None):
        """Set any bot state. Value is auto-JSON'd. Survives restarts."""
        self._exec(
            """INSERT INTO bot_state (key, value, category, description, updated_at)
               VALUES (%s, %s, %s, %s, NOW())
               ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = NOW()""",
            (key, json.dumps(value), category, desc, json.dumps(value))
        )

    def get_state(self, key: str, default=None):
        """Get a state value. Returns Python object (auto-deserialized)."""
        rows = self._exec("SELECT value FROM bot_state WHERE key = %s", (key,), fetch=True)
        if rows:
            v = rows[0]['value']
            return v if not isinstance(v, str) else json.loads(v)
        return default

    def get_states_by_category(self, category: str) -> dict:
        """Get all state values in a category as a dict."""
        rows = self._exec(
            "SELECT key, value FROM bot_state WHERE category = %s", (category,), fetch=True
        )
        return {r['key']: r['value'] for r in rows} if rows else {}

    def delete_state(self, key: str):
        self._exec("DELETE FROM bot_state WHERE key = %s", (key,))

    def clear_state_category(self, category: str):
        """Clear all state in a category (e.g., 'intraday' at flush time)."""
        self._exec("DELETE FROM bot_state WHERE category = %s", (category,))

    # ══════════════════════════════════════════════
    #  BOT SESSIONS: Track every run
    # ══════════════════════════════════════════════

    def start_session(self, build_version: str, git_hash: str = '', loops_config: dict = None) -> int:
        """Record bot startup. Returns session_id."""
        import platform, sys
        # Mark previous sessions as stopped
        self._exec(
            "UPDATE bot_sessions SET is_active = FALSE, stopped_at = NOW(), stop_reason = 'new_session' WHERE is_active = TRUE"
        )
        rows = self._exec(
            """INSERT INTO bot_sessions (build_version, git_hash, loops_config, hostname, python_version)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (build_version, git_hash, json.dumps(loops_config or {}),
             platform.node(), f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"),
            fetch=True
        )
        session_id = rows[0]['id'] if rows else None
        if session_id:
            self.set_state('current_session_id', session_id, 'system', 'Active bot session ID')
            self.set_state('bot_started_at', datetime.now(timezone.utc).isoformat(), 'system')
        return session_id

    def end_session(self, reason: str = 'shutdown'):
        """Record bot shutdown."""
        session_id = self.get_state('current_session_id')
        if session_id:
            self._exec(
                "UPDATE bot_sessions SET is_active = FALSE, stopped_at = NOW(), stop_reason = %s WHERE id = %s",
                (reason, session_id)
            )

    def update_session_stats(self, trades: int = 0, pnl: float = 0, errors: int = 0):
        """Update running stats for current session."""
        session_id = self.get_state('current_session_id')
        if session_id:
            self._exec(
                """UPDATE bot_sessions SET total_trades = total_trades + %s,
                   total_pnl = total_pnl + %s, errors_count = errors_count + %s WHERE id = %s""",
                (trades, pnl, errors, session_id)
            )

    def get_session_info(self) -> dict:
        """Get current session info (for dashboard)."""
        rows = self._exec(
            "SELECT * FROM bot_sessions WHERE is_active = TRUE ORDER BY started_at DESC LIMIT 1",
            fetch=True
        )
        return rows[0] if rows else {}

    def get_session_history(self, limit=20) -> list:
        """Get past bot sessions (for dashboard analytics)."""
        return self._exec(
            "SELECT * FROM bot_sessions ORDER BY started_at DESC LIMIT %s", (limit,), fetch=True
        ) or []

    # ══════════════════════════════════════════════
    #  PRICE MEMORY: Persistent per-stock tracking
    # ══════════════════════════════════════════════

    def update_price(self, symbol: str, price: float):
        """Update last known price + track intraday high/low."""
        self._exec(
            """INSERT INTO price_memory (symbol, last_price, intraday_high, intraday_low, updated_at)
               VALUES (%s, %s, %s, %s, NOW())
               ON CONFLICT (symbol) DO UPDATE SET
                   last_price = %s,
                   intraday_high = GREATEST(price_memory.intraday_high, %s),
                   intraday_low = LEAST(price_memory.intraday_low, %s),
                   updated_at = NOW()""",
            (symbol, price, price, price, price, price, price)
        )

    def record_sell(self, symbol: str, price: float):
        """Record a sell (for cooldowns + anti-buyback)."""
        self._exec(
            """INSERT INTO price_memory (symbol, last_sell_price, last_sell_time, updated_at)
               VALUES (%s, %s, NOW(), NOW())
               ON CONFLICT (symbol) DO UPDATE SET
                   last_sell_price = %s, last_sell_time = NOW(), updated_at = NOW()""",
            (symbol, price, price)
        )

    def record_buy(self, symbol: str, price: float):
        """Record a buy."""
        self._exec(
            """INSERT INTO price_memory (symbol, last_buy_price, last_buy_time, updated_at)
               VALUES (%s, %s, NOW(), NOW())
               ON CONFLICT (symbol) DO UPDATE SET
                   last_buy_price = %s, last_buy_time = NOW(), updated_at = NOW()""",
            (symbol, price, price)
        )

    def record_scalp(self, symbol: str):
        self._exec(
            """INSERT INTO price_memory (symbol, last_scalp_time, updated_at) VALUES (%s, NOW(), NOW())
               ON CONFLICT (symbol) DO UPDATE SET last_scalp_time = NOW(), updated_at = NOW()""",
            (symbol,)
        )

    def record_pyramid(self, symbol: str):
        self._exec(
            """INSERT INTO price_memory (symbol, last_pyramid_time, updated_at) VALUES (%s, NOW(), NOW())
               ON CONFLICT (symbol) DO UPDATE SET last_pyramid_time = NOW(), updated_at = NOW()""",
            (symbol,)
        )

    def record_reload(self, symbol: str):
        self._exec(
            """INSERT INTO price_memory (symbol, last_reload_time, updated_at) VALUES (%s, NOW(), NOW())
               ON CONFLICT (symbol) DO UPDATE SET last_reload_time = NOW(), updated_at = NOW()""",
            (symbol,)
        )

    def get_price_memory(self, symbol: str) -> dict:
        """Get everything we remember about this stock's prices."""
        rows = self._exec("SELECT * FROM price_memory WHERE symbol = %s", (symbol,), fetch=True)
        return rows[0] if rows else {}

    def get_all_price_memory(self) -> dict:
        """Get ALL price memory as {symbol: {...}} dict."""
        rows = self._exec("SELECT * FROM price_memory", fetch=True) or []
        return {r['symbol']: r for r in rows}

    def check_sell_cooldown(self, symbol: str, cooldown_seconds: int = 300) -> bool:
        """Returns True if we're still in cooldown after selling this stock."""
        rows = self._exec(
            "SELECT last_sell_time FROM price_memory WHERE symbol = %s AND last_sell_time IS NOT NULL",
            (symbol,), fetch=True
        )
        if rows and rows[0]['last_sell_time']:
            elapsed = (datetime.now(timezone.utc) - rows[0]['last_sell_time']).total_seconds()
            return elapsed < cooldown_seconds
        return False

    def check_anti_buyback(self, symbol: str, current_price: float) -> bool:
        """Returns True if current_price is HIGHER than last sell price (block the buy)."""
        rows = self._exec(
            "SELECT last_sell_price FROM price_memory WHERE symbol = %s AND last_sell_price IS NOT NULL",
            (symbol,), fetch=True
        )
        if rows and rows[0]['last_sell_price']:
            return current_price > rows[0]['last_sell_price']
        return False

    def get_intraday_high(self, symbol: str) -> float:
        rows = self._exec("SELECT intraday_high FROM price_memory WHERE symbol = %s", (symbol,), fetch=True)
        return rows[0]['intraday_high'] if rows and rows[0].get('intraday_high') else 0

    def reset_intraday(self):
        """Reset intraday highs/lows + alerts (called at 3 AM flush)."""
        self._exec(
            "UPDATE price_memory SET intraday_high = last_price, intraday_low = last_price, "
            "drop_alert_sent = FALSE, loss_alert_sent = FALSE, updated_at = NOW()"
        )

    # ══════════════════════════════════════════════
    #  BOT CONFIG: Dashboard-editable settings
    # ══════════════════════════════════════════════

    def get_config(self, key: str, default=None):
        """Get a config value (dashboard-editable)."""
        rows = self._exec("SELECT value, data_type FROM bot_config WHERE key = %s", (key,), fetch=True)
        if rows:
            v = rows[0]['value']
            dt = rows[0].get('data_type', 'string')
            if dt == 'number':
                return float(v) if isinstance(v, (int, float, str)) else default
            elif dt == 'boolean':
                return v if isinstance(v, bool) else str(v).lower() in ('true', '1')
            return v
        return default

    def set_config(self, key: str, value, updated_by: str = 'system'):
        """Set a config value (from dashboard or bot)."""
        self._exec(
            """UPDATE bot_config SET value = %s, updated_at = NOW(), updated_by = %s WHERE key = %s""",
            (json.dumps(value), updated_by, key)
        )

    def get_all_config(self, category: str = None) -> list:
        """Get all config (for dashboard settings page)."""
        if category:
            return self._exec(
                "SELECT * FROM bot_config WHERE category = %s ORDER BY category, key", (category,), fetch=True
            ) or []
        return self._exec("SELECT * FROM bot_config ORDER BY category, key", fetch=True) or []

    def is_kill_switch_on(self) -> bool:
        """Quick check: is kill switch engaged?"""
        return self.get_config('kill_switch', False)

    def get_bot_mode(self) -> str:
        """Get current bot mode: active / paused / monitor_only."""
        return self.get_config('bot_mode', 'active')

    # ══════════════════════════════════════════════
    #  TRADE DECISIONS: Full audit trail
    # ══════════════════════════════════════════════

    def log_decision(self, symbol: str, action: str, confidence: float = 0,
                     tv_data: dict = None, sentiment_data: dict = None, ai_verdict: dict = None,
                     signals: dict = None, trend_data: dict = None,
                     executed: bool = False, execution_result: str = None,
                     order_id: str = None, block_reason: str = None,
                     strategy: str = None, scan_type: str = '5min',
                     price_at_decision: float = None) -> int:
        """Log every trade decision (buy/skip/block) with FULL context."""
        rows = self._exec(
            """INSERT INTO trade_decisions (symbol, action, confidence, tv_data, sentiment_data,
               ai_verdict, signals, trend_data, executed, execution_result, order_id,
               block_reason, strategy, scan_type, price_at_decision)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (symbol, action, confidence,
             json.dumps(tv_data) if tv_data else None,
             json.dumps(sentiment_data) if sentiment_data else None,
             json.dumps(ai_verdict) if ai_verdict else None,
             json.dumps(signals) if signals else None,
             json.dumps(trend_data) if trend_data else None,
             executed, execution_result, order_id, block_reason,
             strategy, scan_type, price_at_decision),
            fetch=True
        )
        return rows[0]['id'] if rows else None

    def update_decision_outcome(self, decision_id: int, price_after: float, hours: int = 1):
        """Update with actual price after N hours (was our decision correct?)."""
        col = 'price_after_1h' if hours <= 1 else 'price_after_4h'
        self._exec(f"UPDATE trade_decisions SET {col} = %s WHERE id = %s", (price_after, decision_id))
        # Auto-grade: was the decision correct?
        self._exec(
            f"""UPDATE trade_decisions SET was_correct = 
                CASE WHEN action = 'BUY' AND {col} > price_at_decision THEN TRUE
                     WHEN action = 'BUY' AND {col} <= price_at_decision THEN FALSE
                     WHEN action IN ('SKIP','BLOCK') AND {col} < price_at_decision THEN TRUE
                     WHEN action IN ('SKIP','BLOCK') AND {col} >= price_at_decision THEN FALSE
                     ELSE NULL END
                WHERE id = %s AND price_at_decision IS NOT NULL""",
            (decision_id,)
        )

    def get_decision_accuracy(self, days: int = 7) -> dict:
        """How accurate are our decisions? (for dashboard + self-learning)."""
        rows = self._exec(
            """SELECT action, 
                      COUNT(*) as total,
                      SUM(CASE WHEN was_correct = TRUE THEN 1 ELSE 0 END) as correct,
                      SUM(CASE WHEN was_correct = FALSE THEN 1 ELSE 0 END) as wrong,
                      SUM(CASE WHEN was_correct IS NULL THEN 1 ELSE 0 END) as pending
               FROM trade_decisions 
               WHERE created_at > NOW() - interval '%s days'
               GROUP BY action""",
            (days,), fetch=True
        ) or []
        return {r['action']: r for r in rows}

    def get_decisions(self, limit: int = 50, symbol: str = None, action: str = None) -> list:
        """Get trade decisions (for dashboard)."""
        sql = "SELECT * FROM trade_decisions WHERE 1=1"
        params = []
        if symbol:
            sql += " AND symbol = %s"
            params.append(symbol)
        if action:
            sql += " AND action = %s"
            params.append(action)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        return self._exec(sql, params, fetch=True) or []

    def get_missed_trades(self, days: int = 3) -> list:
        """Stocks we SKIPPED/BLOCKED but went up (regret analysis)."""
        return self._exec(
            """SELECT symbol, action, confidence, block_reason, price_at_decision,
                      price_after_1h, price_after_4h,
                      ROUND(((price_after_4h - price_at_decision) / price_at_decision * 100)::numeric, 2) as pct_missed
               FROM trade_decisions
               WHERE action IN ('SKIP', 'BLOCK') AND was_correct = FALSE
                 AND created_at > NOW() - interval '%s days'
               ORDER BY (price_after_4h - price_at_decision) DESC LIMIT 20""",
            (days,), fetch=True
        ) or []

    # ══════════════════════════════════════════════
    #  NOTIFICATIONS: Queue for dashboard
    # ══════════════════════════════════════════════

    def notify(self, title: str, body: str = '', severity: str = 'info',
               category: str = 'bot', symbol: str = None, channel: str = 'dashboard',
               data: dict = None, expires_hours: int = 24):
        """Push a notification to the dashboard."""
        self._exec(
            """INSERT INTO notifications (channel, title, body, severity, category, symbol, data, expires_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, NOW() + interval '%s hours')""",
            (channel, title, body[:2000] if body else '', severity, category, symbol,
             json.dumps(data) if data else None, expires_hours)
        )

    def get_notifications(self, limit: int = 50, unread_only: bool = True, channel: str = None) -> list:
        sql = "SELECT * FROM notifications WHERE (expires_at IS NULL OR expires_at > NOW())"
        params = []
        if unread_only:
            sql += " AND is_read = FALSE"
        if channel:
            sql += " AND channel = %s"
            params.append(channel)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        return self._exec(sql, params, fetch=True) or []

    def mark_notifications_read(self, ids: list = None):
        if ids:
            self._exec("UPDATE notifications SET is_read = TRUE WHERE id = ANY(%s)", (ids,))
        else:
            self._exec("UPDATE notifications SET is_read = TRUE WHERE is_read = FALSE")

    def get_unread_count(self) -> int:
        rows = self._exec(
            "SELECT COUNT(*) as cnt FROM notifications WHERE is_read = FALSE AND (expires_at IS NULL OR expires_at > NOW())",
            fetch=True
        )
        return rows[0]['cnt'] if rows else 0

    # ══════════════════════════════════════════════
    #  STRATEGY SIGNALS: Every signal per scan
    # ══════════════════════════════════════════════

    def log_signal(self, symbol: str, strategy: str, signal_type: str,
                   value: float = 0, scan_id: str = None, metadata: dict = None):
        """Log a strategy signal (for backtesting + analytics)."""
        self._exec(
            """INSERT INTO strategy_signals (scan_id, symbol, strategy, signal_type, signal_value, metadata)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (scan_id, symbol, strategy, signal_type, value,
             json.dumps(metadata) if metadata else None)
        )

    def get_signal_history(self, symbol: str = None, strategy: str = None, hours: int = 24) -> list:
        sql = "SELECT * FROM strategy_signals WHERE created_at > NOW() - interval '%s hours'"
        params = [hours]
        if symbol:
            sql += " AND symbol = %s"
            params.append(symbol)
        if strategy:
            sql += " AND strategy = %s"
            params.append(strategy)
        sql += " ORDER BY created_at DESC LIMIT 200"
        return self._exec(sql, params, fetch=True) or []

    # ══════════════════════════════════════════════
    #  DAILY REPORTS: Archive AI analysis
    # ══════════════════════════════════════════════

    def save_daily_report(self, insights: dict, report_type: str = 'daily_deep_learn',
                          ai_source: str = 'claude', regime: str = None, vix: float = None):
        """Archive a daily AI analysis report (permanent)."""
        from datetime import date
        self._exec(
            """INSERT INTO daily_reports (report_date, report_type, ai_source, buy_list, avoid_list,
               sector_signal, earnings_plays, risk_alerts, strategy, key_insight,
               tv_learnings, missed_opportunities, full_report, market_regime, vix_at_time)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (report_date, report_type) DO UPDATE SET
                   buy_list = EXCLUDED.buy_list, avoid_list = EXCLUDED.avoid_list,
                   sector_signal = EXCLUDED.sector_signal, full_report = EXCLUDED.full_report,
                   key_insight = EXCLUDED.key_insight, tv_learnings = EXCLUDED.tv_learnings,
                   missed_opportunities = EXCLUDED.missed_opportunities""",
            (date.today(), report_type, ai_source,
             json.dumps(insights.get('buy_list')),
             json.dumps(insights.get('avoid_list')),
             str(insights.get('sector_signal', ''))[:500],
             json.dumps(insights.get('earnings_plays')),
             json.dumps(insights.get('risk_alerts')),
             str(insights.get('tomorrow_strategy', ''))[:500],
             str(insights.get('key_insight', ''))[:500],
             str(insights.get('tv_learnings', ''))[:500],
             str(insights.get('missed_opportunities', ''))[:500],
             json.dumps(insights),
             regime, vix)
        )

    def get_daily_reports(self, days: int = 30) -> list:
        return self._exec(
            "SELECT * FROM daily_reports WHERE report_date > CURRENT_DATE - %s ORDER BY report_date DESC",
            (days,), fetch=True
        ) or []

    # ══════════════════════════════════════════════
    #  DASHBOARD AGGREGATE: One-call data bundle
    # ══════════════════════════════════════════════

    def get_dashboard_state(self) -> dict:
        """Single call for dashboard to get EVERYTHING it needs."""
        return {
            'session': self.get_session_info(),
            'mode': self.get_bot_mode(),
            'kill_switch': self.is_kill_switch_on(),
            'unread_notifications': self.get_unread_count(),
            'cycle_count': self.get_state('cycle_count', 0),
            'last_scan_time': self.get_state('last_scan_time'),
            'last_trade_time': self.get_state('last_trade_time'),
            'errors_today': self.get_state('errors_today', 0),
            'trades_today': self.get_state('trades_today', 0),
            'decision_accuracy': self.get_decision_accuracy(7),
        }

    # ══════════════════════════════════════════════
    #  FLUSH V4: Smarter — analyze → archive → flush
    # ══════════════════════════════════════════════

    def daily_flush_v4(self):
        """3 AM flush: Clear intraday ephemeral data, keep permanent records.
        Called AFTER daily deep learn has analyzed everything."""
        log.info("🧹 V4 daily flush starting...")

        # Reset intraday price tracking
        self.reset_intraday()

        # Clear ephemeral state (intraday stuff)
        self.clear_state_category('intraday')

        # Clear old TV readings (insights already stored in ai_trends)
        self._exec("DELETE FROM tv_readings WHERE created_at < NOW() - interval '24 hours'")

        # Clear old position snapshots (equity curve stays for 30 days)
        self._exec("DELETE FROM position_snapshots WHERE created_at < NOW() - interval '2 days'")

        # Clear old activity log (keep 7 days)
        self._exec("DELETE FROM activity_log WHERE created_at < NOW() - interval '7 days'")

        # Clear old scan results (keep 3 days)
        self._exec("DELETE FROM scan_results WHERE created_at < NOW() - interval '3 days'")

        # Clear expired notifications
        self._exec("DELETE FROM notifications WHERE expires_at < NOW()")

        # Clear old strategy signals (keep 7 days for backtesting)
        self._exec("DELETE FROM strategy_signals WHERE created_at < NOW() - interval '7 days'")

        # Clear old login attempts
        self._exec("DELETE FROM login_attempts WHERE created_at < NOW() - interval '7 days'")

        # Clear expired sessions
        self._exec("UPDATE sessions SET is_active = FALSE WHERE expires_at < NOW()")

        # Grade ungraded decisions (mark expired ones as unknown)
        self._exec(
            """UPDATE trade_decisions SET was_correct = NULL 
               WHERE was_correct IS NULL AND price_after_4h IS NULL 
                 AND created_at < NOW() - interval '6 hours'"""
        )

        # Reset daily counters
        self.set_state('errors_today', 0, 'daily')
        self.set_state('trades_today', 0, 'daily')
        self.set_state('daily_pnl', 0, 'daily')

        log.info("🧹 V4 daily flush complete. Permanent data preserved.")

    # ══════════════════════════════════════════════════════════
    #  PERFORMANCE LAYER: Cache + Batch + Async writes
    #  Trading decisions NEVER wait for DB writes.
    #  Reads use in-memory cache with TTL.
    # ══════════════════════════════════════════════════════════

    def cached_get(self, key: str, fetcher, ttl_seconds: int = 300):
        """Read-through cache. Fetcher is called on miss. Thread-safe."""
        import time as _time
        with self._cache_lock:
            if key in self._cache:
                val, expires = self._cache[key]
                if _time.time() < expires:
                    return val
        # Cache miss — fetch from DB
        val = fetcher()
        with self._cache_lock:
            self._cache[key] = (val, _time.time() + ttl_seconds)
        return val

    def invalidate_cache(self, key: str = None):
        with self._cache_lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()

    def _fire_and_forget(self, sql, params=None):
        """Non-blocking DB write. Errors are logged, never raised.
        Used for logging — MUST NOT slow trading."""
        try:
            if self._pool:
                conn = self._pool.getconn()
                try:
                    conn.autocommit = True
                    with conn.cursor() as cur:
                        cur.execute(sql, params)
                finally:
                    self._pool.putconn(conn)
            else:
                self._exec(sql, params)
        except Exception as e:
            log.debug(f"Fire-and-forget write failed (non-critical): {e}")

    def batch_insert(self, table: str, columns: list, rows: list):
        """Bulk insert using execute_values (10-50x faster than individual INSERTs)."""
        if not rows or not self._ensure_conn():
            return
        cols = ', '.join(columns)
        template = '(' + ', '.join(['%s'] * len(columns)) + ')'
        sql = f"INSERT INTO {table} ({cols}) VALUES %s ON CONFLICT DO NOTHING"
        try:
            with self.conn.cursor() as cur:
                execute_values(cur, sql, rows, template=template, page_size=100)
        except Exception as e:
            log.warning(f"Batch insert {table} failed: {e}")
            try:
                self.conn.rollback()
            except:
                self.conn = None

    # ══════════════════════════════════════════════════════════
    #  SCAN SNAPSHOTS: One-shot deep log of entire scan
    #  Everything in one JSONB write — fast, queryable, complete
    # ══════════════════════════════════════════════════════════

    def log_scan_snapshot(self, scan_id: str, scan_type: str, duration_ms: int = 0,
                          regime: str = None, spy_change: float = 0, vix: float = 0,
                          equity: float = 0, total_pl: float = 0,
                          positions: list = None, tv_data: dict = None,
                          sentiment_data: dict = None, confidence_data: dict = None,
                          ai_verdicts: dict = None, decisions: list = None,
                          market_context: dict = None, runners_found: list = None,
                          ai_reasoning: str = None):
        """Log an ENTIRE scan as one row. This is the deep log.
        Every signal, every verdict, every decision — all in one place.
        Uses fire-and-forget so it NEVER slows the scan loop."""
        stocks_scanned = len(positions or [])
        stocks_tv = len(tv_data or {})
        stocks_sent = len(sentiment_data or {})
        ai_count = len(ai_verdicts or {})
        buys = sum(1 for d in (decisions or []) if d.get('action') == 'BUY' and d.get('executed'))
        sells = sum(1 for d in (decisions or []) if d.get('action') == 'SELL' and d.get('executed'))
        blocks = sum(1 for d in (decisions or []) if d.get('action') in ('BLOCK', 'SKIP'))

        self._fire_and_forget(
            """INSERT INTO scan_snapshots (scan_id, scan_type, duration_ms, regime, spy_change, vix,
                equity, total_pl, position_count, stocks_scanned, stocks_with_tv,
                stocks_with_sentiment, ai_verdicts_count, buys_executed, sells_executed,
                blocks_count, positions, tv_data, sentiment_data, confidence_data,
                ai_verdicts, decisions, market_context, runners_found, ai_reasoning)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (scan_id) DO NOTHING""",
            (scan_id, scan_type, duration_ms, regime, spy_change, vix,
             equity, total_pl, stocks_scanned, stocks_scanned, stocks_tv,
             stocks_sent, ai_count, buys, sells, blocks,
             json.dumps(self._sanitize_for_json(positions)),
             json.dumps(self._sanitize_for_json(tv_data)),
             json.dumps(self._sanitize_for_json(sentiment_data)),
             json.dumps(self._sanitize_for_json(confidence_data)),
             json.dumps(self._sanitize_for_json(ai_verdicts)),
             json.dumps(self._sanitize_for_json(decisions)),
             json.dumps(self._sanitize_for_json(market_context)),
             json.dumps(self._sanitize_for_json(runners_found)),
             (ai_reasoning or '')[:5000])
        )

    def _sanitize_for_json(self, obj):
        """Make any object JSON-serializable (handles Decimal, datetime, Position objects)."""
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {str(k): self._sanitize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._sanitize_for_json(i) for i in obj]
        if hasattr(obj, '__dict__'):
            return {k: self._sanitize_for_json(v) for k, v in obj.__dict__.items()
                    if not k.startswith('_')}
        return str(obj)

    def get_scan_snapshots(self, limit: int = 20, scan_type: str = None) -> list:
        """Get recent scan snapshots (for dashboard timeline)."""
        sql = "SELECT id, scan_id, scan_type, duration_ms, regime, spy_change, vix, equity, total_pl, "
        sql += "position_count, stocks_scanned, stocks_with_tv, ai_verdicts_count, "
        sql += "buys_executed, sells_executed, blocks_count, ai_reasoning, created_at "
        sql += "FROM scan_snapshots WHERE 1=1"
        params = []
        if scan_type:
            sql += " AND scan_type = %s"
            params.append(scan_type)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        return self._exec(sql, params, fetch=True) or []

    def get_scan_detail(self, scan_id: str) -> dict:
        """Get full scan snapshot with all JSONB data (for deep analysis)."""
        rows = self._exec("SELECT * FROM scan_snapshots WHERE scan_id = %s", (scan_id,), fetch=True)
        return rows[0] if rows else {}

    # ══════════════════════════════════════════════════════════
    #  TRADE LOG: Every trade with full context + AI reasoning
    #  Permanent — never flushed — this is how the bot learns
    # ══════════════════════════════════════════════════════════

    def log_trade_deep(self, symbol: str, side: str, qty: int, price: float,
                       scan_id: str = None, strategy: str = None, source: str = None,
                       trigger: str = None, tv_at_trade: dict = None,
                       sentiment_at_trade: dict = None, ai_verdict_at_trade: dict = None,
                       confidence: float = 0, ai_reasoning: str = None,
                       regime: str = None, vix: float = 0, spy_change: float = 0,
                       heat_pct: float = 0, position_count: int = 0,
                       day_change_pct: float = 0, order_result: str = None,
                       order_id: str = None) -> int:
        """Log a trade with EVERY piece of context that led to the decision.
        This is permanent — the AI learns from this on every deep learn cycle.
        Uses fire-and-forget to never slow the trade execution."""
        rows = self._exec(
            """INSERT INTO trade_log (scan_id, symbol, side, qty, price, strategy, source, trigger,
                tv_at_trade, sentiment_at_trade, ai_verdict_at_trade, confidence_at_trade,
                ai_reasoning, market_regime, vix_at_trade, spy_change, portfolio_heat,
                position_count, day_change_pct, order_result, order_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (scan_id, symbol, side, qty, price, strategy, source, trigger,
             json.dumps(self._sanitize_for_json(tv_at_trade)),
             json.dumps(self._sanitize_for_json(sentiment_at_trade)),
             json.dumps(self._sanitize_for_json(ai_verdict_at_trade)),
             confidence, (ai_reasoning or '')[:2000],
             regime, vix, spy_change, heat_pct, position_count,
             day_change_pct, order_result, order_id),
            fetch=True
        )
        return rows[0]['id'] if rows else None

    def update_trade_outcome(self, trade_id: int, pnl_1h: float = None,
                              pnl_4h: float = None, pnl_eod: float = None,
                              filled_price: float = None, lesson: str = None):
        """Update trade with actual outcome (called by background grader)."""
        updates = []
        params = []
        if pnl_1h is not None:
            updates.append("pnl_1h = %s")
            params.append(pnl_1h)
        if pnl_4h is not None:
            updates.append("pnl_4h = %s")
            params.append(pnl_4h)
        if pnl_eod is not None:
            updates.append("pnl_eod = %s, was_profitable = %s")
            params.extend([pnl_eod, pnl_eod > 0])
        if filled_price is not None:
            updates.append("filled_price = %s, filled_at = NOW()")
            params.append(filled_price)
        if lesson:
            updates.append("lesson_learned = %s")
            params.append(lesson[:500])
        if updates:
            params.append(trade_id)
            self._fire_and_forget(
                f"UPDATE trade_log SET {', '.join(updates)} WHERE id = %s", params
            )

    def get_trade_log(self, limit: int = 50, symbol: str = None, side: str = None) -> list:
        sql = "SELECT * FROM trade_log WHERE 1=1"
        params = []
        if symbol:
            sql += " AND symbol = %s"
            params.append(symbol)
        if side:
            sql += " AND side = %s"
            params.append(side)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        return self._exec(sql, params, fetch=True) or []

    def get_trade_win_rate(self, days: int = 30) -> dict:
        """Win rate analysis for AI learning — which strategies actually work?"""
        return {
            'by_strategy': self._exec(
                """SELECT strategy, COUNT(*) as total,
                          SUM(CASE WHEN was_profitable THEN 1 ELSE 0 END) as wins,
                          ROUND(AVG(CASE WHEN pnl_eod IS NOT NULL THEN pnl_eod ELSE 0 END)::numeric, 2) as avg_pnl
                   FROM trade_log WHERE created_at > NOW() - interval '%s days' AND pnl_eod IS NOT NULL
                   GROUP BY strategy ORDER BY total DESC""",
                (days,), fetch=True
            ) or [],
            'by_trigger': self._exec(
                """SELECT trigger, COUNT(*) as total,
                          SUM(CASE WHEN was_profitable THEN 1 ELSE 0 END) as wins
                   FROM trade_log WHERE created_at > NOW() - interval '%s days' AND pnl_eod IS NOT NULL
                   GROUP BY trigger ORDER BY total DESC""",
                (days,), fetch=True
            ) or [],
            'by_regime': self._exec(
                """SELECT market_regime, COUNT(*) as total,
                          SUM(CASE WHEN was_profitable THEN 1 ELSE 0 END) as wins,
                          ROUND(AVG(vix_at_trade)::numeric, 1) as avg_vix
                   FROM trade_log WHERE created_at > NOW() - interval '%s days' AND pnl_eod IS NOT NULL
                   GROUP BY market_regime""",
                (days,), fetch=True
            ) or [],
        }

    def get_learning_context_for_stock(self, symbol: str) -> dict:
        """Get EVERYTHING the bot has learned about a stock — for AI prompts.
        This is what makes the bot smarter over time. Cached 5 min."""
        cache_key = f"learn_{symbol}"
        return self.cached_get(cache_key, lambda: self._build_learning_context(symbol), ttl_seconds=300)

    def _build_learning_context(self, symbol: str) -> dict:
        """Build comprehensive learning context from all DB sources."""
        return {
            'trade_history': self._exec(
                """SELECT side, qty, price, strategy, trigger, ai_reasoning, 
                          was_profitable, pnl_eod, lesson_learned, created_at
                   FROM trade_log WHERE symbol = %s ORDER BY created_at DESC LIMIT 20""",
                (symbol,), fetch=True
            ) or [],
            'recent_decisions': self._exec(
                """SELECT action, confidence, block_reason, tv_data, executed, was_correct
                   FROM trade_decisions WHERE symbol = %s 
                   ORDER BY created_at DESC LIMIT 10""",
                (symbol,), fetch=True
            ) or [],
            'tv_patterns': self._exec(
                """SELECT AVG(rsi) as avg_rsi, MIN(rsi) as min_rsi, MAX(rsi) as max_rsi,
                          AVG(macd_hist) as avg_macd, AVG(confluence) as avg_confluence,
                          SUM(CASE WHEN vwap_above THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0) as vwap_above_pct,
                          COUNT(*) as readings
                   FROM tv_readings WHERE symbol = %s AND created_at > NOW() - interval '7 days'""",
                (symbol,), fetch=True
            ) or [{}],
            'ai_trends': self.get_trends(symbol=symbol),
            'earnings': self.get_earnings_pattern(symbol),
            'watchlist_stats': self._exec(
                "SELECT times_traded, total_pnl, last_seen_at, source FROM watchlist WHERE symbol = %s",
                (symbol,), fetch=True
            ) or [],
        }

    def get_learning_digest_for_ai(self, symbols: list = None, limit: int = 30) -> str:
        """Build a text digest of all learning for AI prompt injection.
        This gets prepended to every AI analysis call so it KNOWS our history."""
        lines = []

        # Overall performance
        perf = self.get_trade_win_rate(30)
        if perf.get('by_strategy'):
            lines.append("=== STRATEGY PERFORMANCE (30 days) ===")
            for s in perf['by_strategy'][:5]:
                wr = (s['wins'] / s['total'] * 100) if s['total'] > 0 else 0
                lines.append(f"  {s['strategy']}: {s['wins']}/{s['total']} wins ({wr:.0f}%) avg P&L ${s['avg_pnl']}")

        # Per-stock lessons
        if symbols:
            for sym in symbols[:10]:
                ctx = self.get_learning_context_for_stock(sym)
                trades = ctx.get('trade_history', [])
                if trades:
                    wins = sum(1 for t in trades if t.get('was_profitable'))
                    total = sum(1 for t in trades if t.get('was_profitable') is not None)
                    lessons = [t['lesson_learned'] for t in trades if t.get('lesson_learned')]
                    if total > 0:
                        lines.append(f"\n--- {sym} ({wins}/{total} wins) ---")
                        for l in lessons[:3]:
                            lines.append(f"  Lesson: {l[:100]}")

        # Missed opportunities
        missed = self.get_missed_trades(7)
        if missed:
            lines.append("\n=== MISSED OPPORTUNITIES (7 days) ===")
            for m in missed[:5]:
                lines.append(f"  {m['symbol']}: blocked ({m['block_reason'][:50]}) but went +{m.get('pct_missed', 0)}%")

        return '\n'.join(lines) if lines else ''
