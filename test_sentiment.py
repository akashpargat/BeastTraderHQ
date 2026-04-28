"""Quick test of full sentiment system."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentiment_analyst import SentimentAnalyst

sa = SentimentAnalyst()
print("=== FULL MARKET SENTIMENT ===")
result = sa.full_market_sentiment()
print()
total = result.get('total_score', 0)
action = result.get('action', '?')
print(f"TOTAL: {total:+d}/25 -> {action}")
print()

trump = result.get('trump_headlines', [])
if trump:
    print("TRUMP/TARIFF HEADLINES:")
    for h in trump:
        print(f"  - {h}")

breaking = result.get('breaking_headlines', [])
if breaking:
    print("\nBREAKING NEWS:")
    for h in breaking:
        print(f"  - {h}")

geo = result.get('geo_headlines', [])
if geo:
    print("\nGEOPOLITICAL:")
    for h in geo:
        print(f"  - {h}")

print("\n=== PER-STOCK SENTIMENT ===")
for sym in ['NVDA', 'INTC', 'NOK', 'AMZN']:
    s = sa.analyze(sym)
    print(f"{sym}: Yahoo {s.yahoo_score:+d} | Reddit {s.reddit_score:+d} | Analyst {s.analyst_score:+d} | Total {s.total_score:+d}")
