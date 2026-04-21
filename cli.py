import typer
from rich.console import Console
from db.engine import init_db

app = typer.Typer(help="FreshBase: Autonomous Semantic Code Collaboration")
console = Console()

@app.command()
def init():
    """
    Initialize FreshBase in the current directory.
    Creates a .fresh/ database block to track intents and semantic commits.
    """
    console.print("[bold green]Initializing FreshBase...[/bold green]")
    init_db()
    console.print("Successfully initialized semantic tracking in .fresh/")

from core.indexer import index_repo

@app.command()
def index():
    """
    Scan the local repository and generate AST embeddings into LanceDB.
    """
    console.print("[bold blue]Indexing codebase for the Knowledge Engine (Vector DB)...[/bold blue]")
    try:
        count = index_repo()
        console.print(f"[bold green]Successfully indexed {count} code chunks into the local Data Vector database.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Indexing Failed:[/bold red] {str(e)}")

from core.agent import BuilderPod

@app.command()
def build(intent: str):
    """
    Submits an intent directly to the Builder Pod for a code proposal.
    """
    console.print(f"[bold magenta]Assigning intent to Builder Pod:[/bold magenta] {intent}")
    pod = BuilderPod()
    
    with console.status("[bold yellow]Agent Swarm is analyzing codebase and synthesizing logic...[/bold yellow]", spinner="dots"):
        response = pod.propose_implementation(intent)
        
    console.print("\n[bold cyan]Builder Pod Output:[/bold cyan]")
    console.print(response)

from core.sandbox import SandboxManager

@app.command()
def verify():
    """
    Spins up a fleeting Sandbox container to execute deterministic 
    tests against the current state, enforcing the Triangle of Trust.
    """
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

from core.resolution import ResolutionSwarm

@app.command()
def revert(intent_id: str):
    """
    Semantically revert an intent and resolve any downstream code dependencies autonomously.
    """
    console.print(f"[bold red]Triggering Resolution Swarm for Intent Checkout: {intent_id}[/bold red]")
    swarm = ResolutionSwarm()
    
    with console.status("Navigating Semantic Dependency Graph...", spinner="runner"):
        result = swarm.execute_semantic_revert(intent_id)
        
    console.print(result)

if __name__ == "__main__":
    app()
