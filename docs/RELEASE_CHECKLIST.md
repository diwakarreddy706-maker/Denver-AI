# Denver AI Assistant — Windows Release Candidate Checklist

**Product:** Denver AI Assistant  
**Namespace:** `denver`  
**Version:** v0.1.0-RC (Release Candidate)  
**Binary Output:** `dist/Denver/Denver.exe`  
**Target:** Windows 11 / Windows 10 (x64)  
**Build Platform:** Python 3.14.7  

---

## 1. Release Verification Matrix

- [x] **Test Suite Pass Rate**: `221 / 221 PASS` (100% clean test execution)
- [x] **No Test Regression**: All Phase 0–6.1 baseline tests remain green.
- [x] **Zero Plaintext Secrets**: Vault uses Windows DPAPI; API keys/tokens are masked in logs, UI, and diagnostics.
- [x] **Zero Unrestricted Execution**: No `eval()`, `exec()`, `os.system()`, or arbitrary shell execution.
- [x] **Path Independence**: Application resolves paths via `src/denver/config/paths.py` and supports execution from any working directory.
- [x] **Database Reliability**: SQLite WAL mode, foreign keys, migrations, and automatic parent directory creation.
- [x] **Graceful Degradation**: Denver launches and operates when microphones, AI providers, or optional cloud keys are unavailable.
- [x] **Packaging Implemented**: PyInstaller `denver.spec` and automated build pipeline `scripts/build_windows.ps1`.
- [x] **Standalone Binary Verified**: `dist/Denver/Denver.exe` compiles with code 0 and executes without requiring source files or python interpreter in PATH.
- [x] **CLI Subcommands Tested**: `--version`, `--health`, `--check-config`, `-c "<command>"`.
- [x] **Cockpit GUI Tested**: Launches cleanly on Windows 11, HUD animations run at 30 FPS, and system tray minimizes.
- [x] **Clean Shutdown**: Shuts down event loops, background audio threads, and database connections cleanly.

---

## 2. Command Verification Log

| Command | Expected Exit | Tested Status | Output Snippet |
|---|---|---|---|
| `Denver.exe --version` | `0` | **PASS** | `Denver AI Assistant v0.1.0 (Denver)` |
| `Denver.exe --check-config` | `0` | **PASS** | Valid sanitized JSON dictionary |
| `Denver.exe --health` | `0` | **PASS** | Subsystem status report (`READY`/`UNAVAILABLE`) |
| `Denver.exe -c "what time is it"` | `0` | **PASS** | Executed in 6.06ms (`The current time is ...`) |
| `Denver.exe` from `C:\Temp` | `0` | **PASS** | Working-directory independent |
