import subprocess
from typing import Optional, Tuple


def run_git_command(command: list[str]) -> Tuple[int, str, str]:
    """Runs a git command and returns (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + command, capture_output=True, text=True, check=False
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
