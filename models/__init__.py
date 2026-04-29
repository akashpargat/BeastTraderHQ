"""
Beast v2.0 — Data Models
All dataclasses used across the system. Single source of truth for types.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ── Enums ──────────────────────────────────────────────

class Regime(Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    CHOPPY = "CHOPPY"
    RED_ALERT = "RED_ALERT"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderState(Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    ACCEPTED = "accepted"
    PARTIAL_FILL = "partial_fill"
    FILLED = "filled"
    CANCELED = "canceled"
    FAILED = "failed"


class SignalType(Enum):
    STRONG_BUY = "STRONG_BUY"    # confidence > 60%
    BUY = "BUY"                  # confidence 40-60%
    HOLD = "HOLD"                # no action
    SELL = "SELL"                 # exit signal
    NO_TRADE = "NO_TRADE"        # confidence < 40%


class Strategy(Enum):
    ORB_BREAKOUT = "A"
    VWAP_BOUNCE = "B"
    GAP_AND_GO = "C"
    QUICK_FLIP = "D"
    TOUCH_AND_TURN = "E"
    FAIR_VALUE_GAP = "F"
    RED_TO_GREEN = "G"
    FIVE_MIN_SCALP = "H"
    BLUE_CHIP_REVERSION = "I"
    SMA_TREND_FOLLOW = "J"
    SECTOR_MOMENTUM = "K"


class LawPriority(Enum):
    """Iron Law priority hierarchy. Higher number = higher priority."""
    PROFIT = 1       # Strategy signals, entry/exit preferences
    STRATEGY = 2     # Iron Laws 1-13
    RISK_CAP = 3     # Per-position max unrealized loss
    REGULATORY = 4   # PDT compliance, max positions
    SAFETY = 5       # Account survival, kill switch


# ── Market Data ────────────────────────────────────────

@dataclass
class Quote:
    symbol: str
    bid: float
    ask: float
    last: float
    timestamp: datetime
    volume: int = 0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    def is_fresh(self, ttl_seconds: int = 10) -> bool:
        age = (datetime.now() - self.timestamp).total_seconds()
        return age <= ttl_seconds


@dataclass
class Position:
    symbol: str
    qty: int
    avg_entry: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_pl_pct: float
    side: str = "long"
    qty_available: int = 0  # shares NOT held by open orders

    @property
    def is_green(self) -> bool:
        return self.unrealized_pl > 0

    @property
    def is_red(self) -> bool:
        return self.unrealized_pl < 0


@dataclass
class MarketData:
    """Aggregated market snapshot with freshness tracking."""
    spy_price: float = 0.0
    spy_change_pct: float = 0.0
    qqq_price: float = 0.0
    vix: float = 0.0
    regime: Regime = Regime.CHOPPY
    positions: list[Position] = field(default_factory=list)
    account_equity: float = 0.0
    buying_power: float = 0.0
    day_trade_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    def is_fresh(self, ttl_seconds: int = 30) -> bool:
        age = (datetime.now() - self.timestamp).total_seconds()
        return age <= ttl_seconds


# ── Technical Signals ──────────────────────────────────

@dataclass
class TechnicalSignals:
    symbol: str
    rsi: float = 50.0
    macd: float = 0.0
    macd_histogram: float = 0.0
    macd_signal: float = 0.0
    vwap: float = 0.0
    price_vs_vwap: float = 0.0  # positive = above VWAP
    bb_upper: float = 0.0
    bb_mid: float = 0.0
    bb_lower: float = 0.0
    ema_9: float = 0.0
    ema_21: float = 0.0
    sma_20: float = 0.0
    sma_200: float = 0.0
    volume_ratio: float = 1.0  # current vs 20-bar avg
    orb_high: float = 0.0
    orb_low: float = 0.0
    confluence_score: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def is_oversold(self) -> bool:
        return self.rsi < 30

    @property
    def is_overbought(self) -> bool:
        return self.rsi > 70

    @property
    def above_vwap(self) -> bool:
        return self.price_vs_vwap > 0

    def is_fresh(self, ttl_seconds: int = 30) -> bool:
        age = (datetime.now() - self.timestamp).total_seconds()
        return age <= ttl_seconds


# ── Sentiment ──────────────────────────────────────────

@dataclass
class SentimentScore:
    symbol: str
    yahoo_score: int = 0        # -5 to +5
    reddit_score: int = 0       # -5 to +5
    analyst_score: int = 0      # -5 to +5
    news_headline: str = ""
    total_score: int = 0        # -15 to +15
    timestamp: datetime = field(default_factory=datetime.now)

    def is_fresh(self, ttl_seconds: int = 900) -> bool:  # 15 min TTL
        age = (datetime.now() - self.timestamp).total_seconds()
        return age <= ttl_seconds


# ── Confidence & Decisions ─────────────────────────────

@dataclass
class StrategyScore:
    strategy: Strategy
    score: float = 0.0          # 0.0 to 1.0
    reason: str = ""


@dataclass
class ConfidenceResult:
    symbol: str
    overall_confidence: float = 0.0  # 0.0 to 1.0
    signal: SignalType = SignalType.NO_TRADE
    best_strategy: Optional[Strategy] = None
    strategy_scores: list[StrategyScore] = field(default_factory=list)
    technical: Optional[TechnicalSignals] = None
    sentiment: Optional[SentimentScore] = None
    bull_case: str = ""
    bear_case: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TradeProposal:
    """What the signal generator wants to do."""
    symbol: str
    side: OrderSide
    qty: int
    limit_price: float
    strategy: Strategy
    confidence: float
    reason: str
    is_scalp: bool = True       # vs runner
    target_price: float = 0.0
    stop_price: float = 0.0


@dataclass
class PolicyVerdict:
    """What the policy engine decided."""
    approved: bool
    proposal: Optional[TradeProposal] = None
    rejection_reason: str = ""
    law_violated: str = ""
    priority: LawPriority = LawPriority.PROFIT


@dataclass
class OrderRecord:
    """Tracks an order through its lifecycle."""
    id: str = ""                # Alpaca order ID
    client_id: str = ""         # Our internal ID
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    qty: int = 0
    filled_qty: int = 0
    limit_price: float = 0.0
    filled_avg_price: float = 0.0
    state: OrderState = OrderState.PROPOSED
    strategy: Strategy = Strategy.ORB_BREAKOUT
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    error: str = ""


@dataclass
class TradeJournalEntry:
    """Complete record of a trade for the journal."""
    symbol: str
    side: str
    qty: int
    entry_price: float
    exit_price: float = 0.0
    pnl: float = 0.0
    strategy: str = ""
    regime: str = ""
    confidence: float = 0.0
    hold_time_seconds: int = 0
    grade: str = ""             # A, B, C, D, F
    notes: str = ""
    iron_law_violations: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
