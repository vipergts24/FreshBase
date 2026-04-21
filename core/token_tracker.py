"""
TokenTracker: Session-aware token usage and cost accumulator.

Thread-safe singleton that records every LLM call, embedding call,
and resource spin-up across the session. Provides live status bars,
budget guardrails, and hot context trimming.
"""

import threading
import uuid
from datetime import datetime, timezone
from litellm import completion_cost, token_counter, model_cost
from rich.panel import Panel
from rich.table import Table
from rich.console import Console

console = Console()

# Intent size guardrail thresholds (input tokens)
TIER_GREEN = 4_000
TIER_YELLOW = 16_000
TIER_ORANGE = 50_000
# Anything above TIER_ORANGE is a hard block (Red)


class TokenTracker:
    """Thread-safe session-wide token and cost accumulator."""

    def __init__(self, session_id=None):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.start_time = datetime.now(timezone.utc)
        self._lock = threading.Lock()

        # LLM usage accumulators
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_cost = 0.0
        self.llm_calls = 0

        # Embedding usage accumulators
        self.embedding_tokens = 0
        self.embedding_cost = 0.0
        self.embedding_calls = 0

        # Resource tracking
        self.docker_builds = 0
        self.git_branches = 0
        self.worktrees = 0

        # Intent tracking
        self.intents_processed = 0
        self.intents_resolved = 0
        self.intents_reverted = 0
        self.total_intents = 0

        # Model tracking
        self.primary_model = None

    def record_llm(self, model, response):
        """Extract usage from a LiteLLM response and accumulate."""
        with self._lock:
            try:
                usage = response.usage
                self.prompt_tokens += usage.prompt_tokens or 0
                self.completion_tokens += usage.completion_tokens or 0
                self.llm_calls += 1

                cost = completion_cost(completion_response=response)
                self.total_cost += cost

                if not self.primary_model:
                    self.primary_model = model
            except Exception:
                self.llm_calls += 1

    def record_embedding(self, model, token_count):
        """Track embedding API calls (vector store queries)."""
        with self._lock:
            self.embedding_tokens += token_count
            self.embedding_calls += 1
            # ada-002 pricing: $0.0001 per 1K tokens
            self.embedding_cost += (token_count / 1000) * 0.0001

    def record_resource(self, resource_type):
        """Track non-token resources: docker builds, branches, worktrees."""
        with self._lock:
            if resource_type == "docker":
                self.docker_builds += 1
            elif resource_type == "branch":
                self.git_branches += 1
            elif resource_type == "worktree":
                self.worktrees += 1

    def record_intent_result(self, resolved=True):
        """Track intent completion outcomes."""
        with self._lock:
            self.intents_processed += 1
            if resolved:
                self.intents_resolved += 1
            else:
                self.intents_reverted += 1

    def get_total_cost(self):
        """Return the total session cost (LLM + embeddings)."""
        with self._lock:
            return self.total_cost + self.embedding_cost

    def check_intent_budget(self, model, messages):
        """
        Estimate the token count for a prompt and return the budget tier.

        Returns:
            tuple: (tier: str, token_count: int)
            - "green": < 4K tokens, proceed
            - "yellow": 4K-16K, warning
            - "orange": 16K-50K, requires confirmation
            - "red": > 50K, hard block
        """
        try:
            count = token_counter(model=model, messages=messages)
        except Exception:
            # If token counting fails, estimate from character length
            total_chars = sum(len(m.get("content", "")) for m in messages)
            count = total_chars // 4  # Rough 4 chars per token estimate

        if count < TIER_GREEN:
            return "green", count
        elif count < TIER_YELLOW:
            return "yellow", count
        elif count < TIER_ORANGE:
            return "orange", count
        else:
            return "red", count

    def get_model_context_window(self, model):
        """
        Auto-detect the model's max context window size.
        Returns the max tokens for the model, defaulting to 128K.
        """
        try:
            cost_info = model_cost.get(model, {})
            return cost_info.get("max_input_tokens", 128_000)
        except Exception:
            return 128_000

    def trim_hot_context(self, hot_context, model):
        """
        Trim the hot context dict to fit within 40% of the model's
        context window. Evicts oldest entries first.

        Args:
            hot_context: dict of {filepath: content}
            model: model name for context window detection

        Returns:
            dict: trimmed hot context
        """
        max_window = self.get_model_context_window(model)
        budget = int(max_window * 0.4)

        # Estimate current token count
        total_chars = sum(len(v) for v in hot_context.values())
        estimated_tokens = total_chars // 4

        if estimated_tokens <= budget:
            return hot_context

        # Evict oldest entries (dict preserves insertion order in Python 3.7+)
        trimmed = {}
        running_tokens = 0
        # Reverse to keep newest entries
        for key in reversed(list(hot_context.keys())):
            entry_tokens = len(hot_context[key]) // 4
            if running_tokens + entry_tokens <= budget:
                trimmed[key] = hot_context[key]
                running_tokens += entry_tokens
            else:
                break

        evicted = len(hot_context) - len(trimmed)
        if evicted > 0:
            console.print(
                f"[dim]Hot Context trimmed: evicted {evicted} file(s) "
                f"to stay within {budget:,} token budget.[/dim]"
            )

        return trimmed

    def render_status_bar(self):
        """Render a compact Rich Panel showing live session usage."""
        total_cost = self.get_total_cost()
        total_tokens = self.prompt_tokens + self.completion_tokens

        progress = ""
        if self.total_intents > 0:
            progress = f"  Intent {self.intents_processed}/{self.total_intents}"

        content = (
            f"Tokens: [bold]{self.prompt_tokens:,}[/bold] in / "
            f"[bold]{self.completion_tokens:,}[/bold] out   "
            f"Cost: [bold green]${total_cost:.4f}[/bold green]{progress}\n"
            f"LLM: {self.llm_calls}   "
            f"Embed: {self.embedding_calls}   "
            f"Docker: {self.docker_builds}"
        )

        return Panel(
            content,
            title="[bold]Session Usage[/bold]",
            border_style="cyan",
            expand=False,
        )

    def render_summary(self):
        """Render a detailed Rich Panel for end-of-session summary."""
        elapsed = datetime.datetime.utcnow() - self.start_time
        minutes = int(elapsed.total_seconds() // 60)
        seconds = int(elapsed.total_seconds() % 60)

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Category", style="white")
        table.add_column("Calls", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Cost", justify="right", style="green")

        table.add_row(
            "LLM",
            str(self.llm_calls),
            f"{self.prompt_tokens + self.completion_tokens:,}",
            f"${self.total_cost:.4f}",
        )
        table.add_row(
            "Embedding",
            str(self.embedding_calls),
            f"{self.embedding_tokens:,}",
            f"${self.embedding_cost:.4f}",
        )
        table.add_row(
            "─" * 10,
            "─" * 5,
            "─" * 8,
            "─" * 8,
        )
        total_tokens = (
            self.prompt_tokens + self.completion_tokens + self.embedding_tokens
        )
        total_cost = self.get_total_cost()
        table.add_row(
            "[bold]TOTAL[/bold]",
            f"[bold]{self.llm_calls + self.embedding_calls}[/bold]",
            f"[bold]{total_tokens:,}[/bold]",
            f"[bold]${total_cost:.4f}[/bold]",
        )

        resources = (
            f"\nResources: {self.docker_builds} Docker builds, "
            f"{self.git_branches} branches, {self.worktrees} worktrees\n"
            f"Intents: {self.intents_resolved} resolved, "
            f"{self.intents_reverted} reverted"
        )

        from rich.console import Group
        from rich.text import Text

        header = Text(
            f"Session: {self.session_id}     " f"Duration: {minutes}m {seconds}s",
            style="dim",
        )

        return Panel(
            Group(header, Text(""), table, Text(resources)),
            title="[bold]Session Summary[/bold]",
            border_style="cyan",
            expand=False,
        )

    def flush_to_db(self):
        """Persist the session usage to SQLite for historical tracking."""
        try:
            from db.engine import get_session
            from db.models import TokenUsage

            db_session = get_session()
            record = TokenUsage(
                session_id=self.session_id,
                model=self.primary_model or "unknown",
                prompt_tokens=self.prompt_tokens,
                completion_tokens=self.completion_tokens,
                embedding_tokens=self.embedding_tokens,
                estimated_cost=round(self.get_total_cost(), 6),
                llm_calls=self.llm_calls,
                embedding_calls=self.embedding_calls,
                docker_builds=self.docker_builds,
                intents_processed=self.intents_processed,
                intents_resolved=self.intents_resolved,
                intents_reverted=self.intents_reverted,
            )
            db_session.add(record)
            db_session.commit()
            db_session.close()
        except Exception as e:
            console.print(f"[dim]Failed to persist usage: {e}[/dim]")
