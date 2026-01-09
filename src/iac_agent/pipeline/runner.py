"""Main pipeline runner orchestrating all stages."""

import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from iac_agent.analysis.dedup import deduplicate_findings
from iac_agent.analysis.gap_builder import build_gaps
from iac_agent.analysis.normalize import normalize_findings
from iac_agent.llm.bedrock import BedrockClient
from iac_agent.metrics.collector import collect_metrics
from iac_agent.models.contracts import (
    Finding,
    Gap,
    Report,
    RunMetrics,
    ScanPlan,
    ScanPlanOption,
    ToolRunResult,
)
from iac_agent.observability.inventory import build_inventory, get_repo_ref
from iac_agent.observability.run_artifacts import (
    build_manifest,
    create_run_directory,
    save_inventory,
    save_manifest,
    save_tool_artifacts,
)
from iac_agent.pipeline.paths import resolve_scan_paths
from iac_agent.pipeline.repo import prepare_repo
from iac_agent.tools.checkov import run_checkov
from iac_agent.tools.terraform import run_terraform_validate
from iac_agent.tools.tfsec import run_tfsec


def run_pipeline(
    repo_url: str | None = None,
    local_path: str | None = None,
    human_request: str | None = None,
    execute_tools: bool = False,
    llm_enable: bool = False,
    allow_network: bool = False,
    run_dir_base: str = "out/runs",
    llm_model_id: str | None = None,
    llm_region: str | None = None,
    llm_tool_router: bool | None = None,
    general_tool: str = "checkov",
) -> tuple[Report, RunMetrics, Path | None]:
    """
    Run the complete IaC assessment pipeline.

    Args:
        repo_url: Git repository URL
        local_path: Local directory path
        human_request: Human request/query
        execute_tools: Whether to execute tools (default False)
        llm_enable: Whether to enable LLM enrichment (default False)
        allow_network: Whether to allow network operations (default False)
        run_dir_base: Base directory for run artifacts (default "out/runs")
        llm_model_id: LLM model ID (defaults to env BEDROCK_MODEL_ID or "eu.amazon.nova-2-lite-v1:0")
        llm_region: AWS region for LLM (defaults to env AWS_REGION/AWS_DEFAULT_REGION or "eu-north-1")
        llm_tool_router: Whether to use LLM tool router (default True if llm_enable, else False)
        general_tool: General fallback tool ID (default "checkov")

    Returns:
        Tuple of (Report, RunMetrics, run_path)
    """
    start_time = time.time()
    scan_id = _generate_scan_id(repo_url or local_path or "unknown", human_request)

    # Generate run_id (timestamp-based is allowed for run_id)
    run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f") + "_" + scan_id[:8]

    # Create run directory
    run_path: Path | None = None
    if execute_tools:
        run_path = create_run_directory(run_dir_base, run_id)

    # Stage 1: Prepare repository
    repo_path, repo_error = prepare_repo(repo_url, local_path, allow_network)
    if not repo_path and repo_error:
        # Return empty report with error
        report = Report(
            scan_id=scan_id,
            target=repo_url or local_path or "unknown",
            human_request=human_request,
            tool_results=[repo_error] if repo_error else [],
        )
        metrics = collect_metrics(
            report,
            start_time,
            llm_enable,
            0,
            0,
            llm_model_id=None,
            llm_region=None,
            llm_total_latency=0.0,
            llm_total_input_tokens=None,
            llm_total_output_tokens=None,
        )
        return report, metrics, None

    # Stage 2: Resolve scan paths
    scan_paths = resolve_scan_paths(repo_path)

    # Stage 2.5: Build inventory BEFORE running tools (if executing)
    inventory_data: dict[str, Any] = {}
    repo_ref_info: dict[str, Any] = {}
    if execute_tools and run_path:
        inventory_data = build_inventory(scan_paths, repo_path)
        repo_ref_info = get_repo_ref(repo_path)
        save_inventory(run_path, inventory_data)

    # Stage 3: Determine scan plan (LLM tool router if enabled)
    scan_plan: ScanPlan | None = None
    tool_router_output = None
    llm_client: BedrockClient | None = None
    llm_calls = 0
    llm_failures = 0
    llm_total_latency = 0.0
    llm_total_input_tokens: int | None = None
    llm_total_output_tokens: int | None = None
    llm_model_id_used: str | None = None
    llm_region_used: str | None = None

    # Determine if tool router should be used
    use_tool_router = llm_tool_router if llm_tool_router is not None else llm_enable

    if llm_enable:
        llm_client = BedrockClient(model_id=llm_model_id, region=llm_region)
        llm_model_id_used = llm_client.model_id
        llm_region_used = llm_client.region

        # Use new tool router if enabled, otherwise use legacy router
        if use_tool_router and human_request:
            tool_router_output = llm_client.tool_router(human_request)
            llm_calls += 1

            # Track LLM metadata if available
            if tool_router_output and hasattr(tool_router_output, "_llm_metadata"):
                metadata = tool_router_output._llm_metadata
                llm_total_latency += metadata.get("latency_seconds", 0.0)
                if metadata.get("input_tokens"):
                    llm_total_input_tokens = (llm_total_input_tokens or 0) + metadata["input_tokens"]
                if metadata.get("output_tokens"):
                    llm_total_output_tokens = (llm_total_output_tokens or 0) + metadata["output_tokens"]

            if tool_router_output and tool_router_output.selected_tools:
                # Convert tool IDs to ScanPlanOption
                options: list[ScanPlanOption] = []
                for tool_id in tool_router_output.selected_tools:
                    if tool_id == "terraform_validate":
                        options.append(ScanPlanOption.TERRAFORM_VALIDATE)
                    elif tool_id == "tfsec":
                        options.append(ScanPlanOption.TFSEC)
                    elif tool_id == "checkov":
                        options.append(ScanPlanOption.CHECKOV)

                # If options is empty (shouldn't happen due to fallback), use ALL
                if not options:
                    options = [ScanPlanOption.ALL]

                scan_plan = ScanPlan(
                    options=options,
                    reasoning=f"Tool router: {tool_router_output.rationale}",
                )
            else:
                llm_failures += 1
                # Default to all tools if tool router fails
                scan_plan = ScanPlan(
                    options=[ScanPlanOption.ALL],
                    reasoning="LLM tool router failed, defaulting to all tools",
                )
        else:
            # Legacy router (fallback when tool router not used or no human request)
            router_output = llm_client.router(human_request, f"Repository: {repo_path}")
            llm_calls += 1

            # Track LLM metadata if available
            if router_output and hasattr(router_output, "_llm_metadata"):
                metadata = router_output._llm_metadata
                llm_total_latency += metadata.get("latency_seconds", 0.0)
                if metadata.get("input_tokens"):
                    llm_total_input_tokens = (llm_total_input_tokens or 0) + metadata["input_tokens"]
                if metadata.get("output_tokens"):
                    llm_total_output_tokens = (llm_total_output_tokens or 0) + metadata["output_tokens"]

            if router_output:
                scan_plan = ScanPlan(
                    options=[ScanPlanOption(opt) for opt in router_output.options],
                    reasoning=router_output.reasoning,
                )
            else:
                llm_failures += 1
                # Default to all tools if router fails
                scan_plan = ScanPlan(
                    options=[ScanPlanOption.ALL],
                    reasoning="LLM router failed, defaulting to all tools",
                )

    # Stage 4: Run tools
    tool_results: list[ToolRunResult] = []
    all_findings: list[Finding] = []
    tool_executions: list[dict[str, Any]] = []
    tool_versions: dict[str, str | None] = {}

    # Determine which tools to run
    tools_to_run = _determine_tools(scan_plan)

    for scan_path in scan_paths:
        if ScanPlanOption.TERRAFORM_VALIDATE in tools_to_run or ScanPlanOption.ALL in tools_to_run:
            result, started_at, finished_at, cmd, cwd, original_stdout = run_terraform_validate(
                scan_path, execute_tools
            )
            tool_results.append(result)
            # normalize_findings expects ToolRunResult, not tuple
            # Pass original stdout to avoid truncated JSON
            findings = normalize_findings(result, stdout_override=original_stdout)
            all_findings.extend(findings)

            # Track tool execution details
            tool_versions["terraform"] = result.version
            tool_executions.append(
                {
                    "tool": "terraform",
                    "cmd": cmd,
                    "cwd": cwd,
                    "target_path": scan_path,
                    "started_at": started_at.isoformat() + "Z",
                    "finished_at": finished_at.isoformat() + "Z",
                    "duration_seconds": result.duration_seconds,
                    "exit_code": result.exit_code,
                    "success": result.success,
                }
            )

            # Save artifacts if executing
            if execute_tools and run_path:
                save_tool_artifacts(
                    run_path, "terraform", result, cmd, cwd, scan_path, started_at, finished_at, original_stdout
                )

        if ScanPlanOption.TFSEC in tools_to_run or ScanPlanOption.ALL in tools_to_run:
            result, started_at, finished_at, cmd, cwd, original_stdout = run_tfsec(scan_path, execute_tools)
            tool_results.append(result)
            # normalize_findings expects ToolRunResult, not tuple
            # Pass original stdout to avoid truncated JSON
            findings = normalize_findings(result, stdout_override=original_stdout)
            all_findings.extend(findings)

            # Track tool execution details
            tool_versions["tfsec"] = result.version
            tool_executions.append(
                {
                    "tool": "tfsec",
                    "cmd": cmd,
                    "cwd": cwd,
                    "target_path": scan_path,
                    "started_at": started_at.isoformat() + "Z",
                    "finished_at": finished_at.isoformat() + "Z",
                    "duration_seconds": result.duration_seconds,
                    "exit_code": result.exit_code,
                    "success": result.success,
                }
            )

            # Save artifacts if executing
            if execute_tools and run_path:
                save_tool_artifacts(
                    run_path, "tfsec", result, cmd, cwd, scan_path, started_at, finished_at, original_stdout
                )

        if ScanPlanOption.CHECKOV in tools_to_run or ScanPlanOption.ALL in tools_to_run:
            result, started_at, finished_at, cmd, cwd, original_stdout = run_checkov(scan_path, execute_tools)
            tool_results.append(result)
            # normalize_findings expects ToolRunResult, not tuple
            # Pass original stdout to avoid truncated JSON
            findings = normalize_findings(result, stdout_override=original_stdout)
            all_findings.extend(findings)

            # Track tool execution details
            tool_versions["checkov"] = result.version
            tool_executions.append(
                {
                    "tool": "checkov",
                    "cmd": cmd,
                    "cwd": cwd,
                    "target_path": scan_path,
                    "started_at": started_at.isoformat() + "Z",
                    "finished_at": finished_at.isoformat() + "Z",
                    "duration_seconds": result.duration_seconds,
                    "exit_code": result.exit_code,
                    "success": result.success,
                }
            )

            # Save artifacts if executing
            if execute_tools and run_path:
                save_tool_artifacts(
                    run_path, "checkov", result, cmd, cwd, scan_path, started_at, finished_at, original_stdout
                )

    # Stage 5: Deduplicate findings
    findings_raw_count = len(all_findings)
    all_findings = deduplicate_findings(all_findings)
    findings_deduped_count = len(all_findings)

    # Stage 6: Build gaps
    gaps = build_gaps(all_findings)

    # Stage 7: LLM enrichment (if enabled)
    if llm_enable and llm_client:
        gaps, llm_calls, llm_failures, llm_latency, llm_input_tokens, llm_output_tokens = (
            _enrich_gaps(
                gaps,
                all_findings,
                llm_client,
                llm_calls,
                llm_failures,
                llm_total_latency,
                llm_total_input_tokens,
                llm_total_output_tokens,
            )
        )
        llm_total_latency = llm_latency
        llm_total_input_tokens = llm_input_tokens
        llm_total_output_tokens = llm_output_tokens

    # Stage 8: Generate summary (if LLM enabled)
    summary = ""
    if llm_enable and llm_client:
        summary_result = _generate_summary(
            all_findings,
            gaps,
            llm_client,
            llm_total_latency,
            llm_total_input_tokens,
            llm_total_output_tokens,
        )
        if summary_result:
            summary = summary_result[0]
            llm_total_latency = summary_result[1]
            llm_total_input_tokens = summary_result[2]
            llm_total_output_tokens = summary_result[3]
        else:
            summary = _generate_default_summary(all_findings, gaps)

    # Stage 9: Build report
    # Always include tool_results in report (even if empty) for debugging
    # Include tool router information if available
    report_scan_plan = scan_plan
    if tool_router_output:
        # Enrich scan plan with tool router details
        report_scan_plan = ScanPlan(
            options=scan_plan.options if scan_plan else [],
            reasoning=(
                f"{tool_router_output.rationale} | "
                f"Intent: {tool_router_output.tool_intent_summary} | "
                f"Fallback used: {tool_router_output.fallback_used}"
            ),
        )

    report = Report(
        scan_id=scan_id,
        target=repo_url or local_path or "unknown",
        human_request=human_request,
        findings=all_findings,
        gaps=gaps,
        scan_plan=report_scan_plan,
        tool_results=tool_results,  # Always included for debugging
        summary=summary or _generate_default_summary(all_findings, gaps),
    )

    # Stage 10: Collect metrics
    metrics = collect_metrics(
        report,
        start_time,
        llm_enable,
        llm_calls,
        llm_failures,
        llm_model_id=llm_model_id_used,
        llm_region=llm_region_used,
        llm_total_latency=llm_total_latency,
        llm_total_input_tokens=llm_total_input_tokens,
        llm_total_output_tokens=llm_total_output_tokens,
    )

    # Stage 11: Save manifest (if executing)
    if execute_tools and run_path:
        # Include tool routing information in manifest
        tool_routing_info: dict[str, Any] | None = None
        if tool_router_output:
            tool_routing_info = {
                "selected_tools": tool_router_output.selected_tools,
                "fallback_used": tool_router_output.fallback_used,
                "rationale": tool_router_output.rationale,
                "tool_intent_summary": tool_router_output.tool_intent_summary,
            }

        manifest = build_manifest(
            run_id=run_id,
            repo_url=repo_url,
            local_path=local_path,
            repo_ref=repo_ref_info.get("repo_ref"),
            commit=repo_ref_info.get("commit"),
            flags={
                "allow_network": allow_network,
                "execute_tools": execute_tools,
                "llm_enable": llm_enable,
                "llm_tool_router": use_tool_router,
            },
            tool_versions=tool_versions,
            tool_executions=tool_executions,
            counts={
                "findings_raw": findings_raw_count,
                "findings_deduped": findings_deduped_count,
                "gaps_total": len(gaps),
            },
            tool_routing=tool_routing_info,
        )
        save_manifest(run_path, manifest)

    return report, metrics, run_path


def _generate_scan_id(target: str, human_request: str | None) -> str:
    """Generate deterministic scan ID."""
    content = f"{target}:{human_request or ''}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _determine_tools(scan_plan: ScanPlan | None) -> list[ScanPlanOption]:
    """Determine which tools to run based on scan plan."""
    if not scan_plan:
        return [ScanPlanOption.ALL]

    if ScanPlanOption.ALL in scan_plan.options:
        return [ScanPlanOption.ALL]

    return scan_plan.options


def _enrich_gaps(
    gaps: list[Gap],
    findings: list[Finding],
    llm_client: BedrockClient,
    llm_calls: int,
    llm_failures: int,
    llm_total_latency: float,
    llm_total_input_tokens: int | None,
    llm_total_output_tokens: int | None,
) -> tuple[list[Gap], int, int, float, int | None, int | None]:
    """Enrich gaps with LLM-generated content."""
    enriched: list[Gap] = []
    calls = llm_calls
    failures = llm_failures
    total_latency = llm_total_latency
    total_input_tokens = llm_total_input_tokens
    total_output_tokens = llm_total_output_tokens

    for gap in gaps:
        # FedRAMP mapping
        fedramp_output = llm_client.map_fedramp(gap.title, gap.description)
        calls += 1

        # Track LLM metadata
        if fedramp_output and hasattr(fedramp_output, "_llm_metadata"):
            metadata = fedramp_output._llm_metadata
            total_latency += metadata.get("latency_seconds", 0.0)
            if metadata.get("input_tokens"):
                total_input_tokens = (total_input_tokens or 0) + metadata["input_tokens"]
            if metadata.get("output_tokens"):
                total_output_tokens = (total_output_tokens or 0) + metadata["output_tokens"]

        if fedramp_output:
            gap.fedramp_families = fedramp_output.families
        else:
            failures += 1

        # Remediation advisor
        findings_summary = _get_findings_summary(gap, findings)
        remediation_output = llm_client.remediation_advisor(
            gap.title, gap.description, findings_summary
        )
        calls += 1

        # Track LLM metadata
        if remediation_output and hasattr(remediation_output, "_llm_metadata"):
            metadata = remediation_output._llm_metadata
            total_latency += metadata.get("latency_seconds", 0.0)
            if metadata.get("input_tokens"):
                total_input_tokens = (total_input_tokens or 0) + metadata["input_tokens"]
            if metadata.get("output_tokens"):
                total_output_tokens = (total_output_tokens or 0) + metadata["output_tokens"]

        if remediation_output:
            gap.remediation_checklist = [item.step for item in remediation_output.checklist]
            gap.confidence = remediation_output.overall_confidence
            gap.requires_human_decision = remediation_output.requires_human_decision
        else:
            failures += 1

        enriched.append(gap)

    return enriched, calls, failures, total_latency, total_input_tokens, total_output_tokens


def _get_findings_summary(gap: Gap, all_findings: list[Finding]) -> str:
    """Get summary of findings for a gap."""
    gap_findings = [f for f in all_findings if f.id in gap.findings]
    titles = [f.title for f in gap_findings[:5]]  # Limit to 5
    return "; ".join(titles)


def _generate_summary(
    findings: list[Finding],
    gaps: list[Gap],
    llm_client: BedrockClient,
    llm_total_latency: float,
    llm_total_input_tokens: int | None,
    llm_total_output_tokens: int | None,
) -> tuple[str, float, int | None, int | None] | None:
    """Generate summary using LLM. Returns (summary_text, latency, input_tokens, output_tokens)."""
    summary_data = {
        "total_findings": len(findings),
        "total_gaps": len(gaps),
        "gaps_by_category": {},
    }
    for gap in gaps:
        category = gap.category.value
        summary_data["gaps_by_category"][category] = (
            summary_data["gaps_by_category"].get(category, 0) + 1
        )

    summary_result = llm_client.summary_writer(str(summary_data))

    if summary_result:
        summary_text, latency, input_tokens, output_tokens = summary_result
        total_latency = llm_total_latency + latency
        if input_tokens:
            total_input_tokens = (llm_total_input_tokens or 0) + input_tokens
        else:
            total_input_tokens = llm_total_input_tokens
        if output_tokens:
            total_output_tokens = (llm_total_output_tokens or 0) + output_tokens
        else:
            total_output_tokens = llm_total_output_tokens
        return (summary_text, total_latency, total_input_tokens, total_output_tokens)

    return None


def _generate_default_summary(findings: list[Finding], gaps: list[Gap]) -> str:
    """Generate default summary without LLM."""
    return f"""Security Assessment Summary

Total Findings: {len(findings)}
Total Gaps: {len(gaps)}

Findings by Severity:
{_count_by_severity(findings)}

Gaps by Category:
{_count_gaps_by_category(gaps)}
"""


def _count_by_severity(findings: list[Finding]) -> str:
    """Count findings by severity."""
    counts: dict[str, int] = {}
    for finding in findings:
        sev = finding.severity.upper()
        counts[sev] = counts.get(sev, 0) + 1
    return "\n".join(f"  {sev}: {count}" for sev, count in sorted(counts.items()))


def _count_gaps_by_category(gaps: list[Gap]) -> str:
    """Count gaps by category."""
    counts: dict[str, int] = {}
    for gap in gaps:
        cat = gap.category.value
        counts[cat] = counts.get(cat, 0) + 1
    return "\n".join(f"  {cat}: {count}" for cat, count in sorted(counts.items()))
