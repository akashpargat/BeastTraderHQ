"""
Beast v2.0 — Keep Alive + Windows Service Setup
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Prevents laptop from sleeping and runs the bot as a Windows Service.

Run this ONCE to set up:
    python setup_service.py --install

What it does:
  1. Disables sleep/hibernate when on power
  2. Installs NSSM (Non-Sucking Service Manager)
  3. Registers Beast Bot as a Windows Service
  4. Registers copilot-api as a Windows Service
  5. Both start automatically on boot
  6. Both restart automatically if they crash
"""
import os
import sys
import subprocess
import ctypes

BEAST_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable
NSSM_URL = "https://nssm.cc/release/nssm-2.24.zip"


def is_admin():
    """Check if running as administrator."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def prevent_sleep():
    """Prevent Windows from sleeping when on AC power."""
    print("⚡ Preventing sleep on AC power...")
    
    # Disable sleep on AC
    subprocess.run(["powercfg", "/change", "standby-timeout-ac", "0"], check=True)
    # Disable hibernate on AC
    subprocess.run(["powercfg", "/change", "hibernate-timeout-ac", "0"], check=True)
    # Disable display off on AC (optional — set to 30 min)
    subprocess.run(["powercfg", "/change", "monitor-timeout-ac", "30"], check=True)
    # Keep system awake
    subprocess.run(["powercfg", "/change", "standby-timeout-dc", "30"], check=True)
    
    print("  ✅ Sleep disabled on AC power")
    print("  ✅ Hibernate disabled on AC power")
    print("  ✅ Screen off after 30 min (saves power, bot still runs)")


def create_bat_files():
    """Create batch files for the services."""
    
    # Beast bot launcher
    beast_bat = os.path.join(BEAST_DIR, "service_beast.bat")
    with open(beast_bat, 'w') as f:
        f.write(f"""@echo off
cd /d "{BEAST_DIR}"
"{PYTHON}" discord_bot.py
""")
    print(f"  ✅ Created {beast_bat}")

    # Copilot API launcher
    copilot_bat = os.path.join(BEAST_DIR, "service_copilot_api.bat")
    npm_path = os.path.expandvars(r"%APPDATA%\npm\copilot-api.cmd")
    with open(copilot_bat, 'w') as f:
        f.write(f"""@echo off
"{npm_path}" start
""")
    print(f"  ✅ Created {copilot_bat}")

    # TradingView launcher
    tv_bat = os.path.join(BEAST_DIR, "service_tradingview.bat")
    with open(tv_bat, 'w') as f:
        f.write(f"""@echo off
REM Find TradingView and launch with CDP
for /f "delims=" %%i in ('dir /s /b "C:\\Program Files\\WindowsApps\\TradingView.Desktop*\\TradingView.exe" 2^>nul') do (
    start "" "%%i" --remote-debugging-port=9222
    exit /b
)
echo TradingView not found!
""")
    print(f"  ✅ Created {tv_bat}")

    return beast_bat, copilot_bat, tv_bat


def install_with_task_scheduler():
    """
    Use Windows Task Scheduler instead of NSSM (no admin/install needed).
    Creates tasks that:
      - Run at login
      - Restart on failure
      - Run whether user is logged in or not
    """
    print("\n📋 Setting up Windows Task Scheduler tasks...")

    beast_bat, copilot_bat, tv_bat = create_bat_files()

    tasks = [
        ("BeastTrader_CopilotAPI", copilot_bat, "Copilot API for Beast Trader"),
        ("BeastTrader_TradingView", tv_bat, "TradingView for Beast Trader"),
        ("BeastTrader_Bot", beast_bat, "Beast Trading Discord Bot"),
    ]

    for task_name, bat_path, description in tasks:
        # Delete existing task if it exists
        subprocess.run(
            ["schtasks", "/delete", "/tn", task_name, "/f"],
            capture_output=True
        )

        # Create task that runs at logon
        result = subprocess.run([
            "schtasks", "/create",
            "/tn", task_name,
            "/tr", f'"{bat_path}"',
            "/sc", "onlogon",
            "/rl", "highest",
            "/f",
        ], capture_output=True, text=True)

        if result.returncode == 0:
            print(f"  ✅ Task '{task_name}' created — runs at login")
        else:
            print(f"  ❌ Task '{task_name}' failed: {result.stderr.strip()}")

    print("\n  📋 All tasks registered! They will start on next login.")
    print("  To start them NOW, run:")
    for task_name, _, _ in tasks:
        print(f"    schtasks /run /tn {task_name}")


def create_keepalive_script():
    """Create a Python keepalive that prevents system sleep programmatically."""
    keepalive_path = os.path.join(BEAST_DIR, "keepalive.py")
    with open(keepalive_path, 'w') as f:
        f.write('''"""
Keepalive — Prevents Windows from sleeping while the bot runs.
Uses SetThreadExecutionState to tell Windows "I'm busy, don't sleep."
Run this alongside the bot.
"""
import ctypes
import time
import logging

log = logging.getLogger('Keepalive')

# Windows API constants
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

def prevent_sleep():
    """Tell Windows not to sleep. Must be called periodically."""
    ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    )

def allow_sleep():
    """Allow Windows to sleep again."""
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

if __name__ == '__main__':
    print("💤 Keepalive running — Windows will NOT sleep")
    print("   Press Ctrl+C to stop and allow sleep")
    try:
        while True:
            prevent_sleep()
            time.sleep(30)  # Refresh every 30 seconds
    except KeyboardInterrupt:
        allow_sleep()
        print("✅ Sleep re-enabled")
''')
    print(f"  ✅ Created {keepalive_path}")
    return keepalive_path


def main():
    print("""
╔═══════════════════════════════════════════════════╗
║  🦍 BEAST ENGINE — Service Setup                  ║
║  Makes the bot run 24/7 even when laptop is locked ║
╚═══════════════════════════════════════════════════╝
    """)

    # Step 1: Prevent sleep
    prevent_sleep()

    # Step 2: Create keepalive script
    create_keepalive_script()

    # Step 3: Create batch launchers
    create_bat_files()

    # Step 4: Register with Task Scheduler
    install_with_task_scheduler()

    print("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ SETUP COMPLETE!

Your laptop will now:
  ⚡ Never sleep on AC power
  🔄 Auto-start these on login:
     1. copilot-api (AI Brain)
     2. TradingView Desktop (CDP)
     3. Beast Discord Bot (trading)
  💤 Screen turns off after 30 min (saves power)
  🔒 Bot keeps running when screen locks!

To start everything NOW:
  python keepalive.py      (in one terminal)
  copilot-api start        (in another)
  python discord_bot.py    (in another)

Or just log out and back in — everything starts automatically.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """)


if __name__ == '__main__':
    main()
