"""
Beast V6 — AI Brain
━━━━━━━━━━━━━━━━━━━━━━━━━━

CURRENT SETUP (V6):
  ALL SCANS → Azure GPT-5.4 (gpt54 deployment on East US)
    - 5-min scans: analyze_batch() — 16 stocks per batch
    - 30-min deep: deep_analyze() — 8 stocks, deeper prompts
    - 1-hr learning: analyze_stock() — 20 watchlist stocks
    - 3AM daily learning: call_raw() — 3 batched prompts for playbook

CLAUDE STATUS: DISABLED (placeholder for future)
  - Tunnel retired — see archive_claude_tunnel/TUNNEL_HISTORY.md
  - Direct Anthropic API ready — just add ANTHROPIC_API_KEY to .env
  - Auto-enables when key is set: CLAUDE_ENABLED = bool(ANTHROPIC_API_KEY)

TOKEN TRACKING:
  - Every GPT call logs input_tokens + output_tokens to _ai_stats
  - brain.get_token_stats() returns session totals + estimated USD cost
  - Needed for 2 weeks to estimate Claude costs before purchasing

BRANCH RULES:
  - V5 branch (feature/beast-v5-pro-upgrades) = production, DO NOT MODIFY
  - V6 branch (feature/beast-v6-direct-claude) = AI changes go here
  - Merge V6 → V5 only after testing

Fallback chain: GPT-5.4 → Claude (when enabled) → deterministic rules
"""
import os
import logging
import requests
import json
import time as _time
import threading
from datetime import datetime
from openai import AzureOpenAI

log = logging.getLogger('Beast.AI')

# ═══════════════════════════════════════════════════════════
# AZURE GPT-5.4 CONFIG
# This is the ONLY active AI model. All scans use this.
# Deployment name: "gpt54" on Azure East US
# ═══════════════════════════════════════════════════════════
AZURE_ENDPOINT = os.getenv('AZURE_OPENAI_ENDPOINT', 'https://eastus.api.cognitive.microsoft.com/')
AZURE_KEY = os.getenv('AZURE_OPENAI_KEY', '')
AZURE_DEPLOYMENT = os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt54')
AZURE_API_VERSION = '2024-10-21'

# ═══════════════════════════════════════════════════════════
# CLAUDE API — DISABLED (placeholder for future)
#
# HOW TO ENABLE:
#   1. Buy key at console.anthropic.com
#   2. Add to .env: ANTHROPIC_API_KEY=sk-ant-...
#   3. Bot auto-enables (CLAUDE_ENABLED = bool(key))
#   4. call_raw() will prefer Claude over GPT for 3AM learning
#
# COST ESTIMATES (need 2 weeks of token tracking first):
#   Sonnet 4 for all scans: ~$77/mo
#   Opus 4.7 for 3AM only:  ~$3/mo
#   See AI_ARCHITECTURE.md for full breakdown
# ═══════════════════════════════════════════════════════════
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
CLAUDE_MODEL = os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-20250514')
CLAUDE_ENABLED = bool(ANTHROPIC_API_KEY)  # Flips to True when key is added

# ═══════════════════════════════════════════════════════════
# TOKEN TRACKING + RATE LIMITING
#
# WHY: We need accurate token counts to estimate Claude costs.
# Every GPT call increments gpt_input_tokens and gpt_output_tokens.
# After 2 weeks: brain.get_token_stats() → accurate monthly estimate.
#
# Rate limit: 2s between calls to avoid Azure 429 errors.
# Stats tracked: calls, successes, errors, 429s, tokens, latency.
# ═══════════════════════════════════════════════════════════
_ai_last_call = 0
_ai_lock = threading.Lock()
_ai_stats = {
    # GPT-5.4 stats
    'gpt_calls': 0, 'gpt_success': 0, 'gpt_errors': 0, 'gpt_429s': 0,
    'gpt_total_ms': 0, 'gpt_last_error': '', 'gpt_last_success': '',
    'gpt_input_tokens': 0,   # Running total — for cost estimation
    'gpt_output_tokens': 0,  # Running total — for cost estimation
    # Claude stats (will populate when enabled)
    'claude_calls': 0, 'claude_success': 0, 'claude_errors': 0,
    'claude_total_ms': 0, 'claude_last_error': '',
    'claude_input_tokens': 0, 'claude_output_tokens': 0,
}
AI_MIN_INTERVAL = 2  # seconds between calls (Azure allows 300 RPM)

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

def _is_trading_hours_check() -> bool:
    """Returns True during tradeable hours (4 AM - 8 PM ET).
    Claude fallback only allowed during these hours to save quota."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    return 4 <= now.hour < 20

# ── AI verdict cache: skip re-analysis if nothing material changed ──
_verdict_cache = {}  # symbol -> {verdict, price, timestamp}
VERDICT_CACHE_TTL = 300  # 5 min — skip AI if price moved < 1% since last analysis

def _should_reanalyze(symbol: str, current_price: float) -> bool:
    """Check if we need fresh AI analysis or can use cached verdict.
    Returns True if we should call AI, False if cached is fine."""
    if symbol not in _verdict_cache:
        return True
    cached = _verdict_cache[symbol]
    age = _time.time() - cached['time']
    if age > VERDICT_CACHE_TTL:
        return True  # Cache expired
    # Check if price moved significantly (>1%)
    old_price = cached.get('price', 0)
    if old_price > 0:
        pct_move = abs(current_price - old_price) / old_price * 100
        if pct_move > 1.0:
            return True  # Price moved >1% — reanalyze
    return False  # Price stable, cache is fresh

def _cache_verdict(symbol: str, verdict: dict, price: float):
    """Store verdict in cache."""
    _verdict_cache[symbol] = {
        'verdict': verdict, 'price': price, 'time': _time.time()
    }

def _safe_parse_json(text: str) -> dict:
    """Parse JSON from AI response. Handles truncated/malformed responses.
    GPT-5.4 sometimes returns unterminated strings or trailing content."""
    if not text:
        return {}
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try truncating at last complete object
    for end_char in ['}', ']}', '"}}']:
        idx = text.rfind(end_char)
        if idx > 0:
            try:
                return json.loads(text[:idx + len(end_char)])
            except:
                pass
    # Try fixing common issues: trailing comma, unclosed strings
    cleaned = text.strip()
    if cleaned.endswith(','):
        cleaned = cleaned[:-1]
    # Close any unclosed braces
    opens = cleaned.count('{') - cleaned.count('}')
    if opens > 0:
        cleaned += '}' * opens
    try:
        return json.loads(cleaned)
    except:
        pass
    log.warning(f"  [AI] JSON repair failed — response: {text[:200]}")
    return {}

# ── Shared state ──
_last_deep_briefing = {}
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

FOR ALL RESPONSES:
- Output VALID JSON only. No markdown, no explanation outside JSON.
- confidence: 30-100 (NEVER 0). 30=low, 50=neutral, 70=high, 90=very high.
- action: BUY, SELL, HOLD, or ADD_MORE
- reasoning: max 20 words, specific numbers from the data
- {"action":"HOLD","confidence":55,"reasoning":"RSI 52 neutral, MACD flat, wait for direction"}"""

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
    """Hybrid AI: GPT-5.4 (all scans) + Claude Opus (30min)."""

    def __init__(self):
        self._gpt_available = False
        self._claude_available = False
        self._claude_direct = False  # True when using Direct Anthropic API
        self._azure_client = None

        # Check Azure GPT-5.4
        if AZURE_KEY:
            try:
                self._azure_client = AzureOpenAI(
                    azure_endpoint=AZURE_ENDPOINT,
                    api_key=AZURE_KEY,
                    api_version=AZURE_API_VERSION,
                )
                self._gpt_available = True
                log.info(f"🤖 Azure GPT-5.4 ONLINE ({AZURE_ENDPOINT})")
            except Exception as e:
                log.warning(f"Azure GPT-5.4 init failed: {e}")

        # Claude — only check if CLAUDE_ENABLED (auto-enables when ANTHROPIC_API_KEY set)
        if CLAUDE_ENABLED and ANTHROPIC_API_KEY:
            try:
                resp = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": CLAUDE_MODEL, "max_tokens": 50, "messages": [{"role": "user", "content": "Say OK"}]},
                    timeout=10)
                if resp.status_code == 200:
                    self._claude_available = True
                    self._claude_direct = True
                    log.info(f"🧠 Claude ONLINE — Direct Anthropic API ({CLAUDE_MODEL})")
                else:
                    log.warning(f"🧠 Claude API error: {resp.status_code}")
            except Exception as e:
                log.warning(f"🧠 Claude API failed: {e}")

        if not self._claude_available:
            log.info("🧠 Claude DISABLED — GPT-only mode (set ANTHROPIC_API_KEY to enable)")

    @property
    def is_available(self) -> bool:
        return self._gpt_available or self._claude_available

    # ══════════════════════════════════════════════════
    # TOKEN TRACKING — for cost estimation
    # ══════════════════════════════════════════════════

    def get_token_stats(self) -> dict:
        """Get current session token usage for cost estimation."""
        return {
            'gpt_calls': _ai_stats['gpt_calls'],
            'gpt_input_tokens': _ai_stats['gpt_input_tokens'],
            'gpt_output_tokens': _ai_stats['gpt_output_tokens'],
            'gpt_total_tokens': _ai_stats['gpt_input_tokens'] + _ai_stats['gpt_output_tokens'],
            'claude_calls': _ai_stats['claude_calls'],
            'claude_input_tokens': _ai_stats['claude_input_tokens'],
            'claude_output_tokens': _ai_stats['claude_output_tokens'],
            'claude_enabled': self._claude_available,
            # Cost estimates (per MTok pricing)
            'est_gpt_cost_usd': round(
                _ai_stats['gpt_input_tokens'] / 1_000_000 * 2.50 +
                _ai_stats['gpt_output_tokens'] / 1_000_000 * 10.0, 4),
        }

    # ══════════════════════════════════════════════════
    # RAW PROMPT CALL — for 3AM batched learning
    # Sends prompt directly, returns parsed JSON dict
    # Tries: Claude Direct → GPT Raw → {}
    # ══════════════════════════════════════════════════

    def call_raw(self, prompt: str, system: str = "Output valid JSON only.",
                 timeout: int = 120) -> dict:
        """Send a raw prompt to AI and get JSON back. Used by 3AM learning.
        Does NOT go through analyze_stock (which wraps in its own format)."""
        import json as _json

        # Try 1: Claude Direct (Anthropic API)
        if self._claude_available and self._claude_direct and ANTHROPIC_API_KEY:
            try:
                t0 = time.time()
                resp = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": CLAUDE_MODEL,
                        "max_tokens": 4096,
                        "system": system,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    timeout=timeout)
                elapsed = int((time.time() - t0) * 1000)
                if resp.status_code == 200:
                    data = resp.json()
                    text = data.get('content', [{}])[0].get('text', '{}')
                    # Extract JSON from possible markdown wrapping
                    if '```json' in text:
                        text = text.split('```json')[1].split('```')[0].strip()
                    elif '```' in text:
                        text = text.split('```')[1].split('```')[0].strip()
                    try:
                        result = _json.loads(text)
                        log.info(f"  [AI] Claude direct OK ({elapsed}ms, {len(text)} chars)")
                        return result
                    except _json.JSONDecodeError:
                        log.warning(f"  [AI] Claude direct non-JSON: {text[:150]}")
                        return {'raw_response': text[:1000]}
                else:
                    log.warning(f"  [AI] Claude direct HTTP {resp.status_code}: {resp.text[:150]}")
            except Exception as e:
                log.warning(f"  [AI] Claude direct error: {e}")

        # Try 2: Azure GPT Raw (direct OpenAI call, NOT analyze_stock)
        if self._gpt_available and self._azure_client:
            try:
                t0 = time.time()
                response = self._azure_client.chat.completions.create(
                    model=AZURE_DEPLOYMENT,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                )
                elapsed = int((time.time() - t0) * 1000)
                usage = response.usage if hasattr(response, 'usage') and response.usage else None
                tok_in = usage.prompt_tokens if usage else 0
                tok_out = usage.completion_tokens if usage else 0
                _ai_stats['gpt_input_tokens'] += tok_in
                _ai_stats['gpt_output_tokens'] += tok_out
                text = response.choices[0].message.content or '{}'
                try:
                    result = _json.loads(text)
                    log.info(f"  [AI] GPT-5.4 raw OK ({elapsed}ms, {tok_in}+{tok_out} tok, daily={_ai_stats['gpt_input_tokens']+_ai_stats['gpt_output_tokens']:,})")
                    return result
                except _json.JSONDecodeError:
                    log.warning(f"  [AI] GPT-5.4 raw non-JSON: {text[:150]}")
                    return {'raw_response': text[:1000]}
            except Exception as e:
                log.warning(f"  [AI] GPT-5.4 raw error: {type(e).__name__}: {e}")

        log.warning("  [AI] All AI providers failed for raw call")
        return {}

    # ══════════════════════════════════════════════════
    # 5-MIN SCAN: GPT-5.4 (fast, maxed out)
    # ══════════════════════════════════════════════════

    def analyze_stock(self, symbol: str, data: dict) -> dict:
        """5-min scan: GPT-5.4 primary → Claude fallback → deterministic."""
        if self._gpt_available:
            return self._gpt_analyze(symbol, data)
        elif self._claude_available:
            log.info(f"  [AI] GPT offline — using Claude quick for {symbol}")
            return self._claude_quick(symbol, data)
        return self._deterministic_fallback(symbol, data)

    def analyze_batch(self, stocks_data: dict) -> dict:
        """Batch analyze all stocks in ONE GPT-5.4 call.
        Sends only FILTERED data that matters for trade decisions.
        Returns compact verdicts — action + confidence + short reason."""
        if not stocks_data:
            return {}
        if not self._gpt_available:
            return {sym: self.analyze_stock(sym, data) for sym, data in stocks_data.items()}

        try:
            # SMART CACHE: Skip stocks that haven't moved since last analysis
            need_analysis = {}
            cached_results = {}
            for sym, d in stocks_data.items():
                price = d.get('price', 0)
                if _should_reanalyze(sym, price):
                    need_analysis[sym] = d
                else:
                    cached_results[sym] = _verdict_cache[sym]['verdict']
            
            if cached_results:
                log.info(f"  [AI CACHE] {len(cached_results)} stocks cached (price stable <1%), "
                         f"{len(need_analysis)} need fresh analysis")
            
            # If everything is cached, return immediately — no API call
            if not need_analysis:
                log.info(f"  [AI CACHE] All {len(stocks_data)} stocks cached — skipping GPT call entirely")
                return cached_results

            # Build LEAN per-stock line — only what matters for a trade decision
            lines = []
            for sym, d in need_analysis.items():
                pnl = d.get('unrealized_pl', d.get('pnl', 0))
                cost = d.get('entry', 1) * d.get('qty', 1)
                pnl_pct = (pnl / cost * 100) if cost > 0 else 0
                # One line per stock — only actionable data
                lines.append(
                    f"{sym} ${d.get('price',0):.0f} "
                    f"PnL:{pnl_pct:+.1f}% "
                    f"RSI:{d.get('rsi',50):.0f} "
                    f"MACD:{'+' if d.get('macd_hist',0)>0 else ''}{d.get('macd_hist',0):.2f} "
                    f"VWAP:{'A' if d.get('vwap_above') else 'B'} "
                    f"Sent:{d.get('sentiment',0):+d} "
                    f"{d.get('learning_context','')}"
                )

            regime = list(stocks_data.values())[0].get('regime', '?')

            user_msg = f"""Trade decisions for {len(stocks_data)} stocks. Regime: {regime}

{chr(10).join(lines)}

For each stock respond JSON:
{{"results":{{"SYM":{{"action":"BUY/SELL/HOLD/ADD_MORE","confidence":30-100,"reasoning":"10 words max"}}}}}}

Rules: RSI>75=SELL. RSI<30=BUY. PnL>+3% momentum=ADD_MORE. PnL<-5% bad sentiment=SELL. Blue chip loss=HOLD. confidence 30-100 NEVER 0."""

            _rate_limit_gpt()
            t0 = _time.time()
            _ai_stats['gpt_calls'] += 1
            log.info(f"  [AI GPT-5.4] BATCH — {len(stocks_data)} stocks, prompt ~{len(user_msg)} chars")
            
            response = self._azure_client.chat.completions.create(
                model=AZURE_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": GPT4O_SYSTEM},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.3,
                max_completion_tokens=4000,
                response_format={"type": "json_object"},
            )
            
            elapsed_ms = int((_time.time() - t0) * 1000)
            _ai_stats['gpt_success'] += 1
            _ai_stats['gpt_total_ms'] += elapsed_ms
            _ai_stats['gpt_last_success'] = _time.strftime('%H:%M:%S')
            
            usage = response.usage if hasattr(response, 'usage') and response.usage else None
            tokens_in = usage.prompt_tokens if usage else 0
            tokens_out = usage.completion_tokens if usage else 0
            _ai_stats['gpt_input_tokens'] += tokens_in
            _ai_stats['gpt_output_tokens'] += tokens_out
            log.info(f"  [AI GPT-5.4] BATCH done — {elapsed_ms}ms | {tokens_in}+{tokens_out}={tokens_in+tokens_out} tokens | daily_total={_ai_stats['gpt_input_tokens']+_ai_stats['gpt_output_tokens']:,}")

            raw_content = response.choices[0].message.content
            if tokens_out >= 3900:
                log.warning(f"  [AI GPT-5.4] Response may be truncated — used {tokens_out}/4000 output tokens")
            
            result = _safe_parse_json(raw_content)
            if not result:
                log.warning(f"  [AI GPT-5.4] JSON PARSE FAILED — raw ({len(raw_content)} chars):\n{raw_content[:400]}")
                return {sym: self._deterministic_fallback(sym, data) for sym, data in stocks_data.items()}
            verdicts = result.get('results', result)

            # Log each verdict + cache it
            for sym in list(verdicts.keys()):
                if isinstance(verdicts[sym], dict):
                    verdicts[sym]['ai_source'] = f'Azure {AZURE_DEPLOYMENT}'
                    verdicts[sym]['scan_type'] = '5min_batch'
                    action = verdicts[sym].get('action', '?')
                    conf = verdicts[sym].get('confidence', 0)
                    reason = str(verdicts[sym].get('reasoning', ''))[:40]
                    log.info(f"    {sym}: {action} ({conf}%) — {reason}")
                    # Cache for next scan
                    price = need_analysis.get(sym, {}).get('price', 0)
                    _cache_verdict(sym, verdicts[sym], price)
                else:
                    del verdicts[sym]

            # Merge fresh verdicts with cached results
            verdicts.update(cached_results)

            avg_ms = _ai_stats['gpt_total_ms'] // max(_ai_stats['gpt_success'], 1)
            log.info(f"  [AI STATS] ok:{_ai_stats['gpt_success']}/{_ai_stats['gpt_calls']} "
                     f"429s:{_ai_stats['gpt_429s']} err:{_ai_stats['gpt_errors']} avg:{avg_ms}ms")
            return verdicts

        except Exception as e:
            elapsed_ms = int((_time.time() - t0) * 1000) if 't0' in dir() else 0
            _ai_stats['gpt_errors'] += 1
            _ai_stats['gpt_last_error'] = f"{e}"[:100]
            if '429' in str(e):
                _ai_stats['gpt_429s'] += 1
                log.warning(f"  [AI GPT-5.4] 429 RATE LIMITED [{elapsed_ms}ms]")
            else:
                log.warning(f"  [AI GPT-5.4] BATCH FAILED [{elapsed_ms}ms] — {e}")
            log.warning(f"  [AI] Using deterministic for all {len(stocks_data)} stocks")
            return {sym: self._deterministic_fallback(sym, data) for sym, data in stocks_data.items()}

    def deep_analysis(self, symbol: str, data: dict) -> dict:
        """30-min ultra deep: Claude Opus preferred, GPT-5.4."""
        if self._claude_available:
            result = self._claude_deep(symbol, data)
            if result:
                _last_deep_briefing[symbol] = result
            return result
        elif self._gpt_available:
            return self._gpt_analyze(symbol, data)
        return self._deterministic_fallback(symbol, data)

    def _gpt_analyze(self, symbol: str, data: dict) -> dict:
        """GPT-5.4: EXTREME per-stock analysis with all data sources."""
        try:
            deep_ref = ""
            if symbol in _last_deep_briefing:
                brief = _last_deep_briefing[symbol]
                deep_ref = f"\n\nCLAUDE DEEP ANALYSIS (institutional scan):\n{json.dumps(brief, indent=2)[:800]}"

            pnl = data.get('unrealized_pl', data.get('pnl', 0))
            cost = data.get('entry', 1) * data.get('qty', 1)
            pnl_pct = (pnl / cost * 100) if cost > 0 else 0

            user_msg = f"""{symbol}: ${data.get('price',0):.2f} entry=${data.get('entry',0):.2f} PnL:{pnl_pct:+.1f}%
RSI={data.get('rsi',50):.0f} MACD={data.get('macd_hist',0):.2f} VWAP={'above' if data.get('vwap_above') else 'below'} Vol={data.get('volume_ratio',1):.1f}x Conf={data.get('confluence',5)}/10
Sentiment: {data.get('sentiment',0):+d} (Yahoo={data.get('yahoo_score',0)} Reddit={data.get('reddit_score',0)} Analyst={data.get('analyst_score',0)})
Engine: {data.get('confidence_engine',50)}% | Regime: {data.get('regime','?')} | {data.get('learning_context','')}
{deep_ref}

Trade decision? JSON: action, confidence (30-100 never 0), reasoning (20 words max)."""

            _rate_limit_gpt()
            t0 = _time.time()
            _ai_stats['gpt_calls'] += 1
            log.info(f"  [AI GPT-5.4] {symbol} — prompt {len(user_msg)} chars")
            
            response = self._azure_client.chat.completions.create(
                model=AZURE_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": GPT4O_SYSTEM},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.3,
                max_completion_tokens=1500,
                response_format={"type": "json_object"},
            )
            
            elapsed_ms = int((_time.time() - t0) * 1000)
            _ai_stats['gpt_success'] += 1
            _ai_stats['gpt_total_ms'] += elapsed_ms
            _ai_stats['gpt_last_success'] = _time.strftime('%H:%M:%S')
            
            usage = response.usage if hasattr(response, 'usage') and response.usage else None
            tokens_in = usage.prompt_tokens if usage else 0
            tokens_out = usage.completion_tokens if usage else 0
            _ai_stats['gpt_input_tokens'] += tokens_in
            _ai_stats['gpt_output_tokens'] += tokens_out

            raw_content = response.choices[0].message.content
            result = _safe_parse_json(raw_content)
            if not result:
                log.warning(f"  [AI GPT-5.4] {symbol} JSON PARSE FAILED — raw:\n{raw_content[:300]}")
                return self._deterministic_fallback(symbol, data)
            result['ai_source'] = f'Azure {AZURE_DEPLOYMENT}'
            result['scan_type'] = '5min'
            result['response_ms'] = elapsed_ms
            result['tokens_used'] = tokens_in + tokens_out
            result['tokens_in'] = tokens_in
            result['tokens_out'] = tokens_out
            log.info(f"  [AI GPT-5.4] {symbol}: {result.get('action')} ({result.get('confidence')}%) "
                     f"[{elapsed_ms}ms, {tokens_in}+{tokens_out} tok] — {str(result.get('key_signal',''))[:50]}")
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
            if self._claude_available and _is_trading_hours_check():
                log.info(f"  [AI] GPT-5.4 failed → falling back to Claude quick for {symbol}")
                _ai_stats['claude_calls'] += 1
                try:
                    t1 = _time.time()
                    result = self._claude_quick(symbol, data)
                    claude_ms = int((_time.time() - t1) * 1000)
                    _ai_stats['claude_success'] += 1
                    _ai_stats['claude_total_ms'] += claude_ms
                    log.info(f"  [AI Claude] {symbol}: {result.get('action','?')} ({result.get('confidence',0)}%) [{claude_ms}ms]")
                    return result
                except Exception as ce:
                    _ai_stats['claude_errors'] += 1
                    _ai_stats['claude_last_error'] = f"{symbol}: {ce}"[:100]
                    log.warning(f"  [AI Claude] ALSO FAILED on {symbol} — {ce}")
            elif self._claude_available:
                log.info(f"  [AI] GPT-5.4 failed but outside trading hours (8PM-4AM) — skipping Claude, using deterministic")
            return self._deterministic_fallback(symbol, data)

    # ══════════════════════════════════════════════════
    # 30-MIN SCAN: Claude Opus 4.7 (ULTRA DEEP)
    # ══════════════════════════════════════════════════

    def deep_analyze(self, symbol: str, data: dict) -> dict:
        """30-min ultra deep: Claude Opus institutional-grade analysis."""
        global _last_deep_briefing, _last_deep_time

        if self._claude_available:
            result = self._claude_deep(symbol, data)
            # Cache for GPT-5.4 to reference
            _last_deep_briefing[symbol] = result
            _last_deep_time = datetime.now()
            return result
        elif self._gpt_available:
            # Fallback: use GPT-5.4 with deeper prompt
            return self._gpt_analyze(symbol, data)
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
        """Claude fallback for 5-min when GPT-5.4 is down."""
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
        """Full bull vs bear debate — uses Claude if available, else GPT-5.4."""
        if self._claude_available:
            return self.deep_analyze(symbol, data)
        elif self._gpt_available:
            return self._gpt_analyze(symbol, data)
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
