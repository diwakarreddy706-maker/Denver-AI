# Denver Memory & Persistence Architecture Specification

> **Product**: Denver AI Assistant (`Denver`)  
> **Objective**: Define a high-performance, durable, privacy-conscious memory subsystem replacing flat JSON files with an embedded SQLite relational + vector database.

---

## 1. Architectural Overview

```mermaid
graph TB
    subgraph Memory Ingestion & Queries
        UserCmd[User Command] --> MemManager[Denver Unified Memory Manager]
        LLMReq[LLM Context Request] --> MemManager
        UIQuery[Denver Cockpit Memory Inspector] --> MemManager
    end

    subgraph Memory Layers
        MemManager --> ShortTerm[Tier 1: Ephemeral Short-Term Buffer<br/>In-Memory Ring Buffer / Deque]
        MemManager --> Relational[Tier 2: Relational SQLite Store<br/>Preferences, Notes, Tasks, Habits, Audits]
        MemManager --> VectorStore[Tier 3: Vector Embedding Store<br/>sqlite-vec / Local Cosine Similarity]
    end

    subgraph Privacy & Redaction Engine
        MemManager <--> PrivacyGuard[Denver Privacy Mode & Secret Redaction Engine]
    end

    subgraph Data Store (denver_memory.sqlite3)
        Relational --> TablePref[(user_preferences)]
        Relational --> TableNotes[(notes & reminders)]
        Relational --> TableHabits[(command_habits)]
        Relational --> TableAudit[(command_audit_log)]
        VectorStore --> TableVec[(memory_embeddings)]
    end
```

---

## 2. Memory Tiering Model

### Tier 1: Ephemeral Short-Term Buffer
- **Data Structure**: In-memory ring buffer (`collections.deque(maxlen=20)`).
- **Scope**: Current active user session.
- **Content**: Last 10-20 turns of raw conversation exchanges (`user` and `denver`).
- **Lifecycle**: Flushed or optionally summarized into long-term storage on session completion.

### Tier 2: Relational Long-Term Store (SQLite)
- **Engine**: Embedded SQLite (`denver_memory.sqlite3`).
- **Pragmas**:
  - `PRAGMA journal_mode = WAL;` (Concurrent reads without locking writes)
  - `PRAGMA synchronous = NORMAL;` (High durability with minimal disk write latency)
  - `PRAGMA foreign_keys = ON;`
- **Scope**: Multi-session persistent intelligence.

### Tier 3: Semantic Vector Memory (`sqlite-vec`)
- **Engine**: Lightweight SQLite vector extension or local sentence-transformers embedding index.
- **Embedding Model**: `all-MiniLM-L6-v2` or `bge-small-en-v1.5` (running via ONNX runtime locally in `< 15ms`).
- **Functionality**: Enables semantic search such as:
  - *Query*: `"What did I mention about the project deadline?"*
  - *Match*: Retrieves note `"Submit final report by Friday 5 PM"` with high cosine similarity.

---

## 3. Database Schema Design

```sql
-- 1. User Preferences Table
CREATE TABLE IF NOT EXISTS user_preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Notes & Persistent Reminders
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    content TEXT NOT NULL,
    tags TEXT, -- JSON array of strings
    is_pinned BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Scheduled Tasks & Reminders
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_text TEXT NOT NULL,
    due_at TIMESTAMP,
    is_completed BOOLEAN DEFAULT 0,
    reminder_sent BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Command Habit Frequency & Time-Series
CREATE TABLE IF NOT EXISTS command_habits (
    command_phrase TEXT PRIMARY KEY,
    execution_count INTEGER DEFAULT 1,
    last_executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Structured Audit Trail
CREATE TABLE IF NOT EXISTS command_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_command TEXT NOT NULL,
    routed_action TEXT NOT NULL,
    provider_used TEXT NOT NULL,
    status TEXT NOT NULL, -- 'success', 'failed', 'blocked'
    latency_ms REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Vector Embeddings Table (Semantic Recall)
CREATE TABLE IF NOT EXISTS memory_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL, -- 'note', 'preference', 'interaction'
    entity_id INTEGER,
    content_chunk TEXT NOT NULL,
    embedding BLOB NOT NULL, -- Float32 vector array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. Migration from Reference `memory.json`

The system includes an automatic one-time migration routine:
1. Detects legacy `memory.json` in the working directory or AppData.
2. Parses preferences, notes array, and habit counts.
3. Inserts records into `denver_memory.sqlite3` tables inside a single atomic transaction.
4. Backs up legacy file as `memory.json.bak` and switches active storage engine to SQLite.

---

## 5. Context Synthesis & Prompt Construction

When forwarding complex commands to cloud or local LLMs, the memory manager builds a compact, token-bounded context string:

```text
[SYSTEM CONTEXT: USER PROFILE & DENVER MEMORY]
- User Preferences: {favorite_music: 'synthwave', default_browser: 'chrome'}
- Relevant Notes: ['Submit weekly report on Friday', 'Project repo is at C:/Dev/AI']
- Frequent Habits: ['open chrome', 'spotify play', 'get cpu']
- Recent Conversation (Last 3 Turns):
  User: "What's my memory usage?"
  Denver: "Memory usage is at 42 percent, sir."
```

---

## 6. Privacy Controls & Retention Policy

1. **Privacy Mode (`DENVER_PRIVACY_MODE=true`)**:
   - Zero writes committed to `denver_memory.sqlite3`.
   - Short-term conversation buffer is kept in RAM only and wiped on application exit.
2. **Automated Secret Redaction**:
   - The memory manager runs pre-save regex filters masking passwords, API tokens, bearer keys, and credit cards before inserting into notes or audit logs.
3. **Data Retention & Pruning**:
   - Audit logs older than 30 days are automatically archived or purged.
   - Built-in one-click memory cleanup tools accessible from the Denver Cockpit Security & Health panels.
