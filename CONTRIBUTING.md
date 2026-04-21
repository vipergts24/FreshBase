# Contributing to FreshBase

First off, thank you for considering contributing to FreshBase! It's people like you that make open-source such a powerful community. 

FreshBase is aiming to redefine how autonomous agents interact with codebases. Because we are building the orchestration tier that *writes* code, our own standards for stability and deterministic verification are extremely high.

## How Can I Contribute?

### 1. Reporting Bugs
If you find a bug, please create an Issue on GitHub. Include:
*   A clear, descriptive title.
*   Your OS, Python version, and execution environment.
*   The exact `fresh` terminal trace output.
*   Steps to reproduce the bug.

### 2. Suggesting Enhancements
Feature requests are highly encouraged! When proposing a change to the core architecture (e.g., modifying the Swarm Orchestrator or the Vector Engine), please open a "Discussion" or an "Enhancement Issue" first so we can map out the logic before you write any code.

### 3. Pull Requests
1.  **Fork the repo** and create your branch from `main`.
2.  **Ensure tests pass.** If you add a new core feature, you must append tests to the `tests/` directory. Remember, the BuilderPod uses the Sandbox (`pytest`) as its source of truth. Your tests must be deterministic.
3.  **Update documentation.** If your changes alter the CLI commands or logic, update the `docs/` or `README.md` accordingly.
4.  **Format your code.** Try to match the structural patterns established in the repository.

## Local Development Setup

To test FreshBase locally while developing:

1. Clone your fork:
   ```bash
   git clone https://github.com/YOUR-USERNAME/FreshBase.git
   cd FreshBase
   ```
2. Install it in editable mode (this maps the `fresh` CLI command directly to your active repository state):
   ```bash
   pip install -e .
   ```
3. Establish your environment:
   Create a `.env` file at the root:
   ```bash
   OPENAI_API_KEY="sk-..."
   ```

## Architectural Philosophy
Before submitting a PR, please read [1_VISION_AND_PRINCIPLES.md](docs/1_VISION_AND_PRINCIPLES.md). FreshBase operates on the **Triangle of Trust**. Any merged feature must prioritize:
1. **Safety**: Preventing context drift and hallucination.
2. **Determinism**: Code verification is absolute.
3. **Human-in-the-Loop**: The Director ALWAYS retains over-ride capabilities. 

Thank you for contributing!
