# Denver Scheduler: Architecture & Operational Specification

## 1. Overview & Philosophy
The **Denver Scheduler** (`DenverScheduler`) delivers proactive, scheduled, user-authored routines and reminders without autonomous agency.
The core philosophy is **Deterministic & User-Authored**:
- Denver NEVER initiates arbitrary tasks outside user intent.
- Denver NEVER executes unapproved background routines.
- AI models may PROPOSE routine configurations, but cannot enable, mutate, or execute them without explicit user confirmation.

## 2. Safety & Security Guardrails
All routine executions flow through Denver's three-tier safety boundary:
1. **Validation Layer**: Prohibits dangerous execution patterns (`eval`, `exec`, `subprocess`, `powershell`, `cmd.exe`).
2. **Action Registry**: All actions must match registered, allowlisted capabilities.
3. **Automation & Approval Layer**: High-risk actions demand interactive tokens (`RoutineApprovalManager`).
4. **Execution Bound**: Strict timeouts (`max_runtime_seconds`), global semaphore (`max_concurrency=2`), and non-overlapping routine executions.

## 3. Supported Trigger Types
- **ONE_TIME**: Executes once at a specified UTC timestamp. Automatically marked `COMPLETED` afterwards.
- **DAILY**: Executes daily at a specified `time_of_day` (e.g. `08:30`).
- **WEEKLY**: Executes on designated days of the week (`days_of_week=[0, 2, 4]`, 0=Monday) at `time_of_day`.
- **INTERVAL**: Recurring interval with a mandatory safety minimum of 300.0s (5 minutes) to prevent resource thrashing.

## 4. Operational Controls
| Natural Language Command | Action | Description |
|---|---|---|
| `list routines` | `list_routines` | Lists all configured routines, status, and next scheduled run |
| `pause all routines` | `pause_scheduler` | Globally halts background routine processing |
| `resume scheduler` | `resume_scheduler` | Resumes routine processing |
| `enable scheduler` | `enable_scheduler` | Enables background scheduler daemon |
| `disable scheduler` | `disable_scheduler` | Disables background scheduler daemon |
| `pause routine <id_or_name>` | `pause_routine` | Pauses a specific routine without deleting schedule |
| `resume routine <id_or_name>` | `resume_routine` | Resumes a paused routine |
| `delete routine <id_or_name>` | `delete_routine` | Deletes routine and cascades removal of history |
| `run routine <id_or_name> now` | `run_routine_now` | Manually triggers immediate routine execution |
| `remind me at <HH:MM> to <msg>` | `create_reminder` | Schedules a daily reminder routine |
