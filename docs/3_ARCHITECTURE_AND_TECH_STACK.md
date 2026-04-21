# Core Architecture and Tech Stack Analysis

To achieve a local-first, blazing-fast, and open-source system, we must carefully analyze our infrastructure choices. We want to avoid heavy bloat (which drives up hosting costs and prevents local developer adoption), while ensuring robustness to handle asynchronous agent operations.

## Storage & Metastore

| Requirement | Proposed Tech | Why? | Pros | Cons |
| :--- | :--- | :--- | :--- | :--- |
| **Core Versioning** | Git (Core) | Developers already know it. It operates perfectly completely offline. | Ubiquitous, perfectly maps file history, fast algorithms. | Was not designed to natively store AI metadata (Intents, reasoning traces). |
| **Metadata DB** | SQLite | We need a relational mapping of `Intents <-> PRs <-> Test Suites`. Postgres is too heavy to demand install on a user's laptop. SQLite allows `freshd` to be a single binary drop-in that just works. | Zero config, single file DB, lightning fast locally. | Lacks native high-availability for massive SaaS scaling (but we are prioritizing local-first/open-source). |

## Search & Context Engine

**Why do we need a Knowledge Graph / Vector DB?**
When human developers fix a bug, they search for the exact class name or rely on IDE references. When AI Agents fix a bug based on an intent like "Fix the race condition in the auth flow," they do not inherently know which files handle auth. 
A Vector DB translates English intents into mathematical vectors and instantly surfaces semantically related files and past architectural decisions. Without it, the AI will hallucinate file paths or require dumping the entire 100,000-line codebase into context (expensive and slow).

| Requirement | Proposed Tech | Why? | Pros | Cons |
| :--- | :--- | :--- | :--- | :--- |
| **Vector DB** | LanceDB (or embedded Chroma) | Instead of relying on a cloud provider like Pinecone, LanceDB embeds directly into the local application process, functioning on local multidimensional arrays. | Completely local, avoids network latency, no SaaS fees. | Requires local indexing overhead on large codebases. |

## Orchestration & Agent Queueing

In the original plan, Temporal.io was proposed. We must re-evaluate this based on our "Local-First / Open-Source" mandate.

### The Temporal.io Analysis
**Pros:** 
- Bulletproof state machines. If an LLM Agent takes 20 minutes to resolve a task and the local machine reboots halfway through, Temporal instantly resumes exactly from the last step.
- Built-in UI for viewing exactly where an agent is stuck.

**Cons:** 
- Massive overhead. Standing up Temporal requires running its servers, workers, and a Postgres/Cassandra backend just to get started. 
- Defeats the "pain-free, zero-config" mandate for open-source adoption.

### The Solution: A Two-Tier Orchestration approach
We do not use Temporal.io for the core open-source install. 
1.  **Local Mode (Default):** `freshd` utilizes a lightweight file-backed task queue built on top of SQLite. It handles standard retries, exponential backoffs for API limits, and simple pod orchestration natively without demanding heavy daemon setups.
2.  **SaaS/Enterprise Mode:** The architecture is designed via interfaces so that an enterprise with 5,000 agents can point the orchestrator adapter to Temporal.io if they choose to scale massively in the cloud.

## Summary of the Tech Stack
1. **Runner / Daemon**: Go or Rust binary (`freshd`), managing file watching and task queues locally.
2. **Metadata**: Embedded SQLite + Embedded LanceDB.
3. **Execution Sandboxing**: Ephemeral Docker compose spins via local Linux sockets.
4. **Agent Logic Layer**: Python / Node API adapters handling the specific prompt executions.
