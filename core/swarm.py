"""
SwarmManager: Asynchronous Dependency-Aware Orchestration Engine.

For 1 intent: runs directly on main (zero overhead).
For 2+ intents: classifies dependencies via IntentScheduler, executes
independent groups in parallel on isolated git branches, and merges
results back to main via the Ordered Gate.
"""

import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from db.models import Intent, FreshCommit
from db.engine import get_session
from core.agent import BuilderPod
from core.sandbox import SandboxManager
from core.scheduler import IntentScheduler
from core.indexer import reindex_files
from core.git_utils import (
    run_git_command,
    create_intent_branch,
    merge_intent_branch,
    delete_branch,
)
from rich.console import Console

console = Console()

# Thread lock for git operations and shared state
_git_lock = threading.Lock()
_merge_lock = threading.Lock()


class SwarmManager:
    """
    Orchestrates intent execution with dependency-aware parallel scheduling.
    """

    def __init__(self):
        self.session = get_session()
        self.sandbox = SandboxManager()
        self.scheduler = IntentScheduler()
        self.hot_context = {}
        self.updates_since_sync = 0
        # Buffer for completed branch results awaiting merge
        self._completed = {}

    def process_intents(self):
        """
        Main entry point. Queries pending intents, classifies them,
        and dispatches execution groups in parallel.
        """
        try:
            intents = (
                self.session.query(Intent).filter(Intent.status == "PENDING").all()
            )
            if not intents:
                console.print(
                    "[bold yellow]No PENDING intents found in the "
                    "Vector Metastore.[/bold yellow]"
                )
                return

            if len(intents) == 1:
                # Single intent fast-path: execute directly on main
                self._execute_single(intents[0])
            else:
                # Multi-intent: classify → parallelize → Ordered Gate merge
                self._execute_parallel(intents)

            # Final vector sync
            if self.hot_context:
                console.print(
                    "[bold cyan]Swarm loop finalizing. Flushing remaining "
                    "Hot Context to LanceDB...[/bold cyan]"
                )
                reindex_files(list(self.hot_context.keys()))
                self.hot_context.clear()

        except Exception as e:
            console.print(f"[bold red]Critical Swarm Query Error:[/bold red] {str(e)}")
        finally:
            # Prune orphaned sandbox images to prevent zombie disk bloat
            try:
                subprocess.run(
                    [
                        "docker",
                        "image",
                        "prune",
                        "-f",
                        "--filter",
                        "label=freshbase=sandbox",
                    ],
                    capture_output=True,
                )
            except Exception:
                pass
            self.session.close()

    # ------------------------------------------------------------------ #
    #  Single Intent Path (direct on main, no branching)
    # ------------------------------------------------------------------ #

    def _execute_single(self, intent):
        """Execute a single intent directly on main with no branching overhead."""
        console.print(
            f"\n[bold magenta]--- Processing Intent {intent.id} ---[/bold magenta]"
        )
        console.print(f"[white]Goal:[/white] {intent.description}")

        try:
            intent.status = "IN_PROGRESS"
            self.session.commit()

            builder = BuilderPod()
            response, applied_files = builder.execute_intent(
                intent.description, hot_context=self.hot_context
            )
            console.print(f"\n[dim]Raw BuilderPod Trace Output:[/dim]\n{response}")

            if applied_files:
                console.print(
                    f"\n[bold cyan]Agent applied {len(applied_files)} patches. "
                    f"Initiating Sandbox verification...[/bold cyan]"
                )
                tests_passed, test_logs = self.sandbox.execute_tests()

                if tests_passed:
                    console.print(
                        "[bold green]Isolated Tests Passed. "
                        "Committing to main.[/bold green]"
                    )
                    self._commit_intent(intent, applied_files)
                else:
                    console.print(
                        "[bold red]Tests Failed in Sandbox! "
                        "Logic branch reverted.[/bold red]"
                    )
                    console.print(f"[dim]{test_logs}[/dim]")
                    intent.status = "REVERTED"
                    os.system("git checkout -- . && git clean -fd")
                self.session.commit()
            else:
                console.print(
                    "[bold yellow]No code files generated. "
                    "Intent resolved as discussion/clarification.[/bold yellow]"
                )
                intent.status = "RESOLVED"
                self.session.commit()
        except Exception as e:
            console.print(
                f"[bold red]Exception during orchestration of "
                f"intent {intent.id}:[/bold red] {str(e)}"
            )
            self.session.rollback()

    # ------------------------------------------------------------------ #
    #  Multi-Intent Parallel Path
    # ------------------------------------------------------------------ #

    def _execute_parallel(self, intents):
        """
        Classify intents into dependency groups, execute groups in parallel,
        then merge all results via the Ordered Gate.
        """
        groups = self.scheduler.classify(intents)

        console.print(
            f"\n[bold magenta]Launching parallel execution across "
            f"{len(groups)} group(s)...[/bold magenta]"
        )

        # Each group runs as a thread. Within a group, intents run sequentially.
        with ThreadPoolExecutor(max_workers=len(groups)) as executor:
            futures = {}
            for group in groups:
                future = executor.submit(self._execute_group, group)
                futures[future] = group

            for future in as_completed(futures):
                group = futures[future]
                try:
                    future.result()
                except Exception as e:
                    group_ids = [str(i.id) for i in group]
                    console.print(
                        f"[bold red]Execution group [{', '.join(group_ids)}] "
                        f"failed: {str(e)}[/bold red]"
                    )

        # Ordered Gate: merge all completed branches in original queue order
        self._ordered_gate_merge(intents)

    def _execute_group(self, group):
        """
        Execute a sequential chain of intents on isolated branches.
        Each intent in the group gets its own branch for sandbox isolation.
        """
        group_hot_context = {}

        for intent in group:
            console.print(
                f"\n[bold magenta]--- Background Agent processing "
                f"Intent {intent.id} ---[/bold magenta]"
            )
            console.print(f"[white]Goal:[/white] {intent.description}")

            try:
                # Update status
                with _git_lock:
                    intent.status = "IN_PROGRESS"
                    self.session.commit()

                # Create an isolated branch for this intent
                with _git_lock:
                    branch = create_intent_branch(intent.id)
                    if not branch:
                        console.print(
                            f"[bold red]Failed to create branch for "
                            f"intent {intent.id}[/bold red]"
                        )
                        intent.status = "REVERTED"
                        self.session.commit()
                        continue
                    run_git_command(["checkout", branch])

                # Execute the BuilderPod on the isolated branch
                builder = BuilderPod()
                merged_context = {**self.hot_context, **group_hot_context}
                response, applied_files = builder.execute_intent(
                    intent.description, hot_context=merged_context
                )
                console.print(f"\n[dim]Raw BuilderPod Trace Output:[/dim]\n{response}")

                if applied_files:
                    console.print(
                        f"\n[bold cyan]Agent applied {len(applied_files)} "
                        f"patches. Initiating Sandbox verification...[/bold cyan]"
                    )
                    sandbox = SandboxManager()
                    tests_passed, test_logs = sandbox.execute_tests()

                    if tests_passed:
                        console.print(
                            f"[bold green]Intent {intent.id}: Isolated Tests "
                            f"Passed. Branch ready for merge.[/bold green]"
                        )
                        # Commit on the feature branch
                        os.system("black . > /dev/null 2>&1")
                        with _git_lock:
                            run_git_command(["add", "."])
                            run_git_command(
                                [
                                    "commit",
                                    "--no-verify",
                                    "-m",
                                    f"FreshBase Semantic Resolve: Intent {intent.id}",
                                ]
                            )

                        # Track files for hot context within this group
                        for fpath in applied_files:
                            if os.path.exists(fpath):
                                with open(fpath, "r", encoding="utf-8") as f:
                                    group_hot_context[fpath] = f.read()

                        # Mark as ready for the Ordered Gate
                        self._completed[intent.id] = {
                            "branch": branch,
                            "files": applied_files,
                            "status": "PASSED",
                        }
                    else:
                        console.print(
                            f"[bold red]Intent {intent.id}: Tests Failed "
                            f"in Sandbox! Branch discarded.[/bold red]"
                        )
                        console.print(f"[dim]{test_logs}[/dim]")
                        self._completed[intent.id] = {
                            "branch": branch,
                            "files": [],
                            "status": "FAILED",
                        }
                else:
                    console.print(
                        f"[bold yellow]Intent {intent.id}: No code files "
                        f"generated.[/bold yellow]"
                    )
                    self._completed[intent.id] = {
                        "branch": branch,
                        "files": [],
                        "status": "NO_OUTPUT",
                    }

                # Return to main before the next intent in the chain
                with _git_lock:
                    run_git_command(["checkout", "main"])

            except Exception as e:
                console.print(
                    f"[bold red]Exception during intent {intent.id}: "
                    f"{str(e)}[/bold red]"
                )
                with _git_lock:
                    run_git_command(["checkout", "main"])
                self._completed[intent.id] = {
                    "branch": f"fresh/intent-{intent.id}",
                    "files": [],
                    "status": "ERROR",
                }

    # ------------------------------------------------------------------ #
    #  Ordered Gate: Sequential Merge in Queue Order
    # ------------------------------------------------------------------ #

    def _ordered_gate_merge(self, intents):
        """
        Merge completed branches into main strictly in original queue order.
        This preserves intent ordering regardless of which agent finished first.
        """
        console.print(
            "\n[bold cyan]--- Ordered Gate: Merging branches into "
            "main ---[/bold cyan]"
        )

        with _git_lock:
            run_git_command(["checkout", "main"])

        for intent in intents:
            result = self._completed.get(intent.id)

            if not result:
                console.print(
                    f"[dim]Intent {intent.id}: No result found, skipping.[/dim]"
                )
                continue

            branch = result["branch"]

            if result["status"] == "PASSED":
                console.print(
                    f"[bold cyan]Merging Intent {intent.id} into main...[/bold cyan]"
                )

                with _merge_lock:
                    success, err = merge_intent_branch(intent.id)

                    if success:
                        os.system("black . > /dev/null 2>&1")
                        run_git_command(["add", "."])
                        run_git_command(
                            [
                                "commit",
                                "--no-verify",
                                "-m",
                                f"FreshBase Semantic Resolve: Intent {intent.id}",
                            ]
                        )

                        # Record the commit SHA
                        git_sha = subprocess.run(
                            ["git", "rev-parse", "HEAD"],
                            capture_output=True,
                            text=True,
                        ).stdout.strip()

                        if git_sha:
                            self.session.add(
                                FreshCommit(intent_id=intent.id, git_sha=git_sha)
                            )

                        intent.status = "RESOLVED"

                        # Update hot context
                        for fpath in result["files"]:
                            if os.path.exists(fpath):
                                with open(fpath, "r", encoding="utf-8") as f:
                                    self.hot_context[fpath] = f.read()
                        self.updates_since_sync += 1

                        if self.updates_since_sync >= 5:
                            console.print(
                                "[bold cyan]Delta Vector Sync triggered. "
                                "Flushing Hot Context to LanceDB...[/bold cyan]"
                            )
                            reindex_files(list(self.hot_context.keys()))
                            self.hot_context.clear()
                            self.updates_since_sync = 0

                        console.print(
                            f"[bold green]Intent {intent.id}: Successfully "
                            f"merged into main.[/bold green]"
                        )
                    else:
                        console.print(
                            f"[bold red]Intent {intent.id}: Merge conflict "
                            f"detected. Attempting semantic resolution..."
                            f"[/bold red]"
                        )
                        # Abort the failed merge state
                        run_git_command(["reset", "--hard", "HEAD"])
                        intent.status = "REVERTED"

            elif result["status"] == "FAILED":
                intent.status = "REVERTED"
                console.print(
                    f"[dim]Intent {intent.id}: Sandbox failed, "
                    f"skipping merge.[/dim]"
                )

            elif result["status"] == "NO_OUTPUT":
                intent.status = "RESOLVED"
                console.print(
                    f"[dim]Intent {intent.id}: No output, "
                    f"resolved as discussion.[/dim]"
                )

            elif result["status"] == "ERROR":
                intent.status = "REVERTED"
                console.print(
                    f"[dim]Intent {intent.id}: Execution error, "
                    f"marked reverted.[/dim]"
                )

            self.session.commit()

            # Cleanup the feature branch
            delete_branch(branch)

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _commit_intent(self, intent, applied_files):
        """Commit a resolved intent directly on main (single-intent path)."""
        os.system("black . > /dev/null 2>&1")
        os.system("git add .")
        subprocess.run(
            [
                "git",
                "commit",
                "--no-verify",
                "-m",
                f"FreshBase Semantic Resolve: Intent {intent.id}",
            ],
            capture_output=True,
        )
        git_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        ).stdout.strip()

        if git_sha:
            self.session.add(FreshCommit(intent_id=intent.id, git_sha=git_sha))

        intent.status = "RESOLVED"

        for fpath in applied_files:
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    self.hot_context[fpath] = f.read()
        self.updates_since_sync += 1

        if self.updates_since_sync >= 5:
            console.print(
                "[bold cyan]Delta Vector Sync triggered. "
                "Flushing Hot Context to LanceDB...[/bold cyan]"
            )
            reindex_files(list(self.hot_context.keys()))
            self.hot_context.clear()
            self.updates_since_sync = 0
