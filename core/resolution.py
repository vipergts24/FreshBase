import os
from sqlalchemy.orm import Session
from db.engine import get_session
from db.models import Intent, FreshCommit
from core.git_utils import run_git_command, checkout_shadow_branch
from core.sandbox import SandboxManager
from core.agent import BuilderPod

class ResolutionSwarm:
    """
    The orchestrator for Semantic Reverts.
    When a revert breaks code-dependencies downstream, this swarm triggers
    BuilderPods to re-write the downstream code specifically to pass invariant tests
    while strictly fulfilling the absence of the reverted intent.
    """
    def __init__(self):
        self.session: Session = get_session()
        self.builder = BuilderPod()
        self.sandbox = SandboxManager()
        
    def execute_semantic_revert(self, target_intent_id: str) -> str:
        try:
            target_id_int = int(target_intent_id)
            intent = self.session.query(Intent).filter(Intent.id == target_id_int).first()
        except ValueError:
            return "Error: Intent ID must be an integer mapping."
            
        if not intent:
            return f"Error: No tracked intent found with ID {target_intent_id} in the local Metastore."
            
        if not intent.commits:
            return f"Error: Intent {target_intent_id} has no linked git commits to physically revert."
            
        target_commit_sha = intent.commits[0].git_sha
        
        # 1. Spin up a Shadow Branch
        shadow_branch = checkout_shadow_branch(target_intent_id)
        if not shadow_branch:
            return "Error: Could not spin up a shadow branch in Git."
            
        # 2. Issue standard git revert patch
        code, out, err = run_git_command(["revert", "--no-commit", target_commit_sha])
        has_text_conflict = code != 0
        
        # 3. Verification Phase
        if not has_text_conflict:
            success, logs = self.sandbox.execute_tests()
            if success:
                # Easiest case: Clean revert, no downstream code was tied to this intent
                run_git_command(["commit", "-m", f"FreshBase: Cleanly Reverted Intent {target_intent_id}"])
                intent.status = "REVERTED"
                self.session.commit()
                return f"[SUCCESS] Revert executed flawlessly. No downstream code impacts detected."
            else:
                failure_logs = logs
        else:
            failure_logs = "Merge conflict textually blocked the revert:\\n" + err
            
        # 4. RESOLUTION SWARM ACTIVATION
        prompt_intent = (
            f"The human Director requested to revert Intent '{intent.description}'. "
            f"However, doing so logically breaks downstream code that depended on it.\\n"
            f"Here are the Verification Test failures that occurred when we stripped it:\\n"
            f"{failure_logs[-1500:]}\\n\\n"
            f"Please propose a refactoring patch that modifies the downstream code so that "
            f"the tests pass again, WITHOUT relying on the logic from Intent '{intent.description}'."
        )
        
        refactor_proposal, applied_files = self.builder.execute_intent(prompt_intent)
        
        applied_str = "\\n  - ".join(applied_files) if applied_files else "No files modified."
        
        return (
            f"[SEMANTIC CONFLICT DETECTED]\\n"
            f"Downstream tests failed. The Resolution Swarm analyzed the failure "
            f"and applied the following autonomous repair:\\n\\n{refactor_proposal}\\n\\n"
            f"Files patched:\\n  - {applied_str}"
        )
