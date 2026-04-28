"""
Beast V3 — Auto-Start Setup
Creates Windows scheduled tasks so Beast Engine survives VM reboots.
Run once on the VM: python auto_start.py
"""
import subprocess
import os

PYTHON = r"C:\Python312\python.exe"
BOT_DIR = r"C:\beast-test2"
BOT_SCRIPT = os.path.join(BOT_DIR, "discord_bot.py")
USER = "beastadmin"

def create_startup_bat():
    """Create a batch file that starts everything."""
    bat = os.path.join(BOT_DIR, "start_beast.bat")
    content = f"""@echo off
set PYTHONIOENCODING=utf-8
cd /d {BOT_DIR}

:: Start TradingView Desktop (CDP auto-enabled)
start "" "C:\\Users\\{USER}\\AppData\\Local\\Microsoft\\WindowsApps\\TradingView.exe"

:: Wait for TV to load
timeout /t 10 /nobreak

:: Start Beast Discord Bot (autonomous loop built-in)
{PYTHON} {BOT_SCRIPT}
"""
    with open(bat, 'w') as f:
        f.write(content)
    print(f"Created: {bat}")
    return bat


def create_scheduled_task(bat_path):
    """Create a scheduled task that runs on user logon."""
    task_name = "BeastEngineV3"
    # Delete if exists
    subprocess.run(f'schtasks /Delete /TN {task_name} /F', shell=True, 
                   capture_output=True)
    # Create task on logon
    cmd = (f'schtasks /Create /TN {task_name} '
           f'/TR "\"{bat_path}\"" '
           f'/SC ONLOGON /RU {USER} '
           f'/RL HIGHEST /F')
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Scheduled task '{task_name}' created (runs on logon)")
    else:
        print(f"Task creation failed: {result.stderr}")
        # Fallback: add to Startup folder
        startup = os.path.join(os.environ.get('APPDATA', ''), 
                              'Microsoft', 'Windows', 'Start Menu', 
                              'Programs', 'Startup')
        shortcut = os.path.join(startup, 'BeastEngine.bat')
        with open(shortcut, 'w') as f:
            f.write(f'@echo off\nstart "" "{bat_path}"\n')
        print(f"Fallback: Added to Startup folder: {shortcut}")


if __name__ == '__main__':
    bat = create_startup_bat()
    create_scheduled_task(bat)
    print("\nBeast Engine will auto-start on next login/reboot.")
    print("To test: schtasks /Run /TN BeastEngineV3")
