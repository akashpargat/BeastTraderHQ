"""Quick test of Claude Opus 4.7 as AI Brain."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv('.env')
from ai_brain import AIBrain, FAST_MODEL, DEEP_MODEL

print(f"Model: {FAST_MODEL}")
brain = AIBrain()
print(f"Status: {'ONLINE' if brain.is_available else 'OFFLINE'}")

if brain.is_available:
    print("\n=== AMZN Analysis (Claude Opus 4.7) ===")
    result = brain.analyze_stock('AMZN', {
        'price': 262, 'rsi': 28, 'macd_hist': -0.35,
        'vwap_above': False, 'volume_ratio': 1.8,
        'bb_position': 'below', 'confluence': 4,
        'yahoo_score': 4, 'analyst_score': 5, 'reddit_score': 1,
        'trump_score': -1, 'regime': 'CHOPPY', 'sector': 'mag7',
        'earnings_days': 2, 'holding': True, 'unrealized_pl': -11.0,
        'ema_9': 263, 'ema_21': 264
    })
    for k, v in result.items():
        print(f"  {k}: {v}")
