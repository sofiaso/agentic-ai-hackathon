"""Collect metrics from pipeline run."""

import time
from collections import Counter

from iac_agent.models.contracts import Report, RunMetrics


def collect_metrics(
    report: Report,
    start_time: float,
    llm_enabled: bool,
    llm_calls: int,
    llm_failures: int,
    llm_model_id: str | None = None,
    llm_region: str | None = None,
    llm_total_latency: float = 0.0,
    llm_total_input_tokens: int | None = None,
    llm_total_output_tokens: int | None = None,
) -> RunMetrics:
    """
    Collect metrics from a pipeline run.

    Args:
        report: Generated report
        start_time: Pipeline start time (from time.time())
        llm_enabled: Whether LLM was enabled
        llm_calls: Number of LLM calls made
        llm_failures: Number of LLM call failures
        llm_model_id: LLM model ID used
        llm_region: AWS region for LLM calls
        llm_total_latency: Total LLM call latency in seconds
        llm_total_input_tokens: Total input tokens (if available)
        llm_total_output_tokens: Total output tokens (if available)

    Returns:
        RunMetrics object
    """
    # Count findings by tool
    findings_by_tool: dict[str, int] = Counter(f.tool for f in report.findings)

    # Count findings by severity
    findings_by_severity: dict[str, int] = Counter(f.severity.upper() for f in report.findings)

    # Count gaps by category
    gaps_by_category: dict[str, int] = Counter(g.category.value for g in report.gaps)

    # Tool execution times
    tool_execution_times: dict[str, float] = {}
    for result in report.tool_results:
        tool_execution_times[result.tool_name] = result.duration_seconds

    duration = time.time() - start_time

    # Determine token usage note
    token_usage_note = None
    if llm_enabled and llm_calls > 0:
        if llm_total_input_tokens is None or llm_total_output_tokens is None:
            token_usage_note = "Token usage not provided by API"

    return RunMetrics(
        scan_id=report.scan_id,
        total_findings=len(report.findings),
        findings_by_tool=dict(findings_by_tool),
        findings_by_severity=dict(findings_by_severity),
        total_gaps=len(report.gaps),
        gaps_by_category=dict(gaps_by_category),
        tool_execution_times=tool_execution_times,
        llm_enabled=llm_enabled,
        llm_model_id=llm_model_id,
        llm_region=llm_region,
        llm_calls=llm_calls,
        llm_failures=llm_failures,
        llm_total_latency_seconds=llm_total_latency,
        llm_total_input_tokens=llm_total_input_tokens,
        llm_total_output_tokens=llm_total_output_tokens,
        llm_token_usage_note=token_usage_note,
        pipeline_duration_seconds=duration,
    )
