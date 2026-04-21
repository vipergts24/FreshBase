import os
import tempfile
import subprocess


class SandboxManager:
    """
    Manages the 'Triangle of Trust'. Takes the current codebase state,
    generates an ephemeral Docker configuration, and verifies deterministically
    via isolated tests.
    """

    def __init__(self, root_dir=None):
        self.root_dir = root_dir or os.getcwd()

    def execute_tests(self) -> tuple[bool, str]:
        """
        Spins up a fleeting Docker container replicating the current directory state
        and executes underlying framework tests (pytest for MVP).
        Returns (success_boolean, console_logs).
        """
        # Determine packaging state dynamically
        req_path = os.path.join(self.root_dir, "requirements.txt")
        has_reqs = os.path.exists(req_path)
        has_setup = os.path.exists(
            os.path.join(self.root_dir, "setup.py")
        ) or os.path.exists(os.path.join(self.root_dir, "pyproject.toml"))

        req_install_block = ""
        if has_reqs:
            # Layer Caching: Fetch requirements first to persist heavy dependencies across runs
            req_install_block = "COPY requirements.txt /app/requirements.txt\\nRUN pip install --no-cache-dir -r /app/requirements.txt"

        pkg_install_block = ""
        if has_setup:
            pkg_install_block = "RUN pip install --no-cache-dir -e ."

        dockerfile_content = f"""
FROM python:3.10-slim
LABEL freshbase="sandbox"

# Setup pristine configuration preventing bytecode and enabling directory-agnostic modules
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

WORKDIR /app

# Enable aggressive Layer Caching for pip installs securely
{req_install_block}

# Copy the actual structure down sequentially
COPY . /app

# Install isolated test framework and native structural package
RUN pip install --no-cache-dir pytest
{pkg_install_block}

# Enforce deterministic testing
CMD ["pytest", "--maxfail=1", "--disable-warnings", "-v"]
"""
        # Inject ephemeral .dockerignore to prevent API key leakage into containers
        dockerignore_path = os.path.join(self.root_dir, ".dockerignore")
        had_existing_ignore = os.path.exists(dockerignore_path)
        original_ignore_content = None
        if had_existing_ignore:
            with open(dockerignore_path, "r", encoding="utf-8") as f:
                original_ignore_content = f.read()

        security_ignore = ".env\n.git\n.fresh\n__pycache__\n*.pyc\n"
        if original_ignore_content:
            security_ignore = original_ignore_content.rstrip() + "\n" + security_ignore

        with open(dockerignore_path, "w", encoding="utf-8") as f:
            f.write(security_ignore)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                dockerfile_path = os.path.join(tmpdir, "Dockerfile")
                with open(dockerfile_path, "w") as f:
                    f.write(dockerfile_content)

                # Build the isolated image
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
                    # Compile environment
                    subprocess.run(
                        build_cmd, capture_output=True, text=True, check=True
                    )

                    # Execute environment
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
                    return (
                        False,
                        f"Sandbox execution fatal error (is Docker running?): {str(e)}",
                    )
        finally:
            # Restore original .dockerignore state to prevent host pollution
            if had_existing_ignore and original_ignore_content is not None:
                with open(dockerignore_path, "w", encoding="utf-8") as f:
                    f.write(original_ignore_content)
            elif not had_existing_ignore and os.path.exists(dockerignore_path):
                os.remove(dockerignore_path)
