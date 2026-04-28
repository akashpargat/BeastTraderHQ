"""
Beast v2.0 — Performance Tracker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Real-time and historical performance analytics.
Generates reports for Telegram and Discord.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from trade_db import TradeDB

log = logging.getLogger('Beast.Performance')
ET = ZoneInfo("America/New_York")


class PerformanceTracker:
    """Tracks and reports trading performance."""

    def __init__(self, db: TradeDB = None):
        self.db = db or TradeDB()

    def generate_report(self) -> str:
        """Generate a full performance report (fancy, for Telegram/Discord)."""
        stats = self.db.get_overall_stats()
        by_strategy = self.db.get_stats_by_strategy()
        by_stock = self.db.get_stats_by_stock()
        by_regime = self.db.get_stats_by_regime()
        by_day = self.db.get_stats_by_day(10)
        streak = self.db.get_streak()

        lines = []
        lines.append("🏆 PERFORMANCE REPORT")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # Overall
        total = stats.get('total_trades', 0)
        wins = stats.get('wins', 0)
        wr = stats.get('win_rate', 0)
        pnl = stats.get('total_pnl', 0)
        pf = stats.get('profit_factor', 0)

        lines.append("")
        lines.append("📊 OVERALL")
        lines.append(f"┌─────────────────────────┐")
        lines.append(f"│ Trades:    {total:>6d}        │")
        lines.append(f"│ Win Rate:  {wr:>5.1%}        │")
        lines.append(f"│ Total P&L: ${pnl:>+9.2f}  │")
        lines.append(f"│ Avg P&L:   ${stats.get('avg_pnl', 0):>+9.2f}  │")
        lines.append(f"│ Profit Factor: {pf:>5.2f}    │")
        lines.append(f"│ Max Win:   ${stats.get('max_win', 0):>+9.2f}  │")
        lines.append(f"│ Max Loss:  ${stats.get('max_loss', 0):>+9.2f}  │")
        lines.append(f"│ Streak:    {streak['count']}x {'🟢 WIN' if streak['type'] == 'win' else '🔴 LOSS'} │")
        lines.append(f"└─────────────────────────┘")

        # By Strategy
        if by_strategy:
            lines.append("")
            lines.append("📋 BY STRATEGY")
            for s in by_strategy:
                emoji = "🟢" if s['total_pnl'] > 0 else "🔴"
                lines.append(f"{emoji} {s['strategy']:5s} {s['trades']:3d} trades "
                            f"WR:{s['win_rate']:>5.1f}% P&L:${s['total_pnl']:>+.2f}")

        # By Stock
        if by_stock:
            lines.append("")
            lines.append("📈 BY STOCK (top 5)")
            for s in by_stock[:5]:
                emoji = "🟢" if s['total_pnl'] > 0 else "🔴"
                lines.append(f"{emoji} {s['symbol']:6s} {s['trades']:3d}t "
                            f"WR:{s['win_rate']:>5.1f}% ${s['total_pnl']:>+.2f}")

        # By Regime
        if by_regime:
            lines.append("")
            lines.append("🌤️ BY REGIME")
            for r in by_regime:
                regime_emoji = {"BULL": "🐂", "BEAR": "🐻", "CHOPPY": "🌊"}.get(r['regime'], "📊")
                lines.append(f"{regime_emoji} {r['regime']:8s} {r['trades']:3d}t "
                            f"WR:{r['win_rate']:>5.1f}% ${r['total_pnl']:>+.2f}")

        # Daily P&L
        if by_day:
            lines.append("")
            lines.append("📅 DAILY P&L (last 10)")
            for d in by_day:
                emoji = "🟢" if d['daily_pnl'] > 0 else "🔴"
                lines.append(f"{emoji} {d['trade_date']} {d['trades']:2d}t "
                            f"WR:{d['win_rate']:>5.1f}% ${d['daily_pnl']:>+.2f}")

        lines.append("")
        lines.append(f"📊 Generated: {datetime.now(ET).strftime('%H:%M ET %b %d')}")

        return "\n".join(lines)

    def get_strategy_recommendation(self) -> str:
        """Based on historical performance, recommend which strategies to use."""
        by_strategy = self.db.get_stats_by_strategy()
        if not by_strategy:
            return "Not enough data. Need more trades to make recommendations."

        profitable = [s for s in by_strategy if s['total_pnl'] > 0]
        losing = [s for s in by_strategy if s['total_pnl'] <= 0]

        lines = ["🎯 STRATEGY RECOMMENDATIONS", ""]
        if profitable:
            lines.append("✅ KEEP USING:")
            for s in profitable:
                lines.append(f"  {s['strategy']} — ${s['total_pnl']:+.2f} ({s['win_rate']:.0f}% WR)")

        if losing:
            lines.append("")
            lines.append("⛔ STOP USING:")
            for s in losing:
                lines.append(f"  {s['strategy']} — ${s['total_pnl']:+.2f} ({s['win_rate']:.0f}% WR)")

        return "\n".join(lines)
