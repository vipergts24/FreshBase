import os
import re
import time
from litellm import completion
from db.vector_store import search_code
from rich.prompt import Prompt
from rich.console import Console
from core.config import get_global_model

# Transient HTTP errors that warrant retry
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BASE_BACKOFF_SECONDS = 2

console = Console()


class BuilderPod:
    """
    The Builder Pod represents the core intelligence agent responsible for
    translating an Intent into an actionable codebase patch, and parsing
    its own output to write files directly.
    """

    def __init__(self, override_model=None, interactive=True, tracker=None):
        base_model = override_model or get_global_model()
        self.model_name = os.environ.get("FRESH_MODEL", base_model)
        self.interactive = interactive
        self.tracker = tracker

    def execute_intent(
        self, intent: str, hot_context: dict = None
    ) -> tuple[str, list[str]]:
        """
        Takes a human-readable intent, searches the vector DB for context,
        prompts the LLM, and parses the response to physically apply code.
        Returns the raw text response, and a list of files modified.
        """

        hot_context = hot_context or {}

        # 1. Semantic Search for Context
        context_chunks = search_code(intent, limit=5)

        context_text = "No prior codebase context found."
        if context_chunks:
            context_pieces = [
                f"--- FILE: {c['file_path']} ---\n{c['text']}" for c in context_chunks
            ]
            context_text = "\n\n".join(context_pieces)

        # Optional: Inject Hot Context string
        hot_context_str = ""
        if hot_context:
            hot_context_str = "\n\nCRITICAL: The following files were JUST MODIFIED by prior Swarm intents. They supercede any stale context from the Database above:\n"
            for hp, hcontent in hot_context.items():
                hot_context_str += f"--- NEW FILE STATE: {hp} ---\n{hcontent}\n\n"

        # 2. Construct Strict Prompt Constraints
        system_prompt = (
            "You are FreshBase BuilderPod, an autonomous software engineering agent. "
            "You are given an Intent (a goal) and relevant pieces of the codebase as context. "
            "You must output the logic and code changes required to satisfy this intent. "
            "For this MVP, provide your reasoning first.\n\n"
            "CRITICAL: For EVERY new file you create or existing file you modify, you MUST output the code "
            "in the following exact structural format:\n"
            "<FILE>\n"
            "<PATH>filename.py</PATH>\n"
            "<CODE>\n"
            "def main():\n"
            "    print('hello')\n"
            "</CODE>\n"
            "</FILE>\n"
            "Do not omit the <FILE> tags, as the orchestration layer uses them to apply changes."
            "If an Intent is highly ambiguous or conceptually conflicts with the existing codebase, "
            "output a <PROMPT_DIRECTOR>The Question</PROMPT_DIRECTOR> tag instead."
        )

        user_prompt = f"INTENT:\n{intent}\n\nRELEVANT REPOSITORY CONTEXT:\n{context_text}{hot_context_str}\n\nPlease output your reasoning and the structured <FILE> patches."

        # 3. Dynamic Model Routing and Recursive Response Handling
        message_history = [{"role": "system", "content": system_prompt}]
        message_history.append({"role": "user", "content": user_prompt})

        # Intent size guardrail: estimate tokens before calling the LLM
        if self.tracker:
            tier, token_count = self.tracker.check_intent_budget(
                self.model_name, message_history
            )
            if tier == "red":
                console.print(
                    f"[bold red]BUDGET BLOCK: This intent would consume "
                    f"~{token_count:,} tokens. That's too large for a "
                    f"single agent pass. Break it into smaller "
                    f"intents.[/bold red]"
                )
                return "Intent blocked: exceeds 50K token budget.", []
            elif tier == "orange":
                console.print(
                    f"[bold yellow]WARNING: This intent will consume "
                    f"~{token_count:,} tokens (~${token_count * 0.0000025:.4f} "
                    f"input cost).[/bold yellow]"
                )
                if self.interactive:
                    from rich.prompt import Confirm

                    if not Confirm.ask("Continue with this large intent?"):
                        return "Intent cancelled by user.", []
            elif tier == "yellow":
                console.print(
                    f"[dim]Note: Large intent (~{token_count:,} tokens)[/dim]"
                )

        while True:
            raw_response = self._call_llm_with_retry(message_history)
            if raw_response is None:
                return "LLM call failed after retries.", []

            if "<PROMPT_DIRECTOR>" in raw_response:
                if not self.interactive:
                    # Parallel mode: cannot prompt stdin, defer to human
                    return raw_response, []
                # Extract the question and prompt the user
                question = (
                    re.search(r"<PROMPT_DIRECTOR>(.*?)</PROMPT_DIRECTOR>", raw_response)
                    .group(1)
                    .strip()
                )
                user_answer = Prompt.ask(f"PROMPT DIRECTOR Question: {question}")
                message_history.append({"role": "assistant", "content": raw_response})
                message_history.append({"role": "user", "content": user_answer})
            else:
                applied_files = self._apply_files(raw_response)
                return raw_response, applied_files

    def _call_llm_with_retry(self, messages: list) -> "str | None":
        """
        Calls the LLM with exponential backoff retry for transient errors.
        Returns the raw response string, or None if all retries fail.
        """
        for attempt in range(_MAX_RETRIES):
            try:
                response = completion(model=self.model_name, messages=messages)
                # Record usage in the tracker
                if self.tracker:
                    self.tracker.record_llm(self.model_name, response)
                return response.choices[0].message.content
            except Exception as e:
                error_str = str(e)
                # Check if the error is retryable (rate limit, server error)
                is_retryable = any(
                    str(code) in error_str for code in _RETRYABLE_STATUS_CODES
                )

                if is_retryable and attempt < _MAX_RETRIES - 1:
                    wait_time = _BASE_BACKOFF_SECONDS * (2**attempt)
                    console.print(
                        f"[bold yellow]Transient API error (attempt "
                        f"{attempt + 1}/{_MAX_RETRIES}). Retrying in "
                        f"{wait_time}s...[/bold yellow]"
                    )
                    time.sleep(wait_time)
                else:
                    console.print(f"[bold red]LLM call failed: {error_str}[/bold red]")
                    return None
        return None

    def _apply_files(self, agent_output: str) -> list[str]:
        """
        Parses the <FILE> blocks from the agent's output and writes them tracking changes.
        All paths are validated to resolve within the project root before any write.
        Existing files are staged in git before overwrite for safe rollback.
        """
        pattern = re.compile(
            r"<FILE>\s*<PATH>(.*?)</PATH>\s*<CODE>(.*?)</CODE>\s*</FILE>", re.DOTALL
        )
        matches = pattern.findall(agent_output)

        project_root = os.path.abspath(os.getcwd())
        applied = []

        for path_match, code_match in matches:
            path = path_match.strip()

            # ---- PATH SECURITY SANDBOX ----
            # Reject absolute paths immediately
            if os.path.isabs(path):
                console.print(
                    f"[bold red]SECURITY BLOCK: Absolute path rejected: "
                    f"{path}[/bold red]"
                )
                continue

            # Reject any path containing traversal components
            normalized = os.path.normpath(path)
            if normalized.startswith("..") or "/.." in normalized:
                console.print(
                    f"[bold red]SECURITY BLOCK: Path traversal rejected: "
                    f"{path}[/bold red]"
                )
                continue

            # Resolve the full path and verify it's within the project root
            resolved = os.path.abspath(os.path.join(project_root, normalized))
            if (
                not resolved.startswith(project_root + os.sep)
                and resolved != project_root
            ):
                console.print(
                    f"[bold red]SECURITY BLOCK: Path escapes project root: "
                    f"{path} → {resolved}[/bold red]"
                )
                continue
            # ---- END PATH SECURITY SANDBOX ----

            # Stage existing file in git before overwrite (Q20 safety net)
            if os.path.exists(resolved):
                import subprocess

                subprocess.run(
                    ["git", "add", resolved],
                    capture_output=True,
                )

            # Strip a single leading and trailing newline to prevent whitespace drift
            code = code_match.strip("\n")

            # Create directories within the project boundary
            os.makedirs(os.path.dirname(resolved) or ".", exist_ok=True)

            with open(resolved, "w", encoding="utf-8") as f:
                f.write(code)
            applied.append(path)

        return applied
