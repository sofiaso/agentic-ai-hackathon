# IaC Agent

CLI-first Agentic IaC assessment pipeline for security and compliance analysis of Infrastructure as Code.

## Overview

IaC Agent is a Python-based tool that analyzes Terraform and other IaC configurations for security vulnerabilities and compliance gaps. It integrates with multiple security scanners (terraform validate, tfsec, checkov) and optionally uses AWS Bedrock LLM for intelligent enrichment.

## Features

- **Multi-tool Support**: Integrates terraform validate, tfsec, and checkov
- **Intelligent Tool Selection**: LLM-powered tool router automatically selects appropriate scanning tools based on user intent
- **Deterministic Analysis**: No timestamps or randomness in deduplication keys or gap IDs
- **LLM Enrichment**: Optional AWS Bedrock integration for tool routing, FedRAMP mapping, and remediation advice
- **Dry-Run by Default**: Safe by default - no execution or network operations without explicit flags
- **Comprehensive Reporting**: Generates Markdown reports, JSON exports, and metrics

## Installation

### Prerequisites

- Python 3.11 or higher
- External tools (install separately):
  - **terraform**: [Install Terraform](https://www.terraform.io/downloads)
  - **tfsec**: [Install tfsec](https://aquasecurity.github.io/tfsec/latest/getting-started/installation/)
  - **checkov**: [Install Checkov](https://www.checkov.io/2.Basics/Installing%20Checkov.html)

### Install IaC Agent

```bash
# Clone or download the repository
cd iac-agent

# Install in development mode
pip install -e .

# Or install with dev dependencies
pip install -e ".[dev]"
```

## Usage

### Basic Usage (Dry-Run)

By default, IaC Agent runs in **DRY-RUN mode** - no tools are executed, no network operations occur:

```bash
# Scan a local directory (dry-run)
iac-agent scan --local-path /path/to/terraform

# Scan a repository URL (dry-run, won't clone)
iac-agent scan --repo-url https://github.com/terraform-aws-modules/terraform-aws-opensearch
```

### Enable Tool Execution

To actually run security scanners:

```bash
# Execute tools on local path
iac-agent scan --local-path /path/to/terraform --execute-tools

# Execute tools on cloned repository
iac-agent scan \
  --repo-url https://github.com/terraform-aws-modules/terraform-aws-opensearch \
  --allow-network \
  --execute-tools
```

### Enable LLM Enrichment and Tool Routing

To enable AWS Bedrock LLM enrichment (requires AWS credentials configured):

```bash
iac-agent scan \
  --local-path /path/to/terraform \
  --execute-tools \
  --llm-enable \
  --request "Check for FedRAMP compliance gaps"
```

The `--llm-enable` flag automatically enables tool routing by default. The LLM will analyze your request and automatically select the appropriate tools from: `terraform_validate`, `tfsec`, and `checkov`.

### Complete Example

```bash
# Full scan with all features enabled
iac-agent scan \
  --repo-url https://github.com/terraform-aws-modules/terraform-aws-opensearch \
  --request "Comprehensive security assessment for production deployment" \
  --allow-network \
  --execute-tools \
  --llm-enable \
  --output-dir results \
  --export-findings-raw \
  --export-gaps
```

## How Tool Selection Works

When you provide a human request with `--request` and enable LLM (`--llm-enable`), the tool router automatically selects which scanning tools to run based on your intent.

### Tool Selection Examples

**Example 1: Syntax Validation**
```bash
iac-agent scan \
  --local-path ./terraform \
  --execute-tools \
  --llm-enable \
  --request "Check for syntax errors and configuration issues"
```
**Expected Selection:** `terraform_validate`  
**Rationale:** User request mentions "syntax errors" and "configuration issues", which matches terraform_validate's strengths.

**Example 2: Security Scanning**
```bash
iac-agent scan \
  --local-path ./terraform \
  --execute-tools \
  --llm-enable \
  --request "Find IAM overly permissive policies and public exposure"
```
**Expected Selection:** `tfsec`  
**Rationale:** User request mentions "IAM policies", "permissive", and "public exposure", which are security concerns best handled by tfsec.

**Example 3: Compliance Assessment**
```bash
iac-agent scan \
  --local-path ./terraform \
  --execute-tools \
  --llm-enable \
  --request "Check for FedRAMP controls gaps and compliance issues"
```
**Expected Selection:** `checkov`  
**Rationale:** User request mentions "FedRAMP", "controls", and "compliance", which are policy/compliance frameworks best handled by checkov.

**Example 4: Broad/Unclear Request**
```bash
iac-agent scan \
  --local-path ./terraform \
  --execute-tools \
  --llm-enable \
  --request "Scan everything"
```
**Expected Selection:** `checkov` (fallback)  
**Rationale:** User request is broad and unclear. The tool router applies deterministic fallback to checkov, the most general-purpose scanner.

**Example 5: Multiple Tools**
```bash
iac-agent scan \
  --local-path ./terraform \
  --execute-tools \
  --llm-enable \
  --request "Validate configuration and check security issues"
```
**Expected Selection:** `terraform_validate`, `tfsec`  
**Rationale:** User request mentions both "validate configuration" (terraform_validate) and "security issues" (tfsec), so both tools are selected.

### Tool Routing Rules

The tool router uses the following rules to select tools:

1. **terraform_validate**: Selected when user mentions:
   - "syntax", "validation", "parse", "configuration errors"
   - "missing arguments", "type errors"
   - "module validation", "provider validation"

2. **tfsec**: Selected when user mentions:
   - "security", "vulnerability", "IAM", "permissions"
   - "public exposure", "encryption", "access control"
   - "security misconfiguration", "overly permissive"

3. **checkov**: Selected when user mentions:
   - "compliance", "CIS", "FedRAMP", "PCI-DSS", "HIPAA", "SOC 2"
   - "policy", "framework", "best practices"
   - "regulatory", "audit", "assessment"
   - Or when request is broad/unclear (fallback)

4. **Fallback Rule**: If selected_tools would be empty or user intent is ambiguous, always use `checkov` with `fallback_used=true`.

### Deterministic Fallback

The tool router ensures deterministic fallback:
- If LLM returns invalid/unknown tool IDs → filtered out, fallback to `checkov`
- If LLM returns empty list → fallback to `checkov`
- If LLM call fails → deterministic fallback to `checkov`
- If no human request provided → deterministic fallback to `checkov`

This ensures the pipeline always has at least one tool to run.

### Tool Catalog

The tool catalog (defined in `src/iac_agent/llm/tool_catalog.py`) contains detailed descriptions for each tool:

- **terraform_validate**: Validates Terraform configuration syntax and structure
- **tfsec**: Security-focused Terraform static analysis scanner
- **checkov**: Comprehensive IaC policy and compliance scanner (general fallback)

Each tool description includes:
- Display name and short description
- Detailed description (5-10 lines)
- Strengths (bullet list)
- Limitations (bullet list)
- Best for (use cases and user intents)
- Keywords (for matching user requests)

### Tool Routing Behavior

- When `--llm-enable` is used with `--request`, tool routing is automatically enabled by default
- The tool router analyzes your request and selects appropriate tools
- If you want to run all tools instead, omit `--request` or use the legacy router behavior
- Tool routing information is included in the report's Scan Plan section and manifest.json

## Command-Line Options

```
Usage: iac-agent scan [OPTIONS]

Options:
  -r, --repo-url TEXT          Git repository URL to scan
  -p, --local-path TEXT        Local directory path to scan
  -q, --request TEXT            Human request/query for the scan
  --execute-tools               Execute tools (terraform/tfsec/checkov)
  --llm-enable                  Enable LLM enrichment (requires AWS Bedrock)
  --llm-tool-router / --tool-routing  Enable LLM-based tool routing (default: True when --llm-enable)
  --general-tool TEXT           General fallback tool ID (default: checkov)
  --llm-region TEXT             AWS region for LLM calls [default: eu-north-1]
  --model-id TEXT               Bedrock model ID [default: us.amazon.nova-micro-v1:0]
  --allow-network               Allow network operations (e.g., git clone)
  -o, --output-dir TEXT          Output directory [default: out]
  --run-dir TEXT                 Base directory for run artifacts [default: out/runs]
  --export-findings-raw         Export raw findings JSON
  --export-gaps                 Export gaps JSON
```

## Output Artifacts

The pipeline always generates these files in the output directory (default: `out/`):

- **report.md**: Human-readable Markdown report
- **report.json**: Complete report in JSON format
- **metrics.json**: Pipeline execution metrics

Optional exports (with flags):

- **findings_raw.json**: Raw findings from all tools
- **gaps.json**: Detailed gap analysis

## Default Behavior (DRY-RUN)

**Important Security Note**: By default, IaC Agent does NOT:

- Execute any external tools (terraform, tfsec, checkov)
- Perform network operations (git clone)
- Make LLM API calls

This ensures safe exploration and testing. You must explicitly enable features with flags:

- `--execute-tools`: Run security scanners
- `--allow-network`: Allow git clone operations
- `--llm-enable`: Enable AWS Bedrock LLM calls

## External Tools

IaC Agent requires these tools to be installed separately:

### Terraform

```bash
# macOS
brew install terraform

# Linux (using tfenv)
tfenv install latest

# Windows (using Chocolatey)
choco install terraform
```

### tfsec

```bash
# macOS
brew install tfsec

# Linux
wget https://github.com/aquasecurity/tfsec/releases/latest/download/tfsec-linux-amd64 -O /usr/local/bin/tfsec
chmod +x /usr/local/bin/tfsec

# Windows (using Chocolatey)
choco install tfsec
```

### Checkov

```bash
# Using pip
pip install checkov

# Using Homebrew (macOS)
brew install checkov
```

## AWS Bedrock Setup (Optional)

To use LLM enrichment, configure AWS credentials using one of these methods:

### Option 1: Using `.env.local` (Recommended for local development)

Create a `.env.local` file in the project root:

```bash
# Copy the example file
cp .env.example .env.local

# Edit .env.local with your actual credentials
```

The `.env.local` file will be automatically loaded when you run the CLI. Example contents:

```env
AWS_ACCESS_KEY_ID=your-access-key-id-here
AWS_SECRET_ACCESS_KEY=your-secret-access-key-here
AWS_REGION=eu-north-1
BEDROCK_MODEL_ID=us.amazon.nova-micro-v1:0
```

**Note**: `.env.local` is in `.gitignore` and will not be committed to version control.

### Option 2: Using AWS CLI

```bash
aws configure
```

### Option 3: Using Environment Variables

```bash
# PowerShell (Windows)
$env:AWS_ACCESS_KEY_ID = "your-key"
$env:AWS_SECRET_ACCESS_KEY = "your-secret"
$env:AWS_DEFAULT_REGION = "eu-north-1"

# Bash/Zsh (Linux/macOS)
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
export AWS_DEFAULT_REGION=eu-north-1
```

The default model is `us.amazon.nova-micro-v1:0` in region `eu-north-1`. You can override via `--model-id` and `--llm-region` flags, or environment variables `BEDROCK_MODEL_ID`, `AWS_REGION`, or `AWS_DEFAULT_REGION`.

## Project Structure

```
iac-agent/
├── src/
│   └── iac_agent/
│       ├── models/          # Pydantic v2 data contracts
│       ├── tools/           # Tool wrappers (terraform, tfsec, checkov)
│       ├── analysis/        # Normalization, dedup, gap building
│       ├── llm/             # AWS Bedrock integration
│       ├── pipeline/        # Pipeline orchestration
│       ├── reporting/       # Report generation
│       ├── metrics/         # Metrics collection
│       └── cli.py           # CLI entry point
├── prompts/                 # LLM prompt templates
├── pyproject.toml           # Project configuration
└── README.md
```

## Development

### Setup Development Environment

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Format code
ruff format .

# Lint code
ruff check .

# Type checking
mypy src/
```

## Determinism

IaC Agent ensures deterministic outputs:

- **Finding IDs**: Generated from tool + rule_id + file_path (SHA256 hash)
- **Gap IDs**: Generated from category + sorted finding IDs (SHA256 hash)
- **Deduplication**: Based on finding IDs, no randomness
- **No Timestamps**: Gap IDs and dedup keys never include timestamps

This ensures consistent results across runs.

## Example Workflow

1. **Initial Assessment (Dry-Run)**:
   ```bash
   iac-agent scan --local-path ./terraform
   ```
   Review `out/report.md` to understand what would be scanned.

2. **Execute Tools**:
   ```bash
   iac-agent scan --local-path ./terraform --execute-tools
   ```
   Get actual findings from security scanners.

3. **Full Analysis with LLM**:
   ```bash
   iac-agent scan \
     --local-path ./terraform \
     --execute-tools \
     --llm-enable \
     --request "Assess for FedRAMP Moderate compliance"
   ```
   Get enriched analysis with FedRAMP mapping and remediation advice.

## License

MIT

## Contributing

Contributions welcome! Please ensure:

- Code is ruff-formatted and mypy-clean
- Determinism is maintained (no timestamps in IDs)
- Tool failures don't crash the pipeline
