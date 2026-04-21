# Getting Started with FreshBase

FreshBase is designed to be a globally available orchestration tool on your machine. You can use it across as many repositories as you want. 

## Step 1: Install the `fresh` CLI globally
The FreshBase codebase acts as a standard Python library. You should install this CLI tool onto your machine globally.

To use the `fresh` command anywhere in your terminal, clone the `FreshBase` repository, navigate to the root directory, and run:
```bash
pip install -e .
```
*(This installs FreshBase in "editable mode". Any updates or custom forks instantly apply to your global `fresh` CLI).*

## Step 2: Configure your Environment
FreshBase uses OpenAI for embeddings and logic synthesis via LiteLLM. Create a `.env` file at the root of the targeted repository you are working in:
```bash
OPENAI_API_KEY="sk-..."
```

## Step 3: Initialize a Target Repository
You do not use FreshBase by dropping code *into* the FreshBase install folder. Instead, FreshBase is a tool you bring to *other* project folders.

Navigate to **any other codebase** on your machine (e.g., an existing software project, or a brand new empty folder where you want to write a new app).
```bash
cd /path/to/your/custom_project
git init
fresh init
```
*The `fresh init` command sets up the hidden SQLite metastore specifically for that codebase to track intents.*

## Step 4: Index the Codebase locally
Whenever you want the Agent Swarm to "read" the codebase, you build the Vector Index:
```bash
fresh index
```
*This parses all local files and stores them mathematically in the local LanceDB so agents don't hallucinate file paths when they write code.*

## Step 5: Queue Up Intents
Instead of writing execution commands sequentially, you define business or logic Intents in an asynchronous queue:
```bash
fresh queue "Add a green secondary button to the homepage"
fresh queue "Wire the green button up to trigger a log out sequence"
```
*Intents are tracked persistently via SQLite inside `.fresh/fresh.db`.* 

## Step 6: Unleash the Orchestrator
Launch the multi-agent asynchronous swarm to consume the queue continuously:
```bash
fresh swarm
```
*The Swarm Manager cycles through the pending intents, maintains memory vectors across modifications to prevent Context Drift, fires up Sandboxed validation suites to deterministically test the code before it is allowed in the repository, and explicitly commits the diff securely.*

For advanced test commands, please see [5. Demo Scenarios](5_DEMO_SCENARIOS.md).
