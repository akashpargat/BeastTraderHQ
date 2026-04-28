"""Test headless Chrome + TradingView CDP."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_cdp_client import TVClient

tv = TVClient(port=9223)
ok = tv.health_check()
status = "CONNECTED" if ok else "FAILED"
print(f"Headless TV CDP: {status} (port 9223)")

if ok:
    tv._connect()
    
    # Read studies
    studies = tv.get_study_values()
    print(f"Studies loaded: {len(studies)}")
    for s in studies:
        print(f"  {s.get('name', '?')}: {s.get('values', {})}")
    
    # Read quote
    q = tv.get_quote()
    print(f"Quote: {q}")
    
    # Switch symbol
    print("\nSwitching to NVDA...")
    tv.set_symbol("NVDA")
    time.sleep(4)
    
    studies2 = tv.get_study_values()
    print(f"NVDA Studies: {len(studies2)}")
    for s in studies2:
        print(f"  {s.get('name', '?')}: {s.get('values', {})}")
    
    q2 = tv.get_quote()
    print(f"NVDA Quote: {q2}")
    
    print("\n✅ HEADLESS TRADINGVIEW WORKS!")
    print("This runs even when screen is LOCKED.")
else:
    print("❌ Headless TV not responding")
