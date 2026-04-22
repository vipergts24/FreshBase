import os
import tempfile
import subprocess
from abc import ABC, abstractmethod
from core.config import get_sandbox_type


class SandboxBase(ABC):
    def __init__(self, root_dir=None):
        self.root_dir = root_dir or os.getcwd()

    @abstractmethod
    def execute_tests(self) -> tuple[bool, str]:
        pass


class DockerSandboxManager(SandboxBase):
    """
    Manages the 'Triangle of Trust' via Docker containers.
    Provides high isolation at the cost of speed.
    """

    def execute_tests(self) -> tuple[bool, str]:
        # Determine packaging state dynamically
        req_path = os.path.join(self.root_dir, "requirements.txt")
        has_reqs = os.path.exists(req_path)
        has_setup = os.path.exists(
            os.path.join(self.root_dir, "setup.py")
        ) or os.path.exists(os.path.join(self.root_dir, "pyproject.toml"))

        req_install_block = ""
        if has_reqs:
            req_install_block = "COPY requirements.txt /app/requirements.txt\\nRUN pip install --no-cache-dir -r /app/requirements.txt"

        pkg_install_block = ""
        if has_setup:
            pkg_install_block = "RUN pip install --no-cache-dir -e ."

        dockerfile_content = f"""
FROM python:3.10-slim
LABEL freshbase="sandbox"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app
WORKDIR /app
{req_install_block}
COPY . /app
RUN pip install --no-cache-dir pytest
{pkg_install_block}
CMD ["pytest", "--maxfail=1", "--disable-warnings", "-v"]
"""
        dockerignore_path = os.path.join(self.root_dir, ".dockerignore")
        had_existing_ignore = os.path.exists(dockerignore_path)
        original_ignore_content = None
        if had_existing_ignore:
            with open(dockerignore_path, "r", encoding="utf-8") as f:
                original_ignore_content = f.read()

        security_ignore = ".env\n.git\n.fresh\n.fresh_worktrees\n__pycache__\n*.pyc\n"
        if original_ignore_content:
            security_ignore = original_ignore_content.rstrip() + "\n" + security_ignore

        with open(dockerignore_path, "w", encoding="utf-8") as f:
            f.write(security_ignore)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                dockerfile_path = os.path.join(tmpdir, "Dockerfile")
                with open(dockerfile_path, "w") as f:
                    f.write(dockerfile_content)

                image_name = "freshbase_sandbox_verify"
                build_cmd = [
                    "docker",
                    "build",
                    "-t",
                    image_name,
                    "-f",
                    dockerfile_path,
                    self.root_dir,
                ]

                try:
                    subprocess.run(
                        build_cmd, capture_output=True, text=True, check=True
                    )
                    run_cmd = ["docker", "run", "--rm", image_name]
                    run_res = subprocess.run(run_cmd, capture_output=True, text=True)
                    success = run_res.returncode == 0
                    logs = run_res.stdout + "\\n" + run_res.stderr
                    return success, logs
                except subprocess.CalledProcessError as e:
                    return (
                        False,
                        f"Sandbox Environment Build Failed:\\n{e.stderr}\\n{e.stdout}",
                    )
                except Exception as e:
                    return (False, f"Sandbox execution fatal error: {str(e)}")
        finally:
            if had_existing_ignore and original_ignore_content is not None:
                with open(dockerignore_path, "w", encoding="utf-8") as f:
                    f.write(original_ignore_content)
            elif not had_existing_ignore and os.path.exists(dockerignore_path):
                os.remove(dockerignore_path)


class UvSandboxManager(SandboxBase):
    """
    Ultra-fast verification using 'uv'. Runs tests on the host within a venv.
    Provides low isolation but near-instant feedback.
    """

    def execute_tests(self) -> tuple[bool, str]:
        try:
            # Check for pytest first
            check_pytest = subprocess.run(
                ["uv", "run", "pytest", "--version"],
                capture_output=True,
                cwd=self.root_dir,
            )

            # Use 'uv run' which handles venv creation and dependency resolution automatically
            # if a pyproject.toml or requirements.txt is present.
            cmd = ["uv", "run", "pytest", "--maxfail=1", "--disable-warnings", "-v"]

            # If no pyproject.toml/requirements.txt exists, uv run might fail to find pytest
            # We can fallback to ensuring pytest is installed in a temporary venv
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=self.root_dir)

            success = res.returncode == 0
            logs = res.stdout + "\\n" + res.stderr
            return success, logs

        except FileNotFoundError:
            return False, "Error: 'uv' is not installed on the host system."
        except Exception as e:
            return False, f"Uv verification failed: {str(e)}"


def SandboxManager(root_dir=None):
    """
    Factory function that returns the configured sandbox engine.
    """
    sb_type = get_sandbox_type()
    if sb_type == "docker":
        return DockerSandboxManager(root_dir=root_dir)
    return UvSandboxManager(root_dir=root_dir)
