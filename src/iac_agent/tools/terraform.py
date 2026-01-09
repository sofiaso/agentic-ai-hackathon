"""Terraform validate tool wrapper."""

from datetime import datetime
from pathlib import Path

from iac_agent.models.contracts import ToolRunResult
from iac_agent.tools.base import run_tool


def run_terraform_validate(
    scan_path: str, execute: bool = False
) -> tuple[ToolRunResult, datetime, datetime, list[str], str | None]:
    """
    Run terraform validate on a directory.

    Args:
        scan_path: Path to directory containing Terraform files
        execute: Whether to actually execute (default False for dry-run)

    Returns:
        Tuple of (ToolRunResult, started_at, finished_at, cmd, cwd)
    """
    started_at = datetime.utcnow()
    cmd = ["terraform", "validate", "-json"]
    cwd = str(Path(scan_path).resolve()) if execute else None

    if not execute:
        finished_at = datetime.utcnow()
        return (
            ToolRunResult(
                tool_name="terraform",
                exit_code=0,
                stdout="[DRY-RUN] terraform validate would run here",
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

    path = Path(scan_path)
    if not path.exists():
        finished_at = datetime.utcnow()
        return (
            ToolRunResult(
                tool_name="terraform",
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

    # Initialize terraform if needed
    init_result, init_start, init_end, init_original_stdout = run_tool(
        "terraform",
        ["terraform", "init", "-backend=false"],
        cwd=str(path),
        timeout=120,
    )

    if not init_result.success:
        return (
            ToolRunResult(
                tool_name="terraform",
                exit_code=init_result.exit_code,
                stdout=init_result.stdout,
                stderr=init_result.stderr,
                version=init_result.version,
                duration_seconds=init_result.duration_seconds,
                success=False,
            ),
            init_start,
            init_end,
            ["terraform", "init", "-backend=false"],
            cwd,
            init_original_stdout,
        )

    # Run validate
    result, result_start, result_end, original_stdout = run_tool(
        "terraform",
        cmd,
        cwd=str(path),
        timeout=60,
    )
    return result, result_start, result_end, cmd, cwd, original_stdout
