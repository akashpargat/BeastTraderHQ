"""
Beast v3.0 — Remote AI Client
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Calls the work laptop's AI API server via Cloudflare Tunnel.
Falls back to deterministic mode if laptop is offline.

V3 DIFFERENCE FROM V2:
  v2: Calls local copilot-api directly
  v3: Calls work laptop's Flask API via HTTP tunnel

Same interface — all existing code works unchanged.

SETUP:
  1. Work laptop runs: python ai_api_server.py (port 5555)
  2. Work laptop runs: cloudflared tunnel (exposes port 5555)
  3. Set AI_API_URL in .env to the tunnel URL
  OR for local testing: AI_API_URL=http://localhost:5555
"""
import os
import logging
import requests
from datetime import datetime

log = logging.getLogger('Beast.RemoteAI')

AI_API_URL = os.getenv('AI_API_URL', 'http://localhost:5555')
AI_API_KEY = os.getenv('AI_API_KEY', 'beast-v3-sk-7f3a9e2b4d1c8f5e6a0b3d9c')
AI_TIMEOUT = 30
AI_HEADERS = {'X-API-Key': AI_API_KEY, 'Content-Type': 'application/json'}


class AIBrain:
    """Remote AI client. Same interface as v2 but calls laptop via HTTP."""

    def __init__(self):
        self._available = False
        self._check_connection()

    def _check_connection(self):
        try:
            resp = requests.get(f"{AI_API_URL}/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                self._available = data.get('ai_available', False)
                if self._available:
                    log.info(f"🧠 Remote AI Brain ONLINE ({AI_API_URL})")
                else:
                    log.warning("🧠 Remote AI reachable but AI unavailable")
            else:
                log.warning(f"🧠 Remote AI returned {resp.status_code}")
        except Exception:
            log.warning(f"🧠 Remote AI OFFLINE — deterministic mode")
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def analyze_stock(self, symbol: str, data: dict) -> dict:
        if not self._available:
            return self._deterministic_fallback(symbol, data)
        try:
            data['symbol'] = symbol
            resp = requests.post(f"{AI_API_URL}/analyze", json=data, headers=AI_HEADERS, timeout=AI_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            log.warning(f"Remote AI failed for {symbol}: {e}")
        return self._deterministic_fallback(symbol, data)

    def bull_bear_debate(self, symbol: str, data: dict) -> dict:
        if not self._available:
            return {'bull_case': '', 'bear_case': '', 'verdict': 'HOLD',
                    'bull_confidence': 50, 'bear_confidence': 50}
        try:
            data['symbol'] = symbol
            resp = requests.post(f"{AI_API_URL}/debate", json=data, headers=AI_HEADERS, timeout=AI_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
        return {'bull_case': '', 'bear_case': '', 'verdict': 'HOLD',
                'bull_confidence': 50, 'bear_confidence': 50}

    def morning_briefing(self, market_data: dict, positions: list,
                          sentiment: dict) -> str:
        if not self._available:
            return "AI offline — deterministic mode"
        try:
            resp = requests.post(f"{AI_API_URL}/briefing", json={
                'market': market_data, 'positions': positions, 'sentiment': sentiment
            }, headers=AI_HEADERS, timeout=AI_TIMEOUT)
            if resp.status_code == 200:
                return resp.json().get('briefing', '')
        except:
            pass
        return "AI briefing unavailable"

    def earnings_play_analysis(self, symbol: str, data: dict) -> dict:
        return self.analyze_stock(symbol, data)

    def trade_journal_entry(self, trade: dict) -> str:
        if not self._available:
            pnl = trade.get('pnl', 0)
            grade = 'A' if pnl > 50 else 'B' if pnl > 0 else 'C' if pnl > -10 else 'D'
            return f"GRADE: {grade} — (AI offline)"
        result = self.analyze_stock(trade.get('symbol', '?'), trade)
        return result.get('reasoning', 'No analysis')

    def explain_confidence(self, symbol, confidence_result) -> str:
        if not self._available:
            return f"{symbol}: {confidence_result.overall:.0f}%"
        data = {'symbol': symbol, 'confidence': confidence_result.overall,
                'action': confidence_result.action.value}
        result = self.analyze_stock(symbol, data)
        return result.get('reasoning', f"{symbol}: {confidence_result.overall:.0f}%")

    def reconnect(self):
        self._check_connection()

    def _deterministic_fallback(self, symbol: str, data: dict) -> dict:
        """When AI is offline, use simple rules."""
        rsi = data.get('rsi', 50)
        holding = data.get('holding', False)
        pl = data.get('unrealized_pl', 0)

        if holding and pl < 0:
            action, reason, conf = 'HOLD', f'Loss ${pl:+.2f}. Iron Law 1.', 70
        elif rsi < 30:
            action = 'BUY' if not holding else 'HOLD'
            reason, conf = f'RSI {rsi} oversold — Akash Method', 65
        elif rsi > 70:
            action, reason, conf = 'HOLD', f'RSI {rsi} overbought', 40
        else:
            action, reason, conf = 'HOLD', f'RSI {rsi} neutral', 50

        return {
            'action': action, 'confidence': conf, 'strategy': 'NONE',
            'position_type': 'NONE', 'entry_price': 0, 'scalp_target': 0,
            'runner_target': 0, 'stop_price': 0,
            'reasoning': f'[DETERMINISTIC] {reason}',
            'risks': ['AI offline — rule-based fallback'],
        }
