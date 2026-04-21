# Demo Scenarios

Want to see FreshBase operate natively? Here are three powerful terminal sequence demonstrations highlighting the Agent Swarm architecture. These are fully deterministic demonstrations.

Before running any demonstrations, ensure you've run `pip install -e .` on FreshBase, created a `.env` with `OPENAI_API_KEY`, and executed `fresh init` in an empty, `git init`-enabled test directory.

## Scenario 1: The Context Tracker & Resolution Reverts
This sequence will prove that agents inherently track the exact in-memory modified state of sequential executions (preventing Context Drift). Then, we will intentionally rollback the foundational logic dependency in the repository via the CLI to trigger a `Resolution Swarm`, which intelligently refactors your code instead of blindly destroying it.

**Run the Setup:**
```bash
# 1. Base Logic Implementation
fresh queue "Create a python file scripts/demo.py. Add a main() function and a get_greeting() function. Set get_greeting() to return the string 'hello ' and have main print it."

# 2. Sequential Enhancement #1
fresh queue "In scripts/demo.py, add a format_feature() function that uppercases the text. Update get_greeting() to wrap its string in format_feature() before returning."

# 3. Sequential Enhancement #2 (Downstream Dependency)
fresh queue "In scripts/demo.py, modify format_feature() to also replace 'HELLO' with 'WELCOME'. Make no other changes."

# Execute the Swarm
fresh swarm
```

*The Swarm will spin up three agents. You'll notice they perfectly interlink their dependencies without losing track of the immediate code states created seconds prior!*

**Execute the Semantic Revert:**
First, use SQLite (or an SQLite viewer tool) to identify the specific numeric ID of Enhancement #1. 
```bash
# Assuming the enhancement is Intent ID 2:
fresh revert 2
```

*Watch as the Sandbox testing layer realizes that deleting Enhancement #1 severely breaks Enhancement #2's logic, instantly triggering an emergency Resolution Swarm. A new agent spins up, reads the Pytest failure trace natively, and elegantly hardcodes the result of Enhancement #2 to successfully satisfy the tests without violating the revert!*

---

## Scenario 2: Human-In-The-Loop Escalation
This demonstrates how FreshBase catches critical conceptual branching bugs. Rather than writing random guesswork, the BuilderPod suspends execution, drops an interactive trigger, and merges your text responses manually.

**Run the Setup:**
```bash
fresh queue "Create models/cart.py with a ShoppingCart class that stores item names as strings in a list."

fresh queue "We are migrating to microservices. The ShoppingCart in models/cart.py must be ripped out completely. CRITICAL: Do NOT write code yet. You must output <PROMPT_DIRECTOR> to ask the Director which database back-end we should use (Postgres or DynamoDB) before proceeding."

fresh swarm
```

*Instead of the Swarm blindly completing the second task, it will drop out into your live bash pipe and halt process execution: `PROMPT DIRECTOR Question: Which database backend...`. Answer the CLI, and watch the agent instantly implement your decision into the structural patch!*

---

## Scenario 3: Triangle of Trust (Sandbox Protection)
See exactly how FreshBase intercepts untested logic.

**Run the Setup:**
```bash
fresh queue "Write a massive sorting algorithm in a new file algorithms/sort.py, but strictly forbid the inclusion of any pytest or unittest blocks."

fresh swarm
```
*The Agent will construct the sorting logic, but when it passes to the Sandbox verification step, `pytest` will hit Exit Code 5 (No Tests Discovered/Passed). The Orchestration engine will print the output logs natively and subsequently run a `git checkout -- .` to violently erase the hallucination and protect your codebase!*
