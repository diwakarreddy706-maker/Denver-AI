# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Security Model & Zero-Secret Architecture

Denver AI Assistant follows strict privacy, security, and zero-leak guardrails:

1. **Zero Secret Persistence in Logs & Releases**:
   - All API keys (`gsk_`, `sk-`, `AIzaSy`, `Bearer`) are masked in logs, diagnostics (`--export-diagnostics`), and memory snapshots (`--export-memory`).
   - Distribution builder (`--build-portable`) automatically executes `ReleaseArtifactVerifier` prior to finalizing release packages.
2. **Permission-Gated Plugin Sandboxing**:
   - Plugins execute within bounded contexts and cannot access network, filesystem, or audio without explicit manifest permissions.
3. **High-Risk Confirmation Gates**:
   - Destructive actions (e.g. file deletion, memory purging, system locks) require explicit user tokens or affirmative confirmation.
4. **Local-First Processing**:
   - Context, notes, preferences, and embeddings are stored in local SQLite databases protected with WAL journaling.

## Reporting a Vulnerability

If you discover a security vulnerability in Denver, please report it privately:
- Do NOT file a public issue on GitHub.
- Submit a detailed report including reproduction steps to the project security maintainers.
- We will respond within 48 hours and coordinate a coordinated patch release.
