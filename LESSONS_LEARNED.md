# Beast V3 — Lessons Learned (The Hard Way)

## CRITICAL: az vm run-command Limitations
These cost us 5+ hours. NEVER forget them.

### 1. SYSTEM Account Is Blind
- `az vm run-command` runs as NT AUTHORITY\SYSTEM, NOT as beastadmin
- SYSTEM cannot see user-installed tools in PATH (git, node, etc.)
- SYSTEM cannot see Machine environment variables set in same session
- SYSTEM cannot kill user-session processes reliably
- **FIX**: Use full paths (e.g., `C:\Program Files\Git\cmd\git.exe`)

### 2. Git Writes Progress to stderr
- Git clone/pull writes progress to stderr, NOT stdout
- PowerShell treats ANY stderr output as an error (NativeCommandError)
- This makes it LOOK like git failed when it actually SUCCEEDED
- **FIX**: Always verify results AFTER the command, don't trust exit behavior
- **FIX**: Use `2>&1 | Out-String` to capture but don't panic on "errors"

### 3. Empty Output ≠ Failure
- `az vm run-command` often returns empty stdout for commands that worked
- Especially when the output contains Unicode/emoji characters
- The SYSTEM account's console encoding (cp1252) can't handle emoji
- **FIX**: Write results to a file, then read that file in a separate command
- **FIX**: Use simple ASCII output (True/False, numbers) for verification

### 4. File Operations That Silently Fail
- `Remove-Item -Recurse -Force` silently fails if ANY file is locked
- `Rename-Item` silently fails if target already exists
- `Copy-Item -Force` may silently fail on locked files
- `Invoke-WebRequest` with SAS tokens gets URL mangled by escaping layers
- **FIX**: Always verify after file operations, never chain them assuming success
- **FIX**: If a folder can't be deleted, just use the new folder directly

### 5. Don't Fight the Folder — Use What Works
- If `C:\beast-v3` is locked, DON'T spend hours trying to delete it
- Just clone to `C:\beast-test2` and USE IT THERE
- Update configs/bat files to point to the new path
- **THE CORRECT ANSWER IS ALWAYS THE SIMPLEST ONE**

### 6. Escaping Hell
- Nested quotes (Python inside PowerShell inside az CLI) are IMPOSSIBLE
- Never try to write Python code with quotes via az vm run-command
- **FIX**: Write files to GitHub repo, clone on VM
- **FIX**: Or use base64 encoding for binary-safe transfer
- **FIX**: Or just ask the user (they're in RDP!) for 1-line commands

### 7. Python Encoding on Windows
- Windows console uses cp1252 by default
- Any emoji (codepoints > U+FFFF) will crash Python's print()
- `PYTHONIOENCODING=utf-8` env var must be set BEFORE Python starts
- Setting it in the same process doesn't help (too late)
- **FIX**: Add `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')` at the TOP of entry point files
- **FIX**: Or use `sitecustomize.py` in site-packages (applies globally)
- **FIX**: Or set PYTHONIOENCODING in registry (needs reboot/re-login)

## Deployment Workflow (USE THIS)
1. Edit files locally on laptop
2. `git push` to GitHub (akashpargat/BeastTraderHQ)
3. On VM: `git -C C:\beast-test2 pull` (or clone if first time)
4. Restart bot: `cd C:\beast-test2 && C:\Python312\python.exe discord_bot.py`

## VM Quick Reference
- **VM IP**: 172.179.234.42
- **Login**: beastadmin / BeastTrader12,.
- **Python**: C:\Python312\python.exe
- **Git**: C:\Program Files\Git\cmd\git.exe
- **Code**: C:\beast-test2 (was C:\beast-v3, moved due to locked folder)
- **TradingView**: MSIX app, CDP on port 9222 automatically
- **Chocolatey**: Installed (use for package management)
- **winget**: NOT available on Server 2022

## Architecture
```
Work Laptop                    Azure VM (beast-trader-vm)
┌──────────────┐              ┌──────────────────────────┐
│ copilot-api  │◄─Cloudflare──│ Discord Bot              │
│ (Claude 4.7) │   Tunnel     │ Beast Mode Loop          │
│ Flask :5555  │              │ TV CDP Client            │
└──────────────┘              │ Alpaca OrderGateway      │
                              │ Sentiment (Yahoo/Reddit) │
                              │ VM Agent :7777           │
                              └──────────────────────────┘
```

## What NOT To Do (I did all of these)
- ❌ Don't try to delete a folder that has running processes
- ❌ Don't try to write Python with quotes via az vm run-command
- ❌ Don't assume az vm run-command output means the command failed
- ❌ Don't try 50 variations of the same broken approach
- ❌ Don't forget git writes to stderr (it's not an error)
- ❌ Don't use SAS tokens in nested command strings (escaping hell)
- ❌ Don't ask the user to run 5 chained commands — give them ONE
- ✅ DO use GitHub as the file transfer mechanism
- ✅ DO verify results with separate simple commands
- ✅ DO use the new folder if the old one is locked
- ✅ DO use full paths for tools (git, python, etc.)
- ✅ DO add encoding fix at TOP of Python entry points
