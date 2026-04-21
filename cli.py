import os
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.getcwd(), '.env'), override=True)

import os
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.getcwd(), '.env'), override=True)

import typer
from rich.console import Console
from db.engine import init_db, get_session
from db.models import Intent
from core.indexer import index_repo
from core.agent import BuilderPod
from core.sandbox import SandboxManager
from core.resolution import ResolutionSwarm
from core.swarm import SwarmManager

app = typer.Typer(help="FreshBase: Autonomous Semantic Code Collaboration")
console = Console()

@app.command()
def init():
    console.print("[bold green]Initializing FreshBase...[/bold green]")
    init_db()
    console.print("Successfully initialized semantic tracking in .fresh/")

@app.command()
def index():
    console.print("[bold blue]Indexing codebase for the Knowledge Engine (Vector DB)...[/bold blue]")
    try:
        count = index_repo()
        console.print(f"[bold green]Successfully indexed {count} code chunks into the local Data Vector database.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Indexing Failed:[/bold red] {str(e)}")

@app.command()
def build(intent: str):
    console.print(f"[bold magenta]Assigning intent to Builder Pod:[/bold magenta] {intent}")
    pod = BuilderPod()
    with console.status("[bold yellow]Agent Swarm is synthesizing logic and modifying files...[/bold yellow]", spinner="dots"):
        response, applied_files = pod.execute_intent(intent)
    console.print("\n[bold cyan]Builder Pod Output:[/bold cyan]")
    console.print(response)
    if applied_files:
        console.print("\n[bold green]Files successfully written to disk by Agent:[/bold green]")
        for f in applied_files:
            console.print(f"  - {f}")
    else:
        console.print("\n[bold yellow]No structural <FILE> modifications were detected in the Agent's output.[/bold yellow]")

@app.command()
def verify():
    console.print("[bold cyan]Initializing zero-config execution sandbox...[/bold cyan]")
    sandbox = SandboxManager()
    with console.status("Building and running Verification Container...", spinner="bouncingBar"):
        success, logs = sandbox.execute_tests()
    if success:
        console.print("[bold green]Verification Passed! Triangle of Trust maintained.[/bold green]")
    else:
        console.print("[bold red]Verification Failed. Invariant broken.[/bold red]")
    console.print("\n[bold cyan]Sandbox Test Logs:[/bold cyan]")
    console.print(logs)

@app.command()
def revert(intent_id: str):
    console.print(f"[bold red]Triggering Resolution Swarm for Intent Checkout: {intent_id}[/bold red]")
    swarm = ResolutionSwarm()
    with console.status("Navigating Semantic Dependency Graph...", spinner="runner"):
        result = swarm.execute_semantic_revert(intent_id)
    console.print(result)

@app.command()
def queue(description: str):
    console.print(f"Queueing a new intent: {description}")
    session = get_session()
    intent = Intent(description=description, status='PENDING')
    session.add(intent)
    session.commit()
    console.print("[bold green]Intent queued successfully.[/bold green]")

@app.command()
def swarm():
    console.print("[bold magenta]Launching Swarm Manager...[/bold magenta]")
    swarm_manager = SwarmManager()
    swarm_manager.process_intents()
    console.print("[bold green]Swarm execution completed.[/bold green]")

if __name__ == "__main__":
    app()
