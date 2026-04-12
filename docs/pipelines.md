# HordeForge Pipelines

This document describes the production pipeline set used by HordeForge.

## Active Pipelines

| Name | Purpose | File |
|---|---|---|
| `init_pipeline` | Connect repository and prepare runtime context | `pipelines/init_pipeline.yaml` |
| `ci_scanner_pipeline` | Analyze failed CI and create/enrich incident issue with `agent:opened` label | `pipelines/ci_scanner_pipeline.yaml` |
| `ci_fix_pipeline` | Production-safe execution pipeline for CI incidents and repair tasks | `pipelines/ci_fix_pipeline.yaml` |
| `issue_scanner_pipeline` | Scan staged issues (`agent:opened/planning/ready/fixed`), run planning when required, dispatch `feature_pipeline` or `ci_fix_pipeline`, close validated fixed issues | `pipelines/issue_scanner_pipeline.yaml` |
| `feature_pipeline` | Execute prepared implementation plan, run tests/fix/review, decide merge by safety gates | `pipelines/feature_pipeline.yaml` |
| `dependency_check_pipeline` | Dependency checks and analysis | `pipelines/dependency_check_pipeline.yaml` |
| `code_generation` | Standalone code/test/fix/review flow used for experiments | `pipelines/code_generation.yaml` |

## Retired Pipelines

These pipelines were removed to avoid duplicated scanner logic:

- `all_issues_scanner_pipeline`
- `all_issues_no_filter_pipeline`
- `backlog_analysis_pipeline`

## Production Flow

1. `ci_scanner_pipeline` captures CI failure and creates/enriches an `agent:opened` issue.
2. `issue_scanner_pipeline` processes labels:
   - `agent:opened` -> `agent:planning` -> planning artifacts -> dispatch -> `agent:ready`
   - `agent:planning` -> planning artifacts -> dispatch
   - `agent:ready` -> direct dispatch without planning
   - `agent:fixed` -> validate related merged PR and close issue
3. `issue_scanner_pipeline` dispatches CI incidents to `ci_fix_pipeline` and non-CI issues to `feature_pipeline`.

## Merge Safety Gates

`pr_merge_agent` merges only if all are true:

- review decision is `approve`
- tests passed (`failed=0`, `exit_code=0`)
- PR exists

In dry-run/no-live-merge mode, `merged` remains `false`.

On successful merge:
- Automatically applies `agent:merged` label to the issue
- Removes planning labels: `agent:opened`, `agent:planning`, `agent:ready`, `agent:fixed`
- Posts a service comment with PR link

## CI Fix Pipeline Quality Gates

The `ci_fix_pipeline` includes comprehensive quality validation:

### Patch Quality Gate

Enabled via `enforce_patch_quality_gate: true` in pipeline definition.

**Quality Checks**:
1. **Unjustified Full Rewrite**: Detects files >400 lines without `full_file_rewrite_approved` in decisions
2. **Analysis-Only Patch**: Blocks responses with analysis markers but no source code changes
3. **Test-Only Change**: Prevents modifying only test files when source file candidates exist

**Quality Gate Modes**:
- `enforce` (default): Blocks execution on quality gate failure
- `shadow`/`observe`/`monitor`: Records quality metrics without blocking

**Quality Gate Output**:
```yaml
quality_gate:
  passed: true/false
  reasons: []  # List of failure reasons
  enforced: true/false
  mode: "enforce"  # or "shadow"
  target_files_count: N
  selected_files_count: M
```

### Strict Target Files Mode

Enabled via `strict_target_files: true`:
- Rejects files not in candidate list
- Allows existing non-candidate files when `allow_new_files=false`
- Prevents hallucinated file creation

### Fix Agent Strategy Rotation

The `fix_agent` rotates through strategies in the loop:
1. `status_transition_guard`
2. `failing_test_alignment`
3. `minimal_source_correction`

Stops after exhausting all strategies with `max_strategy_classes_exhausted`.

### Execution Guardrails

The orchestrator includes pre/post execution hooks:

**Pre-Execution**:
- Permission validation via `__step_permissions` and `__granted_permissions`
- Blocks steps without required permissions

**Post-Execution**:
- Validates output has required keys: `status`, `artifacts`, `decisions`, `logs`, `next_actions`
- Ensures `artifacts` is a list
- Fails step on validation error

