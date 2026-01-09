"""Scoring utilities for findings and gaps."""

from iac_agent.models.contracts import Finding, Gap


def calculate_severity_score(severity: str) -> float:
    """
    Calculate numeric score for severity level.

    Args:
        severity: Severity level (HIGH, MEDIUM, LOW, INFO)

    Returns:
        Score between 0.0 and 1.0
    """
    severity_upper = severity.upper()
    if severity_upper == "HIGH":
        return 1.0
    if severity_upper == "MEDIUM":
        return 0.6
    if severity_upper == "LOW":
        return 0.3
    return 0.1


def calculate_finding_priority(finding: Finding) -> float:
    """
    Calculate priority score for a finding.

    Args:
        finding: Finding to score

    Returns:
        Priority score (higher = more important)
    """
    base_score = calculate_severity_score(finding.severity)

    # Boost if it's in a critical resource
    if finding.resource and any(
        keyword in finding.resource.lower() for keyword in ["database", "storage", "network", "iam"]
    ):
        base_score *= 1.2

    return min(base_score, 1.0)


def calculate_gap_priority(gap: Gap) -> float:
    """
    Calculate priority score for a gap.

    Args:
        gap: Gap to score

    Returns:
        Priority score (higher = more important)
    """
    base_score = calculate_severity_score(gap.severity)

    # Boost based on number of findings
    finding_multiplier = 1.0 + (len(gap.findings) * 0.1)
    base_score *= min(finding_multiplier, 1.5)

    # Boost based on confidence if available
    if gap.confidence > 0:
        base_score *= (1.0 + gap.confidence) / 2.0

    return min(base_score, 1.0)
