import os
from litellm import completion
from db.vector_store import search_code

class BuilderPod:
    """
    The Builder Pod represents the core intelligence agent responsible for 
    translating an Intent into an actionable codebase patch.
    """
    def __init__(self, model_name="gpt-4o"):
        # BYOM (Bring Your Own Model) approach
        self.model_name = os.environ.get("FRESH_MODEL", model_name)
        
    def propose_implementation(self, intent: str) -> str:
        """
        Takes a human-readable intent, searches the vector DB for context,
        and prompts the LLM to propose an implementation.
        """
        if not os.environ.get("OPENAI_API_KEY"):
            return "Error: OPENAI_API_KEY environment variable is required."
            
        # 1. Semantic Search for Context
        context_chunks = search_code(intent, limit=5)
        
        context_text = "No prior codebase context found."
        if context_chunks:
            context_pieces = [f"--- FILE: {c['file_path']} ---\n{c['text']}" for c in context_chunks]
            context_text = "\n\n".join(context_pieces)
            
        # 2. Construct Prompt Constraints
        system_prompt = (
            "You are FreshBase BuilderPod, an autonomous software engineering agent. "
            "You are given an Intent (a goal) and relevant pieces of the codebase as context. "
            "You must output the logic and code changes required to satisfy this intent. "
            "For this MVP, provide your reasoning, followed by the explicit modifications required."
        )
        
        user_prompt = f"INTENT:\n{intent}\n\nRELEVANT REPOSITORY CONTEXT:\n{context_text}\n\nPlease propose your implementation."
        
        # 3. Dynamic Model Routing via LiteLLM
        try:
            response = completion(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"BuilderPod failed during execution: {str(e)}"
