"""
Beast v2.0 — Notification System (Telegram + WhatsApp)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Sends real-time alerts to your phone:
  🚨 Sudden drops (>2% in 5 min)
  📊 Hourly portfolio summary
  💰 Trade executions (every buy/sell)
  ⛔ Iron Law violations
  🦍 Beast Mode cycle results
  📅 Earnings warnings
  🔥 Sector rotation alerts
  🏆 Daily P&L report

SETUP:
  Telegram (FREE, recommended):
    1. Message @BotFather on Telegram → /newbot → get TOKEN
    2. Message @userinfobot → get your CHAT_ID
    3. Add to .env:
       TELEGRAM_BOT_TOKEN=your_token
       TELEGRAM_CHAT_ID=your_chat_id
  
  WhatsApp (via Twilio, ~$0.005/msg):
    1. Sign up at twilio.com → get SID + AUTH_TOKEN
    2. Enable WhatsApp sandbox
    3. Add to .env:
       TWILIO_SID=your_sid
       TWILIO_AUTH_TOKEN=your_token
       WHATSAPP_FROM=whatsapp:+14155238886
       WHATSAPP_TO=whatsapp:+1YOURNUMBER
"""
import logging
import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

log = logging.getLogger('Beast.Notify')
ET = ZoneInfo("America/New_York")


class Notifier:
    """Multi-channel notification system for the Beast Engine."""

    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        self.twilio_sid = os.getenv('TWILIO_SID', '')
        self.twilio_auth = os.getenv('TWILIO_AUTH_TOKEN', '')
        self.whatsapp_from = os.getenv('WHATSAPP_FROM', '')
        self.whatsapp_to = os.getenv('WHATSAPP_TO', '')

        self._telegram_ok = bool(self.telegram_token and self.telegram_chat_id)
        self._whatsapp_ok = bool(self.twilio_sid and self.twilio_auth)
        
        # Discord auto-alerts via bot token + channel ID
        self.discord_token = os.getenv('DISCORD_BOT_TOKEN', '')
        self.discord_channel_id = os.getenv('DISCORD_CHANNEL_ID', '')
        self._discord_ok = bool(self.discord_token and self.discord_channel_id)

        if self._telegram_ok:
            log.info("📱 Telegram notifications ENABLED")
        if self._whatsapp_ok:
            log.info("📱 WhatsApp notifications ENABLED")
        if self._discord_ok:
            log.info("🎮 Discord auto-alerts ENABLED (channel: %s)", self.discord_channel_id)
        if not self._telegram_ok and not self._whatsapp_ok and not self._discord_ok:
            log.warning("📱 No notification channels configured. Add to .env")

    # ── Core Send Methods ──────────────────────────────

    def _send_telegram(self, message: str, parse_mode: str = "HTML"):
        """Send a message via Telegram Bot API."""
        if not self._telegram_ok:
            return
        try:
            # Sanitize HTML — escape angle brackets that aren't valid tags
            import re
            allowed_tags = ['b', 'i', 'u', 's', 'a', 'code', 'pre']
            # Remove any tags that aren't in our allowed list
            def clean_tag(match):
                tag = match.group(1).split()[0].strip('/')
                if tag.lower() in allowed_tags:
                    return match.group(0)
                return match.group(0).replace('<', '&lt;').replace('>', '&gt;')
            
            # If HTML parse fails, fall back to plain text
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            
            # Try HTML first
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            resp = requests.post(url, json=payload, timeout=10)
            
            if resp.status_code != 200:
                # Fallback: send as plain text (strip HTML tags)
                clean = re.sub(r'<[^>]+>', '', message)
                payload["text"] = clean
                payload["parse_mode"] = ""
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code != 200:
                    log.warning(f"Telegram send failed: {resp.text}")
        except Exception as e:
            log.warning(f"Telegram error: {e}")

    def _send_whatsapp(self, message: str):
        """Send a message via Twilio WhatsApp."""
        if not self._whatsapp_ok:
            return
        try:
            from twilio.rest import Client
            client = Client(self.twilio_sid, self.twilio_auth)
            client.messages.create(
                body=message,
                from_=self.whatsapp_from,
                to=self.whatsapp_to,
            )
        except Exception as e:
            log.warning(f"WhatsApp error: {e}")

    def _send_discord(self, message: str):
        """Send a message to Discord channel via bot HTTP API."""
        if not self._discord_ok:
            return
        try:
            # Strip HTML tags for Discord (it uses markdown, not HTML)
            import re
            clean = re.sub(r'<[^>]+>', '', message)
            # Convert bold HTML to Discord markdown
            clean = clean.replace('&lt;', '<').replace('&gt;', '>')
            
            # Discord max message length is 2000
            chunks = [clean[i:i+1950] for i in range(0, len(clean), 1950)]
            
            url = f"https://discord.com/api/v10/channels/{self.discord_channel_id}/messages"
            headers = {
                "Authorization": f"Bot {self.discord_token}",
                "Content-Type": "application/json",
            }
            
            for chunk in chunks:
                payload = {"content": chunk}
                resp = requests.post(url, json=payload, headers=headers, timeout=10)
                if resp.status_code not in (200, 201):
                    log.warning(f"Discord send failed: {resp.status_code} {resp.text[:100]}")
        except Exception as e:
            log.warning(f"Discord error: {e}")

    def send(self, message: str, urgent: bool = False):
        """Send to ALL configured channels (Telegram + Discord + WhatsApp)."""
        self._send_telegram(message)
        self._send_discord(message)
        if urgent:
            self._send_whatsapp(message)  # WhatsApp for urgent only
        log.info(f"📱 Notification sent to all channels")

    # ── Alert Types ────────────────────────────────────

    def alert_trade_executed(self, symbol: str, side: str, qty: int,
                             price: float, strategy: str, confidence: float):
        """Notify on every trade execution."""
        emoji = "🟢 BUY" if side == "buy" else "🔴 SELL"
        msg = (
            f"{emoji} <b>{symbol}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Qty: {qty} @ ${price:.2f}\n"
            f"Strategy: {strategy}\n"
            f"Confidence: {confidence:.0%}\n"
            f"Time: {datetime.now(ET).strftime('%H:%M:%S ET')}"
        )
        self.send(msg)

    def alert_sudden_drop(self, symbol: str, drop_pct: float,
                          current_price: float, unrealized_pl: float):
        """🚨 URGENT: Stock dropped >2% in 5 min."""
        msg = (
            f"🚨 <b>SUDDEN DROP: {symbol}</b> 🚨\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Drop: {drop_pct:+.2%} in 5 min!\n"
            f"Price: ${current_price:.2f}\n"
            f"Your P&L: ${unrealized_pl:+.2f}\n"
            f"Action: HOLDING (Iron Law 1)\n"
            f"Time: {datetime.now(ET).strftime('%H:%M:%S ET')}"
        )
        self.send(msg, urgent=True)

    def alert_iron_law_violation(self, law: str, details: str):
        """⛔ Iron Law was almost violated."""
        msg = (
            f"⛔ <b>IRON LAW BLOCKED</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Law: {law}\n"
            f"Details: {details}\n"
            f"Action: TRADE REJECTED\n"
            f"Time: {datetime.now(ET).strftime('%H:%M:%S ET')}"
        )
        self.send(msg)

    def alert_loss_threshold(self, symbol: str, unrealized_pl: float):
        """⚠️ Position exceeds $500 loss — alert user for manual decision."""
        msg = (
            f"⚠️ <b>LOSS ALERT: {symbol}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Unrealized P&L: ${unrealized_pl:+.2f}\n"
            f"⚠️ Exceeds $500 loss threshold\n"
            f"Bot action: HOLDING (Iron Law 1)\n"
            f"YOUR CALL: Reply to override\n"
            f"Time: {datetime.now(ET).strftime('%H:%M:%S ET')}"
        )
        self.send(msg, urgent=True)

    def alert_earnings_warning(self, symbol: str, earnings_date: str):
        """📅 Stock has earnings soon."""
        msg = (
            f"📅 <b>EARNINGS WARNING</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{symbol} reports: {earnings_date}\n"
            f"Action: NO NEW TRADES on {symbol}\n"
            f"Consider: Exit if green\n"
            f"Time: {datetime.now(ET).strftime('%H:%M:%S ET')}"
        )
        self.send(msg)

    def alert_sector_rotation(self, sector: str, direction: str,
                               movers: list[str]):
        """🔥 Sector moving — scan opportunity."""
        emoji = "🔥" if direction == "UP" else "🔻"
        msg = (
            f"{emoji} <b>SECTOR ALERT: {sector}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Direction: {direction}\n"
            f"Movers: {', '.join(movers)}\n"
            f"Action: Scanning full sector\n"
            f"Time: {datetime.now(ET).strftime('%H:%M:%S ET')}"
        )
        self.send(msg)

    def alert_kill_switch(self, daily_pnl: float):
        """⛔ Kill switch activated."""
        msg = (
            f"🛑 <b>KILL SWITCH ACTIVATED</b> 🛑\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Daily P&L: ${daily_pnl:+.2f}\n"
            f"ALL TRADING HALTED\n"
            f"Positions: HOLDING\n"
            f"Time: {datetime.now(ET).strftime('%H:%M:%S ET')}"
        )
        self.send(msg, urgent=True)

    # ── Periodic Reports ───────────────────────────────

    def send_hourly_summary(self, positions: list, total_pl: float,
                            equity: float, regime: str, day_trades: int):
        """📊 Hourly portfolio summary."""
        now = datetime.now(ET)
        lines = [
            f"📊 <b>HOURLY SUMMARY — {now.strftime('%H:%M ET')}</b>",
            f"━━━━━━━━━━━━━━━━━━",
            f"Equity: ${equity:,.2f}",
            f"Total P&L: ${total_pl:+.2f}",
            f"Regime: {regime}",
            f"Day trades: {day_trades}/3",
            f"",
        ]

        for p in positions:
            emoji = "🟢" if p.get('pl', 0) > 0 else "🔴"
            lines.append(
                f"{emoji} {p['symbol']:6s} {p.get('qty', 0)}x "
                f"${p.get('price', 0):.2f} ({p.get('pl', 0):+.2f})"
            )

        msg = "\n".join(lines)
        self.send(msg)

    def send_daily_report(self, positions: list, closed_trades: list,
                          total_realized: float, total_unrealized: float,
                          equity: float, win_rate: float):
        """🏆 End of day report."""
        now = datetime.now(ET)
        msg = (
            f"🏆 <b>DAILY REPORT — {now.strftime('%b %d, %Y')}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Realized P&L: ${total_realized:+.2f}\n"
            f"Unrealized P&L: ${total_unrealized:+.2f}\n"
            f"Equity: ${equity:,.2f}\n"
            f"Trades today: {len(closed_trades)}\n"
            f"Win rate: {win_rate:.0%}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        if closed_trades:
            msg += "\n<b>Closed Trades:</b>\n"
            for t in closed_trades:
                emoji = "🟢" if t.get('pl', 0) > 0 else "🔴"
                msg += f"{emoji} {t['symbol']} ${t.get('pl', 0):+.2f}\n"

        msg += f"\nOpen positions: {len(positions)}"
        self.send(msg)

    def send_beast_mode_result(self, cycle_num: int, regime: str,
                                positions_count: int, total_pl: float,
                                actions_taken: list[str]):
        """🦍 Beast Mode cycle complete."""
        now = datetime.now(ET)
        actions = "\n".join(f"  • {a}" for a in actions_taken) if actions_taken else "  • No actions"
        msg = (
            f"🦍 <b>BEAST CYCLE #{cycle_num}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Time: {now.strftime('%H:%M:%S ET')}\n"
            f"Regime: {regime}\n"
            f"Positions: {positions_count}\n"
            f"P&L: ${total_pl:+.2f}\n"
            f"Actions:\n{actions}"
        )
        self.send(msg)

    # ── Pre/Post Market ────────────────────────────────

    def send_premarket_scan(self, runners: list[dict], gaps: list[dict],
                            sentiment_score: int):
        """🌅 Pre-market scan results."""
        now = datetime.now(ET)
        lines = [
            f"🌅 <b>PRE-MARKET SCAN — {now.strftime('%H:%M ET')}</b>",
            f"━━━━━━━━━━━━━━━━━━",
            f"Sentiment: {sentiment_score}/10",
            f"",
        ]

        if gaps:
            lines.append("<b>Gaps:</b>")
            for g in gaps[:5]:
                emoji = "🟢" if g.get('pct', 0) > 0 else "🔴"
                lines.append(f"{emoji} {g['symbol']} {g.get('pct', 0):+.1%}")

        if runners:
            lines.append("\n<b>Runners:</b>")
            for r in runners[:5]:
                lines.append(f"🏃 {r['symbol']} +{r.get('pct', 0):.1%} "
                           f"vol: {r.get('volume', 0):,}")

        msg = "\n".join(lines)
        self.send(msg)

    # ── Price Monitoring ───────────────────────────────

    def check_sudden_drops(self, current_prices: dict[str, float],
                           previous_prices: dict[str, float],
                           positions: list):
        """Check for >2% drops in held positions and alert."""
        for pos in positions:
            sym = pos.get('symbol', '') if isinstance(pos, dict) else pos.symbol
            curr = current_prices.get(sym, 0)
            prev = previous_prices.get(sym, 0)
            if curr > 0 and prev > 0:
                change = (curr - prev) / prev
                if change <= -0.02:  # >2% drop
                    pl = pos.get('unrealized_pl', 0) if isinstance(pos, dict) else pos.unrealized_pl
                    self.alert_sudden_drop(sym, change, curr, pl)
