"""Deduplicate findings using deterministic keys."""

from iac_agent.models.contracts import Finding


def deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    """
    Deduplicate findings using deterministic keys.

    Args:
        findings: List of findings to deduplicate

    Returns:
        Deduplicated list of findings
    """
    seen: dict[str, Finding] = {}

    for finding in findings:
        # Use finding.id as the deduplication key (already deterministic)
        if finding.id not in seen:
            seen[finding.id] = finding
        else:
            # If duplicate, merge information if needed
            existing = seen[finding.id]
            # Keep the one with more information
            if len(finding.description) > len(existing.description):
                seen[finding.id] = finding

    return list(seen.values())
