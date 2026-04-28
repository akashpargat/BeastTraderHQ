"""
Beast v2.0 — Auto Daily Reports
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generates and sends daily/weekly P&L reports to Telegram + Discord.
Runs at 4:30 PM ET (after market close) or on demand.
"""
import os
import sys
import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv('.env')

from trade_db import TradeDB
from order_gateway import OrderGateway
from notifier import Notifier
from ai_brain import AIBrain

log = logging.getLogger('Beast.DailyReport')
ET = ZoneInfo("America/New_York")


class DailyReportGenerator:
    """Generates rich daily reports for Telegram + Discord."""

    def __init__(self):
        self.db = TradeDB()
        api_key = os.getenv('ALPACA_API_KEY', '')
        secret = os.getenv('ALPACA_SECRET_KEY', '')
        self.gateway = OrderGateway(api_key, secret, paper=True)
        self.notify = Notifier()
        self.brain = AIBrain()

    def generate_daily_report(self) -> str:
        """Generate end-of-day report."""
        now = datetime.now(ET)
        positions = self.gateway.get_positions()
        acct = self.gateway.get_account()
        
        total_pl = sum(p.unrealized_pl for p in positions)
        green = [p for p in positions if p.is_green]
        red = [p for p in positions if p.is_red]

        # Get today's closed trades from DB
        today_trades = self.db.get_trades_today()
        closed = [t for t in today_trades if t.get('exit_price', 0) > 0]
        realized = sum(t.get('pnl', 0) for t in closed)
        wins = sum(1 for t in closed if t.get('pnl', 0) > 0)
        wr = wins / len(closed) * 100 if closed else 0

        # Stats
        stats = self.db.get_overall_stats()
        streak = self.db.get_streak()
        by_strategy = self.db.get_stats_by_strategy()

        lines = []
        lines.append(f"🏆 DAILY REPORT — {now.strftime('%B %d, %Y')}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # Portfolio
        lines.append("")
        lines.append("💰 PORTFOLIO")
        lines.append(f"┌─────────────────────────┐")
        lines.append(f"│ Equity:   ${acct.get('equity', 0):>10,.2f}  │")
        lines.append(f"│ Cash:     ${acct.get('cash', 0):>10,.2f}  │")
        lines.append(f"│ Unreal:   ${total_pl:>+10,.2f}  │")
        lines.append(f"│ Realized: ${realized:>+10,.2f}  │")
        lines.append(f"│ Positions: {len(positions):>3d}            │")
        lines.append(f"│ 🟢 Green: {len(green):>3d}             │")
        lines.append(f"│ 🔴 Red:   {len(red):>3d} (HELD)       │")
        lines.append(f"└─────────────────────────┘")

        # Today's trades
        if closed:
            lines.append("")
            lines.append(f"📊 TODAY'S TRADES ({len(closed)} closed)")
            for t in sorted(closed, key=lambda x: x.get('pnl', 0), reverse=True):
                emoji = "🟢" if t.get('pnl', 0) > 0 else "🔴"
                lines.append(f"  {emoji} {t.get('symbol', '?'):6s} ${t.get('pnl', 0):+8.2f} "
                            f"({t.get('strategy', '?')})")
            lines.append(f"  Win Rate: {wr:.0f}% | Realized: ${realized:+,.2f}")
        else:
            lines.append("")
            lines.append("📊 No closed trades today")

        # Open positions
        lines.append("")
        lines.append("📦 OPEN POSITIONS")
        for p in sorted(positions, key=lambda x: x.unrealized_pl, reverse=True):
            emoji = "🟢" if p.is_green else "🔴"
            lines.append(f"  {emoji} {p.symbol:6s} {p.qty:5d}x ${p.unrealized_pl:+8.2f}")

        # Streak
        streak_emoji = "🟢" if streak['type'] == 'win' else "🔴"
        lines.append(f"\n  Streak: {streak_emoji} {streak['count']}x {streak['type']}")

        # All-time stats
        if stats.get('total_trades', 0) > 0:
            lines.append("")
            lines.append("📈 ALL-TIME STATS")
            lines.append(f"  Trades: {stats.get('total_trades', 0)} | "
                        f"WR: {stats.get('win_rate', 0):.0%} | "
                        f"PF: {stats.get('profit_factor', 0):.2f}")
            lines.append(f"  Total P&L: ${stats.get('total_pnl', 0):+,.2f}")

        # Strategy breakdown
        if by_strategy:
            lines.append("")
            lines.append("📋 BY STRATEGY")
            for s in by_strategy[:5]:
                emoji = "🟢" if s['total_pnl'] > 0 else "🔴"
                lines.append(f"  {emoji} {s['strategy']:10s} {s['trades']:3d}t "
                            f"WR:{s['win_rate']:.0f}% ${s['total_pnl']:+,.2f}")

        # AI morning reflection (if brain is available)
        if self.brain.is_available:
            lines.append("")
            lines.append("🧠 AI REFLECTION")
            reflection = self.brain._ask(
                f"Give a 3-line trading day summary:\n"
                f"P&L: ${total_pl:+.2f} unrealized, ${realized:+.2f} realized\n"
                f"Positions: {len(green)} green, {len(red)} red\n"
                f"Today's trades: {len(closed)}, WR: {wr:.0f}%\n"
                f"Keep it SHORT and actionable.",
                max_tokens=100,
                system="You are a senior trader doing an end-of-day review. 3 lines max."
            )
            if reflection:
                lines.append(f"  {reflection}")

        lines.append("")
        lines.append(f"⏰ {now.strftime('%H:%M ET')} | Iron Law 1: All red = HELD 🔒")

        return "\n".join(lines)

    def generate_weekly_report(self) -> str:
        """Generate weekly performance summary."""
        stats = self.db.get_overall_stats()
        by_day = self.db.get_stats_by_day(7)
        by_strategy = self.db.get_stats_by_strategy()
        by_stock = self.db.get_stats_by_stock()

        lines = []
        lines.append("📊 WEEKLY PERFORMANCE REPORT")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        if by_day:
            lines.append("")
            lines.append("📅 DAILY P&L")
            total_week = 0
            for d in by_day:
                emoji = "🟢" if d['daily_pnl'] > 0 else "🔴"
                lines.append(f"  {emoji} {d['trade_date']} {d['trades']:2d}t "
                            f"WR:{d['win_rate']:.0f}% ${d['daily_pnl']:+,.2f}")
                total_week += d['daily_pnl']
            lines.append(f"  {'━' * 35}")
            lines.append(f"  WEEK TOTAL: ${total_week:+,.2f}")

        if by_strategy:
            lines.append("")
            lines.append("📋 STRATEGY RANKING")
            for i, s in enumerate(by_strategy[:5], 1):
                medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
                lines.append(f"  {medal} {s['strategy']:10s} ${s['total_pnl']:+,.2f} "
                            f"({s['win_rate']:.0f}% WR)")

        if by_stock:
            lines.append("")
            lines.append("📈 BEST STOCKS")
            for s in by_stock[:5]:
                emoji = "🟢" if s['total_pnl'] > 0 else "🔴"
                lines.append(f"  {emoji} {s['symbol']:6s} ${s['total_pnl']:+,.2f} "
                            f"({s['win_rate']:.0f}% WR, {s['trades']}t)")

        return "\n".join(lines)

    def send_daily(self):
        """Generate and send daily report to Telegram + Discord."""
        report = self.generate_daily_report()
        self.notify.send(report)
        log.info("📊 Daily report sent to all channels")
        return report

    def send_weekly(self):
        """Generate and send weekly report."""
        report = self.generate_weekly_report()
        self.notify.send(report)
        log.info("📊 Weekly report sent to all channels")
        return report


if __name__ == '__main__':
    gen = DailyReportGenerator()
    if '--weekly' in sys.argv:
        print(gen.generate_weekly_report())
    else:
        report = gen.send_daily()
        print(report)
