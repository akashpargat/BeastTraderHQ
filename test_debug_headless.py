"""Debug why headless TV indicators return empty values."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_cdp_client import TVClient

tv = TVClient(port=9223)
tv.health_check()
tv._connect()

# Check chart state (symbol, timeframe, etc.)
js_state = """
(function() {
    try {
        var chart = window.TradingViewApi._activeChartWidgetWV.value();
        var cw = chart._chartWidget;
        var model = cw.model();
        var series = model.mainSeries();
        return {
            symbol: series.symbol(),
            resolution: model.model().mainSeries().properties().interval.value(),
            chartType: model.model().mainSeries().properties().style.value(),
        };
    } catch(e) { return {error: e.message}; }
})()
"""
state = tv._evaluate(js_state)
print(f"Chart state: {state}")

# Check if indicators are actually computing
js_debug = """
(function() {
    var chart = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget;
    var model = chart.model();
    var sources = model.model().dataSources();
    var results = [];
    for (var i = 0; i < sources.length; i++) {
        var s = sources[i];
        if (!s.metaInfo) continue;
        try {
            var meta = s.metaInfo();
            var name = meta.description || meta.shortDescription || '';
            var dwv = null;
            var itemCount = 0;
            var rawVals = {};
            try {
                dwv = s.dataWindowView();
                if (dwv) {
                    var items = dwv.items();
                    itemCount = items ? items.length : 0;
                    if (items) {
                        for (var j = 0; j < Math.min(items.length, 5); j++) {
                            var item = items[j];
                            rawVals[item._title || 'no_title'] = {
                                value: item._value,
                                visible: item._visible,
                                type: typeof item._value
                            };
                        }
                    }
                }
            } catch(e) { rawVals['error'] = e.message; }
            results.push({
                name: name,
                itemCount: itemCount,
                hasDWV: dwv !== null,
                rawVals: rawVals
            });
        } catch(e) {}
    }
    return results;
})()
"""

result = tv._evaluate(js_debug)
print(f"\nDetailed study debug ({len(result)} studies):")
for r in result:
    name = r.get('name', '?')
    items = r.get('itemCount', 0)
    has_dwv = r.get('hasDWV', False)
    vals = r.get('rawVals', {})
    print(f"\n  [{name}]")
    print(f"    dataWindowView: {has_dwv} | items: {items}")
    for k, v in vals.items():
        print(f"    {k}: {v}")
