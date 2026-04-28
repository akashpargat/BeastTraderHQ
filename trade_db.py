"""
Beast v2.0 — Trade Database (SQLite)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Foundation for ALL analytics. Every trade, every P&L, every grade.
Stores: trades, daily_summaries, strategy_performance, positions_history.
"""
import sqlite3
import os
import logging
from datetime import datetime, date
from typing import Optional

log = logging.getLogger('Beast.TradeDB')

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'beast_trades.db')


class TradeDB:
    """SQLite database for trade history and analytics."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        log.info(f"📁 Trade DB initialized: {db_path}")

    def _create_tables(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,           -- buy/sell
            qty INTEGER NOT NULL,
            price REAL NOT NULL,
            total_value REAL NOT NULL,
            strategy TEXT DEFAULT '',     -- A-K strategy name
            confidence REAL DEFAULT 0,    -- 0-100 confidence at entry
            regime TEXT DEFAULT '',       -- BULL/BEAR/CHOPPY/RED_ALERT
            position_type TEXT DEFAULT '',-- SWING/SPLIT/SCALP
            reason TEXT DEFAULT '',       -- why this trade
            
            -- Exit info (filled when position closes)
            exit_price REAL DEFAULT 0,
            exit_time TEXT DEFAULT '',
            pnl REAL DEFAULT 0,
            pnl_pct REAL DEFAULT 0,
            hold_time_seconds INTEGER DEFAULT 0,
            
            -- Grading
            grade TEXT DEFAULT '',        -- A/B/C/D/F
            ai_grade TEXT DEFAULT '',     -- AI-generated grade
            ai_reasoning TEXT DEFAULT '', -- AI explanation
            iron_law_violations TEXT DEFAULT '[]',
            
            -- Metadata
            order_id TEXT DEFAULT '',
            is_scalp INTEGER DEFAULT 0,   -- 1=scalp half, 0=runner half
            parent_trade_id INTEGER DEFAULT 0,  -- links scalp+runner
            
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS daily_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            trades_count INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            breakeven INTEGER DEFAULT 0,
            realized_pnl REAL DEFAULT 0,
            unrealized_pnl REAL DEFAULT 0,
            equity_start REAL DEFAULT 0,
            equity_end REAL DEFAULT 0,
            regime TEXT DEFAULT '',
            sentiment_score INTEGER DEFAULT 0,
            sentiment_action TEXT DEFAULT '',
            best_trade TEXT DEFAULT '',
            worst_trade TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS strategy_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy TEXT NOT NULL,
            regime TEXT NOT NULL,
            trades INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            total_pnl REAL DEFAULT 0,
            avg_pnl REAL DEFAULT 0,
            win_rate REAL DEFAULT 0,
            avg_win REAL DEFAULT 0,
            avg_loss REAL DEFAULT 0,
            profit_factor REAL DEFAULT 0,
            max_win REAL DEFAULT 0,
            max_loss REAL DEFAULT 0,
            avg_hold_seconds INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(strategy, regime)
        );

        CREATE TABLE IF NOT EXISTS position_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            qty INTEGER,
            avg_entry REAL,
            current_price REAL,
            unrealized_pnl REAL,
            unrealized_pnl_pct REAL
        );

        CREATE TABLE IF NOT EXISTS alerts_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            alert_type TEXT NOT NULL,   -- TRADE/DROP/EARNINGS/SECTOR/KILL_SWITCH/LAW_VIOLATION
            symbol TEXT DEFAULT '',
            message TEXT DEFAULT '',
            sent_telegram INTEGER DEFAULT 0,
            sent_discord INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
        CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
        CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(created_at);
        CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_summary(date);
        CREATE INDEX IF NOT EXISTS idx_snapshots_time ON position_snapshots(timestamp);
        """)
        self.conn.commit()

    # ── Trade CRUD ─────────────────────────────────────

    def log_entry(self, symbol: str, qty: int, price: float,
                  strategy: str = '', confidence: float = 0,
                  regime: str = '', position_type: str = '',
                  reason: str = '', is_scalp: bool = False,
                  order_id: str = '') -> int:
        """Log a trade entry (buy). Returns trade_id."""
        cur = self.conn.execute("""
            INSERT INTO trades (symbol, side, qty, price, total_value,
                               strategy, confidence, regime, position_type,
                               reason, is_scalp, order_id)
            VALUES (?, 'buy', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, qty, price, qty * price, strategy, confidence,
              regime, position_type, reason, 1 if is_scalp else 0, order_id))
        self.conn.commit()
        trade_id = cur.lastrowid
        log.info(f"📝 Trade #{trade_id} logged: BUY {qty}x {symbol} @ ${price:.2f} ({strategy})")
        return trade_id

    def log_exit(self, trade_id: int, exit_price: float,
                 pnl: float, hold_time: int = 0,
                 grade: str = '', ai_grade: str = '', ai_reasoning: str = ''):
        """Log a trade exit (sell)."""
        entry = self.get_trade(trade_id)
        if entry:
            entry_price = entry['price']
            pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0
        else:
            pnl_pct = 0

        self.conn.execute("""
            UPDATE trades SET exit_price = ?, exit_time = datetime('now'),
                pnl = ?, pnl_pct = ?, hold_time_seconds = ?,
                grade = ?, ai_grade = ?, ai_reasoning = ?,
                updated_at = datetime('now')
            WHERE id = ?
        """, (exit_price, pnl, pnl_pct, hold_time, grade, ai_grade, ai_reasoning, trade_id))
        self.conn.commit()
        log.info(f"📝 Trade #{trade_id} closed: ${pnl:+.2f} ({grade})")

    def get_trade(self, trade_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return dict(row) if row else None

    # ── Analytics Queries ──────────────────────────────

    def get_all_trades(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_closed_trades(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE exit_price > 0 ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_trades_by_symbol(self, symbol: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE symbol = ? ORDER BY created_at DESC", (symbol,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_trades_by_strategy(self, strategy: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE strategy = ? ORDER BY created_at DESC", (strategy,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_trades_today(self) -> list[dict]:
        today = date.today().isoformat()
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE date(created_at) = ? ORDER BY created_at", (today,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Performance Stats ──────────────────────────────

    def get_overall_stats(self) -> dict:
        """Overall performance across all closed trades."""
        row = self.conn.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN pnl = 0 THEN 1 ELSE 0 END) as breakeven,
                SUM(pnl) as total_pnl,
                AVG(pnl) as avg_pnl,
                AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
                AVG(CASE WHEN pnl < 0 THEN pnl END) as avg_loss,
                MAX(pnl) as max_win,
                MIN(pnl) as max_loss,
                AVG(hold_time_seconds) as avg_hold_time
            FROM trades WHERE exit_price > 0
        """).fetchone()
        
        stats = dict(row)
        total = stats['total_trades'] or 1
        wins = stats['wins'] or 0
        stats['win_rate'] = wins / total if total > 0 else 0
        
        avg_win = abs(stats['avg_win'] or 0)
        avg_loss = abs(stats['avg_loss'] or 1)
        stats['profit_factor'] = avg_win / avg_loss if avg_loss > 0 else 0
        
        return stats

    def get_stats_by_strategy(self) -> list[dict]:
        """Performance broken down by strategy."""
        rows = self.conn.execute("""
            SELECT 
                strategy,
                COUNT(*) as trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                SUM(pnl) as total_pnl,
                AVG(pnl) as avg_pnl,
                ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
                MAX(pnl) as max_win,
                MIN(pnl) as max_loss
            FROM trades WHERE exit_price > 0 AND strategy != ''
            GROUP BY strategy ORDER BY total_pnl DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def get_stats_by_stock(self) -> list[dict]:
        """Performance broken down by stock."""
        rows = self.conn.execute("""
            SELECT 
                symbol,
                COUNT(*) as trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(pnl) as total_pnl,
                AVG(pnl) as avg_pnl,
                ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate
            FROM trades WHERE exit_price > 0
            GROUP BY symbol ORDER BY total_pnl DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def get_stats_by_regime(self) -> list[dict]:
        """Performance broken down by regime."""
        rows = self.conn.execute("""
            SELECT 
                regime,
                COUNT(*) as trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(pnl) as total_pnl,
                ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate
            FROM trades WHERE exit_price > 0 AND regime != ''
            GROUP BY regime ORDER BY total_pnl DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def get_stats_by_day(self, limit: int = 30) -> list[dict]:
        """Daily P&L for the last N days."""
        rows = self.conn.execute("""
            SELECT 
                date(created_at) as trade_date,
                COUNT(*) as trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(pnl) as daily_pnl,
                ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate
            FROM trades WHERE exit_price > 0
            GROUP BY date(created_at) ORDER BY trade_date DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_streak(self) -> dict:
        """Current win/loss streak."""
        rows = self.conn.execute("""
            SELECT pnl FROM trades WHERE exit_price > 0 
            ORDER BY created_at DESC LIMIT 20
        """).fetchall()
        
        if not rows:
            return {'type': 'none', 'count': 0}
        
        streak_type = 'win' if rows[0]['pnl'] > 0 else 'loss'
        count = 0
        for row in rows:
            if (streak_type == 'win' and row['pnl'] > 0) or \
               (streak_type == 'loss' and row['pnl'] <= 0):
                count += 1
            else:
                break
        
        return {'type': streak_type, 'count': count}

    # ── Daily Summary ──────────────────────────────────

    def save_daily_summary(self, equity_start: float, equity_end: float,
                            regime: str = '', sentiment_score: int = 0,
                            sentiment_action: str = '', notes: str = ''):
        """Save end-of-day summary."""
        today = date.today().isoformat()
        trades = self.get_trades_today()
        closed = [t for t in trades if t['exit_price'] > 0]
        
        wins = sum(1 for t in closed if t['pnl'] > 0)
        losses = sum(1 for t in closed if t['pnl'] < 0)
        be = sum(1 for t in closed if t['pnl'] == 0)
        realized = sum(t['pnl'] for t in closed)
        
        best = max(closed, key=lambda t: t['pnl'])['symbol'] if closed else ''
        worst = min(closed, key=lambda t: t['pnl'])['symbol'] if closed else ''
        
        self.conn.execute("""
            INSERT OR REPLACE INTO daily_summary 
            (date, trades_count, wins, losses, breakeven, realized_pnl,
             equity_start, equity_end, regime, sentiment_score, sentiment_action,
             best_trade, worst_trade, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (today, len(trades), wins, losses, be, realized,
              equity_start, equity_end, regime, sentiment_score,
              sentiment_action, best, worst, notes))
        self.conn.commit()

    # ── Position Snapshots ─────────────────────────────

    def snapshot_positions(self, positions: list):
        """Take a snapshot of all positions (for tracking over time)."""
        now = datetime.now().isoformat()
        for p in positions:
            self.conn.execute("""
                INSERT INTO position_snapshots 
                (timestamp, symbol, qty, avg_entry, current_price, unrealized_pnl, unrealized_pnl_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (now, p.symbol, p.qty, p.avg_entry, p.current_price,
                  p.unrealized_pl, p.unrealized_pl_pct))
        self.conn.commit()

    # ── Alert Logging ──────────────────────────────────

    def log_alert(self, alert_type: str, symbol: str = '', message: str = '',
                  telegram: bool = False, discord: bool = False):
        self.conn.execute("""
            INSERT INTO alerts_log (alert_type, symbol, message, sent_telegram, sent_discord)
            VALUES (?, ?, ?, ?, ?)
        """, (alert_type, symbol, message, 1 if telegram else 0, 1 if discord else 0))
        self.conn.commit()

    def close(self):
        self.conn.close()
