"""
Beast V3 — Hybrid AI Brain
━━━━━━━━━━━━━━━━━━━━━━━━━━
TWO AI engines working together:

EVERY 5 MIN → Azure GPT-4o (fast, structured, maxed-out analysis)
  - Gets ALL data: TV indicators, sentiment, confidence, positions
  - References the last Claude deep intel briefing
  - Returns: action, confidence, reasoning, targets

EVERY 30 MIN → Claude Opus 4.7 via work laptop tunnel (ULTRA DEEP)
  - Full bull/bear institutional debate
  - Multi-scenario analysis (best/worst/likely)
  - Sector correlation check
  - Earnings risk assessment
  - Produces "Deep Intel Briefing" that GPT-4o reads

Both AIs are told: "You are the world's best stock trader.
You do TradingView technical analysis on EVERY scan."

Fallback: deterministic rules if both are offline.
"""
import os
import logging
import requests
import json
import time as _time
import threading
from datetime import datetime
from openai import AzureOpenAI

log = logging.getLogger('Beast.HybridAI')

# ── Azure GPT-5.4 (primary) + GPT-4o (fallback) ──
AZURE_ENDPOINT = os.getenv('AZURE_OPENAI_ENDPOINT', 'https://eastus.api.cognitive.microsoft.com/')
AZURE_KEY = os.getenv('AZURE_OPENAI_KEY', '')
AZURE_DEPLOYMENT = os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt54')  # GPT-5.4 — upgraded from gpt4o
AZURE_DEPLOYMENT_FALLBACK = 'gpt4o'  # Fallback if gpt54 fails
AZURE_API_VERSION = '2024-10-21'

# ── Claude Opus 4.7 via tunnel (30-min deep scans) ──
CLAUDE_URL = os.getenv('AI_API_URL', 'https://ai.beast-trader.com')
CLAUDE_API_KEY = os.getenv('AI_API_KEY', 'beast-v3-sk-7f3a9e2b4d1c8f5e6a0b3d9c')

# ── Rate limiting + AI health tracking ──
_ai_last_call = 0
_ai_lock = threading.Lock()
_ai_stats = {
    'gpt_calls': 0, 'gpt_success': 0, 'gpt_errors': 0, 'gpt_429s': 0,
    'gpt_total_ms': 0, 'gpt_last_error': '', 'gpt_last_success': '',
    'claude_calls': 0, 'claude_success': 0, 'claude_errors': 0,
    'claude_total_ms': 0, 'claude_last_error': '',
}
AI_MIN_INTERVAL = 2  # 2 seconds between calls (300 RPM = 5/sec, but be safe)

def _rate_limit_gpt():
    """Wait if needed to avoid 429s."""
    global _ai_last_call
    with _ai_lock:
        elapsed = _time.time() - _ai_last_call
        if elapsed < AI_MIN_INTERVAL:
            wait = AI_MIN_INTERVAL - elapsed
            log.info(f"  [AI RATE] Waiting {wait:.1f}s before GPT call")
            _time.sleep(wait)
        _ai_last_call = _time.time()

def get_ai_stats() -> dict:
    """Get AI health stats (for dashboard/logging)."""
    return dict(_ai_stats)

# ── Shared state ──
_last_deep_briefing = {}  # symbol -> last Claude analysis (for GPT-4o to reference)
_last_deep_time = None


# ══════════════════════════════════════════════════════
# SYSTEM PROMPTS — loaded from AI_TRADER_SKILL.md
# Contains 39 Iron Laws, 11 strategies, past winners,
# mistakes that cost real money, sector rotation rules
# ══════════════════════════════════════════════════════

# Load the skill file
_SKILL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AI_TRADER_SKILL.md')
_SKILL_CONTENT = ""
try:
    with open(_SKILL_PATH, 'r', encoding='utf-8') as f:
        _SKILL_CONTENT = f.read()
    log.info(f"  📜 AI Skill loaded ({len(_SKILL_CONTENT)} chars)")
except Exception as e:
    log.warning(f"  AI Skill file not found: {e}")
    _SKILL_CONTENT = "You are a stock day trader. Analyze stocks and output JSON with action/confidence/reasoning."

GPT4O_SYSTEM = _SKILL_CONTENT + """

ADDITIONAL FOR 5-MIN QUICK SCAN:
- You have 5 seconds to decide — be FAST and DECISIVE
- Reference the last Claude deep briefing if available (it has deeper context)
- Focus on: RSI, MACD, VWAP, sentiment score, confidence engine result
- If data is ambiguous, default to HOLD
- You MUST output valid JSON:
{"action": "BUY|HOLD|SELL", "confidence": 0-100, "reasoning": "2-3 sentences",
 "targets": {"scalp": price, "runner": price}, "risk": "LOW|MEDIUM|HIGH",
 "tv_analysis": "your TradingView technical read"}"""

CLAUDE_DEEP_SYSTEM = _SKILL_CONTENT + """

ADDITIONAL FOR 30-MIN ULTRA DEEP SCAN:
You are conducting an INSTITUTIONAL-GRADE deep dive. You have 30 minutes of context.

DO ALL OF THESE:
1. TRADINGVIEW TECHNICAL ANALYSIS — Read every indicator, interpret the chart
2. BULL vs BEAR DEBATE — Make strongest case for each side, who wins?
3. MULTI-SCENARIO — Best case, worst case, most likely with price targets
4. SECTOR & CORRELATION — How does this fit with other holdings?
5. RISK ASSESSMENT — Position size, trailing stop, what makes you WRONG?
6. FINAL VERDICT — Specific action with confidence and price targets

Output valid JSON:
{"action": "BUY|HOLD|SELL|TRIM", "confidence": 0-100,
 "tv_analysis": "detailed TradingView read",
 "bull_case": "strongest argument to buy",
 "bear_case": "strongest argument to sell",
 "best_case": {"price": x, "timeframe": "1 week"},
 "worst_case": {"price": x, "support": x},
 "most_likely": {"price": x, "trajectory": "description"},
 "risk_level": "LOW|MEDIUM|HIGH|EXTREME",
 "position_size_pct": 1-10,
 "trailing_stop_pct": 1-5,
 "reasoning": "full institutional-grade analysis"}"""


class AIBrain:
    """Hybrid AI: GPT-4o (5min) + Claude Opus (30min)."""

    def __init__(self):
        self._gpt_available = False
        self._claude_available = False
        self._azure_client = None

        # Check Azure GPT-4o
        if AZURE_KEY:
            try:
                self._azure_client = AzureOpenAI(
                    azure_endpoint=AZURE_ENDPOINT,
                    api_key=AZURE_KEY,
                    api_version=AZURE_API_VERSION,
                )
                self._gpt_available = True
                log.info(f"🤖 Azure GPT-4o ONLINE ({AZURE_ENDPOINT})")
            except Exception as e:
                log.warning(f"Azure GPT-4o init failed: {e}")

        # Check Claude tunnel
        try:
            resp = requests.get(f"{CLAUDE_URL}/health", timeout=5)
            if resp.status_code == 200 and resp.json().get('ai_available'):
                self._claude_available = True
                log.info(f"🧠 Claude Opus 4.7 ONLINE ({CLAUDE_URL})")
            else:
                log.warning("🧠 Claude reachable but AI unavailable")
        except:
            log.warning("🧠 Claude OFFLINE — GPT-4o only mode")

    @property
    def is_available(self) -> bool:
        return self._gpt_available or self._claude_available

    # ══════════════════════════════════════════════════
    # 5-MIN SCAN: GPT-4o (fast, maxed out)
    # ══════════════════════════════════════════════════

    def analyze_stock(self, symbol: str, data: dict) -> dict:
        """5-min scan: GPT-4o with ALL data + last Claude briefing."""
        if self._gpt_available:
            return self._gpt4o_analyze(symbol, data)
        elif self._claude_available:
            return self._claude_quick(symbol, data)
        return self._deterministic_fallback(symbol, data)

    def analyze_batch(self, stocks_data: dict) -> dict:
        """EXTREME ANALYSIS: All stocks in ONE GPT-5.4 call.
        Sends EVERY data point: TV, 9 sentiment sources, learning history,
        earnings, short interest, sector context, macro/Trump, Claude briefing.
        GPT-5.4 has 300 RPM — we can afford deep prompts."""
        if not stocks_data:
            return {}
        if not self._gpt_available:
            return {sym: self.analyze_stock(sym, data) for sym, data in stocks_data.items()}

        try:
            # Build EXTREME per-stock data
            lines = []
            for sym, d in stocks_data.items():
                pnl = d.get('unrealized_pl', d.get('pnl', 0))
                lines.append(
                    f"\n--- {sym} ---\n"
                    f"  Price: ${d.get('price',0):.2f} | Entry: ${d.get('entry',0):.2f} | P&L: ${pnl:.2f}\n"
                    f"  TECHNICALS: RSI={d.get('rsi',50):.0f} MACD={d.get('macd_hist',0):.3f} "
                    f"VWAP={'ABOVE' if d.get('vwap_above') else 'BELOW'} "
                    f"EMA9={d.get('ema_9',0):.1f} EMA21={d.get('ema_21',0):.1f} "
                    f"Confluence={d.get('confluence',5)}/10 Vol={d.get('volume_ratio',1):.1f}x\n"
                    f"  SENTIMENT: Total={d.get('sentiment',0):+d} Yahoo={d.get('yahoo_score',0)} "
                    f"Reddit={d.get('reddit_score',0)} Analyst={d.get('analyst_score',0)} "
                    f"StockTwits={d.get('stocktwits_score',0)} Trump={d.get('trump_score',0)}\n"
                    f"  ENGINE: Score={d.get('confidence_engine',50)}% Strategy={d.get('signal','?')}\n"
                    f"  LEARNING: {d.get('learning_context','No history')}"
                )

            # Claude deep analysis references
            deep_refs = []
            for sym in stocks_data:
                if sym in _last_deep_briefing:
                    b = _last_deep_briefing[sym]
                    deep_refs.append(f"  {sym}: {b.get('action','?')} ({b.get('confidence',0)}%) - {str(b.get('reasoning',''))[:80]}")

            # Portfolio-wide learning
            portfolio_learn = list(stocks_data.values())[0].get('portfolio_learning', '') if stocks_data else ''

            regime = list(stocks_data.values())[0].get('regime', '?') if stocks_data else '?'
            trump = list(stocks_data.values())[0].get('trump_score', 0) if stocks_data else 0

            user_msg = f"""EXTREME ANALYSIS — Analyze ALL positions for day trading decisions.

MARKET CONTEXT:
  Regime: {regime} | Trump/Tariff Score: {trump:+d} | VIX: {list(stocks_data.values())[0].get('vix', 18) if stocks_data else 18}

PORTFOLIO ({len(stocks_data)} positions):
{''.join(lines)}

{'CLAUDE DEEP ANALYSIS (30-min institutional scan):' + chr(10) + chr(10).join(deep_refs) if deep_refs else 'No Claude analysis available yet.'}

{'STRATEGY PERFORMANCE (from learning DB):' + chr(10) + portfolio_learn if portfolio_learn else ''}

INSTRUCTIONS:
For EACH stock, provide an EXTREME analysis. Consider:
1. TECHNICAL SETUP: Is RSI overbought/oversold? MACD momentum direction? Above/below VWAP?
2. SENTIMENT: What are Reddit, Yahoo, analysts, StockTwits saying? Is there a catalyst?
3. RISK: How much are we down? Is this a blue chip that recovers or a speculative play?
4. SECTOR: Is the sector rotating in or out? Macro headwinds?
5. LEARNING: What happened LAST TIME we traded this stock? Did we win or lose?
6. EARNINGS: Is earnings coming? Did it just report? How did it react?
7. TRUMP/TARIFF: Is this stock affected by geopolitical risk?
8. MOMENTUM: Is price trending up, down, or sideways? Volume confirming?
9. CONVICTION: How sure are you? USE THE FULL RANGE 30-100.

Respond with JSON:
{{"results": {{
  "SYMBOL": {{
    "action": "BUY/SELL/HOLD/ADD_MORE",
    "confidence": 30-100,
    "reasoning": "2-3 sentences with specific numbers from the data",
    "target_price": 0.00,
    "stop_price": 0.00,
    "risk_level": "LOW/MEDIUM/HIGH",
    "urgency": "IMMEDIATE/WAIT/NO_RUSH",
    "key_signal": "the single most important factor driving this decision"
  }},
  ...
}}}}

RULES:
- confidence MUST be 30-100. NEVER 0. Use full range.
- RSI>75 without catalyst = SELL. RSI<30 with support = BUY.
- Winners +3%+ with momentum and volume = ADD_MORE with high confidence.
- Losers -5%+ with bad sentiment and no catalyst = SELL.
- Blue chips (AAPL,MSFT,GOOGL,AMZN,META,NVDA,TSLA) at loss = HOLD, they recover.
- If learning says we lose on this stock = lower confidence, smaller size.
- Be AGGRESSIVE. Be SPECIFIC. Every stock gets a real verdict with real numbers."""

            _rate_limit_gpt()
            t0 = _time.time()
            _ai_stats['gpt_calls'] += 1
            log.info(f"  [AI GPT-5.4] BATCH call starting — {len(stocks_data)} stocks, model={AZURE_DEPLOYMENT}")
            
            response = self._azure_client.chat.completions.create(
                model=AZURE_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": GPT4O_SYSTEM},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.3,
                max_completion_tokens=2000,
                response_format={"type": "json_object"},
            )
            
            elapsed_ms = int((_time.time() - t0) * 1000)
            _ai_stats['gpt_success'] += 1
            _ai_stats['gpt_total_ms'] += elapsed_ms
            _ai_stats['gpt_last_success'] = _time.strftime('%H:%M:%S')
            
            # Token usage tracking
            usage = response.usage if hasattr(response, 'usage') and response.usage else None
            tokens_in = usage.prompt_tokens if usage else 0
            tokens_out = usage.completion_tokens if usage else 0
            log.info(f"  [AI GPT-5.4] BATCH complete — {elapsed_ms}ms | tokens: {tokens_in} in + {tokens_out} out = {tokens_in+tokens_out} total")

            result = json.loads(response.choices[0].message.content)
            verdicts = result.get('results', result)

            # Normalize + log each verdict
            for sym in list(verdicts.keys()):
                if isinstance(verdicts[sym], dict):
                    verdicts[sym]['ai_source'] = f'Azure {AZURE_DEPLOYMENT}'
                    verdicts[sym]['scan_type'] = '5min_batch'
                    verdicts[sym]['response_ms'] = elapsed_ms
                    verdicts[sym]['tokens_used'] = tokens_in + tokens_out
                    action = verdicts[sym].get('action', '?')
                    conf = verdicts[sym].get('confidence', 0)
                    key_sig = str(verdicts[sym].get('key_signal', ''))[:40]
                    log.info(f"    {sym}: {action} ({conf}%) — {key_sig}")
                else:
                    del verdicts[sym]

            avg_ms = _ai_stats['gpt_total_ms'] // max(_ai_stats['gpt_success'], 1)
            log.info(f"  [AI STATS] GPT calls: {_ai_stats['gpt_success']}/{_ai_stats['gpt_calls']} ok | "
                     f"429s: {_ai_stats['gpt_429s']} | avg: {avg_ms}ms | this: {elapsed_ms}ms")
            return verdicts

        except Exception as e:
            elapsed_ms = int((_time.time() - t0) * 1000) if 't0' in dir() else 0
            _ai_stats['gpt_errors'] += 1
            _ai_stats['gpt_last_error'] = f"{e}"[:100]
            if '429' in str(e):
                _ai_stats['gpt_429s'] += 1
                log.warning(f"  [AI GPT-5.4] 429 RATE LIMITED after {elapsed_ms}ms — "
                            f"total 429s: {_ai_stats['gpt_429s']}/{_ai_stats['gpt_calls']} calls")
            else:
                log.warning(f"  [AI GPT-5.4] BATCH FAILED after {elapsed_ms}ms — {e}")
            log.warning(f"  [AI GPT-5.4] Falling back to per-stock for top 5")
            return {sym: self.analyze_stock(sym, data) for sym, data in list(stocks_data.items())[:5]}

    def deep_analysis(self, symbol: str, data: dict) -> dict:
        """30-min ultra deep: Claude Opus preferred, GPT-4o fallback."""
        if self._claude_available:
            result = self._claude_deep(symbol, data)
            if result:
                _last_deep_briefing[symbol] = result
            return result
        elif self._gpt_available:
            return self._gpt4o_analyze(symbol, data)
        return self._deterministic_fallback(symbol, data)

    def _gpt4o_analyze(self, symbol: str, data: dict) -> dict:
        """GPT-5.4: EXTREME per-stock analysis with all data sources."""
        try:
            deep_ref = ""
            if symbol in _last_deep_briefing:
                brief = _last_deep_briefing[symbol]
                deep_ref = f"\n\nCLAUDE DEEP ANALYSIS (institutional scan):\n{json.dumps(brief, indent=2)[:800]}"

            user_msg = f"""EXTREME ANALYSIS for {symbol}. Use ALL data below.

TRADINGVIEW INDICATORS (LIVE):
  RSI: {data.get('rsi', 'N/A')} | MACD Histogram: {data.get('macd_hist', 'N/A')}
  VWAP: {'ABOVE - institutional buying' if data.get('vwap_above') else 'BELOW - institutional selling'}
  Bollinger Band: {data.get('bb_position', 'N/A')} | Volume: {data.get('volume_ratio', 'N/A')}x avg
  EMA 9/21: {data.get('ema_9', 'N/A')} / {data.get('ema_21', 'N/A')}
  Confluence Score: {data.get('confluence', 'N/A')}/10

POSITION:
  Price: ${data.get('price', 0):.2f} | Entry: ${data.get('entry', 0):.2f}
  P&L: ${data.get('unrealized_pl', data.get('pnl', 0)):.2f} | Shares: {data.get('qty', 0)}
  Day Change: {data.get('day_change_pct', 0):+.1f}%

SENTIMENT (9 SOURCES):
  Yahoo News: {data.get('yahoo_score', 0)}/5 | Reddit WSB: {data.get('reddit_score', 0)}/5
  Wall St Analysts: {data.get('analyst_score', 0)}/5 | StockTwits: {data.get('stocktwits_score', 0)}/5
  Trump/Tariff Risk: {data.get('trump_score', 0):+d} | Overall: {data.get('sentiment', 0):+d}

CONFIDENCE ENGINE:
  Score: {data.get('confidence_engine', 'N/A')}% | Best Strategy: {data.get('best_strategy', 'N/A')}
  Signal: {data.get('signal', 'N/A')}

MARKET: Regime={data.get('regime', 'N/A')} | Sector={data.get('sector', 'N/A')}

LEARNING HISTORY: {data.get('learning_context', 'No prior trades')}
PORTFOLIO CONTEXT: {data.get('portfolio_learning', '')[:300]}
{deep_ref}

Give your EXTREME analysis:
1. What do the technicals say? (RSI trend, MACD direction, VWAP position)
2. What does sentiment say? (bullish/bearish consensus across sources)
3. What does our trading history say? (past wins/losses on this stock)
4. What's the risk? (earnings, sector rotation, macro headwinds)
5. FINAL VERDICT with specific target and stop prices.

Respond with JSON. confidence MUST be 30-100, never 0."""

            _rate_limit_gpt()
            t0 = _time.time()
            _ai_stats['gpt_calls'] += 1
            log.info(f"  [AI GPT-5.4] Per-stock {symbol} — calling model={AZURE_DEPLOYMENT}")
            
            response = self._azure_client.chat.completions.create(
                model=AZURE_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": GPT4O_SYSTEM},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.3,
                max_completion_tokens=800,
                response_format={"type": "json_object"},
            )
            
            elapsed_ms = int((_time.time() - t0) * 1000)
            _ai_stats['gpt_success'] += 1
            _ai_stats['gpt_total_ms'] += elapsed_ms
            _ai_stats['gpt_last_success'] = _time.strftime('%H:%M:%S')
            
            usage = response.usage if hasattr(response, 'usage') and response.usage else None
            tokens_in = usage.prompt_tokens if usage else 0
            tokens_out = usage.completion_tokens if usage else 0

            result = json.loads(response.choices[0].message.content)
            result['ai_source'] = f'Azure {AZURE_DEPLOYMENT}'
            result['scan_type'] = '5min'
            result['response_ms'] = elapsed_ms
            result['tokens_used'] = tokens_in + tokens_out
            log.info(f"  [AI GPT-5.4] {symbol}: {result.get('action')} ({result.get('confidence')}%) "
                     f"[{elapsed_ms}ms, {tokens_in+tokens_out} tokens] — {str(result.get('key_signal',''))[:50]}")
            return result

        except Exception as e:
            elapsed_ms = int((_time.time() - t0) * 1000) if 't0' in dir() else 0
            _ai_stats['gpt_errors'] += 1
            _ai_stats['gpt_last_error'] = f"{symbol}: {e}"[:100]
            if '429' in str(e):
                _ai_stats['gpt_429s'] += 1
                log.warning(f"  [AI GPT-5.4] 429 RATE LIMITED on {symbol} [{elapsed_ms}ms] — "
                            f"429s today: {_ai_stats['gpt_429s']}")
            else:
                log.warning(f"  [AI GPT-5.4] FAILED on {symbol} [{elapsed_ms}ms] — {e}")
            if self._claude_available:
                log.info(f"  [AI] Falling back to Claude quick for {symbol}")
                return self._claude_quick(symbol, data)
            return self._deterministic_fallback(symbol, data)

    # ══════════════════════════════════════════════════
    # 30-MIN SCAN: Claude Opus 4.7 (ULTRA DEEP)
    # ══════════════════════════════════════════════════

    def deep_analyze(self, symbol: str, data: dict) -> dict:
        """30-min ultra deep: Claude Opus institutional-grade analysis."""
        global _last_deep_briefing, _last_deep_time

        if self._claude_available:
            result = self._claude_deep(symbol, data)
            # Cache for GPT-4o to reference
            _last_deep_briefing[symbol] = result
            _last_deep_time = datetime.now()
            return result
        elif self._gpt_available:
            # Fallback: use GPT-4o with deeper prompt
            return self._gpt4o_analyze(symbol, data)
        return self._deterministic_fallback(symbol, data)

    def _claude_deep(self, symbol: str, data: dict) -> dict:
        """Claude Opus 4.7: ultra deep institutional analysis."""
        try:
            payload = {
                'symbol': symbol,
                'system_prompt': CLAUDE_DEEP_SYSTEM,
                **data,
            }
            resp = requests.post(
                f"{CLAUDE_URL}/analyze",
                json=payload,
                headers={'X-API-Key': CLAUDE_API_KEY, 'Content-Type': 'application/json'},
                timeout=45,
            )
            if resp.status_code == 200:
                result = resp.json()
                result['ai_source'] = 'Claude Opus 4.7 (DEEP)'
                result['scan_type'] = '30min_deep'
                log.info(f"Claude DEEP {symbol}: {result.get('action')} ({result.get('confidence')}%)")
                return result
        except Exception as e:
            log.warning(f"Claude deep failed for {symbol}: {e}")
        return self._deterministic_fallback(symbol, data)

    def _claude_quick(self, symbol: str, data: dict) -> dict:
        """Claude fallback for 5-min when GPT-4o is down."""
        try:
            data['symbol'] = symbol
            resp = requests.post(
                f"{CLAUDE_URL}/analyze",
                json=data,
                headers={'X-API-Key': CLAUDE_API_KEY, 'Content-Type': 'application/json'},
                timeout=30,
            )
            if resp.status_code == 200:
                result = resp.json()
                result['ai_source'] = 'Claude Opus 4.7 (quick)'
                result['scan_type'] = '5min_fallback'
                return result
        except Exception as e:
            log.warning(f"Claude quick failed for {symbol}: {e}")
        return self._deterministic_fallback(symbol, data)

    # ══════════════════════════════════════════════════
    # OTHER METHODS (bull/bear debate, briefing)
    # ══════════════════════════════════════════════════

    def bull_bear_debate(self, symbol: str, data: dict) -> dict:
        """Full bull vs bear debate — uses Claude if available, else GPT-4o."""
        if self._claude_available:
            return self.deep_analyze(symbol, data)
        elif self._gpt_available:
            return self._gpt4o_analyze(symbol, data)
        return {'bull_case': '', 'bear_case': '', 'verdict': 'HOLD',
                'bull_confidence': 50, 'bear_confidence': 50}

    def morning_briefing(self, market_data: dict, positions: list, sentiment: dict) -> str:
        """Morning briefing — Claude deep analysis."""
        if self._claude_available:
            try:
                resp = requests.post(
                    f"{CLAUDE_URL}/briefing",
                    json={'market': market_data, 'positions': positions, 'sentiment': sentiment},
                    headers={'X-API-Key': CLAUDE_API_KEY, 'Content-Type': 'application/json'},
                    timeout=45,
                )
                if resp.status_code == 200:
                    return resp.json().get('briefing', '')
            except:
                pass
        return "AI briefing unavailable"

    def get_last_deep_briefing(self, symbol: str) -> dict:
        """Get the cached Claude deep analysis for a symbol."""
        return _last_deep_briefing.get(symbol, {})

    def get_cached_analysis(self, symbol: str) -> dict:
        """Get cached analysis for a symbol (alias for dashboard API)."""
        return _last_deep_briefing.get(symbol, {})

    def get_deep_briefing_age_minutes(self) -> int:
        """How old is the last deep briefing in minutes."""
        if _last_deep_time:
            return int((datetime.now() - _last_deep_time).total_seconds() / 60)
        return 999

    # ══════════════════════════════════════════════════
    # DETERMINISTIC FALLBACK (no AI needed)
    # ══════════════════════════════════════════════════

    def _deterministic_fallback(self, symbol: str, data: dict) -> dict:
        """Rule-based fallback when both AIs are offline."""
        rsi = data.get('rsi', 50)
        pnl = data.get('unrealized_pl', data.get('pnl', 0))
        confluence = data.get('confluence', 5)
        sentiment = data.get('sentiment', 0)
        holding = data.get('holding', False)

        if holding and pnl > 0:
            cost = data.get('entry', 1) * data.get('qty', 1)
            pct = (pnl / cost * 100) if cost > 0 else 0
            if pct >= 5:
                return {'action': 'SELL', 'confidence': 80,
                        'reasoning': f'Runner target +{pct:.1f}%. Take partial profits.',
                        'ai_source': 'Deterministic', 'scan_type': 'fallback'}
            elif pct >= 2:
                return {'action': 'HOLD', 'confidence': 70,
                        'reasoning': f'Approaching scalp target +{pct:.1f}%. Hold for +2% minimum.',
                        'ai_source': 'Deterministic', 'scan_type': 'fallback'}

        if holding and pnl < 0:
            return {'action': 'HOLD', 'confidence': 90,
                    'reasoning': f'Iron Law 1: NEVER sell at loss. P&L ${pnl:+.2f}. Hold for recovery.',
                    'ai_source': 'Deterministic', 'scan_type': 'fallback'}

        if rsi < 30 and confluence >= 6:
            return {'action': 'BUY', 'confidence': 65,
                    'reasoning': f'RSI {rsi} oversold + confluence {confluence}/10. Akash Method dip buy.',
                    'ai_source': 'Deterministic', 'scan_type': 'fallback'}

        return {'action': 'HOLD', 'confidence': 50,
                'reasoning': f'No clear signal. RSI {rsi}, confluence {confluence}/10.',
                'ai_source': 'Deterministic', 'scan_type': 'fallback'}


    def earnings_play_analysis(self, symbol: str, data: dict) -> dict:
        return self.deep_analyze(symbol, data)
