# Denver Task & Workflow Security Policy

## Security Model
Denver's Task Orchestration subsystem adheres to a zero-trust model regarding task generation:

1. **AI Isolation**: AI models and external prompts produce only declarative data models (`TaskProposal`). AI is never given execution capabilities.
2. **Step Re-Validation**: Every step is re-validated through `SafetyValidator` immediately prior to dispatching to `ActionRegistry`.
3. **Restricted Actions**: Only pre-registered deterministic actions in `ActionRegistry` can ever execute. No dynamic code generation, `eval`, `exec`, `os.system`, or shell strings are permitted.
4. **Explicit Approvals**: High-impact or destructive operations require explicit user approval tokens before proceeding.
5. **No Autonomous Loops**: Tasks cannot self-generate new routines or child tasks, preventing runaway execution cycles.
