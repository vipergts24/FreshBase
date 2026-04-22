import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"), override=True)

import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"), override=True)

import typer
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
import shutil
import subprocess
from db.engine import init_db, get_session
from db.models import Intent, FreshCommit
from core.indexer import index_repo
from core.agent import BuilderPod
from core.sandbox import SandboxManager
from core.resolution import ResolutionSwarm
from core.swarm import SwarmManager
from core.config import set_global_model, set_sandbox_type

app = typer.Typer(help="FreshBase: Autonomous Semantic Code Collaboration")
console = Console()


@app.command()
def init():
    console.print("[bold green]Initializing FreshBase...[/bold green]")
    init_db()

    # Configure post-commit hook for out-of-band tracking
    if os.path.exists(".git"):
        hooks_dir = os.path.join(".git", "hooks")
        os.makedirs(hooks_dir, exist_ok=True)
        hook_path = os.path.join(hooks_dir, "post-commit")
        hook_script = "#!/bin/sh\nfresh sync-commits\n"
        with open(hook_path, "w") as f:
            f.write(hook_script)
        os.chmod(hook_path, 0o755)

    console.print("Successfully initialized semantic tracking in .fresh/")


@app.command()
def index():
    console.print(
        "[bold blue]Indexing codebase for the Knowledge Engine (Vector DB)...[/bold blue]"
    )
    try:
        count = index_repo()
        console.print(
            f"[bold green]Successfully indexed {count} code chunks into the local Data Vector database.[/bold green]"
        )
    except Exception as e:
        console.print(f"[bold red]Indexing Failed:[/bold red] {str(e)}")


@app.command()
def build(intent: str):
    console.print(
        f"[bold magenta]Assigning intent to Builder Pod:[/bold magenta] {intent}"
    )
    pod = BuilderPod()
    with console.status(
        "[bold yellow]Agent Swarm is synthesizing logic and modifying files...[/bold yellow]",
        spinner="dots",
    ):
        response, applied_files = pod.execute_intent(intent)
    console.print("\n[bold cyan]Builder Pod Output:[/bold cyan]")
    console.print(response)
    if applied_files:
        console.print(
            "\n[bold green]Files successfully written to disk by Agent:[/bold green]"
        )
        for f in applied_files:
            console.print(f"  - {f}")
    else:
        console.print(
            "\n[bold yellow]No structural <FILE> modifications were detected in the Agent's output.[/bold yellow]"
        )


@app.command()
def verify():
    console.print(
        "[bold cyan]Initializing zero-config execution sandbox...[/bold cyan]"
    )
    sandbox = SandboxManager()
    with console.status(
        "Building and running Verification Container...", spinner="bouncingBar"
    ):
        success, logs = sandbox.execute_tests()
    if success:
        console.print(
            "[bold green]Verification Passed! Triangle of Trust maintained.[/bold green]"
        )
    else:
        console.print("[bold red]Verification Failed. Invariant broken.[/bold red]")
    console.print("\n[bold cyan]Sandbox Test Logs:[/bold cyan]")
    console.print(logs)


@app.command()
def revert(intent_id: str):
    console.print(
        f"[bold red]Triggering Resolution Swarm for Intent Checkout: {intent_id}[/bold red]"
    )
    swarm = ResolutionSwarm()
    with console.status("Navigating Semantic Dependency Graph...", spinner="runner"):
        result = swarm.execute_semantic_revert(intent_id)
    console.print(result)


@app.command()
def queue(description: str):
    console.print(f"Queueing a new intent: {description}")
    session = get_session()
    intent = Intent(description=description, status="PENDING")
    session.add(intent)
    session.commit()
    console.print("[bold green]Intent queued successfully.[/bold green]")


@app.command()
def swarm():
    console.print("[bold magenta]Launching Swarm Manager...[/bold magenta]")
    swarm_manager = SwarmManager()
    swarm_manager.process_intents()
    console.print("[bold green]Swarm execution completed.[/bold green]")


@app.command()
def config():
    console.print("[bold cyan]--- FreshBase Global LLM Configuration ---[/bold cyan]")
    console.print(
        "Select your preferred autonomous reasoning model across all repositories:"
    )
    console.print("1. [bold white]OpenAI[/bold white] (gpt-4o)")
    console.print("2. [bold white]Anthropic[/bold white] (claude-3-5-sonnet-20240620)")
    console.print("3. [bold white]Google[/bold white] (gemini-1.5-pro)")
    console.print("4. [bold white]Meta[/bold white] (groq/llama3-70b-8192)")
    console.print("5. [bold white]DeepSeek[/bold white] (deepseek/deepseek-chat)")

    choice = Prompt.ask(
        "Enter the number of your choice",
        choices=["1", "2", "3", "4", "5"],
        default="1",
    )

    model_map = {
        "1": ("gpt-4o", "OPENAI_API_KEY"),
        "2": ("claude-3-5-sonnet-20240620", "ANTHROPIC_API_KEY"),
        "3": ("gemini-1.5-pro", "GEMINI_API_KEY"),
        "4": ("groq/llama3-70b-8192", "GROQ_API_KEY"),
        "5": ("deepseek/deepseek-chat", "DEEPSEEK_API_KEY"),
    }

    model_name, key_name = model_map[choice]
    set_global_model(model_name)

    # Sandbox Engine Configuration
    console.print("\n[bold cyan]Select your preferred Sandbox Engine:[/bold cyan]")
    console.print(
        "1. [bold white]uv[/bold white] (Host-venv: Ultra Fast, Low Isolation)"
    )
    console.print(
        "2. [bold white]docker[/bold white] (Container: Slow, High Isolation)"
    )

    sb_choice = Prompt.ask(
        "Enter choice",
        choices=["1", "2"],
        default="1",
    )
    sb_type = "uv" if sb_choice == "1" else "docker"
    set_sandbox_type(sb_type)

    console.print(
        f"\n[bold green]Success![/bold green] Global model set to [bold white]{model_name}[/bold white]."
    )
    console.print(f"Sandbox Engine set to [bold white]{sb_type}[/bold white].")
    console.print(
        f"\nPlease ensure you add the following to your [bold yellow].env[/bold yellow] file in your project root:"
    )
    console.print(f'[bold cyan]{key_name}="your-api-key-here"[/bold cyan]')


@app.command()
def log(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show full descriptions without truncation"
    )
):
    console.print("[bold cyan]--- Swarm Intent History ---[/bold cyan]")
    session = get_session()

    intents = session.query(Intent).order_by(Intent.id.desc()).all()
    if not intents:
        console.print(
            "[bold yellow]No intents found in the local FreshBase database.[/bold yellow]"
        )
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Status", width=12)
    table.add_column("Target SHA", width=10)
    table.add_column("Description")

    for intent in intents:
        # Determine color for status
        status_color = "white"
        if intent.status == "PENDING":
            status_color = "yellow"
        elif intent.status == "RESOLVED":
            status_color = "green"
        elif intent.status == "REVERTED":
            status_color = "red"

        status_str = f"[{status_color}]{intent.status}[/{status_color}]"

        # Git SHA mapping
        sha_str = "None"
        if intent.commits:
            sha_str = intent.commits[0].git_sha[:7]

        # Truncate description if extremely long and not verbose
        desc = intent.description
        if not verbose and len(desc) > 60:
            desc = desc[:57] + "..."

        table.add_row(str(intent.id), status_str, sha_str, desc)

    console.print(table)


@app.command()
def reset():
    """Wipes the Swarm log, DB, and Vector metadata cleanly."""
    console.print(
        "\n[bold red]⚠️  WARNING: You are about to initiate a Hard Reset  ⚠️[/bold red]"
    )
    console.print(
        "[yellow]This will permanently delete the following metadata:[/yellow]"
    )
    console.print("  - The FreshBase SQLite Intent History (.fresh/fresh.db)")
    console.print("  - The LanceDB Vector Codebase Memory (.fresh/lancedb/)\n")
    console.print(
        "[green]Rest assured: Your source code and git history will NOT be touched.[/green]\n"
    )

    confirmation = Confirm.ask(
        "[bold red]Are you absolutely sure you want to nuke the Swarm tracking metadata?[/bold red]"
    )

    if confirmation:
        if os.path.exists(".fresh"):
            shutil.rmtree(".fresh")
            console.print("[bold cyan]Metadata wiped.[/bold cyan]")

        init_db()
        console.print(
            "[bold green]FreshBase successfully re-initialized with an empty slate.[/bold green]"
        )
    else:
        console.print("[bold white]Reset aborted.[/bold white]")


@app.command(hidden=True)
def sync_commits():
    """Silently parses manual commits and injects them into the Intent Swarm DB."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        msg = subprocess.run(
            ["git", "log", "-1", "--pretty=%B"], capture_output=True, text=True
        ).stdout.strip()

        # Don't recurse if the swarm built it natively
        if "FreshBase Semantic Resolve: Intent" in msg[:100]:
            return

        session = get_session()
        # Verify it doesn't exist
        existing = session.query(FreshCommit).filter_by(git_sha=sha).first()
        if not existing:
            # It's an out-of-band commit!
            intent = Intent(
                description=f"Manual Commit: {msg[:200]}", status="RESOLVED"
            )
            session.add(intent)
            session.commit()

            f_commit = FreshCommit(intent_id=intent.id, git_sha=sha)
            session.add(f_commit)
            session.commit()
    except Exception:
        pass


@app.command()
def usage(
    show_all: bool = typer.Option(False, "--all", help="Show all sessions"),
    session_id: str = typer.Option(None, "--session", help="Drill into a session"),
):
    """Display historical token usage and cost tracking."""
    from db.models import TokenUsage

    db_session = get_session()

    if session_id:
        # Show detail for a specific session
        record = (
            db_session.query(TokenUsage)
            .filter(TokenUsage.session_id == session_id)
            .first()
        )
        if not record:
            console.print(f"[bold red]Session '{session_id}' not found.[/bold red]")
            return

        table = Table(title=f"Session: {record.session_id}")
        table.add_column("Metric", style="white")
        table.add_column("Value", justify="right", style="cyan")

        table.add_row("Model", record.model or "unknown")
        table.add_row("Prompt Tokens", f"{record.prompt_tokens:,}")
        table.add_row("Completion Tokens", f"{record.completion_tokens:,}")
        table.add_row("Embedding Tokens", f"{record.embedding_tokens:,}")
        table.add_row("LLM Calls", str(record.llm_calls))
        table.add_row("Embedding Calls", str(record.embedding_calls))
        table.add_row("Docker Builds", str(record.docker_builds))
        table.add_row("Intents Processed", str(record.intents_processed))
        table.add_row("Intents Resolved", str(record.intents_resolved))
        table.add_row("Intents Reverted", str(record.intents_reverted))
        table.add_row(
            "Estimated Cost",
            f"[bold green]${record.estimated_cost:.4f}[/bold green]",
        )
        table.add_row("Date", str(record.created_at))

        console.print(table)
    else:
        # Show session list
        limit = None if show_all else 10
        query = db_session.query(TokenUsage).order_by(TokenUsage.created_at.desc())
        if limit:
            query = query.limit(limit)
        records = query.all()

        if not records:
            console.print(
                "[bold yellow]No usage data found. Run `fresh swarm` first.[/bold yellow]"
            )
            return

        table = Table(title="FreshBase Usage History")
        table.add_column("Session", style="cyan")
        table.add_column("Date", style="white")
        table.add_column("Model", style="dim")
        table.add_column("Intents", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Cost", justify="right", style="green")

        total_cost = 0.0
        total_intents = 0

        for r in records:
            total_tokens = r.prompt_tokens + r.completion_tokens + r.embedding_tokens
            intents_str = f"{r.intents_resolved}/{r.intents_processed}"
            date_str = r.created_at.strftime("%b %d, %H:%M") if r.created_at else "N/A"

            table.add_row(
                r.session_id,
                date_str,
                r.model or "unknown",
                intents_str,
                f"{total_tokens:,}",
                f"${r.estimated_cost:.4f}",
            )
            total_cost += r.estimated_cost
            total_intents += r.intents_processed

        console.print(table)
        console.print(
            f"\n[bold]Lifetime Total:[/bold] {len(records)} session(s), "
            f"{total_intents} intents, [bold green]${total_cost:.4f}[/bold green]"
        )

    db_session.close()


if __name__ == "__main__":
    app()
