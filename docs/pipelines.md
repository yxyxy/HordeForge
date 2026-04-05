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
- tests passed
- PR exists

In dry-run/no-live-merge mode, `merged` remains `false`.

