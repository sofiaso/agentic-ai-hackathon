"""Normalize findings from different tools into a common format."""

import hashlib
import json

from iac_agent.models.contracts import Finding, ToolRunResult


def normalize_findings(tool_result: ToolRunResult, stdout_override: str | None = None) -> list[Finding]:
    """
    Normalize findings from a tool result into common Finding format.

    Args:
        tool_result: Result from tool execution
        stdout_override: Optional original stdout to use instead of truncated one

    Returns:
        List of normalized findings
    """
    findings: list[Finding] = []

    # Use override if provided, otherwise use truncated stdout from result
    stdout_to_use = stdout_override if stdout_override is not None else tool_result.stdout
    
    # Tfsec returns exit code 1 when it finds issues (this is not a failure)
    # Checkov may also return non-zero exit codes but still have valid JSON output
    if not stdout_to_use:
        return findings
    
    # For terraform, we only process if it's successful (exit code 0)
    # For tfsec and checkov, we process even if exit code is non-zero (they found issues)
    if tool_result.tool_name == "terraform" and not tool_result.success:
        return findings

    # Parse directly from stdout_to_use (which is the original, non-truncated stdout)
    # This avoids the truncation that happens when creating a ToolRunResult
    try:
        if tool_result.tool_name == "terraform":
            findings.extend(_normalize_terraform_raw(tool_result, stdout_to_use))
        elif tool_result.tool_name == "tfsec":
            findings.extend(_normalize_tfsec_raw(tool_result, stdout_to_use))
        elif tool_result.tool_name == "checkov":
            findings.extend(_normalize_checkov_raw(tool_result, stdout_to_use))
    except Exception as e:
        # If normalization fails, continue with empty list
        # Debug: uncomment to see the error
        # print(f"Normalization error for {tool_result.tool_name}: {e}")
        pass

    return findings


def _normalize_terraform(result: ToolRunResult) -> list[Finding]:
    """Normalize Terraform validate output."""
    return _normalize_terraform_raw(result, result.stdout)


def _normalize_terraform_raw(result: ToolRunResult, stdout: str) -> list[Finding]:
    """Normalize Terraform validate output from raw stdout string."""
    findings: list[Finding] = []

    try:
        data = json.loads(stdout)
        if not isinstance(data, dict):
            return findings

        # Terraform validate JSON format
        if "valid" in data and not data["valid"]:
            errors = data.get("errors", [])
            for _i, error in enumerate(errors):
                finding_id = _generate_finding_id(
                    "terraform",
                    error.get("summary", ""),
                    error.get("range", {}).get("filename", ""),
                )
                findings.append(
                    Finding(
                        id=finding_id,
                        tool="terraform",
                        rule_id="terraform_validate",
                        severity="HIGH",
                        title=error.get("summary", "Terraform validation error"),
                        description=error.get("detail", ""),
                        file_path=error.get("range", {}).get("filename"),
                        line_number=error.get("range", {}).get("start", {}).get("line"),
                        resource=None,
                        raw_payload=error,
                    )
                )
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    return findings


def _normalize_tfsec(result: ToolRunResult) -> list[Finding]:
    """Normalize tfsec JSON output."""
    return _normalize_tfsec_raw(result, result.stdout)


def _normalize_tfsec_raw(result: ToolRunResult, stdout: str) -> list[Finding]:
    """Normalize tfsec JSON output from raw stdout string."""
    findings: list[Finding] = []

    try:
        data = json.loads(stdout)
        # Tfsec can return either a direct array or an object with a "results" key
        if isinstance(data, dict):
            items = data.get("results", [])
        elif isinstance(data, list):
            items = data
        else:
            return findings

        for item in items:
            if not isinstance(item, dict):
                continue

            finding_id = _generate_finding_id(
                "tfsec",
                item.get("rule_id", ""),
                item.get("location", {}).get("filename", ""),
            )
            findings.append(
                Finding(
                    id=finding_id,
                    tool="tfsec",
                    rule_id=item.get("rule_id"),
                    severity=_map_tfsec_severity(item.get("severity", "UNKNOWN")),
                    title=item.get("description", "tfsec finding"),
                    description=item.get("long_id", ""),
                    file_path=item.get("location", {}).get("filename"),
                    line_number=item.get("location", {}).get("start_line"),
                    resource=item.get("resource"),
                    raw_payload=item,
                )
            )
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        # Debug: uncomment to see the error
        # print(f"tfsec normalization error: {e}")
        pass

    return findings


def _normalize_checkov(result: ToolRunResult) -> list[Finding]:
    """Normalize Checkov JSON output."""
    return _normalize_checkov_raw(result, result.stdout)


def _normalize_checkov_raw(result: ToolRunResult, stdout: str) -> list[Finding]:
    """Normalize Checkov JSON output from raw stdout string."""
    findings: list[Finding] = []

    try:
        data = json.loads(stdout)
        if not isinstance(data, dict):
            return findings

        results = data.get("results", {})
        failed_checks = results.get("failed_checks", [])

        for check in failed_checks:
            if not isinstance(check, dict):
                continue

            finding_id = _generate_finding_id(
                "checkov",
                check.get("check_id", ""),
                check.get("file_path", ""),
            )
            findings.append(
                Finding(
                    id=finding_id,
                    tool="checkov",
                    rule_id=check.get("check_id"),
                    severity=_map_checkov_severity(check.get("severity", "UNKNOWN")),
                    title=check.get("check_name", "Checkov finding"),
                    description=check.get("guideline", ""),
                    file_path=check.get("file_path"),
                    line_number=check.get("file_line_range", [None])[0]
                    if check.get("file_line_range")
                    else None,
                    resource=check.get("resource"),
                    raw_payload=check,
                )
            )
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    return findings


def _map_tfsec_severity(severity: str) -> str:
    """Map tfsec severity to standard levels."""
    severity_upper = severity.upper()
    if severity_upper in ("CRITICAL", "HIGH"):
        return "HIGH"
    if severity_upper == "MEDIUM":
        return "MEDIUM"
    if severity_upper == "LOW":
        return "LOW"
    return "INFO"


def _map_checkov_severity(severity: str) -> str:
    """Map Checkov severity to standard levels."""
    severity_upper = severity.upper()
    if severity_upper in ("CRITICAL", "HIGH"):
        return "HIGH"
    if severity_upper == "MEDIUM":
        return "MEDIUM"
    if severity_upper == "LOW":
        return "LOW"
    return "INFO"


def _generate_finding_id(tool: str, rule_id: str, file_path: str) -> str:
    """
    Generate deterministic finding ID (no timestamps/randomness).

    Args:
        tool: Tool name
        rule_id: Rule identifier
        file_path: File path

    Returns:
        Deterministic finding ID
    """
    # Use hash of deterministic components
    content = f"{tool}:{rule_id}:{file_path}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]
