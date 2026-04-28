"""
Beast v2.0 — AI API Server (runs on work laptop)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tiny Flask server that exposes the AI brain via HTTP.
The VM calls this to get Claude Opus 4.7 analysis.

Test: Lock your screen, then from another terminal:
  curl http://localhost:5555/health
  curl -X POST http://localhost:5555/analyze -H "Content-Type: application/json" -d "{\"symbol\":\"NVDA\",\"rsi\":55}"
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv('.env')

from flask import Flask, request, jsonify
from ai_brain import AIBrain
from datetime import datetime

app = Flask(__name__)
brain = AIBrain()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'online',
        'ai_available': brain.is_available,
        'time': datetime.now().isoformat(),
    })

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.json or {}
    symbol = data.get('symbol', 'SPY')
    result = brain.analyze_stock(symbol, data)
    return jsonify(result)

@app.route('/debate', methods=['POST'])
def debate():
    data = request.json or {}
    symbol = data.get('symbol', 'SPY')
    result = brain.bull_bear_debate(symbol, data)
    return jsonify(result)

@app.route('/briefing', methods=['POST'])
def briefing():
    data = request.json or {}
    result = brain.morning_briefing(
        data.get('market', {}),
        data.get('positions', []),
        data.get('sentiment', {})
    )
    return jsonify({'briefing': result})

if __name__ == '__main__':
    print("🧠 AI API Server starting on port 5555...")
    print(f"   AI Brain: {'ONLINE' if brain.is_available else 'OFFLINE'}")
    print(f"   Test: curl http://localhost:5555/health")
    print(f"   Lock screen test: lock screen, then curl again")
    app.run(host='0.0.0.0', port=5555, debug=False)
