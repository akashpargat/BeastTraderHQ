"""
Beast Terminal V4 — PostgreSQL Database Layer (Schema V3)
=========================================================
13 tables, 4 views, 44 indexes, 7 FKs, 82 constraints.

Tables:
  AUTH:     users, sessions, login_attempts
  TRADING:  orders, ai_verdicts
  MARKET:   tv_readings, sentiment_readings
  STATE:    equity_snapshots, position_snapshots
  ACTIVITY: activity_log, alerts, scan_results, commands

Views:
  v_latest_verdicts    — most recent AI verdict per symbol
  v_daily_pnl          — daily equity OHLC
  v_strategy_performance — P&L by strategy
  v_activity_summary   — daily activity counts

Design: Alpaca = source of truth. This DB = event log + analytics + audit.
Every method handles errors gracefully — bot NEVER crashes from DB issues.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
import logging
import hashlib

log = logging.getLogger('Beast.DB')

DB_URL = os.getenv('DATABASE_URL', '')


class BeastDB:
    def __init__(self):
        self.conn = None
        self._connect()

    def _connect(self):
        if not DB_URL:
            log.warning("DATABASE_URL not set — PostgreSQL disabled")
            return
        try:
            self.conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
            self.conn.autocommit = True
            log.info("✅ Connected to PostgreSQL")
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
