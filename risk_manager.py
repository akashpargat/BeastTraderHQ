"""
risk_manager.py — Institutional-Grade Risk Management for Beast Trading Bot

Implements Kelly Criterion sizing, loss limits, correlation checks,
sector caps, earnings avoidance, and a master approval gate.
Every decision is logged to PostgreSQL for audit trail.
"""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import yfinance as yf

# Use numpy for correlation instead of scipy (scipy hard to install on some VMs)
def _pearsonr(x, y):
    """Numpy-only Pearson correlation. Returns (r, p_value_placeholder)."""
    try:
        if len(x) < 3 or len(y) < 3:
            return 0.0, 1.0
        x = np.array(x, dtype=float)
        y = np.array(y, dtype=float)
        r = np.corrcoef(x, y)[0, 1]
        return float(r) if not np.isnan(r) else 0.0, 0.0
    except:
        return 0.0, 1.0

try:
    from db_postgres import BeastDB
except ImportError:
    BeastDB = None

log = logging.getLogger("beast")

# ─────────────────────────────────────────────────────────────────────
# Sector map — extend as your universe grows
# ─────────────────────────────────────────────────────────────────────
SECTOR_MAP = {
    # Technology
    "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology",
    "GOOG": "Technology", "META": "Technology", "NVDA": "Technology",
    "AMD": "Technology", "INTC": "Technology", "TSM": "Technology",
    "AVGO": "Technology", "ORCL": "Technology", "CRM": "Technology",
    "ADBE": "Technology", "CSCO": "Technology", "QCOM": "Technology",
    "TXN": "Technology", "IBM": "Technology", "NOW": "Technology",
    "MU": "Technology", "AMAT": "Technology", "LRCX": "Technology",
    "KLAC": "Technology", "MRVL": "Technology", "SNPS": "Technology",
    "CDNS": "Technology", "PANW": "Technology", "CRWD": "Technology",
    "NET": "Technology", "PLTR": "Technology", "SMCI": "Technology",
    "ARM": "Technology", "DELL": "Technology", "HPE": "Technology",
    # Consumer Discretionary
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    "HD": "Consumer Discretionary", "NKE": "Consumer Discretionary",
    "MCD": "Consumer Discretionary", "SBUX": "Consumer Discretionary",
    "LOW": "Consumer Discretionary", "TJX": "Consumer Discretionary",
    "BKNG": "Consumer Discretionary", "CMG": "Consumer Discretionary",
    # Financials
    "JPM": "Financials", "BAC": "Financials", "WFC": "Financials",
    "GS": "Financials", "MS": "Financials", "C": "Financials",
    "BLK": "Financials", "SCHW": "Financials", "AXP": "Financials",
    "V": "Financials", "MA": "Financials", "PYPL": "Financials",
    "SQ": "Financials", "COIN": "Financials",
    # Healthcare
    "UNH": "Healthcare", "JNJ": "Healthcare", "LLY": "Healthcare",
    "PFE": "Healthcare", "ABBV": "Healthcare", "MRK": "Healthcare",
    "TMO": "Healthcare", "ABT": "Healthcare", "DHR": "Healthcare",
    "BMY": "Healthcare", "AMGN": "Healthcare", "GILD": "Healthcare",
    "ISRG": "Healthcare", "MDT": "Healthcare", "MRNA": "Healthcare",
    # Energy
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy",
    "SLB": "Energy", "EOG": "Energy", "OXY": "Energy",
    "MPC": "Energy", "VLO": "Energy", "PSX": "Energy",
    # Communication Services
    "DIS": "Communication Services", "NFLX": "Communication Services",
    "CMCSA": "Communication Services", "T": "Communication Services",
    "VZ": "Communication Services", "TMUS": "Communication Services",
    # Consumer Staples
    "PG": "Consumer Staples", "KO": "Consumer Staples",
    "PEP": "Consumer Staples", "COST": "Consumer Staples",
    "WMT": "Consumer Staples", "PM": "Consumer Staples",
    "MO": "Consumer Staples", "CL": "Consumer Staples",
    # Industrials
    "CAT": "Industrials", "DE": "Industrials", "BA": "Industrials",
    "HON": "Industrials", "UPS": "Industrials", "RTX": "Industrials",
    "GE": "Industrials", "LMT": "Industrials", "UNP": "Industrials",
    # Materials
    "LIN": "Materials", "APD": "Materials", "SHW": "Materials",
    "FCX": "Materials", "NEM": "Materials", "NUE": "Materials",
    # Utilities
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities",
    "D": "Utilities", "AEP": "Utilities", "XEL": "Utilities",
    # Real Estate
    "AMT": "Real Estate", "PLD": "Real Estate", "CCI": "Real Estate",
    "EQIX": "Real Estate", "SPG": "Real Estate", "O": "Real Estate",
    # ETFs
    "SPY": "ETF-Broad", "QQQ": "ETF-Tech", "IWM": "ETF-SmallCap",
    "DIA": "ETF-Broad", "ARKK": "ETF-Innovation", "XLF": "ETF-Financials",
    "XLE": "ETF-Energy", "XLK": "ETF-Tech", "XLV": "ETF-Healthcare",
    "SOXX": "ETF-Semis", "GLD": "ETF-Gold", "TLT": "ETF-Bonds",
    "VTI": "ETF-Broad", "VOO": "ETF-Broad", "SOXL": "ETF-Semis",
}

# ─────────────────────────────────────────────────────────────────────
# Defaults / constants
# ─────────────────────────────────────────────────────────────────────
DEFAULT_WIN_RATE = 0.50
DEFAULT_AVG_WIN = 1.5          # avg win / avg loss ratio
DEFAULT_AVG_LOSS = 1.0
MAX_POSITION_PCT = 0.05        # 5 % of portfolio per position
MAX_RISK_PER_TRADE_PCT = 0.01  # 1 % risk per trade
ATR_STOP_MULTIPLIER = 2.0
VIX_THRESHOLD = 25.0
VIX_REDUCTION = 0.50           # halve size when VIX > threshold
DAILY_LOSS_LIMIT = -0.02       # -2 %
WEEKLY_LOSS_LIMIT = -0.05      # -5 %
MONTHLY_LOSS_LIMIT = -0.10     # -10 %
WEEKLY_LOSS_SIZE_MULT = 0.50   # halve sizes on weekly breach
CORRELATION_HIGH = 0.70
CORRELATION_EXTREME = 0.90
SECTOR_CAP_PCT = 0.25          # 25 % max per sector
EARNINGS_WINDOW_HOURS = 48
EARNINGS_COOLDOWN_MIN = 30


class RiskManager:
    """Institutional-grade risk controls for the Beast paper-trading bot."""

    def __init__(self, db=None, portfolio_value: float = 103_000.0):
        self.db = db
        self.portfolio_value = portfolio_value
        if self.db:
            self._ensure_tables()
        log.info("[RISK] RiskManager initialised — portfolio $%.2f, db=%s", portfolio_value, 'connected' if db else 'none')

    # ── Schema bootstrap ─────────────────────────────────────────────
    def _ensure_tables(self):
        """Create risk-tracking tables if they don't exist."""
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS risk_checks (
                    id SERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    symbol TEXT NOT NULL,
                    check_type TEXT NOT NULL,
                    approved BOOLEAN,
                    original_qty INTEGER,
                    adjusted_qty INTEGER,
                    reason TEXT,
                    details JSONB
                );
            """)
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS daily_risk_state (
                    id SERIAL PRIMARY KEY,
                    date DATE NOT NULL UNIQUE,
                    starting_equity NUMERIC,
                    min_equity NUMERIC,
                    max_equity NUMERIC,
                    ending_equity NUMERIC,
                    daily_pnl NUMERIC,
                    daily_pnl_pct NUMERIC,
                    trading_halted BOOLEAN DEFAULT FALSE,
                    halt_reason TEXT,
                    trades_count INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0
                );
            """)
            log.info("[RISK] Risk tables verified")
        except Exception as e:
            log.error("[RISK] Table creation failed: %s", e)

    # ── Helpers ───────────────────────────────────────────────────────
    def _log_check(self, symbol: str, check_type: str, approved: bool,
                   original_qty: int, adjusted_qty: int, reason: str,
                   details: Optional[dict] = None):
        """Persist every risk decision to PostgreSQL."""
        import json
        try:
            self.db.execute(
                """INSERT INTO risk_checks
                   (symbol, check_type, approved, original_qty, adjusted_qty, reason, details)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (symbol, check_type, approved, original_qty, adjusted_qty,
                 reason, json.dumps(details or {})),
            )
        except Exception as e:
            log.error("[RISK] Failed to log check: %s", e)

    def _get_trade_stats(self, symbol: str) -> dict:
        """Pull win_rate, avg_win, avg_loss from trade history."""
        try:
            rows = self.db.fetch(
                """SELECT pnl FROM trades
                   WHERE symbol = %s AND pnl IS NOT NULL
                   ORDER BY closed_at DESC LIMIT 100""",
                (symbol,),
            )
            if not rows or len(rows) < 5:
                return {
                    "win_rate": DEFAULT_WIN_RATE,
                    "avg_win": DEFAULT_AVG_WIN,
                    "avg_loss": DEFAULT_AVG_LOSS,
                    "sample_size": len(rows) if rows else 0,
                }
            pnls = [float(r[0]) for r in rows]
            wins = [p for p in pnls if p > 0]
            losses = [abs(p) for p in pnls if p <= 0]
            win_rate = len(wins) / len(pnls) if pnls else DEFAULT_WIN_RATE
            avg_win = float(np.mean(wins)) if wins else DEFAULT_AVG_WIN
            avg_loss = float(np.mean(losses)) if losses else DEFAULT_AVG_LOSS
            return {
                "win_rate": win_rate,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "sample_size": len(pnls),
            }
        except Exception as e:
            log.warning("[RISK] Trade stats lookup failed: %s — using defaults", e)
            return {
                "win_rate": DEFAULT_WIN_RATE,
                "avg_win": DEFAULT_AVG_WIN,
                "avg_loss": DEFAULT_AVG_LOSS,
                "sample_size": 0,
            }

    @staticmethod
    def _get_sector(symbol: str) -> str:
        return SECTOR_MAP.get(symbol.upper(), "Unknown")

    def _get_vix(self) -> float:
        """Fetch current VIX level via yfinance."""
        try:
            vix = yf.Ticker("^VIX")
            price = vix.fast_info.get("lastPrice", None)
            if price is None:
                hist = vix.history(period="1d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            return float(price) if price else 20.0
        except Exception as e:
            log.warning("[RISK] VIX fetch failed: %s — defaulting 20", e)
            return 20.0

    # ══════════════════════════════════════════════════════════════════
    # 1. Kelly Criterion Position Sizing
    # ══════════════════════════════════════════════════════════════════
    def kelly_position_size(
        self,
        symbol: str,
        conviction: float,
        current_price: float,
        atr: float,
    ) -> dict:
        """
        Calculate optimal position size using Half-Kelly with multiple
        safety adjustments (VIX, correlation, ATR-based stop).
        """
        adjustments: list[str] = []
        try:
            conviction = max(0.0, min(1.0, conviction))

            # --- trade stats ---
            stats = self._get_trade_stats(symbol)
            win_rate = stats["win_rate"]
            avg_win = stats["avg_win"]
            avg_loss = stats["avg_loss"]
            loss_rate = 1.0 - win_rate

            # --- full Kelly ---
            if avg_win == 0:
                kelly_raw = 0.0
            else:
                kelly_raw = (win_rate * avg_win - loss_rate * avg_loss) / avg_win
            kelly_raw = max(kelly_raw, 0.0)
            kelly_half = kelly_raw / 2.0
            adjustments.append(f"half-kelly={kelly_half:.4f}")

            # --- scale by conviction ---
            sized_pct = kelly_half * conviction
            adjustments.append(f"conviction={conviction:.2f}")

            # --- hard cap at 5 % ---
            if sized_pct > MAX_POSITION_PCT:
                sized_pct = MAX_POSITION_PCT
                adjustments.append(f"capped-at-{MAX_POSITION_PCT*100:.0f}%")

            # --- VIX reduction ---
            vix = self._get_vix()
            if vix > VIX_THRESHOLD:
                sized_pct *= VIX_REDUCTION
                adjustments.append(f"vix-reduction(VIX={vix:.1f})")

            # --- ATR-based stop sizing ---
            if atr > 0 and current_price > 0:
                risk_dollars = self.portfolio_value * MAX_RISK_PER_TRADE_PCT
                stop_distance = atr * ATR_STOP_MULTIPLIER
                atr_shares = int(risk_dollars / stop_distance)
                kelly_shares = int((sized_pct * self.portfolio_value) / current_price)
                shares = min(kelly_shares, atr_shares)
                if shares < kelly_shares:
                    adjustments.append("atr-stop-limited")
            else:
                shares = int((sized_pct * self.portfolio_value) / current_price) if current_price > 0 else 0

            shares = max(shares, 0)
            dollar_amount = shares * current_price
            risk_pct = dollar_amount / self.portfolio_value if self.portfolio_value else 0.0

            result = {
                "shares": shares,
                "dollar_amount": round(dollar_amount, 2),
                "risk_pct": round(risk_pct, 4),
                "kelly_raw": round(kelly_raw, 4),
                "kelly_half": round(kelly_half, 4),
                "adjustments": adjustments,
                "trade_stats": stats,
                "vix": vix,
            }

            log.info(
                "[RISK] Kelly sizing %s: %d shares ($%.2f, %.2f%%) adj=%s",
                symbol, shares, dollar_amount, risk_pct * 100, adjustments,
            )
            self._log_check(symbol, "kelly", True, shares, shares,
                            f"kelly_half={kelly_half:.4f}", result)
            return result

        except Exception as e:
            log.error("[RISK] Kelly sizing failed for %s: %s — returning 0", symbol, e)
            fallback = {
                "shares": 0, "dollar_amount": 0.0, "risk_pct": 0.0,
                "kelly_raw": 0.0, "kelly_half": 0.0,
                "adjustments": ["ERROR: " + str(e)],
            }
            self._log_check(symbol, "kelly", False, 0, 0, str(e))
            return fallback

    # ══════════════════════════════════════════════════════════════════
    # 2. Daily / Weekly / Monthly Loss Limits
    # ══════════════════════════════════════════════════════════════════
    def check_loss_limits(
        self,
        equity: float,
        starting_equity_today: float,
        starting_equity_week: float,
        starting_equity_month: float,
    ) -> dict:
        """Enforce tiered loss limits — daily, weekly, monthly."""
        alerts: list[str] = []
        can_trade = True
        can_buy = True
        size_multiplier = 1.0
        reason = "all-clear"

        try:
            daily_pnl = equity - starting_equity_today
            weekly_pnl = equity - starting_equity_week
            monthly_pnl = equity - starting_equity_month

            daily_pct = daily_pnl / starting_equity_today if starting_equity_today else 0.0
            weekly_pct = weekly_pnl / starting_equity_week if starting_equity_week else 0.0
            monthly_pct = monthly_pnl / starting_equity_month if starting_equity_month else 0.0

            # Monthly: full halt
            if monthly_pct <= MONTHLY_LOSS_LIMIT:
                can_trade = False
                can_buy = False
                size_multiplier = 0.0
                reason = f"MONTHLY HALT: {monthly_pct*100:.2f}% loss"
                alerts.append(f"🚨 MONTHLY LOSS LIMIT BREACHED ({monthly_pct*100:.2f}%) — FULL HALT")

            # Weekly: halve sizes
            elif weekly_pct <= WEEKLY_LOSS_LIMIT:
                size_multiplier = WEEKLY_LOSS_SIZE_MULT
                reason = f"WEEKLY CAUTION: {weekly_pct*100:.2f}% loss"
                alerts.append(f"⚠️ Weekly loss {weekly_pct*100:.2f}% — sizes halved")

            # Daily: sell-only
            if daily_pct <= DAILY_LOSS_LIMIT and can_trade:
                can_buy = False
                reason = f"DAILY SELL-ONLY: {daily_pct*100:.2f}% loss"
                alerts.append(f"🛑 Daily loss {daily_pct*100:.2f}% — sell-only mode")

            result = {
                "can_trade": can_trade,
                "can_buy": can_buy,
                "size_multiplier": size_multiplier,
                "daily_pnl_pct": round(daily_pct, 4),
                "weekly_pnl_pct": round(weekly_pct, 4),
                "monthly_pnl_pct": round(monthly_pct, 4),
                "daily_pnl_dollar": round(daily_pnl, 2),
                "weekly_pnl_dollar": round(weekly_pnl, 2),
                "monthly_pnl_dollar": round(monthly_pnl, 2),
                "alerts": alerts,
                "reason": reason,
            }

            if alerts:
                for a in alerts:
                    log.warning("[RISK] %s", a)
            else:
                log.info(
                    "[RISK] Loss limits OK — D:%.2f%% W:%.2f%% M:%.2f%%",
                    daily_pct * 100, weekly_pct * 100, monthly_pct * 100,
                )

            self._log_check("PORTFOLIO", "loss_limits", can_trade, 0, 0, reason, result)
            return result

        except Exception as e:
            log.error("[RISK] Loss-limit check failed: %s — blocking trades", e)
            return {
                "can_trade": False, "can_buy": False, "size_multiplier": 0.0,
                "daily_pnl_pct": 0.0, "weekly_pnl_pct": 0.0, "monthly_pnl_pct": 0.0,
                "daily_pnl_dollar": 0.0, "weekly_pnl_dollar": 0.0, "monthly_pnl_dollar": 0.0,
                "alerts": [f"ERROR: {e}"], "reason": f"error: {e}",
            }

    # ══════════════════════════════════════════════════════════════════
    # 3. Correlation-Aware Sizing
    # ══════════════════════════════════════════════════════════════════
    def correlation_check(
        self,
        symbol: str,
        current_positions: list[str],
        historical_returns: dict[str, list[float]],
    ) -> dict:
        """
        Check pairwise Pearson correlation of *symbol* against every
        held position.  Reduce size when highly correlated.
        """
        try:
            if not current_positions or symbol not in historical_returns:
                return {
                    "max_correlation": 0.0,
                    "correlated_with": "",
                    "size_adjustment": 1.0,
                    "sector_exposure": {},
                    "details": [],
                }

            target_returns = np.array(historical_returns[symbol])
            max_corr = 0.0
            max_corr_sym = ""
            details: list[dict] = []

            for pos in current_positions:
                if pos == symbol:
                    continue
                pos_returns = historical_returns.get(pos)
                if pos_returns is None:
                    continue
                pos_arr = np.array(pos_returns)
                min_len = min(len(target_returns), len(pos_arr))
                if min_len < 10:
                    continue
                corr, _ = _pearsonr(target_returns[:min_len], pos_arr[:min_len])
                corr = abs(corr)
                details.append({"symbol": pos, "correlation": round(corr, 4)})
                if corr > max_corr:
                    max_corr = corr
                    max_corr_sym = pos

            size_adj = 1.0
            if max_corr >= CORRELATION_EXTREME:
                size_adj = 0.25
            elif max_corr >= CORRELATION_HIGH:
                size_adj = 0.50

            # Sector tally
            sectors: dict[str, int] = {}
            for pos in current_positions:
                s = self._get_sector(pos)
                sectors[s] = sectors.get(s, 0) + 1

            result = {
                "max_correlation": round(max_corr, 4),
                "correlated_with": max_corr_sym,
                "size_adjustment": size_adj,
                "sector_exposure": sectors,
                "details": details,
            }

            log.info(
                "[RISK] Correlation %s: max=%.2f with %s, adj=%.2f",
                symbol, max_corr, max_corr_sym, size_adj,
            )
            self._log_check(symbol, "correlation", True, 0, 0,
                            f"max_corr={max_corr:.2f} adj={size_adj}", result)
            return result

        except Exception as e:
            log.error("[RISK] Correlation check failed for %s: %s", symbol, e)
            return {
                "max_correlation": 0.0, "correlated_with": "",
                "size_adjustment": 1.0, "sector_exposure": {},
                "details": [], "error": str(e),
            }

    # ══════════════════════════════════════════════════════════════════
    # 4. Sector Exposure Cap
    # ══════════════════════════════════════════════════════════════════
    def check_sector_exposure(
        self,
        symbol: str,
        current_positions: dict[str, float],
        proposed_size: float,
    ) -> dict:
        """
        Enforce 25 % portfolio cap per sector.

        current_positions: {symbol: market_value, ...}
        proposed_size: dollar value of the proposed new position.
        """
        try:
            sector = self._get_sector(symbol)
            sector_total = 0.0
            # Handle both dict and list of Position objects
            if isinstance(current_positions, dict):
                pos_items = current_positions.items()
            elif isinstance(current_positions, list):
                pos_items = [(getattr(p, 'symbol', ''), getattr(p, 'market_value', 0)) for p in current_positions]
            else:
                pos_items = []
            for pos_sym, mkt_val in pos_items:
                if self._get_sector(pos_sym) == sector:
                    sector_total += float(mkt_val or 0)

            current_pct = sector_total / self.portfolio_value if self.portfolio_value else 0.0
            after_pct = (sector_total + proposed_size) / self.portfolio_value if self.portfolio_value else 0.0
            allowed = after_pct <= SECTOR_CAP_PCT

            remaining_room = max(0.0, (SECTOR_CAP_PCT * self.portfolio_value) - sector_total)
            max_shares = int(remaining_room / (proposed_size / max(1, 1))) if proposed_size > 0 else 0
            # Recalculate max_shares using per-share price if possible
            if proposed_size > 0 and symbol in current_positions:
                pass  # caller should clamp externally

            result = {
                "sector": sector,
                "current_exposure_pct": round(current_pct, 4),
                "after_trade_pct": round(after_pct, 4),
                "allowed": allowed,
                "remaining_room_dollars": round(remaining_room, 2),
                "max_additional_dollars": round(remaining_room, 2),
            }

            if not allowed:
                log.warning(
                    "[RISK] Sector cap BLOCKED %s (%s): %.1f%% -> %.1f%% (cap %.0f%%)",
                    symbol, sector, current_pct * 100, after_pct * 100, SECTOR_CAP_PCT * 100,
                )
            else:
                log.info(
                    "[RISK] Sector OK %s (%s): %.1f%% -> %.1f%%",
                    symbol, sector, current_pct * 100, after_pct * 100,
                )

            self._log_check(symbol, "sector_exposure", allowed, 0, 0,
                            f"{sector} {after_pct*100:.1f}%", result)
            return result

        except Exception as e:
            log.error("[RISK] Sector check failed for %s: %s — blocking", symbol, e)
            return {
                "sector": self._get_sector(symbol),
                "current_exposure_pct": 0.0,
                "after_trade_pct": 1.0,
                "allowed": False,
                "remaining_room_dollars": 0.0,
                "max_additional_dollars": 0.0,
                "error": str(e),
            }

    # ══════════════════════════════════════════════════════════════════
    # 5. Earnings Exposure
    # ══════════════════════════════════════════════════════════════════
    def check_earnings_risk(self, symbol: str, positions: list[str]) -> dict:
        """
        Reduce or block exposure around earnings dates.

        Rules:
        - ≤48 h before earnings → reduce position by 50 %
        - Day of earnings → no new buys
        - ≤30 min after earnings → no new buys (dust settling)
        """
        try:
            ticker = yf.Ticker(symbol)
            cal = ticker.calendar
            now = datetime.now(timezone.utc)

            earnings_date = None

            # yfinance returns calendar in varying formats
            if cal is not None:
                if isinstance(cal, dict):
                    ed = cal.get("Earnings Date")
                    if ed is not None:
                        if isinstance(ed, list) and len(ed) > 0:
                            earnings_date = ed[0]
                        elif isinstance(ed, datetime):
                            earnings_date = ed
                elif hasattr(cal, "iloc"):
                    try:
                        ed = cal.iloc[0, 0]
                        if isinstance(ed, datetime):
                            earnings_date = ed
                    except Exception:
                        pass

            if earnings_date is None:
                result = {
                    "has_earnings_soon": False,
                    "earnings_date": None,
                    "hours_until": None,
                    "action": "none",
                    "size_multiplier": 1.0,
                }
                log.info("[RISK] No upcoming earnings found for %s", symbol)
                self._log_check(symbol, "earnings", True, 0, 0, "no-earnings", result)
                return result

            # Make timezone-aware if needed
            if earnings_date.tzinfo is None:
                earnings_date = earnings_date.replace(tzinfo=timezone.utc)

            hours_until = (earnings_date - now).total_seconds() / 3600.0

            action = "none"
            size_mult = 1.0

            if hours_until <= 0 and abs(hours_until) <= (EARNINGS_COOLDOWN_MIN / 60.0):
                action = "block-new-buys-cooldown"
                size_mult = 0.0
            elif 0 < hours_until <= EARNINGS_WINDOW_HOURS:
                if hours_until <= 24:
                    action = "block-new-buys-earnings-day"
                    size_mult = 0.0
                else:
                    action = "reduce-50pct"
                    size_mult = 0.5

            has_soon = action != "none"

            result = {
                "has_earnings_soon": has_soon,
                "earnings_date": str(earnings_date),
                "hours_until": round(hours_until, 2),
                "action": action,
                "size_multiplier": size_mult,
            }

            if has_soon:
                log.warning(
                    "[RISK] Earnings risk %s: %s in %.1f hrs — action=%s",
                    symbol, earnings_date, hours_until, action,
                )
            else:
                log.info("[RISK] Earnings clear for %s (%.1f hrs away)", symbol, hours_until)

            self._log_check(symbol, "earnings", not has_soon or size_mult > 0,
                            0, 0, action, result)
            return result

        except Exception as e:
            log.error("[RISK] Earnings check failed for %s: %s — assuming safe", symbol, e)
            return {
                "has_earnings_soon": False, "earnings_date": None,
                "hours_until": None, "action": "error-safe-default",
                "size_multiplier": 1.0, "error": str(e),
            }

    # ══════════════════════════════════════════════════════════════════
    # 6. Master Approval Gate
    # ══════════════════════════════════════════════════════════════════
    def approve_trade(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        conviction: float,
        positions: dict[str, float],
        equity: float,
        atr: float = 0.0,
        historical_returns: Optional[dict[str, list[float]]] = None,
        starting_equity_today: Optional[float] = None,
        starting_equity_week: Optional[float] = None,
        starting_equity_month: Optional[float] = None,
    ) -> dict:
        """
        Master approval gate — runs ALL risk checks and returns a
        single go / no-go decision with the (possibly reduced) qty.
        """
        self.portfolio_value = equity  # refresh
        rejections: list[str] = []
        adj_list: list[str] = []
        adjusted_qty = qty

        # Default equity anchors to current equity when not provided
        s_today = starting_equity_today or equity
        s_week = starting_equity_week or equity
        s_month = starting_equity_month or equity

        # ── Loss limits ──────────────────────────────────────────────
        loss = self.check_loss_limits(equity, s_today, s_week, s_month)
        if not loss["can_trade"]:
            rejections.append(f"loss-limit-halt: {loss['reason']}")
            adjusted_qty = 0
        elif side.lower() == "buy" and not loss["can_buy"]:
            rejections.append(f"loss-limit-sell-only: {loss['reason']}")
            adjusted_qty = 0
        elif loss["size_multiplier"] < 1.0:
            adjusted_qty = max(1, int(adjusted_qty * loss["size_multiplier"]))
            adj_list.append(f"loss-limit-size-mult={loss['size_multiplier']}")

        # ── Kelly sizing (buy only) ──────────────────────────────────
        kelly: dict = {}
        if side.lower() == "buy" and adjusted_qty > 0:
            kelly = self.kelly_position_size(symbol, conviction, price, atr)
            if kelly["shares"] < adjusted_qty:
                adjusted_qty = kelly["shares"]
                adj_list.append(f"kelly-capped-to-{kelly['shares']}")

        # ── Correlation ──────────────────────────────────────────────
        corr: dict = {}
        if side.lower() == "buy" and adjusted_qty > 0:
            # positions can be a list of Position objects or a dict
            if isinstance(positions, dict):
                pos_syms = list(positions.keys())
            elif isinstance(positions, list):
                pos_syms = [getattr(p, 'symbol', str(p)) for p in positions]
            else:
                pos_syms = []
            h_ret = historical_returns or {}
            corr = self.correlation_check(symbol, pos_syms, h_ret)
            if corr["size_adjustment"] < 1.0:
                adjusted_qty = max(1, int(adjusted_qty * corr["size_adjustment"]))
                adj_list.append(
                    f"correlation-adj={corr['size_adjustment']} "
                    f"(vs {corr['correlated_with']})"
                )

        # ── Sector exposure ──────────────────────────────────────────
        sector: dict = {}
        if side.lower() == "buy" and adjusted_qty > 0:
            proposed_dollar = adjusted_qty * price
            sector = self.check_sector_exposure(symbol, positions, proposed_dollar)
            if not sector["allowed"]:
                # Shrink to fit remaining room
                if sector["remaining_room_dollars"] > 0 and price > 0:
                    max_shares = int(sector["remaining_room_dollars"] / price)
                    if max_shares > 0:
                        adjusted_qty = min(adjusted_qty, max_shares)
                        adj_list.append(f"sector-capped-to-{max_shares}")
                    else:
                        rejections.append(f"sector-cap-{sector['sector']}")
                        adjusted_qty = 0
                else:
                    rejections.append(f"sector-cap-{sector['sector']}")
                    adjusted_qty = 0

        # ── Earnings ─────────────────────────────────────────────────
        earnings: dict = {}
        if side.lower() == "buy" and adjusted_qty > 0:
            if isinstance(positions, dict):
                pos_syms = list(positions.keys())
            elif isinstance(positions, list):
                pos_syms = [getattr(p, 'symbol', str(p)) for p in positions]
            else:
                pos_syms = []
            earnings = self.check_earnings_risk(symbol, pos_syms)
            if earnings["size_multiplier"] == 0.0:
                rejections.append(f"earnings-block: {earnings['action']}")
                adjusted_qty = 0
            elif earnings["size_multiplier"] < 1.0:
                adjusted_qty = max(1, int(adjusted_qty * earnings["size_multiplier"]))
                adj_list.append(f"earnings-reduce={earnings['size_multiplier']}")

        # ── Final decision ───────────────────────────────────────────
        approved = adjusted_qty > 0 and len(rejections) == 0

        result = {
            "approved": approved,
            "adjusted_qty": adjusted_qty,
            "original_qty": qty,
            "side": side,
            "symbol": symbol,
            "checks": {
                "kelly": kelly,
                "loss_limits": loss,
                "correlation": corr,
                "sector": sector,
                "earnings": earnings,
            },
            "rejections": rejections,
            "adjustments": adj_list,
        }

        status = "APPROVED" if approved else "REJECTED"
        log.info(
            "[RISK] Trade %s %s %s %d→%d @ $%.2f | %s | rej=%s adj=%s",
            status, side.upper(), symbol, qty, adjusted_qty, price,
            status, rejections, adj_list,
        )
        self._log_check(symbol, "master_gate", approved, qty, adjusted_qty,
                        f"{status}: {rejections or 'clean'}", result)

        return result
