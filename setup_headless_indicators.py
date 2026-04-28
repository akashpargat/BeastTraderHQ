"""Add indicators to TradingView headless Chrome."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_cdp_client import TVClient

tv = TVClient(port=9223)
tv.health_check()
tv._connect()

indicators = [
    'Relative Strength Index',
    'MACD',
    'VWAP',
    'Bollinger Bands',
    'Moving Average Exponential',
]

for ind in indicators:
    print(f"Adding {ind}...")
    js = f"""
    (function() {{
        try {{
            var chart = window.TradingViewApi._activeChartWidgetWV.value();
            chart.createStudy("{ind}", false, false);
            return true;
        }} catch(e) {{ return e.message; }}
    }})()
    """
    result = tv._evaluate(js)
    print(f"  Result: {result}")
    time.sleep(1.5)

# Second EMA with period 21
print("Adding EMA 21...")
js2 = """
(function() {
    try {
        var chart = window.TradingViewApi._activeChartWidgetWV.value();
        chart.createStudy("Moving Average Exponential", false, false, {length: 21});
        return true;
    } catch(e) { return e.message; }
})()
"""
tv._evaluate(js2)
time.sleep(2)

# SMA 20
print("Adding SMA 20...")
js3 = """
(function() {
    try {
        var chart = window.TradingViewApi._activeChartWidgetWV.value();
        chart.createStudy("Moving Average", false, false, {length: 20});
        return true;
    } catch(e) { return e.message; }
})()
"""
tv._evaluate(js3)
time.sleep(2)

# Read all studies
studies = tv.get_study_values()
print(f"\nStudies loaded: {len(studies)}")
for s in studies:
    print(f"  {s.get('name', '?')}: {s.get('values', {})}")

quote = tv.get_quote()
print(f"\nQuote: {quote}")

if len(studies) >= 5:
    print("\n✅ ALL INDICATORS LOADED! Headless TV Premium is ready.")
else:
    print(f"\n⚠️ Only {len(studies)} studies. May need to refresh or add more.")
