from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from db.models import Intent
from db.engine import get_session
from core.agent import BuilderPod
from core.sandbox import SandboxManager
from rich.console import Console

console = Console()

from core.indexer import reindex_files
import os


class SwarmManager:
    def __init__(self):
        self.session = get_session()
        self.builder = BuilderPod()
        self.sandbox = SandboxManager()

    def process_intents(self):
        hot_context = {}
        updates_since_sync = 0

        try:
            intents = (
                self.session.query(Intent).filter(Intent.status == "PENDING").all()
            )
            if not intents:
                console.print(
                    "[bold yellow]No PENDING intents found in the Vector Metastore.[/bold yellow]"
                )
                return

            for intent in intents:
                console.print(
                    f"\n[bold magenta]--- Background Agent processing Intent {intent.id} ---[/bold magenta]"
                )
                console.print(f"[white]Goal:[/white] {intent.description}")
                try:
                    intent.status = "IN_PROGRESS"
                    self.session.commit()

                    response, applied_files = self.builder.execute_intent(
                        intent.description, hot_context=hot_context
                    )
                    console.print(
                        f"\n[dim]Raw BuilderPod Trace Output:[/dim]\n{response}"
                    )

                    if applied_files:
                        console.print(
                            f"\n[bold cyan]Agent applied {len(applied_files)} patches. Initiating Sandbox verification...[/bold cyan]"
                        )
                        tests_passed, test_logs = self.sandbox.execute_tests()
                        if tests_passed:
                            console.print(
                                "[bold green]Isolated Tests Passed. Committing to main.[/bold green]"
                            )
                            intent.status = "RESOLVED"

                            import subprocess
                            from db.models import FreshCommit

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
                                self.session.add(
                                    FreshCommit(intent_id=intent.id, git_sha=git_sha)
                                )

                            for fpath in applied_files:
                                if os.path.exists(fpath):
                                    with open(fpath, "r", encoding="utf-8") as f:
                                        hot_context[fpath] = f.read()
                            updates_since_sync += 1

                            if updates_since_sync >= 5:
                                console.print(
                                    "[bold cyan]Delta Vector Sync triggered. Flushing Hot Context to LanceDB...[/bold cyan]"
                                )
                                reindex_files(list(hot_context.keys()))
                                hot_context.clear()
                                updates_since_sync = 0

                        else:
                            console.print(
                                "[bold red]Tests Failed in Sandbox! Logic branch reverted.[/bold red]"
                            )
                            console.print(f"[dim]{test_logs}[/dim]")
                            intent.status = "REVERTED"
                            os.system("git checkout -- . && git clean -fd")
                        self.session.commit()
                    else:
                        console.print(
                            "[bold yellow]No code files generated. Intent resolved as discussion/clarification.[/bold yellow]"
                        )
                        intent.status = "RESOLVED"
                        self.session.commit()
                except Exception as e:
                    console.print(
                        f"[bold red]Exception during orchestration of intent {intent.id}:[/bold red] {str(e)}"
                    )
                    self.session.rollback()

            # Final sync if the swarm finishes and queue ends
            if hot_context:
                console.print(
                    "[bold cyan]Swarm loop finalizing. Flushing remaining Hot Context to LanceDB...[/bold cyan]"
                )
                reindex_files(list(hot_context.keys()))
                hot_context.clear()

        except Exception as e:
            console.print(f"[bold red]Critical Swarm Query Error:[/bold red] {str(e)}")
        finally:
            self.session.close()
