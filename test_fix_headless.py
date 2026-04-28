"""Fix headless TV: trigger crosshair to populate indicator values."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_cdp_client import TVClient

tv = TVClient(port=9223)
tv.health_check()
tv._connect()

# Method 1: Move crosshair to last bar to trigger data window update
print("Triggering crosshair update...")
js_fix = """
(function() {
    try {
        var chart = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget;
        var model = chart.model();
        var bars = model.mainSeries().bars();
        var lastIdx = bars.lastIndex();
        
        // Force the crosshair to the last bar
        var cc = model.model().crossHairSource();
        if (cc && cc.setPosition) {
            cc.setPosition(lastIdx, 0);
        }
        
        // Alternative: trigger price scale update
        model.model().invalidate();
        
        return {lastIdx: lastIdx, success: true};
    } catch(e) { return {error: e.message}; }
})()
"""
result = tv._evaluate(js_fix)
print(f"Crosshair fix: {result}")
time.sleep(1)

# Method 2: Read values directly from study data instead of dataWindowView
print("\nTrying direct data access...")
js_direct = """
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
            if (!name) continue;
            var values = {};
            
            // Try data() method instead of dataWindowView
            try {
                var data = s.data();
                if (data && data.size && data.size() > 0) {
                    var lastIdx = data.size() - 1;
                    var lastBar = data.valueAt(lastIdx);
                    if (lastBar) {
                        // Plot values are in the bar data
                        var plots = meta.plots || [];
                        for (var j = 0; j < plots.length; j++) {
                            var plotName = plots[j].id || plots[j].name || ('plot_' + j);
                            // Values start after OHLCV (index 5+)
                            if (lastBar[j] !== undefined && lastBar[j] !== null) {
                                values[plotName] = typeof lastBar[j] === 'number' ? 
                                    lastBar[j].toFixed(4) : String(lastBar[j]);
                            }
                        }
                    }
                }
            } catch(e) { values['_data_error'] = e.message; }
            
            // Also try plots directly
            try {
                if (s._series && s._series._data) {
                    var sd = s._series._data;
                    var lastKey = sd._data ? sd._data.lastKey() : null;
                    if (lastKey !== null) {
                        var val = sd._data.get(lastKey);
                        if (val) {
                            for (var k = 0; k < Math.min(val.length, 10); k++) {
                                if (val[k] !== undefined && val[k] !== null && !isNaN(val[k])) {
                                    values['raw_' + k] = val[k].toFixed(4);
                                }
                            }
                        }
                    }
                }
            } catch(e) {}
            
            if (Object.keys(values).length > 0) {
                results.push({name: name, values: values});
            }
        } catch(e) {}
    }
    return results;
})()
"""

result2 = tv._evaluate(js_direct)
print(f"Direct data access: {len(result2)} studies with values")
for r in result2:
    print(f"  {r.get('name', '?')}: {r.get('values', {})}")

# Method 3: Try re-reading dataWindowView after invalidation
print("\nRe-reading dataWindowView after invalidation...")
time.sleep(1)
studies = tv.get_study_values()
print(f"Studies with values: {len(studies)}")
for s in studies:
    print(f"  {s.get('name', '?')}: {s.get('values', {})}")
