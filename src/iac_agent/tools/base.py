"""Base tool runner with subprocess handling and timeout support."""

import subprocess
import time
from datetime import datetime

from iac_agent.models.contracts import ToolRunResult


def run_tool(
    tool_name: str,
    args: list[str],
    cwd: str | None = None,
    timeout: int = 300,
    env: dict[str, str] | None = None,
) -> tuple[ToolRunResult, datetime, datetime]:
    """
    Run an external tool with subprocess handling.

    Args:
        tool_name: Name of the tool
        args: Command arguments (tool name should be first)
        cwd: Working directory for execution
        timeout: Timeout in seconds (default 300)
        env: Environment variables to set

    Returns:
        Tuple of (ToolRunResult, started_at, finished_at)
    """
    started_at = datetime.utcnow()
    start_time = time.time()
    stdout = ""
    stderr = ""
    exit_code = 1
    version: str | None = None

    try:
        # Try to get version first (non-blocking)
        try:
            version_result = subprocess.run(
                [args[0], "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=cwd,
                env=env,
            )
            if version_result.returncode == 0:
                version = version_result.stdout.strip()[:100]  # Limit version string
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass  # Version check failed, continue anyway

        # Run the actual command
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
        success = exit_code == 0

    except subprocess.TimeoutExpired:
        stderr = f"Tool execution timed out after {timeout} seconds"
        exit_code = 124
        success = False
    except FileNotFoundError:
        stderr = f"Tool '{args[0]}' not found. Please install it."
        exit_code = 127
        success = False
    except Exception as e:
        stderr = f"Unexpected error running tool: {str(e)}"
        exit_code = 1
        success = False

    finished_at = datetime.utcnow()
    duration = time.time() - start_time

    # Store original stdout before truncation (for normalization)
    original_stdout = stdout

    tool_result = ToolRunResult(
        tool_name=tool_name,
        exit_code=exit_code,
        stdout=stdout,  # Will be truncated by Pydantic validator
        stderr=stderr,
        version=version,
        duration_seconds=duration,
        success=success,
    )

    return tool_result, started_at, finished_at, original_stdout
