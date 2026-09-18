# Contributing to Denver AI Assistant

Thank you for your interest in contributing to Denver AI Assistant!

## Code Standards & Architecture

1. **Windows-First Compatibility**: Ensure all automation, audio, and UI features work seamlessly on Windows 11 / 10 with non-blocking fallbacks.
2. **Deterministic Intent Routing**: Core commands should use deterministic pattern matching before delegating to LLM routing.
3. **Zero Secret Leakage**: Never hardcode API keys, secrets, or personal paths in code or tests.
4. **Automated Testing**: Every new subsystem, command, or widget must include unit and integration tests.
5. **Quality Gates**: All PRs must pass `pytest` (100% pass rate) and `ReleaseArtifactVerifier` checks.

## Development Workflow

1. Clone repository and install dependencies:
   ```bash
   pip install -e .
   ```
2. Run test suite:
   ```bash
   pytest
   ```
3. Test release verification:
   ```bash
   python main.py --verify-release dist
   ```
