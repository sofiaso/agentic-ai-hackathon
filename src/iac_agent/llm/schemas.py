"""Pydantic schemas for LLM JSON outputs."""

from pydantic import BaseModel, Field


class RouterOutput(BaseModel):
    """Output schema for router prompt (legacy - used by old router)."""

    options: list[str] = Field(
        ..., description="Selected scan options (terraform_validate, tfsec, checkov, all)"
    )
    reasoning: str = Field(..., description="Reasoning for selection")


class ToolRouterOutput(BaseModel):
    """Output schema for tool router prompt."""

    selected_tools: list[str] = Field(
        ...,
        description=(
            "List of selected tool IDs from: terraform_validate, tfsec, checkov. "
            "Must be non-empty. Use terraform_validate if no tool matches."
        ),
    )
    fallback_used: bool = Field(
        default=False,
        description="True if fallback tool (tfsec) was selected because no other tool matched",
    )
    rationale: str = Field(
        ...,
        description="Brief rationale (1-2 sentences) explaining tool selection, citing user intent",
    )
    tool_intent_summary: str = Field(
        ..., description="Short paraphrase of what the user wants to find or check"
    )


class FedRampMapperOutput(BaseModel):
    """Output schema for FedRAMP mapper prompt."""

    families: list[str] = Field(..., description="FedRAMP control families (AU/AC/SC/CM/SI)")
    priority: int = Field(..., ge=1, le=5, description="Priority level 1-5")
    justification: str = Field(..., description="Justification for mapping")


class RemediationItem(BaseModel):
    """Single remediation item."""

    step: str = Field(..., description="Remediation step description")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    requires_human_decision: bool = Field(
        default=False, description="Whether human review is required"
    )


class RemediationAdvisorOutput(BaseModel):
    """Output schema for remediation advisor prompt."""

    checklist: list[RemediationItem] = Field(..., description="Remediation checklist")
    overall_confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence")
    requires_human_decision: bool = Field(
        default=False, description="Whether human review is required"
    )