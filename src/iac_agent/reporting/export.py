"""Export report and metrics to files."""

import json
from pathlib import Path

from iac_agent.models.contracts import Report, RunMetrics
from iac_agent.reporting.render_md import render_markdown


def export_report(
    report: Report,
    metrics: RunMetrics,
    output_dir: str = "out",
    export_findings_raw: bool = False,
    export_gaps: bool = False,
    execution_errors: list[str] | None = None,
    run_path: Path | None = None,
    inventory_data: dict | None = None,
) -> None:
    """
    Export report and metrics to output directory.

    Args:
        report: Report to export
        metrics: Metrics to export
        output_dir: Output directory (default "out")
        export_findings_raw: Whether to export raw findings JSON
        export_gaps: Whether to export gaps JSON
        execution_errors: List of execution errors/tracebacks to log
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Export report.md
    md_content = render_markdown(report, run_path=run_path, inventory_data=inventory_data)
    (out_path / "report.md").write_text(md_content, encoding="utf-8")

    # Export report.json
    report_dict = report.model_dump(mode="json")
    (out_path / "report.json").write_text(
        json.dumps(report_dict, indent=2, default=str), encoding="utf-8"
    )

    # Export metrics.json
    metrics_dict = metrics.model_dump(mode="json")
    (out_path / "metrics.json").write_text(
        json.dumps(metrics_dict, indent=2, default=str), encoding="utf-8"
    )

    # Export findings_raw.json (optional)
    if export_findings_raw:
        findings_dict = [f.model_dump(mode="json") for f in report.findings]
        (out_path / "findings_raw.json").write_text(
            json.dumps(findings_dict, indent=2, default=str), encoding="utf-8"
        )

    # Export gaps.json (optional)
    if export_gaps:
        gaps_dict = [g.model_dump(mode="json") for g in report.gaps]
        (out_path / "gaps.json").write_text(
            json.dumps(gaps_dict, indent=2, default=str), encoding="utf-8"
        )

    # Export execution.log with detailed tool outputs and tracebacks
    _export_execution_log(report, metrics, execution_errors, out_path)


def _export_execution_log(
    report: Report,
    metrics: RunMetrics,
    execution_errors: list[str] | None,
    out_path: Path,
) -> None:
    """Export detailed execution log with tool outputs and tracebacks."""
    log_lines: list[str] = []

    log_lines.append("=" * 80)
    log_lines.append("IaC Agent Execution Log")
    log_lines.append("=" * 80)
    log_lines.append(f"Scan ID: {report.scan_id}")
    log_lines.append(f"Target: {report.target}")
    log_lines.append(f"Timestamp: {report.timestamp.isoformat()}")
    if report.human_request:
        log_lines.append(f"Request: {report.human_request}")
    log_lines.append("")

    # Pipeline summary
    log_lines.append("-" * 80)
    log_lines.append("Pipeline Summary")
    log_lines.append("-" * 80)
    log_lines.append(f"Total Findings: {len(report.findings)}")
    log_lines.append(f"Total Gaps: {len(report.gaps)}")
    log_lines.append(f"Pipeline Duration: {metrics.pipeline_duration_seconds:.2f}s")
    log_lines.append(f"LLM Enabled: {metrics.llm_enabled}")
    if metrics.llm_enabled:
        log_lines.append(f"LLM Calls: {metrics.llm_calls}")
        log_lines.append(f"LLM Failures: {metrics.llm_failures}")
    log_lines.append("")

    # Tool execution results
    if report.tool_results:
        log_lines.append("-" * 80)
        log_lines.append("Tool Execution Results (Detailed)")
        log_lines.append("-" * 80)
        log_lines.append("")

        for i, result in enumerate(report.tool_results, 1):
            log_lines.append(f"[{i}] {result.tool_name}")
            log_lines.append("-" * 40)
            log_lines.append(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
            log_lines.append(f"Exit Code: {result.exit_code}")
            log_lines.append(f"Duration: {result.duration_seconds:.2f}s")
            if result.version:
                log_lines.append(f"Version: {result.version}")
            log_lines.append("")

            # Full stdout output
            log_lines.append("STDOUT:")
            log_lines.append("-" * 40)
            if result.stdout:
                log_lines.append(result.stdout)
            else:
                log_lines.append("(empty)")
            log_lines.append("")

            # Full stderr output
            log_lines.append("STDERR:")
            log_lines.append("-" * 40)
            if result.stderr:
                log_lines.append(result.stderr)
            else:
                log_lines.append("(empty)")
            log_lines.append("")

            log_lines.append("")

    # Execution errors and tracebacks
    if execution_errors:
        log_lines.append("-" * 80)
        log_lines.append("Execution Errors and Tracebacks")
        log_lines.append("-" * 80)
        log_lines.append("")
        for i, error in enumerate(execution_errors, 1):
            log_lines.append(f"Error {i}:")
            log_lines.append("-" * 40)
            log_lines.append(error)
            log_lines.append("")

    # Findings summary
    if report.findings:
        log_lines.append("-" * 80)
        log_lines.append("Findings Summary")
        log_lines.append("-" * 80)
        for finding in report.findings:
            log_lines.append(f"  [{finding.id}] {finding.tool}: {finding.title}")
            log_lines.append(f"    Severity: {finding.severity}")
            if finding.file_path:
                log_lines.append(f"    File: {finding.file_path}")
                if finding.line_number:
                    log_lines.append(f"    Line: {finding.line_number}")
        log_lines.append("")

    # Gaps summary
    if report.gaps:
        log_lines.append("-" * 80)
        log_lines.append("Gaps Summary")
        log_lines.append("-" * 80)
        for gap in report.gaps:
            log_lines.append(f"  [{gap.gap_id}] {gap.category.value}: {gap.title}")
            log_lines.append(f"    Severity: {gap.severity}")
            log_lines.append(f"    Findings: {len(gap.findings)}")
        log_lines.append("")

    log_lines.append("=" * 80)
    log_lines.append("End of Execution Log")
    log_lines.append("=" * 80)

    # Write log file
    log_content = "\n".join(log_lines)
    (out_path / "execution.log").write_text(log_content, encoding="utf-8")
