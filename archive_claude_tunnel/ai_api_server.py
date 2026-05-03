"""
Beast v2.0 — AI API Server (runs on work laptop)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tiny Flask server that exposes the AI brain via HTTP.
The VM calls this to get Claude Opus 4.7 analysis.
SECURED with API key — only requests with valid key are accepted.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv('.env')

from flask import Flask, request, jsonify
from ai_brain import AIBrain
from datetime import datetime
from functools import wraps

app = Flask(__name__)
brain = AIBrain()

# API key for authentication — must match VM's AI_API_KEY env var
API_KEY = os.getenv('AI_API_KEY', 'beast-v3-sk-7f3a9e2b4d1c8f5e6a0b3d9c')

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if key != API_KEY:
            return jsonify({'error': 'unauthorized', 'message': 'Invalid or missing X-API-Key header'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/health', methods=['GET'])
def health():
    """Health check — no auth needed (just status, no data)."""
    return jsonify({
        'status': 'online',
        'ai_available': brain.is_available,
        'time': datetime.now().isoformat(),
        'auth': 'enabled',
    })

@app.route('/analyze', methods=['POST'])
@require_api_key
def analyze():
    data = request.json or {}
    symbol = data.get('symbol', 'SPY')
    result = brain.analyze_stock(symbol, data)
    return jsonify(result)

@app.route('/debate', methods=['POST'])
@require_api_key
def debate():
    data = request.json or {}
    symbol = data.get('symbol', 'SPY')
    result = brain.bull_bear_debate(symbol, data)
    return jsonify(result)

@app.route('/briefing', methods=['POST'])
@require_api_key
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
    print(f"   Auth: ENABLED (X-API-Key header required)")
    print(f"   Test: curl http://localhost:5555/health")
    app.run(host='0.0.0.0', port=5555, debug=False)
