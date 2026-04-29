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
import discord
from discord.ext import commands, tasks
from datetime import datetime
from zoneinfo import ZoneInfo

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
_last_full_scan = 0
_tv_client = None

# Watchlist for auto-buy dips (Akash Method)
DIP_BUY_WATCHLIST = ['AAPL', 'AMZN', 'GOOGL', 'META', 'MSFT', 'NVDA', 'TSLA',
                     'AMD', 'TSM', 'INTC', 'CRM', 'PLTR', 'OXY', 'DVN', 'LMT',
                     'SOFI', 'COIN', 'ROKU', 'SQ', 'SNAP', 'UBER', 'SHOP',
                     'MU', 'MRVL', 'ARM', 'SMCI', 'NOK', 'PLUG', 'NIO', 'RIVN']

# Past winners — scan these FIRST (Phase 0, Rule #21)
PAST_WINNERS = ['NOK', 'GOOGL', 'CRM', 'META', 'MSFT', 'NOW', 'AMD', 'NVDA',
                'OXY', 'DVN', 'INTC', 'ORCL', 'MSTR', 'COIN', 'HOOD']

# Rule #29: Don't chase stocks already up >5% WITHOUT catalyst
# NOK +18% with NVIDIA deal = OK. Random +5% no news = BLOCK.
MAX_CHASE_PCT = 5.0
CATALYST_SENTIMENT_THRESHOLD = 3  # sentiment >= +3 = has catalyst, allow chase

# Law 9: Max simultaneous scalp positions (< 2% profit)
MAX_ACTIVE_SCALPS = 3

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
        time.sleep(5)  # Wait for chart + indicators to load

        # Read study values — retry if only Volume shows up or values look stale
        studies = _tv_client.get_study_values()
        study_names = [s.get('name', '?') for s in (studies or [])]

        # Staleness check: if we only got Volume or less than 3 studies, wait and retry
        retries = 0
        while len(studies or []) <= 3 and retries < 2:
            retries += 1
            time.sleep(3)
            studies = _tv_client.get_study_values()
            study_names = [s.get('name', '?') for s in (studies or [])]
            log.debug(f"  TV {symbol} retry {retries}: {len(studies)} studies")

        if not studies:
            log.debug(f"  TV: no study values for {symbol}")
            return {}

        log.info(f"  TV {symbol} raw studies ({len(studies)}): {study_names}")

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

def _pct(p) -> float:
    """Position P&L percentage."""
    cost = p.avg_entry * p.qty
    return (p.unrealized_pl / cost * 100) if cost > 0 else 0

# Trade action log — tracks all auto-trades for reporting + persists to DB
_trade_log = []
_trade_db = None

def _get_trade_db():
    global _trade_db
    if _trade_db is None:
        try:
            from trade_db import TradeDB
            _trade_db = TradeDB()
        except Exception as e:
            log.warning(f"TradeDB init failed: {e}")
    return _trade_db

def _log_trade(action, symbol, qty, price, reason, scan_type="60s"):
    """Log a trade action to memory + SQLite database."""
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
    # Persist to SQLite
    db = _get_trade_db()
    if db:
        try:
            side = 'sell' if 'SELL' in action.upper() else 'buy'
            if side == 'buy':
                db.log_entry(symbol=symbol, qty=qty, price=price,
                            strategy=scan_type, reason=f"{action}: {reason}")
            else:
                db.log_entry(symbol=symbol, qty=qty, price=price,
                            strategy=scan_type, reason=f"{action}: {reason}")
        except Exception as e:
            log.debug(f"Trade DB write failed: {e}")

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


@tasks.loop(seconds=60)
async def position_monitor():
    """Every 60s: check positions, alert drops, auto-scalp, auto-protect, auto-buy dips."""
    global _prev_prices, _cycle_count
    _cycle_count += 1
    try:
        positions = gateway.get_positions()
        if not positions:
            return
        channel = bot.get_channel(SCAN_CHANNEL_ID)
        total_pl = sum(p.unrealized_pl for p in positions)
        greens = sum(1 for p in positions if p.unrealized_pl >= 0)
        held_symbols = {p.symbol for p in positions}

        # ── AUTO-PROTECT: place 3% trailing stop on any unprotected position ──
        if _is_market_hours() and _cycle_count % 3 == 0:
            try:
                open_orders = await asyncio.to_thread(gateway.get_open_orders)
                # Build set of symbols that already have trailing stops
                protected = set()
                for o in open_orders:
                    if 'trailing' in str(o.get('type', '')).lower() or 'trail' in str(o.get('client_order_id', '')).lower():
                        protected.add(o.get('symbol', ''))
                for p in positions:
                    if p.symbol not in protected and p.qty_available and p.qty_available > 0:
                        try:
                            trail_qty = p.qty_available
                            gateway.place_trailing_stop(p.symbol, trail_qty, trail_percent=3.0,
                                                        reason="Auto-protect (no trailing stop found)",
                                                        entry_price=p.avg_entry)
                            _log_trade("TRAILING STOP (Auto-Protect)", p.symbol, trail_qty, 0,
                                       f"3% trail on {trail_qty} unprotected shares", "60s Monitor")
                            if channel:
                                await channel.send(
                                    f"🛡️ **[60s] AUTO-PROTECT: {p.symbol}** — 3% trailing stop on {trail_qty} shares\n"
                                    f"No existing trailing stop found. Protecting against downside.")
                            log.info(f"  🛡️ Auto-protect: {p.symbol} {trail_qty} shares with 3% trail")
                        except Exception as e:
                            log.debug(f"Auto-protect {p.symbol}: {e}")
            except Exception as e:
                log.debug(f"Auto-protect scan: {e}")

        for p in positions:
            prev = _prev_prices.get(p.symbol, p.current_price)
            pct = _pct(p)

            # ── AUTO-RUNNER: +5% → sell half (only if shares available) ──
            if pct >= 5.0 and not _prev_prices.get(f"_runner_{p.symbol}") and _is_market_hours():
                avail = p.qty_available or 0
                half = max(1, min(avail, p.qty // 2))
                if avail < 1:
                    log.info(f"  {p.symbol} +{pct:.1f}% runner but 0 shares available (held by orders)")
                else:
                    try:
                        sell_price = round(p.current_price * 0.999, 2)
                        gateway.place_sell(p.symbol, half, sell_price,
                                          reason=f"Auto-runner +{pct:.1f}%")
                        _prev_prices[f"_runner_{p.symbol}"] = True
                        _log_trade("LIMIT SELL (Runner)", p.symbol, half, sell_price,
                                   f"+{pct:.1f}% runner — selling {half} to lock profit.", "60s Monitor")
                        if channel:
                            await channel.send(
                                f"🏃 **[60s] AUTO-RUNNER: {p.symbol}** +{pct:.1f}%\n"
                                f"Selling {half}/{p.qty} shares @ ${sell_price} (avail: {avail})")
                    except Exception as e:
                        log.error(f"Auto-runner failed {p.symbol}: {e}")

            # ── AUTO-SCALP: +2% → limit sell half (only if shares available) ──
            elif pct >= 2.0 and not _prev_prices.get(f"_scalp_{p.symbol}") and _is_market_hours():
                avail = p.qty_available or 0
                half = max(1, min(avail, p.qty // 2))
                if avail < 1:
                    log.info(f"  {p.symbol} +{pct:.1f}% scalp but 0 shares available (held by orders)")
                else:
                    try:
                        sell_price = round(p.avg_entry * 1.025, 2)
                        sell_price = max(sell_price, round(p.current_price * 1.005, 2))
                        gateway.place_sell(p.symbol, half, sell_price,
                                          reason=f"Auto-scalp +{pct:.1f}%")
                        _prev_prices[f"_scalp_{p.symbol}"] = True
                        _log_trade("LIMIT SELL (Scalp)", p.symbol, half, sell_price,
                                   f"+{pct:.1f}% scalp target hit. Selling {half}, keeping rest.", "60s Monitor")
                        if channel:
                            await channel.send(
                                f"🎯 **[60s] AUTO-SCALP: {p.symbol}** +{pct:.1f}%\n"
                                f"Selling {half}/{p.qty} shares @ ${sell_price} (avail: {avail})")
                    except Exception as e:
                        log.error(f"Auto-scalp failed {p.symbol}: {e}")

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

        # ── LAW 9: Count active scalps (positions < +2%) ──
        active_scalps = sum(1 for p in positions if 0 < _pct(p) < 2.0)

        # ── AUTO-BUY DIPS (Akash Method) ──
        if _is_market_hours() and _cycle_count % 5 == 0:
            # Law 9: Max 3 active scalps at a time
            if active_scalps >= MAX_ACTIVE_SCALPS:
                log.info(f"  Law 9: {active_scalps} active scalps (max {MAX_ACTIVE_SCALPS}). Skipping new buys.")
            else:
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
                                    gateway.quick_buy(sym, qty, buy_price,
                                                      reason=f"Akash Method: {day_change:+.1f}% dip",
                                                      day_change_pct=day_change)
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

        # ── PHASE 0: Past Winners scan (Rule #21) ──
        if _is_market_hours() and _cycle_count % 10 == 0 and active_scalps < MAX_ACTIVE_SCALPS:
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
                        except:
                            pass
            except Exception as e:
                log.debug(f"Phase 0 scan: {e}")

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
    except Exception as e:
        log.error(f"Position monitor error: {e}")


@tasks.loop(minutes=5)
async def full_scan():
    """Every 5 min: MANDATORY full scan — TV + ALL sentiment + confidence engine + AI.
    NO EXCEPTIONS. Every source runs. Confidence is generated. AI analyzes AFTER data."""
    global _last_full_scan
    try:
        channel = bot.get_channel(SCAN_CHANNEL_ID)
        if not channel:
            return

        import asyncio
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))

        # ── Skip off-hours (midnight to 4 AM) ──
        if now.hour < 4 or now.hour >= 20:
            return

        positions = gateway.get_positions()
        acct = gateway.get_account()
        equity = float(acct.get('equity', 100000))
        total_pl = sum(p.unrealized_pl for p in positions)
        greens = sum(1 for p in positions if p.unrealized_pl >= 0)
        held = [p.symbol for p in positions]

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
        # ══════════════════════════════════════════════════

        # ── STEP 1: TV INDICATORS (MANDATORY) ──
        tv_data = {}
        def _read_all_tv(syms):
            d = {}
            for sym in syms:
                ind = _get_tv_indicators(sym)
                if ind:
                    d[sym] = ind
                    log.info(f"  TV {sym}: RSI={ind.get('rsi','?'):.0f} MACD={ind.get('macd_hist','?')} VWAP={'above' if ind.get('vwap_above') else 'BELOW'}")
            return d
        tv_data = await asyncio.to_thread(_read_all_tv, held[:10])
        log.info(f"  TV: read {len(tv_data)}/{len(held)} stocks")

        # ── STEP 2: ALL SENTIMENT (MANDATORY — 5 sources) ──
        sentiments = {}
        trump_score = 0
        trump_headlines = []
        def _read_all_sentiment(syms):
            from sentiment_analyst import SentimentAnalyst
            sa = SentimentAnalyst()
            results = {}
            # Per-stock sentiment (Yahoo + Reddit + Analyst)
            for sym in syms:
                try:
                    results[sym] = sa.analyze(sym)
                except Exception as e:
                    log.warning(f"  Sentiment {sym} failed: {e}")
            # Trump/tariff/geopolitical (Google News RSS — NO API KEY)
            try:
                t_score, t_headlines = sa.get_trump_sentiment()
                results['_trump'] = {'score': t_score, 'headlines': t_headlines}
            except Exception as e:
                log.warning(f"  Trump sentiment failed: {e}")
            # Market-wide sentiment
            try:
                results['_market'] = sa.analyze_market()
            except:
                pass
            return results
        sent_raw = await asyncio.to_thread(_read_all_sentiment, held[:10])
        # Extract trump data
        trump_info = sent_raw.pop('_trump', {})
        trump_score = trump_info.get('score', 0)
        trump_headlines = trump_info.get('headlines', [])
        market_sent = sent_raw.pop('_market', None)
        sentiments = sent_raw
        log.info(f"  Sentiment: {len(sentiments)} stocks | Trump: {trump_score:+d} | Headlines: {len(trump_headlines)}")

        # ── STEP 3: CONFIDENCE ENGINE (11 strategies, MANDATORY) ──
        confidence_results = {}
        def _run_confidence(syms, tv_d, sent_d, reg):
            from engine.confidence_engine import ConfidenceEngine
            from models import TechnicalSignals
            ce = ConfidenceEngine()
            results = {}
            for sym in syms:
                tv = tv_d.get(sym, {})
                sent = sent_d.get(sym)
                pos = next((p for p in positions if p.symbol == sym), None)
                price = pos.current_price if pos else 0
                # Build TechnicalSignals from TV data
                # VWAP is meaningless outside market hours — default to neutral
                vwap_val = 0.0  # neutral default for extended hours
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
            return results
        confidence_results = await asyncio.to_thread(_run_confidence, held[:10], tv_data, sentiments, regime)
        log.info(f"  Confidence: {len(confidence_results)} scored")

        # ── OPEN ORDERS ──
        open_orders = await asyncio.to_thread(gateway.get_open_orders)

        # ── STEP 4: AI ANALYSIS (AFTER all data collected) ──
        ai_verdicts = {}
        if brain and brain.is_available:
            def _run_ai_final(pos_list, sent_d, tv_d, conf_d, regime_val, t_score):
                results = {}
                for pos in pos_list:
                    try:
                        sym = pos.symbol
                        sent = sent_d.get(sym)
                        tv = tv_d.get(sym, {})
                        cr = conf_d.get(sym)
                        conf_pct = int(cr.overall_confidence * 100) if cr else 50
                        best_strat = cr.best_strategy.value if cr and cr.best_strategy else 'none'
                        signal = cr.signal.value if cr else 'no_trade'
                        data = {
                            'price': pos.current_price, 'entry': pos.avg_entry,
                            'pnl': pos.unrealized_pl, 'qty': pos.qty,
                            'regime': regime_val,
                            'sentiment': sent.total_score if sent else 0,
                            'rsi': tv.get('rsi', 50),
                            'macd_hist': tv.get('macd_hist', 0),
                            'vwap_above': tv.get('vwap_above', False),
                            'volume_ratio': tv.get('volume_ratio', 1.0),
                            'bb_position': tv.get('bb_position', 'mid'),
                            'confluence': tv.get('confluence', 5),
                            'ema_9': tv.get('ema_9', 0),
                            'ema_21': tv.get('ema_21', 0),
                            'yahoo_score': sent.yahoo_score if sent else 0,
                            'analyst_score': sent.analyst_score if sent else 0,
                            'reddit_score': sent.reddit_score if sent else 0,
                            'trump_score': t_score,
                            'confidence_engine': conf_pct,
                            'best_strategy': best_strat,
                            'signal': signal,
                            'sector': '?', 'earnings_days': 999, 'holding': True,
                            'unrealized_pl': pos.unrealized_pl,
                        }
                        results[sym] = brain.analyze_stock(sym, data)
                    except:
                        pass
                return results
            ai_verdicts = await asyncio.to_thread(
                _run_ai_final, positions[:8], sentiments, tv_data,
                confidence_results, regime.value, trump_score
            )
        log.info(f"  AI: {len(ai_verdicts)} analyzed")

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
        log.info(f"Full scan sent at {now.strftime('%H:%M')} [TV:{len(tv_data)} AI:{len(ai_verdicts)}]")

        # ── LOG TO DATABASE (scan log + equity curve + position snapshots) ──
        db = _get_trade_db()
        if db:
            try:
                conf_data = {sym: cr.overall_confidence for sym, cr in confidence_results.items()}
                db.log_scan(
                    regime=regime.value, spy_change=spy_change, equity=equity,
                    total_pl=total_pl, positions_count=len(positions),
                    tv_count=len(tv_data), sentiment_count=len(sentiments),
                    ai_count=len(ai_verdicts), trump_score=trump_score,
                    confidence_scores=conf_data
                )
                db.log_equity(equity, total_pl, len(positions))
                db.snapshot_positions(positions)
                log.info(f"  DB: scan + equity + snapshots logged")
            except Exception as e:
                log.debug(f"DB logging failed: {e}")

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
        if now.hour < 4 or now.hour >= 20:
            return

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


@tasks.loop(minutes=30)
async def claude_deep_scan():
    """Every 30 min: Claude Opus 4.7 ULTRA DEEP analysis on top positions.
    Produces Deep Intel Briefing that GPT-4o references in 5-min scans."""
    try:
        channel = bot.get_channel(SCAN_CHANNEL_ID)
        if not channel:
            return

        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
        if now.hour < 4 or now.hour >= 20:
            return

        if not brain or not brain.is_available:
            return

        positions = gateway.get_positions()
        if not positions:
            return

        # Pick top 5 positions by absolute P&L (most impactful)
        top = sorted(positions, key=lambda x: abs(x.unrealized_pl), reverse=True)[:5]

        # Gather data for Claude
        sentiments_data = {}
        def _get_sentiment_batch(syms):
            sa = SentimentAnalyst()
            for sym in syms:
                try:
                    sentiments_data[sym] = sa.full_stock_intel(sym)
                except:
                    pass
        await asyncio.to_thread(_get_sentiment_batch, [p.symbol for p in top])

        # Run Claude deep analysis
        deep_results = {}
        def _run_claude_deep(pos_list):
            for pos in pos_list:
                try:
                    sym = pos.symbol
                    intel = sentiments_data.get(sym, {})
                    data = {
                        'price': pos.current_price, 'entry': pos.avg_entry,
                        'pnl': pos.unrealized_pl, 'qty': pos.qty,
                        'sentiment': intel.get('total_sentiment', 0),
                        'earnings_days': intel.get('earnings_days', 999),
                        'short_pct': intel.get('short_pct', 0),
                        'squeeze_risk': intel.get('squeeze_risk', False),
                        'holding': True, 'unrealized_pl': pos.unrealized_pl,
                    }
                    result = brain.deep_analysis(sym, data)
                    if result:
                        deep_results[sym] = result
                except Exception as e:
                    log.warning(f"Claude deep {pos.symbol}: {e}")
        await asyncio.to_thread(_run_claude_deep, top)

        if not deep_results:
            log.info("Claude deep scan: no results (Claude may be offline)")
            return

        # Send compact report
        embed = discord.Embed(
            title=f"🧠 CLAUDE DEEP INTEL — {now.strftime('%I:%M %p ET')}",
            description=f"Ultra-deep 30-min analysis on {len(deep_results)} positions",
            color=0x9B59B6
        )
        for sym, r in deep_results.items():
            action = r.get('action', 'HOLD')
            conf = r.get('confidence', 0)
            reasoning = r.get('reasoning', '')[:200]
            icon = "🟢" if action == 'BUY' else "🔴" if action == 'SELL' else "⚪"
            embed.add_field(
                name=f"{icon} {sym} — {action} ({conf}%)",
                value=reasoning or "No reasoning provided",
                inline=False
            )
        embed.set_footer(text=f"Source: Claude Opus 4.7 via ai.beast-trader.com | Next: {(now.hour*60+now.minute+30)//60}:{(now.minute+30)%60:02d}")
        await channel.send(embed=embed)

        # Telegram
        tg_msg = f"🧠 Claude Deep Intel {now.strftime('%I:%M %p')}\n"
        for sym, r in deep_results.items():
            tg_msg += f"{'🟢' if r.get('action')=='BUY' else '🔴' if r.get('action')=='SELL' else '⚪'} {sym}: {r.get('action')} ({r.get('confidence',0)}%)\n"
        _tg(tg_msg)

        log.info(f"Claude deep scan: {len(deep_results)} analyzed at {now.strftime('%H:%M')}")

    except Exception as e:
        log.error(f"Claude deep scan error: {e}\n{traceback.format_exc()}")


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

@claude_deep_scan.before_loop
async def before_claude():
    await bot.wait_until_ready()
    await asyncio.sleep(120)  # Wait 2 min — let first full_scan run first

@bot.event
async def on_ready():
    log.info(f"🦍 Beast Discord Bot online as {bot.user}")
    log.info(f"   AI Brain: {'✅ Opus 4.7' if brain and brain.is_available else '❌ offline'}")
    tv_ok = False
    try:
        from tv_cdp_client import TVClient
        tv_ok = TVClient().health_check()
    except:
        pass
    log.info(f"   TradingView: {'✅' if tv_ok else '❌'}")

    if not position_monitor.is_running():
        position_monitor.start()
        log.info("   ✅ Position monitor: every 60s (auto-scalp + auto-buy dips)")
    if not full_scan.is_running():
        full_scan.start()
        log.info("   ✅ Full scan: every 5 min (TV + sentiment + AI)")
    if not decision_report.is_running():
        decision_report.start()
        log.info("   ✅ Decision report: every 10 min")
    if not claude_deep_scan.is_running():
        claude_deep_scan.start()
        log.info("   ✅ Claude deep scan: every 30 min")

    channel = bot.get_channel(SCAN_CHANNEL_ID)
    if channel:
        await channel.send(
            "🦍 **BEAST ENGINE V3 ONLINE**\n"
            f"• Position monitor: every 60s (auto-scalp/runner/dip-buy)\n"
            f"• Full scan: every 5 min (TV + sentiment + GPT-4o)\n"
            f"• Decision report: every 10 min\n"
            f"• Claude deep scan: every 30 min\n"
            f"• AI: {'GPT-4o ✅' if brain and brain._gpt_available else '❌'} + {'Claude ✅' if brain and brain._claude_available else 'Claude ❌'}\n"
            f"• TV: {'Connected ✅' if tv_ok else 'Offline ❌'}\n"
            f"• Iron Laws: HARDCODED ✅\n"
            f"• Auto-protect: 3% trailing stops ✅\n"
            f"• Auto-buy dips: ENABLED (Akash Method)\n"
            f"• Pre/post market: ENABLED (4AM-8PM)"
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
