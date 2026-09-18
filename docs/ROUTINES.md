# Denver Routines: User-Authored Proactive Intelligence

## 1. Structure of a Routine
A Routine represents a sequence of one or more allowlisted actions executed against a defined trigger schedule.

```json
{
  "routine_id": "rtn_morning_briefing",
  "name": "Morning Briefing",
  "description": "Checks system telemetry and reads the current date and time",
  "enabled": true,
  "status": "active",
  "trigger": {
    "trigger_type": "daily",
    "time_of_day": "08:00",
    "timezone": "UTC"
  },
  "actions": [
    {
      "action_name": "get_date",
      "params": {},
      "description": "Fetch current date"
    },
    {
      "action_name": "get_system_status",
      "params": {},
      "description": "Check system status"
    }
  ],
  "notification_policy": "ALWAYS",
  "max_runtime_seconds": 60.0,
  "requires_confirmation": false
}
```

## 2. Notification Policies
- `ALWAYS`: Sends UI desktop notification on every execution (success or failure).
- `ON_FAILURE`: Only notifies if an action within the routine fails or times out.
- `NEVER`: Executes silently without raising UI toast notifications.

## 3. Rate Limiting & Anti-Storming
To prevent desktop notification storms, `RoutineNotificationService` enforces a configurable cooldown window (`DENVER_SCHEDULER_NOTIFICATION_RATE_LIMIT_SECONDS=10.0`). High-frequency routine events are throttled.

## 4. Execution Audit Trail
Every routine mutation (creation, enabling, pausing, execution, deletion) is permanently recorded in the `routine_audit` SQLite table for full forensic accountability.
