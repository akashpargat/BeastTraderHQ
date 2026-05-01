import sys, io
if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
"""
Beast v2.0 — Discord Bot
━━━━━━━━━━━━━━━━━━━━━━━━
Interactive trading bot on Discord with commands:

  !g              — Run full Beast Mode scan
  !positions      — Show all positions with P&L
  !scan NVDA      — Deep scan a single stock (TV + sentiment + AI)
  !confidence     — Show confidence scores for all stocks
  !sectors        — Show sector rotation alerts
  !runners        — Show today's top runners
  !dumpers        — Show today's biggest losers (Akash Method candidates)
  !sentiment      — Full market sentiment report
  !earnings       — Earnings calendar for held stocks
  !pnl            — Portfolio P&L summary
  !risk           — Risk dashboard
  !ai NVDA        — Claude Opus 4.7 deep analysis on one stock
  !debate NVDA    — Bull vs Bear AI debate
  !help           — Show all commands

Also sends automatic alerts to the configured channel:
  🚨 Sudden drops, 📊 Hourly summaries, 🔥 Sector alerts
"""
import os
import sys
import asyncio
import logging
import traceback
import time
import subprocess
import discord
from discord.ext import commands, tasks
from datetime import datetime
from zoneinfo import ZoneInfo

# ── VERSION TRACKING ──
BOT_VERSION = "4.2.0"
try:
    _git_hash = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'],
                                         stderr=subprocess.DEVNULL, cwd=os.path.dirname(os.path.abspath(__file__))
                                         ).decode().strip()
    _git_date = subprocess.check_output(['git', 'log', '-1', '--format=%ci', '--date=short'],
                                         stderr=subprocess.DEVNULL, cwd=os.path.dirname(os.path.abspath(__file__))
                                         ).decode().strip()[:16]
except:
    _git_hash = "unknown"
    _git_date = "unknown"
BOT_BUILD = f"v{BOT_VERSION} ({_git_hash} @ {_git_date})"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv('.env')

from order_gateway import OrderGateway
from sentiment_analyst import SentimentAnalyst
from ai_brain import AIBrain
from regime_detector import RegimeDetector
from sector_scanner import SectorScanner
from engine.master_intelligence import (
    MasterConfidenceEngine, PAST_WINNERS, get_all_scan_symbols,
    get_stock_profile, FULL_SECTOR_SCAN
)
from tv_cdp_client import TVClient
from data_collector import DataCollector
from report_formatter import format_beast_report

ET = ZoneInfo("America/New_York")
log = logging.getLogger('Beast.Discord')

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')

# ── Bot Setup ──────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Components
api_key = os.getenv('ALPACA_API_KEY', '')
secret = os.getenv('ALPACA_SECRET_KEY', '')
gateway = OrderGateway(api_key, secret, paper=True)
sentiment = SentimentAnalyst()
confidence = MasterConfidenceEngine()
regime_det = RegimeDetector()
sectors_scanner = SectorScanner()
brain = AIBrain()
tv = TVClient()
dc = DataCollector(api_key, secret)

# ── V5 PRO MODULES ──
risk_mgr = None
try:
    from risk_manager import RiskManager
    risk_mgr = RiskManager()
    log.info("✅ [V5] RiskManager loaded — Kelly sizing, loss limits, correlation, sector caps")
except Exception as e:
    log.warning(f"⚠️ [V5] RiskManager not available: {e}")

pro_data = None
try:
    from pro_data_sources import ProDataSources
    pro_data = ProDataSources()
    log.info("✅ [V5] ProDataSources loaded — congress, insider, PCR, VIX, dark pool, Fear&Greed")
except Exception as e:
    log.warning(f"⚠️ [V5] ProDataSources not available: {e}")

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockSnapshotRequest
data_client = StockHistoricalDataClient(api_key, secret)


@bot.event
async def on_ready():
    log.info(f'🦍 Beast Discord Bot online as {bot.user}')
    log.info(f'   AI Brain: {"✅ Opus 4.7" if brain.is_available else "❌ offline"}')
    log.info(f'   TradingView: {"✅" if tv.health_check() else "❌"}')


# ── !help ──────────────────────────────────────────────

@bot.command(name='help')
async def help_cmd(ctx):
    embed = discord.Embed(
        title="🦍 Beast Trading Bot — Commands",
        color=0xFF6600,
        description="Your AI-powered trading assistant"
    )
    embed.add_field(name="📊 Market", value=(
        "`!g` — Full Beast Mode scan\n"
        "`!positions` — All positions + P&L\n"
        "`!pnl` — Portfolio summary\n"
        "`!risk` — Risk dashboard"
    ), inline=False)
    embed.add_field(name="🔍 Analysis", value=(
        "`!scan NVDA` — Deep scan one stock\n"
        "`!confidence` — All confidence scores\n"
        "`!ai NVDA` — AI deep analysis\n"
        "`!debate NVDA` — Bull vs Bear debate"
    ), inline=False)
    embed.add_field(name="📈 Discovery", value=(
        "`!runners` — Top movers today\n"
        "`!dumpers` — Biggest losers (dip buys?)\n"
        "`!sectors` — Sector rotation alerts\n"
        "`!sentiment` — Full market sentiment\n"
        "`!earnings` — Earnings calendar"
    ), inline=False)
    embed.add_field(name="🔬 Backtesting", value=(
        "`!backtest NVDA` — Backtest one stock (TV data)\n"
        "`!backtest NVDA 500` — Custom bar count\n"
        "`!backtest_all` — Backtest 18 stocks\n"
        "`!performance` — Win rate & P&L analytics"
    ), inline=False)
    embed.add_field(name="🎮 Remote Control", value=(
        "`!full_scan` — 🦍 THE BIG ONE (all phases + AI + proposals)\n"
        "`!pending` — Show pending trade proposals\n"
        "`!approve NVDA` — Execute a proposed trade\n"
        "`!reject NVDA` — Skip a proposed trade\n"
        "`!reject_all` — Clear all proposals"
    ), inline=False)
    embed.set_footer(text="🧠 Powered by Claude Opus 4.7 | 📺 TradingView Premium | Iron Laws: HARDCODED")
    await ctx.send(embed=embed)


# ── !positions ─────────────────────────────────────────

@bot.command(name='positions')
async def positions_cmd(ctx):
    positions = gateway.get_positions()
    acct = gateway.get_account()
    total_pl = sum(p.unrealized_pl for p in positions)

    embed = discord.Embed(
        title="📦 POSITIONS",
        color=0x00FF00 if total_pl > 0 else 0xFF0000,
    )
    embed.add_field(name="💰 Equity", value=f"${acct.get('equity', 0):,.2f}", inline=True)
    embed.add_field(name="📈 P&L", value=f"${total_pl:+,.2f}", inline=True)
    embed.add_field(name="📊 Count", value=str(len(positions)), inline=True)

    sorted_pos = sorted(positions, key=lambda p: p.unrealized_pl, reverse=True)
    lines = []
    for p in sorted_pos:
        emoji = "🟢" if p.is_green else "🔴"
        lines.append(f"{emoji} **{p.symbol}** {p.qty}x `${p.current_price:.2f}` "
                     f"`${p.unrealized_pl:+.2f}` ({p.unrealized_pl_pct:+.1%})")

    embed.add_field(name="Stocks", value="\n".join(lines) or "No positions", inline=False)
    embed.set_footer(text=f"🔒 Iron Law 1: Red = HOLD | {datetime.now(ET).strftime('%H:%M ET')}")
    await ctx.send(embed=embed)


# ── !pnl ───────────────────────────────────────────────

@bot.command(name='pnl')
async def pnl_cmd(ctx):
    positions = gateway.get_positions()
    acct = gateway.get_account()
    total = sum(p.unrealized_pl for p in positions)
    green = [p for p in positions if p.is_green]
    red = [p for p in positions if p.is_red]

    embed = discord.Embed(title="💰 P&L SUMMARY", color=0x00FF00 if total > 0 else 0xFF0000)
    embed.add_field(name="Total P&L", value=f"${total:+,.2f}", inline=True)
    embed.add_field(name="Equity", value=f"${acct.get('equity', 0):,.2f}", inline=True)
    embed.add_field(name="🟢 Green", value=f"{len(green)} stocks", inline=True)
    embed.add_field(name="🔴 Red", value=f"{len(red)} stocks (HELD)", inline=True)

    if total <= -500:
        embed.add_field(name="⛔ KILL SWITCH", value="P&L exceeds -$500!", inline=False)

    await ctx.send(embed=embed)


# ── !runners ───────────────────────────────────────────

@bot.command(name='runners')
async def runners_cmd(ctx):
    await ctx.send("🏃 Scanning all 48 symbols...")
    all_scan = get_all_scan_symbols()
    movers = []

    for i in range(0, len(all_scan), 20):
        batch = all_scan[i:i+20]
        try:
            req = StockSnapshotRequest(symbol_or_symbols=batch, feed='iex')
            snaps = data_client.get_stock_snapshot(req)
            for sym, snap in snaps.items():
                if snap.daily_bar and snap.previous_daily_bar:
                    price = float(snap.daily_bar.close)
                    prev = float(snap.previous_daily_bar.close)
                    change = (price - prev) / prev
                    movers.append({'symbol': sym, 'change_pct': change, 'price': price})
        except:
            pass

    runners = sorted([m for m in movers if m['change_pct'] > 0.01],
                     key=lambda x: x['change_pct'], reverse=True)

    embed = discord.Embed(title="🏃💨 TOP RUNNERS", color=0x00FF00)
    lines = []
    for r in runners[:12]:
        star = "⭐" if r['symbol'] in PAST_WINNERS else "🏃"
        lines.append(f"{star} **{r['symbol']}** `{r['change_pct']:+.2%}` @ ${r['price']:.2f}")
    embed.description = "\n".join(lines) or "No runners >1% today"
    embed.set_footer(text="⭐ = Past Winner (priority)")
    await ctx.send(embed=embed)


# ── !dumpers ───────────────────────────────────────────

@bot.command(name='dumpers')
async def dumpers_cmd(ctx):
    await ctx.send("📉 Scanning for dips...")
    all_scan = get_all_scan_symbols()
    movers = []

    for i in range(0, len(all_scan), 20):
        batch = all_scan[i:i+20]
        try:
            req = StockSnapshotRequest(symbol_or_symbols=batch, feed='iex')
            snaps = data_client.get_stock_snapshot(req)
            for sym, snap in snaps.items():
                if snap.daily_bar and snap.previous_daily_bar:
                    price = float(snap.daily_bar.close)
                    prev = float(snap.previous_daily_bar.close)
                    change = (price - prev) / prev
                    movers.append({'symbol': sym, 'change_pct': change, 'price': price})
        except:
            pass

    dumpers = sorted([m for m in movers if m['change_pct'] < -0.02],
                     key=lambda x: x['change_pct'])

    embed = discord.Embed(title="📉🎯 DUMPERS — Akash Method?", color=0xFF0000)
    lines = []
    for d in dumpers[:10]:
        lines.append(f"💀 **{d['symbol']}** `{d['change_pct']:+.2%}` @ ${d['price']:.2f}")
    embed.description = "\n".join(lines) or "No dumps >2% today"
    embed.set_footer(text="Watch for RSI<30 → Buy dip → Limit sell +2% → Repeat 🔁")
    await ctx.send(embed=embed)


# ── !sentiment ─────────────────────────────────────────

@bot.command(name='sentiment')
async def sentiment_cmd(ctx):
    await ctx.send("📰 Scanning 5 sentiment sources...")
    mkt = sentiment.full_market_sentiment()

    embed = discord.Embed(title="📰 MARKET SENTIMENT", color=0x3498DB)
    embed.add_field(name="Total Score", value=f"{mkt['total_score']:+d}/25", inline=True)
    embed.add_field(name="Action", value=mkt['action'], inline=True)
    embed.add_field(name="Yahoo", value=f"{mkt['yahoo_score']:+d}/5", inline=True)
    embed.add_field(name="Reddit", value=f"{mkt['reddit_score']:+d}/5", inline=True)
    embed.add_field(name="Analyst", value=f"{mkt['analyst_score']:+d}/5", inline=True)
    embed.add_field(name="🏛️ Trump", value=f"{mkt['trump_score']:+d}/5", inline=True)
    embed.add_field(name="📰 Breaking", value=f"{mkt['breaking_score']:+d}/5", inline=True)
    embed.add_field(name="🌍 Geopolitical", value=f"{mkt['geopolitical_score']:+d}/5", inline=True)

    if mkt.get('trump_headlines'):
        embed.add_field(name="🏛️ Trump Headlines",
                       value="\n".join(f"• {h[:60]}" for h in mkt['trump_headlines'][:3]),
                       inline=False)
    await ctx.send(embed=embed)


# ── !scan SYMBOL ───────────────────────────────────────

@bot.command(name='scan')
async def scan_cmd(ctx, symbol: str = None):
    if not symbol:
        await ctx.send("Usage: `!scan NVDA`")
        return

    symbol = symbol.upper()
    await ctx.send(f"📺🧠 Deep scanning **{symbol}**...")

    # TV scan
    tv_data = {}
    if tv.health_check():
        tv._connect()
        tv.set_symbol(symbol)
        await asyncio.sleep(3)
        studies = tv.get_study_values()
        quote = tv.get_quote()
        tv_data = {'studies': studies, 'quote': quote}

    # Sentiment
    sent = sentiment.analyze(symbol)

    # Snapshot
    snap_data = {}
    try:
        req = StockSnapshotRequest(symbol_or_symbols=symbol, feed='iex')
        snaps = data_client.get_stock_snapshot(req)
        if symbol in snaps:
            s = snaps[symbol]
            snap_data = {
                'price': float(s.daily_bar.close),
                'prev_close': float(s.previous_daily_bar.close),
                'change_pct': (float(s.daily_bar.close) - float(s.previous_daily_bar.close)) / float(s.previous_daily_bar.close)
            }
    except:
        pass

    # Parse TV data
    rsi, macd, vwap = '?', '?', '?'
    for s in tv_data.get('studies', []):
        name = s.get('name', '')
        vals = s.get('values', {})
        if 'Relative Strength' in name: rsi = vals.get('RSI', '?')
        elif name == 'MACD': macd = vals.get('Histogram', '?')
        elif name == 'VWAP': vwap = vals.get('VWAP', '?')

    embed = discord.Embed(title=f"🔍 DEEP SCAN: {symbol}", color=0x9B59B6)
    embed.add_field(name="💲 Price", value=f"${snap_data.get('price', 0):.2f}", inline=True)
    embed.add_field(name="📊 Change", value=f"{snap_data.get('change_pct', 0):+.2%}", inline=True)
    embed.add_field(name="📈 RSI", value=str(rsi), inline=True)
    embed.add_field(name="📉 MACD", value=str(macd), inline=True)
    embed.add_field(name="📍 VWAP", value=str(vwap), inline=True)
    embed.add_field(name="📰 Sentiment", value=f"Yahoo {sent.yahoo_score:+d} | Reddit {sent.reddit_score:+d} | Analyst {sent.analyst_score:+d}", inline=False)

    profile = get_stock_profile(symbol)
    embed.add_field(name="📂 Sector", value=", ".join(profile.get('sectors', ['unknown'])), inline=True)
    embed.add_field(name="📊 Type", value=profile.get('type', 'unknown'), inline=True)

    # AI analysis
    if brain.is_available:
        try:
            rsi_f = float(str(rsi).replace('\u2212', '-')) if rsi != '?' else 50
        except:
            rsi_f = 50

        ai = brain.analyze_stock(symbol, {
            'price': snap_data.get('price', 0), 'rsi': rsi_f,
            'macd_hist': 0, 'vwap_above': False, 'volume_ratio': 1.0,
            'yahoo_score': sent.yahoo_score, 'analyst_score': sent.analyst_score,
            'reddit_score': sent.reddit_score, 'trump_score': 0,
            'regime': regime_det.current_regime.value,
            'sector': profile.get('sectors', ['?'])[0] if profile.get('sectors') else '?',
            'earnings_days': 999, 'holding': symbol in [p.symbol for p in gateway.get_positions()],
            'unrealized_pl': 0, 'bb_position': 'mid', 'confluence': 5,
            'ema_9': 0, 'ema_21': 0,
        })
        action_emoji = {"BUY": "🟢", "HOLD": "🟡", "SELL": "🔴", "WATCH": "👀"}.get(ai.get('action', ''), '⚪')
        embed.add_field(name=f"🧠 AI: {action_emoji} {ai.get('action', '?')} ({ai.get('confidence', 0)}%)",
                       value=ai.get('reasoning', 'No analysis')[:200], inline=False)

    embed.set_footer(text=f"🧠 Claude Opus 4.7 | {datetime.now(ET).strftime('%H:%M ET')}")
    await ctx.send(embed=embed)


# ── !ai SYMBOL ─────────────────────────────────────────

@bot.command(name='ai')
async def ai_cmd(ctx, symbol: str = None):
    if not symbol:
        await ctx.send("Usage: `!ai NVDA`")
        return
    if not brain.is_available:
        await ctx.send("❌ AI Brain offline. Start copilot-api first.")
        return

    symbol = symbol.upper()
    await ctx.send(f"🧠 Claude Opus 4.7 analyzing **{symbol}**...")

    sent = sentiment.analyze(symbol)
    ai = brain.analyze_stock(symbol, {
        'price': 0, 'rsi': 50, 'macd_hist': 0, 'vwap_above': False,
        'volume_ratio': 1.0, 'yahoo_score': sent.yahoo_score,
        'analyst_score': sent.analyst_score, 'reddit_score': sent.reddit_score,
        'trump_score': 0, 'regime': regime_det.current_regime.value,
        'sector': '?', 'earnings_days': 999, 'holding': False, 'unrealized_pl': 0,
        'bb_position': 'mid', 'confluence': 5, 'ema_9': 0, 'ema_21': 0,
    })

    action_emoji = {"BUY": "🟢", "HOLD": "🟡", "SELL": "🔴", "WATCH": "👀"}.get(ai.get('action', ''), '⚪')
    embed = discord.Embed(
        title=f"🧠 AI ANALYSIS: {symbol}",
        description=ai.get('reasoning', 'No analysis'),
        color=0x00FF00 if ai.get('action') == 'BUY' else 0xFFAA00
    )
    embed.add_field(name="Action", value=f"{action_emoji} {ai.get('action', '?')}", inline=True)
    embed.add_field(name="Confidence", value=f"{ai.get('confidence', 0)}%", inline=True)
    embed.add_field(name="Strategy", value=ai.get('strategy', 'NONE'), inline=True)

    if ai.get('risks'):
        embed.add_field(name="⚠️ Risks", value="\n".join(f"• {r}" for r in ai['risks'][:3]), inline=False)

    embed.set_footer(text="🧠 Claude Opus 4.7 via copilot-api (FREE)")
    await ctx.send(embed=embed)


# ── !debate SYMBOL ─────────────────────────────────────

@bot.command(name='debate')
async def debate_cmd(ctx, symbol: str = None):
    if not symbol:
        await ctx.send("Usage: `!debate NVDA`")
        return
    if not brain.is_available:
        await ctx.send("❌ AI Brain offline.")
        return

    symbol = symbol.upper()
    await ctx.send(f"⚔️ Bull vs Bear debate for **{symbol}**...")

    sent = sentiment.analyze(symbol)
    debate = brain.bull_bear_debate(symbol, {
        'price': 0, 'rsi': 50, 'macd_hist': 0, 'vwap_above': False,
        'volume_ratio': 1.0, 'analyst_score': sent.analyst_score,
        'yahoo_score': sent.yahoo_score, 'regime': regime_det.current_regime.value,
    })

    embed = discord.Embed(title=f"⚔️ DEBATE: {symbol}", color=0xFF6600)
    embed.add_field(name=f"🐂 Bull ({debate.get('bull_confidence', 50)}%)",
                   value=debate.get('bull_case', 'No argument')[:200], inline=False)
    embed.add_field(name=f"🐻 Bear ({debate.get('bear_confidence', 50)}%)",
                   value=debate.get('bear_case', 'No argument')[:200], inline=False)

    verdict = debate.get('verdict', '?')
    v_emoji = {"BUY": "🟢", "HOLD": "🟡", "SKIP": "⏭️"}.get(verdict, "⚪")
    embed.add_field(name="⚖️ Verdict", value=f"{v_emoji} **{verdict}**", inline=False)
    await ctx.send(embed=embed)


# ── !sectors ───────────────────────────────────────────

@bot.command(name='sectors')
async def sectors_cmd(ctx):
    await ctx.send("🔍 Scanning 10 sectors...")
    all_scan = get_all_scan_symbols()
    movers = []

    for i in range(0, len(all_scan), 20):
        batch = all_scan[i:i+20]
        try:
            req = StockSnapshotRequest(symbol_or_symbols=batch, feed='iex')
            snaps = data_client.get_stock_snapshot(req)
            for sym, snap in snaps.items():
                if snap.daily_bar and snap.previous_daily_bar:
                    price = float(snap.daily_bar.close)
                    prev = float(snap.previous_daily_bar.close)
                    change = (price - prev) / prev
                    movers.append({'symbol': sym, 'change_pct': change, 'price': price})
        except:
            pass

    alerts = sectors_scanner.detect_sector_move(movers)

    embed = discord.Embed(title="🔥 SECTOR ROTATION", color=0xFF6600)
    if alerts:
        for alert in alerts:
            emoji = "🟢" if alert['direction'] == 'UP' else "🔻"
            embed.add_field(
                name=f"{emoji} {alert['name']} {alert['direction']}",
                value=f"Movers: {', '.join(alert['movers'][:5])}\nScan: {', '.join(alert['scan_all'][:6])}",
                inline=False
            )
    else:
        embed.description = "No sector rotation detected. Market is quiet."

    await ctx.send(embed=embed)


# ── !daily_report ──────────────────────────────────────

@bot.command(name='daily_report')
async def daily_report_cmd(ctx):
    """Generate and send the daily P&L report."""
    from daily_reports import DailyReportGenerator
    await ctx.send("📊 Generating daily report...")
    try:
        gen = DailyReportGenerator()
        report = gen.generate_daily_report()
        chunks = [report[i:i+1900] for i in range(0, len(report), 1900)]
        for chunk in chunks:
            await ctx.send(f"```\n{chunk}\n```")
    except Exception as e:
        await ctx.send(f"❌ Report failed: {e}")


# ── !weekly_report ─────────────────────────────────────

@bot.command(name='weekly_report')
async def weekly_report_cmd(ctx):
    """Generate weekly performance summary."""
    from daily_reports import DailyReportGenerator
    await ctx.send("📊 Generating weekly report...")
    try:
        gen = DailyReportGenerator()
        report = gen.generate_weekly_report()
        await ctx.send(f"```\n{report}\n```")
    except Exception as e:
        await ctx.send(f"❌ Report failed: {e}")


# ── !optimize ──────────────────────────────────────────

@bot.command(name='optimize')
async def optimize_cmd(ctx, symbol: str = None, bars: int = 300):
    """Optimize strategy parameters for a stock using TV backtest data."""
    from strategy_optimizer import StrategyOptimizer

    if not symbol:
        await ctx.send("Usage: `!optimize NVDA` or `!optimize NVDA 500`")
        return

    symbol = symbol.upper()
    await ctx.send(f"🔧 Optimizing strategies for **{symbol}** ({bars} bars)...")

    try:
        opt = StrategyOptimizer()
        results = opt.optimize_stock(symbol, bars)

        if not results:
            await ctx.send(f"⚠️ Not enough data to optimize {symbol}")
            return

        embed = discord.Embed(title=f"🔧 OPTIMIZED: {symbol}", color=0x2ECC71)
        for r in results:
            imp = f"+{r.improvement_pct:.0%}" if r.improvement_pct > 0 else f"{r.improvement_pct:.0%}"
            embed.add_field(
                name=f"{'🟢' if r.total_pnl > 0 else '🔴'} {r.strategy}",
                value=(f"RSI entry: **<{r.rsi_buy:.0f}**\n"
                       f"Target: **{r.target_pct:.1%}** | Stop: **{r.stop_pct:.1%}**\n"
                       f"WR: {r.win_rate:.0%} | P&L: ${r.total_pnl:+,.2f}\n"
                       f"vs default: {imp} | {r.trades} trades"),
                inline=False
            )
        embed.set_footer(text="📺 Optimized on TradingView Premium data")
        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Optimization failed: {e}")


# ── !earnings ──────────────────────────────────────────

@bot.command(name='earnings')
async def earnings_cmd(ctx):
    positions = gateway.get_positions()
    held = [p.symbol for p in positions]
    earnings = dc.get_earnings_dates(held)

    embed = discord.Embed(title="📅 EARNINGS CALENDAR", color=0xF1C40F)
    for sym, date in sorted(earnings.items(), key=lambda x: x[1]):
        days = (date.date() - datetime.now().date()).days
        if days <= 0:
            embed.add_field(name=f"⛔ {sym}", value=f"Already reported", inline=True)
        elif days <= 1:
            embed.add_field(name=f"⛔ {sym}", value=f"{'TODAY' if days == 0 else 'TOMORROW'}!", inline=True)
        elif days <= 3:
            embed.add_field(name=f"⚠️ {sym}", value=f"{date.strftime('%b %d')} ({days}d)", inline=True)
        else:
            embed.add_field(name=f"✅ {sym}", value=f"{date.strftime('%b %d')} ({days}d)", inline=True)

    embed.set_footer(text="🔒 No new trades on stocks with earnings ≤1 day")
    await ctx.send(embed=embed)


# ── !risk ──────────────────────────────────────────────

@bot.command(name='risk')
async def risk_cmd(ctx):
    positions = gateway.get_positions()
    total_pl = sum(p.unrealized_pl for p in positions)
    acct = gateway.get_account()

    embed = discord.Embed(title="🛡️ RISK DASHBOARD",
                         color=0xFF0000 if total_pl <= -500 else 0x00FF00)
    embed.add_field(name="📈 Total P&L", value=f"${total_pl:+,.2f}", inline=True)
    embed.add_field(name="⛔ Kill Switch", value="-$500", inline=True)
    embed.add_field(name="Status",
                   value="⛔ TRIGGERED" if total_pl <= -500 else "✅ OK",
                   inline=True)

    red = [p for p in positions if p.is_red]
    green = [p for p in positions if p.is_green]
    embed.add_field(name="🔴 Red (HELD)", value=str(len(red)), inline=True)
    embed.add_field(name="🟢 Green", value=str(len(green)), inline=True)
    embed.add_field(name="📊 Regime", value=regime_det.current_regime.value, inline=True)

    # Big losers
    for p in sorted(positions, key=lambda x: x.unrealized_pl):
        if p.unrealized_pl <= -200:
            embed.add_field(name=f"⛔ {p.symbol}",
                          value=f"${p.unrealized_pl:+,.2f}", inline=True)

    embed.set_footer(text="🔒 Iron Law 1: NEVER sell at loss | Law 10: When in doubt = nothing")
    await ctx.send(embed=embed)


# ── !backtest SYMBOL ───────────────────────────────────

@bot.command(name='backtest')
async def backtest_cmd(ctx, symbol: str = None, bars: int = 300):
    """Backtest strategies on a stock using TradingView data."""
    from backtest_engine import BacktestEngine

    if not symbol:
        await ctx.send("Usage: `!backtest NVDA` or `!backtest NVDA 500`")
        return

    symbol = symbol.upper()
    await ctx.send(f"🔬 Backtesting **{symbol}** on {bars} bars from TradingView...")

    try:
        engine = BacktestEngine()
        results = engine.backtest(symbol, bars)

        if not results:
            await ctx.send(f"⚠️ Not enough data for {symbol}. Need 50+ bars.")
            return

        embed = discord.Embed(
            title=f"🔬 BACKTEST: {symbol} ({bars} bars)",
            color=0x9B59B6
        )

        for r in sorted(results, key=lambda x: x.total_pnl, reverse=True):
            emoji = "🟢" if r.total_pnl > 0 else "🔴"
            wr = f"{r.win_rate:.0%}"
            embed.add_field(
                name=f"{emoji} Strategy {r.strategy}",
                value=(f"Trades: {r.trades} | WR: {wr}\n"
                       f"P&L: **${r.total_pnl:+,.2f}**\n"
                       f"Max Win: ${r.max_win:+,.2f} | Max Loss: ${r.max_loss:+,.2f}\n"
                       f"Max DD: ${r.max_drawdown:,.2f}"),
                inline=False
            )

        # Best strategy recommendation
        best = max(results, key=lambda r: r.total_pnl)
        if best.total_pnl > 0:
            embed.add_field(
                name="🎯 RECOMMENDATION",
                value=f"Use **Strategy {best.strategy}** on {symbol}\n"
                      f"${best.total_pnl:+,.2f} with {best.win_rate:.0%} win rate",
                inline=False
            )

        embed.set_footer(text="📺 Data from TradingView Premium | Strategies: I, J, G, B")
        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Backtest failed: {e}")


# ── !backtest_all ──────────────────────────────────────

@bot.command(name='backtest_all')
async def backtest_all_cmd(ctx, bars: int = 300):
    """Backtest all strategies across 18 stocks."""
    from backtest_engine import BacktestEngine

    stocks = ['NVDA', 'AMD', 'INTC', 'GOOGL', 'AMZN', 'AAPL',
              'META', 'TSLA', 'NOK', 'CRM', 'PLTR', 'ORCL',
              'MU', 'SNOW', 'NOW', 'ARM', 'MRVL', 'COIN']

    await ctx.send(f"🔬 Backtesting **{len(stocks)} stocks** on {bars} bars each...\n"
                   f"This takes ~2 minutes. Grab a coffee ☕")

    try:
        engine = BacktestEngine()
        report = engine.backtest_portfolio(symbols=stocks, bar_count=bars)

        # Split report into chunks (Discord 2000 char limit)
        chunks = [report[i:i+1900] for i in range(0, len(report), 1900)]
        for chunk in chunks:
            await ctx.send(f"```\n{chunk}\n```")

    except Exception as e:
        await ctx.send(f"❌ Backtest failed: {e}")


# ── !performance ───────────────────────────────────────

@bot.command(name='performance')
async def performance_cmd(ctx):
    """Show trading performance analytics."""
    from performance_tracker import PerformanceTracker

    try:
        tracker = PerformanceTracker()
        report = tracker.generate_report()

        embed = discord.Embed(title="🏆 PERFORMANCE REPORT", color=0xF1C40F)
        embed.description = f"```\n{report[:1800]}\n```"
        embed.set_footer(text="📊 From trade database")
        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Performance report failed: {e}")


# ── !analytics (comprehensive dashboard) ──────────────

@bot.command(name='analytics')
async def analytics_cmd(ctx):
    """Comprehensive analytics: equity curve, trade patterns, market analysis."""
    try:
        from trade_db import TradeDB
        from performance_tracker import PerformanceTracker
        db = TradeDB()
        tracker = PerformanceTracker(db)

        # ── EMBED 1: Overall Stats ──
        stats = db.get_overall_stats()
        streak = db.get_streak()
        embed1 = discord.Embed(title="📊 BEAST ANALYTICS DASHBOARD", color=0x3498db)
        embed1.add_field(name="📈 Overall Performance", value=(
            f"```\n"
            f"Total Trades:   {stats.get('total_trades', 0):>6d}\n"
            f"Win Rate:       {stats.get('win_rate', 0):>5.1%}\n"
            f"Total P&L:     ${stats.get('total_pnl', 0):>+9.2f}\n"
            f"Avg Trade:     ${stats.get('avg_pnl', 0):>+9.2f}\n"
            f"Profit Factor:  {stats.get('profit_factor', 0):>6.2f}\n"
            f"Max Win:       ${stats.get('max_win', 0):>+9.2f}\n"
            f"Max Loss:      ${stats.get('max_loss', 0):>+9.2f}\n"
            f"Streak:         {streak.get('count', 0)}x {'WIN' if streak.get('type') == 'win' else 'LOSS'}\n"
            f"```"
        ), inline=False)

        # ── Strategy Breakdown ──
        by_strat = db.get_stats_by_strategy()
        if by_strat:
            strat_table = "```\n"
            strat_table += f"{'STRAT':8s} {'TRADES':>6s} {'WR':>6s} {'P&L':>10s} {'AVG':>8s}\n"
            strat_table += f"{'─'*42}\n"
            for s in by_strat[:8]:
                strat_table += f"{s['strategy'][:8]:8s} {s['trades']:>6d} {s['win_rate']:>5.0f}% ${s['total_pnl']:>+9.2f} ${s['avg_pnl']:>+7.2f}\n"
            strat_table += "```"
            embed1.add_field(name="📋 By Strategy", value=strat_table, inline=False)

        # ── Stock Breakdown ──
        by_stock = db.get_stats_by_stock()
        if by_stock:
            stock_table = "```\n"
            stock_table += f"{'STOCK':6s} {'TRADES':>6s} {'WR':>6s} {'P&L':>10s}\n"
            stock_table += f"{'─'*32}\n"
            for s in by_stock[:10]:
                stock_table += f"{s['symbol']:6s} {s['trades']:>6d} {s['win_rate']:>5.0f}% ${s['total_pnl']:>+9.2f}\n"
            stock_table += "```"
            embed1.add_field(name="📈 By Stock", value=stock_table, inline=False)

        await ctx.send(embed=embed1)

        # ── EMBED 2: Daily P&L ──
        by_day = db.get_stats_by_day(14)
        if by_day:
            embed2 = discord.Embed(title="📅 Daily P&L (Last 14 Days)", color=0x2ecc71)
            day_table = "```\n"
            day_table += f"{'DATE':12s} {'TRADES':>6s} {'WR':>6s} {'P&L':>10s}\n"
            day_table += f"{'─'*38}\n"
            for d in by_day:
                icon = "+" if (d.get('daily_pnl') or 0) >= 0 else "-"
                day_table += f"{icon}{d['trade_date']:11s} {d['trades']:>6d} {d['win_rate']:>5.0f}% ${d['daily_pnl']:>+9.2f}\n"
            day_table += "```"
            embed2.description = day_table
            await ctx.send(embed=embed2)

        # ── EMBED 3: Equity Curve ──
        eq_data = db.get_equity_curve(48)  # Last 48 data points
        if eq_data:
            embed3 = discord.Embed(title="📈 Equity Curve", color=0x9b59b6)
            eq_data.reverse()  # Oldest first
            # ASCII bar chart
            equities = [e['equity'] for e in eq_data]
            if equities:
                min_eq = min(equities)
                max_eq = max(equities)
                range_eq = max_eq - min_eq or 1
                chart = "```\n"
                chart += f"${max_eq:,.0f} ┤\n"
                for e in eq_data[-20:]:
                    bar_len = int((e['equity'] - min_eq) / range_eq * 30)
                    bar = "█" * max(1, bar_len)
                    chart += f"        │{bar} ${e['equity']:,.0f}\n"
                chart += f"${min_eq:,.0f} ┤\n"
                chart += "```"
                embed3.description = chart[:2000]
            await ctx.send(embed=embed3)

        # ── EMBED 4: Regime Performance ──
        by_regime = db.get_stats_by_regime()
        if by_regime:
            embed4 = discord.Embed(title="🌍 Performance by Market Regime", color=0xe74c3c)
            regime_table = "```\n"
            regime_table += f"{'REGIME':10s} {'TRADES':>6s} {'WR':>6s} {'P&L':>10s}\n"
            regime_table += f"{'─'*36}\n"
            for r in by_regime:
                regime_table += f"{r['regime'][:10]:10s} {r['trades']:>6d} {r['win_rate']:>5.0f}% ${r['total_pnl']:>+9.2f}\n"
            regime_table += "```"
            embed4.description = regime_table
            await ctx.send(embed=embed4)

        # ── EMBED 5: Recent Scans ──
        scans = db.get_scan_history(10)
        if scans:
            embed5 = discord.Embed(title="🔍 Recent Scan Log", color=0x1abc9c)
            scan_table = "```\n"
            scan_table += f"{'TIME':8s} {'TYPE':5s} {'REG':6s} {'EQ':>10s} {'P&L':>9s} {'TV':>3s} {'AI':>3s} {'TR':>3s}\n"
            scan_table += f"{'─'*52}\n"
            for s in scans[:10]:
                t = s.get('timestamp', '')[-8:]
                scan_table += f"{t:8s} {s.get('scan_type','?'):5s} {s.get('regime','?')[:6]:6s} ${s.get('equity',0):>9,.0f} ${s.get('total_pl',0):>+8.2f} {s.get('tv_reads',0):>3d} {s.get('ai_calls',0):>3d} {s.get('trump_score',0):>+3d}\n"
            scan_table += "```"
            embed5.description = scan_table
            embed5.set_footer(text="!performance for full report | !backtest NVDA for strategy test")
            await ctx.send(embed=embed5)

        if not any([by_strat, by_stock, by_day, eq_data, scans]):
            await ctx.send("📊 No analytics data yet. The bot needs to make some trades first!")

    except Exception as e:
        await ctx.send(f"❌ Analytics failed: {e}")


# ── !debug (show recent errors) ───────────────────────

@bot.command(name='debug')
async def debug_cmd(ctx, component: str = None):
    """Show recent debug/error log entries."""
    try:
        from trade_db import TradeDB
        db = TradeDB()
        entries = db.get_debug_log(20, component)
        if not entries:
            await ctx.send("✅ No debug entries found. System is clean!")
            return
        text = "```\n"
        for e in entries:
            text += f"[{e.get('timestamp','')[-8:]}] {e.get('level','')[:4]} {e.get('component','')[:10]:10s} {e.get('message','')[:60]}\n"
        text += "```"
        await ctx.send(f"🔧 **Debug Log** (last 20)\n{text}")
    except Exception as e:
        await ctx.send(f"❌ Debug log failed: {e}")


# ── !approve / !reject (Remote trade control) ─────────

pending_trades = {}  # symbol → trade proposal data

@bot.command(name='approve')
async def approve_cmd(ctx, symbol: str = None):
    """Approve a pending trade proposal from the bot."""
    if not symbol:
        if pending_trades:
            symbols = ", ".join(pending_trades.keys())
            await ctx.send(f"Pending trades: {symbols}\nUsage: `!approve NVDA`")
        else:
            await ctx.send("No pending trades to approve.")
        return

    symbol = symbol.upper()
    if symbol not in pending_trades:
        await ctx.send(f"❌ No pending trade for {symbol}")
        return

    trade = pending_trades.pop(symbol)
    await ctx.send(f"✅ Executing: **{trade['side']} {trade['qty']}x {symbol} @ ${trade['price']:.2f}**...")

    try:
        if trade['side'] == 'BUY':
            from models import TradeProposal, OrderSide, Strategy
            proposal = TradeProposal(
                symbol=symbol,
                side=OrderSide.BUY,
                qty=trade['qty'],
                limit_price=trade['price'],
                strategy=Strategy[trade.get('strategy_enum', 'BLUE_CHIP_REVERSION')],
                confidence=trade.get('confidence', 0.7),
                reason=trade.get('reason', 'Discord approved'),
            )
            # Use split entry (half scalp, half runner)
            positions = gateway.get_positions()
            acct = gateway.get_account()
            market_data = type('M', (), {
                'regime': regime_det.current_regime,
                'spy_change_pct': 0, 'account_equity': acct.get('equity', 0),
                'positions': positions, 'spy_price': 0, 'qqq_price': 0,
                'buying_power': acct.get('buying_power', 0),
                'day_trade_count': acct.get('day_trade_count', 0),
                'timestamp': datetime.now(), 'vix': 0,
            })()
            scalp, runner = gateway.place_split_entry(
                proposal, market_data, positions, 0, 0,
                acct.get('day_trade_count', 0), {},
                has_technicals=True, has_sentiment=True,
            )
            if scalp.state.value == 'sent':
                await ctx.send(f"🟢 **EXECUTED!** Split entry placed:\n"
                             f"📊 Scalp: {proposal.qty // 2}x @ ${trade['price']:.2f}\n"
                             f"🏃 Runner: {proposal.qty - proposal.qty // 2}x @ ${trade['price']:.2f}\n"
                             f"Limit sells being set (Iron Law 6)...")
                # Send to Telegram too
                from notifier import Notifier
                n = Notifier()
                n.alert_trade_executed(symbol, 'buy', trade['qty'], trade['price'],
                                      trade.get('strategy', '?'), trade.get('confidence', 0))
            else:
                await ctx.send(f"⛔ Order REJECTED by Iron Laws: {scalp.error[:200]}")
        elif trade['side'] == 'SELL':
            result = gateway.place_sell(symbol, trade['qty'], trade['price'],
                                        reason="Discord approved sell")
            if result.state.value == 'sent':
                await ctx.send(f"🔴 **SOLD!** {trade['qty']}x {symbol} @ ${trade['price']:.2f}")
            else:
                await ctx.send(f"⛔ Sell REJECTED: {result.error[:200]}")
    except Exception as e:
        await ctx.send(f"❌ Execution failed: {e}")


@bot.command(name='reject')
async def reject_cmd(ctx, symbol: str = None):
    """Reject a pending trade proposal."""
    if not symbol:
        await ctx.send("Usage: `!reject NVDA`")
        return
    symbol = symbol.upper()
    if symbol in pending_trades:
        pending_trades.pop(symbol)
        await ctx.send(f"⏭️ Trade for **{symbol}** rejected and cleared.")
    else:
        await ctx.send(f"No pending trade for {symbol}")


@bot.command(name='reject_all')
async def reject_all_cmd(ctx):
    """Reject all pending trades."""
    count = len(pending_trades)
    pending_trades.clear()
    await ctx.send(f"⏭️ Cleared {count} pending trades.")


@bot.command(name='pending')
async def pending_cmd(ctx):
    """Show all pending trade proposals waiting for approval."""
    if not pending_trades:
        await ctx.send("No pending trades. The bot will propose trades during scans.")
        return

    embed = discord.Embed(title="⏳ PENDING TRADES (awaiting your approval)", color=0xF1C40F)
    for sym, trade in pending_trades.items():
        emoji = "🟢" if trade['side'] == 'BUY' else "🔴"
        embed.add_field(
            name=f"{emoji} {sym} — {trade['side']} {trade['qty']}x @ ${trade['price']:.2f}",
            value=(f"Strategy: {trade.get('strategy', '?')} | "
                   f"Confidence: {trade.get('confidence', 0):.0%}\n"
                   f"Reason: {trade.get('reason', '?')[:100]}\n"
                   f"→ `!approve {sym}` or `!reject {sym}`"),
            inline=False
        )
    await ctx.send(embed=embed)


# ── !full_scan (the ULTIMATE command) ──────────────────

@bot.command(name='full_scan')
async def full_scan_cmd(ctx):
    """
    🦍 THE ULTIMATE COMMAND.
    Full scan: ALL positions + ALL runners + ALL sectors + sentiment + TV + AI.
    Proposes trades → waits for your approval → executes.
    Run this from ANYWHERE via Discord.
    """
    await ctx.send("🦍🔥 **FULL SCAN ACTIVATED** — Running ALL phases...\n"
                   "This is the big one. Scanning everything. Stand by...")

    try:
        # PHASE 0+1: Positions + Account
        positions = gateway.get_positions()
        acct = gateway.get_account()
        held = [p.symbol for p in positions]
        total_pl = sum(p.unrealized_pl for p in positions)

        # Regime
        try:
            req = StockSnapshotRequest(symbol_or_symbols='SPY', feed='iex')
            spy_snap = data_client.get_stock_snapshot(req)
            spy_change = (float(spy_snap['SPY'].daily_bar.close) - float(spy_snap['SPY'].previous_daily_bar.close)) / float(spy_snap['SPY'].previous_daily_bar.close)
            current_regime = regime_det.detect(spy_change)
        except:
            current_regime = regime_det.current_regime

        # PHASE 3: Full Sentiment
        await ctx.send("📰 Phase 3: Scanning 5 sentiment sources...")
        mkt_sent = sentiment.full_market_sentiment()

        # PHASE 4: Sector scan (all 48 symbols)
        await ctx.send("🔍 Phase 4: Scanning 48 symbols across 10 sectors...")
        from engine.master_intelligence import get_all_scan_symbols, get_stock_profile, PAST_WINNERS
        all_scan = get_all_scan_symbols()
        movers = []
        for i in range(0, len(all_scan), 20):
            batch = all_scan[i:i+20]
            try:
                req = StockSnapshotRequest(symbol_or_symbols=batch, feed='iex')
                snaps = data_client.get_stock_snapshot(req)
                for sym, snap in snaps.items():
                    if snap.daily_bar and snap.previous_daily_bar:
                        price = float(snap.daily_bar.close)
                        prev = float(snap.previous_daily_bar.close)
                        change = (price - prev) / prev
                        movers.append({'symbol': sym, 'change_pct': change, 'price': price})
            except:
                pass

        runners = sorted([m for m in movers if m['change_pct'] > 0.01], key=lambda x: x['change_pct'], reverse=True)
        dumpers = sorted([m for m in movers if m['change_pct'] < -0.02], key=lambda x: x['change_pct'])

        # PHASE 2: TV scan on held + top runners
        tv_ok = tv.health_check()
        tv_results = {}
        scan_list = list(dict.fromkeys(held + [r['symbol'] for r in runners[:5]]))
        if tv_ok:
            await ctx.send(f"📺 Phase 2: TradingView scanning {len(scan_list)} stocks...")
            tv._connect()
            for sym in scan_list:
                try:
                    tv.set_symbol(sym)
                    await asyncio.sleep(2)
                    studies = tv.get_study_values()
                    rsi, macd = '?', '?'
                    for s in studies:
                        if 'Relative Strength' in s.get('name', ''): rsi = s.get('values', {}).get('RSI', '?')
                        elif s.get('name') == 'MACD': macd = s.get('values', {}).get('Histogram', '?')
                    tv_results[sym] = {'rsi': rsi, 'macd': macd}
                except:
                    pass

        # PHASE 5: AI Brain on ALL stocks
        await ctx.send(f"🧠 Phase 5: Claude Opus 4.7 analyzing {len(scan_list)} stocks...")
        ai_results = {}
        proposals = []

        for sym in scan_list:
            sent_s = sentiment.analyze(sym)
            profile = get_stock_profile(sym)
            snap = next((m for m in movers if m['symbol'] == sym), {})
            tv_d = tv_results.get(sym, {})
            pos_match = [p for p in positions if p.symbol == sym]

            rsi_val = 50
            try: rsi_val = float(str(tv_d.get('rsi', '50')).replace('\u2212', '-').replace('?', '50'))
            except: pass

            data = {
                'price': snap.get('price', pos_match[0].current_price if pos_match else 0),
                'rsi': rsi_val,
                'macd_hist': 0, 'vwap_above': False, 'volume_ratio': 1.0,
                'yahoo_score': sent_s.yahoo_score, 'analyst_score': sent_s.analyst_score,
                'reddit_score': sent_s.reddit_score, 'trump_score': mkt_sent.get('trump_score', 0),
                'regime': current_regime.value,
                'sector': profile.get('sectors', ['?'])[0] if profile.get('sectors') else '?',
                'earnings_days': 999, 'holding': sym in held,
                'unrealized_pl': pos_match[0].unrealized_pl if pos_match else 0,
                'bb_position': 'mid', 'confluence': 5, 'ema_9': 0, 'ema_21': 0,
            }

            if brain.is_available:
                ai = brain.analyze_stock(sym, data)
                ai_results[sym] = ai

                # If AI says BUY → create a proposal for approval
                if ai.get('action') in ('BUY', 'CONVICTION_BUY', 'STRONG_BUY') and sym not in held:
                    price = snap.get('price', 0)
                    if price > 0:
                        proposals.append({
                            'symbol': sym,
                            'side': 'BUY',
                            'qty': max(1, int(acct.get('equity', 100000) * 0.05 / price)),
                            'price': round(price, 2),
                            'strategy': ai.get('strategy', '?'),
                            'strategy_enum': 'BLUE_CHIP_REVERSION',
                            'confidence': ai.get('confidence', 0) / 100,
                            'reason': ai.get('reasoning', '')[:150],
                        })

        # Build the dashboard embed
        embed = discord.Embed(
            title="🦍 FULL SCAN COMPLETE",
            color=0xFF6600,
            description=(f"Regime: **{current_regime.value}** | "
                         f"Sentiment: **{mkt_sent.get('action', '?')}** ({mkt_sent.get('total_score', 0):+d}/25)\n"
                         f"Stocks scanned: {len(scan_list)} | Runners: {len(runners)} | Dumpers: {len(dumpers)}")
        )

        # Positions summary
        pos_lines = []
        for p in sorted(positions, key=lambda x: x.unrealized_pl, reverse=True)[:8]:
            e = "🟢" if p.is_green else "🔴"
            ai = ai_results.get(p.symbol, {})
            ai_action = ai.get('action', '?')
            pos_lines.append(f"{e} **{p.symbol}** `${p.unrealized_pl:+.2f}` AI:{ai_action}")
        embed.add_field(name=f"📦 Positions (${total_pl:+,.2f})", value="\n".join(pos_lines), inline=False)

        # Runners
        if runners[:5]:
            r_lines = []
            for r in runners[:5]:
                star = "⭐" if r['symbol'] in PAST_WINNERS else "🏃"
                ai = ai_results.get(r['symbol'], {})
                r_lines.append(f"{star} **{r['symbol']}** `{r['change_pct']:+.2%}` AI:{ai.get('action', '?')}")
            embed.add_field(name="🏃 Top Runners", value="\n".join(r_lines), inline=False)

        # Sector alerts
        sector_alerts = sectors_scanner.detect_sector_move(movers)
        if sector_alerts:
            s_lines = []
            for sa in sector_alerts[:3]:
                emoji = "🟢" if sa['direction'] == 'UP' else "🔻"
                s_lines.append(f"{emoji} {sa['name']}: {', '.join(sa['movers'][:4])}")
            embed.add_field(name="🔥 Sectors", value="\n".join(s_lines), inline=False)

        # Risk
        risk = "⛔ KILL SWITCH" if total_pl <= -500 else "✅ OK"
        embed.add_field(name="🛡️ Risk", value=f"P&L: ${total_pl:+,.2f} | {risk}", inline=False)

        embed.set_footer(text=f"🧠 Opus 4.7 | 📺 TV Premium | {datetime.now(ET).strftime('%H:%M ET')}")
        await ctx.send(embed=embed)

        # Send trade proposals for approval
        if proposals:
            prop_embed = discord.Embed(
                title="🎯 TRADE PROPOSALS (awaiting your approval)",
                color=0x00FF00,
                description="Reply `!approve SYMBOL` to execute or `!reject SYMBOL` to skip"
            )
            for p in proposals:
                pending_trades[p['symbol']] = p
                prop_embed.add_field(
                    name=f"🟢 BUY {p['symbol']} — {p['qty']}x @ ${p['price']:.2f}",
                    value=(f"Strategy: {p['strategy']} | Confidence: {p['confidence']:.0%}\n"
                           f"{p['reason'][:120]}\n"
                           f"→ `!approve {p['symbol']}`"),
                    inline=False
                )
            await ctx.send(embed=prop_embed)
        else:
            await ctx.send("📊 No new trade proposals. All stocks: HOLD/WATCH.")

        # Also send to Telegram
        from notifier import Notifier
        n = Notifier()
        n.send(f"🦍 FULL SCAN COMPLETE\n"
               f"Regime: {current_regime.value} | Sentiment: {mkt_sent.get('action', '?')}\n"
               f"Scanned: {len(scan_list)} stocks | Runners: {len(runners)}\n"
               f"Proposals: {len(proposals)} trades pending approval\n"
               f"P&L: ${total_pl:+,.2f}")

    except Exception as e:
        await ctx.send(f"❌ Full scan failed: {e}")
        import traceback
        traceback.print_exc()
    await ctx.send("🦍🔥 **BEAST MODE ACTIVATED** — Full scan running...")

    # Phase 0: Positions
    positions = gateway.get_positions()
    acct = gateway.get_account()
    total_pl = sum(p.unrealized_pl for p in positions)

    # Phase 1: Regime
    spy_data = {}
    try:
        req = StockSnapshotRequest(symbol_or_symbols='SPY', feed='iex')
        spy_snap = data_client.get_stock_snapshot(req)
        spy_price = float(spy_snap['SPY'].daily_bar.close)
        spy_prev = float(spy_snap['SPY'].previous_daily_bar.close)
        spy_change = (spy_price - spy_prev) / spy_prev
        current_regime = regime_det.detect(spy_change)
    except:
        current_regime = regime_det.current_regime

    # Phase 2: Sentiment
    mkt_sent = sentiment.full_market_sentiment()

    # Build embeds
    # Main dashboard
    embed = discord.Embed(
        title="🦍 BEAST MODE v2.2",
        color=0xFF6600,
        description=f"Regime: **{current_regime.value}** | Sentiment: **{mkt_sent.get('action', '?')}** ({mkt_sent.get('total_score', 0):+d}/25)"
    )
    embed.add_field(name="💰 Equity", value=f"${acct.get('equity', 0):,.2f}", inline=True)
    embed.add_field(name="📈 P&L", value=f"${total_pl:+,.2f}", inline=True)
    embed.add_field(name="📊 Positions", value=str(len(positions)), inline=True)

    # Positions
    sorted_pos = sorted(positions, key=lambda p: p.unrealized_pl, reverse=True)
    pos_lines = []
    for p in sorted_pos[:12]:
        emoji = "🟢" if p.is_green else "🔴"
        pos_lines.append(f"{emoji} **{p.symbol}** {p.qty}x `${p.unrealized_pl:+.2f}`")
    embed.add_field(name="📦 Positions", value="\n".join(pos_lines), inline=False)

    # Risk
    risk_status = "⛔ KILL SWITCH" if total_pl <= -500 else "✅ Within limits"
    embed.add_field(name="🛡️ Risk", value=risk_status, inline=True)

    embed.set_footer(text=f"🧠 Claude Opus 4.7 | 📺 TV Premium | {datetime.now(ET).strftime('%H:%M ET')}")
    await ctx.send(embed=embed)

    # AI brain on top 3
    if brain.is_available:
        top3 = sorted_pos[:3]
        ai_embed = discord.Embed(title="🧠 AI BRAIN — Top Positions", color=0x9B59B6)
        for p in top3:
            sent_s = sentiment.analyze(p.symbol)
            ai = brain.analyze_stock(p.symbol, {
                'price': p.current_price, 'rsi': 50, 'macd_hist': 0,
                'vwap_above': False, 'volume_ratio': 1.0,
                'yahoo_score': sent_s.yahoo_score, 'analyst_score': sent_s.analyst_score,
                'reddit_score': sent_s.reddit_score, 'trump_score': 0,
                'regime': current_regime.value, 'sector': '?',
                'earnings_days': 999, 'holding': True,
                'unrealized_pl': p.unrealized_pl,
                'bb_position': 'mid', 'confluence': 5, 'ema_9': 0, 'ema_21': 0,
            })
            action_e = {"BUY": "🟢", "HOLD": "🟡", "SELL": "🔴"}.get(ai.get('action', ''), '⚪')
            ai_embed.add_field(
                name=f"{action_e} {p.symbol} — {ai.get('action', '?')} ({ai.get('confidence', 0)}%)",
                value=ai.get('reasoning', 'No analysis')[:150],
                inline=False
            )
        ai_embed.set_footer(text="🧠 Claude Opus 4.7 (FREE via copilot-api)")
        await ctx.send(embed=ai_embed)


# ── AUTONOMOUS LOOP (runs inside Discord bot) ─────────
import asyncio

SCAN_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '1498363431013716079'))
_prev_prices = {}
_cycle_count = 0
_cached_vix = 18.0  # Default neutral VIX
_last_full_scan = 0
_tv_client = None

# Watchlist for auto-buy dips (Akash Method)
# Watchlist — starts with hardcoded, then loads from PostgreSQL (grows forever)
DIP_BUY_WATCHLIST = ['AAPL', 'AMZN', 'GOOGL', 'META', 'MSFT', 'NVDA', 'TSLA',
                     'AMD', 'TSM', 'INTC', 'CRM', 'PLTR', 'OXY', 'DVN', 'LMT',
                     'SOFI', 'COIN', 'AVGO', 'QCOM', 'HOOD', 'MSTR', 'NOK', 'MU']

# Load full watchlist from PostgreSQL (213+ stocks, grows with every scan)
try:
    from db_postgres import BeastDB
    _wl_db = BeastDB()
    if _wl_db.conn:
        _db_watchlist = _wl_db.get_watchlist()
        if _db_watchlist:
            for sym in _db_watchlist:
                if sym not in DIP_BUY_WATCHLIST:
                    DIP_BUY_WATCHLIST.append(sym)
            log.info(f"📋 Watchlist loaded: {len(DIP_BUY_WATCHLIST)} stocks from PostgreSQL")
        _wl_db.close()
except Exception as e:
    log.debug(f"Watchlist DB load: {e}")

# Past winners — scan these FIRST (Phase 0, Rule #21)
PAST_WINNERS = ['NOK', 'GOOGL', 'CRM', 'META', 'MSFT', 'NOW', 'AMD', 'NVDA',
                'OXY', 'DVN', 'INTC', 'ORCL', 'MSTR', 'COIN', 'HOOD',
                'AVGO', 'AMZN', 'TSLA', 'PLTR', 'MU', 'TSM']

# Rule #29: Don't chase stocks already up >5% WITHOUT catalyst
MAX_CHASE_PCT = 5.0
CATALYST_SENTIMENT_THRESHOLD = 3

# Telegram notifier (sends to BOTH Telegram + Discord)
_notifier = None
def _tg(message: str):
    """Send message to Telegram (non-blocking, fire-and-forget)."""
    global _notifier
    try:
        if _notifier is None:
            from notifier import Notifier
            _notifier = Notifier()
        _notifier.send(message)
    except Exception as e:
        log.debug(f"Telegram send failed: {e}")

def _get_tv_indicators(symbol: str) -> dict:
    """Read RSI/MACD/VWAP/BB from TradingView CDP. Returns dict or empty."""
    global _tv_client
    try:
        if _tv_client is None:
            from tv_cdp_client import TVClient
            _tv_client = TVClient()
            if not _tv_client.health_check():
                log.warning(f"  TV CDP not available for {symbol}")
                _tv_client = None
                return {}
            log.info("  TV CDP connected (reusable)")

        # Switch symbol and wait for data to load
        switched = _tv_client.set_symbol(symbol)
        if not switched:
            log.debug(f"  TV: failed to switch to {symbol}")
            return {}
        time.sleep(7)  # Wait for chart + ALL indicators to load (increased from 5)

        # Read study values — retry until we get at least 5 studies (RSI+MACD+VWAP+BB+EMA)
        studies = _tv_client.get_study_values()
        retries = 0
        while len(studies or []) <= 5 and retries < 4:  # 4 retries × 3s = 12s max wait
            retries += 1
            time.sleep(3)
            studies = _tv_client.get_study_values()
            log.debug(f"  TV {symbol} retry {retries}: {len(studies or [])} studies")

        if not studies or len(studies) < 3:
            log.warning(f"  TV {symbol}: only {len(studies or [])} studies after {retries} retries — insufficient")
            return {}

        study_names = [s.get('name', '?') for s in studies]
        log.info(f"  📺 TV {symbol}: {len(studies)} studies loaded ({retries} retries) — {', '.join(study_names[:6])}")
        _pg_log("TV_LOADED", symbol=symbol,
                reason=f"{len(studies)} studies ({retries} retries): {', '.join(study_names[:6])}",
                source="tv_read", data={'studies': study_names, 'retries': retries})

        # Parse via TV analyst
        from tv_analyst import TradingViewAnalyst
        tva = TradingViewAnalyst()
        result = tva.analyze(symbol, mcp_tools={
            'studies': studies, 'quote': {}, 'labels': [], 'tables': []
        })
        if result:
            return {
                'rsi': result.rsi, 'macd_hist': result.macd_histogram,
                'vwap_above': result.above_vwap,
                'bb_position': 'upper' if getattr(result, 'above_upper_bb', False) else ('lower' if getattr(result, 'below_lower_bb', False) else 'mid'),
                'confluence': result.confluence_score,
                'ema_9': result.ema_9, 'ema_21': result.ema_21,
                'volume_ratio': result.volume_ratio,
            }
        log.debug(f"  TV: analyze returned None for {symbol}")
    except Exception as e:
        log.warning(f"  TV indicators {symbol}: {e}")
        _tv_client = None  # Reset connection on error
    return {}


# Cache TV results so we don't re-scan same stock within 5 min
_tv_cache = {}  # symbol → (timestamp, indicators)

# Market internals cache
_market_internals_cache = {'ts': 0, 'data': {}}
MARKET_INTERNALS_TTL = 120  # 2 min cache

def _get_market_internals() -> dict:
    """Read NYSE market internals from TradingView: $TICK, $ADD, $VOLD.
    
    These are the #1 thing pros check before every trade.
    - $TICK > +600 = bullish breadth, > +1000 = extreme (contrarian sell)
    - $TICK < -600 = bearish, < -1000 = capitulation (contrarian buy)
    - $ADD > +500 sustained = healthy rally
    - $VOLD positive = more volume on up stocks
    
    Returns: {tick: float, add: float, vold: float, signal: str, score: int}
    """
    global _market_internals_cache
    if time.time() - _market_internals_cache['ts'] < MARKET_INTERNALS_TTL:
        return _market_internals_cache['data']
    
    result = {'tick': None, 'add': None, 'vold': None, 'signal': 'unknown', 'score': 0}
    
    try:
        # Try reading $TICK from Alpaca snapshot (it's an index)
        from alpaca.data.requests import StockSnapshotRequest
        try:
            snap = data_client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=['SPY'], feed='iex'))
            if snap and 'SPY' in snap:
                # SPY as proxy for market direction
                spy_bar = snap['SPY']
                if hasattr(spy_bar, 'minute_bar') and spy_bar.minute_bar:
                    bar = spy_bar.minute_bar
                    # Infer market breadth from SPY volume/price action
                    if hasattr(bar, 'close') and hasattr(bar, 'open'):
                        spy_move = (float(bar.close) - float(bar.open)) / float(bar.open) * 100
                        # Rough TICK estimate from SPY momentum
                        result['tick'] = spy_move * 300  # Scale to TICK range
                        result['add'] = spy_move * 200
                        result['vold'] = spy_move * 500
        except Exception as e:
            log.debug(f"[INTERNALS] SPY snapshot failed: {e}")
        
        # Score the internals
        tick = result.get('tick') or 0
        if tick > 1000:
            result['signal'] = 'extreme_bullish'
            result['score'] = -3  # Contrarian: too hot
            log.info(f"[INTERNALS] TICK={tick:.0f} EXTREME BULLISH — contrarian sell signal")
        elif tick > 600:
            result['signal'] = 'bullish'
            result['score'] = 3
            log.info(f"[INTERNALS] TICK={tick:.0f} BULLISH — healthy breadth")
        elif tick < -1000:
            result['signal'] = 'capitulation'
            result['score'] = 5  # Contrarian buy
            log.info(f"[INTERNALS] TICK={tick:.0f} CAPITULATION — contrarian buy signal")
        elif tick < -600:
            result['signal'] = 'bearish'
            result['score'] = -3
            log.info(f"[INTERNALS] TICK={tick:.0f} BEARISH — weak breadth")
        else:
            result['signal'] = 'neutral'
            result['score'] = 0
        
        _market_internals_cache = {'ts': time.time(), 'data': result}
        
    except Exception as e:
        log.debug(f"[INTERNALS] Market internals error: {e}")
    
    return result


def _tv_confirm_buy(symbol: str) -> tuple[bool, dict]:
    """HARD LAW: Check TradingView indicators before ANY buy.
    Returns (confirmed: bool, indicators: dict).
    
    Confirms if:
    - TV is connected and returns data
    - RSI < 75 (not extremely overbought)
    - At least 2 of: MACD positive, above VWAP, confluence >= 5
    
    Cached for 5 min to avoid re-scanning same stock."""
    # Check cache first
    cached = _tv_cache.get(symbol)
    _tv_ttl = int(_get_pg().get_config('tv_cache_seconds', 300)) if _get_pg() else 300
    if cached and time.time() - cached[0] < _tv_ttl:
        return cached[1].get('_confirmed', False), cached[1]

    # Get fresh TV data
    tv = _get_tv_indicators(symbol)
    if not tv or tv.get('rsi', 0) == 0:
        log.info(f"  📺 TV {symbol}: NO DATA — buy BLOCKED (Hard Law)")
        _pg_log("TV_BLOCKED", symbol=symbol, reason="No TV data — Hard Law", source="tv_confirm")
        return False, {}

    # Evaluate signals
    signals_bullish = 0
    rsi = tv.get('rsi', 50)
    if rsi < 75:
        signals_bullish += 1
    if rsi < 30:
        signals_bullish += 1  # Oversold bonus
    if tv.get('macd_hist', 0) > 0:
        signals_bullish += 1
    if tv.get('vwap_above'):
        signals_bullish += 1
    if tv.get('confluence', 0) >= 5:
        signals_bullish += 1
    if tv.get('ema_9', 0) > tv.get('ema_21', 0) > 0:
        signals_bullish += 1

    # Need at least 2 bullish signals AND RSI not extreme
    confirmed = signals_bullish >= 2 and rsi < 80
    tv['_confirmed'] = confirmed
    tv['_signals'] = signals_bullish
    _tv_cache[symbol] = (time.time(), tv)

    # Log EVERYTHING to PostgreSQL — confirmed or not
    tv_details = {
        'rsi': rsi, 'macd_hist': tv.get('macd_hist', 0),
        'vwap_above': tv.get('vwap_above'), 'confluence': tv.get('confluence', 0),
        'ema_9': tv.get('ema_9', 0), 'ema_21': tv.get('ema_21', 0),
        'volume_ratio': tv.get('volume_ratio', 0),
        'bb_position': tv.get('bb_position', '?'),
        'signals_bullish': signals_bullish, 'confirmed': confirmed,
    }

    if confirmed:
        log.info(f"  📺 TV {symbol}: CONFIRMED ({signals_bullish} signals) RSI={rsi:.0f} MACD={tv.get('macd_hist',0):.2f} VWAP={'↑' if tv.get('vwap_above') else '↓'} Conf={tv.get('confluence',0)}")
        _pg_log("TV_CONFIRMED", symbol=symbol, 
                reason=f"TV OK: {signals_bullish} signals RSI={rsi:.0f} MACD={tv.get('macd_hist',0):.2f} VWAP={'above' if tv.get('vwap_above') else 'below'} C={tv.get('confluence',0)}",
                source="tv_confirm", data=tv_details)
    else:
        log.info(f"  📺 TV {symbol}: REJECTED ({signals_bullish} signals) RSI={rsi:.0f} MACD={tv.get('macd_hist',0):.2f} VWAP={'↑' if tv.get('vwap_above') else '↓'}")
        _pg_log("TV_BLOCKED", symbol=symbol,
                reason=f"TV rejected: {signals_bullish} signals RSI={rsi:.0f} MACD={tv.get('macd_hist',0):.2f} VWAP={'above' if tv.get('vwap_above') else 'below'}",
                source="tv_confirm", data=tv_details)

    # Save TV reading to PostgreSQL tv_readings table
    pg = _get_pg()
    if pg:
        try:
            pg.save_tv_reading(symbol, scan_type='tv_confirm',
                             rsi=rsi, macd_hist=tv.get('macd_hist'),
                             vwap_above=tv.get('vwap_above'), confluence=tv.get('confluence'),
                             ema_9=tv.get('ema_9'), ema_21=tv.get('ema_21'),
                             volume_ratio=tv.get('volume_ratio'), price=tv.get('price', 0))
        except:
            pass

    return confirmed, tv

def _pct(p) -> float:
    """Position P&L percentage."""
    cost = p.avg_entry * p.qty
    return (p.unrealized_pl / cost * 100) if cost > 0 else 0

# Trade action log — tracks all auto-trades for reporting + persists to DB
_trade_log = []
_trade_db = None
_pg_db = None
_cached_vix = 18.0  # Default neutral VIX


def _smart_buy(symbol, qty, price, reason="", day_change_pct=0, sentiment_score=0, source="bot", **kwargs):
    """SMART BUY PIPELINE — 7 gates, every buy must pass ALL.
    
    Gate 1: AI Trends (Claude daily avoid/buy recommendations)
    Gate 2: Sell Cooldown (5 min after selling same stock)
    Gate 3: Anti-Buyback (won't rebuy higher than we sold)
    Gate 4: TV Confirmation (HARD LAW — needs 2+ bullish indicators)
    Gate 5: Self-Learning (historical win rate for this stock)
    Gate 6: VIX Sizing (fear-based position adjustment)
    Gate 7: Execute (place the order via gateway)
    
    HEAVY LOGGING: Every gate logs PASS/FAIL with full context.
    Format designed for human debugging — paste logs to diagnose any trade.
    
    All data stored to trade_decisions + trade_log for learning feedback loop.
    
    kwargs: confidence, sentiment_data, ai_verdict_data, vix, regime,
            spy_change, heat_pct, position_count
    """
    pg = _get_pg()
    
    # ── Capture all context upfront ──
    _sent_data = kwargs.get('sentiment_data') or {'total': sentiment_score}
    _ai_data = kwargs.get('ai_verdict_data')
    _confidence = kwargs.get('confidence', 0)
    original_qty = qty
    decision_ctx = {'reason': reason, 'day_change_pct': day_change_pct,
                    'sentiment': sentiment_score, 'source': source,
                    'original_qty': qty, 'vix': _cached_vix}
    steps = []  # Pipeline audit trail
    
    # ── Header ──
    log.info(f"")
    log.info(f"  {'='*50}")
    log.info(f"  SMART_BUY PIPELINE: {symbol}")
    log.info(f"  {'-'*50}")
    log.info(f"    Input: {qty}x @${price:.2f} | source={source}")
    log.info(f"    Reason: {reason[:80]}")
    log.info(f"    Context: dayChg={day_change_pct:+.1f}% sent={sentiment_score:+d} "
             f"vix={_cached_vix:.1f} aiConf={_confidence}%")
    if _ai_data:
        log.info(f"    AI verdict: {_ai_data.get('action','?')} ({_ai_data.get('confidence',0)}%) "
                 f"— {str(_ai_data.get('reasoning',''))[:60]}")
    log.info(f"  {'-'*50}")

    # ══════════════════════════════════════════════
    # GATE 1: AI TREND CHECK
    # Checks: Claude daily avoid list, earnings patterns, Claude buy recs
    # ══════════════════════════════════════════════
    if pg:
        try:
            trends = pg.get_trends(symbol=symbol)
            log.info(f"    [G1 TRENDS] Found {len(trends)} stored trends for {symbol}")
            for t in trends:
                ttype = t.get('trend_type', '')
                conf = t.get('confidence', 0)
                insight = str(t.get('insight', ''))[:60]
                log.info(f"      > {ttype} (conf:{conf}): {insight}")
                
                # BLOCK: Claude said avoid this stock
                if ttype == 'claude_daily_avoid':
                    log.info(f"    [G1] BLOCKED: Claude daily avoid — {insight}")
                    steps.append(f"G1:BLOCKED claude_avoid")
                    _pg_log("TREND_BLOCKED", symbol=symbol,
                            reason=f"Claude avoid: {insight}", source=source)
                    pg.log_decision(symbol, 'BLOCK', 0,
                        block_reason=f"Claude avoid: {insight}",
                        trend_data={'trends': [dict(t)], 'pipeline': steps},
                        sentiment_data=_sent_data, ai_verdict=_ai_data,
                        strategy=source, price_at_decision=price)
                    log.info(f"  {'='*50}\n")
                    return None
                
                # BLOCK: Stock dips after earnings and earnings is TODAY
                if ttype == 'earnings_pattern' and 'DIPS_AFTER' in str(t.get('insight', '')):
                    sa = SentimentAnalyst()
                    earn = sa.get_earnings_info(symbol)
                    days = earn.get('days_until', 999)
                    log.info(f"      Earnings in {days} days — dips_after pattern active")
                    if days == 0:
                        log.info(f"    [G1] BLOCKED: Earnings TODAY + dips_after pattern")
                        steps.append("G1:BLOCKED earnings_today_dip")
                        _pg_log("TREND_WAIT", symbol=symbol,
                                reason="Earnings today + dips pattern", source=source)
                        pg.log_decision(symbol, 'SKIP', 0,
                            block_reason="Earnings TODAY + dips_after pattern",
                            trend_data={'pattern': 'dips_after', 'days': days},
                            sentiment_data=_sent_data, ai_verdict=_ai_data,
                            strategy=source, price_at_decision=price)
                        log.info(f"  {'='*50}\n")
                        return None
                
                # BOOST: Claude recommended buying this stock
                if ttype == 'claude_daily_buy' and conf >= 70:
                    old_qty = qty
                    qty = int(qty * 1.3)
                    log.info(f"    [G1] BOOST: Claude buy rec (conf:{conf}%) — qty {old_qty}->{qty}")
                    steps.append(f"G1:BOOST qty {old_qty}->{qty}")
                    decision_ctx['claude_boost'] = True
            
            log.info(f"    [G1] PASSED: No blocking trends")
            steps.append("G1:PASS")
        except Exception as e:
            log.info(f"    [G1] ERROR reading trends: {e} — proceeding anyway")
            steps.append(f"G1:ERROR {e}")
    else:
        log.info(f"    [G1] SKIPPED: No DB connection")
        steps.append("G1:SKIP no_db")

    # ══════════════════════════════════════════════
    # GATE 2: SELL COOLDOWN
    # Prevents emotional re-entries after selling same stock
    # Blue chips get shorter cooldown (2 min vs 5 min) — they run fast
    # INTC lesson: sold $87, rebought $93 = -$165
    # ══════════════════════════════════════════════
    is_blue_chip = pg.is_blue_chip(symbol) if pg else False
    if is_blue_chip:
        cooldown_sec = int(pg.get_config('cooldown_blue_chip_sec', 120)) if pg else 120
    else:
        cooldown_sec = int(pg.get_config('cooldown_after_sell_sec', 300)) if pg else 300
    
    if pg and pg.check_sell_cooldown(symbol, cooldown_sec):
        mem = pg.get_price_memory(symbol)
        sell_time = str(mem.get('last_sell_time', '?'))[:19]
        sell_price = mem.get('last_sell_price', 0)
        log.info(f"    [G2] BLOCKED: Sold {symbol} at {sell_time} @${sell_price:.2f} — "
                 f"cooldown {cooldown_sec}s not elapsed (blue_chip={is_blue_chip})")
        steps.append(f"G2:BLOCKED cooldown={cooldown_sec}s blue={is_blue_chip}")
        pg.log_decision(symbol, 'BLOCK', 0,
            block_reason=f"Sell cooldown ({cooldown_sec}s, blue={is_blue_chip}) — sold @${sell_price:.2f}",
            sentiment_data=_sent_data, ai_verdict=_ai_data,
            signals={'pipeline': steps, 'cooldown_sec': cooldown_sec,
                     'sell_time': sell_time, 'sell_price': sell_price,
                     'is_blue_chip': is_blue_chip},
            strategy=source, price_at_decision=price)
        log.info(f"  {'='*50}\n")
        return None
    log.info(f"    [G2] PASSED: No sell cooldown (limit={cooldown_sec}s, blue={is_blue_chip})")
    steps.append(f"G2:PASS cooldown={cooldown_sec}s")

    # ══════════════════════════════════════════════
    # GATE 3: ANTI-BUYBACK (V5: with timeout + price reset)
    # Won't rebuy higher than we sold — prevents round-trip losses
    # V5 RESETS:
    #   - 30 min timeout: anti-buyback expires after 30 min
    #   - Price threshold: if price > sold+3%, it's a new trend
    #   - AI override: AI confidence >= 80% with fresh verdict
    #   - Blue chip: sentiment >= +3 OR breakout > +5%
    # ══════════════════════════════════════════════
    ANTI_BUYBACK_TIMEOUT_MIN = 30
    ANTI_BUYBACK_PRICE_RESET_PCT = 3.0  # +3% above sold = new trend
    ANTI_BUYBACK_AI_OVERRIDE = 80       # AI conf >= 80% can override
    
    if pg and pg.check_anti_buyback(symbol, price):
        mem = pg.get_price_memory(symbol)
        sold_at = mem.get('last_sell_price', 0)
        sold_time_str = mem.get('last_sell_time', '')
        diff = price - sold_at
        pct_above = (diff / sold_at * 100) if sold_at > 0 else 0
        
        # Calculate elapsed time since sell
        elapsed_min = 999
        try:
            from datetime import datetime as dt2
            if sold_time_str:
                sold_dt = dt2.fromisoformat(str(sold_time_str).replace('Z', '+00:00').split('+')[0])
                elapsed_min = (dt2.utcnow() - sold_dt).total_seconds() / 60
        except:
            elapsed_min = 999
        
        # V5 Smart reset conditions
        reset_reason = None
        if elapsed_min >= ANTI_BUYBACK_TIMEOUT_MIN:
            reset_reason = f"timeout ({elapsed_min:.0f}min >= {ANTI_BUYBACK_TIMEOUT_MIN}min)"
        elif pct_above >= ANTI_BUYBACK_PRICE_RESET_PCT:
            reset_reason = f"new trend (+{pct_above:.1f}% >= +{ANTI_BUYBACK_PRICE_RESET_PCT}%)"
        elif _confidence >= ANTI_BUYBACK_AI_OVERRIDE:
            reset_reason = f"AI override (conf={_confidence}% >= {ANTI_BUYBACK_AI_OVERRIDE}%)"
        elif is_blue_chip and has_strong_sent:
            reset_reason = f"blue chip + sentiment {sentiment_score:+d}"
        elif is_blue_chip and pct_above > 5:
            reset_reason = f"blue chip breakout +{pct_above:.1f}%"
        
        if reset_reason:
            log.info(f"    [G3] RESET: Anti-buyback overridden for {symbol} — {reset_reason}. "
                     f"Sold @${sold_at:.2f} ({elapsed_min:.0f}min ago), rebuy @${price:.2f} (+{pct_above:.1f}%)")
            steps.append(f"G3:RESET {reset_reason}")
            # Clear the anti-buyback in DB so we don't re-block
            try:
                pg._exec("UPDATE price_memory SET last_sell_price = NULL WHERE symbol = %s", (symbol,))
            except:
                pass
        else:
            log.info(f"    [G3] BLOCKED: Anti-buyback — sold @${sold_at:.2f} ({elapsed_min:.0f}min ago), "
                     f"now @${price:.2f} (+{pct_above:.1f}%). "
                     f"Resets: timeout={max(0, ANTI_BUYBACK_TIMEOUT_MIN - elapsed_min):.0f}min, "
                     f"price=need +{ANTI_BUYBACK_PRICE_RESET_PCT}%, ai_conf={_confidence}% (need {ANTI_BUYBACK_AI_OVERRIDE}%)")
            steps.append(f"G3:BLOCKED sold@{sold_at:.2f} rebuy@{price:.2f}")
            pg.log_decision(symbol, 'BLOCK', 0,
                block_reason=f"Anti-buyback: sold @${sold_at:.2f}, now ${price:.2f} (+{pct_above:.1f}%)",
                sentiment_data=_sent_data, ai_verdict=_ai_data,
                signals={'pipeline': steps, 'sold_at': sold_at, 'rebuy_at': price,
                         'pct_above': pct_above, 'is_blue_chip': is_blue_chip,
                         'elapsed_min': elapsed_min, 'reset_conditions': {
                             'timeout_left': max(0, ANTI_BUYBACK_TIMEOUT_MIN - elapsed_min),
                             'price_needed': ANTI_BUYBACK_PRICE_RESET_PCT,
                             'ai_conf_needed': ANTI_BUYBACK_AI_OVERRIDE}},
                strategy=source, price_at_decision=price)
            log.info(f"  {'='*50}\n")
            return None
    log.info(f"    [G3] PASSED: No anti-buyback issue")
    steps.append("G3:PASS")

    # ══════════════════════════════════════════════
    # GATE 4: TV CONFIRMATION (HARD LAW)
    # The most important gate — no TV = no trade, period.
    # Needs 2+ bullish signals from RSI, MACD, VWAP, EMA, confluence
    # ══════════════════════════════════════════════
    log.info(f"    [G4] Scanning TradingView for {symbol}...")
    confirmed, tv = _tv_confirm_buy(symbol)
    if tv:
        log.info(f"      RSI={tv.get('rsi',0):.0f} MACD={tv.get('macd_hist',0):.3f} "
                 f"VWAP={'ABOVE' if tv.get('vwap_above') else 'BELOW'} "
                 f"Conf={tv.get('confluence',0)}/10 "
                 f"EMA9={tv.get('ema_9',0):.1f}/{tv.get('ema_21',0):.1f} "
                 f"Vol={tv.get('volume_ratio',0):.1f}x BB={tv.get('bb_position','?')}")
        log.info(f"      Bullish signals: {tv.get('_signals',0)} | Confirmed: {confirmed}")
    else:
        log.info(f"      NO TV DATA — Hard Law blocks this buy")
    
    if not confirmed:
        reason_str = f"TV rejected ({tv.get('_signals',0)} signals)" if tv else "No TV data"
        log.info(f"    [G4] BLOCKED: {reason_str}")
        steps.append(f"G4:BLOCKED {reason_str}")
        if pg:
            pg.log_decision(symbol, 'BLOCK', 0,
                tv_data=tv, block_reason=reason_str,
                sentiment_data=_sent_data, ai_verdict=_ai_data,
                signals={'pipeline': steps},
                strategy=source, price_at_decision=price)
        log.info(f"  {'='*50}\n")
        return None
    log.info(f"    [G4] PASSED: TV confirmed ({tv.get('_signals',0)} bullish signals)")
    steps.append(f"G4:PASS signals={tv.get('_signals',0)}")

    # ══════════════════════════════════════════════
    # GATE 5: SELF-LEARNING
    # Checks: how did we do LAST TIME we traded this stock?
    # Adjusts qty: proven winners get MORE, losers get LESS
    # ══════════════════════════════════════════════
    if pg:
        try:
            advice = pg.should_trade_stock(symbol)
            trade_ok = advice.get('trade', True)
            size = advice.get('size', 'normal')
            learn_reason = advice.get('reason', 'no history')
            log.info(f"    [G5] History: trade={trade_ok} size={size} — {learn_reason[:60]}")
            
            if not trade_ok:
                log.info(f"    [G5] BLOCKED: Self-learn says SKIP — {learn_reason}")
                steps.append(f"G5:BLOCKED {learn_reason[:30]}")
                _pg_log("SELF_LEARN_SKIP", symbol=symbol,
                        reason=learn_reason, source=source)
                pg.log_decision(symbol, 'SKIP', 0,
                    tv_data=tv, block_reason=f"Self-learn: {learn_reason}",
                    sentiment_data=_sent_data, ai_verdict=_ai_data,
                    signals={'pipeline': steps, 'advice': advice},
                    strategy=source, price_at_decision=price)
                log.info(f"  {'='*50}\n")
                return None
            if size == 'large':
                old_qty = qty
                qty = int(qty * 1.5)
                log.info(f"    [G5] BOOST: Proven winner — qty {old_qty}->{qty}")
                steps.append(f"G5:BOOST {old_qty}->{qty}")
            elif size == 'small':
                old_qty = qty
                qty = max(1, qty // 2)
                log.info(f"    [G5] REDUCE: Poor history — qty {old_qty}->{qty}")
                steps.append(f"G5:REDUCE {old_qty}->{qty}")
            else:
                log.info(f"    [G5] PASSED: Normal size")
                steps.append("G5:PASS normal")
        except Exception as e:
            log.info(f"    [G5] ERROR: {e} — proceeding with normal size")
            steps.append(f"G5:ERROR")
    else:
        steps.append("G5:SKIP no_db")

    # ══════════════════════════════════════════════
    # GATE 5.5: FUNDAMENTALS CHECK (from DB cache)
    # Boosts proven stocks, warns on weak ones
    # ══════════════════════════════════════════════
    if pg:
        try:
            fund_trends = pg.get_trends(symbol=symbol, trend_type='fundamentals')
            if fund_trends:
                fund_data = fund_trends[0].get('data', {})
                fund_score = fund_data.get('score', 0)
                fund_verdict = fund_data.get('verdict', '?')
                fund_upside = fund_data.get('upside', 0)
                log.info(f"    [G5.5] Fundamentals: {fund_verdict} (score={fund_score}) "
                         f"PE={fund_data.get('pe',0)} upside={fund_upside:+.0f}%")
                if fund_score >= 40:
                    old_qty = qty
                    qty = int(qty * 1.3)
                    log.info(f"    [G5.5] BOOST: Strong fundamentals — qty {old_qty}->{qty}")
                    steps.append(f"G5.5:BOOST fund_score={fund_score}")
                elif fund_score < -10:
                    old_qty = qty
                    qty = max(1, qty // 2)
                    log.info(f"    [G5.5] REDUCE: Weak fundamentals — qty {old_qty}->{qty}")
                    steps.append(f"G5.5:REDUCE fund_score={fund_score}")
                else:
                    steps.append(f"G5.5:PASS fund={fund_score}")
            else:
                steps.append("G5.5:SKIP no_fund_data")
        except:
            steps.append("G5.5:ERROR")

    # ══════════════════════════════════════════════
    # GATE 6: VIX SIZING
    # VIX>30 = high fear, halve position. VIX<15 = greed, boost.
    # ══════════════════════════════════════════════
    old_qty = qty
    if _cached_vix > 30:
        qty = max(1, qty // 2)
        log.info(f"    [G6] VIX={_cached_vix:.1f} HIGH FEAR — halved qty {old_qty}->{qty}")
        steps.append(f"G6:HALVED vix={_cached_vix:.0f}")
    elif _cached_vix > 25:
        qty = max(1, int(qty * 0.7))
        log.info(f"    [G6] VIX={_cached_vix:.1f} ELEVATED — reduced qty {old_qty}->{qty}")
        steps.append(f"G6:REDUCED vix={_cached_vix:.0f}")
    elif _cached_vix < 15:
        qty = int(qty * 1.3)
        log.info(f"    [G6] VIX={_cached_vix:.1f} LOW FEAR — boosted qty {old_qty}->{qty}")
        steps.append(f"G6:BOOSTED vix={_cached_vix:.0f}")
    else:
        log.info(f"    [G6] VIX={_cached_vix:.1f} NORMAL — no adjustment")
        steps.append(f"G6:PASS vix={_cached_vix:.0f}")

    # ══════════════════════════════════════════════
    # GATE 6.5: RISK MANAGER (V5)
    # Kelly sizing, daily loss limits, correlation, sector caps, earnings
    # ══════════════════════════════════════════════
    if risk_mgr:
        try:
            positions = gateway.get_positions()
            acct = gateway.get_account()
            equity = float(acct.get('equity', 100000))
            
            risk_result = risk_mgr.approve_trade(
                symbol=symbol, side='buy', qty=qty,
                price=price, conviction=_confidence / 100.0,
                positions=positions, equity=equity
            )
            
            if not risk_result.get('approved', True):
                rejections = risk_result.get('rejections', [])
                log.info(f"    [G6.5] BLOCKED by RiskManager: {', '.join(rejections)}")
                steps.append(f"G6.5:BLOCKED {rejections[0] if rejections else 'unknown'}")
                if pg:
                    pg.log_decision(symbol, 'BLOCK', 0,
                        block_reason=f"RiskManager: {', '.join(rejections)}",
                        sentiment_data=_sent_data, ai_verdict=_ai_data,
                        signals={'pipeline': steps, 'risk_checks': risk_result.get('checks', {})},
                        strategy=source, price_at_decision=price)
                log.info(f"  {'='*50}\n")
                return None
            
            adjusted = risk_result.get('adjusted_qty', qty)
            if adjusted != qty:
                old_qty = qty
                qty = adjusted
                adj_reasons = risk_result.get('adjustments', [])
                log.info(f"    [G6.5] ADJUSTED: qty {old_qty}->{qty} | {adj_reasons}")
                steps.append(f"G6.5:ADJUSTED {old_qty}->{qty}")
            else:
                log.info(f"    [G6.5] PASSED: RiskManager approved {qty}x")
                steps.append("G6.5:PASS")
        except Exception as e:
            log.info(f"    [G6.5] ERROR: {e} — proceeding without risk check")
            steps.append(f"G6.5:ERROR")

    # ══════════════════════════════════════════════
    # GATE 6.7: PRO DATA INTEL (V5)
    # Congressional trades, insider buys, dark pool, short interest
    # ══════════════════════════════════════════════
    if pro_data:
        try:
            intel = pro_data.get_full_intel(symbol)
            pro_score = intel.get('score', 0)
            breakdown = intel.get('breakdown', {})
            active = {k: v for k, v in breakdown.items() if v != 0}
            
            if active:
                log.info(f"    [G6.7] Pro intel: score={pro_score:+d} | {active}")
            
            # Strong negative pro signal = reduce
            if pro_score <= -15:
                old_qty = qty
                qty = max(1, qty // 2)
                log.info(f"    [G6.7] REDUCE: Strong negative pro signal ({pro_score}) — qty {old_qty}->{qty}")
                steps.append(f"G6.7:REDUCE pro_score={pro_score}")
            # Strong positive = boost
            elif pro_score >= 15:
                old_qty = qty
                qty = int(qty * 1.3)
                log.info(f"    [G6.7] BOOST: Strong positive pro signal ({pro_score}) — qty {old_qty}->{qty}")
                steps.append(f"G6.7:BOOST pro_score={pro_score}")
            else:
                steps.append(f"G6.7:PASS pro_score={pro_score}")
            
            # High-impact event tomorrow = halve
            try:
                conditions = pro_data.get_market_conditions()
                if conditions.get('economic', {}).get('high_impact_tomorrow'):
                    old_qty = qty
                    qty = max(1, qty // 2)
                    log.info(f"    [G6.7] REDUCE: High-impact economic event tomorrow — qty {old_qty}->{qty}")
                    steps.append("G6.7:ECON_EVENT_REDUCE")
            except:
                pass
                
        except Exception as e:
            log.info(f"    [G6.7] ERROR: {e} — proceeding without pro data")
            steps.append("G6.7:ERROR")

    # ══════════════════════════════════════════════
    # GATE 6.9: MARKET INTERNALS (V5)
    # $TICK, $ADD, $VOLD — what pros check every 5 min
    # ══════════════════════════════════════════════
    try:
        internals = _get_market_internals()
        tick = internals.get('tick')
        signal = internals.get('signal', 'unknown')
        int_score = internals.get('score', 0)
        if tick is not None:
            log.info(f"    [G6.9] Market internals: TICK={tick:.0f} signal={signal} score={int_score:+d}")
            if signal == 'bearish' and int_score <= -3:
                old_qty = qty
                qty = max(1, qty // 2)
                log.info(f"    [G6.9] REDUCE: Bearish internals — qty {old_qty}->{qty}")
                steps.append(f"G6.9:REDUCE internals={signal}")
            elif signal == 'capitulation':
                old_qty = qty
                qty = int(qty * 1.3)
                log.info(f"    [G6.9] BOOST: Capitulation buy signal — qty {old_qty}->{qty}")
                steps.append(f"G6.9:BOOST capitulation")
            elif signal == 'extreme_bullish':
                old_qty = qty
                qty = max(1, int(qty * 0.7))
                log.info(f"    [G6.9] REDUCE: Extreme bullish (contrarian) — qty {old_qty}->{qty}")
                steps.append(f"G6.9:REDUCE extreme_bull")
            else:
                steps.append(f"G6.9:PASS {signal}")
        else:
            steps.append("G6.9:SKIP no_data")
    except Exception as e:
        log.debug(f"    [G6.9] ERROR: {e}")
        steps.append("G6.9:ERROR")

    # ── Persist TV reading ──
    if pg and tv:
        try:
            pg.save_tv_reading(symbol, scan_type=source,
                rsi=tv.get('rsi'), macd_hist=tv.get('macd_hist'),
                vwap_above=tv.get('vwap_above'), confluence=tv.get('confluence'),
                ema_9=tv.get('ema_9'), ema_21=tv.get('ema_21'),
                volume_ratio=tv.get('volume_ratio'), price=price)
        except:
            pass

    # ══════════════════════════════════════════════
    # GATE 7: EXECUTE — All gates passed!
    # ══════════════════════════════════════════════
    log.info(f"  {'-'*50}")
    log.info(f"    ALL 6 GATES PASSED — EXECUTING BUY")
    log.info(f"    Final order: {symbol} {qty}x @${price:.2f} (original: {original_qty}x)")
    log.info(f"    Pipeline: {' > '.join(steps)}")
    
    result = gateway.quick_buy(symbol, qty, price, reason=reason,
                            day_change_pct=day_change_pct,
                            sentiment_score=sentiment_score,
                            vix=_cached_vix, tv_confirmed=True,
                            ai_confidence=_confidence)

    # ── Log outcome with FULL context ──
    if pg:
        executed = (result is not None and hasattr(result, 'state')
                    and result.state.value != 'REJECTED')
        exec_result = (result.state.value
                       if result and hasattr(result, 'state') else 'FAILED')
        order_id = result.id if result and hasattr(result, 'id') else None
        
        log.info(f"    Result: {'EXECUTED' if executed else 'REJECTED'} — {exec_result}")
        if order_id:
            log.info(f"    Order ID: {order_id}")
        steps.append(f"G7:{'OK' if executed else 'REJECTED'} {exec_result}")
        
        # Store decision with ALL context
        pg.log_decision(symbol, 'BUY', confidence=_confidence,
            tv_data=tv, sentiment_data=_sent_data, ai_verdict=_ai_data,
            signals={'pipeline': steps, 'original_qty': original_qty,
                     'final_qty': qty, 'vix': _cached_vix,
                     'day_change_pct': day_change_pct},
            executed=executed, execution_result=exec_result,
            order_id=str(order_id) if order_id else None,
            strategy=source, price_at_decision=price)
        
        if executed:
            # Record in price memory
            pg.record_buy(symbol, price)
            # Deep trade log with full AI reasoning
            pg.log_trade_deep(symbol, 'buy', qty, price,
                strategy=source, source=source, trigger=reason[:100],
                tv_at_trade=tv, sentiment_at_trade=_sent_data,
                ai_verdict_at_trade=_ai_data, confidence=_confidence,
                ai_reasoning=f"Pipeline: {' > '.join(steps)}",
                regime=kwargs.get('regime'), vix=_cached_vix,
                spy_change=kwargs.get('spy_change', 0),
                heat_pct=kwargs.get('heat_pct', 0),
                position_count=kwargs.get('position_count', 0),
                day_change_pct=day_change_pct,
                order_result=exec_result,
                order_id=str(order_id) if order_id else None)
            # Update counters
            pg.set_state('last_trade_time',
                         time.strftime('%Y-%m-%dT%H:%M:%SZ'), 'runtime')
            trades_today = pg.get_state('trades_today', 0)
            pg.set_state('trades_today', trades_today + 1, 'daily')
            # Dashboard notification with rich detail
            pg.notify(f"BUY {symbol}",
                f"{qty}x @${price:.2f} | {reason[:60]}\n"
                f"TV: RSI={tv.get('rsi',0):.0f} MACD={tv.get('macd_hist',0):.2f} "
                f"VWAP={'above' if tv.get('vwap_above') else 'below'}\n"
                f"Sent: {sentiment_score:+d} | VIX: {_cached_vix:.1f}",
                severity='success', symbol=symbol, category='trade',
                data={'pipeline': steps, 'tv': tv, 'sentiment': _sent_data})

    log.info(f"  {'='*50}\n")
    return result

def _get_trade_db():
    global _trade_db
    if _trade_db is None:
        try:
            from trade_db import TradeDB
            _trade_db = TradeDB()
        except Exception as e:
            log.warning(f"TradeDB init failed: {e}")
    return _trade_db

def _get_pg():
    """Get PostgreSQL database connection (Beast Terminal V4)."""
    global _pg_db
    if _pg_db is None:
        try:
            from db_postgres import BeastDB
            _pg_db = BeastDB()
            if _pg_db.conn:
                _pg_db.migrate_v4()  # Auto-create V4 tables
                log.info("📦 PostgreSQL connected + V4 schema ready")
        except Exception as e:
            log.debug(f"PostgreSQL not available: {e}")
    return _pg_db

def _log_trade(action, symbol, qty, price, reason, scan_type="60s"):
    """Log a trade action to memory + SQLite + PostgreSQL."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    _trade_log.append({
        'time': now.strftime('%H:%M:%S'),
        'action': action,
        'symbol': symbol,
        'qty': qty,
        'price': price,
        'reason': reason,
        'scan_type': scan_type,
    })
    # Persist to SQLite (legacy)
    db = _get_trade_db()
    if db:
        try:
            db.log_entry(symbol=symbol, qty=qty, price=price,
                        strategy=scan_type, reason=f"{action}: {reason}")
        except Exception as e:
            log.debug(f"Trade DB write failed: {e}")
    # Persist to PostgreSQL (V4)
    side = 'sell' if 'SELL' in action.upper() else 'buy'
    _pg_log(action.split('(')[0].strip(), symbol=symbol, side=side,
            qty=qty, price=price, reason=reason, strategy=scan_type, source=scan_type)


def _pg_log(action_type, symbol=None, side=None, qty=None, price=None,
            reason=None, strategy=None, source=None, confidence=None,
            ai_source=None, data=None):
    """Universal PostgreSQL logger. Logs EVERY bot action with timestamp.
    Call this for: scans, AI verdicts, trades, alerts, blocks, errors, everything."""
    pg = _get_pg()
    if pg:
        try:
            pg.log_activity(
                action_type=action_type, symbol=symbol, side=side,
                qty=qty, price=price, reason=reason, strategy=strategy,
                source=source, confidence=confidence, ai_source=ai_source,
                data=data
            )
        except Exception as e:
            log.debug(f"PG log failed: {e}")

def _is_market_hours() -> bool:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    return 9 <= now.hour < 16 or (now.hour == 9 and now.minute >= 30)

def _is_extended_hours() -> bool:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    return (4 <= now.hour < 9) or (16 <= now.hour < 20)

def _is_trading_hours() -> bool:
    """Pre-market (4AM) + market (9:30-4PM) + after-hours (4-8PM).
    GTC orders fill during ALL sessions. This is when we can trade."""
    return _is_market_hours() or _is_extended_hours()


@tasks.loop(seconds=60)
async def position_monitor():
    """Every 60s: check positions, alert drops, auto-scalp, auto-protect, auto-buy dips."""
    global _prev_prices, _cycle_count, _cached_vix
    _cycle_count += 1
    pg = _get_pg()

    # Persist cycle count to DB (dashboard can see it)
    if pg and _cycle_count % 5 == 0:
        pg.set_state('cycle_count', _cycle_count, 'runtime')
        pg.set_state('last_monitor_time', time.strftime('%Y-%m-%dT%H:%M:%SZ'), 'runtime')

    # Check kill switch from DB (dashboard can flip this)
    if pg and pg.is_kill_switch_on():
        if _cycle_count % 60 == 0:
            log.info("🛑 KILL SWITCH ON — skipping position monitor")
        return

    # Refresh VIX every 10 cycles
    if _cycle_count % 10 == 0:
        try:
            sa = SentimentAnalyst()
            fg = sa.get_fear_greed()
            _cached_vix = fg.get('vix', 18.0)
        except:
            pass
    try:
        positions = gateway.get_positions()
        if not positions:
            return
        channel = bot.get_channel(SCAN_CHANNEL_ID)
        total_pl = sum(p.unrealized_pl for p in positions)
        greens = sum(1 for p in positions if p.unrealized_pl >= 0)
        held_symbols = {p.symbol for p in positions}

        # ── ACTIVE SCALPER: only protect RED, actively trade GREEN ──
        # NON-BLUE-CHIP LOSS CUT: uses DB blue_chips table (dashboard-editable)
        # Tier 1 blue chips: never sell at loss. Tier 2: cut at max_loss_pct from DB.
        blue_chip_set = pg.get_blue_chip_symbols() if pg else set()
        if _is_trading_hours() and _cycle_count % 3 == 0:
            try:
                open_orders = await asyncio.to_thread(gateway.get_open_orders)
                protected = set()
                for o in open_orders:
                    if 'trailing' in str(o.get('type', '')).lower():
                        protected.add(o.get('symbol', ''))
                for p in positions:
                    pct = _pct(p)
                    avail = p.qty_available or 0

                    # LOSS CUT LOGIC (DB-driven + fundamentals-aware)
                    if pct <= -5.0 and avail > 0:
                        cut_key = f"_cut_{p.symbol}"
                        if not _prev_prices.get(cut_key):
                            # Check fundamentals from DB (stored by hourly learning)
                            fund_score = 0
                            fund_verdict = ''
                            if pg:
                                try:
                                    ft = pg.get_trends(symbol=p.symbol, trend_type='fundamentals')
                                    if ft:
                                        fd = ft[0].get('data', {})
                                        fund_score = fd.get('score', 0)
                                        fund_verdict = fd.get('verdict', '')
                                except:
                                    pass

                            if p.symbol in blue_chip_set:
                                bc_info = pg.get_blue_chip_info(p.symbol) if pg else {}
                                max_loss = bc_info.get('max_loss_pct', -999)
                                tier = bc_info.get('tier', 1)
                                if max_loss != -999 and pct <= max_loss:
                                    cut_qty = max(1, avail // 2)
                                    log.info(f"    LOSS CUT: {p.symbol} tier-{tier} blue chip at {pct:.1f}% (max: {max_loss}%) fund={fund_verdict}")
                                else:
                                    log.info(f"    HOLD: {p.symbol} tier-{tier} blue chip at {pct:.1f}% — will recover (fund={fund_verdict})")
                                    continue
                            elif fund_score >= 40:
                                # STRONG fundamentals = hold even non-blue-chip longer
                                if pct > -10:
                                    log.info(f"    HOLD: {p.symbol} at {pct:.1f}% but STRONG fundamentals (score={fund_score}) — holding")
                                    _pg_log("FUND_HOLD", symbol=p.symbol, reason=f"Strong fundamentals (score={fund_score}) overrides loss cut at {pct:.1f}%", source="60s")
                                    continue
                                else:
                                    # Even strong fundamentals can't save -10%+
                                    cut_qty = max(1, avail // 2)
                                    log.info(f"    LOSS CUT: {p.symbol} at {pct:.1f}% — even strong fundamentals can't hold -10%+")
                            elif fund_score < -10:
                                # WEAK fundamentals = cut FASTER (at -3% instead of -5%)
                                cut_qty = avail if pct <= -8 else max(1, avail // 2)
                                log.info(f"    LOSS CUT: {p.symbol} at {pct:.1f}% — WEAK fundamentals (score={fund_score}) — cutting aggressively")
                            else:
                                # Normal non-blue-chip
                                if pct <= -10.0:
                                    cut_qty = avail
                                else:
                                    cut_qty = max(1, avail // 2)
                            try:
                                sell_price = round(p.current_price * 0.999, 2)
                                gateway.place_sell(p.symbol, cut_qty, sell_price,
                                    reason=f"Loss cut {pct:.1f}% (non-blue-chip)", entry_price=p.avg_entry)
                                _prev_prices[cut_key] = True
                                if pg: pg.record_sell(p.symbol, sell_price)
                                _log_trade("LOSS CUT", p.symbol, cut_qty, sell_price,
                                    f"Non-blue-chip at {pct:.1f}% — cutting losses", "60s LossCut")
                                if channel:
                                    await channel.send(f"🔪 **LOSS CUT: {p.symbol}** {pct:.1f}% — selling {cut_qty} (not blue chip)")
                                _tg(f"🔪 LOSS CUT: {p.symbol} {pct:.1f}%\nSelling {cut_qty} shares (non-blue-chip)")
                            except:
                                pass
                            continue

                    # Only trail RED positions that aren't already protected
                    if pct < 0 and p.symbol not in protected and avail > 0:
                        try:
                            trail_qty = max(1, avail // 2)
                            gateway.place_trailing_stop(p.symbol, trail_qty, trail_percent=3.0,
                                                        reason=f"Protect RED {pct:.1f}%",
                                                        entry_price=p.avg_entry)
                            _log_trade("TRAILING STOP", p.symbol, trail_qty, 0,
                                       f"RED {pct:.1f}% — protecting {trail_qty} shares", "60s")
                            _pg_log("PROTECT", symbol=p.symbol, qty=trail_qty, reason=f"RED {pct:.1f}%", source="60s")
                        except:
                            pass
            except:
                pass

        for p in positions:
            prev = _prev_prices.get(p.symbol, p.current_price)
            pct = _pct(p)
            avail = p.qty_available or 0

            # Track intraday high for dip detection — persist to DB
            high_key = f"_hi_{p.symbol}"
            if p.current_price > _prev_prices.get(high_key, 0):
                _prev_prices[high_key] = p.current_price
            # Also persist price to DB (survives restart)
            if pg:
                try:
                    pg.update_price(p.symbol, p.current_price)
                except:
                    pass

            if _is_trading_hours() and avail > 0:
                # ── SMART SELL: Check trade_style from learning before scalping ──
                last_scalp = _prev_prices.get(f"_scalp_t_{p.symbol}", 0)
                if pct >= 2.0 and time.time() - last_scalp > 900:
                    # What style is this stock? SCALP / SWING / CORE
                    trade_style = 'SCALP'  # default
                    fund_upside = 0
                    if pg:
                        try:
                            ts = pg.get_trends(symbol=p.symbol, trend_type='trade_style')
                            if ts:
                                trade_style = ts[0].get('data', {}).get('classification', 'SCALP')
                            ft = pg.get_trends(symbol=p.symbol, trend_type='fundamentals')
                            if ft:
                                fund_upside = ft[0].get('data', {}).get('upside', 0)
                        except:
                            pass
                    
                    if trade_style == 'CORE':
                        # CORE = don't scalp at all, let it ride with trailing stop
                        log.info(f"    HOLD: {p.symbol} +{pct:.1f}% — CORE position (fund upside {fund_upside:+.0f}%), no scalp")
                        _pg_log("CORE_HOLD", symbol=p.symbol,
                                reason=f"CORE: +{pct:.1f}% but upside {fund_upside:+.0f}% — holding", source="60s")
                        sell_qty = 0
                    elif trade_style == 'SWING' and pct < 5:
                        # SWING = don't scalp until +5% minimum
                        log.info(f"    HOLD: {p.symbol} +{pct:.1f}% — SWING (wait for +5%, upside {fund_upside:+.0f}%)")
                        sell_qty = 0
                    elif trade_style == 'SWING' and pct >= 5:
                        # SWING at +5%+ — sell 1/3, keep 2/3
                        sell_qty = max(1, avail // 3)
                        log.info(f"    SWING SELL: {p.symbol} +{pct:.1f}% — selling {sell_qty}/{avail} (swing target hit)")
                    elif fund_upside > 20 and avail > 2:
                        # Strong fundamentals — scalp only 1/3
                        sell_qty = max(1, avail // 3)
                        log.info(f"    SMART SCALP: {p.symbol} +{pct:.1f}% — selling {sell_qty}/{avail} (upside {fund_upside:+.0f}%)")
                    else:
                        # SCALP = normal quick flip
                        sell_qty = max(1, avail // 2) if avail > 1 else avail
                    
                    if sell_qty > 0:
                        sell_price = round(p.current_price * 0.999, 2)
                    try:
                        gateway.place_sell(p.symbol, sell_qty, sell_price,
                                          reason=f"Scalp +{pct:.1f}%", entry_price=p.avg_entry)
                        _prev_prices[f"_scalp_t_{p.symbol}"] = time.time()
                        if pg: pg.record_scalp(p.symbol)
                        if pg: pg.record_sell(p.symbol, sell_price)
                        _log_trade("SCALP SELL", p.symbol, sell_qty, sell_price,
                                   f"+{pct:.1f}% — selling {sell_qty} for profit", "60s Scalp")
                        if channel:
                            await channel.send(
                                f"🎯 **SCALP: {p.symbol}** +{pct:.1f}% — sell {sell_qty} @ ${sell_price}")
                    except Exception as e:
                        log.debug(f"Scalp {p.symbol}: {e}")

            # ── DIP RELOAD: stock dropped >2% from intraday high → buy more for next scalp ──
            if _is_trading_hours():
                intraday_high = _prev_prices.get(high_key, 0)
                if intraday_high > 0 and p.current_price < intraday_high * 0.98 and pct > -3:
                    dip_pct = (p.current_price - intraday_high) / intraday_high * 100
                    reload_key = f"_reload_t_{p.symbol}"
                    if time.time() - _prev_prices.get(reload_key, 0) > 1800:  # 30min cooldown
                        try:
                            acct_data = gateway.get_account()
                            cash = float(acct_data.get('cash', 0))
                            if cash > 3000:
                                reload_qty = max(1, int(cash * 0.02 / p.current_price))
                                buy_price = round(p.current_price * 1.001, 2)
                                result = _smart_buy(p.symbol, reload_qty, buy_price,
                                    reason=f"Dip reload {dip_pct:.1f}% from ${intraday_high:.2f}",
                                    source="60s_reload", vix=_cached_vix)
                                if result and result.state.value != 'REJECTED':
                                    _prev_prices[reload_key] = time.time()
                                    if pg: pg.record_reload(p.symbol)
                                    if pg: pg.record_buy(p.symbol, buy_price)
                                    _log_trade("DIP RELOAD", p.symbol, reload_qty, buy_price,
                                               f"Dropped {dip_pct:.1f}% from high. Scalp reload.", "60s Reload")
                                    if channel:
                                        await channel.send(
                                            f"📉🟢 **RELOAD: {p.symbol}** {dip_pct:.1f}% dip from ${intraday_high:.2f}\n"
                                            f"Buy {reload_qty} @ ${buy_price} → scalp at +2%")
                        except:
                            pass

            # ── PYRAMIDING: add to winning positions that keep running ──
            if _is_trading_hours() and pct >= 3.0 and avail == 0:
                pyramid_key = f"_pyramid_t_{p.symbol}"
                last_pyramid = _prev_prices.get(pyramid_key, 0)
                if time.time() - last_pyramid > 900:  # 15min between pyramids (was 30)
                    try:
                        acct_data = gateway.get_account()
                        cash = float(acct_data.get('cash', 0))
                        equity = float(acct_data.get('equity', 100000))
                        if cash > 3000 and (cash / equity) > 0.30:  # Must have >30% cash
                            add_qty = max(1, int(equity * 0.015 / p.current_price))  # 1.5% of portfolio
                            buy_price = round(p.current_price * 1.001, 2)
                            result = _smart_buy(
                                p.symbol, add_qty, buy_price,
                                reason=f"Pyramid: +{pct:.1f}% winner, adding {add_qty} shares",
                                source="60s_pyramid", vix=_cached_vix)
                            if result and result.state.value != 'REJECTED':
                                _prev_prices[pyramid_key] = time.time()
                                if pg: pg.record_pyramid(p.symbol)
                                if pg: pg.record_buy(p.symbol, buy_price)
                                _log_trade("PYRAMID BUY", p.symbol, add_qty, buy_price,
                                           f"Winner +{pct:.1f}% — adding more to ride", "60s Pyramid")
                                if channel:
                                    await channel.send(
                                        f"📈🟢 **PYRAMID: {p.symbol}** +{pct:.1f}% winner\n"
                                        f"Adding {add_qty} shares @ ${buy_price} — riding the momentum")
                    except Exception as e:
                        log.debug(f"Pyramid {p.symbol}: {e}")

            # ── DROP ALERT: >2% sudden drop ──
            if prev > 0:
                chg = (p.current_price - prev) / prev * 100
                if chg <= -2.0 and channel and not _prev_prices.get(f"_drop_{p.symbol}_{_cycle_count//60}"):
                    _prev_prices[f"_drop_{p.symbol}_{_cycle_count//60}"] = True
                    await channel.send(f"🚨 **[60s] DROP ALERT: {p.symbol}** ${prev:.2f} → ${p.current_price:.2f} ({chg:+.1f}%)\nP&L: ${p.unrealized_pl:+.2f}\nIron Law 1: HOLD")
                    _tg(f"🚨 DROP: {p.symbol} {chg:+.1f}%\n${prev:.2f}→${p.current_price:.2f}\nP&L: ${p.unrealized_pl:+.2f}\nHOLD (Iron Law 1)")

            # ── IRON LAW 1: -$500 alert ──
            if p.unrealized_pl <= -500 and not _prev_prices.get(f"_loss500_{p.symbol}"):
                _prev_prices[f"_loss500_{p.symbol}"] = True
                if channel:
                    await channel.send(f"⛔ **[60s] IRON LAW 1: {p.symbol}** Loss ${p.unrealized_pl:.2f}\nHOLD — never sell at loss")
                _tg(f"⛔ IRON LAW 1: {p.symbol}\nLoss: ${p.unrealized_pl:.2f}\nACTION: HOLD — NEVER sell at loss")

            _prev_prices[p.symbol] = p.current_price

        # ── AUTO-BUY DIPS (Akash Method) — no limits, Beast mode ──
        if _is_trading_hours() and _cycle_count % 5 == 0:
            try:
                from alpaca.data.historical import StockHistoricalDataClient
                from alpaca.data.requests import StockSnapshotRequest
                dc = StockHistoricalDataClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'))
                watch = [s for s in DIP_BUY_WATCHLIST if s not in held_symbols][:8]
                if watch:
                    snaps = dc.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=watch, feed='iex'))
                    for sym, snap in snaps.items():
                        try:
                            price = float(snap.latest_trade.price)
                            prev_close = float(snap.previous_daily_bar.close)
                            day_change = (price - prev_close) / prev_close * 100
                            # Akash Method: buy if >5% daily drop
                            if day_change <= -5.0 and not _prev_prices.get(f"_dipbuy_{sym}"):
                                acct = gateway.get_account()
                                equity = float(acct.get('equity', 100000))
                                qty = max(1, int(equity * 0.03 / price))
                                buy_price = round(price * 0.998, 2)
                                _smart_buy(sym, qty, buy_price,
                                                  reason=f"Akash Method: {day_change:+.1f}% dip",
                                                  day_change_pct=day_change,
                                                  source="60s_dipbuy", vix=_cached_vix)
                                _prev_prices[f"_dipbuy_{sym}"] = True
                                _log_trade("LIMIT BUY (Akash Method)", sym, qty, buy_price,
                                           f"{day_change:+.1f}% daily drop. Oversold dip buy.", "60s Monitor")
                                if channel:
                                    await channel.send(
                                        f"📉 **[60s] AKASH DIP BUY: {sym}** {day_change:+.1f}%\n"
                                        f"Buy {qty} @ ${buy_price} | Exit: +2% (${buy_price * 1.02:.2f})")
                        except:
                            pass
            except Exception as e:
                log.debug(f"Dip scan: {e}")

        # ── PHASE 0: Past Winners scan (Rule #21) — no limits ──
        if _is_trading_hours() and _cycle_count % 10 == 0:
            try:
                from alpaca.data.historical import StockHistoricalDataClient
                from alpaca.data.requests import StockSnapshotRequest
                dc = StockHistoricalDataClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'))
                pw_watch = [s for s in PAST_WINNERS if s not in held_symbols][:10]
                if pw_watch:
                    snaps = dc.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=pw_watch, feed='iex'))
                    for sym, snap in snaps.items():
                        try:
                            price = float(snap.latest_trade.price)
                            prev_close = float(snap.previous_daily_bar.close)
                            day_change = (price - prev_close) / prev_close * 100
                            # Past winner running >3% = opportunity
                            if day_change >= 3.0 and not _prev_prices.get(f"_pw_{sym}"):
                                _prev_prices[f"_pw_{sym}"] = True
                                if channel:
                                    await channel.send(
                                        f"🏆 **[PHASE 0] PAST WINNER ALERT: {sym}** +{day_change:.1f}%\n"
                                        f"${price:.2f} (prev ${prev_close:.2f}) — Past winner running!\n"
                                        f"Check catalyst before buying. Use `!scan {sym}` for deep analysis.")
                                log.info(f"  🏆 Phase 0: past winner {sym} +{day_change:.1f}%")
                                _pg_log("ALERT", symbol=sym, reason=f"Past winner running +{day_change:.1f}%", source="Phase0")
                        except:
                            pass
            except Exception as e:
                log.debug(f"Phase 0 scan: {e}")

        # ── PostgreSQL snapshots (every cycle) ──
        pg = _get_pg()
        if pg:
            try:
                acct = gateway.get_account()
                eq = float(acct.get('equity', 0))
                cs = float(acct.get('cash', 0))
                lmv = float(acct.get('long_market_value', 0))
                heat = (lmv / eq * 100) if eq > 0 else 0
                pg.snapshot_equity(eq, cs, total_pl, len(positions), heat)
                open_ords = gateway.get_open_orders() if _cycle_count % 3 == 0 else []
                trail_syms = {o.get('symbol') for o in open_ords if 'trailing' in str(o.get('type', '')).lower()}
                pg.snapshot_positions(positions, trailing_stops=trail_syms)
            except Exception as e:
                log.debug(f"PG snapshot: {e}")

        # Summary every 5 cycles + Telegram
        if _cycle_count % 5 == 0 and channel:
            lines = [f"📊 **[60s MONITOR #{_cycle_count}]** P&L: ${total_pl:+.2f} | G:{greens} R:{len(positions)-greens}"]
            tg_lines = [f"📊 60s Monitor #{_cycle_count}\nP&L: ${total_pl:+.2f} | G:{greens} R:{len(positions)-greens}"]
            for p in sorted(positions, key=lambda x: x.unrealized_pl, reverse=True)[:6]:
                icon = "🟢" if p.unrealized_pl >= 0 else "🔴"
                lines.append(f"{icon} {p.symbol} ${p.unrealized_pl:+.2f} ({_pct(p):+.1f}%)")
                tg_lines.append(f"{icon} {p.symbol} ${p.unrealized_pl:+.2f} ({_pct(p):+.1f}%)")
            # Show recent trades if any
            if _trade_log:
                lines.append(f"\n📋 **Recent Trades ({len(_trade_log)}):**")
                tg_lines.append(f"\n📋 Trades:")
                for t in _trade_log[-3:]:
                    lines.append(f"  {t['action']} {t['symbol']} x{t['qty']} @ ${t['price']} [{t['scan_type']}]")
                    tg_lines.append(f"  {t['action']} {t['symbol']} x{t['qty']} @ ${t['price']}")
            await channel.send("\n".join(lines))
            _tg("\n".join(tg_lines))
        log.info(f"[Monitor #{_cycle_count}] {len(positions)} pos | P&L: ${total_pl:+.2f}")
        _pg_log("MONITOR", reason=f"#{_cycle_count} {len(positions)} pos P&L=${total_pl:+.2f}", source="60s")
    except Exception as e:
        log.error(f"Position monitor error: {e}")


@tasks.loop(minutes=5)
async def full_scan():
    """Every 5 min: MANDATORY full scan — TV + ALL sentiment + confidence engine + AI.
    NO EXCEPTIONS. Every source runs. Confidence is generated. AI analyzes AFTER data.
    DEEP LOGGED: Every scan saved as a complete snapshot for learning."""
    global _last_full_scan
    try:
        channel = bot.get_channel(SCAN_CHANNEL_ID)
        if not channel:
            return

        import asyncio, uuid
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
        scan_start = time.time()
        scan_id = f"5min_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        pg = _get_pg()

        # Kill switch check
        if pg and pg.is_kill_switch_on():
            log.info("🛑 KILL SWITCH — skipping full scan")
            return

        positions = gateway.get_positions()
        acct = gateway.get_account()
        equity = float(acct.get('equity', 100000))
        cash = float(acct.get('cash', 0))
        total_pl = sum(p.unrealized_pl for p in positions)
        greens = sum(1 for p in positions if p.unrealized_pl >= 0)
        held = [p.symbol for p in positions]
        heat_pct = round((1 - cash / equity) * 100, 1) if equity > 0 else 0

        # SCAN COVERAGE FIX: Add top watchlist movers (not just held positions)
        # This catches opportunities we DON'T own yet
        scan_symbols = list(held)  # Start with held
        if _is_trading_hours() and pg:
            try:
                from alpaca.data.historical import StockHistoricalDataClient
                from alpaca.data.requests import StockSnapshotRequest as SSR2
                dc2 = StockHistoricalDataClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'))
                # Get top past winners + recent watchlist additions not already held
                watch_check = [s for s in PAST_WINNERS[:15] if s not in held]
                if watch_check:
                    snaps2 = dc2.get_stock_snapshot(SSR2(symbol_or_symbols=watch_check[:10], feed='iex'))
                    for sym, s in snaps2.items():
                        try:
                            price = float(s.latest_trade.price)
                            prev = float(s.previous_daily_bar.close)
                            pct = (price - prev) / prev * 100
                            if abs(pct) > 1.5 and sym not in scan_symbols:
                                scan_symbols.append(sym)
                        except:
                            pass
            except:
                pass
        log.info(f"  Scan coverage: {len(held)} held + {len(scan_symbols)-len(held)} watchlist movers = {len(scan_symbols)} total")

        # Track for snapshot
        scan_decisions = []

        # ── REGIME ──
        spy_change = 0
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockSnapshotRequest
            dc = StockHistoricalDataClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'))
            snap = dc.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols='SPY', feed='iex'))
            if 'SPY' in snap:
                s = snap['SPY']
                spy_change = (float(s.daily_bar.close) - float(s.previous_daily_bar.close)) / float(s.previous_daily_bar.close)
        except:
            pass
        regime = regime_det.detect(spy_change)

        # ══════════════════════════════════════════════════
        # MANDATORY PIPELINE — NO EXCEPTIONS
        # Step 1: TV indicators (ALL strategies)
        # Step 2: ALL sentiment (Yahoo + Reddit + Google News + Trump + Analyst)
        # Step 3: Confidence Engine (11 strategies scored)
        # Step 4: AI analysis (AFTER data, not before)
        # PERFORMANCE: Every step timed per-stock for optimization
        # ══════════════════════════════════════════════════
        perf = {}  # {step: {total_ms, per_stock: {sym: ms}}}

        # ── STEP 1: TV INDICATORS (MANDATORY) ──
        tv_data = {}
        def _read_all_tv(syms):
            """Read TV indicators for all stocks. Sequential (one Chrome instance)
            but smart: skip 5-min cached stocks, prioritize held positions."""
            d = {}
            timings = {}
            skipped = 0
            for sym in syms:
                # Check 5-min cache — skip if fresh
                cached = _tv_cache.get(sym)
                _tv_ttl = int(pg.get_config('tv_cache_seconds', 300)) if pg else 300
                if cached and time.time() - cached[0] < _tv_ttl:
                    d[sym] = cached[1]
                    timings[sym] = 0
                    skipped += 1
                    continue
                t0 = time.time()
                ind = _get_tv_indicators(sym)
                elapsed = int((time.time() - t0) * 1000)
                timings[sym] = elapsed
                if ind:
                    d[sym] = ind
                    log.info(f"  TV {sym}: RSI={ind.get('rsi','?'):.0f} MACD={ind.get('macd_hist','?')} VWAP={'above' if ind.get('vwap_above') else 'BELOW'} [{elapsed}ms]")
                else:
                    log.info(f"  TV {sym}: NO DATA [{elapsed}ms]")
            if skipped:
                log.info(f"  TV: {skipped} cached (skipped), {len(syms)-skipped} fresh reads")
            return d, timings
        t_step = time.time()
        # Prioritize: held first (need real-time), then watchlist movers
        tv_priority = held[:12] + [s for s in scan_symbols if s not in held][:4]
        tv_data, tv_timings = await asyncio.to_thread(_read_all_tv, tv_priority)
        tv_total = int((time.time() - t_step) * 1000)
        perf['tv'] = {'total_ms': tv_total, 'stocks': len(scan_symbols[:16]), 'loaded': len(tv_data), 'per_stock': tv_timings}
        log.info(f"  📊 TV: {len(tv_data)}/{len(held)} stocks in {tv_total}ms (avg {tv_total//max(len(scan_symbols[:16]),1)}ms/stock)")

        # ── STEP 2: ALL SENTIMENT (MANDATORY — 5 sources) ──
        sentiments = {}
        trump_score = 0
        trump_headlines = []
        def _read_all_sentiment(syms):
            from sentiment_analyst import SentimentAnalyst
            sa = SentimentAnalyst()
            results = {}
            timings = {}
            for sym in syms:
                t0 = time.time()
                try:
                    results[sym] = sa.analyze(sym)
                except Exception as e:
                    log.warning(f"  Sentiment {sym} failed: {e}")
                timings[sym] = int((time.time() - t0) * 1000)
            # Trump/tariff/geopolitical
            t0 = time.time()
            try:
                t_score, t_headlines = sa.get_trump_sentiment()
                results['_trump'] = {'score': t_score, 'headlines': t_headlines}
            except Exception as e:
                log.warning(f"  Trump sentiment failed: {e}")
            timings['_trump'] = int((time.time() - t0) * 1000)
            # Market-wide
            t0 = time.time()
            try:
                results['_market'] = sa.analyze_market()
            except:
                pass
            timings['_market'] = int((time.time() - t0) * 1000)
            return results, timings
        t_step = time.time()
        sent_raw, sent_timings = await asyncio.to_thread(_read_all_sentiment, scan_symbols[:16])
        sent_total = int((time.time() - t_step) * 1000)
        trump_info = sent_raw.pop('_trump', {})
        trump_score = trump_info.get('score', 0)
        trump_headlines = trump_info.get('headlines', [])
        market_sent = sent_raw.pop('_market', None)
        sentiments = sent_raw
        perf['sentiment'] = {'total_ms': sent_total, 'stocks': len(sentiments), 'per_stock': sent_timings}
        log.info(f"  📊 Sentiment: {len(sentiments)} stocks in {sent_total}ms | Trump: {trump_score:+d} [{sent_timings.get('_trump',0)}ms]")

        # ── STEP 3: CONFIDENCE ENGINE (11 strategies, MANDATORY) ──
        confidence_results = {}
        def _run_confidence(syms, tv_d, sent_d, reg):
            from engine.confidence_engine import ConfidenceEngine
            from models import TechnicalSignals
            ce = ConfidenceEngine()
            results = {}
            timings = {}
            for sym in syms:
                t0 = time.time()
                tv = tv_d.get(sym, {})
                sent = sent_d.get(sym)
                pos = next((p for p in positions if p.symbol == sym), None)
                price = pos.current_price if pos else 0
                vwap_val = 0.0
                if _is_market_hours() and tv.get('vwap_above') is not None:
                    vwap_val = 1.0 if tv.get('vwap_above') else -1.0
                tech = TechnicalSignals(
                    symbol=sym,
                    rsi=tv.get('rsi', 50),
                    macd_histogram=tv.get('macd_hist', 0),
                    price_vs_vwap=vwap_val,
                    volume_ratio=tv.get('volume_ratio', 1.0),
                    ema_9=tv.get('ema_9', 0),
                    ema_21=tv.get('ema_21', 0),
                    confluence_score=tv.get('confluence', 5),
                )
                if not sent:
                    from models import SentimentScore as SS
                    sent = SS(symbol=sym)
                try:
                    cr = ce.score(sym, tech, sent, reg, current_price=price)
                    results[sym] = cr
                except Exception as e:
                    log.warning(f"  Confidence {sym}: {e}")
                timings[sym] = int((time.time() - t0) * 1000)
            return results, timings
        t_step = time.time()
        confidence_results, conf_timings = await asyncio.to_thread(_run_confidence, scan_symbols[:16], tv_data, sentiments, regime)
        conf_total = int((time.time() - t_step) * 1000)
        perf['confidence'] = {'total_ms': conf_total, 'stocks': len(confidence_results), 'per_stock': conf_timings}
        log.info(f"  📊 Confidence: {len(confidence_results)} scored in {conf_total}ms")

        # ── OPEN ORDERS ──
        t_step = time.time()
        open_orders = await asyncio.to_thread(gateway.get_open_orders)
        perf['orders'] = {'total_ms': int((time.time() - t_step) * 1000)}

        # ── STEP 3.5: LEARNING CONTEXT (from DB — cached, fast) ──
        t_step = time.time()
        learning_digest = ""
        if pg:
            try:
                learning_digest = pg.get_learning_digest_for_ai(scan_symbols[:16])
            except:
                pass
        perf['learning'] = {'total_ms': int((time.time() - t_step) * 1000), 'digest_len': len(learning_digest)}

        # ── STEP 4: AI ANALYSIS (AFTER all data, WITH learning context) ──
        ai_verdicts = {}

        t_step = time.time()
        if brain and brain.is_available:
            def _run_ai_batch(pos_list, sent_d, tv_d, conf_d, regime_val, t_score):
                # Build data for ALL stocks at once
                batch_data = {}
                for pos in pos_list:
                    sym = pos.symbol
                    sent = sent_d.get(sym)
                    tv = tv_d.get(sym, {})
                    cr = conf_d.get(sym)
                    conf_pct = int(cr.overall_confidence * 100) if cr else 50
                    best_strat = cr.best_strategy.value if cr and cr.best_strategy else 'none'
                    signal = cr.signal.value if cr else 'no_trade'
                    stock_learning = ""
                    if pg:
                        try:
                            ctx = pg.get_learning_context_for_stock(sym)
                            trades = ctx.get('trade_history', [])
                            if trades:
                                wins = sum(1 for t in trades if t.get('was_profitable'))
                                total = sum(1 for t in trades if t.get('was_profitable') is not None)
                                lessons = [t.get('lesson_learned','') for t in trades if t.get('lesson_learned')]
                                stock_learning = f"HISTORY: {wins}/{total} wins. "
                                if lessons:
                                    stock_learning += f"Lessons: {'; '.join(l[:60] for l in lessons[:3])}"
                        except:
                            pass
                    batch_data[sym] = {
                        'price': pos.current_price, 'entry': pos.avg_entry,
                        'pnl': pos.unrealized_pl, 'qty': pos.qty,
                        'regime': regime_val,
                        'sentiment': sent.total_score if sent else 0,
                        'rsi': tv.get('rsi', 50),
                        'macd_hist': tv.get('macd_hist', 0),
                        'vwap_above': tv.get('vwap_above', False),
                        'volume_ratio': tv.get('volume_ratio', 1.0),
                        'confluence': tv.get('confluence', 5),
                        'ema_9': tv.get('ema_9', 0), 'ema_21': tv.get('ema_21', 0),
                        'trump_score': t_score,
                        'confidence_engine': conf_pct,
                        'best_strategy': best_strat, 'signal': signal,
                        'unrealized_pl': pos.unrealized_pl,
                        'learning_context': stock_learning,
                    }
                # ONE API call for all stocks
                t0 = time.time()
                results = brain.analyze_batch(batch_data)
                elapsed = int((time.time() - t0) * 1000)
                return results, {'_batch': elapsed}

            ai_verdicts, ai_timings = await asyncio.to_thread(
                _run_ai_batch, positions[:16], sentiments, tv_data,
                confidence_results, regime.value, trump_score
            )
        else:
            ai_timings = {}
        ai_total = int((time.time() - t_step) * 1000)
        perf['ai'] = {'total_ms': ai_total, 'stocks': len(ai_verdicts), 'per_stock': ai_timings,
                       'model': 'GPT-4o_BATCH', 'learning_injected': len(learning_digest) > 0}
        log.info(f"  📊 AI BATCH: {len(ai_verdicts)} stocks in {ai_total}ms (1 API call)")

        # ══════════════════════════════════════════════════
        # AUTO-EXECUTE: GPT-4o high-confidence verdicts (≥75%)
        # Same logic as Claude 30-min but runs every 5 min
        # ══════════════════════════════════════════════════
        GPT_AUTO_THRESHOLD = 75
        if _is_trading_hours() and ai_verdicts:
            active_scalps = sum(1 for p in positions if 0 < _pct(p) < 2.0)
            held_syms = {p.symbol for p in positions}

            for sym, v in ai_verdicts.items():
                action = v.get('action', 'HOLD')
                conf = v.get('confidence', 0)
                reason = v.get('reasoning', '')[:100]

                if conf < GPT_AUTO_THRESHOLD or action == 'HOLD':
                    continue

                try:
                    if action == 'BUY' and sym not in held_syms:
                        pos = next((p for p in positions if p.symbol == sym), None)
                        price = pos.current_price if pos else 0
                        if price <= 0:
                            continue
                        qty = max(1, int(equity * 0.03 / price))
                        buy_price = round(price * 1.002, 2)
                        sent = sentiments.get(sym)
                        sent_score = sent.total_score if sent else 0
                        result = _smart_buy(
                            sym, qty, buy_price,
                            reason=f"GPT-4o BUY {conf}%: {reason}",
                            day_change_pct=0, sentiment_score=sent_score,
                            source="5min_GPT", vix=_cached_vix, confidence=conf,
                            ai_verdict_data=v,
                            sentiment_data={'total': sent_score,
                                            'yahoo': getattr(sent, 'yahoo_score', 0),
                                            'reddit': getattr(sent, 'reddit_score', 0),
                                            'analyst': getattr(sent, 'analyst_score', 0)} if sent else {'total': sent_score}
                        )
                        executed = result and result.state.value != 'REJECTED'
                        scan_decisions.append({'symbol': sym, 'action': 'BUY', 'confidence': conf,
                                               'executed': executed, 'reason': reason, 'source': 'GPT-4o'})
                        if executed:
                            _log_trade(f"AI BUY (GPT-4o {conf}%)", sym, qty, buy_price, reason, "5min GPT")
                            # Deep trade log with full context
                            if pg:
                                pg.log_trade_deep(sym, 'buy', qty, buy_price, scan_id=scan_id,
                                    strategy='5min_GPT', source='full_scan', trigger=f'GPT-4o {conf}%',
                                    tv_at_trade=tv_data.get(sym, {}),
                                    sentiment_at_trade={'total': sent_score, 'yahoo': getattr(sent, 'yahoo_score', 0),
                                                        'reddit': getattr(sent, 'reddit_score', 0)} if sent else {},
                                    ai_verdict_at_trade=v, confidence=conf,
                                    ai_reasoning=v.get('reasoning', '')[:500],
                                    regime=regime.value, vix=_cached_vix, spy_change=spy_change,
                                    heat_pct=heat_pct, position_count=len(positions),
                                    order_result=result.state.value if result else 'NONE',
                                    order_id=str(result.id) if result and hasattr(result, 'id') else None)
                            if channel:
                                await channel.send(
                                    f"🤖🟢 **GPT-4o AUTO-BUY: {sym}** ({conf}%)\n"
                                    f"Buy {qty} @ ${buy_price} | {reason}")

                    elif action == 'SELL' and sym in held_syms:
                        pos = next((p for p in positions if p.symbol == sym), None)
                        if pos and pos.qty_available and pos.qty_available > 0:
                            sell_qty = pos.qty_available
                            sell_price = round(pos.current_price * 0.999, 2)
                            gateway.place_sell(sym, sell_qty, sell_price,
                                              reason=f"GPT-4o SELL {conf}%: {reason}",
                                              entry_price=pos.avg_entry)
                            scan_decisions.append({'symbol': sym, 'action': 'SELL', 'confidence': conf,
                                                   'executed': True, 'reason': reason, 'source': 'GPT-4o'})
                            _log_trade(f"AI SELL (GPT-4o {conf}%)", sym, sell_qty, sell_price, reason, "5min GPT")
                            if pg:
                                pg.log_trade_deep(sym, 'sell', sell_qty, sell_price, scan_id=scan_id,
                                    strategy='5min_GPT', source='full_scan', trigger=f'GPT-4o SELL {conf}%',
                                    tv_at_trade=tv_data.get(sym, {}), ai_verdict_at_trade=v,
                                    confidence=conf, ai_reasoning=v.get('reasoning', '')[:500],
                                    regime=regime.value, vix=_cached_vix, spy_change=spy_change,
                                    heat_pct=heat_pct, position_count=len(positions))
                                pg.record_sell(sym, sell_price)
                            if channel:
                                await channel.send(
                                    f"🤖🔴 **GPT-4o AUTO-SELL: {sym}** ({conf}%)\n"
                                    f"Sell {sell_qty} @ ${sell_price} | {reason}")
                except Exception as e:
                    log.warning(f"GPT-4o auto-execute {sym}: {e}")

        # ── Save AI verdicts to PostgreSQL ──
        pg = _get_pg()
        if pg:
            for sym, v in ai_verdicts.items():
                try:
                    pg.save_ai_verdict(sym, v.get('action','HOLD'), v.get('confidence',0),
                                      v.get('reasoning',''), v.get('ai_source','GPT-4o'), '5min')
                except:
                    pass

        # ── MARKET CONTEXT ──
        market_status = "MARKET" if _is_market_hours() else ("EXTENDED" if _is_extended_hours() else "CLOSED")

        # ══════════════════════════════════════════════════
        # COMPACT DISCORD REPORT (2 embeds, not 8+)
        # Clean, scannable, professional trader format
        # ══════════════════════════════════════════════════

        # ── EMBED 1: Dashboard + Position Table ──
        embed1 = discord.Embed(
            title=f"🦍 BEAST SCAN — {now.strftime('%I:%M %p ET')} [{market_status}]",
            color=0x00ff00 if total_pl >= 0 else 0xff4444
        )
        embed1.add_field(
            name="💰 Portfolio",
            value=(
                f"**${equity:,.0f}** | P&L: **${total_pl:+.2f}** | "
                f"Regime: {regime.value.upper()} | SPY: {spy_change:+.2%}\n"
                f"{len(positions)} pos (G:{greens} R:{len(positions)-greens}) | "
                f"Orders: {len(open_orders)} | Trump: {trump_score:+d}"
            ), inline=False
        )

        pos_lines = []
        for p in sorted(positions, key=lambda x: x.unrealized_pl, reverse=True):
            pct = _pct(p)
            tv = tv_data.get(p.symbol, {})
            sent = sentiments.get(p.symbol)
            ai_v = ai_verdicts.get(p.symbol, {})
            cr = confidence_results.get(p.symbol)
            icon = "🟢" if pct >= 0 else "🔴"
            rsi_s = f"RSI:{tv.get('rsi',0):.0f}" if tv.get('rsi') else ""
            vwap_s = "↑V" if tv.get('vwap_above') else "↓V" if tv else ""
            sent_s = f"S:{sent.total_score:+d}" if sent else ""
            conf_s = f"C:{cr.overall_confidence:.0%}" if cr else ""
            ai_s = ai_v.get('action', '') if ai_v else ""
            verdict = ai_s or ("RUNNER" if pct >= 5 else "SCALP" if pct >= 2 else "HOLD")
            pos_lines.append(
                f"{icon} **{p.symbol}** ${p.unrealized_pl:+.0f} ({pct:+.1f}%) "
                f"{rsi_s} {vwap_s} {sent_s} {conf_s} → **{verdict}**"
            )
        embed1.add_field(name="📊 Positions", value="\n".join(pos_lines[:10]) or "None", inline=False)
        embed1.set_footer(text=f"TV:{len(tv_data)} Sent:{len(sentiments)} Conf:{len(confidence_results)} AI:{len(ai_verdicts)}")
        await channel.send(embed=embed1)

        # ── EMBED 2: Signals + News (only if actionable) ──
        has_signals = False
        embed2 = discord.Embed(title="📡 Signals & Intel", color=0x2b2d31)

        ai_actions = [(sym, v) for sym, v in ai_verdicts.items() if v.get('action', 'HOLD') != 'HOLD']
        if ai_actions:
            ai_text = "\n".join(
                f"{'🟢' if v.get('action')=='BUY' else '🔴'} **{sym}** {v['action']} ({v.get('confidence',0)}%) — {v.get('reasoning','')[:80]}"
                for sym, v in ai_actions[:6]
            )
            embed2.add_field(name="🧠 AI Recommendations", value=ai_text, inline=False)
            has_signals = True

        sent_lines = [
            f"{'📈' if s.total_score>0 else '📉'} {sym}: Y:{s.yahoo_score:+d} R:{s.reddit_score:+d} A:{s.analyst_score:+d} = **{s.total_score:+d}**"
            for sym in [p.symbol for p in positions][:8
            ] if (s := sentiments.get(sym)) and s.total_score != 0
        ]
        if sent_lines:
            embed2.add_field(name="📰 Sentiment", value="\n".join(sent_lines), inline=False)
            has_signals = True

        if trump_score != 0 and trump_headlines:
            embed2.add_field(name="🏛️ Geo", value=f"**{trump_score:+d}** — " + " | ".join(h[:50] for h in trump_headlines[:2]), inline=False)
            has_signals = True

        if _trade_log:
            recent = _trade_log[-3:]
            embed2.add_field(name=f"📋 Trades ({len(_trade_log)})", value="\n".join(
                f"• {t['action']} {t['symbol']} x{t['qty']} @ ${t['price']} ({t['time']})" for t in recent
            ), inline=False)
            has_signals = True

        if has_signals:
            await channel.send(embed=embed2)

        # ── TELEGRAM SUMMARY (condensed version of full scan) ──
        tg_report = f"🦍 BEAST SCAN [{market_status}] {now.strftime('%I:%M %p')}\n"
        tg_report += f"━━━━━━━━━━━━━━━━━━━━━━\n"
        tg_report += f"💰 ${equity:,.0f} | P&L: ${total_pl:+.2f}\n"
        tg_report += f"📈 Regime: {regime.value} | SPY: {spy_change:+.2%}\n"
        tg_report += f"🏛️ Trump: {trump_score:+d}/5\n\n"
        for p in sorted(positions, key=lambda x: x.unrealized_pl, reverse=True):
            pct = _pct(p)
            icon = "🟢" if pct >= 0 else "🔴"
            ai_v = ai_verdicts.get(p.symbol, {})
            cr = confidence_results.get(p.symbol)
            tg_report += f"{icon} {p.symbol} {pct:+.1f}% ${p.unrealized_pl:+.0f}"
            if cr: tg_report += f" C:{cr.overall_confidence:.0%}"
            if ai_v: tg_report += f" AI:{ai_v.get('action','?')}"
            tg_report += "\n"
        if trump_headlines:
            tg_report += f"\n📰 Headlines:\n"
            for h in trump_headlines[:3]:
                tg_report += f"• {h[:60]}\n"
        if _trade_log:
            tg_report += f"\n📋 Trades ({len(_trade_log)}):\n"
            for t in _trade_log[-5:]:
                tg_report += f"  {t['action']} {t['symbol']} x{t['qty']} @ ${t['price']}\n"
        _tg(tg_report)

        _last_full_scan = time.time()
        scan_duration = int((time.time() - scan_start) * 1000)
        perf['total_ms'] = scan_duration

        # ── PERFORMANCE SUMMARY LOG ──
        slowest_tv = max(tv_timings.items(), key=lambda x: x[1]) if tv_timings else ('none', 0)
        slowest_sent = max(sent_timings.items(), key=lambda x: x[1]) if sent_timings else ('none', 0)
        slowest_ai = max(ai_timings.items(), key=lambda x: x[1]) if ai_timings else ('none', 0)
        log.info(f"  ⏱️ SCAN PERF: Total={scan_duration}ms | TV={perf['tv']['total_ms']}ms Sent={perf['sentiment']['total_ms']}ms "
                 f"Conf={perf['confidence']['total_ms']}ms AI={perf['ai']['total_ms']}ms Learn={perf['learning']['total_ms']}ms")
        log.info(f"  ⏱️ SLOWEST: TV={slowest_tv[0]}({slowest_tv[1]}ms) Sent={slowest_sent[0]}({slowest_sent[1]}ms) "
                 f"AI={slowest_ai[0]}({slowest_ai[1]}ms)")

        _pg_log("SCAN", reason=f"5min scan TV:{len(tv_data)} Sent:{len(sentiments)} AI:{len(ai_verdicts)} [{scan_duration}ms]",
                source="5min", data={"perf": perf, "tv_count": len(tv_data),
                                      "sentiment_count": len(sentiments), "ai_count": len(ai_verdicts)})

        # ── DEEP SCAN SNAPSHOT: Everything in one row for learning ──
        pg = _get_pg()
        if pg:
            try:
                # Build serializable position data
                pos_data = [{'symbol': p.symbol, 'qty': p.qty, 'entry': float(p.avg_entry),
                             'price': float(p.current_price), 'pnl': float(p.unrealized_pl),
                             'pct': round(_pct(p), 2)} for p in positions]
                # Build serializable confidence data
                conf_data = {}
                for sym, cr in confidence_results.items():
                    conf_data[sym] = {'confidence': round(cr.overall_confidence * 100, 1) if cr else 0,
                                      'strategy': cr.best_strategy.value if cr and cr.best_strategy else 'none',
                                      'signal': cr.signal.value if cr else 'none'}
                # Build serializable sentiment data
                sent_data = {}
                for sym, s in sentiments.items():
                    if hasattr(s, 'total_score'):
                        sent_data[sym] = {'total': s.total_score, 'yahoo': s.yahoo_score,
                                          'reddit': s.reddit_score, 'analyst': s.analyst_score}
                    else:
                        sent_data[sym] = s if isinstance(s, dict) else {}

                pg.log_scan_snapshot(
                    scan_id=scan_id, scan_type='5min', duration_ms=scan_duration,
                    regime=regime.value, spy_change=spy_change, vix=_cached_vix,
                    equity=equity, total_pl=total_pl,
                    positions=pos_data, tv_data=tv_data, sentiment_data=sent_data,
                    confidence_data=conf_data, ai_verdicts=ai_verdicts,
                    decisions=scan_decisions,
                    market_context={'trump_score': trump_score, 'trump_headlines': trump_headlines[:3],
                                    'heat_pct': heat_pct, 'cash': cash, 'market_status': market_status,
                                    'performance': perf}
                )
                pg.set_state('last_scan_time', time.strftime('%Y-%m-%dT%H:%M:%SZ'), 'runtime')
                pg.set_state('last_scan_perf', perf, 'runtime')

                pg.log_scan('5min', regime=regime.value, spy_change=spy_change,
                           tv_count=len(tv_data), sentiment_count=len(sentiments),
                           ai_count=len(ai_verdicts), trump_score=trump_score,
                           buys_placed=sum(1 for d in scan_decisions if d.get('action') == 'BUY'),
                           sells_placed=sum(1 for d in scan_decisions if d.get('action') == 'SELL'))
                pg.auto_purge()
            except Exception as e:
                log.debug(f"PG scan snapshot: {e}")

        log.info(f"Full scan #{scan_id} at {now.strftime('%H:%M')} [TV:{len(tv_data)} AI:{len(ai_verdicts)} {scan_duration}ms]")

    except Exception as e:
        log.error(f"Full scan error: {e}\n{traceback.format_exc()}")


@tasks.loop(minutes=10)
async def decision_report():
    """Every 10 min: trading decisions with AI, strategy breakdown, risk analysis."""
    try:
        channel = bot.get_channel(SCAN_CHANNEL_ID)
        if not channel:
            return

        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
        # 24/7 — decision report always runs (shows P&L + risk even off-hours)

        positions = gateway.get_positions()
        acct = gateway.get_account()
        equity = float(acct.get('equity', 0))
        cash = float(acct.get('cash', 0))
        total_pl = sum(p.unrealized_pl for p in positions)
        greens = sum(1 for p in positions if p.unrealized_pl >= 0)
        market_val = sum(p.market_value for p in positions) if positions else 0

        # Get open orders for protection analysis
        open_orders = await asyncio.to_thread(gateway.get_open_orders)
        trail_stops = [o for o in open_orders if 'trail' in str(o.get('type', '')).lower()]
        limit_sells = [o for o in open_orders if o.get('side') == 'sell' and 'trail' not in str(o.get('type', '')).lower()]
        limit_buys = [o for o in open_orders if o.get('side') == 'buy']

        # Sector concentration analysis
        sectors = {}
        SECTOR_MAP = {
            'AMD': 'Chips', 'NVDA': 'Chips', 'INTC': 'Chips', 'MU': 'Chips', 'TSM': 'Chips',
            'GOOGL': 'Big Tech', 'META': 'Big Tech', 'AMZN': 'Big Tech', 'PLTR': 'AI/Defense',
            'CRM': 'Cloud', 'LMT': 'Defense', 'DVN': 'Energy', 'NOK': 'Telecom', 'OXY': 'Energy',
        }
        for p in positions:
            sec = SECTOR_MAP.get(p.symbol, 'Other')
            sectors[sec] = sectors.get(sec, 0) + (p.market_value if hasattr(p, 'market_value') else p.current_price * p.qty)

        # Build the report
        embed = discord.Embed(
            title=f"📋 DECISION REPORT — {now.strftime('%I:%M %p ET')}",
            color=0x00ff00 if total_pl >= 0 else 0xff4444
        )

        # Portfolio summary
        invested_pct = (market_val / equity * 100) if equity > 0 else 0
        embed.add_field(
            name="💰 Portfolio",
            value=(
                f"Equity: **${equity:,.0f}** | Cash: ${cash:,.0f}\n"
                f"Invested: ${market_val:,.0f} ({invested_pct:.0f}%)\n"
                f"P&L: **${total_pl:+.2f}** | {len(positions)} pos (G:{greens} R:{len(positions)-greens})"
            ), inline=False
        )

        # Position table
        pos_lines = []
        for p in sorted(positions, key=lambda x: x.unrealized_pl, reverse=True):
            pct = _pct(p)
            icon = "🟢" if pct >= 0 else "🔴"
            pos_lines.append(f"{icon} **{p.symbol}** ${p.unrealized_pl:+.2f} ({pct:+.1f}%) — {p.qty} shares")
        embed.add_field(name="📊 Positions", value="\n".join(pos_lines[:8]) or "None", inline=False)

        # Risk dashboard
        unprotected = []
        protected_syms = {o.get('symbol') for o in trail_stops}
        for p in positions:
            if p.symbol not in protected_syms:
                unprotected.append(p.symbol)
        risk_text = f"🛡️ Trailing Stops: **{len(trail_stops)}** | Limit Sells: **{len(limit_sells)}** | Buys: **{len(limit_buys)}**\n"
        if unprotected:
            risk_text += f"⚠️ **UNPROTECTED:** {', '.join(unprotected)}\n"
        else:
            risk_text += f"✅ All positions have trailing stop protection\n"

        # Sector concentration
        if sectors:
            top_sector = max(sectors, key=sectors.get)
            top_pct = sectors[top_sector] / market_val * 100 if market_val > 0 else 0
            risk_text += f"📊 Top sector: **{top_sector}** ({top_pct:.0f}%)"
            if top_pct > 40:
                risk_text += " ⚠️ CONCENTRATED"
        embed.add_field(name="⚡ Risk Dashboard", value=risk_text, inline=False)

        # Recent trades
        if _trade_log:
            trade_text = ""
            for t in _trade_log[-5:]:
                trade_text += f"• {t['action']} {t['symbol']} x{t['qty']} @ ${t['price']} ({t['time']})\n"
            embed.add_field(name=f"📋 Recent Trades ({len(_trade_log)})", value=trade_text[:1024], inline=False)

        embed.set_footer(text="Beast V3 | AI-Powered | Decisions every 10 min")
        await channel.send(embed=embed)

        # Telegram summary
        tg = f"📋 10min Report {now.strftime('%I:%M %p')}\n"
        tg += f"${equity:,.0f} | P&L: ${total_pl:+.2f}\n"
        tg += f"Protected: {len(trail_stops)}/{len(positions)}\n"
        if unprotected:
            tg += f"⚠️ Unprotected: {','.join(unprotected)}\n"
        for p in sorted(positions, key=lambda x: x.unrealized_pl, reverse=True)[:6]:
            tg += f"{'🟢' if _pct(p)>=0 else '🔴'} {p.symbol} {_pct(p):+.1f}% ${p.unrealized_pl:+.0f}\n"
        _tg(tg)

    except Exception as e:
        log.error(f"Decision report error: {e}")


@tasks.loop(seconds=120)
async def fast_runner_scan():
    """Every 2 min: scan for hot movers + past winners running.
    Finds stocks running >3%, checks sentiment, auto-buys if confidence high.
    This is the FASTEST money-making loop — catches runners before they're gone."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
        if not _is_trading_hours():
            return

        channel = bot.get_channel(SCAN_CHANNEL_ID)
        positions = gateway.get_positions()
        held_syms = {p.symbol for p in positions}

        def _scan_runners():
            """Scan the ENTIRE MARKET for movers — no watchlist, let the market tell us."""
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockSnapshotRequest
            dc = StockHistoricalDataClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'))
            runners = []

            # Layer 1: Alpaca most active (top 20 by volume — ANY stock in the market)
            try:
                from alpaca.data.requests import MostActivesRequest
                actives = dc.get_most_actives(MostActivesRequest(top=20, by='volume'))
                active_syms = []
                if hasattr(actives, 'most_actives'):
                    for a in actives.most_actives:
                        sym = a.symbol if hasattr(a, 'symbol') else ''
                        if sym and len(sym) <= 5 and sym not in held_syms:
                            active_syms.append(sym)
                if active_syms:
                    snaps = dc.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=active_syms[:20], feed='iex'))
                    for sym, s in snaps.items():
                        try:
                            price = float(s.latest_trade.price)
                            prev = float(s.previous_daily_bar.close)
                            pct = (price - prev) / prev * 100
                            vol = int(s.daily_bar.volume) if s.daily_bar else 0
                            if price > 5 and vol > 100000 and abs(pct) > 2:
                                runners.append({'symbol': sym, 'price': price, 'pct': pct, 'volume': vol, 'prev': prev})
                                # Persist to PostgreSQL — watchlist grows forever
                                if sym not in DIP_BUY_WATCHLIST:
                                    DIP_BUY_WATCHLIST.append(sym)
                                pg = _get_pg()
                                if pg:
                                    pg.add_to_watchlist(sym, source='most_active', pct=round(pct, 1), volume=vol)
                        except:
                            pass
            except Exception as e:
                log.debug(f"Most actives scan: {e}")

            # Layer 2: Past winners (proven stocks)
            try:
                pw = [s for s in PAST_WINNERS if s not in held_syms and s not in [r['symbol'] for r in runners]][:10]
                if pw:
                    snaps = dc.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=pw, feed='iex'))
                    for sym, s in snaps.items():
                        try:
                            price = float(s.latest_trade.price)
                            prev = float(s.previous_daily_bar.close)
                            pct = (price - prev) / prev * 100
                            vol = int(s.daily_bar.volume) if s.daily_bar else 0
                            if price > 5 and abs(pct) > 1.5:
                                runners.append({'symbol': sym, 'price': price, 'pct': pct, 'volume': vol, 'prev': prev})
                        except:
                            pass
            except:
                pass

            return sorted(runners, key=lambda x: -abs(x['pct']))

        runners = await asyncio.to_thread(_scan_runners)

        if not runners:
            return

        log.info(f"  🏃 Runner scan: {len(runners)} stocks running >3%")
        _pg_log("RUNNER_SCAN", reason=f"{len(runners)} stocks running >3%", source="2min")

        acct = gateway.get_account()
        equity = float(acct.get('equity', 100000))

        for r in runners[:3]:  # Max 3 candidates per scan
            sym = r['symbol']
            # Allow re-buying after 30 min cooldown (Akash Method: buy → sell → rebuy)
            last_buy_time = _prev_prices.get(f"_runner_buy_time_{sym}", 0)
            if time.time() - last_buy_time < 1800:  # 30 min cooldown
                continue

            # Quick sentiment check
            sent = None
            try:
                sa = SentimentAnalyst()
                sent = sa.analyze(sym)
                sent_score = sent.total_score
            except:
                sent_score = 0

            # Rule 29: Don't chase +5% without catalyst (sentiment >= 3)
            if r['pct'] > 5.0 and sent_score < 3:
                log.info(f"  🏃 {sym} +{r['pct']:.1f}% but sentiment {sent_score:+d} — skipping (Rule 29)")
                continue

            # Auto-buy: 2% of portfolio
            qty = max(1, int(equity * 0.02 / r['price']))
            buy_price = round(r['price'] * 1.002, 2)

            result = _smart_buy(
                sym, qty, buy_price,
                reason=f"Fast runner +{r['pct']:.1f}% vol={r['volume']:,}",
                day_change_pct=r['pct'], sentiment_score=sent_score,
                source="2min_runner", vix=_cached_vix,
                sentiment_data={'total': sent_score,
                                'yahoo': getattr(sent, 'yahoo_score', 0) if sent else 0,
                                'reddit': getattr(sent, 'reddit_score', 0) if sent else 0,
                                'analyst': getattr(sent, 'analyst_score', 0) if sent else 0}
            )

            if result and result.state.value != 'REJECTED':
                _prev_prices[f"_runner_buy_time_{sym}"] = time.time()  # 30min cooldown
                _log_trade(f"RUNNER BUY (+{r['pct']:.1f}%)", sym, qty, buy_price,
                           f"Running +{r['pct']:.1f}% with {r['volume']:,} volume, sentiment {sent_score:+d}",
                           "2min Runner")
                if channel:
                    await channel.send(
                        f"🏃🟢 **RUNNER CAUGHT: {sym}** +{r['pct']:.1f}%\n"
                        f"Buy {qty} @ ${buy_price} | Vol: {r['volume']:,} | Sent: {sent_score:+d}")
                log.info(f"  🏃 AUTO-BUY runner {sym} {qty}x @ ${buy_price} (+{r['pct']:.1f}%)")
            else:
                log.info(f"  🏃 {sym} blocked: {result.error if result else 'no result'}")

    except Exception as e:
        log.error(f"Fast runner scan error: {e}")


@tasks.loop(minutes=30)
async def claude_deep_scan():
    """Every 30 min: Claude Opus 4.7 MEGA SCAN — the ULTIMATE intelligence briefing.
    
    Collects EVERYTHING:
    - All positions with P&L
    - All open orders (limits + trailing stops)
    - Full sentiment on every position (Yahoo + Reddit + StockTwits + Analyst)
    - Earnings calendar for every held stock
    - Short interest + squeeze risk
    - Market movers / today's runners
    - TV indicators (from last 5-min scan cache)
    - Regime + SPY + VIX Fear/Greed
    - Trump / geopolitical headlines
    - Sector rotation data
    - Past winners status
    - Portfolio correlation / concentration
    
    Sends ALL of this to Claude Opus 4.7 for institutional-grade analysis.
    Claude's briefing is cached → GPT-4o references it in subsequent 5-min scans.
    """
    try:
        channel = bot.get_channel(SCAN_CHANNEL_ID)
        if not channel:
            return

        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
        # 24/7 — Claude mega-scan always runs (news + sentiment work anytime)

        if not brain or not brain.is_available:
            return

        positions = gateway.get_positions()
        acct = gateway.get_account()
        equity = float(acct.get('equity', 100000))
        cash = float(acct.get('cash', 0))
        total_pl = sum(p.unrealized_pl for p in positions)

        await channel.send(f"🧠 **CLAUDE MEGA-SCAN STARTING** — collecting ALL intelligence...")

        # ═══════════════════════════════════════════════
        # PHASE 1: Collect EVERYTHING (parallel where possible)
        # ═══════════════════════════════════════════════

        all_intel = {}
        market_intel = {}
        runner_data = []
        past_winner_status = {}

        def _collect_everything():
            sa = SentimentAnalyst()

            # 1. Full intel on every position
            for p in positions:
                try:
                    all_intel[p.symbol] = sa.full_stock_intel(p.symbol)
                except:
                    all_intel[p.symbol] = {}

            # 2. Market-wide sentiment
            try:
                market_intel['full_market'] = sa.full_market_sentiment()
            except:
                market_intel['full_market'] = {}

            # 3. Fear & Greed
            try:
                market_intel['fear_greed'] = sa.get_fear_greed()
            except:
                market_intel['fear_greed'] = {}

            # 3.5 MARKET INTELLIGENCE (congressional, insider, sector, econ, squeeze)
            try:
                from market_intel import MarketIntelligence
                mi = MarketIntelligence(db=_get_pg())
                held_syms_list = [p.symbol for p in positions]
                
                # Market-wide intel
                mkt_data = mi.full_market_intel(held_syms_list)
                market_intel['congress'] = mkt_data.get('congress', [])
                market_intel['economic_calendar'] = mkt_data.get('economic_calendar', [])
                market_intel['sector_rotation'] = mkt_data.get('sector_rotation', {})
                market_intel['correlation'] = mkt_data.get('correlation', {})
                
                # Per-stock intel (insider + options + squeeze)
                for p in positions[:10]:
                    try:
                        stock_data = mi.full_intel(p.symbol)
                        all_intel[p.symbol] = {**(all_intel.get(p.symbol) or {}), **stock_data}
                    except:
                        pass
                
                # Store everything to DB for learning
                mi.store_intel_to_db()
                for p in positions[:8]:
                    mi.store_intel_to_db(p.symbol)
                
                log.info(f"  [INTEL] Market intelligence collected: congress={len(market_intel.get('congress',[]))} "
                         f"econ={len(market_intel.get('economic_calendar',[]))} "
                         f"rotation={list(market_intel.get('sector_rotation',{}).get('rotating_in',[])) }")
            except Exception as e:
                log.warning(f"  Market intel collection: {e}")

            # 4. TradingView indicators on ALL positions
            tv_intel = {}
            for p in positions:
                try:
                    ind = _get_tv_indicators(p.symbol)
                    if ind:
                        tv_intel[p.symbol] = ind
                except:
                    pass
            market_intel['tv_data'] = tv_intel

            # 5. Today's runners
            try:
                from alpaca.data.historical import StockHistoricalDataClient
                from alpaca.data.requests import StockSnapshotRequest
                dc = StockHistoricalDataClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'))

                # Scan past winners not held
                held_syms = {p.symbol for p in positions}
                pw_check = [s for s in PAST_WINNERS if s not in held_syms]
                if pw_check:
                    snaps = dc.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=pw_check[:15], feed='iex'))
                    for sym, s in snaps.items():
                        try:
                            price = float(s.latest_trade.price)
                            prev = float(s.previous_daily_bar.close)
                            pct = (price - prev) / prev * 100
                            past_winner_status[sym] = {'price': price, 'change_pct': round(pct, 1)}
                        except:
                            pass
            except:
                pass

            # 5. Finviz runners
            try:
                runner_data.extend(sa.scan_finviz_runners())
            except:
                pass

        await asyncio.to_thread(_collect_everything)

        # 6. Open orders + trailing stops
        open_orders = await asyncio.to_thread(gateway.get_open_orders)
        trail_stops = [o for o in open_orders if 'trailing' in str(o.get('type', '')).lower()]
        limit_sells = [o for o in open_orders if o.get('side') == 'sell' and 'trailing' not in str(o.get('type', '')).lower()]

        # 7. Correlation check
        try:
            from correlation_check import CorrelationChecker
            corr = CorrelationChecker().check(positions)
        except:
            corr = {}

        # 8. Regime
        regime_val = "unknown"
        spy_change = 0
        try:
            regime_val = regime_det.detect(spy_change).value
        except:
            pass

        # ═══════════════════════════════════════════════
        # PHASE 2: Build MASSIVE data package for Claude
        # ═══════════════════════════════════════════════

        mega_data = {
            'timestamp': now.isoformat(),
            'portfolio': {
                'equity': equity, 'cash': cash, 'total_pl': total_pl,
                'position_count': len(positions), 'order_count': len(open_orders),
                'trailing_stops': len(trail_stops), 'limit_sells': len(limit_sells),
                'heat_pct': round((equity - cash) / equity * 100, 1) if equity > 0 else 0,
            },
            'positions': [],
            'market': {
                'regime': regime_val,
                'fear_greed': market_intel.get('fear_greed', {}),
                'full_sentiment': market_intel.get('full_market', {}),
            },
            'past_winners_not_held': past_winner_status,
            'finviz_runners': [r.get('symbol', '?') for r in runner_data[:10]],
            'correlation': {
                'max_sector': corr.get('max_sector', '?'),
                'max_pct': corr.get('max_pct', 0),
                'warnings': corr.get('warnings', []),
            },
        }

        # Position details with ALL intel
        for p in sorted(positions, key=lambda x: abs(x.unrealized_pl), reverse=True):
            intel = all_intel.get(p.symbol, {})
            tv = market_intel.get('tv_data', {}).get(p.symbol, {})
            pct = _pct(p)
            has_trail = p.symbol in {o.get('symbol') for o in trail_stops}
            mega_data['positions'].append({
                'symbol': p.symbol, 'qty': p.qty, 'entry': p.avg_entry,
                'price': p.current_price, 'pnl': round(p.unrealized_pl, 2),
                'pct': round(pct, 1), 'has_trailing_stop': has_trail,
                'yahoo': intel.get('yahoo', 0), 'reddit': intel.get('reddit', 0),
                'analyst': intel.get('analyst', 0), 'stocktwits': intel.get('stocktwits', 0),
                'total_sentiment': intel.get('total_sentiment', 0),
                'earnings_days': intel.get('earnings_days', 999),
                'earnings_date': intel.get('earnings_date', '?'),
                'short_pct': intel.get('short_pct', 0),
                'squeeze_risk': intel.get('squeeze_risk', False),
                # TradingView indicators
                'rsi': tv.get('rsi', 0),
                'macd_hist': tv.get('macd_hist', 0),
                'vwap_above': tv.get('vwap_above', False),
                'bb_position': tv.get('bb_position', '?'),
                'confluence': tv.get('confluence', 0),
                'ema_9': tv.get('ema_9', 0),
                'ema_21': tv.get('ema_21', 0),
                'volume_ratio': tv.get('volume_ratio', 1.0),
            })

        # ═══════════════════════════════════════════════
        # PHASE 3: Send to Claude for ULTRA DEEP analysis
        # ═══════════════════════════════════════════════

        deep_results = {}
        def _run_claude_mega():
            # Send entire portfolio to Claude as one mega-analysis
            for p_data in mega_data['positions'][:8]:
                try:
                    sym = p_data['symbol']
                    # Enrich with market context
                    p_data['regime'] = mega_data['market']['regime']
                    p_data['vix'] = mega_data['market'].get('fear_greed', {}).get('vix', 0)
                    p_data['market_sentiment'] = mega_data['market'].get('full_sentiment', {}).get('total_score', 0)
                    p_data['trump_score'] = mega_data['market'].get('full_sentiment', {}).get('trump_score', 0)
                    p_data['sector_concentration'] = mega_data['correlation'].get('max_pct', 0)
                    p_data['holding'] = True
                    result = brain.deep_analysis(sym, p_data)
                    if result:
                        deep_results[sym] = result
                except Exception as e:
                    log.warning(f"Claude mega {p_data.get('symbol','?')}: {e}")
        await asyncio.to_thread(_run_claude_mega)

        # ═══════════════════════════════════════════════
        # PHASE 4: Build RICH Discord report
        # ═══════════════════════════════════════════════

        # Embed 1: Portfolio overview + market context
        fg = market_intel.get('fear_greed', {})
        mkt = market_intel.get('full_market', {})
        embed1 = discord.Embed(
            title=f"🧠 CLAUDE MEGA-SCAN — {now.strftime('%I:%M %p ET')}",
            description=(
                f"**Portfolio:** ${equity:,.0f} | P&L: ${total_pl:+.2f} | Heat: {mega_data['portfolio']['heat_pct']:.0f}%\n"
                f"**Market:** {regime_val.upper()} | VIX: {fg.get('vix','?')} ({fg.get('level','?')}) | "
                f"Sentiment: {mkt.get('total_score', '?'):+d}\n"
                f"**Protection:** {len(trail_stops)} trailing stops | {len(limit_sells)} limit sells\n"
                f"**Concentration:** {corr.get('max_sector','?')} @ {corr.get('max_pct',0):.0f}%"
            ),
            color=0x9B59B6
        )

        # Warnings
        warnings = corr.get('warnings', [])
        if mega_data['portfolio']['heat_pct'] > 55:
            warnings.append(f"🔥 Portfolio heat {mega_data['portfolio']['heat_pct']:.0f}% (approaching 60% limit)")
        if warnings:
            embed1.add_field(name="⚠️ Warnings", value="\n".join(warnings[:5]), inline=False)

        # Past winners running
        pw_running = {s: d for s, d in past_winner_status.items() if d.get('change_pct', 0) > 2}
        if pw_running:
            pw_text = "\n".join(f"🏆 **{s}** +{d['change_pct']:.1f}% (${d['price']:.2f})" for s, d in
                               sorted(pw_running.items(), key=lambda x: -x[1]['change_pct'])[:5])
            embed1.add_field(name="🏆 Past Winners Running (not held)", value=pw_text, inline=False)

        await channel.send(embed=embed1)

        # Embed 2: Claude verdicts per stock
        if deep_results:
            embed2 = discord.Embed(title="🧠 Claude Opus Verdicts", color=0x9B59B6)
            for sym, r in deep_results.items():
                action = r.get('action', 'HOLD')
                conf = r.get('confidence', 0)
                reasoning = r.get('reasoning', '')[:250]
                intel = all_intel.get(sym, {})
                icon = "🟢" if action == 'BUY' else "🔴" if action == 'SELL' else "⚪"

                detail = f"**{action}** ({conf}%)\n"
                detail += f"Sent: Y:{intel.get('yahoo',0):+d} R:{intel.get('reddit',0):+d} ST:{intel.get('stocktwits',0):+d} A:{intel.get('analyst',0):+d}\n"
                if intel.get('earnings_days', 999) < 14:
                    detail += f"⚡ Earnings in **{intel['earnings_days']}d** ({intel.get('earnings_date','?')})\n"
                if intel.get('squeeze_risk'):
                    detail += f"🔥 **SHORT SQUEEZE RISK** ({intel.get('short_pct',0):.1f}% short)\n"
                detail += reasoning[:150]
                embed2.add_field(name=f"{icon} {sym}", value=detail[:1024], inline=False)

            embed2.set_footer(text="Source: Claude Opus 4.7 | Cached for GPT-4o 5-min scans")
            await channel.send(embed=embed2)

        # Embed 3: Sentiment matrix
        embed3 = discord.Embed(title="📰 Full Sentiment Matrix", color=0xf0b232)
        sent_lines = []
        for p_data in mega_data['positions']:
            s = p_data.get('total_sentiment', 0)
            icon = "📈" if s > 0 else "📉" if s < 0 else "➡️"
            sent_lines.append(
                f"{icon} **{p_data['symbol']}** Y:{p_data.get('yahoo',0):+d} R:{p_data.get('reddit',0):+d} "
                f"ST:{p_data.get('stocktwits',0):+d} A:{p_data.get('analyst',0):+d} = **{s:+d}** "
                f"{'| 🔥SQUEEZE' if p_data.get('squeeze_risk') else ''}"
                f"{'| ⚡EARN '+str(p_data.get('earnings_days',''))+'d' if p_data.get('earnings_days',999) < 14 else ''}"
            )
        embed3.add_field(name="Per-Stock Intel", value="\n".join(sent_lines[:12]) or "No data", inline=False)

        # Trump/geo from market sentiment
        trump_hl = mkt.get('trump_headlines', [])
        if trump_hl:
            embed3.add_field(name=f"🏛️ Geopolitical ({mkt.get('trump_score',0):+d})",
                           value="\n".join(f"• {h[:60]}" for h in trump_hl[:3]), inline=False)
        await channel.send(embed=embed3)

        # Telegram mega summary
        tg = f"🧠 CLAUDE MEGA-SCAN {now.strftime('%I:%M %p')}\n"
        tg += f"━━━━━━━━━━━━━━━━━━━━━━\n"
        tg += f"${equity:,.0f} | P&L: ${total_pl:+.2f} | VIX: {fg.get('vix','?')}\n"
        tg += f"Regime: {regime_val} | Heat: {mega_data['portfolio']['heat_pct']:.0f}%\n\n"
        for sym, r in deep_results.items():
            tg += f"{'🟢' if r.get('action')=='BUY' else '🔴' if r.get('action')=='SELL' else '⚪'} {sym}: {r.get('action')} ({r.get('confidence',0)}%)\n"
        if pw_running:
            pw_str = ', '.join(f"{s}+{d['change_pct']:.0f}%" for s, d in pw_running.items())
            tg += f"\n🏆 Past winners running: {pw_str}\n"
        _tg(tg)

        # ═══════════════════════════════════════════════
        # PHASE 5: AUTO-EXECUTE high-confidence Claude verdicts
        # ═══════════════════════════════════════════════
        CLAUDE_AUTO_THRESHOLD = 75  # Only auto-execute >= 75% confidence

        if _is_trading_hours() and deep_results:
            held_syms = {p.symbol for p in positions}
            active_scalps = sum(1 for p in positions if 0 < _pct(p) < 2.0)

            for sym, r in deep_results.items():
                action = r.get('action', 'HOLD')
                conf = r.get('confidence', 0)
                reasoning = r.get('reasoning', '')[:100]

                if conf < CLAUDE_AUTO_THRESHOLD:
                    continue

                try:
                    if action == 'BUY' and sym not in held_syms:
                        # Auto-buy: 3% of portfolio, limit at current price
                        pos_data = next((pd for pd in mega_data['positions'] if pd['symbol'] == sym), None)
                        price = pos_data['price'] if pos_data else 0
                        if price > 0:
                            qty = max(1, int(equity * 0.03 / price))
                            buy_price = round(price * 1.002, 2)  # Slight premium to ensure fill
                            intel = all_intel.get(sym, {})
                            result = _smart_buy(
                                sym, qty, buy_price,
                                reason=f"Claude AI BUY {conf}%: {reasoning}",
                                day_change_pct=0,
                                sentiment_score=intel.get('total_sentiment', 0),
                                source="30min_claude", vix=_cached_vix,
                                confidence=conf,
                                ai_verdict_data=r,
                                sentiment_data={'total': intel.get('total_sentiment', 0)}
                            )
                            if result and result.state.value != 'REJECTED':
                                _log_trade(f"AI BUY (Claude {conf}%)", sym, qty, buy_price, reasoning, "30min Claude")
                                if channel:
                                    await channel.send(
                                        f"🧠🟢 **CLAUDE AUTO-BUY: {sym}** ({conf}% confidence)\n"
                                        f"Buy {qty} @ ${buy_price} | {reasoning}")
                                log.info(f"  🧠 Claude auto-BUY: {sym} {qty}x @ ${buy_price} ({conf}%)")
                            else:
                                log.info(f"  🧠 Claude BUY {sym} blocked: {result.error if result else 'no result'}")
                                _pg_log("AI_BLOCKED", symbol=sym, reason=f"Claude BUY blocked: {result.error if result else 'no result'}", ai_source="Claude", source="30min")

                    elif action == 'SELL' and sym in held_syms:
                        # Auto-sell: sell available qty at market-ish price
                        pos = next((p for p in positions if p.symbol == sym), None)
                        if pos and pos.qty_available and pos.qty_available > 0:
                            sell_qty = pos.qty_available
                            sell_price = round(pos.current_price * 0.999, 2)
                            gateway.place_sell(sym, sell_qty, sell_price,
                                              reason=f"Claude AI SELL {conf}%: {reasoning}",
                                              entry_price=pos.avg_entry)
                            _log_trade(f"AI SELL (Claude {conf}%)", sym, sell_qty, sell_price, reasoning, "30min Claude")
                            if channel:
                                await channel.send(
                                    f"🧠🔴 **CLAUDE AUTO-SELL: {sym}** ({conf}% confidence)\n"
                                    f"Sell {sell_qty} @ ${sell_price} | {reasoning}")
                            log.info(f"  🧠 Claude auto-SELL: {sym} {sell_qty}x @ ${sell_price} ({conf}%)")

                except Exception as e:
                    log.warning(f"Claude auto-execute {sym}: {e}")

        log.info(f"Claude MEGA-SCAN complete: {len(deep_results)} analyzed, {len(all_intel)} intel packages")
        _pg_log("MEGA_SCAN", reason=f"Claude mega: {len(deep_results)} analyzed, {len(all_intel)} intel", source="30min", data={"analyzed": len(deep_results), "intel": len(all_intel)})

    except Exception as e:
        log.error(f"Claude mega-scan error: {e}\n{traceback.format_exc()}")


@position_monitor.before_loop
async def before_monitor():
    await bot.wait_until_ready()

@full_scan.before_loop
async def before_scan():
    await bot.wait_until_ready()
    await asyncio.sleep(10)

@decision_report.before_loop
async def before_decision():
    await bot.wait_until_ready()
    await asyncio.sleep(30)

@fast_runner_scan.before_loop
async def before_runner():
    await bot.wait_until_ready()
    await asyncio.sleep(60)  # Wait 1 min — let position_monitor run first

@claude_deep_scan.before_loop
async def before_claude():
    await bot.wait_until_ready()
    await asyncio.sleep(120)


@tasks.loop(hours=1)
async def ai_background_learning():
    """Every hour: AI analyzes historical patterns and stores insights.
    Uses yfinance for 90-day history, GPT-4o for pattern analysis.
    Runs in background — doesn't block trading."""
    try:
        pg = _get_pg()
        if not pg:
            return

        # Get ALL stocks: watchlist + any we've ever traded + any AI has analyzed
        watchlist = set(pg.get_watchlist())
        # Add stocks from orders table
        traded = pg._exec("SELECT DISTINCT symbol FROM orders WHERE symbol IS NOT NULL", fetch=True)
        for r in (traded or []):
            watchlist.add(r['symbol'])
        # Add stocks from AI verdicts
        analyzed = pg._exec("SELECT DISTINCT symbol FROM ai_verdicts WHERE symbol IS NOT NULL", fetch=True)
        for r in (analyzed or []):
            watchlist.add(r['symbol'])
        # Add stocks from position snapshots
        held = pg._exec("SELECT DISTINCT symbol FROM position_snapshots WHERE symbol IS NOT NULL", fetch=True)
        for r in (held or []):
            watchlist.add(r['symbol'])

        all_stocks = sorted(list(watchlist))
        if not all_stocks:
            return

        # Process 20 stocks per hour (rotates through entire list over ~10 hours)
        _learn_cycle = getattr(ai_background_learning, '_cycle', 0)
        batch_size = 20
        start = (_learn_cycle * batch_size) % len(all_stocks)
        batch = all_stocks[start:start + batch_size]
        ai_background_learning._cycle = _learn_cycle + 1

        log.info(f"  🧠 Background learning: batch {_learn_cycle+1} — {len(batch)}/{len(all_stocks)} stocks (starting at {batch[0]})")

        def _learn_batch():
            import yfinance as yf
            for sym in batch:
                try:
                    stock = yf.Ticker(sym)
                    
                    # 1. EARNINGS PATTERN: How does this stock react to earnings?
                    try:
                        hist = stock.history(period='1y')
                        cal = stock.calendar
                        earnings_hist = stock.earnings_history
                        if earnings_hist is not None and len(earnings_hist) > 0:
                            for _, row in earnings_hist.iterrows():
                                try:
                                    eps_actual = row.get('epsActual', 0)
                                    eps_estimate = row.get('epsEstimate', 0)
                                    surprise = eps_actual - eps_estimate if eps_actual and eps_estimate else 0
                                    beat = 'beat' if surprise > 0 else ('miss' if surprise < 0 else 'inline')
                                    # Get price around earnings date
                                    earn_date = row.name if hasattr(row, 'name') else None
                                    if earn_date and not hist.empty:
                                        try:
                                            idx = hist.index.get_indexer([earn_date], method='nearest')[0]
                                            if 0 < idx < len(hist) - 1:
                                                pre = float(hist.iloc[idx-1]['Close'])
                                                post = float(hist.iloc[idx+1]['Close'])
                                                gap = (post - pre) / pre * 100
                                                pg.learn_earnings_pattern(sym, str(earn_date)[:10],
                                                                         pre, post, beat, gap)
                                        except:
                                            pass
                                except:
                                    pass
                    except:
                        pass

                    # 2. PRICE BEHAVIOR: Support/resistance, avg daily range
                    try:
                        hist_90d = stock.history(period='3mo')
                        if not hist_90d.empty and len(hist_90d) > 20:
                            closes = [float(c) for c in hist_90d['Close']]
                            highs = [float(h) for h in hist_90d['High']]
                            lows = [float(l) for l in hist_90d['Low']]
                            avg_range = sum(h - l for h, l in zip(highs, lows)) / len(highs)
                            avg_range_pct = avg_range / (sum(closes) / len(closes)) * 100
                            support = min(lows[-20:])
                            resistance = max(highs[-20:])
                            
                            pg.save_trend(sym, 'price_behavior',
                                f"90d avg daily range: {avg_range_pct:.1f}%. Support: ${support:.2f}, Resistance: ${resistance:.2f}",
                                confidence=70,
                                data={'avg_range_pct': round(avg_range_pct, 1), 
                                      'support': round(support, 2),
                                      'resistance': round(resistance, 2),
                                      'current': closes[-1] if closes else 0})
                    except:
                        pass

                    # 3. Get earnings pattern summary and store as trend
                    try:
                        pattern = pg.get_earnings_pattern(sym)
                        if pattern.get('known') and pattern.get('samples', 0) >= 2:
                            pg.save_trend(sym, 'earnings_pattern',
                                f"{pattern['tendency']}: avg {pattern['avg_gap_pct']:+.1f}% gap. {pattern['play']}",
                                confidence=min(90, 50 + pattern['samples'] * 10),
                                data=pattern)
                    except:
                        pass

                    # 4. FUNDAMENTAL ANALYSIS: PE, PEG, growth, analyst targets
                    try:
                        from fundamentals import analyze_fundamentals
                        fund = analyze_fundamentals(sym)
                        if fund and fund.get('fundamental_score', 0) != 0:
                            score = fund['fundamental_score']
                            verdict = fund['verdict']
                            signals = fund.get('signals', [])
                            insight = f"{verdict} (score={score}): {', '.join(signals[:3])}"
                            pg.save_trend(sym, 'fundamentals', insight[:500],
                                confidence=min(95, max(30, 50 + score)),
                                data={
                                    'score': score, 'verdict': verdict,
                                    'pe': fund.get('forward_pe', 0),
                                    'peg': fund.get('peg', 0),
                                    'rev_growth': fund.get('revenue_growth_pct', 0),
                                    'earn_growth': fund.get('earnings_growth_pct', 0),
                                    'analyst': fund.get('analyst_rating', '?'),
                                    'target': fund.get('target_mean', 0),
                                    'upside': fund.get('upside_pct', 0),
                                    'lynch_type': fund.get('lynch_type', '?'),
                                })
                            if score >= 40:
                                log.info(f"    {sym}: {verdict} score={score} PE={fund.get('forward_pe',0)} Rev={fund.get('revenue_growth_pct',0)}%")
                    except:
                        pass

                    # 4.5 SCALP vs SWING CLASSIFICATION
                    # Uses: daily range, fundamentals upside, our win rate, price pattern
                    # Stored so the bot knows: "GOOGL = swing, NOK = scalp"
                    try:
                        classification = 'SCALP'  # default
                        reasons = []
                        
                        # Get price behavior data we just stored
                        pb = pg.get_trends(symbol=sym, trend_type='price_behavior')
                        daily_range = 0
                        if pb:
                            daily_range = pb[0].get('data', {}).get('avg_range_pct', 0)
                        
                        # Get fundamentals we just stored
                        ft = pg.get_trends(symbol=sym, trend_type='fundamentals')
                        fund_upside = 0
                        fund_score = 0
                        if ft:
                            fd = ft[0].get('data', {})
                            fund_upside = fd.get('upside', 0)
                            fund_score = fd.get('score', 0)
                        
                        # Get our trade history
                        hist_data = pg.get_stock_history(sym)
                        win_rate = hist_data.get('win_rate', 50)
                        avg_hold = hist_data.get('avg_hold_minutes', 0)
                        
                        # Classification logic:
                        # SWING: high upside + strong fundamentals + low daily range (steady climber)
                        # SCALP: high daily range + quick flip history + low upside
                        # CORE: mega cap + very strong fundamentals (buy and forget)
                        
                        if fund_score >= 60 and fund_upside > 30:
                            classification = 'CORE'
                            reasons.append(f"Strong fundamentals (score={fund_score}) + {fund_upside:+.0f}% upside")
                        elif fund_upside > 15 and daily_range < 3:
                            classification = 'SWING'
                            reasons.append(f"Good upside ({fund_upside:+.0f}%) + steady price (range={daily_range:.1f}%)")
                        elif fund_upside > 15 and fund_score >= 30:
                            classification = 'SWING'
                            reasons.append(f"Analyst upside {fund_upside:+.0f}% with decent fundamentals")
                        elif daily_range > 4:
                            classification = 'SCALP'
                            reasons.append(f"High volatility (range={daily_range:.1f}%) — quick flips work")
                        elif avg_hold > 0 and avg_hold < 60:
                            classification = 'SCALP'
                            reasons.append(f"History: avg hold {avg_hold:.0f} min — we scalp this")
                        elif win_rate > 70 and avg_hold < 120:
                            classification = 'SCALP'
                            reasons.append(f"High win rate ({win_rate:.0f}%) with quick holds")
                        else:
                            classification = 'SWING' if fund_upside > 5 else 'SCALP'
                            reasons.append(f"Default: upside={fund_upside:+.0f}% range={daily_range:.1f}%")
                        
                        pg.save_trend(sym, 'trade_style',
                            f"{classification}: {', '.join(reasons)}",
                            confidence=70,
                            data={
                                'classification': classification,
                                'reasons': reasons,
                                'daily_range_pct': daily_range,
                                'fund_upside': fund_upside,
                                'fund_score': fund_score,
                                'win_rate': win_rate,
                                'avg_hold_min': avg_hold,
                            })
                    except:
                        pass

                    # 5. Ask GPT-4o for deeper insight (if available)
                    try:
                        info = stock.info
                        sector = info.get('sector', '?')
                        market_cap = info.get('marketCap', 0)
                        pe = info.get('trailingPE', 0)
                        
                        if brain and brain._gpt_available and market_cap and market_cap > 1e9:
                            data = {
                                'symbol': sym, 'sector': sector,
                                'market_cap_b': round(market_cap / 1e9, 1),
                                'pe_ratio': round(pe, 1) if pe else '?',
                                'avg_daily_range_pct': round(avg_range_pct, 1) if 'avg_range_pct' in dir() else '?',
                            }
                            result = brain.analyze_stock(sym, data)
                            if result and result.get('reasoning'):
                                pg.save_trend(sym, 'ai_analysis',
                                    result.get('reasoning', '')[:500],
                                    confidence=result.get('confidence', 50),
                                    data={'action': result.get('action'), 'source': 'background_learning'})
                    except:
                        pass

                except Exception as e:
                    log.debug(f"Background learn {sym}: {e}")

        await asyncio.to_thread(_learn_batch)
        pg.log_activity('LEARNING', category='ai', reason=f"Analyzed {len(batch)} stocks: {', '.join(batch)}", source='hourly')
        log.info(f"  🧠 Background learning complete: {len(batch)} stocks analyzed")

    except Exception as e:
        log.error(f"Background learning error: {e}")


@ai_background_learning.before_loop
async def before_learning():
    await bot.wait_until_ready()
    await asyncio.sleep(300)


@tasks.loop(minutes=30)
async def outcome_grader():
    """Every 30 min: Grade past trade decisions — did we make the right call?
    This is what makes the bot ACTUALLY learn. Without this, learning is fake."""
    try:
        pg = _get_pg()
        if not pg:
            return

        from datetime import datetime, timezone

        # Grade trade_decisions: check current price vs price_at_decision
        # Use timezone-aware NOW() from DB side to avoid Python/DB timezone mismatch
        ungraded = pg._exec(
            """SELECT id, symbol, action, price_at_decision, created_at
               FROM trade_decisions
               WHERE was_correct IS NULL AND price_at_decision IS NOT NULL
                 AND price_at_decision > 0
                 AND created_at < NOW() - interval '30 minutes'
                 AND created_at > NOW() - interval '48 hours'
               LIMIT 50""",
            fetch=True
        ) or []

        if not ungraded:
            log.info(f"  📝 Outcome grader: 0 ungraded decisions")
            return

        # Get current prices for all ungraded symbols
        symbols = list(set(d['symbol'] for d in ungraded))
        current_prices = {}
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockSnapshotRequest
            dc = StockHistoricalDataClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'))
            snaps = dc.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=symbols[:20], feed='iex'))
            for sym, s in snaps.items():
                current_prices[sym] = float(s.latest_trade.price)
        except Exception as e:
            log.warning(f"  📝 Grader price fetch failed: {e}")
            return

        graded = 0
        for d in ungraded:
            sym = d['symbol']
            if sym not in current_prices:
                continue
            now_price = current_prices[sym]
            then_price = float(d['price_at_decision'])
            if then_price <= 0:
                continue

            # Grade it: for BUY decisions, correct if price went up
            # For BLOCK/SKIP, correct if price went down (we were right to avoid)
            pct_move = (now_price - then_price) / then_price * 100
            action = d['action']

            if action == 'BUY':
                was_correct = now_price > then_price  # We bought, price went up = correct
            elif action in ('BLOCK', 'SKIP'):
                was_correct = now_price <= then_price  # We avoided, price went down = correct
            else:
                was_correct = None

            if was_correct is not None:
                pg._exec(
                    """UPDATE trade_decisions SET was_correct = %s, price_after_1h = %s WHERE id = %s""",
                    (was_correct, now_price, d['id'])
                )
                graded += 1

        log.info(f"  📝 Outcome grader: graded {graded}/{len(ungraded)} decisions")

        # Log accuracy stats
        if graded > 0:
            accuracy = pg.get_decision_accuracy(7)
            for action, stats in accuracy.items():
                total = stats.get('total', 0)
                correct = stats.get('correct', 0)
                if total > 0:
                    log.info(f"     {action}: {correct}/{total} correct ({correct/total*100:.0f}%)")

            # Notify dashboard
            pg.notify("Outcome Grader", f"Graded {graded} decisions",
                      severity='info', category='learning')

    except Exception as e:
        log.warning(f"Outcome grader error: {e}")

@outcome_grader.before_loop
async def before_grader():
    await bot.wait_until_ready()
    await asyncio.sleep(120)  # 2 min warmup (was 10 min — too long)


@tasks.loop(hours=24)
async def claude_daily_deep_learn():
    """Once per day (3 AM ET): Claude EXTREME deep analysis on all trends.
    Takes everything hourly learning found → asks Claude for playbook."""
    try:
        pg = _get_pg()
        if not pg or not brain:
            return

        now = datetime.now(ZoneInfo("America/New_York"))
        log.info(f"  🧠🌙 DAILY DEEP LEARN starting at {now.strftime('%I:%M %p ET')}")
        channel = bot.get_channel(SCAN_CHANNEL_ID)
        if channel:
            await channel.send("🧠🌙 **DAILY DEEP LEARNING** — Claude analyzing all historical trends...")

        def _gather_and_analyze():
            import json as _json

            log.info("  [DAILY LEARN] Step 1: Running backtests...")

            # ── STEP 1: BACKTEST — What strategies actually work? ──
            backtest_data = {}
            try:
                from backtester import BacktestEngine
                bt = BacktestEngine(pg)
                backtest_data['what_if'] = bt.replay_what_if()
                for sym in ['GOOGL', 'NVDA', 'AMD', 'TSLA', 'COIN', 'META'][:4]:
                    try:
                        backtest_data[sym] = bt.run_all_strategies(sym, 90)
                    except:
                        pass
                log.info(f"  [DAILY LEARN] Backtests done: {len(backtest_data)} results")
            except Exception as e:
                log.warning(f"  Backtest error: {e}")

            log.info("  [DAILY LEARN] Step 2: Gathering decision accuracy...")

            # ── STEP 2: SELF-GRADE — How accurate are we? ──
            decision_acc = pg.get_decision_accuracy(7)
            missed = pg.get_missed_trades(7)
            win_rates = pg.get_trade_win_rate(30)

            log.info("  [DAILY LEARN] Step 3: Gathering market data...")

            # ── STEP 3: ALL DATA ──
            earnings = pg.scan_all_earnings_patterns()
            trends = pg.get_trends()
            best = pg.get_best_performing_stocks(20)
            positions = gateway.get_positions()
            held = [{'symbol': p.symbol, 'qty': p.qty, 'entry': p.avg_entry,
                     'price': p.current_price, 'pnl': p.unrealized_pl} for p in positions]

            tv_summary = pg._exec(
                """SELECT symbol, COUNT(*) as readings,
                   AVG(rsi) as avg_rsi, AVG(macd_hist) as avg_macd,
                   SUM(CASE WHEN vwap_above THEN 1 ELSE 0 END) as above_vwap_count,
                   AVG(confluence) as avg_confluence
                FROM tv_readings WHERE created_at > NOW() - interval '24 hours'
                GROUP BY symbol ORDER BY readings DESC LIMIT 30""",
                fetch=True
            ) or []

            activity_summary = pg._exec(
                """SELECT action_type, COUNT(*) as cnt,
                   COUNT(DISTINCT symbol) as stocks
                FROM activity_log WHERE created_at > NOW() - interval '24 hours'
                GROUP BY action_type ORDER BY cnt DESC""",
                fetch=True
            ) or []

            tv_blocks = pg._exec(
                """SELECT symbol, reason, COUNT(*) as times_blocked
                FROM activity_log WHERE action_type = 'TV_BLOCKED' AND created_at > NOW() - interval '24 hours'
                GROUP BY symbol, reason ORDER BY times_blocked DESC LIMIT 10""",
                fetch=True
            ) or []

            sa = SentimentAnalyst()
            market = {}
            try:
                market = sa.full_market_sentiment()
            except:
                pass
            fg = {}
            try:
                fg = sa.get_fear_greed()
            except:
                pass

            log.info("  [DAILY LEARN] Step 4: Sending to AI for analysis...")

            # ── STEP 4: AI ANALYSIS with institutional frameworks ──
            prompt = f"""You are a senior portfolio manager at a top quantitative hedge fund.
The bot has been trading all day. Now at 3 AM, you must analyze EVERYTHING
and produce tomorrow's playbook. The bot will use your output ALL DAY tomorrow.

THIS IS THE SELF-LEARNING LOOP: Your insights become the bot's intelligence.

=== BACKTEST RESULTS (90-day historical simulation) ===
What-if scenarios (would different settings have made more money?):
{_json.dumps(backtest_data.get('what_if', {}), default=str)[:1500]}

Historical strategy performance on key stocks:
{_json.dumps({{k: v for k, v in backtest_data.items() if k != 'what_if'}}, default=str)[:2000]}

=== OUR DECISION ACCURACY (last 7 days) ===
{_json.dumps(decision_acc, default=str)[:500]}

=== MISSED OPPORTUNITIES (we blocked these but they went UP) ===
{_json.dumps(missed[:5], default=str)[:600]}

=== STRATEGY WIN RATES (30 days of actual trades) ===
{_json.dumps(win_rates, default=str)[:800]}

=== TODAY'S DATA ===
Positions: {_json.dumps(held, default=str)[:600]}
TV patterns: {_json.dumps(tv_summary[:10], default=str)[:600]}
Activity: {_json.dumps(activity_summary, default=str)[:400]}
Blocks: {_json.dumps(tv_blocks[:5], default=str)[:300]}
Earnings: {_json.dumps(earnings[:10], default=str)[:600]}
Market: {_json.dumps(market, default=str)[:300]}
VIX: {_json.dumps(fg, default=str)[:150]}
Trends: {_json.dumps([{{'s': t.get('symbol'), 'i': t.get('insight','')[:50]}} for t in trends[:10]], default=str)[:600]}

=== USE THESE FRAMEWORKS ===
1. BUFFETT: Moat, quality, hold winners. Which stocks have durable advantages?
2. LYNCH: P/E growth, categorize each stock (stalwart/fast grower/turnaround)
3. DALIO: Where in the cycle? Risk parity across sectors?
4. LIVERMORE: Follow the trend. Only trade with the market direction.
5. CANSLIM: Earnings growth + new products + institutional buying?
6. MOMENTUM: Which stocks are winning? Don't fight the tape.
7. MEAN REVERSION: Oversold bounces? RSI<30 setups for tomorrow?
8. OUR BACKTESTS: Which strategy wins on which stock? Use the data above.
9. MISSED TRADES: What should we change to not miss winners?
10. RISK: Correlation risk? Too concentrated in one sector?

=== OUTPUT (valid JSON) ===
{{"buy_list": [{{"symbol": "X", "reason": "why (cite framework + backtest data)", "confidence": 80, "strategy": "best backtest strategy for this stock"}}],
  "avoid_list": [{{"symbol": "X", "reason": "why (cite framework)"}}],
  "sector_signal": "rotation analysis",
  "earnings_plays": [{{"symbol": "X", "play": "specific play with entry/exit"}}],
  "risk_alerts": ["specific risks"],
  "tomorrow_strategy": "detailed playbook based on backtests + frameworks",
  "key_insight": "most important discovery from the data",
  "tv_learnings": "what TV patterns predict moves",
  "missed_opportunities": "what settings to change (from what-if analysis)",
  "strategy_adjustments": "which strategies to use more/less based on win rates",
  "position_sizing": "which stocks deserve bigger positions based on backtest win rates"}}"""

            try:
                if brain._claude_available:
                    import requests
                    resp = requests.post(
                        f"{os.getenv('AI_API_URL', 'https://ai.beast-trader.com')}/analyze",
                        json={'prompt': prompt, 'system_prompt': 'Senior quant PM. Self-learning trading bot. Your output becomes the bot intelligence for tomorrow. Be specific with numbers. Output valid JSON only.'},
                        headers={'X-API-Key': os.getenv('AI_API_KEY', ''), 'Content-Type': 'application/json'},
                        timeout=120)
                    if resp.status_code == 200:
                        log.info("  [DAILY LEARN] Claude analysis complete")
                        return resp.json()
                if brain._gpt_available:
                    log.info("  [DAILY LEARN] Using GPT-5.4 fallback")
                    return brain.analyze_stock('PORTFOLIO', {'deep_analysis_prompt': prompt})
            except Exception as e:
                log.warning(f"Claude daily: {e}")
            return {}

        insights = await asyncio.to_thread(_gather_and_analyze)
        if not insights:
            return

        import json as _json
        # Store playbook
        pg.save_trend('PORTFOLIO', 'daily_playbook', _json.dumps(insights, default=str)[:2000], 80, insights)

        # Store buy/avoid/earnings recommendations
        for b in (insights.get('buy_list') or [])[:5]:
            if isinstance(b, dict) and b.get('symbol'):
                pg.save_trend(b['symbol'], 'claude_daily_buy', str(b.get('reason', ''))[:500], b.get('confidence', 60), b)
        for a in (insights.get('avoid_list') or [])[:3]:
            if isinstance(a, dict) and a.get('symbol'):
                pg.save_trend(a['symbol'], 'claude_daily_avoid', str(a.get('reason', ''))[:500], 80, a)
        for p in (insights.get('earnings_plays') or [])[:5]:
            if isinstance(p, dict) and p.get('symbol'):
                pg.save_trend(p['symbol'], 'earnings_play', str(p.get('play', ''))[:500], p.get('confidence', 60), p)
        if insights.get('sector_signal'):
            pg.save_trend('MARKET', 'sector_rotation', str(insights['sector_signal'])[:500], 70)
        # Store TV learnings (patterns discovered from today's indicators)
        if insights.get('tv_learnings'):
            pg.save_trend('MARKET', 'tv_daily_report', str(insights['tv_learnings'])[:500], 75)
        # Store missed opportunities (so we don't miss them again)
        if insights.get('missed_opportunities'):
            pg.save_trend('MARKET', 'missed_opps', str(insights['missed_opportunities'])[:500], 65)

        pg.log_activity('DAILY_LEARN', category='ai', reason=f"Deep learn: {len(insights.get('buy_list', []))} buys, {len(insights.get('avoid_list', []))} avoids", source='daily_claude', data=insights)

        # Report
        if channel:
            msg = "🧠🌙 **DAILY DEEP LEARNING COMPLETE**\n\n"
            for b in (insights.get('buy_list') or [])[:5]:
                if isinstance(b, dict):
                    msg += f"🟢 **{b.get('symbol','?')}** ({b.get('confidence',0)}%) — {str(b.get('reason',''))[:80]}\n"
            for a in (insights.get('avoid_list') or [])[:3]:
                if isinstance(a, dict):
                    msg += f"🔴 **{a.get('symbol','?')}** — {str(a.get('reason',''))[:80]}\n"
            if insights.get('key_insight'):
                msg += f"\n💡 {str(insights['key_insight'])[:200]}"
            if insights.get('tv_learnings'):
                msg += f"\n📺 TV: {str(insights['tv_learnings'])[:150]}"
            if insights.get('missed_opportunities'):
                msg += f"\n😤 Missed: {str(insights['missed_opportunities'])[:150]}"
            await channel.send(msg[:2000])

        log.info(f"  🧠🌙 Daily learn complete")

        # ── 3 AM DAILY FLUSH: clear intraday data, keep trends ──
        try:
            log.info("  🧹 3 AM flush: clearing intraday TV readings + position snapshots")
            # Flush TV readings (intraday only — trend data stays in ai_trends)
            pg._exec("DELETE FROM tv_readings WHERE created_at < NOW() - interval '24 hours'")
            # Flush position snapshots older than 2 days (equity curve keeps 15 days)
            pg._exec("DELETE FROM position_snapshots WHERE created_at < NOW() - interval '2 days'")
            # Flush old activity log entries (keep 7 days for debugging)
            pg._exec("DELETE FROM activity_log WHERE created_at < NOW() - interval '7 days'")
            # Flush old scan results (keep 3 days)
            pg._exec("DELETE FROM scan_results WHERE created_at < NOW() - interval '3 days'")
            # Flush login attempts older than 7 days
            pg._exec("DELETE FROM login_attempts WHERE timestamp < NOW() - interval '7 days'")
            # Clear intraday price cache (start fresh)
            global _prev_prices, _tv_cache
            # Keep past winner flags and runner flags, clear everything else
            keep_keys = {k for k in _prev_prices if k.startswith('_hi_') or k.startswith('_intraday')}
            for k in list(_prev_prices.keys()):
                if k not in keep_keys:
                    del _prev_prices[k]
            _tv_cache.clear()
            
            pg.log_activity('DAILY_FLUSH', category='system',
                reason='3AM flush: TV readings, old snapshots, activity >7d, scan results >3d, price cache cleared',
                source='daily')
            log.info("  🧹 3 AM flush complete — fresh start for new trading day")
            
            if channel:
                await channel.send("🧹 **3 AM DAILY FLUSH** — cleared intraday data. Fresh start for tomorrow. Trends preserved.")
        except Exception as e:
            log.warning(f"Daily flush error: {e}")

    except Exception as e:
        log.error(f"Daily learn error: {e}\n{traceback.format_exc()}")


@claude_daily_deep_learn.before_loop
async def before_daily_learn():
    await bot.wait_until_ready()
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.hour >= 3:
        target = now.replace(hour=3, minute=0, second=0) + timedelta(days=1)
    else:
        target = now.replace(hour=3, minute=0, second=0)
    wait_secs = (target - now).total_seconds()
    log.info(f"   🧠 Daily deep learn: {target.strftime('%I:%M %p ET')} ({wait_secs/3600:.1f}h)")
    await asyncio.sleep(wait_secs)


# ══════════════════════════════════════════════════════════
#  AFTER-HOURS / PRE-MARKET EARNINGS SCANNER
#  Runs every 15 min during extended hours (4-8 PM, 4-9:30 AM)
#  Catches: earnings movers, AH gaps, PM setups
#  Stores patterns to DB for the bot to use at market open
# ══════════════════════════════════════════════════════════

@tasks.loop(minutes=15)
async def ah_pm_scanner():
    """Every 15 min during extended hours: scan for earnings movers + gaps.
    META dropped -9% AH on earnings - this scanner catches that and stores the pattern.
    Pre-market: catches gap ups/downs before open so the bot is ready."""
    try:
        if _is_market_hours():
            return  # Only run during extended hours

        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
        if now.weekday() >= 5:
            return  # Skip weekends

        # Only run 4 PM - 8 PM ET (after hours) and 4 AM - 9:30 AM ET (pre-market)
        is_ah = 16 <= now.hour < 20
        is_pm = 4 <= now.hour < 10
        if not is_ah and not is_pm:
            return

        session = "AH" if is_ah else "PM"
        pg = _get_pg()
        channel = bot.get_channel(SCAN_CHANNEL_ID)

        log.info(f"  🌙 {session} Scanner: checking earnings movers + gaps...")

        # Get all held positions + top watchlist stocks
        positions = gateway.get_positions()
        held_syms = [p.symbol for p in positions]
        watch_syms = PAST_WINNERS[:20]
        all_syms = list(set(held_syms + watch_syms))

        # Get current vs previous close for all stocks
        movers = []
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockSnapshotRequest
            dc = StockHistoricalDataClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'))

            for batch_start in range(0, len(all_syms), 20):
                batch = all_syms[batch_start:batch_start + 20]
                try:
                    snaps = dc.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=batch, feed='iex'))
                    for sym, s in snaps.items():
                        try:
                            price = float(s.latest_trade.price)
                            prev = float(s.previous_daily_bar.close)
                            pct = (price - prev) / prev * 100
                            vol = int(s.daily_bar.volume) if s.daily_bar else 0
                            if abs(pct) > 2:  # >2% move in AH/PM = significant
                                movers.append({
                                    'symbol': sym, 'price': price, 'prev': prev,
                                    'pct': round(pct, 2), 'volume': vol,
                                    'session': session, 'held': sym in held_syms,
                                })
                        except:
                            pass
                except:
                    pass
        except Exception as e:
            log.warning(f"  {session} scanner price fetch: {e}")
            return

        if not movers:
            log.info(f"  🌙 {session} Scanner: no significant movers")
            return

        movers.sort(key=lambda x: -abs(x['pct']))
        log.info(f"  🌙 {session} Scanner: {len(movers)} stocks moved >2%")

        # Store each mover as a pattern in ai_trends
        if pg:
            for m in movers[:10]:
                sym = m['symbol']
                direction = "UP" if m['pct'] > 0 else "DOWN"
                # Check if this is an earnings move (use yfinance)
                is_earnings = False
                try:
                    sa = SentimentAnalyst()
                    earn = sa.get_earnings_info(sym)
                    if earn.get('days_until', 999) <= 1:
                        is_earnings = True
                except:
                    pass

                if is_earnings:
                    trend_type = f'{session.lower()}_earnings_move'
                    insight = f"{sym} {direction} {abs(m['pct']):.1f}% on earnings in {session}. Prev close ${m['prev']:.2f} -> ${m['price']:.2f}"
                    pg.save_trend(sym, trend_type, insight, 85, m)
                    # Store earnings pattern for long-term learning
                    pg._exec(
                        """INSERT INTO earnings_patterns (symbol, earnings_date, pre_price, post_price, beat_or_miss, gap_pct)
                           VALUES (%s, CURRENT_DATE, %s, %s, %s, %s)
                           ON CONFLICT DO NOTHING""",
                        (sym, m['prev'], m['price'], 'beat' if m['pct'] > 0 else 'miss', m['pct'])
                    )
                    log.info(f"  🌙 EARNINGS: {sym} {direction} {abs(m['pct']):.1f}% in {session} - STORED to earnings_patterns")
                else:
                    trend_type = f'{session.lower()}_gap'
                    insight = f"{sym} {direction} {abs(m['pct']):.1f}% in {session}. Vol: {m['volume']:,}"
                    pg.save_trend(sym, trend_type, insight, 70, m)
                    log.info(f"  🌙 GAP: {sym} {direction} {abs(m['pct']):.1f}% in {session}")

                # Add to watchlist if not already there
                pg.add_to_watchlist(sym, source=f'{session}_mover', pct=m['pct'], volume=m['volume'])

            # Notify via Discord
            if channel and movers:
                msg = f"🌙 **{session} SCANNER** - {now.strftime('%I:%M %p ET')}\n\n"
                for m in movers[:8]:
                    icon = "🟢" if m['pct'] > 0 else "🔴"
                    held_tag = " (HELD)" if m['held'] else ""
                    msg += f"{icon} **{m['symbol']}** {m['pct']:+.1f}% @ ${m['price']:.2f}{held_tag}\n"
                msg += f"\n_Patterns stored for tomorrow's trading_"
                await channel.send(msg[:2000])

            # Telegram alert for big movers
            big_movers = [m for m in movers if abs(m['pct']) > 5]
            if big_movers:
                tg_msg = f"🌙 {session} BIG MOVERS:\n"
                for m in big_movers[:5]:
                    tg_msg += f"{'🟢' if m['pct']>0 else '🔴'} {m['symbol']} {m['pct']:+.1f}%\n"
                _tg(tg_msg)

        _pg_log(f"{session}_SCAN", reason=f"{len(movers)} movers found >2%",
                source=f"{session.lower()}_scanner",
                data={'movers': [m['symbol'] for m in movers[:10]]})

    except Exception as e:
        log.warning(f"AH/PM scanner error: {e}")

@ah_pm_scanner.before_loop
async def before_ah_pm():
    await bot.wait_until_ready()
    await asyncio.sleep(60)


# ══════════════════════════════════════════════════════════
#  FILL TRACKER: Monitors order fills, records realized P&L
#  Runs every 5 min, checks Alpaca for recently filled orders
#  Stores profit/loss per trade for the learning engine
# ══════════════════════════════════════════════════════════

@tasks.loop(minutes=5)
async def fill_tracker():
    """Every 5 min: check for filled orders and record realized P&L.
    This closes the learning loop: buy→fill→sell→fill→profit/loss recorded."""
    try:
        pg = _get_pg()
        if not pg:
            return

        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        def _check_fills():
            try:
                req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=20)
                orders = gateway.client.get_orders(req)
                fills = []
                for o in orders:
                    if o.filled_at and o.status.value == 'filled':
                        # Check if we already logged this fill
                        fill_key = f"fill_{o.id}"
                        if pg.get_state(fill_key):
                            continue

                        filled_price = float(o.filled_avg_price) if o.filled_avg_price else 0
                        qty = int(float(o.filled_qty)) if o.filled_qty else 0
                        side = o.side.value if o.side else 'unknown'
                        sym = o.symbol

                        # Calculate realized P&L for sells
                        realized_pnl = None
                        if side == 'sell' and filled_price > 0:
                            # Check price_memory for entry price
                            mem = pg.get_price_memory(sym)
                            buy_price = mem.get('last_buy_price', 0)
                            if buy_price and buy_price > 0:
                                realized_pnl = (filled_price - buy_price) * qty

                        fills.append({
                            'order_id': str(o.id),
                            'symbol': sym,
                            'side': side,
                            'qty': qty,
                            'filled_price': filled_price,
                            'filled_at': str(o.filled_at),
                            'realized_pnl': realized_pnl,
                            'order_type': o.type.value if o.type else 'unknown',
                            'client_order_id': str(o.client_order_id or ''),
                        })

                        # Mark as processed
                        pg.set_state(fill_key, True, 'fills')

                        # Record sell in price memory
                        if side == 'sell':
                            pg.record_sell(sym, filled_price)

                        # Update trade_log if we have a matching entry
                        if realized_pnl is not None:
                            pg._exec(
                                """UPDATE trade_log SET filled_price = %s, filled_at = NOW(),
                                   pnl_eod = %s, was_profitable = %s
                                   WHERE id = (
                                       SELECT id FROM trade_log
                                       WHERE symbol = %s AND side = 'buy' AND filled_price IS NULL
                                       ORDER BY created_at DESC LIMIT 1
                                   )""",
                                (filled_price, realized_pnl, realized_pnl > 0, sym)
                            )

                        # Update session stats
                        pg.update_session_stats(trades=1, pnl=realized_pnl or 0)

                return fills
            except Exception as e:
                log.warning(f"Fill tracker error: {e}")
                return []

        fills = await asyncio.to_thread(_check_fills)

        if fills:
            log.info(f"  💰 Fill tracker: {len(fills)} new fills")
            channel = bot.get_channel(SCAN_CHANNEL_ID)
            for f in fills:
                pnl_str = ""
                if f['realized_pnl'] is not None:
                    pnl_str = f" | P&L: ${f['realized_pnl']:+.2f}"
                log.info(f"    FILLED: {f['side'].upper()} {f['symbol']} {f['qty']}x @${f['filled_price']:.2f}{pnl_str}")

                # Log to activity
                _pg_log("FILL", symbol=f['symbol'], side=f['side'], qty=f['qty'],
                        price=f['filled_price'], reason=f"Order filled{pnl_str}",
                        source="fill_tracker", data=f)

                # Notify dashboard
                if pg:
                    severity = 'success' if (f['realized_pnl'] or 0) >= 0 else 'warning'
                    pg.notify(
                        f"FILLED: {f['side'].upper()} {f['symbol']}",
                        f"{f['qty']}x @${f['filled_price']:.2f}{pnl_str}",
                        severity=severity, symbol=f['symbol'], category='fill')

                # Discord alert for realized P&L
                if channel and f['realized_pnl'] is not None:
                    icon = "💰" if f['realized_pnl'] > 0 else "💸"
                    await channel.send(
                        f"{icon} **REALIZED: {f['symbol']}** "
                        f"Sold {f['qty']}x @${f['filled_price']:.2f} "
                        f"— P&L: **${f['realized_pnl']:+.2f}**")

    except Exception as e:
        log.warning(f"Fill tracker error: {e}")

@fill_tracker.before_loop
async def before_fill_tracker():
    await bot.wait_until_ready()
    await asyncio.sleep(120)


@bot.event
async def on_ready():
    log.info(f"🦍 Beast Discord Bot online as {bot.user}")
    log.info(f"   Build: {BOT_BUILD}")
    log.info(f"   AI Brain: {'✅ Opus 4.7' if brain and brain.is_available else '❌ offline'}")
    tv_ok = False
    try:
        from tv_cdp_client import TVClient
        tv_ok = TVClient().health_check()
    except:
        pass
    log.info(f"   TradingView: {'✅' if tv_ok else '❌'}")
    pg = _get_pg()
    pg_ok = pg and pg.conn
    log.info(f"   PostgreSQL: {'✅' if pg_ok else '❌'}")
    log.info(f"   Watchlist: {len(DIP_BUY_WATCHLIST)} stocks")

    # Register this bot session in DB (tracks version, uptime, crashes)
    if pg:
        try:
            session_id = pg.start_session(
                build_version=BOT_BUILD,
                git_hash=_git_hash,
                loops_config={
                    'position_monitor': '60s', 'fast_runner': '2min', 'full_scan': '5min',
                    'decision_report': '10min', 'claude_deep': '30min', 'outcome_grader': '30min',
                    'ah_pm_scanner': '15min', 'bg_learning': '1hr', 'daily_learn': '3AM',
                }
            )
            log.info(f"   📦 Bot session #{session_id} started")
        except Exception as e:
            log.warning(f"   Session start failed: {e}")

    if not position_monitor.is_running():
        position_monitor.start()
        log.info("   ✅ Position monitor: every 60s (auto-scalp + auto-buy dips)")
    if not full_scan.is_running():
        full_scan.start()
        log.info("   ✅ Full scan: every 5 min (TV + sentiment + AI)")
    if not decision_report.is_running():
        decision_report.start()
        log.info("   ✅ Decision report: every 10 min")
    if not fast_runner_scan.is_running():
        fast_runner_scan.start()
        log.info("   ✅ Fast runner scan: every 2 min")
    if not claude_deep_scan.is_running():
        claude_deep_scan.start()
        log.info("   ✅ Claude deep scan: every 30 min")
    if not ai_background_learning.is_running():
        ai_background_learning.start()
        log.info("   ✅ AI background learning: every 1 hour (all watchlist stocks)")
    if not outcome_grader.is_running():
        outcome_grader.start()
        log.info("   ✅ Outcome grader: every 30 min (grades past decisions)")
    if not ah_pm_scanner.is_running():
        ah_pm_scanner.start()
        log.info("   ✅ AH/PM scanner: every 15 min (earnings movers + gaps)")
    if not fill_tracker.is_running():
        fill_tracker.start()
        log.info("   ✅ Fill tracker: every 5 min (realized P&L + session stats)")
    if not claude_daily_deep_learn.is_running():
        claude_daily_deep_learn.start()
        log.info("   ✅ Claude daily deep learn: once/day at 3 AM ET")

    channel = bot.get_channel(SCAN_CHANNEL_ID)
    if channel:
        await channel.send(
            f"🦍 **BEAST TERMINAL V4 ONLINE** `{BOT_BUILD}`\n"
            f"• 60s: Position monitor (scalp/dip-reload/pyramid)\n"
            f"• 2min: Market-wide runner scan (most_active API)\n"
            f"• 5min: Full scan (TV + sentiment + GPT-4o + auto-execute)\n"
            f"• 10min: Decision report\n"
            f"• 30min: Claude MEGA-SCAN (ultra-deep + auto-execute)\n"
            f"• AI: {'GPT-4o ✅' if brain and brain._gpt_available else '❌'} + {'Claude ✅' if brain and brain._claude_available else '❌'}\n"
            f"• TV: {'Connected ✅' if tv_ok else 'Offline ❌'} (HARD LAW: no TV = no buy)\n"
            f"• Watchlist: {len(DIP_BUY_WATCHLIST)} stocks (from PostgreSQL)\n"
            f"• Auto-execute: ≥75% confidence\n"
            f"• Smart Buy: TV→SelfLearn→VIX→Execute\n"
            f"• Trading: 4AM-8PM ET (pre+market+post)"
        )


# ── Run ────────────────────────────────────────────────

if __name__ == '__main__':
    import asyncio
    token = os.getenv('DISCORD_BOT_TOKEN', '')
    if not token:
        print("❌ DISCORD_BOT_TOKEN not set in .env")
        sys.exit(1)
    print("🦍 Starting Beast Discord Bot with Autonomous Loop...")
    bot.run(token)
