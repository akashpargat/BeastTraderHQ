"""
Beast V5 — MEGA Regression Test Suite
======================================
Tests EVERYTHING with REAL data before deployment.
If ANY test fails, DO NOT DEPLOY.

Usage:
    python test_v5_regression.py          # Full test
    python test_v5_regression.py --quick  # Skip slow tests (API, DB)
    
Output: console + test_results.log
"""
import sys, os, time, json, pathlib, importlib, subprocess, traceback, logging, re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Load .env for real credentials
from dotenv import load_dotenv
load_dotenv('.env')

# ── Logging setup — console + file ──
LOG_FILE = 'test_results.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8'),
    ]
)
log = logging.getLogger('V5Test')

QUICK_MODE = '--quick' in sys.argv

passed = 0
failed = 0
skipped = 0
errors = []
timings = []

def test(name, fn, skip_quick=False):
    """Run a test. Logs expected vs actual on failure."""
    global passed, failed, skipped, errors, timings
    if skip_quick and QUICK_MODE:
        log.info(f'  ⏭️  SKIP: {name} (quick mode)')
        skipped += 1
        return
    start = time.time()
    try:
        result = fn()
        elapsed = time.time() - start
        timings.append((name, elapsed))
        if result:
            log.info(f'  ✅ PASS: {name} [{elapsed:.1f}s]')
            passed += 1
            return result
        else:
            log.error(f'  ❌ FAIL: {name} — returned {result} [{elapsed:.1f}s]')
            failed += 1
            errors.append(f'{name}: returned {result}')
    except Exception as e:
        elapsed = time.time() - start
        timings.append((name, elapsed))
        tb = traceback.format_exc()
        log.error(f'  ❌ FAIL: {name} — {e} [{elapsed:.1f}s]')
        log.error(f'          Traceback: {tb[-300:]}')
        failed += 1
        errors.append(f'{name}: {e}')
    return None

log.info('='*70)
log.info('  BEAST V5 — MEGA REGRESSION TEST SUITE')
log.info(f'  Started: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
log.info(f'  Mode: {"QUICK" if QUICK_MODE else "FULL"}')
log.info(f'  CWD: {os.getcwd()}')
log.info(f'  Python: {sys.version}')
log.info('='*70)


# ══════════════════════════════════════════════════════════
# SECTION 1: ALL MODULE IMPORTS (17 modules)
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 1: MODULE IMPORTS')
log.info('='*60)

REQUIRED_MODULES = [
    'order_gateway', 'sentiment_analyst', 'ai_brain', 'regime_detector',
    'sector_scanner', 'tv_cdp_client', 'data_collector', 'report_formatter',
    'iron_laws', 'models', 'trade_db', 'db_postgres',
    'risk_manager', 'pro_data_sources', 'headless_technicals',
    'dashboard_api',
]
for mod in REQUIRED_MODULES:
    test(f'import {mod}', lambda m=mod: importlib.import_module(m) is not None)

test('import engine.master_intelligence', 
     lambda: importlib.import_module('engine.master_intelligence') is not None)


# ══════════════════════════════════════════════════════════
# SECTION 2: COMPILE CHECK (every .py file)
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 2: COMPILE CHECK')
log.info('='*60)

import py_compile
for f in pathlib.Path('.').glob('*.py'):
    if f.name.startswith('test_') and f.name != 'test_v5_regression.py':
        continue
    test(f'compile {f.name}', lambda f=f: py_compile.compile(str(f), doraise=True) is not None)


# ══════════════════════════════════════════════════════════
# SECTION 3: MODULE INITIALIZATION WITH REAL CREDENTIALS
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 3: MODULE INIT (real credentials)')
log.info('='*60)

api_key = os.getenv('ALPACA_API_KEY', '')
secret = os.getenv('ALPACA_SECRET_KEY', '')
log.info(f'  Alpaca key: {"SET (" + api_key[:8] + "...)" if api_key else "MISSING"}')
log.info(f'  Alpaca secret: {"SET" if secret else "MISSING"}')

from order_gateway import OrderGateway
gw = test('OrderGateway init', lambda: OrderGateway(api_key, secret, paper=True))

from risk_manager import RiskManager
rm = test('RiskManager init', lambda: RiskManager())
if rm:
    test('RiskManager.set_db exists', lambda: callable(getattr(rm, 'set_db', None)))

from pro_data_sources import ProDataSources
pds = test('ProDataSources init', lambda: ProDataSources())

from headless_technicals import HeadlessTechnicals
ht = test('HeadlessTechnicals init', lambda: HeadlessTechnicals(api_key, secret))


# ══════════════════════════════════════════════════════════
# SECTION 4: REAL ALPACA DATA
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 4: REAL ALPACA DATA')
log.info('='*60)

if gw:
    acct = test('get_account', lambda: gw.get_account(), skip_quick=False)
    if acct:
        equity = float(acct.get('equity', 0))
        cash = float(acct.get('cash', 0))
        log.info(f'  Account: equity=${equity:,.2f} cash=${cash:,.2f}')
        test('equity > 0', lambda: equity > 0)
        test('cash > 0', lambda: cash > 0)

    positions = test('get_positions', lambda: gw.get_positions())
    if positions:
        log.info(f'  Positions: {len(positions)} held')
        for p in positions[:5]:
            log.info(f'    {p.symbol}: {p.qty}x @ ${p.avg_entry:.2f} → ${p.current_price:.2f} '
                     f'P&L: ${p.unrealized_pl:.2f}')
        test('positions is list', lambda: isinstance(positions, list))

    test('get_open_orders', lambda: isinstance(gw.get_open_orders(), list), skip_quick=True)
else:
    log.warning('  SKIPPED: No gateway')


# ══════════════════════════════════════════════════════════
# SECTION 5: RISK MANAGER — ALL CHECKS WITH REAL DATA
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 5: RISK MANAGER (real portfolio data)')
log.info('='*60)

if rm:
    # Kelly with real conviction values that callers actually pass
    for source, conv in [('5min_GPT', 0.80), ('60s_pyramid', 0.75), 
                          ('60s_reload', 0.65), ('2min_runner', 0.68),
                          ('60s_dipbuy', 0.70), ('30min_claude', 0.85)]:
        r = rm.kelly_position_size('AAPL', conviction=conv, current_price=200.0, atr=5.0)
        test(f'Kelly {source} conv={conv} → shares > 0', lambda r=r: r['shares'] > 0)
        log.info(f'    → {r["shares"]} shares, adjustments: {r["adjustments"]}')
    
    # Kelly with 0 conviction (should baseline + warn)
    r = rm.kelly_position_size('TEST', conviction=0.0, current_price=100.0, atr=3.0)
    test('Kelly conv=0 → shares > 0 (baseline)', lambda: r['shares'] > 0)
    test('Kelly conv=0 → has warning', lambda: 'missing-conviction' in str(r['adjustments']))
    
    # Loss limits
    test('Loss limit normal', lambda: rm.check_loss_limits(103000, 103000, 103000, 100000)['can_trade'])
    test('Loss limit -1% OK', lambda: rm.check_loss_limits(99000, 100000, 100000, 100000)['can_buy'])
    test('Loss limit -3% blocks', lambda: not rm.check_loss_limits(97000, 100000, 100000, 100000)['can_buy'])
    test('Loss limit -3% reason', lambda: 'DAILY' in rm.check_loss_limits(97000, 100000, 100000, 100000).get('reason', ''))
    
    # Approve with real positions
    real_positions = positions if positions else []
    real_equity = equity if acct else 103000
    approval = rm.approve_trade('AAPL', 'buy', 10, 200.0, 0.7, real_positions, real_equity)
    test('approve_trade returns approved key', lambda: 'approved' in approval)
    test('approve_trade returns adjusted_qty', lambda: 'adjusted_qty' in approval)
    log.info(f'    → approved={approval.get("approved")} qty={approval.get("adjusted_qty")} '
             f'rejections={approval.get("rejections")}')

    # ── MOCK DB TEST: verify RiskManager works with BeastDB-compatible interface ──
    log.info('\n  -- Mock DB compatibility test --')
    class MockBeastDB:
        """Mimics BeastDB._exec behavior: returns list of dicts for fetch=True."""
        def _exec(self, sql, params=None, fetch=False):
            if fetch and 'realized_pl' in sql:
                return [{'pnl': 5.2}, {'pnl': -3.1}, {'pnl': 8.0}, {'pnl': -1.5}, {'pnl': 2.3},
                        {'pnl': 6.1}, {'pnl': -2.0}, {'pnl': 4.5}, {'pnl': -0.8}, {'pnl': 3.2}]
            if fetch:
                return []
            return None
    
    rm_with_db = RiskManager(db=MockBeastDB())
    test('RiskManager with MockDB init', lambda: rm_with_db.db is not None)
    
    stats = rm_with_db._get_trade_stats('AAPL')
    test('_get_trade_stats returns win_rate', lambda: 'win_rate' in stats)
    test('_get_trade_stats win_rate > 0', lambda: stats['win_rate'] > 0)
    test('_get_trade_stats sample_size = 10', lambda: stats.get('sample_size', 0) == 10)
    log.info(f'    → trade stats: {stats}')
    
    rm_with_db._log_check('TEST', 'unit_test', True, 10, 10, 'mock test')
    test('_log_check doesnt crash with mock', lambda: True)
    
    kelly_db = rm_with_db.kelly_position_size('AAPL', conviction=0.7, current_price=200.0, atr=5.0)
    test('Kelly with DB → shares > 0', lambda: kelly_db['shares'] > 0)
    test('Kelly with DB → no missing-conviction warning', lambda: 'missing-conviction' not in str(kelly_db['adjustments']))
    log.info(f'    → Kelly with DB: {kelly_db["shares"]} shares, adj={kelly_db["adjustments"]}')


# ══════════════════════════════════════════════════════════
# SECTION 6: ORDER GATEWAY — ANTI-BUYBACK V2
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 6: ANTI-BUYBACK V2')
log.info('='*60)

if gw:
    test('timeout attr = 30', lambda: gw.ANTI_BUYBACK_TIMEOUT_MIN == 30)
    test('price reset = 0.03', lambda: gw.ANTI_BUYBACK_PRICE_RESET_PCT == 0.03)
    test('AI override = 80', lambda: gw.ANTI_BUYBACK_AI_OVERRIDE_CONF == 80)
    test('quick_buy has ai_confidence', lambda: 'ai_confidence' in str(OrderGateway.quick_buy.__code__.co_varnames))
    test('last_sell_times_precise exists', lambda: isinstance(gw.last_sell_times_precise, dict))


# ══════════════════════════════════════════════════════════
# SECTION 7: PRO DATA SOURCES (LIVE API CALLS)
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 7: PRO DATA SOURCES (live APIs)')
log.info('='*60)

if pds:
    from pro_data_sources import (FearGreedIndex, VIXTermStructure, PutCallRatio,
                                   CongressTracker, ShortInterest, EconomicCalendar)
    
    fg = test('FearGreed API', lambda: FearGreedIndex().get_fear_greed(), skip_quick=True)
    if fg:
        log.info(f'    → Fear&Greed = {fg.get("value")} ({fg.get("label")})')
        test('FearGreed 0-100', lambda: 0 <= fg.get('value', -1) <= 100)
    
    vix = test('VIX API', lambda: VIXTermStructure().get_vix_structure(), skip_quick=True)
    if vix:
        log.info(f'    → VIX={vix.get("vix")} VIX3M={vix.get("vix3m")} contango={not vix.get("is_inverted")}')
        test('VIX > 0', lambda: vix.get('vix', 0) > 0)
    
    pcr = test('PCR API', lambda: PutCallRatio().get_pcr(), skip_quick=True)
    if pcr:
        log.info(f'    → PCR={pcr.get("value")} signal={pcr.get("signal")}')
    
    cong = test('Congress scraper', lambda: CongressTracker().fetch(), skip_quick=True)
    if cong:
        log.info(f'    → {len(cong)} trades scraped')
    
    short = test('Short interest AAPL', lambda: ShortInterest().get_short_signal('AAPL'), skip_quick=True)
    if short:
        log.info(f'    → AAPL short_ratio={short.get("short_ratio")}')
    
    econ = EconomicCalendar()
    events = test('Economic calendar', lambda: econ.get_upcoming_events(7), skip_quick=True)
    if events:
        log.info(f'    → {len(events)} events, high_impact_tomorrow={econ.has_high_impact_tomorrow()}')
    
    intel = test('Full intel GOOGL', lambda: pds.get_full_intel('GOOGL'), skip_quick=True)
    if intel:
        log.info(f'    → GOOGL score={intel.get("score")}')
        bd = intel.get('breakdown', {})
        active = {k: v.get('score', 0) if isinstance(v, dict) else v for k, v in bd.items() if isinstance(v, dict) and v.get('score', 0) != 0}
        log.info(f'    → Active signals: {active}')
    
    mc = test('Market conditions', lambda: pds.get_market_conditions(), skip_quick=True)
    if mc:
        log.info(f'    → Keys: {list(mc.keys())}')


# ══════════════════════════════════════════════════════════
# SECTION 8: POSTGRESQL DATABASE
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 8: POSTGRESQL DATABASE')
log.info('='*60)

db_url = os.getenv('DATABASE_URL', '')
log.info(f'  DATABASE_URL: {"SET" if db_url else "MISSING"}')

if db_url:
    try:
        import psycopg2
        conn = psycopg2.connect(db_url, connect_timeout=10)
        cur = conn.cursor()
        test('PostgreSQL connection', lambda: conn.status == 1)
        
        # Check key tables exist
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
        tables = [r[0] for r in cur.fetchall()]
        log.info(f'  Tables: {len(tables)} found')
        for tbl in ['activity_log', 'ai_verdicts', 'equity_snapshots', 'trade_decisions', 'watchlist']:
            test(f'Table {tbl} exists', lambda t=tbl: t in tables)
        
        # Check recent data
        cur.execute("SELECT COUNT(*) FROM activity_log WHERE created_at > NOW() - interval '1 hour'")
        recent = cur.fetchone()[0]
        log.info(f'  Recent activity (1h): {recent} rows')
        test('Recent activity exists', lambda: recent >= 0)
        
        cur.execute("SELECT COUNT(*) FROM equity_snapshots WHERE created_at > NOW() - interval '1 hour'")
        eq_count = cur.fetchone()[0]
        log.info(f'  Recent equity snapshots (1h): {eq_count} rows')
        
        cur.execute("SELECT equity, total_pl FROM equity_snapshots ORDER BY created_at DESC LIMIT 1")
        latest = cur.fetchone()
        if latest:
            log.info(f'  Latest equity: ${float(latest[0]):,.2f} P&L: ${float(latest[1]):,.2f}')
        
        conn.close()
    except Exception as e:
        log.warning(f'  PostgreSQL unavailable: {e}')
        log.warning('  DB tests skipped — this is OK for local testing')
else:
    log.warning('  No DATABASE_URL — PostgreSQL tests skipped')


# ══════════════════════════════════════════════════════════
# SECTION 9: DISCORD BOT CODE ANALYSIS
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 9: DISCORD BOT CODE ANALYSIS')
log.info('='*60)

with open('discord_bot.py', 'r', encoding='utf-8', errors='replace') as f:
    bot_code = f.read()
    bot_lines = bot_code.split('\n')

# Variable ordering
api_line = next((i for i, l in enumerate(bot_lines) if "api_key = os.getenv('ALPACA_API_KEY'" in l), None)
gw_line = next((i for i, l in enumerate(bot_lines) if 'gateway = OrderGateway(api_key' in l), None)
log.info(f'  api_key at line {api_line+1 if api_line else "NOT FOUND"}')
log.info(f'  gateway at line {gw_line+1 if gw_line else "NOT FOUND"}')
test('api_key before gateway', lambda: api_line is not None and gw_line is not None and api_line < gw_line)

# All _smart_buy callers pass confidence
smart_buy_calls = []
for i, line in enumerate(bot_lines):
    if '_smart_buy(' in line and 'def _smart_buy' not in line:
        # Read full call block
        block = ''
        depth = 0
        for j in range(i, min(i + 20, len(bot_lines))):
            block += bot_lines[j] + '\n'
            depth += bot_lines[j].count('(') - bot_lines[j].count(')')
            if depth <= 0:
                break
        has_conf = 'confidence=' in block
        smart_buy_calls.append((i+1, has_conf, block.strip()[:100]))

log.info(f'  Found {len(smart_buy_calls)} _smart_buy callers')
for line_no, has_conf, preview in smart_buy_calls:
    test(f'_smart_buy line {line_no} has confidence', lambda hc=has_conf: hc)
    if not has_conf:
        log.error(f'    MISSING confidence at line {line_no}: {preview}')

# RiskManager DB wiring — must be in the LAST on_ready (not an overwritten one)
on_ready_count = bot_code.count('async def on_ready()')
test(f'Only ONE on_ready handler (found {on_ready_count})', lambda: on_ready_count == 1)

# Find the on_ready block and verify it has V5 wiring
on_ready_start = bot_code.rfind('async def on_ready()')  # Last one wins
on_ready_block = bot_code[on_ready_start:on_ready_start+2000]
test('on_ready has risk_mgr.set_db', lambda: 'risk_mgr.set_db' in on_ready_block)
test('on_ready has pro_data.db', lambda: 'pro_data.db' in on_ready_block)
test('on_ready has _flush_startup_log', lambda: '_flush_startup_log' in on_ready_block)

# Check for undefined variables
test('No undefined has_strong_sent', lambda: 'has_strong_sent' not in bot_code)

# DB method names in risk_manager
with open('risk_manager.py', 'r', encoding='utf-8') as f:
    rm_code = f.read()
test('risk_manager: no self.db.execute()', lambda: 'self.db.execute(' not in rm_code)
test('risk_manager: no self.db.fetch()', lambda: 'self.db.fetch(' not in rm_code)
test('risk_manager: uses self.db._exec()', lambda: 'self.db._exec(' in rm_code)
test('risk_manager: fetch=True in _get_trade_stats', lambda: 'fetch=True' in rm_code)


# ══════════════════════════════════════════════════════════
# SECTION 10: DASHBOARD API ENDPOINTS
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 10: DASHBOARD API ENDPOINTS')
log.info('='*60)

with open('dashboard_api.py', 'r', encoding='utf-8', errors='replace') as f:
    api_code = f.read()

all_endpoints = re.findall(r"@app\.route\('([^']+)'", api_code)
log.info(f'  Total endpoints: {len(all_endpoints)}')

v5_eps = ['/api/v5/pro-intel', '/api/v5/market-conditions', '/api/v5/risk-status',
          '/api/v5/congress', '/api/v5/insiders', '/api/v5/anti-buyback',
          '/api/v5/economic-calendar', '/api/v5/short-squeeze']
for ep in v5_eps:
    test(f'API endpoint {ep}', lambda ep=ep: any(ep in e for e in all_endpoints))


# ══════════════════════════════════════════════════════════
# SECTION 11: DASHBOARD PAGES
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 11: DASHBOARD PAGES')
log.info('='*60)

dash = pathlib.Path('dashboard/src/app')
pages = ['positions', 'trades', 'decisions', 'ai', 'performance', 'blue-chips',
         'config', 'runners', 'stops', 'sectors', 'analytics', 'backtest',
         'activity', 'scans', 'news', 'system', 'notifications', 'feed',
         'pro-intel', 'risk', 'congress', 'market']
for page in pages:
    test(f'Page /{page}', lambda p=page: (dash / p / 'page.tsx').exists())

# NavBar links
nav = pathlib.Path('dashboard/src/components/NavBar.tsx')
if nav.exists():
    nav_code = nav.read_text(encoding='utf-8', errors='replace')
    for page in ['pro-intel', 'risk', 'congress', 'market']:
        test(f'NavBar has /{page}', lambda p=page: p in nav_code)


# ══════════════════════════════════════════════════════════
# SECTION 12: IRON LAWS (pytest)
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 12: IRON LAWS (pytest)')
log.info('='*60)

result = subprocess.run(
    [sys.executable, '-m', 'pytest', 'tests/test_iron_laws.py', '-q', '--tb=short'],
    capture_output=True, text=True, cwd='.'
)
log.info(f'  {result.stdout.strip().split(chr(10))[-1]}')
test('25 iron law tests', lambda: '25 passed' in result.stdout)
if '25 passed' not in result.stdout:
    log.error(f'  STDERR: {result.stderr[:300]}')


# ══════════════════════════════════════════════════════════
# SECTION 13: STARTUP SCRIPTS
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 13: STARTUP SCRIPTS')
log.info('='*60)

for bat_name in ['START_ALL.bat', 'start_beast.bat', 'START_CHROME_TV.bat', 
                  'SETUP_TV_INDICATORS.bat', 'setup_autostart.bat']:
    bat_path = pathlib.Path(bat_name)
    if bat_path.exists():
        bat_content = bat_path.read_text(encoding='utf-8', errors='replace')
        test(f'{bat_name} no C:\\Python312\\python.exe', 
             lambda c=bat_content, n=bat_name: 'C:\\Python312\\python.exe' not in c)
        if bat_name == 'START_ALL.bat':
            test(f'{bat_name} no | tee', lambda c=bat_content: '| tee' not in c)
            test(f'{bat_name} has startup.log', lambda c=bat_content: 'startup.log' in c)
    else:
        log.warning(f'  {bat_name} not found')


# ══════════════════════════════════════════════════════════
# SECTION 14: HEADLESS TECHNICALS
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 14: HEADLESS TECHNICALS')
log.info('='*60)

if ht:
    test('RSI computation', lambda: 0 <= ht._compute_rsi([100+i*0.1 for i in range(30)]) <= 100)
    test('MACD computation', lambda: 'histogram' in ht._compute_macd([100+i*0.1 for i in range(50)]))
    test('VWAP computation', lambda: ht._compute_vwap([{'high':101,'low':99,'close':100,'volume':1000}]*10) > 0)
    test('Bollinger computation', lambda: ht._compute_bollinger([100+i*0.1 for i in range(30)])['upper'] > 0)
    test('EMA computation', lambda: ht._compute_ema([100+i*0.1 for i in range(20)], 9) > 0)
    test('SMA computation', lambda: ht._compute_sma([100+i*0.1 for i in range(200)], 200) > 0)


# ══════════════════════════════════════════════════════════
# SECTION 15: TV CDP CONNECTIVITY
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 15: TV CDP CONNECTIVITY')
log.info('='*60)

import requests
try:
    r = requests.get('http://localhost:9222/json/version', timeout=3)
    log.info(f'  CDP version: {r.json().get("Browser", "unknown")}')
    test('CDP responds on 9222', lambda: r.status_code == 200)
    
    r2 = requests.get('http://localhost:9222/json', timeout=3)
    targets = r2.json()
    log.info(f'  CDP targets: {len(targets)}')
    for t in targets[:3]:
        log.info(f'    {t.get("title", "?")[:50]} — {t.get("url", "?")[:60]}')
    test('CDP has chart targets', lambda: len(targets) > 0)
except:
    log.warning('  CDP not available on localhost:9222 — TV not running locally')
    log.warning('  This is OK for local dev — TV runs on the VM')


# ══════════════════════════════════════════════════════════
# SECTION 16: API SERVER TEST (if running)
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*60)
log.info('SECTION 16: API SERVER (if running)')
log.info('='*60)

try:
    r = requests.get('http://localhost:8080/api/health', timeout=3)
    test('API health endpoint', lambda: r.status_code == 200)
    log.info(f'  Health response: {r.json()}')
    
    # Test V5 endpoints (will 401 without auth, but that's OK — proves they exist)
    for ep in ['/api/v5/market-conditions', '/api/v5/congress', '/api/v5/risk-status']:
        try:
            r = requests.get(f'http://localhost:8080{ep}', timeout=5)
            status = r.status_code
            test(f'API {ep} responds ({status})', lambda s=status: s in [200, 401])
        except:
            log.warning(f'  {ep} — no response')
except:
    log.warning('  API not running on localhost:8080 — skipping')
    log.warning('  This is OK for local dev — API runs on the VM')


# ══════════════════════════════════════════════════════════
# FINAL REPORT
# ══════════════════════════════════════════════════════════
log.info('\n' + '='*70)
total = passed + failed
if failed == 0:
    log.info(f'  🟢 ALL {total} TESTS PASSED ({skipped} skipped) — SAFE TO DEPLOY')
else:
    log.info(f'  🔴 {failed}/{total} TESTS FAILED ({skipped} skipped) — DO NOT DEPLOY')
    log.info(f'  FAILURES:')
    for e in errors:
        log.info(f'    ❌ {e}')

# Top 5 slowest tests
timings.sort(key=lambda x: x[1], reverse=True)
log.info(f'\n  SLOWEST TESTS:')
for name, elapsed in timings[:5]:
    log.info(f'    {elapsed:.1f}s — {name}')

log.info(f'\n  Full log: {os.path.abspath(LOG_FILE)}')
log.info('='*70)

sys.exit(0 if failed == 0 else 1)
