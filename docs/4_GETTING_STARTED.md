# Getting Started with FreshBase

FreshBase is designed to be a globally available orchestration tool on your machine. You can use it across as many repositories as you want. 

Here is precisely how you start using it.

## Step 1: Install the `fresh` CLI globally
The FreshBase codebase acts as a standard Python library. You should install this CLI tool onto your machine globally.

To use the `fresh` command anywhere in your terminal, clone the `FreshBase` repository, navigate to the root directory, and run:
```bash
pip install -e .
```
*(This installs FreshBase in "editable mode", meaning any updates or custom forks to the FreshBase code instantly apply to your global `fresh` CLI tool).*

## Step 2: Configure your API Key
FreshBase's **Knowledge Engine** and **Builder Pod** default to OpenAI for embeddings and logic synthesis. 
Export your API key in your terminal session (or add it to your `~/.bashrc` / `~/.zshrc`):
```bash
export OPENAI_API_KEY="your-api-key-here"
```

## Step 3: Initialize a Target Repository
You do not use FreshBase by dropping code *into* the FreshBase install folder. Instead, FreshBase is the tool you bring to *other* project folders.

Navigate to **any other codebase** on your machine (e.g., an existing software project, or a brand new empty folder where you want to write a new app).
```bash
cd /path/to/your/custom_project
git init
fresh init
```
*The `fresh init` command sets up the hidden SQLite metastore specifically for that codebase to track intents.*

## Step 4: Index the Codebase
Whenever you want the Agent Swarm to "read" the codebase, you build the Vector Index:
```bash
fresh index
```
*This parses all local files and stores them mathematically in the local LanceDB so agents don't hallucinate file paths when they write code.*

## Step 5: Issue your first 'Intent'
Instead of writing code yourself, command the Builder Pod to propose and apply code directly:
```bash
fresh build "Add a secondary green button to the homepage and write a Pytest for it"
```
*The Swarm will analyze the `LanceDB` vectors to find the homepage, and physically write the updated files.* 

## Step 6: Verify the Invariants
After generating or modifying code, always verify the Triangle of Trust:
```bash
fresh verify
```
*This locally clones your directory into a stateless Docker container and runs tests. If tests pass, the LLM didn't break core functionality.*
