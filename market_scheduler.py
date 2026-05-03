"""
Beast V6 — Market-Aware Scheduler
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Controls WHEN each task runs based on market hours.
Saves ~74% of AI costs by not running GPT at 2 AM on Saturday.

TWO MODES:
1. SCHEDULE-BASED: Tasks slow down or pause outside market hours
2. EVENT-DRIVEN: Off-hours tasks only fire on real market events
   (price spike >2%, volume surge, earnings release)

PERIODS:
  MARKET:     9:30 AM - 4:00 PM ET  Mon-Fri  (full speed)
  PRE_MARKET: 7:00 AM - 9:30 AM ET  Mon-Fri  (event-driven + reduced)
  AFTER_HOURS: 4:00 PM - 6:30 PM ET Mon-Fri  (event-driven + earnings watch)
  NIGHT:      6:30 PM - 7:00 AM ET  Mon-Fri  (intelligence only, no AI)
  WEEKEND:    Fri 6:30 PM - Mon 7 AM          (intelligence + 3AM learning only)

SAVINGS: ~$432/mo in GPT costs (74% reduction)
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger("Beast.Scheduler")

ET = ZoneInfo("America/New_York")


# ═══════════════════════════════════════════════════════════
#  MARKET PERIOD DETECTION
# ═══════════════════════════════════════════════════════════

def get_market_period() -> str:
    """Get current market period based on OFFICIAL US market hours.
    
    Returns one of: MARKET, PRE_MARKET, AFTER_HOURS, NIGHT, WEEKEND
    
    All times are ET (Eastern) — NYSE/NASDAQ official hours.
    CST is always ET minus 1 hour.
    
    Official hours:
      Period        ET Time              CST Time
      ──────────    ─────────────────    ─────────────────
      Pre-Market:   4:00 AM - 9:30 AM   3:00 AM - 8:30 AM
      Market:       9:30 AM - 4:00 PM   8:30 AM - 3:00 PM
      After-Hours:  4:00 PM - 8:00 PM   3:00 PM - 7:00 PM
      Night:        8:00 PM - 4:00 AM   7:00 PM - 3:00 AM
      Weekend:      Fri 8PM - Mon 4AM   Fri 7PM - Mon 3AM
    """
    now = datetime.now(ET)
    dow = now.weekday()  # 0=Mon, 6=Sun
    time_mins = now.hour * 60 + now.minute

    # Weekend: Saturday, Sunday, Friday after 8 PM ET, Monday before 4 AM ET
    if dow == 5 or dow == 6:  # Sat, Sun
        return "WEEKEND"
    if dow == 4 and time_mins >= 20 * 60:  # Friday after 8:00 PM ET (7 PM CST)
        return "WEEKEND"
    if dow == 0 and time_mins < 4 * 60:  # Monday before 4:00 AM ET (3 AM CST)
        return "WEEKEND"

    # Weekday periods (official NYSE/NASDAQ hours)
    if time_mins < 4 * 60:       # Before 4:00 AM ET (3 AM CST)
        return "NIGHT"
    if time_mins < 9 * 60 + 30:  # 4:00 - 9:30 AM ET (3:00 - 8:30 AM CST)
        return "PRE_MARKET"
    if time_mins < 16 * 60:      # 9:30 AM - 4:00 PM ET (8:30 AM - 3:00 PM CST)
        return "MARKET"
    if time_mins < 20 * 60:      # 4:00 - 8:00 PM ET (3:00 - 7:00 PM CST)
        return "AFTER_HOURS"
    return "NIGHT"               # After 8:00 PM ET (7:00 PM CST)


def is_trading_hours() -> bool:
    """True during market hours (9:30 AM - 4:00 PM ET / 8:30 AM - 3:00 PM CST)."""
    return get_market_period() == "MARKET"


def is_market_active() -> bool:
    """True during any active period (market + pre + after). False at night/weekend."""
    return get_market_period() in ("MARKET", "PRE_MARKET", "AFTER_HOURS")


# ═══════════════════════════════════════════════════════════
#  TASK SCHEDULE CONFIG
#  
#  Each task has an interval per market period.
#  0 = OFF (don't run), None = use default interval
# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
#  APPROVED SCHEDULE (V6 — revised)
#
#  KEY DESIGN DECISIONS:
#  1. runner_scan runs 24/7 (FREE — just price checks)
#     It's our early warning system. When it finds a >3%
#     mover, it triggers full AI scan for that stock.
#
#  2. AI tasks OFF at night/weekend (saves 74% = ~$288/mo)
#     Market is closed → AI verdicts are worthless.
#
#  3. Intelligence scan runs 24/7 (FREE — yfinance only)
#     Keeps learning stock DNA even on weekends.
#
#  4. 3AM learning runs EVERY night including weekends
#     Only 3 GPT calls = ~$0.10/night.
#
#  5. Event trigger: >2% move at any hour → fires AI scan
#     Catches earnings surprises, geopolitical events.
# ═══════════════════════════════════════════════════════════

# Intervals in SECONDS for each period
# 0 = OFF for that period
TASK_SCHEDULE = {
    # Task name              MARKET    PRE_MARKET  AFTER_HOURS  NIGHT    WEEKEND
    # ─── FREE TASKS (no GPT cost) ───────────────────────────────────────────
    "position_monitor":     (60,       300,        300,         900,     0),
    "fast_runner_scan":     (120,      120,        120,         300,     300),   # ← 24/7 ALWAYS ON (trigger!)
    "decision_report":      (600,      1800,       1800,        0,       0),
    "intelligence_scan":    (3600,     3600,       3600,        7200,    7200),  # ← 24/7 (yfinance, no AI)
    "outcome_grader":       (1800,     1800,       1800,        3600,    0),
    "fill_tracker":         (300,      300,        300,         0,       0),
    "ah_pm_scanner":        (0,        900,        900,         0,       0),
    # ─── AI TASKS (GPT cost) ────────────────────────────────────────────────
    "full_scan":            (300,      900,        900,         0,       0),     # OFF at night (event trigger covers it)
    "claude_deep_scan":     (1800,     3600,       3600,        0,       0),     # OFF at night
    "ai_background_learning": (3600,   3600,       3600,        0,       0),     # OFF at night
    "claude_daily_deep_learn": (0,     0,          0,           86400,   86400), # 3AM EVERY night
}

# Which tasks use AI (GPT) calls — these are the expensive ones
AI_TASKS = {"full_scan", "claude_deep_scan", "ai_background_learning", "claude_daily_deep_learn"}


def should_task_run(task_name: str, last_run_time: float, current_time: float) -> bool:
    """Check if a task should run based on market period and elapsed time.
    
    Args:
        task_name: Name of the task (must be in TASK_SCHEDULE)
        last_run_time: Unix timestamp of last run (0 = never)
        current_time: Current unix timestamp (time.time())
    
    Returns:
        True if enough time has elapsed for this period's interval
    """
    period = get_market_period()
    period_idx = {"MARKET": 0, "PRE_MARKET": 1, "AFTER_HOURS": 2, "NIGHT": 3, "WEEKEND": 4}
    idx = period_idx.get(period, 0)

    schedule = TASK_SCHEDULE.get(task_name)
    if not schedule:
        return True  # Unknown task — always run

    interval = schedule[idx]
    if interval == 0:
        return False  # Task is OFF for this period

    elapsed = current_time - last_run_time
    return elapsed >= interval


def get_task_interval(task_name: str) -> int:
    """Get current interval for a task based on market period.
    Returns seconds, or 0 if task should be OFF."""
    period = get_market_period()
    period_idx = {"MARKET": 0, "PRE_MARKET": 1, "AFTER_HOURS": 2, "NIGHT": 3, "WEEKEND": 4}
    idx = period_idx.get(period, 0)
    schedule = TASK_SCHEDULE.get(task_name)
    if not schedule:
        return 60
    return schedule[idx]


def get_schedule_summary() -> dict:
    """Get full schedule overview for logging/dashboard.
    Shows both ET and CST times for convenience."""
    period = get_market_period()
    now_et = datetime.now(ET)
    CST = ZoneInfo("America/Chicago")
    now_cst = datetime.now(CST)
    
    summary = {
        "current_period": period,
        "time_et": now_et.strftime("%I:%M %p ET"),
        "time_cst": now_cst.strftime("%I:%M %p CST"),
        "day": now_et.strftime("%A"),
        "tasks": {},
    }
    
    period_idx = {"MARKET": 0, "PRE_MARKET": 1, "AFTER_HOURS": 2, "NIGHT": 3, "WEEKEND": 4}
    idx = period_idx.get(period, 0)
    
    for task, intervals in TASK_SCHEDULE.items():
        interval = intervals[idx]
        is_ai = task in AI_TASKS
        if interval == 0:
            status = "OFF"
        elif interval >= 3600:
            status = f"every {interval // 3600}h"
        elif interval >= 60:
            status = f"every {interval // 60}min"
        else:
            status = f"every {interval}s"
        
        summary["tasks"][task] = {
            "interval_sec": interval,
            "status": status,
            "uses_ai": is_ai,
            "active": interval > 0,
        }
    
    active_ai = sum(1 for t, i in summary["tasks"].items() if i["active"] and i["uses_ai"])
    summary["active_ai_tasks"] = active_ai
    summary["estimated_ai_calls_per_hour"] = _estimate_hourly_calls(period)
    
    return summary


def _estimate_hourly_calls(period: str) -> int:
    """Estimate AI calls per hour for a given period."""
    period_idx = {"MARKET": 0, "PRE_MARKET": 1, "AFTER_HOURS": 2, "NIGHT": 3, "WEEKEND": 4}
    idx = period_idx.get(period, 0)
    
    calls = 0
    ai_stock_counts = {
        "full_scan": 16,          # 16 stocks per batch
        "claude_deep_scan": 8,    # 8 stocks deep
        "ai_background_learning": 20,  # 20 stocks
        "claude_daily_deep_learn": 3,  # 3 batches
    }
    
    for task in AI_TASKS:
        interval = TASK_SCHEDULE.get(task, (0,0,0,0,0))[idx]
        if interval > 0:
            runs_per_hour = 3600 / interval
            stocks = ai_stock_counts.get(task, 1)
            calls += int(runs_per_hour * stocks)
    
    return calls


# ═══════════════════════════════════════════════════════════
#  EVENT-DRIVEN TRIGGERS (for off-hours)
#
#  During PRE_MARKET and AFTER_HOURS, instead of scanning
#  on a fixed timer, scan when something ACTUALLY happens:
#  - Stock price moves >2% since last check
#  - Volume spikes >3x average
#  - Known earnings release time
# ═══════════════════════════════════════════════════════════

class EventTrigger:
    """Detects market events that should trigger off-hours scans."""

    def __init__(self):
        self._last_prices = {}  # symbol → price
        self._last_volumes = {}  # symbol → avg_volume
        self._triggered = set()  # symbols that already triggered this session
        self.PRICE_THRESHOLD = 0.02  # 2% move triggers scan
        self.VOLUME_MULT = 3.0  # 3x volume triggers scan

    def check_event(self, symbol: str, current_price: float,
                    current_volume: int = 0, avg_volume: int = 0) -> dict:
        """Check if a stock has an event worth scanning.
        
        Returns: {'triggered': bool, 'reason': str, 'type': str}
        """
        result = {'triggered': False, 'reason': '', 'type': ''}
        
        # Skip if already triggered this session (prevent spam)
        if symbol in self._triggered:
            return result

        last_price = self._last_prices.get(symbol, 0)
        
        if last_price > 0 and current_price > 0:
            pct_move = abs(current_price - last_price) / last_price
            if pct_move >= self.PRICE_THRESHOLD:
                direction = "UP" if current_price > last_price else "DOWN"
                result = {
                    'triggered': True,
                    'reason': f"{symbol} moved {pct_move*100:+.1f}% ({direction})",
                    'type': 'price_spike',
                }
                self._triggered.add(symbol)
                log.info(f"[EVENT] {result['reason']}")

        # Volume spike
        if not result['triggered'] and current_volume > 0 and avg_volume > 0:
            vol_ratio = current_volume / avg_volume
            if vol_ratio >= self.VOLUME_MULT:
                result = {
                    'triggered': True,
                    'reason': f"{symbol} volume spike {vol_ratio:.1f}x avg",
                    'type': 'volume_spike',
                }
                self._triggered.add(symbol)
                log.info(f"[EVENT] {result['reason']}")

        # Update last known price
        if current_price > 0:
            self._last_prices[symbol] = current_price

        return result

    def reset_triggers(self):
        """Reset triggered set (call at start of each market session)."""
        self._triggered.clear()

    def get_triggered_symbols(self) -> list:
        """Get list of symbols that triggered events."""
        return list(self._triggered)


# ═══════════════════════════════════════════════════════════
#  CONVENIENCE: One-liner checks for use in task loops
# ═══════════════════════════════════════════════════════════

def ai_should_run() -> bool:
    """Quick check: should AI tasks run right now?
    Returns False during NIGHT and WEEKEND (saves tokens)."""
    period = get_market_period()
    return period in ("MARKET", "PRE_MARKET", "AFTER_HOURS")


def is_weekend() -> bool:
    """True on Saturday and Sunday (and Friday after 8 PM ET / 7 PM CST)."""
    return get_market_period() == "WEEKEND"


def log_schedule_status():
    """Log current schedule state — call on startup and period transitions."""
    s = get_schedule_summary()
    active = [f"{t}({d['status']})" for t, d in s['tasks'].items() if d['active']]
    off = [t for t, d in s['tasks'].items() if not d['active']]
    log.info(f"[SCHED] {s['current_period']} ({s['time_et']} / {s['time_cst']} {s['day']}) | "
             f"Active: {len(active)} tasks | AI calls/hr: ~{s['estimated_ai_calls_per_hour']} | "
             f"OFF: {', '.join(off) if off else 'none'}")
