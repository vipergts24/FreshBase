import os
import re
from litellm import completion
from db.vector_store import search_code

class BuilderPod:
    """
    The Builder Pod represents the core intelligence agent responsible for 
    translating an Intent into an actionable codebase patch, and parsing
    its own output to write files directly.
    """
    def __init__(self, model_name="gpt-4o"):
        self.model_name = os.environ.get("FRESH_MODEL", model_name)
        
    def execute_intent(self, intent: str) -> tuple[str, list[str]]:
        """
        Takes a human-readable intent, searches the vector DB for context,
        prompts the LLM, and parses the response to physically apply code.
        Returns the raw text response, and a list of files modified.
        """
        if not os.environ.get("OPENAI_API_KEY"):
            return "Error: OPENAI_API_KEY environment variable is required.", []
            
        # 1. Semantic Search for Context
        context_chunks = search_code(intent, limit=5)
        
        context_text = "No prior codebase context found."
        if context_chunks:
            context_pieces = [f"--- FILE: {c['file_path']} ---\n{c['text']}" for c in context_chunks]
            context_text = "\n\n".join(context_pieces)
            
        # 2. Construct Strict Prompt Constraints
        system_prompt = (
            "You are FreshBase BuilderPod, an autonomous software engineering agent. "
            "You are given an Intent (a goal) and relevant pieces of the codebase as context. "
            "You must output the logic and code changes required to satisfy this intent. "
            "For this MVP, provide your reasoning first.\\n\\n"
            "CRITICAL: For EVERY new file you create or existing file you modify, you MUST output the code "
            "in the following exact structural format:\\n"
            "<FILE>\\n"
            "<PATH>filename.py</PATH>\\n"
            "<CODE>\\n"
            "def main():\\n"
            "    print('hello')\\n"
            "</CODE>\\n"
            "</FILE>\\n"
            "Do not omit the <FILE> tags, as the orchestration layer uses them to apply changes."
        )
        
        user_prompt = f"INTENT:\n{intent}\n\nRELEVANT REPOSITORY CONTEXT:\n{context_text}\n\nPlease output your reasoning and the structured <FILE> patches."
        
        # 3. Dynamic Model Routing
        try:
            response = completion(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            raw_response = response.choices[0].message.content
            
            # 4. Parse and Apply
            applied_files = self._apply_files(raw_response)
            return raw_response, applied_files
            
        except Exception as e:
            return f"BuilderPod failed during execution: {str(e)}", []
            
    def _apply_files(self, agent_output: str) -> list[str]:
        """
        Parses the <FILE> blocks from the agent's output and writes them tracking changes.
        """
        pattern = re.compile(r"<FILE>\s*<PATH>(.*?)</PATH>\s*<CODE>(.*?)</CODE>\s*</FILE>", re.DOTALL)
        matches = pattern.findall(agent_output)
        
        applied = []
        for path_match, code_match in matches:
            path = path_match.strip()
            # Strip a single leading and trailing newline to prevent whitespace drift
            code = code_match.strip("\\n")
            
            # Sandbox directories locally
            os.makedirs(os.path.dirname(os.path.abspath(path)) or '.', exist_ok=True)
            
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
            applied.append(path)
            
        return applied
