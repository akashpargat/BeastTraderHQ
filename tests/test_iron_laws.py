"""
Beast v2.0 — Tests for Iron Laws & Policy Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run: python -m pytest tests/ -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from models import (
    Position, TradeProposal, OrderSide, MarketData,
    Strategy, Regime, LawPriority
)
from iron_laws import (
    law_1_never_sell_at_loss, law_2_limit_orders_only,
    law_5_named_strategy, law_8_cooldown, law_10_confidence_check,
    law_11_earnings_check, law_13_strategy_stock_match,
    check_kill_switch, check_consecutive_losses,
    check_max_day_trades, check_position_max_loss,
    validate_entry, is_approved, get_rejections
)


# ── Iron Law Tests ─────────────────────────────────────

class TestIronLaws:

    def test_law_1_blocks_selling_red_position(self):
        pos = Position("AMZN", 15, 262.63, 260.00, 3900, -39.45, -0.015)
        result = law_1_never_sell_at_loss(pos, OrderSide.SELL)
        assert not result.approved
        assert "Iron Law 1" in result.reason

    def test_law_1_allows_selling_green_position(self):
        pos = Position("AMZN", 15, 262.63, 265.00, 3975, 35.55, 0.009)
        result = law_1_never_sell_at_loss(pos, OrderSide.SELL)
        assert result.approved

    def test_law_1_allows_buying_always(self):
        pos = Position("AMZN", 15, 262.63, 260.00, 3900, -39.45, -0.015)
        result = law_1_never_sell_at_loss(pos, OrderSide.BUY)
        assert result.approved

    def test_law_2_rejects_market_orders(self):
        result = law_2_limit_orders_only("market")
        assert not result.approved
        assert "LIMIT ORDERS ONLY" in result.reason

    def test_law_2_accepts_limit_orders(self):
        result = law_2_limit_orders_only("limit")
        assert result.approved

    def test_law_5_rejects_fomo(self):
        result = law_5_named_strategy("FOMO")
        assert not result.approved

    def test_law_5_rejects_empty(self):
        result = law_5_named_strategy("")
        assert not result.approved

    def test_law_5_accepts_valid_strategy(self):
        result = law_5_named_strategy("A")
        assert result.approved

    def test_law_8_blocks_quick_reentry(self):
        last_sells = {"AMZN": datetime.now() - timedelta(seconds=60)}
        result = law_8_cooldown("AMZN", last_sells)
        assert not result.approved
        assert "Cooldown" in result.reason

    def test_law_8_allows_after_cooldown(self):
        last_sells = {"AMZN": datetime.now() - timedelta(seconds=400)}
        result = law_8_cooldown("AMZN", last_sells)
        assert result.approved

    def test_law_10_rejects_low_confidence(self):
        result = law_10_confidence_check(0.25)
        assert not result.approved
        assert "doubt" in result.reason.lower() or "Confidence" in result.reason

    def test_law_10_accepts_high_confidence(self):
        result = law_10_confidence_check(0.65)
        assert result.approved

    def test_law_11_blocks_earnings_day(self):
        dates = {"GOOGL": datetime.now() + timedelta(hours=6)}
        result = law_11_earnings_check("GOOGL", dates)
        assert not result.approved
        assert "earnings" in result.reason.lower()

    def test_law_11_allows_no_earnings(self):
        result = law_11_earnings_check("AMZN", {})
        assert result.approved

    def test_law_13_blocks_quick_flip_in_choppy(self):
        result = law_13_strategy_stock_match("D", "COIN", Regime.CHOPPY)
        assert not result.approved
        assert "TOXIC" in result.reason

    def test_law_13_allows_orb_in_bull(self):
        result = law_13_strategy_stock_match("A", "TSLA", Regime.BULL)
        assert result.approved


# ── Safety Priority Tests ──────────────────────────────

class TestSafetyPriority:

    def test_kill_switch_halts_trading(self):
        result = check_kill_switch(-501.0)
        assert not result.approved
        assert result.priority == LawPriority.SAFETY

    def test_kill_switch_allows_normal(self):
        result = check_kill_switch(-100.0)
        assert result.approved

    def test_consecutive_losses_stops(self):
        result = check_consecutive_losses(2)
        assert not result.approved
        assert result.priority == LawPriority.SAFETY

    def test_max_day_trades_blocks(self):
        result = check_max_day_trades(3)
        assert not result.approved
        assert result.priority == LawPriority.REGULATORY

    def test_risk_cap_alerts_but_holds(self):
        """P3 risk cap alerts user but HOLDS position (Iron Law 1 is absolute)."""
        pos = Position("PLTR", 50, 142.0, 132.0, 6600, -500.0, -0.07)
        result = check_position_max_loss(pos)
        assert result.approved  # HOLDS — Iron Law 1 is absolute
        assert "ALERT" in result.reason  # But alerts the user


# ── Full Validation Tests ──────────────────────────────

class TestFullValidation:

    def _make_proposal(self, symbol="AMZN", confidence=0.65):
        return TradeProposal(
            symbol=symbol, side=OrderSide.BUY, qty=10,
            limit_price=262.0, strategy=Strategy.BLUE_CHIP_REVERSION,
            confidence=confidence, reason="test"
        )

    def _make_market(self, regime=Regime.BULL):
        return MarketData(
            spy_price=714.0, spy_change_pct=0.008,
            regime=regime, account_equity=100000,
        )

    def test_valid_entry_passes_all_laws(self):
        results = validate_entry(
            proposal=self._make_proposal(),
            market=self._make_market(),
            positions=[],
            daily_pnl=0, consecutive_losses=0,
            active_day_trades=0, last_sell_times={},
            earnings_dates={},
            has_technicals=True, has_sentiment=True,
        )
        # Filter out trading window (may fail outside market hours)
        non_window = [r for r in results if r.law != "TRADING_WINDOW"]
        assert all(r.approved for r in non_window)

    def test_low_confidence_rejected(self):
        results = validate_entry(
            proposal=self._make_proposal(confidence=0.20),
            market=self._make_market(),
            positions=[], daily_pnl=0, consecutive_losses=0,
            active_day_trades=0, last_sell_times={},
            earnings_dates={}, has_technicals=True, has_sentiment=True,
        )
        rejections = get_rejections(results)
        assert any("Confidence" in r.reason for r in rejections)

    def test_no_technicals_rejected(self):
        results = validate_entry(
            proposal=self._make_proposal(),
            market=self._make_market(),
            positions=[], daily_pnl=0, consecutive_losses=0,
            active_day_trades=0, last_sell_times={},
            earnings_dates={}, has_technicals=False, has_sentiment=True,
        )
        rejections = get_rejections(results)
        assert any("Law 3" in r.reason for r in rejections)

    def test_no_sentiment_rejected(self):
        results = validate_entry(
            proposal=self._make_proposal(),
            market=self._make_market(),
            positions=[], daily_pnl=0, consecutive_losses=0,
            active_day_trades=0, last_sell_times={},
            earnings_dates={}, has_technicals=True, has_sentiment=False,
        )
        rejections = get_rejections(results)
        assert any("Law 4" in r.reason for r in rejections)


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
