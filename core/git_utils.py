import subprocess
from typing import Optional, Tuple


def run_git_command(command: list[str], cwd: str = None) -> Tuple[int, str, str]:
    """Runs a git command and returns (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + command, capture_output=True, text=True, check=False, cwd=cwd
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def is_git_repo() -> bool:
    """Checks if the current directory is a git repository."""
    code, _, _ = run_git_command(["rev-parse", "--is-inside-work-tree"])
    return code == 0


def get_current_branch() -> Optional[str]:
    code, out, _ = run_git_command(["branch", "--show-current"])
    return out if code == 0 else None


def checkout_shadow_branch(intent_id: str) -> Optional[str]:
    """Creates a temporary isolated branch for an agent to work on."""
    branch_name = f"fresh/intent-{intent_id}"
    code, _, _ = run_git_command(["checkout", "-b", branch_name])
    if code != 0:
        # If it failed to create, try to just checkout if it exists
        code, _, _ = run_git_command(["checkout", branch_name])

    return branch_name if code == 0 else None


def get_latest_commit_sha() -> Optional[str]:
    """Returns the SHA of the HEAD commit."""
    code, out, _ = run_git_command(["rev-parse", "HEAD"])
    return out if code == 0 else None


def create_intent_branch(intent_id: int) -> Optional[str]:
    """Creates an isolated branch from main HEAD for parallel agent work."""
    branch_name = f"fresh/intent-{intent_id}"
    # Always branch from main to ensure clean isolation
    code, _, _ = run_git_command(["branch", branch_name, "main"])
    if code != 0:
        # Branch may already exist from a prior failed run; reset it
        run_git_command(["branch", "-D", branch_name])
        code, _, _ = run_git_command(["branch", branch_name, "main"])
    return branch_name if code == 0 else None


def merge_intent_branch(intent_id: int, cwd: str = None) -> Tuple[bool, str]:
    """
    Squash-merges an intent branch back into main.
    Returns (success, error_message).
    """
    branch_name = f"fresh/intent-{intent_id}"
    code, out, err = run_git_command(["merge", "--squash", branch_name], cwd=cwd)
    if code != 0:
        return False, err
    return True, ""


def delete_branch(branch_name: str):
    """Force-deletes a local branch."""
    run_git_command(["branch", "-D", branch_name])


def add_worktree(intent_id: int, base_branch: str = "main") -> Optional[str]:
    """
    Creates an isolated worktree directory for parallel agent execution.
    Returns the worktree path if successful, None otherwise.
    """
    branch_name = f"fresh/intent-{intent_id}"
    worktree_path = f".fresh_worktrees/intent-{intent_id}"

    # Ensure the branch exists
    create_intent_branch(intent_id)

    # Create the worktree
    code, out, err = run_git_command(["worktree", "add", worktree_path, branch_name])
    if code != 0:
        # Worktree may exist from a prior failed run; remove and retry
        run_git_command(["worktree", "remove", "--force", worktree_path])
        code, out, err = run_git_command(
            ["worktree", "add", worktree_path, branch_name]
        )

    return worktree_path if code == 0 else None


def remove_worktree(intent_id: int):
    """Removes an intent's worktree directory and prunes git metadata."""
    worktree_path = f".fresh_worktrees/intent-{intent_id}"
    run_git_command(["worktree", "remove", "--force", worktree_path])


def prune_worktrees():
    """Cleans up stale worktree metadata from git."""
    run_git_command(["worktree", "prune"])


def is_repo_dirty(cwd: str = None) -> bool:
    """Returns True if there are uncommitted or untracked changes."""
    # --porcelain=v1 provides a machine-readable output.
    # If it's not empty, the repo is dirty.
    code, out, _ = run_git_command(["status", "--porcelain"], cwd=cwd)
    return bool(out.strip())


def commit_changes(message: str, cwd: str = None) -> bool:
    """Stages all changes and commits them."""
    run_git_command(["add", "."], cwd=cwd)
    code, _, _ = run_git_command(["commit", "-m", message], cwd=cwd)
    return code == 0
