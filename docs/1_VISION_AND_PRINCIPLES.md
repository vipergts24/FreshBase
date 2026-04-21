# FreshBase: Vision & Core Principles

## The Core Mandate

FreshBase is fundamentally redefining open-source collaboration in the era of artificial intelligence. It must act as the lowest-friction, highest-leverage system for multi-agent software engineering.

To accomplish this, we adhere to the following principles:

### 1. Local-First and Self-Hostable
Just as Git won because it was a decentralized, local-first tool that eventually evolved into centralized hubs (GitHub), FreshBase must be useful from a single laptop without internet dependencies.
*   **The Daemon (`freshd`)**: A lightweight background process that observes file changes, manages local agent queues, and interfaces with the underlying Git protocol.
*   **Data Sovereignty**: The source code, metadata, vector embeddings, and agent histories live entirely in the user's infrastructure by default. No mandatory SaaS cloud connections.

### 2. Pain-Free Development (Zero-Config Emulation)
A major bottleneck for human developers (and agents alike) is environment configuration. To achieve actual velocity, the environment must just work.
*   **Auto-Emulation**: When an agent tests code that connects to a generic PostgreSQL dependency, FreshBase automatically scans the connection string intent, generates an ephemeral `docker-compose.yml`, stands up the database sandbox, runs the agent's tests, and tears it down.
*   **The Human Fallback**: The developer only configures environment states _once_ when the automatic inference fails. From then on, all agent permutations use this cached sandbox logic.

### 3. Agent Agnostic (Bring Your Own Model - BYOM)
FreshBase is the playing field, not the player. While it provides orchestration, it is un-opinionated about the intelligence source.
*   **Pluggable Intelligence**: You can run an open-weights `Llama 3` model entirely strictly on a local GPU, or hook up via API to `Claude 3.5 Sonnet` or `GPT-4o`.
*   **Standardized Agent Interfaces**: Agents interact via a headless standard protocol (FastAPI/gRPC layer) that requires them to return standard JSON structs confirming Intent mappings, test invariants, and exact code patches.

### 4. Deterministic Verification over Probabilistic Generation
Because LLMs are probabilistic, their outputs cannot be trusted on their own—they must be explicitly verified.
*   We shift the trust model. We do not trust the generated _code_; we only trust the deterministic _tests_ that prove the intent was met.
*   The human role elevates from "Code Reviewer" to "Intent/Invariant Approver."
