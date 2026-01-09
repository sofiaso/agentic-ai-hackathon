"""Repository handling - clone and prepare local paths."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from iac_agent.models.contracts import ToolRunResult


def prepare_repo(
    repo_url: str | None = None,
    local_path: str | None = None,
    allow_network: bool = False,
) -> tuple[str | None, ToolRunResult | None]:
    """
    Prepare repository for scanning.

    Args:
        repo_url: Git repository URL
        local_path: Local directory path
        allow_network: Whether network operations are allowed

    Returns:
        Tuple of (path, error_result if failed)
    """
    if repo_url and local_path:
        return None, ToolRunResult(
            tool_name="repo",
            exit_code=1,
            stdout="",
            stderr="Cannot specify both repo_url and local_path",
            version=None,
            duration_seconds=0.0,
            success=False,
        )

    if repo_url:
        if not allow_network:
            return None, ToolRunResult(
                tool_name="repo",
                exit_code=0,
                stdout="[DRY-RUN] Would clone repository",
                stderr="",
                version=None,
                duration_seconds=0.0,
                success=True,
            )

        return _clone_repo(repo_url)

    if local_path:
        path = Path(local_path)
        if not path.exists():
            return None, ToolRunResult(
                tool_name="repo",
                exit_code=1,
                stdout="",
                stderr=f"Local path does not exist: {local_path}",
                version=None,
                duration_seconds=0.0,
                success=False,
            )
        return str(path.absolute()), None

    return None, ToolRunResult(
        tool_name="repo",
        exit_code=1,
        stdout="",
        stderr="Must specify either repo_url or local_path",
        version=None,
        duration_seconds=0.0,
        success=False,
    )


def _clone_repo(repo_url: str) -> tuple[str | None, ToolRunResult | None]:
    """Clone a git repository to a temporary directory."""
    temp_dir = tempfile.mkdtemp(prefix="iac_agent_")

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, temp_dir],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None, ToolRunResult(
                tool_name="repo",
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                version=None,
                duration_seconds=0.0,
                success=False,
            )

        return temp_dir, None

    except subprocess.TimeoutExpired:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, ToolRunResult(
            tool_name="repo",
            exit_code=124,
            stdout="",
            stderr="Git clone timed out",
            version=None,
            duration_seconds=0.0,
            success=False,
        )
    except FileNotFoundError:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, ToolRunResult(
            tool_name="repo",
            exit_code=127,
            stdout="",
            stderr="Git not found. Please install git.",
            version=None,
            duration_seconds=0.0,
            success=False,
        )
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, ToolRunResult(
            tool_name="repo",
            exit_code=1,
            stdout="",
            stderr=f"Error cloning repository: {str(e)}",
            version=None,
            duration_seconds=0.0,
            success=False,
        )
