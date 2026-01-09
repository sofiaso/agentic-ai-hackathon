"""Build security/compliance gaps from findings."""

import hashlib
from collections import defaultdict

from iac_agent.models.contracts import Finding, Gap, GapCategory


def build_gaps(findings: list[Finding]) -> list[Gap]:
    """
    Build gaps from findings, grouping by category and severity.

    Args:
        findings: List of findings to analyze

    Returns:
        List of gaps
    """
    if not findings:
        return []

    # Group findings by category
    findings_by_category: dict[GapCategory, list[Finding]] = defaultdict(list)

    for finding in findings:
        category = _categorize_finding(finding)
        findings_by_category[category].append(finding)

    gaps: list[Gap] = []

    for category, category_findings in findings_by_category.items():
        # Further group by severity and rule pattern
        grouped = _group_findings(category_findings)

        for group in grouped:
            gap_id = _generate_gap_id(category, group)
            severity = _aggregate_severity(group)

            gaps.append(
                Gap(
                    gap_id=gap_id,
                    category=category,
                    title=_generate_gap_title(category, group),
                    description=_generate_gap_description(group),
                    findings=[f.id for f in group],
                    severity=severity,
                    fedramp_families=[],  # Will be populated by LLM if enabled
                    remediation_checklist=[],  # Will be populated by LLM if enabled
                    confidence=0.0,  # Will be populated by LLM if enabled
                    requires_human_decision=False,  # Will be populated by LLM if enabled
                )
            )

    return gaps


def _categorize_finding(finding: Finding) -> GapCategory:
    """Categorize a finding into a gap category."""
    title_lower = finding.title.lower()
    description_lower = finding.description.lower()
    rule_lower = (finding.rule_id or "").lower()

    # Encryption
    if any(
        keyword in title_lower + description_lower + rule_lower
        for keyword in [
            "encrypt",
            "kms",
            "ssl",
            "tls",
            "certificate",
            "key",
            "secret",
        ]
    ):
        return GapCategory.ENCRYPTION

    # Logging
    if any(
        keyword in title_lower + description_lower + rule_lower
        for keyword in ["log", "audit", "monitor", "cloudwatch", "cloudtrail"]
    ):
        return GapCategory.LOGGING

    # IAM
    if any(
        keyword in title_lower + description_lower + rule_lower
        for keyword in [
            "iam",
            "policy",
            "permission",
            "role",
            "access",
            "principal",
            "assume",
        ]
    ):
        return GapCategory.IAM

    # Network
    if any(
        keyword in title_lower + description_lower + rule_lower
        for keyword in [
            "network",
            "security group",
            "nacl",
            "vpc",
            "subnet",
            "port",
            "ingress",
            "egress",
        ]
    ):
        return GapCategory.NETWORK

    # Backup
    if any(
        keyword in title_lower + description_lower + rule_lower
        for keyword in ["backup", "snapshot", "retention", "recovery"]
    ):
        return GapCategory.BACKUP

    return GapCategory.OTHER


def _group_findings(findings: list[Finding]) -> list[list[Finding]]:
    """Group findings by similar rule patterns."""
    groups: list[list[Finding]] = []
    used: set[str] = set()

    for finding in findings:
        if finding.id in used:
            continue

        # Find similar findings (same rule_id or similar title)
        group = [finding]
        used.add(finding.id)

        for other in findings:
            if other.id in used:
                continue

            if (
                finding.rule_id and other.rule_id and finding.rule_id == other.rule_id
            ) or _similar_titles(finding.title, other.title):
                group.append(other)
                used.add(other.id)

        groups.append(group)

    return groups


def _similar_titles(title1: str, title2: str) -> bool:
    """Check if two titles are similar (simple heuristic)."""
    words1 = set(title1.lower().split())
    words2 = set(title2.lower().split())
    if not words1 or not words2:
        return False
    # If more than 50% words overlap, consider similar
    overlap = len(words1 & words2) / max(len(words1), len(words2))
    return overlap > 0.5


def _aggregate_severity(findings: list[Finding]) -> str:
    """Aggregate severity from a group of findings."""
    severity_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
    max_severity = max(
        (severity_order.get(f.severity.upper(), 0) for f in findings),
        default=0,
    )
    for sev, val in severity_order.items():
        if val == max_severity:
            return sev
    return "INFO"


def _generate_gap_id(category: GapCategory, findings: list[Finding]) -> str:
    """
    Generate deterministic gap ID (no timestamps/randomness).

    Args:
        category: Gap category
        findings: Findings in this gap

    Returns:
        Deterministic gap ID
    """
    # Use hash of category and finding IDs (sorted for determinism)
    finding_ids = sorted([f.id for f in findings])
    content = f"{category.value}:{':'.join(finding_ids)}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _generate_gap_title(category: GapCategory, findings: list[Finding]) -> str:
    """Generate a title for a gap."""
    if not findings:
        return f"{category.value.title()} Gap"

    # Use the most common rule_id or title pattern
    rule_ids = [f.rule_id for f in findings if f.rule_id]
    if rule_ids:
        most_common = max(set(rule_ids), key=rule_ids.count)
        return f"{category.value.title()}: {most_common}"

    titles = [f.title for f in findings]
    if titles:
        # Use first title as base
        base_title = titles[0]
        if len(findings) > 1:
            return f"{base_title} ({len(findings)} instances)"
        return base_title

    return f"{category.value.title()} Gap"


def _generate_gap_description(findings: list[Finding]) -> str:
    """Generate a description for a gap."""
    if not findings:
        return ""

    descriptions = [f.description for f in findings if f.description]
    if descriptions:
        # Use first non-empty description
        return descriptions[0]

    # Fallback to titles
    titles = [f.title for f in findings if f.title]
    if titles:
        return "; ".join(titles[:3])  # Limit to first 3

    return ""
