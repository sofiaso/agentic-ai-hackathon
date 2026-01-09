"""Pydantic v2 data contracts - source of truth for all data structures."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class GapCategory(str, Enum):
    """Gap categories for security and compliance."""

    ENCRYPTION = "encryption"
    LOGGING = "logging"
    IAM = "iam"
    NETWORK = "network"
    BACKUP = "backup"
    OTHER = "other"


class ToolRunResult(BaseModel):
    """Result from running an external tool."""

    tool_name: str = Field(..., description="Name of the tool (terraform, tfsec, checkov)")
    exit_code: int = Field(..., description="Exit code from tool execution")
    stdout: str = Field(default="", description="Standard output")
    stderr: str = Field(default="", description="Standard error")
    version: str | None = Field(default=None, description="Tool version if available")
    duration_seconds: float = Field(default=0.0, description="Execution duration")
    success: bool = Field(..., description="Whether execution was successful")

    @field_validator("stdout", "stderr", mode="before")
    @classmethod
    def truncate_output(cls, v: str) -> str:
        """Truncate output to prevent huge payloads."""
        if isinstance(v, str) and len(v) > 10000:
            return v[:10000] + "\n... (truncated)"
        return v


class Finding(BaseModel):
    """Normalized finding from any tool."""

    id: str = Field(..., description="Unique finding ID (deterministic)")
    tool: str = Field(..., description="Source tool name")
    rule_id: str | None = Field(default=None, description="Rule ID from tool")
    severity: str = Field(..., description="Severity level (HIGH, MEDIUM, LOW, INFO)")
    title: str = Field(..., description="Finding title")
    description: str = Field(default="", description="Finding description")
    file_path: str | None = Field(default=None, description="File path where finding occurs")
    line_number: int | None = Field(default=None, description="Line number if available")
    resource: str | None = Field(default=None, description="Resource identifier")
    raw_payload: dict[str, Any] = Field(
        default_factory=dict, description="Original tool output (trimmed)"
    )

    @field_validator("raw_payload", mode="before")
    @classmethod
    def trim_payload(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Trim raw payload to avoid huge outputs."""
        if not isinstance(v, dict):
            return {}
        # Limit nested structures
        trimmed: dict[str, Any] = {}
        for key, value in list(v.items())[:20]:  # Limit to 20 keys
            if isinstance(value, str) and len(value) > 500:
                trimmed[key] = value[:500] + "... (truncated)"
            elif isinstance(value, (dict, list)) and len(str(value)) > 1000:
                trimmed[key] = str(value)[:1000] + "... (truncated)"
            else:
                trimmed[key] = value
        return trimmed


class Gap(BaseModel):
    """Security/compliance gap identified from findings."""

    gap_id: str = Field(..., description="Deterministic gap ID (no timestamps/randomness)")
    category: GapCategory = Field(..., description="Gap category")
    title: str = Field(..., description="Gap title")
    description: str = Field(default="", description="Gap description")
    findings: list[str] = Field(
        default_factory=list, description="Finding IDs contributing to this gap"
    )
    severity: str = Field(..., description="Aggregated severity (HIGH, MEDIUM, LOW)")
    fedramp_families: list[str] = Field(
        default_factory=list, description="FedRAMP control families (AU/AC/SC/CM/SI)"
    )
    remediation_checklist: list[str] = Field(
        default_factory=list, description="Remediation steps (from LLM if enabled)"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score (0-1)")
    requires_human_decision: bool = Field(
        default=False, description="Whether human review is required"
    )


class ScanPlanOption(str, Enum):
    """Options for scan plan."""

    TERRAFORM_VALIDATE = "terraform_validate"
    TFSEC = "tfsec"
    CHECKOV = "checkov"
    ALL = "all"


class ScanPlan(BaseModel):
    """Plan for what tools to run (from LLM router if enabled)."""

    options: list[ScanPlanOption] = Field(default_factory=list, description="Selected scan options")
    reasoning: str = Field(default="", description="Reasoning for plan selection")


class Report(BaseModel):
    """Final assessment report."""

    scan_id: str = Field(..., description="Unique scan identifier")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Report generation time"
    )
    target: str = Field(..., description="Target repo URL or local path")
    human_request: str | None = Field(default=None, description="Human request/query")
    findings: list[Finding] = Field(default_factory=list, description="All findings")
    gaps: list[Gap] = Field(default_factory=list, description="Identified gaps")
    scan_plan: ScanPlan | None = Field(default=None, description="Scan plan used")
    tool_results: list[ToolRunResult] = Field(
        default_factory=list, description="Tool execution results"
    )
    summary: str = Field(default="", description="Executive summary (from LLM if enabled)")


class RunMetrics(BaseModel):
    """Metrics for the pipeline run."""

    scan_id: str = Field(..., description="Scan identifier")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Metrics collection time"
    )
    total_findings: int = Field(default=0, description="Total findings count")
    findings_by_tool: dict[str, int] = Field(
        default_factory=dict, description="Findings count per tool"
    )
    findings_by_severity: dict[str, int] = Field(
        default_factory=dict, description="Findings count per severity"
    )
    total_gaps: int = Field(default=0, description="Total gaps count")
    gaps_by_category: dict[str, int] = Field(
        default_factory=dict, description="Gaps count per category"
    )
    tool_execution_times: dict[str, float] = Field(
        default_factory=dict, description="Tool execution times in seconds"
    )
    llm_enabled: bool = Field(default=False, description="Whether LLM enrichment was used")
    llm_model_id: str | None = Field(default=None, description="LLM model ID used")
    llm_region: str | None = Field(default=None, description="AWS region for LLM calls")
    llm_calls: int = Field(default=0, description="Number of LLM calls made")
    llm_failures: int = Field(default=0, description="Number of LLM call failures")
    llm_total_latency_seconds: float = Field(
        default=0.0, description="Total LLM call latency in seconds"
    )
    llm_total_input_tokens: int | None = Field(
        default=None, description="Total input tokens (if available)"
    )
    llm_total_output_tokens: int | None = Field(
        default=None, description="Total output tokens (if available)"
    )
    llm_token_usage_note: str | None = Field(
        default=None, description="Note about token usage availability"
    )
    pipeline_duration_seconds: float = Field(default=0.0, description="Total pipeline duration")