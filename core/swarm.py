"""
SwarmManager: Asynchronous Dependency-Aware Orchestration Engine.

For 1 intent: runs directly on main (zero overhead).
For 2+ intents: classifies dependencies via IntentScheduler, executes
independent groups in parallel on isolated git worktrees, and merges
results back to main via the Ordered Gate.
"""

import os
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from db.models import Intent, FreshCommit, Run
from db.engine import get_session
from core.agent import BuilderPod
from core.sandbox import SandboxManager
from core.scheduler import IntentScheduler
from core.indexer import reindex_files
from core.token_tracker import TokenTracker
from core.config import get_max_intents
from core.git_utils import (
    run_git_command,
    merge_intent_branch,
    delete_branch,
    add_worktree,
    remove_worktree,
    prune_worktrees,
    is_repo_dirty,
    commit_changes,
)
from rich.console import Console
from rich.prompt import Prompt, Confirm

console = Console()

# Thread lock for merge gate (serialized merges only)
_merge_lock = threading.Lock()


def _format_files(file_list: list[str], cwd: str = None):
    """Run black on only the specified files, not the entire repo."""
    py_files = [f for f in file_list if f.endswith(".py")]
    if not py_files:
        return
    try:
        # If cwd is provided, files are relative to it
        cmd = ["black", "--quiet"] + py_files
        subprocess.run(cmd, capture_output=True, cwd=cwd)
    except Exception:
        pass


class SwarmManager:
    """
    Orchestrates intent execution with dependency-aware parallel scheduling.
    Uses git worktrees for true filesystem isolation between parallel agents.
    """

    def __init__(self):
        self.scheduler = IntentScheduler()
        self.hot_context = {}
        self.updates_since_sync = 0
        # Buffer for completed branch results awaiting merge
        self._completed = {}
        # Session-wide token tracker
        self.tracker = TokenTracker()

    def process_intents(self):
        """
        Main entry point. Queries pending intents, classifies them,
        and dispatches execution groups in parallel.
        """
        session = get_session()
        # Record the current branch so we can return to it later
        from core.git_utils import get_current_branch

        self.original_branch = get_current_branch() or "main"

        try:
            # Recovery Logic: Recover orphaned intents from crashed prior runs
            stale = (
                session.query(Intent)
                .filter(Intent.status.in_(["IN_PROGRESS", "NEEDS_REVIEW"]))
                .all()
            )
            if stale:
                console.print(
                    f"[bold yellow]Recovering {len(stale)} orphaned intent(s) "
                    f"from a prior crashed run...[/bold yellow]"
                )
                for s in stale:
                    console.print(f"  Intent {s.id} ({s.status}) → reset to PENDING")
                    s.status = "PENDING"
                session.commit()

            intents = session.query(Intent).filter(Intent.status == "PENDING").all()
            if not intents:
                console.print(
                    "[bold yellow]No PENDING intents found in the "
                    "Vector Metastore.[/bold yellow]"
                )
                return

            # --- HUMAN SAFETY NET INTERCEPTOR ---
            if is_repo_dirty():
                console.print(
                    "\n[bold yellow]⚠️  UNCOMMITTED CHANGES DETECTED  ⚠️[/bold yellow]"
                )
                console.print(
                    "To prevent data loss, you should secure your work before the swarm starts."
                )

                choice = Prompt.ask(
                    "What would you like to do?",
                    choices=["s", "c", "a"],
                    default="s",
                )
                # s = stash, c = commit, a = abort

                if choice == "a":
                    console.print("[bold red]Swarm aborted by user.[/bold red]")
                    return
                elif choice == "c":
                    msg = Prompt.ask(
                        "Enter commit message", default="FreshBase: Manual checkpoint"
                    )
                    if commit_changes(msg):
                        console.print(
                            "[bold green]Changes committed successfully.[/bold green]"
                        )
                    else:
                        console.print(
                            "[bold red]Commit failed. Aborting swarm.[/bold red]"
                        )
                        return
                elif choice == "s":
                    # We use a dedicated stash name for easy recovery
                    subprocess.run(
                        [
                            "git",
                            "stash",
                            "push",
                            "-u",
                            "-m",
                            f"FreshBase Safety Stash: {int(time.time())}",
                        ]
                    )
                    console.print(
                        "[bold green]Changes stashed successfully. (Recover with `git stash pop`)[/bold green]"
                    )
            # --- END INTERCEPTOR ---

            # Auto-index if the vector store is empty (Q22)
            self._ensure_indexed()

            # Set total intent count for progress tracking
            self.tracker.total_intents = len(intents)

            # Budget guardrail: confirm if exceeding configurable threshold
            max_intents = get_max_intents()
            if len(intents) > max_intents:
                from rich.prompt import Confirm

                console.print(
                    f"[bold yellow]You are about to process {len(intents)} "
                    f"intents (threshold: {max_intents}). This may consume "
                    f"significant API tokens.[/bold yellow]"
                )
                if not Confirm.ask("Continue?"):
                    console.print("[dim]Swarm cancelled by user.[/dim]")
                    return

            if len(intents) == 1:
                self._execute_single(intents[0], session)
            else:
                self._execute_parallel(intents, session)

            # Process any NEEDS_REVIEW intents interactively
            self._process_deferred(session)

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
            # Display session summary and persist
            console.print(self.tracker.render_summary())
            self.tracker.flush_to_db()

            self._recover_git_state()
            # Prune orphaned sandbox images
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
            session.close()

    # ------------------------------------------------------------------ #
    #  Single Intent Path (direct on main, no branching)
    # ------------------------------------------------------------------ #

    def _execute_single(self, intent, session):
        """Execute a single intent directly on main with no branching overhead."""
        console.print(
            f"\n[bold magenta]--- Processing Intent {intent.id} ---[/bold magenta]"
        )
        console.print(f"[white]Goal:[/white] {intent.description}")

        try:
            intent.status = "IN_PROGRESS"
            session.commit()

            builder = BuilderPod(interactive=True, tracker=self.tracker)
            response, applied_files = builder.execute_intent(
                intent.description, hot_context=self.hot_context
            )
            console.print(f"\n[dim]Raw BuilderPod Trace Output:[/dim]\n{response}")

            if applied_files:
                console.print(
                    f"\n[bold cyan]Agent applied {len(applied_files)} patches. "
                    f"Initiating Sandbox verification...[/bold cyan]"
                )
                sandbox = SandboxManager()
                tests_passed, test_logs = sandbox.execute_tests()
                self.tracker.record_resource("docker")

                # Record the Run for audit trail
                run = Run(
                    intent_id=intent.id,
                    branch_name="main",
                    tests_passed=tests_passed,
                    logs=test_logs[:5000],
                )
                session.add(run)

                if tests_passed:
                    console.print(
                        "[bold green]Isolated Tests Passed. "
                        "Committing to main.[/bold green]"
                    )
                    self._commit_intent(intent, applied_files, session)
                    self.tracker.record_intent_result(resolved=True)
                    console.print(self.tracker.render_status_bar())
                else:
                    console.print(
                        "[bold red]Tests Failed in Sandbox! "
                        "Logic branch reverted.[/bold red]"
                    )
                    console.print(f"[dim]{test_logs}[/dim]")
                    intent.status = "REVERTED"
                    self.tracker.record_intent_result(resolved=False)
                    os.system("git checkout -- . && git clean -fd")
                session.commit()
            else:
                console.print(
                    "[bold yellow]No code files generated. "
                    "Intent resolved as discussion/clarification.[/bold yellow]"
                )
                intent.status = "RESOLVED"
                session.commit()
        except Exception as e:
            console.print(
                f"[bold red]Exception during orchestration of "
                f"intent {intent.id}:[/bold red] {str(e)}"
            )
            session.rollback()

    # ------------------------------------------------------------------ #
    #  Multi-Intent Parallel Path
    # ------------------------------------------------------------------ #

    def _execute_parallel(self, intents, session):
        """
        Classify intents into dependency groups, execute groups in parallel
        using git worktrees, then merge all results via the Ordered Gate.
        """
        groups = self.scheduler.classify(intents, tracker=self.tracker)

        console.print(
            f"\n[bold magenta]Launching parallel execution across "
            f"{len(groups)} group(s)...[/bold magenta]"
        )

        # Ensure clean worktree directory
        os.makedirs(".fresh_worktrees", exist_ok=True)

        # Each group runs as a thread with its own session and worktrees
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
        self._ordered_gate_merge(intents, session)

    def _execute_group(self, group):
        """
        Execute a sequential chain of intents on isolated worktrees.
        Each thread gets its own SQLAlchemy session.
        Intents within a group build on each other sequentially.
        """
        thread_session = get_session()
        group_hot_context = {}

        # Chained Dependency Logic: Start from the active branch, then build on each success
        from core.git_utils import get_current_branch

        current_base_branch = get_current_branch() or "main"

        for intent in group:
            # Re-fetch the intent in this thread's session
            local_intent = thread_session.query(Intent).get(intent.id)

            console.print(
                f"\n[bold magenta]--- Background Agent processing "
                f"Intent {local_intent.id} ---[/bold magenta]"
            )
            console.print(f"[white]Goal:[/white] {local_intent.description}")

            try:
                local_intent.status = "IN_PROGRESS"
                thread_session.commit()

                # Create an isolated worktree branched from the current chain head
                worktree_path = add_worktree(
                    local_intent.id, base_branch=current_base_branch
                )
                if not worktree_path:
                    console.print(
                        f"[bold red]Failed to create worktree for "
                        f"intent {local_intent.id}[/bold red]"
                    )
                    local_intent.status = "REVERTED"
                    thread_session.commit()
                    continue

                abs_worktree = os.path.abspath(worktree_path)

                # Execute the BuilderPod targeting the worktree directory
                builder = BuilderPod(
                    interactive=False, tracker=self.tracker, project_root=abs_worktree
                )
                merged_context = {**self.hot_context, **group_hot_context}

                # Trim hot context to fit within model's context window (Q24)
                merged_context = self.tracker.trim_hot_context(
                    merged_context, builder.model_name
                )

                try:
                    response, applied_files = builder.execute_intent(
                        local_intent.description, hot_context=merged_context
                    )
                    console.print(
                        f"\n[dim]Raw BuilderPod Trace Output:[/dim]\n{response}"
                    )

                    if applied_files:
                        # Check if this was a PROMPT_DIRECTOR deferral
                        if not applied_files and "<PROMPT_DIRECTOR>" in response:
                            local_intent.status = "NEEDS_REVIEW"
                            thread_session.commit()
                            self._completed[local_intent.id] = {
                                "branch": f"fresh/intent-{local_intent.id}",
                                "files": [],
                                "status": "DEFERRED",
                            }
                            continue

                        console.print(
                            f"\n[bold cyan]Agent applied {len(applied_files)} "
                            f"patches. Initiating Sandbox verification..."
                            f"[/bold cyan]"
                        )
                        # Sandbox tests from the worktree directory
                        sandbox = SandboxManager(root_dir=abs_worktree)
                        tests_passed, test_logs = sandbox.execute_tests()

                        # Record the Run
                        run = Run(
                            intent_id=local_intent.id,
                            branch_name=f"fresh/intent-{local_intent.id}",
                            tests_passed=tests_passed,
                            logs=test_logs[:5000],
                        )
                        thread_session.add(run)
                        thread_session.commit()

                        if tests_passed:
                            console.print(
                                f"[bold green]Intent {local_intent.id}: "
                                f"Isolated Tests Passed. Branch ready "
                                f"for merge.[/bold green]"
                            )
                            # Commit on the worktree's branch
                            _format_files(applied_files, cwd=abs_worktree)
                            subprocess.run(
                                ["git", "add", "."],
                                capture_output=True,
                                cwd=abs_worktree,
                            )
                            subprocess.run(
                                [
                                    "git",
                                    "commit",
                                    "--no-verify",
                                    "-m",
                                    f"FreshBase Semantic Resolve: "
                                    f"Intent {local_intent.id}",
                                ],
                                capture_output=True,
                                cwd=abs_worktree,
                            )

                            # Track files for hot context within group
                            for fpath in applied_files:
                                full = os.path.join(abs_worktree, fpath)
                                if os.path.exists(full):
                                    with open(full, "r", encoding="utf-8") as f:
                                        group_hot_context[fpath] = f.read()

                            self._completed[local_intent.id] = {
                                "branch": f"fresh/intent-{local_intent.id}",
                                "files": applied_files,
                                "status": "PASSED",
                            }
                            # Chain the next intent in this group to this successful branch
                            current_base_branch = f"fresh/intent-{local_intent.id}"
                        else:
                            console.print(
                                f"[bold red]Intent {local_intent.id}: "
                                f"Tests Failed in Sandbox![/bold red]"
                            )
                            console.print(f"[dim]{test_logs}[/dim]")
                            self._completed[local_intent.id] = {
                                "branch": f"fresh/intent-{local_intent.id}",
                                "files": [],
                                "status": "FAILED",
                            }
                    else:
                        # Check for PROMPT_DIRECTOR deferral
                        if "<PROMPT_DIRECTOR>" in response:
                            console.print(
                                f"[bold yellow]Intent {local_intent.id}: "
                                f"Requires human review. Deferred.[/bold yellow]"
                            )
                            local_intent.status = "NEEDS_REVIEW"
                            thread_session.commit()
                            self._completed[local_intent.id] = {
                                "branch": f"fresh/intent-{local_intent.id}",
                                "files": [],
                                "status": "DEFERRED",
                            }
                        else:
                            console.print(
                                f"[bold yellow]Intent {local_intent.id}: "
                                f"No code files generated. Agent verified "
                                f"goal is already satisfied.[/bold yellow]"
                            )
                            local_intent.status = "RESOLVED"

                            # Link current state to this intent so it can be reverted/tracked
                            from core.git_utils import get_latest_commit_sha

                            git_sha = get_latest_commit_sha()
                            if git_sha:
                                try:
                                    existing = (
                                        thread_session.query(FreshCommit)
                                        .filter(FreshCommit.git_sha == git_sha)
                                        .first()
                                    )
                                    if not existing:
                                        thread_session.add(
                                            FreshCommit(
                                                intent_id=local_intent.id,
                                                git_sha=git_sha,
                                            )
                                        )
                                except Exception:
                                    thread_session.rollback()

                            thread_session.commit()
                            self._completed[local_intent.id] = {
                                "branch": f"fresh/intent-{local_intent.id}",
                                "files": [],
                                "status": "NO_OUTPUT",
                            }
                            # Maintain the chain even for no-output resolutions
                            current_base_branch = f"fresh/intent-{local_intent.id}"

                finally:
                    # No longer need os.chdir cleanup
                    pass

                # Clean up the worktree (branch is preserved for merge)
                remove_worktree(local_intent.id)

            except Exception as e:
                console.print(
                    f"[bold red]Exception during intent {local_intent.id}: "
                    f"{str(e)}[/bold red]"
                )
                remove_worktree(local_intent.id)
                self._completed[local_intent.id] = {
                    "branch": f"fresh/intent-{local_intent.id}",
                    "files": [],
                    "status": "ERROR",
                }

        thread_session.close()

    # ------------------------------------------------------------------ #
    #  Ordered Gate: Sequential Merge in Queue Order
    # ------------------------------------------------------------------ #

    def _ordered_gate_merge(self, intents, session):
        """
        Merge completed branches into main strictly in original queue order.
        """
        console.print(
            "\n[bold cyan]--- Ordered Gate: Merging branches into "
            "main ---[/bold cyan]"
        )

        for intent in intents:
            # Re-fetch in the main session
            local_intent = session.query(Intent).get(intent.id)
            result = self._completed.get(intent.id)

            if not result:
                console.print(
                    f"[dim]Intent {intent.id}: No result found, skipping.[/dim]"
                )
                continue

            branch = result["branch"]

            if result["status"] == "PASSED":
                console.print(
                    f"[bold cyan]Merging Intent {intent.id} "
                    f"into main...[/bold cyan]"
                )

                with _merge_lock:
                    success, err = merge_intent_branch(intent.id)

                    if success:
                        _format_files(result["files"])
                        run_git_command(["add", "."])
                        run_git_command(
                            [
                                "commit",
                                "--no-verify",
                                "-m",
                                f"FreshBase Semantic Resolve: Intent {intent.id}",
                            ]
                        )

                        git_sha = subprocess.run(
                            ["git", "rev-parse", "HEAD"],
                            capture_output=True,
                            text=True,
                        ).stdout.strip()

                        if git_sha:
                            try:
                                # Avoid IntegrityError: If this SHA is already tracked, just link it
                                existing = (
                                    session.query(FreshCommit)
                                    .filter(FreshCommit.git_sha == git_sha)
                                    .first()
                                )
                                if not existing:
                                    session.add(
                                        FreshCommit(
                                            intent_id=intent.id, git_sha=git_sha
                                        )
                                    )
                                session.commit()
                            except Exception:
                                # If a race condition or collision occurs, rollback and continue
                                session.rollback()
                                console.print(
                                    f"[dim]Note: Intent {intent.id} linked to existing commit {git_sha[:8]}[/dim]"
                                )

                        local_intent.status = "RESOLVED"

                        # Update hot context
                        for fpath in result["files"]:
                            if os.path.exists(fpath):
                                with open(fpath, "r", encoding="utf-8") as f:
                                    self.hot_context[fpath] = f.read()
                        self.updates_since_sync += 1

                        if self.updates_since_sync >= 5:
                            console.print(
                                "[bold cyan]Delta Vector Sync triggered.[/bold cyan]"
                            )
                            reindex_files(list(self.hot_context.keys()))
                            self.hot_context.clear()
                            self.updates_since_sync = 0

                        console.print(
                            f"[bold green]Intent {intent.id}: "
                            f"Successfully merged into main.[/bold green]"
                        )
                    else:
                        console.print(
                            f"[bold red]Intent {intent.id}: Merge conflict. "
                            f"Marked as reverted.[/bold red]"
                        )
                        run_git_command(["reset", "--hard", "HEAD"])
                        local_intent.status = "REVERTED"

            elif result["status"] == "FAILED":
                local_intent.status = "REVERTED"
                console.print(
                    f"[dim]Intent {intent.id}: Sandbox failed, skipping.[/dim]"
                )

            elif result["status"] == "NO_OUTPUT":
                local_intent.status = "RESOLVED"
                console.print(
                    f"[dim]Intent {intent.id}: No output, "
                    f"resolved as discussion.[/dim]"
                )

            elif result["status"] == "DEFERRED":
                console.print(
                    f"[dim]Intent {intent.id}: Deferred for "
                    f"interactive review.[/dim]"
                )

            elif result["status"] == "ERROR":
                local_intent.status = "REVERTED"
                console.print(f"[dim]Intent {intent.id}: Execution error.[/dim]")

            session.commit()

            # Cleanup the feature branch (skip deferred — they re-run later)
            if result["status"] != "DEFERRED":
                delete_branch(branch)

    # ------------------------------------------------------------------ #
    #  Deferred NEEDS_REVIEW Processing
    # ------------------------------------------------------------------ #

    def _process_deferred(self, session):
        """
        After parallel execution, process any NEEDS_REVIEW intents
        interactively in single-intent mode.
        """
        deferred = (
            session.query(Intent)
            .filter(Intent.status == "NEEDS_REVIEW")
            .order_by(Intent.id)
            .all()
        )
        if not deferred:
            return

        console.print(
            f"\n[bold yellow]--- {len(deferred)} intent(s) require "
            f"interactive review ---[/bold yellow]"
        )

        for intent in deferred:
            intent.status = "PENDING"
            session.commit()
            self._execute_single(intent, session)

    # ------------------------------------------------------------------ #
    #  Crash Recovery
    # ------------------------------------------------------------------ #

    def _recover_git_state(self):
        """
        Ensure the repo is back on the original branch in a clean state.
        Called in the finally block.
        """
        try:
            target = getattr(self, "original_branch", "main")
            run_git_command(["checkout", target])
            run_git_command(["reset", "--hard", "HEAD"])
            run_git_command(["clean", "-fd"])
            prune_worktrees()

            if os.path.exists(".fresh_worktrees"):
                shutil.rmtree(".fresh_worktrees", ignore_errors=True)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _ensure_indexed(self):
        """
        Check if the vector store has been populated. If empty, auto-trigger
        indexing so the RAG pipeline and dependency classifier have context.
        """
        try:
            from db.vector_store import get_vector_db

            db = get_vector_db()
            if "code_chunks" not in db.table_names():
                console.print(
                    "[bold yellow]Vector store is empty. Auto-indexing "
                    "codebase for RAG context...[/bold yellow]"
                )
                from core.indexer import index_repo

                count = index_repo()
                console.print(
                    f"[bold green]Auto-indexed {count} code chunks "
                    f"into LanceDB.[/bold green]"
                )
            else:
                table = db.open_table("code_chunks")
                if len(table) == 0:
                    console.print(
                        "[bold yellow]Vector store is empty. Auto-indexing "
                        "codebase for RAG context...[/bold yellow]"
                    )
                    from core.indexer import index_repo

                    count = index_repo()
                    console.print(
                        f"[bold green]Auto-indexed {count} code chunks "
                        f"into LanceDB.[/bold green]"
                    )
        except Exception as e:
            console.print(f"[dim]Auto-index check skipped: {e}[/dim]")

    def _commit_intent(self, intent, applied_files, session):
        """Commit a resolved intent directly on main (single-intent path)."""
        _format_files(applied_files)
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
            session.add(FreshCommit(intent_id=intent.id, git_sha=git_sha))

        intent.status = "RESOLVED"

        for fpath in applied_files:
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    self.hot_context[fpath] = f.read()
        self.updates_since_sync += 1

        if self.updates_since_sync >= 5:
            console.print("[bold cyan]Delta Vector Sync triggered.[/bold cyan]")
            reindex_files(list(self.hot_context.keys()))
            self.hot_context.clear()
            self.updates_since_sync = 0
