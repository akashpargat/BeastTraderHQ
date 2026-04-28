"""
Beast v2.0 — TradingView MCP Bridge Client
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Calls the TV MCP server's Node.js functions via subprocess.
This gives us the SAME data quality as the Copilot MCP tools,
but callable from standalone Python.

Works even when screen is locked because the TV Desktop app
handles rendering — we just read the computed values.

REQUIRES: 
  - TradingView Desktop running with --remote-debugging-port=9222
  - Node.js installed
  - tradingview-mcp server at C:\\Users\\akashpargat\\tradingview-mcp
"""
import json
import subprocess
import logging
import os

log = logging.getLogger('Beast.TVBridge')

BRIDGE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tv_bridge.js')
NODE = 'node'


class TVBridgeClient:
    """Calls TV MCP server functions via Node.js subprocess."""

    def __init__(self):
        self._available = os.path.exists(BRIDGE_SCRIPT)
        if not self._available:
            log.warning("tv_bridge.js not found")

    def _call(self, cmd: str, arg: str = '') -> dict:
        """Call tv_bridge.js and return parsed JSON."""
        try:
            args = [NODE, BRIDGE_SCRIPT, cmd]
            if arg:
                args.append(arg)
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=30,
                cwd=os.path.dirname(BRIDGE_SCRIPT),
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout.strip())
            else:
                log.error(f"TV bridge error: {result.stderr[:200]}")
                return {'error': result.stderr[:200]}
        except subprocess.TimeoutExpired:
            log.error(f"TV bridge timeout on {cmd}")
            return {'error': 'timeout'}
        except Exception as e:
            log.error(f"TV bridge failed: {e}")
            return {'error': str(e)}

    def health_check(self) -> bool:
        result = self._call('health')
        return result.get('success', False)

    def get_study_values(self) -> list:
        result = self._call('studies')
        return result.get('studies', [])

    def get_quote(self) -> dict:
        result = self._call('quote')
        bars = result.get('bars', [])
        return bars[-1] if bars else {}

    def set_symbol(self, symbol: str) -> bool:
        result = self._call('symbol', symbol)
        return result.get('success', False)

    def get_pine_labels(self, study_filter: str = 'Guru') -> list:
        result = self._call('labels', study_filter)
        studies = result.get('studies', [])
        labels = []
        for s in studies:
            labels.extend(s.get('labels', []))
        return labels

    def get_pine_tables(self, study_filter: str = 'Guru') -> list:
        result = self._call('tables', study_filter)
        return result.get('studies', [])

    def get_bars(self, count: int = 200) -> list:
        result = self._call('bars', str(count))
        return result.get('bars', [])

    def scan_stock(self, symbol: str) -> dict:
        """Full scan: switch symbol, wait, read everything."""
        return self._call('scan', symbol)
