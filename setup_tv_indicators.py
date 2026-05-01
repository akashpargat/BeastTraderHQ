"""
Beast V3 — Auto-add TradingView indicators via CDP
Run ONCE on VM to add all required indicators to the chart.
"""
import json
import time
import requests
import websocket

CDP_PORT = 9222

def get_chart_ws():
    """Find the /chart/ page and connect."""
    r = requests.get(f'http://localhost:{CDP_PORT}/json', timeout=5)
    for t in r.json():
        if 'tradingview.com/chart' in t.get('url', '') and t.get('type') == 'page':
            print(f"Found chart: {t['title'][:50]}")
            return websocket.create_connection(t['webSocketDebuggerUrl'], timeout=15, suppress_origin=True)
    raise Exception("No TradingView chart found! Open a chart in Chrome first.")

def evaluate(ws, js):
    """Run JS in the chart page."""
    msg = json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                      'params': {'expression': js, 'returnByValue': True}})
    ws.send(msg)
    while True:
        resp = json.loads(ws.recv())
        if resp.get('id') == 1:
            return resp.get('result', {}).get('result', {}).get('value')

def add_indicator(ws, name, wait=3):
    """Add an indicator by name — tries multiple API paths for compatibility."""
    # Method 1: createStudy on paneViews (newer TV versions)
    methods = [
        f"""
        (function() {{
            try {{
                var chart = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget;
                chart.model().createStudy(chart.model().mainSeries(), '{name}');
                return 'method1_ok';
            }} catch(e) {{ return 'method1_fail: ' + e.message; }}
        }})()
        """,
        f"""
        (function() {{
            try {{
                var api = window.TradingViewApi;
                var chart = api._activeChartWidgetWV.value();
                chart.createStudy('{name}', false, false);
                return 'method2_ok';
            }} catch(e) {{ return 'method2_fail: ' + e.message; }}
        }})()
        """,
        f"""
        (function() {{
            try {{
                var chart = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget;
                var pane = chart.paneViews()[0];
                pane.model().createStudy(pane.model().mainSeries(), '{name}');
                return 'method3_ok';
            }} catch(e) {{ return 'method3_fail: ' + e.message; }}
        }})()
        """,
        f"""
        (function() {{
            try {{
                var w = document.querySelector('[class*="chart-widget"]');
                var api = Object.keys(w).filter(k => k.startsWith('__reactFiber'))[0];
                var fiber = w[api];
                while (fiber && !fiber.memoizedProps?.chartWidgetCollection) fiber = fiber.return;
                var coll = fiber.memoizedProps.chartWidgetCollection;
                var chart = coll.activeChartWidget.value();
                chart.createStudy('{name}', false, false);
                return 'method4_ok';
            }} catch(e) {{ return 'method4_fail: ' + e.message; }}
        }})()
        """,
        # Method 5: Use the search/add UI via keyboard simulation
        f"""
        (function() {{
            try {{
                // Open indicators dialog
                document.querySelector('[data-name="insert-indicator"]')?.click() ||
                document.querySelector('[aria-label="Indicators, Metrics & Strategies"]')?.click();
                return 'method5_clicked_indicator_btn';
            }} catch(e) {{ return 'method5_fail: ' + e.message; }}
        }})()
        """,
    ]
    
    for js in methods:
        result = evaluate(ws, js)
        if result and '_ok' in str(result):
            time.sleep(wait)
            return result
        print(f"    {result}")
    
    time.sleep(wait)
    return 'all_methods_failed'

def get_current_studies(ws):
    """List currently loaded studies."""
    js = """
    (function() {
        var chart = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget;
        var sources = chart.model().model().dataSources();
        var names = [];
        for (var i = 0; i < sources.length; i++) {
            if (sources[i].metaInfo) {
                try {
                    var meta = sources[i].metaInfo();
                    var name = meta.description || meta.shortDescription || '';
                    if (name) names.push(name);
                } catch(e) {}
            }
        }
        return names;
    })()
    """
    return evaluate(ws, js) or []

# Required indicators
REQUIRED = [
    'Relative Strength Index',
    'MACD',
    'VWAP',
    'Bollinger Bands',
    'Moving Average Exponential',  # EMA 9
    'Moving Average Exponential',  # EMA 21
    'Moving Average',              # SMA 20
]

if __name__ == '__main__':
    print("=" * 50)
    print("Beast V3 — Adding TradingView Indicators")
    print("=" * 50)

    ws = get_chart_ws()

    # Check what's already loaded
    current = get_current_studies(ws)
    print(f"\nCurrently loaded: {len(current)} studies")
    for s in current:
        print(f"  - {s}")

    # Add missing indicators
    needed = []
    for ind in REQUIRED:
        count = sum(1 for c in current if ind.lower() in c.lower())
        if ind == 'Moving Average Exponential' and count < 2:
            needed.append(ind)
        elif ind != 'Moving Average Exponential' and count == 0:
            needed.append(ind)

    if not needed:
        print("\n All indicators already loaded!")
    else:
        print(f"\nAdding {len(needed)} indicators...")
        for ind in needed:
            print(f"  Adding: {ind}...", end=" ")
            result = add_indicator(ws, ind)
            print(f"{'OK' if result == True else result}")

    # Verify
    time.sleep(2)
    final = get_current_studies(ws)
    print(f"\nFinal studies: {len(final)}")
    for s in final:
        print(f"  - {s}")

    ws.close()
    print("\nDone! Restart the bot to use the new indicators.")
