"""Markdown report renderer."""

from pathlib import Path

from iac_agent.models.contracts import Report


def render_markdown(
    report: Report, run_path: Path | None = None, inventory_data: dict | None = None
) -> str:
    """
    Render report as Markdown.

    Args:
        report: Report to render

    Returns:
        Markdown string
    """
    lines: list[str] = []

    # Header
    lines.append("# IaC Security Assessment Report")
    lines.append("")
    lines.append(f"**Scan ID:** {report.scan_id}")
    lines.append(f"**Target:** {report.target}")
    lines.append(f"**Timestamp:** {report.timestamp.isoformat()}")
    if report.human_request:
        lines.append(f"**Request:** {report.human_request}")
    lines.append("")

    # Summary
    if report.summary:
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(report.summary)
        lines.append("")

    # Evidence section (if run_path provided)
    if run_path:
        lines.append("## Evidence")
        lines.append("")
        if inventory_data:
            lines.append(
                f"**Scan Paths Resolved:** {', '.join(inventory_data.get('scan_paths_resolved', []))}"
            )
            lines.append(f"**Terraform Files Found:** {inventory_data.get('total_tf_files', 0)}")
            lines.append("")

        # Tool versions and exit codes
        if report.tool_results:
            lines.append("**Tool Versions:**")
            for result in report.tool_results:
                version_str = result.version if result.version else "(not available)"
                lines.append(f"  - {result.tool_name}: {version_str}")
            lines.append("")

            lines.append("**Tool Exit Codes:**")
            for result in report.tool_results:
                status = "SUCCESS" if result.success else "FAILED"
                lines.append(f"  - {result.tool_name}: {result.exit_code} ({status})")
            lines.append("")

        # Pointers to saved artifacts (only manifest and inventory)
        lines.append("**Saved Artifacts:**")
        lines.append(f"  - Manifest: `{run_path / 'manifest.json'}`")
        lines.append(f"  - Inventory: `{run_path / 'inventory.json'}`")
        lines.append("")

    # Scan Plan (includes tool routing information)
    if report.scan_plan:
        lines.append("## Scan Plan")
        lines.append("")
        lines.append(f"**Selected Tools:** {', '.join([opt.value for opt in report.scan_plan.options])}")
        if report.scan_plan.reasoning:
            # Parse tool routing info from reasoning if present
            reasoning = report.scan_plan.reasoning
            if "Tool router:" in reasoning or "Intent:" in reasoning or "Fallback used:" in reasoning:
                # Tool routing info is embedded in reasoning
                parts = reasoning.split(" | ")
                for part in parts:
                    if part.startswith("Tool router:"):
                        lines.append(f"**Tool Router Rationale:** {part.replace('Tool router: ', '')}")
                    elif part.startswith("Intent:"):
                        lines.append(f"**User Intent Summary:** {part.replace('Intent: ', '')}")
                    elif part.startswith("Fallback used:"):
                        fallback_used = part.replace("Fallback used: ", "").lower() == "true"
                        lines.append(f"**Fallback Used:** {fallback_used}")
                # Extract the original reasoning if not tool router
                original_reasoning = next((p for p in parts if not any(p.startswith(x) for x in ["Tool router:", "Intent:", "Fallback used:"])), None)
                if original_reasoning:
                    lines.append(f"**Reasoning:** {original_reasoning}")
            else:
                lines.append(f"**Reasoning:** {report.scan_plan.reasoning}")
        lines.append("")

    # Findings
    lines.append("## Findings")
    lines.append("")
    lines.append(f"Total Findings: {len(report.findings)}")
    lines.append("")

    if report.findings:
        # Group by severity
        by_severity: dict[str, list] = {}
        for finding in report.findings:
            sev = finding.severity.upper()
            if sev not in by_severity:
                by_severity[sev] = []
            by_severity[sev].append(finding)

        for severity in ["HIGH", "MEDIUM", "LOW", "INFO"]:
            if severity not in by_severity:
                continue

            lines.append(f"### {severity} Severity ({len(by_severity[severity])})")
            lines.append("")

            for finding in by_severity[severity]:
                lines.append(f"#### {finding.title}")
                lines.append("")
                lines.append(f"- **ID:** `{finding.id}`")
                lines.append(f"- **Tool:** {finding.tool}")
                if finding.rule_id:
                    lines.append(f"- **Rule:** {finding.rule_id}")
                if finding.file_path:
                    lines.append(f"- **File:** {finding.file_path}")
                    if finding.line_number:
                        lines.append(f"- **Line:** {finding.line_number}")
                if finding.resource:
                    lines.append(f"- **Resource:** {finding.resource}")
                if finding.description:
                    lines.append(f"- **Description:** {finding.description}")
                lines.append("")

    # Gaps
    lines.append("## Security Gaps")
    lines.append("")
    lines.append(f"Total Gaps: {len(report.gaps)}")
    lines.append("")

    if report.gaps:
        # Group by category
        by_category: dict[str, list] = {}
        for gap in report.gaps:
            cat = gap.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(gap)

        for category in sorted(by_category.keys()):
            lines.append(f"### {category.title()} ({len(by_category[category])})")
            lines.append("")

            for gap in by_category[category]:
                lines.append(f"#### {gap.title}")
                lines.append("")
                lines.append(f"- **Gap ID:** `{gap.gap_id}`")
                lines.append(f"- **Severity:** {gap.severity}")
                lines.append(f"- **Findings:** {len(gap.findings)}")
                if gap.fedramp_families:
                    lines.append(f"- **FedRAMP Families:** {', '.join(gap.fedramp_families)}")
                if gap.description:
                    lines.append(f"- **Description:** {gap.description}")
                if gap.remediation_checklist:
                    lines.append("")
                    lines.append("**Remediation Checklist:**")
                    for item in gap.remediation_checklist:
                        lines.append(f"- {item}")
                if gap.confidence > 0:
                    lines.append(f"- **Confidence:** {gap.confidence:.2f}")
                if gap.requires_human_decision:
                    lines.append("- **WARNING: Requires Human Decision**")
                lines.append("")

    # Tool Results
    if report.tool_results:
        lines.append("## Tool Execution Results")
        lines.append("")
        for result in report.tool_results:
            status = "[SUCCESS]" if result.success else "[FAILED]"
            lines.append(f"### {result.tool_name} - {status}")
            lines.append("")
            if result.version:
                lines.append(f"- **Version:** {result.version}")
            lines.append(f"- **Exit Code:** {result.exit_code}")
            lines.append(f"- **Duration:** {result.duration_seconds:.2f}s")
            lines.append(f"- **Success:** {result.success}")
            lines.append("")

            # Show stdout output
            if result.stdout:
                lines.append("**Standard Output:**")
                lines.append("```")
                # Show first 2000 chars of stdout, or all if less
                stdout_preview = (
                    result.stdout
                    if len(result.stdout) <= 2000
                    else result.stdout[:2000]
                    + "\n... (truncated, see full output in execution.log)"
                )
                lines.append(stdout_preview)
                lines.append("```")
                lines.append("")

            # Show stderr output
            if result.stderr:
                lines.append("**Error Output:**")
                lines.append("```")
                # Show first 2000 chars of stderr, or all if less
                stderr_preview = (
                    result.stderr
                    if len(result.stderr) <= 2000
                    else result.stderr[:2000]
                    + "\n... (truncated, see full output in execution.log)"
                )
                lines.append(stderr_preview)
                lines.append("```")
                lines.append("")

            # Note about full logs
            if len(result.stdout) > 2000 or len(result.stderr) > 2000:
                lines.append("> **Note:** Full output available in `execution.log` file")
                lines.append("")
            lines.append("")

    return "\n".join(lines)
