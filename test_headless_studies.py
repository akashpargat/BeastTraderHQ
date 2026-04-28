"""Check what studies are on the headless TV chart."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_cdp_client import TVClient

tv = TVClient(port=9223)
tv.health_check()
tv._connect()

js = """
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
            var vals = {};
            try {
                dwv = s.dataWindowView();
                if (dwv) {
                    var items = dwv.items();
                    if (items) {
                        for (var j = 0; j < items.length; j++) {
                            var item = items[j];
                            if (item._value && item._title) vals[item._title] = item._value;
                        }
                    }
                }
            } catch(e) {}
            results.push({name: name, values: vals, hasValues: Object.keys(vals).length > 0});
        } catch(e) {}
    }
    return results;
})()
"""

result = tv._evaluate(js)
print(f"Total studies found: {len(result)}")
print()
for r in result:
    has = "✅" if r.get('hasValues') else "❌"
    name = r.get('name', '?')
    vals = r.get('values', {})
    print(f"  {has} {name}")
    if vals:
        for k, v in vals.items():
            print(f"      {k}: {v}")
