import sys, io
if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
"""
Beast v2.0 — Entry Point
━━━━━━━━━━━━━━━━━━━━━━━━
Usage:
    python run_beast.py          # Start autonomous trading
    python run_beast.py --test   # Dry run (no orders)
"""
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from beast_engine import BeastEngine


def main():
    print("""
    ╔══════════════════════════════════════════════╗
    ║  🦍 BEAST ENGINE v2.0 — Multi-Agent Trader   ║
    ║  ─────────────────────────────────────────── ║
    ║  Iron Laws: HARDCODED (13 laws, prioritized) ║
    ║  Orders: SINGLE WRITER (no race conditions)  ║
    ║  AI Debate: OPTIONAL (non-blocking)          ║
    ║  Exits: DETERMINISTIC (no AI in stop logic)  ║
    ║  Account: PAPER (PA37M4LP1YKP)               ║
    ╚══════════════════════════════════════════════╝
    """)

    if '--test' in sys.argv:
        print("🧪 DRY RUN MODE — no orders will be placed")
        # TODO: Wire up dry-run flag to OrderGateway
        return

    engine = BeastEngine()
    engine.run()


if __name__ == '__main__':
    main()
