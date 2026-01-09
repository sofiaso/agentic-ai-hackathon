"""Build inventory of Terraform files before tool execution."""

from collections import Counter
from pathlib import Path
from typing import Any


def build_inventory(scan_paths: list[str], repo_path: str) -> dict[str, Any]:
    """
    Build inventory of Terraform files in scan paths.

    Args:
        scan_paths: List of paths to scan
        repo_path: Root repository path

    Returns:
        Dictionary with inventory data
    """
    repo_root = Path(repo_path).resolve()
    terraform_extensions = {".tf", ".tfvars", ".tf.json"}
    all_tf_files: list[str] = []
    file_counts_by_dir: Counter[str] = Counter()

    for scan_path in scan_paths:
        scan_abs = (repo_root / scan_path).resolve() if scan_path != "." else repo_root

        if not scan_abs.exists():
            continue

        # Find all terraform files
        if scan_abs.is_file():
            if scan_abs.suffix in terraform_extensions:
                rel_path = str(scan_abs.relative_to(repo_root))
                all_tf_files.append(rel_path)
                file_counts_by_dir[str(scan_abs.parent.relative_to(repo_root))] += 1
        else:
            # Recursive search
            for tf_file in scan_abs.rglob("*"):
                if tf_file.is_file() and tf_file.suffix in terraform_extensions:
                    rel_path = str(tf_file.relative_to(repo_root))
                    all_tf_files.append(rel_path)
                    dir_path = str(tf_file.parent.relative_to(repo_root))
                    file_counts_by_dir[dir_path] += 1

    # Get top 20 directories by count
    top_dirs = dict(file_counts_by_dir.most_common(20))

    # Sample first 100 files
    sample_files = sorted(set(all_tf_files))[:100]

    return {
        "scan_paths_resolved": scan_paths,
        "total_tf_files": len(all_tf_files),
        "sample_tf_files": sample_files,
        "file_counts_by_dir": top_dirs,
    }


def get_repo_ref(repo_path: str) -> dict[str, Any]:
    """
    Get repository reference/commit if available.

    Args:
        repo_path: Repository path

    Returns:
        Dictionary with repo_ref info
    """
    repo_info: dict[str, Any] = {"repo_ref": None, "commit": None}

    try:
        import subprocess

        repo_root = Path(repo_path).resolve()
        if not (repo_root / ".git").exists():
            return repo_info

        # Try to get current commit
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=str(repo_root),
            )
            if result.returncode == 0:
                repo_info["commit"] = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        # Try to get branch/tag
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=str(repo_root),
            )
            if result.returncode == 0:
                repo_info["repo_ref"] = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

    except Exception:
        pass

    return repo_info
