# Denver DAG Workflow Engine

## Overview
Denver workflows are structured as Directed Acyclic Graphs (DAGs) where nodes represent discrete system actions and edges represent execution dependencies.

## DAG Execution Properties
1. **Parallel Execution**: Independent branches run concurrently up to `task_max_concurrency` (default 2).
2. **Cycle Prevention**: Plans are evaluated with Kahn's algorithm before acceptance.
3. **Failure Policies**:
   - `STOP_ON_FAILURE`: Ceases execution of downstream steps immediately.
   - `CONTINUE_ON_FAILURE`: Executes independent steps and marks failure in telemetry.
   - `RETRY_THEN_STOP`: Retries safe idempotent actions once before stopping.
4. **Step Timeouts**: Each step is bounded by a per-step timeout (default 60s) preventing hung operations.
5. **Cooperative Cancellation**: Steps inspect `CancellationToken` before and during execution.
