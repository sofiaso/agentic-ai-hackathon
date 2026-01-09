"""Checkov tool wrapper."""

from datetime import datetime
from pathlib import Path

from iac_agent.models.contracts import ToolRunResult
from iac_agent.tools.base import run_tool


def run_checkov(
    scan_path: str, execute: bool = False
) -> tuple[ToolRunResult, datetime, datetime, list[str], str | None]:
    """
    Run checkov on a directory.

    Args:
        scan_path: Path to directory containing IaC files
        execute: Whether to actually execute (default False for dry-run)

    Returns:
        Tuple of (ToolRunResult, started_at, finished_at, cmd, cwd)
    """
    started_at = datetime.utcnow()
    path = Path(scan_path)

    # Determine working directory and command
    if path.is_file():
        cwd = str(path.parent)
        target = str(path)
    else:
        cwd = str(path)
        target = str(path)

    cmd = ["checkov", "-d", target, "--framework", "terraform", "--output", "json", "--quiet"]

    if not execute:
        finished_at = datetime.utcnow()
        return (
            ToolRunResult(
                tool_name="checkov",
                exit_code=0,
                stdout="[DRY-RUN] checkov would run here",
                stderr="",
                version=None,
                duration_seconds=0.0,
                success=True,
            ),
            started_at,
            finished_at,
            cmd,
            cwd,
        )

    if not path.exists():
        finished_at = datetime.utcnow()
        return (
            ToolRunResult(
                tool_name="checkov",
                exit_code=1,
                stdout="",
                stderr=f"Path does not exist: {scan_path}",
                version=None,
                duration_seconds=0.0,
                success=False,
            ),
            started_at,
            finished_at,
            cmd,
            cwd,
        )

    result, result_start, result_end, original_stdout = run_tool(
        "checkov",
        cmd,
        cwd=cwd,
        timeout=300,
    )
    return result, result_start, result_end, cmd, cwd, original_stdout
