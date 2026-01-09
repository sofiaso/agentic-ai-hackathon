"""Load prompt templates from prompts/ directory."""

from pathlib import Path


def get_prompts_dir() -> Path:
    """Get the prompts directory path."""
    # Look for prompts/ in project root
    current = Path(__file__).parent
    project_root = current.parent.parent.parent
    prompts_dir = project_root / "prompts"
    return prompts_dir


def load_prompt(name: str) -> str:
    """
    Load a prompt template from prompts/ directory.

    Args:
        name: Prompt file name (e.g., "router.md")

    Returns:
        Prompt template content
    """
    prompts_dir = get_prompts_dir()
    prompt_file = prompts_dir / name

    if not prompt_file.exists():
        # Return default prompt if file doesn't exist
        return _get_default_prompt(name)

    return prompt_file.read_text(encoding="utf-8")


def _get_default_prompt(name: str) -> str:
    """Get default prompt if file doesn't exist."""
    defaults = {
        "router.md": """You are a security scanning router. Analyze the human request and repository context to determine which tools should run.

Available options:
- terraform_validate: Run terraform validate
- tfsec: Run tfsec security scanner
- checkov: Run checkov security scanner
- all: Run all tools

Output JSON only with this schema:
{
  "options": ["tfsec", "checkov"],
  "reasoning": "Brief explanation"
}""",
        "fedramp_mapper.md": """You are a FedRAMP compliance mapper. Map the security gap to FedRAMP control families (AU/AC/SC/CM/SI) and assign priority.

Output JSON only with this schema:
{
  "families": ["AU", "AC"],
  "priority": 3,
  "justification": "Brief explanation"
}""",
        "remediation_advisor.md": """You are a remediation advisor. Generate a remediation checklist for the security gap.

Output JSON only with this schema:
{
  "checklist": [
    {
      "step": "Action description",
      "confidence": 0.8,
      "requires_human_decision": false
    }
  ],
  "overall_confidence": 0.8,
  "requires_human_decision": false
}""",
        "summary_writer.md": """You are a report writer. Generate an executive summary for the security assessment.

Output plain text summary (not JSON).""",
    }

    return defaults.get(name, f"Default prompt for {name}")
