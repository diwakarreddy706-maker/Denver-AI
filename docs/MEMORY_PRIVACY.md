# Denver Memory Privacy & Security Architecture

## Overview
Denver is built with privacy-first engineering. Memories and context are protected at every boundary.

---

## 1. Privacy Levels (`denver.memory.models.PrivacyLevel`)

| Level | Value | Cloud Allowed by Default | Description |
|---|---|---|---|
| `PUBLIC_CONTEXT` | `public_context` | Yes | General, non-sensitive context suitable for cloud routing |
| `PRIVATE` | `private` | No (`false`) | Personal information restricted to local operations |
| `SENSITIVE` | `sensitive` | No (`false`) | High-risk information (credentials, keys, financial data) |
| `EPHEMERAL` | `ephemeral` | No (`false`) | Transient session context; short TTL |

---

## 2. Cloud Privacy Sanitization
When a query requires calling a cloud AI provider (e.g. OpenAI, Anthropic, Gemini, Groq), `CloudPrivacyFilter` evaluates each candidate memory item:

1. If `privacy_level == SENSITIVE` and `DENVER_ALLOW_SENSITIVE_CLOUD_CONTEXT == false`, the memory is **strictly excluded**.
2. If `privacy_level == PRIVATE` and `DENVER_ALLOW_PRIVATE_CLOUD_CONTEXT == false`, the memory is **strictly excluded**.
3. Event `SensitiveMemoryExcluded` is published to the `DenverEventBus` for telemetry and audit logging.

---

## 3. Masking & Secret Redaction
- Log records automatically redact detected API keys, passwords, and authorization headers via `DenverMaskingFilter`.
- Health status and telemetry reports redact database content, reporting only counts and health flags.
- UI components never display unmasked secrets.
