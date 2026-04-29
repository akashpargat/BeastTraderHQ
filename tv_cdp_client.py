"""
Beast v2.0 — TradingView CDP Client (Direct Browser Connection)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Talks DIRECTLY to TradingView Desktop via Chrome DevTools Protocol.
No MCP needed. No Copilot session needed. Fully autonomous.

REQUIRES: TradingView Desktop running with --remote-debugging-port=9222
LAUNCH:   cmd /c "start "" "C:\\Program Files\\WindowsApps\\TradingView.Desktop_*\\TradingView.exe" --remote-debugging-port=9222"
"""
import json
import time
import logging
import requests
import websocket

log = logging.getLogger('Beast.TVClient')

CDP_PORT = 9222
CDP_HOST = "localhost"


class TVClient:
    """Direct CDP connection to TradingView Desktop."""

    def __init__(self, port: int = CDP_PORT):
        self.port = port
        self.ws = None
        self._msg_id = 0
        self._connected = False

    def health_check(self) -> bool:
        """Check if TradingView is running and accessible."""
        try:
            resp = requests.get(f"http://{CDP_HOST}:{self.port}/json", timeout=5)
            targets = resp.json()
            for t in targets:
                if 'tradingview.com' in t.get('url', ''):
                    self._connected = True
                    return True
            return False
        except:
            return False

    def _get_ws_url(self) -> str:
        """Get WebSocket URL for TradingView CHART page (not homepage)."""
        resp = requests.get(f"http://{CDP_HOST}:{self.port}/json", timeout=5)
        targets = resp.json()
        # Priority 1: find /chart/ page specifically
        for target in targets:
            url = target.get('url', '')
            if 'tradingview.com/chart' in url and target.get('type') == 'page':
                log.info(f"📺 Found TV chart: {target.get('title', '')[:40]}")
                return target['webSocketDebuggerUrl']
        # Priority 2: any tradingview page (Desktop app)
        for target in targets:
            if 'tradingview.com' in target.get('url', '') and target.get('type') == 'page':
                return target['webSocketDebuggerUrl']
        raise ConnectionError("TradingView chart tab not found")

    def _connect(self):
        """Connect to TradingView via WebSocket."""
        if self.ws:
            return
        ws_url = self._get_ws_url()
        self.ws = websocket.create_connection(
            ws_url, timeout=10,
            suppress_origin=True,  # Bypass origin check
        )
        self._connected = True

    def _send(self, method: str, params: dict = None) -> dict:
        """Send CDP command and get result."""
        if not self.ws:
            self._connect()
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method, "params": params or {}}
        self.ws.send(json.dumps(msg))

        while True:
            resp = json.loads(self.ws.recv())
            if resp.get("id") == self._msg_id:
                return resp.get("result", {})

    def _evaluate(self, expression: str) -> any:
        """Execute JavaScript in TradingView page context."""
        result = self._send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        val = result.get("result", {}).get("value")
        return val

    # ── TradingView Commands ───────────────────────────

    def set_symbol(self, symbol: str) -> bool:
        """Switch the chart to a new symbol using proven MCP path."""
        js = f"""
        (function() {{
            try {{
                var chart = window.TradingViewApi._activeChartWidgetWV.value();
                chart.setSymbol('{symbol}');
                return true;
            }} catch(e) {{ return false; }}
        }})()
        """
        return self._evaluate(js) == True

    def get_study_values(self) -> list:
        """Read all study/indicator values from the data window.
        Uses the exact same JS path as the TradingView MCP server.
        Handles both visible and headless modes."""
        js = """
        (function() {
            var chart = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget;
            var model = chart.model();
            var sources = model.model().dataSources();
            var results = [];
            for (var si = 0; si < sources.length; si++) {
                var s = sources[si];
                if (!s.metaInfo) continue;
                try {
                    var meta = s.metaInfo();
                    var name = meta.description || meta.shortDescription || '';
                    if (!name) continue;
                    var values = {};
                    
                    // Method 1: Try dataWindowView (works in visible mode)
                    try {
                        var dwv = s.dataWindowView();
                        if (dwv) {
                            var items = dwv.items();
                            if (items) {
                                for (var i = 0; i < items.length; i++) {
                                    var item = items[i];
                                    if (item._value && item._value !== '\u2205' && item._title) 
                                        values[item._title] = item._value;
                                }
                            }
                        }
                    } catch(e) {}
                    
                    // Method 2: If dataWindowView is empty, read from study data directly
                    // This works in headless/minimized mode
                    if (Object.keys(values).length === 0) {
                        try {
                            var data = s.data ? s.data() : (s._series ? s._series : null);
                            if (data && data.bars) {
                                var bars = data.bars();
                                if (bars && bars.size() > 0) {
                                    var lastIdx = bars.lastIndex();
                                    var lastBar = bars.valueAt(lastIdx);
                                    if (lastBar) {
                                        var plots = meta.plots || [];
                                        for (var j = 0; j < plots.length; j++) {
                                            var pname = plots[j].id || ('plot_' + j);
                                            if (lastBar[j+1] !== undefined && lastBar[j+1] !== null && !isNaN(lastBar[j+1])) {
                                                values[pname] = lastBar[j+1].toFixed(4);
                                            }
                                        }
                                    }
                                }
                            }
                        } catch(e2) {}
                    }
                    
                    // Method 3: Try _study._data if available
                    if (Object.keys(values).length === 0) {
                        try {
                            var sd = s._study || s;
                            if (sd._data && sd._data._data) {
                                var d = sd._data._data;
                                var keys = [];
                                d.forEach(function(v, k) { keys.push(k); });
                                if (keys.length > 0) {
                                    var lastKey = keys[keys.length - 1];
                                    var val = d.get(lastKey);
                                    if (val) {
                                        var plots = meta.plots || [];
                                        for (var j = 0; j < Math.min(plots.length, val.length); j++) {
                                            var pname = plots[j].id || ('plot_' + j);
                                            if (val[j] !== undefined && val[j] !== null && !isNaN(val[j])) {
                                                values[pname] = val[j].toFixed(4);
                                            }
                                        }
                                    }
                                }
                            }
                        } catch(e3) {}
                    }
                    
                    if (Object.keys(values).length > 0) results.push({ name: name, values: values });
                } catch(e) {}
            }
            return results;
        })()
        """
        return self._evaluate(js) or []

    def get_quote(self, symbol: str = '') -> dict:
        """Get current quote data using proven MCP path."""
        js = """
        (function() {
            var bars = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget.model().mainSeries().bars();
            if (!bars || typeof bars.lastIndex !== 'function') return {};
            var end = bars.lastIndex();
            var v = bars.valueAt(end);
            if (!v) return {};
            return {
                time: v[0], open: v[1], high: v[2], low: v[3], 
                close: v[4], volume: v[5] || 0
            };
        })()
        """
        return self._evaluate(js) or {}

    def get_pine_labels(self, study_filter: str = '') -> list:
        """Read Pine Script labels (FVG, R2G, Long signals)."""
        js = f"""
        (function() {{
            try {{
                const c = window.chartWidgetCollection;
                if (!c) return [];
                const chart = c.getActiveChartWidget().model();
                const studies = chart.paneManager().getMainPane().getDataSourcesByGroup('study');
                const results = [];
                for (const s of studies) {{
                    const name = s.title();
                    if ('{study_filter}' && !name.includes('{study_filter}')) continue;
                    const labels = [];
                    try {{
                        const labelSource = s._data && s._data._labels;
                        if (labelSource) {{
                            for (const [id, label] of labelSource) {{
                                labels.push({{
                                    text: label.text || '',
                                    price: label.price || 0,
                                }});
                            }}
                        }}
                    }} catch(e) {{}}
                    if (labels.length > 0) {{
                        results.push({{name, labels}});
                    }}
                }}
                return results;
            }} catch(e) {{ return []; }}
        }})()
        """
        return self._evaluate(js) or []

    def get_pine_tables(self, study_filter: str = '') -> list:
        """Read Pine Script table data."""
        js = f"""
        (function() {{
            try {{
                const c = window.chartWidgetCollection;
                if (!c) return [];
                const chart = c.getActiveChartWidget().model();
                const studies = chart.paneManager().getMainPane().getDataSourcesByGroup('study');
                const results = [];
                for (const s of studies) {{
                    const name = s.title();
                    if ('{study_filter}' && !name.includes('{study_filter}')) continue;
                    try {{
                        const tables = s._data && s._data._tables;
                        if (tables) {{
                            for (const [id, table] of tables) {{
                                const rows = [];
                                for (const [rid, row] of table._cells || []) {{
                                    rows.push(row.text || '');
                                }}
                                results.push({{name, rows}});
                            }}
                        }}
                    }} catch(e) {{}}
                }}
                return results;
            }} catch(e) {{ return []; }}
        }})()
        """
        return self._evaluate(js) or []

    def scan_stock(self, symbol: str, delay: float = 2.0) -> dict:
        """
        Complete scan of ONE stock: switch symbol, wait, read everything.
        This is what the bot calls for each stock in Phase 2.
        """
        try:
            self.set_symbol(symbol)
            time.sleep(delay)  # Wait for chart to load

            studies = self.get_study_values()
            quote = self.get_quote()
            labels = self.get_pine_labels('Guru')
            tables = self.get_pine_tables('Guru')

            return {
                'symbol': symbol,
                'studies': studies,
                'quote': quote,
                'labels': labels,
                'tables': tables,
                'success': True,
            }
        except Exception as e:
            log.error(f"TV scan failed for {symbol}: {e}")
            return {'symbol': symbol, 'success': False, 'error': str(e)}

    def scan_multiple(self, symbols: list, delay: float = 2.0) -> dict:
        """Scan multiple stocks sequentially. Returns dict of results."""
        results = {}
        for sym in symbols:
            log.info(f"📺 Scanning {sym} on TradingView...")
            results[sym] = self.scan_stock(sym, delay)
        return results

    def close(self):
        """Close the WebSocket connection."""
        if self.ws:
            self.ws.close()
            self.ws = None
            self._connected = False
