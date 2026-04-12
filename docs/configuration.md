# HordeForge Configuration

This document describes the configuration options available in HordeForge.

## Environment Variables

### Core Configuration

| Variable | Default | Description |
|---|---|---|
| `HORDEFORGE_GATEWAY_URL` | `http://localhost:8000` | Gateway endpoint URL |
| `HORDEFORGE_PIPELINES_DIR` | `pipelines` | Directory containing pipeline YAML files |
| `HORDEFORGE_STORAGE_DIR` | `.hordeforge_data` | Base directory for storage backends |
| `HORDEFORGE_QUEUE_BACKEND` | `memory` | Queue backend (`memory`, `redis`) |
| `HORDEFORGE_MAX_PARALLEL_WORKERS` | `4` | Maximum parallel step execution workers |

### Token Budget

| Variable | Default | Description |
|---|---|---|
| `HORDEFORGE_TOKEN_BUDGET_DAILY_LIMIT` | `10.0` | Daily token budget limit (USD) |
| `HORDEFORGE_TOKEN_BUDGET_MONTHLY_LIMIT` | `100.0` | Monthly token budget limit (USD) |
| `HORDEFORGE_TOKEN_BUDGET_SESSION_LIMIT` | `5.0` | Per-session token budget limit (USD) |

### Context & Memory

| Variable | Default | Description |
|---|---|---|
| `HORDEFORGE_CONTEXT_COMPRESSION_ENABLED` | `true` | Enable context compression |
| `HORDEFORGE_CONTEXT_MAX_TOKENS` | `4000` | Maximum tokens for context |
| `HORDEFORGE_MEMORY_ENABLED` | `true` | Enable agent memory system |
| `HORDEFORGE_VECTOR_STORE_MODE` | `auto` | Vector store mode (`local`, `host`, `auto`) |

### LLM Session Logging

| Variable | Default | Description |
|---|---|---|
| `HORDEFORGE_LLM_SESSION_LOGGING` | `all` | LLM session logging mode: `off`, `errors`, `all` |
| `HORDEFORGE_LLM_SESSION_DIR` | (auto) | Custom directory for LLM session JSON files |

**Session Logging Details**:
- When enabled, each LLM request/response is logged to a JSON file
- Files contain: timestamp, provider, model, status, latency, prompt, response, error
- Sensitive data is automatically redacted
- Default location: `.hordeforge_data/last_logs/current/llm_sessions/`
- Files are atomically written (`.tmp` → `.json`)

## Pipeline Context Flags

These flags can be set in pipeline YAML definitions or passed via context.

### Patch Quality Control

| Flag | Type | Default | Description |
|---|---|---|---|
| `strict_target_files` | `bool` | `false` | When `true`, reject files not in candidate list |
| `enforce_patch_quality_gate` | `bool` | `false` | When `true`, block execution on quality gate failure |
| `quality_gate_mode` | `string` | `enforce` | Quality gate mode: `enforce`, `shadow`, `observe`, `monitor` |

**Quality Gate Checks**:
1. **Unjustified Full Rewrite**: Files >400 lines without `full_file_rewrite_approved` in decisions
2. **Analysis-Only Patch**: Responses with analysis markers but no source changes
3. **Test-Only Change**: Modifying only test files when source candidates exist

**Usage Example** (ci_fix_pipeline.yaml):
```yaml
- name: code_generator
  agent: code_generator
  input:
    strict_target_files: true
    enforce_patch_quality_gate: true
    quality_gate_mode: enforce
```

### LLM Control

| Flag | Type | Default | Description |
|---|---|---|---|
| `use_llm` | `bool` | `true` | Enable LLM usage |
| `require_llm` | `bool` | `false` | Require LLM (fail if unavailable) |
| `publish_pr_in_code_generator` | `bool` | `true` | Allow PR creation in code_generator |

### Target Files

| Flag | Type | Description |
|---|---|---|
| `target_files` | `list[str]` | Explicit list of files to modify |

## Orchestrator Configuration

### Execution Guardrail Hook

The orchestrator accepts an optional `execution_guardrail_hook` parameter:

```python
engine = OrchestratorEngine(
    execution_guardrail_hook=MyCustomGuardrailHook()
)
```

**Default Behavior** (`BasicExecutionGuardrailHook`):

**Pre-Execution Checks**:
- Validates `__step_permissions` against `__granted_permissions`
- Blocks steps with missing permissions

**Post-Execution Checks**:
- Validates output has required keys: `status`, `artifacts`, `decisions`, `logs`, `next_actions`
- Ensures `artifacts` is a list
- Fails step on validation error

### Retry Policy

```python
from orchestrator.retry import RetryPolicy

retry_policy = RetryPolicy(
    retry_limit=3,           # Maximum retry attempts
    backoff_seconds=1.0      # Base backoff duration
)
```

### Loop Configuration

```python
engine = OrchestratorEngine(
    max_loop_iterations=10,      # Maximum loop iterations
    max_parallel_workers=4       # Maximum parallel workers
)
```

## Pipeline Validator

The validator now models execution phases:

- **Pre-loop steps**: Execute in file order
- **Loop steps**: Execute in loop order, can consume outputs from previous iterations
- **Post-loop steps**: Execute after loops, can consume loop outputs

Declared loop cycles in `pipeline.loops` are allowed and skipped during cycle detection.

## Storage Backend Resilience

### JSON Storage Backend

- Retries on `PermissionError` and `FileNotFoundError`
- Automatically creates parent directories
- Cleans up temp files on failure
- Atomic writes (`.tmp` → final)

## Memory Agent

### Collection Check

The memory agent now checks if collection exists before semantic search:
- Returns empty results if collection is missing
- Logs `memory_semantic_search_skipped_missing_collection` instead of warning

## CI Failure Analyzer

### Enhanced Metadata Extraction

The analyzer extracts from issue handoff markdown:
- `Candidate Files` section
- `Test Targets` section  
- `Failed Jobs / Details` section

Returns structured output:
```python
{
    "candidate_files": [...],
    "test_targets": [...],
    "failure_analysis": [...],
    "failed_jobs_details": [...],
    "ci_metadata": {...}
}
```

### Classification Priority

Test failure patterns are checked **before** infrastructure noise:
1. Build failure patterns
2. **Test failure patterns** (moved up)
3. Infrastructure patterns
4. Python errors

## PR Merge Agent

### Auto-Labeling

On successful merge:
1. Applies `agent:merged` label
2. Removes: `agent:opened`, `agent:planning`, `agent:ready`, `agent:fixed`
3. Posts service comment with PR link

### PR Creation Condition

PR is created only when:
- `publish_pr_in_merge_agent` is true
- No existing PR
- GitHub client is available
- Review is **approved**
- Tests **passed**

## Fix Agent

### Strategy Sequence

```python
STRATEGY_SEQUENCE = (
    "status_transition_guard",     # Iteration 1, 4, 7...
    "failing_test_alignment",       # Iteration 2, 5, 8...
    "minimal_source_correction"     # Iteration 3, 6, 9...
)
```

### Fix Plan

Before code generation, creates validation plan:
```python
{
    "iteration": 1,
    "strategy_class": "status_transition_guard",
    "target_files": [...],
    "hypothesis": "...",
    "expected_transition": "...",
    "current_failed": N,
    "current_exit_code": N,
    "plan_valid": true/false
}
```

### Termination Conditions

- **Max strategies exhausted**: Returns `FAILED` with `max_strategy_classes_exhausted`
- **Strategy repetition**: Returns `FAILED` with `strategy_repetition_blocked`
- **No target files**: Returns `FAILED` with `missing_target_files`

## Code Generator

### Instruction Stack

Versioned, layered instruction prompts:

```python
instruction_stack = [
    "global_agent_rules",
    "pipeline_ci_fix_rules",
    "strict_target_files",  # or "non_strict_targets"
    "quality_gate_enforced"  # or "quality_gate_observe_only"
]
```

### Candidate File Snippets

Loads real file content for grounding:
- Up to 3 files
- Up to 3000 characters per file
- Reads from `workspace/repo/<path>` or `<path>`
- Injected into LLM prompt as `## Candidate file snippets`

### Test-to-Source Inference

Automatically infers source files from test paths:
- `tests/unit/test_foo.py` → `foo.py`
- `tests/integration/test_bar_baz.py` → `baz.py`
- Strips test directory prefixes: `unit`, `integration`, `e2e`, etc.

### Placeholder Detection

Filters patches containing:
- "placeholder content - actual file content would be provided"
- "cannot implement fix without access to the actual source code"
- "no source files were identified to modify"
- "without seeing the actual"
- "# generated test file"
- "need to find and examine the specific test case"
- "analyze the failing test"
- "cannot implement fix without"

## Specification Writer

### LLM JSON Repair

On parse failure:
1. Sends raw response to LLM with repair prompt
2. Attempts to parse repaired JSON
3. Falls back to deterministic spec if repair fails

### CI Handoff Enrichment

Extracts from issue body:
- `candidate_files` from `### Candidate Files` section
- `test_targets` from `### Test Targets` section
- `failed_job_excerpt` from `### Failed Jobs / Details` section

Injects into spec prompt context.

### RAG Context Injection

Adds `source_ref` values from RAG items to spec `requirements`:
```python
{
    "requirements": ["source_ref_1", "source_ref_2", ...],
    "notes": ["rag_items_used=3"]
}
```

## Patch Output Schema

### Quality Gate Object

```json
{
  "quality_gate": {
    "passed": true,
    "reasons": [],
    "enforced": true,
    "mode": "enforce",
    "target_files_count": 5,
    "selected_files_count": 3
  }
}
```

### Loop Metrics Object

```json
{
  "loop_metrics": {
    "quality_gate_passed": true,
    "quality_gate_reason_count": 0,
    "target_files_count": 5,
    "selected_files_count": 3,
    "strict_target_files": true
  }
}
```

### Instruction Stack/Layers

```json
{
  "instruction_stack": ["global_agent_rules", "pipeline_ci_fix_rules", ...],
  "instruction_layers": {
    "global_agent_rules": "...",
    "pipeline_ci_fix_rules": "..."
  }
}
```

## Troubleshooting

### LLM Session Files Not Created

1. Check `HORDEFORGE_LLM_SESSION_LOGGING` is not `off`
2. Verify `HORDEFORGE_STORAGE_DIR` is writable
3. Check logs for `llm_session_write_failed` warnings

### Quality Gate Blocking Unexpectedly

1. Review `quality_gate.reasons` in patch output
2. Check if `enforce_patch_quality_gate` is `true`
3. Consider `quality_gate_mode: shadow` for observation

### Strategy Repetition Blocked

1. Review `fix_plan.strategy_class` in context
2. Ensure different strategies are being applied
3. Check if fix loop is making progress

### Permission Denied on Step Execution

1. Verify `__step_permissions` mapping in context
2. Check `__granted_permissions` list
3. Review guardrail hook implementation
