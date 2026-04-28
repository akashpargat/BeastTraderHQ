"""Compare TradingView Desktop (port 9222) vs Headless Chrome (port 9223)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_cdp_client import TVClient

print("=" * 60)
print("📺 DESKTOP APP (port 9222)")
print("=" * 60)
tv1 = TVClient(port=9222)
ok1 = tv1.health_check()
print(f"Connected: {ok1}")

if ok1:
    tv1._connect()
    studies1 = tv1.get_study_values()
    quote1 = tv1.get_quote()
    print(f"Studies: {len(studies1)}")
    for s in studies1:
        print(f"  {s.get('name', '?')}: {s.get('values', {})}")
    print(f"Quote: {quote1}")

print()
print("=" * 60)
print("🌐 HEADLESS CHROME (port 9223)")
print("=" * 60)
tv2 = TVClient(port=9223)
ok2 = tv2.health_check()
print(f"Connected: {ok2}")

if ok2:
    tv2._connect()
    studies2 = tv2.get_study_values()
    quote2 = tv2.get_quote()
    print(f"Studies: {len(studies2)}")
    for s in studies2:
        print(f"  {s.get('name', '?')}: {s.get('values', {})}")
    print(f"Quote: {quote2}")

print()
print("=" * 60)
print("COMPARISON:")
if ok1 and ok2:
    print(f"  Desktop studies:  {len(studies1)} with data")
    print(f"  Headless studies: {len(studies2)} with data")
    
    # Count non-empty values
    desktop_vals = sum(1 for s in studies1 for v in s.get('values', {}).values() if v and v != '\u2205')
    headless_vals = sum(1 for s in studies2 for v in s.get('values', {}).values() if v and v != '\u2205')
    print(f"  Desktop non-empty values:  {desktop_vals}")
    print(f"  Headless non-empty values: {headless_vals}")
    
    if headless_vals < desktop_vals:
        print("\n  ⚠️ Headless has fewer values — investigating...")
        print("  Desktop chart may have different timeframe or settings")
