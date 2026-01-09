"""Create and manage run directory artifacts for audit-grade logging."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from iac_agent.models.contracts import ToolRunResult

# Maximum size for stdout/stderr files (10 MB)
MAX_LOG_SIZE = 10 * 1024 * 1024


def create_run_directory(run_dir_base: str, run_id: str) -> Path:
    """
    Create run directory structure.

    Args:
        run_dir_base: Base directory for runs (e.g., "out/runs")
        run_id: Unique run identifier

    Returns:
        Path to created run directory
    """
    run_path = Path(run_dir_base) / run_id
    run_path.mkdir(parents=True, exist_ok=True)

    # Create tool subdirectories
    for tool in ["terraform", "tfsec", "checkov"]:
        (run_path / tool).mkdir(exist_ok=True)

    return run_path


def save_manifest(
    run_path: Path,
    manifest_data: dict[str, Any],
) -> None:
    """
    Save manifest.json to run directory.

    Args:
        run_path: Run directory path
        manifest_data: Manifest data dictionary
    """
    manifest_file = run_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_data, indent=2, default=str), encoding="utf-8")


def save_inventory(
    run_path: Path,
    inventory_data: dict[str, Any],
) -> None:
    """
    Save inventory.json to run directory.

    Args:
        run_path: Run directory path
        inventory_data: Inventory data dictionary
    """
    inventory_file = run_path / "inventory.json"
    inventory_file.write_text(json.dumps(inventory_data, indent=2, default=str), encoding="utf-8")


def save_tool_artifacts(
    run_path: Path,
    tool_name: str,
    result: ToolRunResult,
    cmd: list[str],
    cwd: str | None,
    target_path: str,
    started_at: datetime,
    finished_at: datetime,
    original_stdout: str | None = None,
) -> None:
    """
    Save tool execution artifacts to run directory.

    Args:
        run_path: Run directory path
        tool_name: Tool name (terraform, tfsec, checkov)
        result: ToolRunResult
        cmd: Command arguments list
        cwd: Working directory used
        target_path: Target path scanned
        started_at: Start timestamp
        finished_at: End timestamp
        original_stdout: Original stdout before truncation (optional)
    """
    tool_dir = run_path / tool_name
    tool_dir.mkdir(exist_ok=True)

    # Save version
    if result.version:
        (tool_dir / "version.txt").write_text(result.version, encoding="utf-8")
    else:
        (tool_dir / "version.txt").write_text("(not available)", encoding="utf-8")

    # Save command
    cmd_str = " ".join(cmd)
    (tool_dir / "cmd.txt").write_text(cmd_str, encoding="utf-8")

    # Save stdout (use original if provided, otherwise use truncated from result)
    stdout_content = original_stdout if original_stdout is not None else result.stdout
    if len(stdout_content.encode("utf-8")) > MAX_LOG_SIZE:
        stdout_content = (
            stdout_content[:MAX_LOG_SIZE] + "\n... (truncated, original size exceeded 10MB)"
        )
    (tool_dir / "stdout.log").write_text(stdout_content, encoding="utf-8")

    # Save stderr (with size cap)
    stderr_content = result.stderr
    if len(stderr_content.encode("utf-8")) > MAX_LOG_SIZE:
        stderr_content = (
            stderr_content[:MAX_LOG_SIZE] + "\n... (truncated, original size exceeded 10MB)"
        )
    (tool_dir / "stderr.log").write_text(stderr_content, encoding="utf-8")

    # Save results.json if tool supports JSON output
    # Use original stdout if available (before truncation) for JSON parsing
    stdout_for_json = original_stdout if original_stdout is not None else result.stdout
    if tool_name in ["tfsec", "checkov"] and stdout_for_json:
        # For tfsec, exit code 1 means it found issues (still valid JSON)
        # For checkov, only process if successful
        should_parse = (tool_name == "tfsec") or (tool_name == "checkov" and result.success)
        if should_parse:
            try:
                # Try to parse as JSON
                json_data = json.loads(stdout_for_json)
                (tool_dir / "results.json").write_text(
                    json.dumps(json_data, indent=2, default=str), encoding="utf-8"
                )
            except (json.JSONDecodeError, Exception):
                # If not valid JSON, save empty object
                (tool_dir / "results.json").write_text("{}", encoding="utf-8")
        else:
            (tool_dir / "results.json").write_text("{}", encoding="utf-8")
    elif tool_name == "terraform" and result.success and stdout_for_json:
        try:
            # Terraform validate outputs JSON
            json_data = json.loads(stdout_for_json)
            (tool_dir / "results.json").write_text(
                json.dumps(json_data, indent=2, default=str), encoding="utf-8"
            )
        except (json.JSONDecodeError, Exception):
            (tool_dir / "results.json").write_text("{}", encoding="utf-8")
    else:
        # Save empty JSON for failed or non-JSON tools
        (tool_dir / "results.json").write_text("{}", encoding="utf-8")


def build_manifest(
    run_id: str,
    repo_url: str | None,
    local_path: str | None,
    repo_ref: str | None,
    commit: str | None,
    flags: dict[str, bool],
    tool_versions: dict[str, str | None],
    tool_executions: list[dict[str, Any]],
    counts: dict[str, int],
    tool_routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build manifest.json structure.

    Args:
        run_id: Run identifier
        repo_url: Repository URL if provided
        local_path: Local path if provided
        repo_ref: Repository reference (branch/tag)
        commit: Git commit hash
        flags: Execution flags
        tool_versions: Tool versions
        tool_executions: List of tool execution details
        counts: Counts (findings_raw, findings_deduped, gaps_total)
        tool_routing: Tool routing information if LLM tool router was used

    Returns:
        Manifest dictionary
    """
    manifest = {
        "run_id": run_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "repo_url": repo_url,
        "local_path": local_path,
        "repo_ref": repo_ref,
        "commit": commit,
        "flags": flags,
        "tool_versions": tool_versions,
        "tool_executions": tool_executions,
        "counts": counts,
    }

    # Add tool routing information if available
    if tool_routing:
        manifest["tool_routing"] = tool_routing

    return manifest
