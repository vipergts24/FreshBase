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
        # Determine if requirements.txt exists to auto-install dependencies
        has_reqs = os.path.exists(os.path.join(self.root_dir, "requirements.txt"))
        
        dockerfile_content = f"""
FROM python:3.10-slim

# Set up the isolated directory
WORKDIR /app

# Copy the host codebase inside
COPY . /app

# Install isolated test framework
RUN pip install --no-cache-dir pytest

# Install custom dependencies if present
{"RUN pip install --no-cache-dir -r requirements.txt" if has_reqs else ""}

# Enforce deterministic testing
CMD ["pytest", "--maxfail=1", "--disable-warnings", "-v"]
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            dockerfile_path = os.path.join(tmpdir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)
                
            # Build the isolated image
            image_name = "freshbase_sandbox_verify"
            build_cmd = ["docker", "build", "-t", image_name, "-f", dockerfile_path, self.root_dir]
            
            try:
                # Compile environment
                subprocess.run(build_cmd, capture_output=True, text=True, check=True)
                
                # Execute environment
                run_cmd = ["docker", "run", "--rm", image_name]
                run_res = subprocess.run(run_cmd, capture_output=True, text=True)
                
                success = run_res.returncode == 0
                logs = run_res.stdout + "\\n" + run_res.stderr
                return success, logs
                
            except subprocess.CalledProcessError as e:
                # This catches errors during the build step (like bad requirements.txt)
                return False, f"Sandbox Environment Build Failed:\\n{e.stderr}\\n{e.stdout}"
            except Exception as e:
                # Catch-all for docker daemon being down, etc.
                return False, f"Sandbox execution fatal error (is Docker running?): {str(e)}"
