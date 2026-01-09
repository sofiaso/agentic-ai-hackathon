"""Resolve scan paths from repository root."""

from pathlib import Path


def resolve_scan_paths(repo_path: str) -> list[str]:
    """
    Resolve scan paths from repository root.

    Default paths: "." and "examples/" (only if exists).

    Args:
        repo_path: Repository root path

    Returns:
        List of paths to scan
    """
    repo = Path(repo_path)
    paths: list[str] = []

    # Always include root
    if repo.exists():
        paths.append(str(repo))

    # Include examples/ if it exists
    examples_path = repo / "examples"
    if examples_path.exists() and examples_path.is_dir():
        paths.append(str(examples_path))

    return paths
