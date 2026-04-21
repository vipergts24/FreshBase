import os
import re
from litellm import completion
from db.vector_store import search_code
from rich.prompt import Prompt
from core.config import get_global_model


class BuilderPod:
    """
    The Builder Pod represents the core intelligence agent responsible for
    translating an Intent into an actionable codebase patch, and parsing
    its own output to write files directly.
    """

    def __init__(self, override_model=None):
        base_model = override_model or get_global_model()
        self.model_name = os.environ.get("FRESH_MODEL", base_model)

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

        while True:
            try:
                response = completion(model=self.model_name, messages=message_history)
                raw_response = response.choices[0].message.content
                if "<PROMPT_DIRECTOR>" in raw_response:
                    # Extract the question and prompt the user
                    question = (
                        re.search(
                            r"<PROMPT_DIRECTOR>(.*?)</PROMPT_DIRECTOR>", raw_response
                        )
                        .group(1)
                        .strip()
                    )
                    user_answer = Prompt.ask(f"PROMPT DIRECTOR Question: {question}")
                    message_history.append(
                        {"role": "assistant", "content": raw_response}
                    )
                    message_history.append({"role": "user", "content": user_answer})
                else:
                    applied_files = self._apply_files(raw_response)
                    return raw_response, applied_files
            except Exception as e:
                return f"An error occurred: {str(e)}", []

    def _apply_files(self, agent_output: str) -> list[str]:
        """
        Parses the <FILE> blocks from the agent's output and writes them tracking changes.
        """
        pattern = re.compile(
            r"<FILE>\s*<PATH>(.*?)</PATH>\s*<CODE>(.*?)</CODE>\s*</FILE>", re.DOTALL
        )
        matches = pattern.findall(agent_output)

        applied = []
        for path_match, code_match in matches:
            path = path_match.strip()
            # Strip a single leading and trailing newline to prevent whitespace drift
            code = code_match.strip("\n")

            # Sandbox directories locally
            os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
            applied.append(path)

        return applied
