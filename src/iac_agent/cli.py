"""CLI entry point for iac-agent."""

import logging
import os
import time
import traceback
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

# Configure logging for console output
# Set level to INFO to avoid DEBUG noise, but show WARNING and ERROR
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
# Suppress noisy boto3/botocore logs
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Create logger for this module
logger = logging.getLogger(__name__)

from iac_agent.metrics.collector import collect_metrics
from iac_agent.pipeline.runner import run_pipeline
from iac_agent.reporting.export import export_report

# Load .env.local if it exists (silently - don't fail if missing)
# .env.local is in the project root, relative to this file: src/iac_agent/cli.py -> project root
project_root = Path(__file__).parent.parent.parent
env_local_path = project_root / ".env.local"
if env_local_path.exists():
    load_dotenv(env_local_path, override=True)
    # Log what was loaded (without sensitive values)
    if os.getenv("BEDROCK_MODEL_ID"):
        logger.info(f"Loaded BEDROCK_MODEL_ID from .env.local: {os.getenv('BEDROCK_MODEL_ID')}")
    if os.getenv("AWS_REGION"):
        logger.info(f"Loaded AWS_REGION from .env.local: {os.getenv('AWS_REGION')}")
else:
    logger.debug(f".env.local not found at {env_local_path}")

app = typer.Typer(help="IaC Agent - CLI-first Agentic IaC assessment pipeline")


@app.command()
def scan(
    repo_url: Annotated[
        str | None,
        typer.Option("--repo-url", "-r", help="Git repository URL to scan"),
    ] = None,
    local_path: Annotated[
        str | None,
        typer.Option("--local-path", "-p", help="Local directory path to scan"),
    ] = None,
    request: Annotated[
        str | None,
        typer.Option("--request", "-q", help="Human request/query for the scan"),
    ] = None,
    execute_tools: Annotated[
        bool,
        typer.Option(
            "--execute-tools",
            help="Execute tools (terraform/tfsec/checkov). Default: dry-run",
        ),
    ] = False,
    llm_enable: Annotated[
        bool,
        typer.Option(
            "--llm-enable",
            help="Enable LLM enrichment (requires AWS Bedrock). Default: disabled",
        ),
    ] = False,
    allow_network: Annotated[
        bool,
        typer.Option(
            "--allow-network",
            help="Allow network operations (e.g., git clone). Default: disabled",
        ),
    ] = False,
    output_dir: Annotated[
        str,
        typer.Option("--output-dir", "-o", help="Output directory", show_default=True),
    ] = "out",
    run_dir: Annotated[
        str,
        typer.Option("--run-dir", help="Base directory for run artifacts", show_default=True),
    ] = "out/runs",
    export_findings_raw: Annotated[
        bool,
        typer.Option(
            "--export-findings-raw",
            help="Export raw findings JSON",
        ),
    ] = False,
    export_gaps: Annotated[
        bool,
        typer.Option(
            "--export-gaps",
            help="Export gaps JSON",
        ),
    ] = False,
    llm_region: Annotated[
        str | None,
        typer.Option(
            "--llm-region",
            help="AWS region for LLM calls (defaults to env AWS_REGION/AWS_DEFAULT_REGION or eu-north-1)",
        ),
    ] = None,
    model_id: Annotated[
        str | None,
        typer.Option(
            "--model-id",
            help="Bedrock model ID (defaults to env BEDROCK_MODEL_ID or eu.amazon.nova-2-lite-v1:0)",
        ),
    ] = None,
    llm_tool_router: Annotated[
        bool | None,
        typer.Option(
            "--llm-tool-router",
            "--tool-routing",
            help="Enable LLM-based tool routing (defaults to True when --llm-enable, otherwise False)",
        ),
    ] = None,
    general_tool: Annotated[
        str,
        typer.Option(
            "--general-tool",
            help="General fallback tool ID (default: checkov)",
            show_default=True,
        ),
    ] = "checkov",
) -> None:
    """
    Run IaC security assessment pipeline.

    By default, runs in DRY-RUN mode:
    - No tool execution
    - No network operations
    - No LLM calls

    Use flags to enable features:
    - --execute-tools: Run terraform/tfsec/checkov
    - --llm-enable: Enable AWS Bedrock LLM enrichment
    - --allow-network: Allow git clone operations
    """
    if not repo_url and not local_path:
        typer.echo("Error: Must specify either --repo-url or --local-path", err=True)
        raise typer.Exit(1)

    # Get model_id and region from .env.local if not provided via CLI
    # Read from environment (already loaded from .env.local if exists)
    env_model_id = os.getenv("BEDROCK_MODEL_ID")
    final_model_id = model_id or env_model_id or "eu.amazon.nova-2-lite-v1:0"
    
    # Log which source was used
    if model_id:
        logger.info(f"Using model_id from CLI parameter: {model_id}")
    elif env_model_id:
        logger.info(f"Using BEDROCK_MODEL_ID from .env.local: {env_model_id}")
    else:
        logger.info(f"Using default model_id: eu.amazon.nova-2-lite-v1:0")
    
    final_llm_region = (
        llm_region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "eu-north-1")
    )

    typer.echo("Running IaC assessment pipeline...")
    typer.echo(f"  Mode: {'EXECUTE' if execute_tools else 'DRY-RUN'}")
    typer.echo(f"  LLM: {'ENABLED' if llm_enable else 'DISABLED'}")
    if llm_enable:
        typer.echo(f"  Model: {final_model_id}")
        typer.echo(f"  Region: {final_llm_region}")
        
        # Show tool routing status
        use_tool_router = llm_tool_router if llm_tool_router is not None else llm_enable
        typer.echo(f"  Tool Router: {'ENABLED' if use_tool_router else 'DISABLED'}")
    typer.echo(f"  Network: {'ALLOWED' if allow_network else 'BLOCKED'}")
    typer.echo("")

    execution_errors: list[str] = []

    try:

        report, metrics, run_path = run_pipeline(
            repo_url=repo_url,
            local_path=local_path,
            human_request=request,
            execute_tools=execute_tools,
            llm_enable=llm_enable,
            allow_network=allow_network,
            run_dir_base=run_dir,
            llm_model_id=final_model_id if llm_enable else None,
            llm_region=final_llm_region if llm_enable else None,
            llm_tool_router=llm_tool_router,
            general_tool=general_tool,
        )

        # Get inventory data if run_path exists
        inventory_data = None
        if execute_tools and run_path:
            try:
                import json

                inventory_file = run_path / "inventory.json"
                if inventory_file.exists():
                    inventory_data = json.loads(inventory_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Export artifacts
        export_report(
            report,
            metrics,
            output_dir=output_dir,
            export_findings_raw=export_findings_raw,
            export_gaps=export_gaps,
            execution_errors=execution_errors if execution_errors else None,
            run_path=run_path,
            inventory_data=inventory_data,
        )

        typer.echo("Pipeline completed successfully!")
        typer.echo(f"  Findings: {len(report.findings)}")
        typer.echo(f"  Gaps: {len(report.gaps)}")
        
        # Show tool routing info if available
        if report.scan_plan and report.scan_plan.reasoning and "Tool router:" in report.scan_plan.reasoning:
            typer.echo("")
            typer.echo("Tool Selection:")
            reasoning = report.scan_plan.reasoning
            parts = reasoning.split(" | ")
            for part in parts:
                if part.startswith("Tool router:"):
                    typer.echo(f"  Rationale: {part.replace('Tool router: ', '')}")
                elif part.startswith("Intent:"):
                    typer.echo(f"  User Intent: {part.replace('Intent: ', '')}")
                elif part.startswith("Fallback used:"):
                    fallback_used = part.replace("Fallback used: ", "").lower() == "true"
                    typer.echo(f"  Fallback Used: {fallback_used}")
        
        typer.echo(f"  Output: {output_dir}/")
        typer.echo("    - report.md")
        typer.echo("    - report.json")
        typer.echo("    - metrics.json")
        typer.echo("    - execution.log")
        if export_findings_raw:
            typer.echo("    - findings_raw.json")
        if export_gaps:
            typer.echo("    - gaps.json")

        # Show run directory if tools were executed
        if execute_tools and run_path:
            typer.echo("")
            typer.echo(f"Run Artifacts: {run_path}")
            typer.echo("  - manifest.json")
            typer.echo("  - inventory.json")
            typer.echo("  - terraform/")
            typer.echo("  - tfsec/")
            typer.echo("  - checkov/")

        # Show tool execution summary
        if report.tool_results:
            typer.echo("")
            typer.echo("Tool Execution Summary:")
            for result in report.tool_results:
                status = "SUCCESS" if result.success else "FAILED"
                typer.echo(
                    f"  - {result.tool_name}: {status} (exit code: {result.exit_code}, duration: {result.duration_seconds:.2f}s)"
                )
                if result.version:
                    typer.echo(f"    Version: {result.version}")

    except Exception as e:
        error_traceback = traceback.format_exc()
        execution_errors.append(error_traceback)

        # Try to export partial report if possible
        try:
            # Create minimal report with error
            from iac_agent.models.contracts import Report

            error_report = Report(
                scan_id="error",
                target=repo_url or local_path or "unknown",
                human_request=request,
            )
            error_metrics = collect_metrics(
                error_report,
                time.time(),
                False,
                0,
                0,
                llm_model_id=None,
                llm_region=None,
                llm_total_latency=0.0,
                llm_total_input_tokens=None,
                llm_total_output_tokens=None,
            )

            export_report(
                error_report,
                error_metrics,
                output_dir=output_dir,
                execution_errors=execution_errors,
            )

            typer.echo(f"ERROR: Pipeline failed: {str(e)}", err=True)
            typer.echo(f"Traceback saved to {output_dir}/execution.log", err=True)
        except Exception:
            pass

        typer.echo(f"ERROR: Pipeline failed: {str(e)}", err=True)
        typer.echo(f"Traceback:\n{error_traceback}", err=True)
        raise typer.Exit(1)


def main() -> None:
    """Main entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
