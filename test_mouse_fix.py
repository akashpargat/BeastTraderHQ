"""Fix headless TV by simulating mouse movement over chart."""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tv_cdp_client import TVClient

tv = TVClient(port=9223)
tv.health_check()
tv._connect()

# Simulate mouse move to center of chart — triggers crosshair and data window
print("Simulating mouse move over chart...")
tv._send("Input.dispatchMouseEvent", {
    "type": "mouseMoved",
    "x": 960,   # center of 1920 viewport
    "y": 400,   # middle of chart area
})
time.sleep(0.5)

# Move mouse a bit to trigger crosshair snap to bar
tv._send("Input.dispatchMouseEvent", {
    "type": "mouseMoved",
    "x": 1800,  # near right edge (latest bar)
    "y": 400,
})
time.sleep(1)

# Now read studies
studies = tv.get_study_values()
print(f"\nStudies after mouse move: {len(studies)}")
for s in studies:
    vals = s.get('values', {})
    non_empty = {k: v for k, v in vals.items() if v and v != '\u2205'}
    if non_empty:
        print(f"  ✅ {s.get('name', '?')}: {non_empty}")
    else:
        print(f"  ❌ {s.get('name', '?')}: still empty")

# Count successes
non_empty_count = sum(1 for s in studies 
                      for v in s.get('values', {}).values() 
                      if v and v != '\u2205')
print(f"\nNon-empty values: {non_empty_count}")
if non_empty_count > 5:
    print("✅ HEADLESS TV INDICATORS WORKING!")
else:
    print("⚠️ Still not populated. Trying keyboard shortcut...")
    
    # Try pressing End key to go to latest bar
    tv._send("Input.dispatchKeyEvent", {
        "type": "keyDown",
        "key": "End",
        "code": "End",
        "windowsVirtualKeyCode": 35,
    })
    time.sleep(0.5)
    tv._send("Input.dispatchKeyEvent", {
        "type": "keyUp",
        "key": "End",
        "code": "End",
        "windowsVirtualKeyCode": 35,
    })
    time.sleep(1)
    
    # Mouse move again
    tv._send("Input.dispatchMouseEvent", {
        "type": "mouseMoved",
        "x": 1850,
        "y": 400,
    })
    time.sleep(1)
    
    studies2 = tv.get_study_values()
    print(f"\nStudies after End + mouse: {len(studies2)}")
    for s in studies2:
        vals = s.get('values', {})
        non_empty = {k: v for k, v in vals.items() if v and v != '\u2205'}
        if non_empty:
            print(f"  ✅ {s.get('name', '?')}: {non_empty}")
