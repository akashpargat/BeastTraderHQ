"""
Beast Trader V4 — PostgreSQL Database Layer
============================================
Replaces SQLite trade_db.py as the primary database.
trade_db.py remains as local fallback.

Alpaca is source of truth for positions/orders.
This DB is cache + event log + analytics.
"""

import os
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
import logging

log = logging.getLogger('Beast.DB')

DB_URL = os.getenv('DATABASE_URL', '')
# Format: postgresql://beastadmin:B3astDB2026!@beast-trading-db.postgres.database.azure.com:5432/beast


class BeastDB:
    """PostgreSQL database for Beast Trader V4.
    Alpaca is source of truth for positions/orders.
    This DB is cache + event log + analytics."""

    def __init__(self):
        self.conn = None
        self._connect()
        self._create_tables()

    # ══════════════════════════════════════════════
    #  Connection
    # ══════════════════════════════════════════════

    def _connect(self):
        """Connect to PostgreSQL. Falls back gracefully."""
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
        """Ensure connection is alive; reconnect if needed."""
        if self.conn is None:
            self._connect()
            return self.conn is not None
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            log.warning("PostgreSQL connection lost — reconnecting")
            self._connect()
            return self.conn is not None

    def _execute(self, sql, params=None, fetch=False):
        """Safe execute wrapper. Returns rows if fetch=True, else None."""
        if not self._ensure_conn():
            return [] if fetch else None
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, params)
                if fetch:
                    return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            log.warning(f"DB execute error: {e}")
            # Try to reset connection on operational errors
            try:
                self.conn.rollback()
            except Exception:
                self.conn = None
            return [] if fetch else None

    # ══════════════════════════════════════════════
    #  Schema
    # ══════════════════════════════════════════════

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS activity_log (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMPTZ DEFAULT NOW(),
        action_type TEXT NOT NULL,
        symbol TEXT,
        side TEXT,
        qty INTEGER,
        price DECIMAL(12,2),
        reason TEXT,
        strategy TEXT,
        source TEXT,
        confidence INTEGER,
        ai_source TEXT,
        data JSONB,
        order_id TEXT,
        client_order_id TEXT
    );

    CREATE TABLE IF NOT EXISTS ai_verdicts (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMPTZ DEFAULT NOW(),
        symbol TEXT NOT NULL,
        action TEXT,
        confidence INTEGER,
        reasoning TEXT,
        ai_source TEXT,
        scan_type TEXT,
        data JSONB
    );
    CREATE INDEX IF NOT EXISTS idx_ai_verdicts_symbol
        ON ai_verdicts(symbol, timestamp DESC);

    CREATE TABLE IF NOT EXISTS position_snapshots (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMPTZ DEFAULT NOW(),
        symbol TEXT NOT NULL,
        qty INTEGER,
        avg_entry DECIMAL(12,2),
        current_price DECIMAL(12,2),
        unrealized_pl DECIMAL(12,2),
        pct_change DECIMAL(8,2),
        has_trailing_stop BOOLEAN DEFAULT FALSE,
        market_value DECIMAL(12,2)
    );
    CREATE INDEX IF NOT EXISTS idx_pos_snap_ts
        ON position_snapshots(timestamp DESC);

    CREATE TABLE IF NOT EXISTS equity_snapshots (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMPTZ DEFAULT NOW(),
        equity DECIMAL(12,2),
        cash DECIMAL(12,2),
        total_pl DECIMAL(12,2),
        position_count INTEGER,
        heat_pct DECIMAL(5,2)
    );

    CREATE TABLE IF NOT EXISTS scan_results (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMPTZ DEFAULT NOW(),
        scan_type TEXT,
        regime TEXT,
        spy_change DECIMAL(8,4),
        tv_count INTEGER,
        sentiment_count INTEGER,
        ai_count INTEGER,
        trump_score INTEGER,
        data JSONB
    );

    CREATE TABLE IF NOT EXISTS commands (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMPTZ DEFAULT NOW(),
        command TEXT NOT NULL,
        parsed JSONB,
        status TEXT DEFAULT 'pending',
        result JSONB,
        executed_at TIMESTAMPTZ
    );
    """

    def _create_tables(self):
        """Auto-create all tables if they don't exist."""
        if not self._ensure_conn():
            return
        try:
            with self.conn.cursor() as cur:
                cur.execute(self._SCHEMA)
            log.info("✅ PostgreSQL tables verified")
        except Exception as e:
            log.error(f"Table creation failed: {e}")

    # ══════════════════════════════════════════════
    #  Activity Log
    # ══════════════════════════════════════════════

    def log_activity(self, action_type, symbol=None, side=None, qty=None,
                     price=None, reason=None, strategy=None, source=None,
                     confidence=None, ai_source=None, data=None,
                     order_id=None, client_order_id=None):
        """Log ANY bot action. This is the master audit trail."""
        self._execute(
            """INSERT INTO activity_log
               (action_type, symbol, side, qty, price, reason, strategy,
                source, confidence, ai_source, data, order_id, client_order_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (action_type, symbol, side, qty, price, reason, strategy,
             source, confidence, ai_source,
             json.dumps(data) if data else None,
             order_id, client_order_id)
        )

    def get_activity(self, limit=50, action_type=None, symbol=None):
        """Get recent activity, optionally filtered."""
        clauses, params = [], []
        if action_type:
            clauses.append("action_type = %s")
            params.append(action_type)
        if symbol:
            clauses.append("symbol = %s")
            params.append(symbol)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        return self._execute(
            f"SELECT * FROM activity_log {where} ORDER BY timestamp DESC LIMIT %s",
            params, fetch=True
        )

    # ══════════════════════════════════════════════
    #  AI Verdicts
    # ══════════════════════════════════════════════

    def save_ai_verdict(self, symbol, action, confidence, reasoning,
                        ai_source, scan_type, data=None):
        """Save AI analysis result."""
        self._execute(
            """INSERT INTO ai_verdicts
               (symbol, action, confidence, reasoning, ai_source, scan_type, data)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (symbol, action, confidence, reasoning, ai_source, scan_type,
             json.dumps(data) if data else None)
        )

    def get_latest_verdict(self, symbol):
        """Get most recent AI verdict for a symbol."""
        rows = self._execute(
            """SELECT * FROM ai_verdicts
               WHERE symbol = %s ORDER BY timestamp DESC LIMIT 1""",
            (symbol,), fetch=True
        )
        return rows[0] if rows else None

    def get_all_verdicts(self):
        """Get latest verdict per symbol."""
        return self._execute(
            """SELECT DISTINCT ON (symbol) *
               FROM ai_verdicts ORDER BY symbol, timestamp DESC""",
            fetch=True
        )

    # ══════════════════════════════════════════════
    #  Position Snapshots
    # ══════════════════════════════════════════════

    def snapshot_positions(self, positions, trailing_stops=None):
        """Save current position state. Called every 60s.
        positions: list of Position objects OR dicts
        trailing_stops: set of symbols with active trailing stops
        """
        if not positions:
            return
        trailing_stops = trailing_stops or set()
        for p in positions:
            # Handle both Position objects and dicts
            if hasattr(p, 'symbol'):
                sym = p.symbol
                qty = p.qty
                entry = float(p.avg_entry) if p.avg_entry else 0
                price = float(p.current_price) if p.current_price else 0
                pl = float(p.unrealized_pl) if p.unrealized_pl else 0
                mv = float(p.market_value) if hasattr(p, 'market_value') and p.market_value else price * qty
                pct = (pl / (entry * qty) * 100) if entry and qty else 0
            else:
                sym = p.get('symbol', '')
                qty = p.get('qty', 0)
                entry = float(p.get('avg_entry', 0))
                price = float(p.get('current_price', 0))
                pl = float(p.get('unrealized_pl', 0))
                mv = float(p.get('market_value', 0))
                pct = float(p.get('pct_change', 0))
            has_ts = sym in trailing_stops
            self._execute(
                """INSERT INTO position_snapshots
                   (symbol, qty, avg_entry, current_price, unrealized_pl,
                    pct_change, has_trailing_stop, market_value)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (sym, qty, entry, price, pl, round(pct, 2), has_ts, mv)
            )

    def get_position_history(self, symbol, hours=24):
        """Get position P&L history for a symbol."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return self._execute(
            """SELECT * FROM position_snapshots
               WHERE symbol = %s AND timestamp >= %s
               ORDER BY timestamp""",
            (symbol, cutoff), fetch=True
        )

    # ══════════════════════════════════════════════
    #  Equity Snapshots
    # ══════════════════════════════════════════════

    def snapshot_equity(self, equity, cash, total_pl, position_count, heat_pct):
        """Save account state. Called every 60s."""
        self._execute(
            """INSERT INTO equity_snapshots
               (equity, cash, total_pl, position_count, heat_pct)
               VALUES (%s,%s,%s,%s,%s)""",
            (float(equity or 0), float(cash or 0), float(total_pl or 0),
             int(position_count or 0), round(float(heat_pct or 0), 2))
        )

    def get_equity_curve(self, days=30):
        """Get equity history for chart."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return self._execute(
            """SELECT * FROM equity_snapshots
               WHERE timestamp >= %s ORDER BY timestamp""",
            (cutoff,), fetch=True
        )

    # ══════════════════════════════════════════════
    #  Scan Results
    # ══════════════════════════════════════════════

    def log_scan(self, scan_type, regime=None, spy_change=0, tv_count=0,
                 sentiment_count=0, ai_count=0, trump_score=0, data=None):
        """Log scan results."""
        self._execute(
            """INSERT INTO scan_results
               (scan_type, regime, spy_change, tv_count, sentiment_count,
                ai_count, trump_score, data)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (scan_type, regime, spy_change, tv_count, sentiment_count,
             ai_count, trump_score, json.dumps(data) if data else None)
        )

    def get_recent_scans(self, limit=20):
        """Get recent scan results."""
        return self._execute(
            "SELECT * FROM scan_results ORDER BY timestamp DESC LIMIT %s",
            (limit,), fetch=True
        )

    # ══════════════════════════════════════════════
    #  Commands
    # ══════════════════════════════════════════════

    def save_command(self, command, parsed=None):
        """Save a user command. Returns command ID."""
        rows = self._execute(
            """INSERT INTO commands (command, parsed)
               VALUES (%s, %s) RETURNING id""",
            (command, json.dumps(parsed) if parsed else None),
            fetch=True
        )
        return rows[0]['id'] if rows else None

    def update_command(self, cmd_id, status, result=None):
        """Update command status after execution."""
        self._execute(
            """UPDATE commands SET status = %s, result = %s,
               executed_at = NOW() WHERE id = %s""",
            (status, json.dumps(result) if result else None, cmd_id)
        )

    def get_commands(self, limit=20, status=None):
        """Get recent commands."""
        if status:
            return self._execute(
                """SELECT * FROM commands WHERE status = %s
                   ORDER BY timestamp DESC LIMIT %s""",
                (status, limit), fetch=True
            )
        return self._execute(
            "SELECT * FROM commands ORDER BY timestamp DESC LIMIT %s",
            (limit,), fetch=True
        )

    # ══════════════════════════════════════════════
    #  Command Parser
    # ══════════════════════════════════════════════

    def parse_command(self, raw: str) -> dict:
        """Parse structured commands like:
        /buy NVDA 3 @210
        /sell AMD 5
        /cancel ORDER_ID
        /status
        /kill        — disable all trading
        /resume      — re-enable trading
        Returns: {'action': str, 'symbol': str, 'qty': int,
                  'price': float, 'raw': str}
        """
        raw = raw.strip()
        result = {'action': None, 'symbol': None, 'qty': None,
                  'price': None, 'raw': raw}

        if not raw.startswith('/'):
            return result

        parts = raw.split()
        action = parts[0].lstrip('/').lower()
        result['action'] = action

        # Simple commands with no arguments
        if action in ('status', 'kill', 'resume'):
            return result

        # /cancel ORDER_ID
        if action == 'cancel' and len(parts) >= 2:
            result['symbol'] = parts[1]  # reuse symbol field for order id
            return result

        # /buy SYMBOL QTY [@PRICE]  or  /sell SYMBOL QTY [@PRICE]
        if action in ('buy', 'sell') and len(parts) >= 2:
            result['symbol'] = parts[1].upper()
            if len(parts) >= 3:
                try:
                    result['qty'] = int(parts[2])
                except ValueError:
                    pass
            # Look for @price anywhere in remaining tokens
            price_match = re.search(r'@(\d+\.?\d*)', raw)
            if price_match:
                result['price'] = float(price_match.group(1))

        return result

    # ══════════════════════════════════════════════
    #  Analytics
    # ══════════════════════════════════════════════

    def get_analytics(self):
        """Calculate trading analytics from activity_log.
        Returns: total_trades, win_rate, total_pnl, best_trade,
        worst_trade, avg_hold_time, strategy_breakdown."""
        default = {
            'total_trades': 0, 'wins': 0, 'losses': 0,
            'win_rate': 0.0, 'total_pnl': 0.0,
            'best_trade': 0.0, 'worst_trade': 0.0,
            'avg_hold_time': 'N/A', 'strategy_breakdown': {}
        }

        # Count all trade executions
        trades = self._execute(
            """SELECT action_type, symbol, side, price, qty, strategy, data
               FROM activity_log
               WHERE action_type IN ('BUY','SELL')
               ORDER BY timestamp""",
            fetch=True
        )
        if not trades:
            return default

        total = len(trades)
        pnl_values = []
        strat_map = {}

        for t in trades:
            d = t.get('data') or {}
            pnl = float(d.get('pnl', 0) or 0)
            pnl_values.append(pnl)
            strat = t.get('strategy') or 'unknown'
            if strat not in strat_map:
                strat_map[strat] = {'trades': 0, 'pnl': 0.0}
            strat_map[strat]['trades'] += 1
            strat_map[strat]['pnl'] += pnl

        wins = sum(1 for p in pnl_values if p > 0)
        losses = sum(1 for p in pnl_values if p < 0)
        total_pnl = sum(pnl_values)
        best = max(pnl_values) if pnl_values else 0
        worst = min(pnl_values) if pnl_values else 0
        sell_count = wins + losses

        return {
            'total_trades': total,
            'wins': wins,
            'losses': losses,
            'win_rate': round(wins / sell_count * 100, 1) if sell_count else 0.0,
            'total_pnl': round(total_pnl, 2),
            'best_trade': round(best, 2),
            'worst_trade': round(worst, 2),
            'avg_hold_time': 'N/A',
            'strategy_breakdown': strat_map
        }

    def get_strategy_stats(self):
        """P&L breakdown by strategy (scalp vs runner vs dip vs claude)."""
        rows = self._execute(
            """SELECT strategy,
                      COUNT(*) as trades,
                      COUNT(CASE WHEN action_type = 'BUY' THEN 1 END) as buys,
                      COUNT(CASE WHEN action_type = 'SELL' THEN 1 END) as sells
               FROM activity_log
               WHERE action_type IN ('BUY','SELL')
               GROUP BY strategy ORDER BY trades DESC""",
            fetch=True
        )
        return rows or []

    # ══════════════════════════════════════════════
    #  Cleanup
    # ══════════════════════════════════════════════

    def cleanup_old_data(self, days=15):
        """Purge ALL snapshot data older than 15 days. Keeps DB lean.
        Activity log and AI verdicts kept for 30 days (audit trail)."""
        cutoff_15 = datetime.now(timezone.utc) - timedelta(days=15)
        cutoff_30 = datetime.now(timezone.utc) - timedelta(days=30)

        # 15-day purge: high-frequency data
        tables_15 = ['position_snapshots', 'equity_snapshots', 'scan_results']
        for t in tables_15:
            self._execute(f"DELETE FROM {t} WHERE timestamp < %s", (cutoff_15,))

        # 30-day purge: audit trail
        tables_30 = ['activity_log', 'ai_verdicts', 'commands']
        for t in tables_30:
            self._execute(f"DELETE FROM {t} WHERE timestamp < %s", (cutoff_30,))

        log.info(f"🧹 Purged: snapshots/scans >15d, activity/verdicts/commands >30d")

    def auto_purge(self):
        """Call this once per day to keep DB clean. Safe to call anytime."""
        try:
            # Check last purge time
            rows = self._execute(
                "SELECT MAX(timestamp) as last FROM activity_log WHERE action_type = 'PURGE'",
                fetch=True
            )
            last = rows[0].get('last') if rows and rows[0].get('last') else None
            if last and (datetime.now(timezone.utc) - last).total_seconds() < 86400:
                return  # Already purged today

            self.cleanup_old_data()
            self.log_activity('PURGE', reason='Auto-purge: 15d snapshots, 30d audit', source='system')
        except Exception as e:
            log.debug(f"Auto-purge: {e}")

    # ══════════════════════════════════════════════
    #  Lifecycle
    # ══════════════════════════════════════════════

    def close(self):
        """Close the database connection."""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
