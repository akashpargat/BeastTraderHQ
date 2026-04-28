"""
Beast v2.0 — Report Formatter
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generates rich, formatted Telegram reports with tables and emojis.
"""

def format_beast_report(positions, runners, dumpers, sector_alerts,
                        ai_results, debates, earnings, mkt_sent,
                        regime, equity, total_pl, acct) -> str:
    """Generate the full fancy Beast Mode report for Telegram."""
    
    lines = []
    
    # Header
    lines.append("🦍🔥 BEAST MODE v2.2 — FULL SCAN 🔥🦍")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # Market Pulse
    sent_emoji = {"AGGRESSIVE": "🚀", "NORMAL": "📊", "CAUTIOUS": "😐", 
                  "DEFENSIVE": "🛡️", "ABORT": "⛔"}.get(mkt_sent.get('action', ''), '📊')
    
    lines.append("")
    lines.append("📊 MARKET PULSE")
    lines.append(f"┌─────────────────────────┐")
    lines.append(f"│ Regime: {regime:8s} {'🐂' if regime == 'BULL' else '🌊' if regime == 'CHOPPY' else '🐻' if regime == 'BEAR' else '🔴'}        │")
    lines.append(f"│ Sentiment: {mkt_sent.get('action', '?'):10s} {sent_emoji} │")
    lines.append(f"│ Score: {mkt_sent.get('total_score', 0):+d}/25             │")
    lines.append(f"└─────────────────────────┘")
    
    # Portfolio
    lines.append("")
    lines.append(f"💰 PORTFOLIO: ${equity:,.0f}")
    pl_emoji = "📈" if total_pl > 0 else "📉"
    alert = " ⛔ KILL SWITCH" if total_pl <= -500 else ""
    lines.append(f"{pl_emoji} P&L: ${total_pl:+,.2f}{alert}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # Positions table
    lines.append("")
    lines.append(f"📦 POSITIONS ({len(positions)} held)")
    
    # Sort: green first, then by P&L desc
    sorted_pos = sorted(positions, key=lambda p: p.unrealized_pl, reverse=True)
    
    for p in sorted_pos:
        emoji = "🟢" if p.is_green else "🔴"
        rsi_warn = ""
        lines.append(f"{emoji}{p.symbol:5s} {p.qty:5d}x ${p.current_price:>8.2f} "
                     f"${p.unrealized_pl:>+8.2f}")
    
    red_count = sum(1 for p in positions if p.is_red)
    if red_count:
        lines.append(f"🔒 {red_count} red = HOLD (Iron Law 1)")
    
    # Runners
    if runners:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🏃💨 TOP RUNNERS")
        for r in runners[:8]:
            emoji = "⭐" if r.get('past_winner') else "🏃"
            lines.append(f"{emoji}{r['symbol']:5s} {r['change_pct']:+.2%} "
                        f"${r['price']:.2f}")
    
    # Dumpers
    if dumpers:
        lines.append("")
        lines.append("📉🎯 DUMPERS (Akash Method?)")
        for d in dumpers[:5]:
            lines.append(f"💀{d['symbol']:5s} {d['change_pct']:+.2%} ${d['price']:.2f}")
        lines.append("Watch for RSI<30 bounce")
    
    # Sector alerts
    if sector_alerts:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔥 SECTOR ALERTS")
        for sa in sector_alerts:
            emoji = "🟢" if sa['direction'] == 'UP' else "🔻"
            lines.append(f"{emoji} {sa['name']}: {', '.join(sa['movers'][:4])}")
    
    # AI Brain results
    if ai_results:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🧠 AI BRAIN (Claude Opus 4.7)")
        
        sorted_ai = sorted(ai_results.items(), 
                          key=lambda x: x[1].get('confidence', 0), reverse=True)
        for sym, ai in sorted_ai:
            conf = ai.get('confidence', 0)
            action = ai.get('action', '?')
            emoji = {"BUY": "🟢", "HOLD": "🟡", "SELL": "🔴", 
                     "WATCH": "👀", "SKIP": "⏭️"}.get(action, "⚪")
            lines.append(f"{emoji}{sym:5s} {conf:3d}% {action}")
        
        # Reasoning for top 3
        lines.append("")
        for sym, ai in sorted_ai[:3]:
            reason = ai.get('reasoning', '')
            if reason:
                lines.append(f"💬{sym}: {reason[:80]}")
    
    # Bull/Bear debates
    if debates:
        lines.append("")
        lines.append("⚔️ DEBATES:")
        for sym, d in debates.items():
            bull = d.get('bull_confidence', 50)
            bear = d.get('bear_confidence', 50)
            v = d.get('verdict', '?')
            lines.append(f"{sym}: 🐂{bull}% vs 🐻{bear}% = {v}")
    
    # Earnings
    if earnings:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("📅 EARNINGS WATCH")
        for sym, info in earnings.items():
            days = info.get('days', 999)
            if days <= 3:
                emoji = "⛔" if days <= 1 else "⚠️"
                lines.append(f"{emoji} {sym} — {info.get('date', '?')} ({days}d)")
    
    # Risk
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🛡️ RISK DASHBOARD")
    
    if total_pl <= -500:
        lines.append(f"⛔ P&L ${total_pl:+,.0f} = KILL SWITCH")
    else:
        lines.append(f"✅ P&L ${total_pl:+,.0f} within limits")
    
    # Alert on big losers
    for p in sorted_pos:
        if p.unrealized_pl <= -500:
            lines.append(f"⛔ {p.symbol}: ${p.unrealized_pl:,.0f} ALERT!")
    
    lines.append(f"📊 Regime: {regime}")
    lines.append(f"🧊 Iron Law 10: When in doubt = NOTHING")
    
    # Final verdict
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # Determine overall action
    buys = [s for s, ai in (ai_results or {}).items() 
            if ai.get('action') in ('BUY', 'CONVICTION_BUY', 'STRONG_BUY')]
    
    if buys:
        lines.append(f"🎯 ACTION: BUY {', '.join(buys)}")
    else:
        lines.append("🎯 VERDICT: DO NOTHING ⏸️")
        lines.append("HOLD all. Wait for setup.")
    
    lines.append("")
    lines.append("🦍 Next scan in 60 seconds...")
    
    return "\n".join(lines)
