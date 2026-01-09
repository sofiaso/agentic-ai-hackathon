"""Tool catalog for LLM-based tool selection."""

from dataclasses import dataclass
from typing import Literal

ToolId = Literal["terraform_validate", "tfsec", "checkov"]


@dataclass
class ToolDescriptor:
    """Descriptor for a scanning tool."""

    tool_id: ToolId
    display_name: str
    short_description: str
    detailed_description: str
    strengths: list[str]
    limitations: list[str]
    best_for: list[str]
    keywords: list[str]
    is_general_fallback: bool


def get_tool_catalog() -> list[ToolDescriptor]:
    """
    Get the complete tool catalog.

    Returns:
        List of tool descriptors
    """
    return [
        ToolDescriptor(
            tool_id="terraform_validate",
            display_name="Terraform Validate",
            short_description="Validates Terraform configuration syntax and structure.",
            detailed_description=(
                "Terraform Validate is a built-in Terraform command that parses and validates "
                "configuration files for correct syntax, validates variable references, checks "
                "module and provider configurations, and ensures resource attribute consistency. "
                "It catches syntax errors, missing required arguments, type mismatches, and "
                "configuration structure issues before attempting to create or modify infrastructure. "
                "This tool requires 'terraform init' to be run first when modules or providers are used. "
                "It focuses purely on configuration correctness and does not perform security scanning "
                "or compliance checking. Use Terraform validator in case 'Terraform' is mentioned in the request."
            ),
            strengths=[
                "Fast execution - typically completes in seconds",
                "Built-in to Terraform - no additional installation needed",
                "Catches syntax and structural errors early",
                "Validates variable references and types",
                "Checks module and provider configurations",
                "No external dependencies or network access required"
            ],
            limitations=[
                "Does not perform security scanning",
                "Does not check compliance or best practices",
                "Requires terraform init when using modules/providers",
                "Cannot detect misconfigurations or policy violations",
                "Limited to Terraform configuration validation only"
            ],
            best_for=[
                "Checking Terraform configuration syntax and structure",
                "Validating configuration before applying changes",
                "Detecting missing required arguments or type errors",
                "Verifying module and provider configurations",
                "CI/CD pipelines requiring fast validation checks",
                "User requests mentioning 'syntax', 'validate', 'parse', 'configuration errors'"
            ],
            keywords=[
                "syntax",
                "validation",
                "validate",
                "parse",
                "structure",
                "configuration errors",
                "syntax errors",
                "terraform init",
                "module validation",
                "provider validation",
                "type checking",
                "missing arguments"
            ],
            is_general_fallback=False,
        ),
        ToolDescriptor(
            tool_id="tfsec",
            display_name="Tfsec",
            short_description="Security-focused Terraform static analysis scanner.",
            detailed_description=(
                "Tfsec is a specialized security scanner designed specifically for Terraform configurations. "
                "It analyzes Terraform code to identify security misconfigurations, vulnerabilities, and "
                "security best practice violations. Tfsec uses a comprehensive rule set covering AWS, Azure, "
                "GCP, and other cloud providers, focusing on common security issues such as overly permissive "
                "IAM policies, exposed resources, missing encryption, insecure default configurations, and "
                "network security misconfigurations. It is fast, easy to integrate, and provides actionable "
                "security findings with remediation guidance. Tfsec excels at finding security-specific issues "
                "that configuration validation tools miss."
            ),
            strengths=[
                "Specialized for security scanning - comprehensive security rule set",
                "Fast execution with focused security checks",
                "Excellent at finding IAM policy issues and public exposure",
                "Identifies encryption and access control misconfigurations",
                "Provides detailed security findings with remediation steps",
                "Lightweight and easy to install",
                "Covers multiple cloud providers (AWS, Azure, GCP)"
            ],
            limitations=[
                "Security-focused only - does not check general compliance frameworks",
                "Does not validate Terraform syntax (use terraform validate for that)",
                "Limited to security rules - not comprehensive policy scanning",
                "May miss some compliance-specific requirements (CIS, FedRAMP, etc.)",
                "Focused on Terraform - may not cover all IaC patterns"
            ],
            best_for=[
                "Finding security misconfigurations and vulnerabilities",
                "Identifying overly permissive IAM policies",
                "Detecting public exposure and network security issues",
                "Checking encryption and access control settings",
                "Security-focused assessments and security reviews",
                "User requests mentioning 'security', 'IAM', 'permissions', 'public', 'encryption', 'exposure', 'vulnerabilities'"
            ],
            keywords=[
                "security",
                "vulnerability",
                "vulnerabilities",
                "IAM",
                "permissions",
                "policy",
                "policies",
                "public",
                "exposure",
                "encryption",
                "access control",
                "misconfiguration",
                "security misconfiguration",
                "overly permissive",
                "publicly exposed",
                "network security",
                "AWS security",
                "Azure security",
                "GCP security"
            ],
            is_general_fallback=False,
        ),
        ToolDescriptor(
            tool_id="checkov",
            display_name="Checkov",
            short_description="Comprehensive IaC policy and compliance scanner.",
            detailed_description=(
                "Checkov is a comprehensive infrastructure-as-code (IaC) static analysis tool that scans "
                "for security and compliance misconfigurations across multiple frameworks and cloud providers. "
                "It supports extensive policy frameworks including CIS benchmarks, AWS Foundational Security "
                "Best Practices, PCI-DSS, HIPAA, SOC 2, and custom policies. Checkov performs deep policy "
                "analysis, compliance checking, and best practice validation across Terraform, CloudFormation, "
                "Kubernetes, Docker, and other IaC formats. It provides detailed findings with policy references, "
                "severity ratings, and remediation guidance. Checkov is the most comprehensive and general-purpose "
                "scanner, suitable for broad compliance assessments and multi-framework policy checking."
            ),
            strengths=[
                "Comprehensive policy scanning - supports multiple compliance frameworks",
                "Broad coverage - CIS, AWS Security Best Practices, PCI-DSS, HIPAA, SOC 2, and more",
                "Deep policy analysis with detailed findings and references",
                "Multi-framework support - works across multiple IaC formats",
                "Excellent for compliance assessments and regulatory requirements",
                "General-purpose scanner suitable for broad security and compliance reviews",
                "Detailed output with policy references and remediation guidance",
                "Best tool when user intent is unclear or broad"
            ],
            limitations=[
                "Slower execution compared to specialized tools",
                "May produce more findings than needed for focused security reviews",
                "Requires more system resources",
                "Installation may be more complex than other tools",
                "Output can be verbose for large codebases"
            ],
            best_for=[
                "Comprehensive compliance assessments",
                "Multi-framework policy checking (CIS, FedRAMP, PCI-DSS, etc.)",
                "Regulatory compliance reviews (HIPAA, SOC 2, etc.)",
                "Broad security and best practice validation",
                "General-purpose IaC scanning when user intent is unclear",
                "Finding policy violations and compliance gaps",
                "User requests mentioning 'compliance', 'CIS', 'FedRAMP', 'policy', 'best practices', 'regulatory', "
                "or when user intent is broad/unclear",
                "FALLBACK: Use when no other tool matches or user request is ambiguous"
            ],
            keywords=[
                "compliance",
                "CIS",
                "FedRAMP",
                "PCI-DSS",
                "HIPAA",
                "SOC 2",
                "policy",
                "policies",
                "framework",
                "regulatory",
                "best practices",
                "benchmark",
                "standards",
                "audit",
                "assessment",
                "comprehensive",
                "general",
                "all",
                "everything",
                "scan"
            ],
            is_general_fallback=True,
        ),
    ]


def get_fallback_tool() -> ToolId:
    """
    Get the fallback tool ID when no tool matches.

    Returns:
        Fallback tool ID (always "tfsec")
    """
    return "tfsec"


def get_tool_by_id(tool_id: str) -> ToolDescriptor | None:
    """
    Get a tool descriptor by tool ID.

    Args:
        tool_id: Tool identifier

    Returns:
        Tool descriptor or None if not found
    """
    catalog = get_tool_catalog()
    for tool in catalog:
        if tool.tool_id == tool_id:
            return tool
    return None
