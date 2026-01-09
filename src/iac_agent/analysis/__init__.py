"""Analysis modules for processing findings and building gaps."""

from iac_agent.analysis.dedup import deduplicate_findings
from iac_agent.analysis.gap_builder import build_gaps
from iac_agent.analysis.normalize import normalize_findings
from iac_agent.analysis.scoring import calculate_severity_score

__all__ = [
    "deduplicate_findings",
    "build_gaps",
    "normalize_findings",
    "calculate_severity_score",
]
