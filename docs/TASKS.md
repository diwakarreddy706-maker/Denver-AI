# Denver Tasks Subsystem

## Overview
The Tasks subsystem allows Denver to register, validate, track, and execute user-defined multi-step tasks.

## Commands
- `plan task <description>`: Generates a proposed DAG task plan.
- `task status <task_id>`: Displays current state, steps, and progress.
- `task history <task_id>`: Shows execution log and duration metrics.
- `run task <task_id>`: Executes the active plan for the specified task.
- `pause task <task_id>`: Pauses task execution safely at step boundaries.
- `resume task <task_id>`: Resumes a paused task.
- `cancel task <task_id>`: Cancels an active or pending task.
- `delete task <task_id>`: Removes task and associated historical records.
- `pause all tasks`: Globally halts execution of all tasks.
- `resume all tasks`: Resumes task execution globally.
- `enable tasks` / `disable tasks`: Toggles orchestration subsystem availability.

## Task States
- `DRAFT`: Newly created task entity with or without a preliminary plan.
- `READY`: Validated plan is saved and ready for execution.
- `RUNNING`: Actively executing steps via `WorkflowEngine`.
- `PAUSED`: Execution suspended cooperatively.
- `COMPLETED`: All steps executed successfully.
- `FAILED`: Execution stopped due to an error and policy settings.
- `CANCELLED`: Aborted by user or cancellation token.
