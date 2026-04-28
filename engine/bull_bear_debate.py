"""
Beast v2.0 — Bull/Bear Debate (Claude AI — OPTIONAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Uses Claude API for AI-powered bull/bear debate.
This is NEVER in the critical path. If Claude is down,
the bot continues with deterministic signals only.
"""
import logging
import json
from datetime import datetime
from typing import Optional

from models import TechnicalSignals, SentimentScore, Regime

log = logging.getLogger('Beast.BullBearDebate')


class BullBearDebate:
    """AI-powered bull/bear debate using Claude. Non-blocking, optional."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.client = None
        self._available = False

        if api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=api_key)
                self._available = True
                log.info("🧠 Claude AI connected for bull/bear debate")
            except Exception as e:
                log.warning(f"Claude not available: {e}. Continuing without AI debate.")

    @property
    def is_available(self) -> bool:
        return self._available and self.client is not None

    def debate(self, symbol: str, technicals: TechnicalSignals,
               sentiment: SentimentScore, regime: Regime,
               price: float = 0) -> tuple[str, str, float]:
        """Run bull/bear debate. Returns (bull_case, bear_case, bull_confidence 0-1).
        Returns defaults if Claude is unavailable (degraded mode)."""

        if not self.is_available:
            return "", "", 0.5  # Neutral if no AI

        context = self._build_context(symbol, technicals, sentiment, regime, price)

        try:
            bull_case = self._ask_agent("bull", symbol, context)
            bear_case = self._ask_agent("bear", symbol, context)
            confidence = self._synthesize(bull_case, bear_case)
            return bull_case, bear_case, confidence
        except Exception as e:
            log.warning(f"Debate failed for {symbol}: {e}. Using neutral.")
            return "", "", 0.5

    def _build_context(self, symbol, tech, sent, regime, price) -> str:
        return (
            f"Stock: {symbol} at ${price:.2f}\n"
            f"Regime: {regime.value}\n"
            f"RSI: {tech.rsi}, MACD: {tech.macd} (hist: {tech.macd_histogram})\n"
            f"VWAP: ${tech.vwap:.2f} ({'above' if tech.above_vwap else 'below'})\n"
            f"Bollinger: ${tech.bb_lower:.2f} / ${tech.bb_mid:.2f} / ${tech.bb_upper:.2f}\n"
            f"EMA 9: ${tech.ema_9:.2f}, EMA 21: ${tech.ema_21:.2f}\n"
            f"Volume ratio: {tech.volume_ratio}x\n"
            f"Confluence score: {tech.confluence_score}/10\n"
            f"Yahoo sentiment: {sent.yahoo_score}/5\n"
            f"Reddit sentiment: {sent.reddit_score}/5\n"
            f"Analyst sentiment: {sent.analyst_score}/5\n"
        )

    def _ask_agent(self, role: str, symbol: str, context: str) -> str:
        prompts = {
            "bull": (
                f"You are a BULL analyst. Argue FOR buying {symbol} right now. "
                f"Cite specific data points from the context. Be concise (3-4 sentences max). "
                f"If the data truly doesn't support buying, say so honestly.\n\n{context}"
            ),
            "bear": (
                f"You are a BEAR analyst. Argue AGAINST buying {symbol} right now. "
                f"Cite specific risks and data points. Be concise (3-4 sentences max). "
                f"If the data truly supports buying, acknowledge it honestly.\n\n{context}"
            ),
        }

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            temperature=0.2,
            messages=[{"role": "user", "content": prompts[role]}],
        )
        return response.content[0].text.strip()

    def _synthesize(self, bull_case: str, bear_case: str) -> float:
        """Ask Claude to weigh bull vs bear and give confidence 0-1."""
        if not self.is_available:
            return 0.5

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=50,
                temperature=0.1,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Bull case: {bull_case}\n\n"
                        f"Bear case: {bear_case}\n\n"
                        f"On a scale of 0.0 (strong sell) to 1.0 (strong buy), "
                        f"what is the appropriate confidence level? "
                        f"Reply with ONLY a number like 0.65"
                    ),
                }],
            )
            text = response.content[0].text.strip()
            return float(text)
        except:
            return 0.5
