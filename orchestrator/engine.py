from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from logging_utils import redact_mapping
from orchestrator.context import ExecutionContext
from orchestrator.executor import StepExecutor
from orchestrator.loader import LoopDefinition, PipelineDefinition, PipelineLoader, StepDefinition
from orchestrator.override import RUN_OVERRIDE_REGISTRY
from orchestrator.parallel import build_step_dependency_graph, select_lock_aware_batch
from orchestrator.retry import RetryPolicy
from orchestrator.state import PipelineRunState
from orchestrator.status import StepStatus
from orchestrator.summary import RunSummaryBuilder
from rules.loader import DEFAULT_RULE_SET_VERSION, RulePackLoader

POLICY_ACTIONS: dict[str, str] = {
    "stop_pipeline": "stop",
    "log_warning": "continue",
    "retry_step": "retry",
    "create_issue_for_human": "block",
    "escalate_to_human": "block",
    "skip_step": "continue",
    "trigger_fix_loop": "continue",
}


class OrchestratorEngine:
    def __init__(
        self,
        pipelines_dir: str = "pipelines",
        *,
        pipeline_loader: PipelineLoader | None = None,
        step_executor: StepExecutor | None = None,
        retry_policy: RetryPolicy | None = None,
        summary_builder: RunSummaryBuilder | None = None,
        strict_schema_validation: bool = True,
        enable_dynamic_fallback: bool = True,
        dynamic_fallback_allowlist: set[str] | None = None,
        max_loop_iterations: int = 5,
        max_parallel_workers: int = 4,
        rules_dir: str = "rules",
        rule_set_version: str = DEFAULT_RULE_SET_VERSION,
        rule_pack_loader: RulePackLoader | None = None,
    ):
        self.pipeline_loader = pipeline_loader or PipelineLoader(pipelines_dir=pipelines_dir)
        self.step_executor = step_executor or StepExecutor(
            strict_schema_validation=strict_schema_validation,
            enable_dynamic_fallback=enable_dynamic_fallback,
            fallback_allowlist=dynamic_fallback_allowlist,
        )
        self.retry_policy = retry_policy or RetryPolicy(retry_limit=0, backoff_seconds=0.0)
        self.summary_builder = summary_builder or RunSummaryBuilder()
        self.max_loop_iterations = max_loop_iterations
        self.max_parallel_workers = max(1, int(max_parallel_workers))
        self.rule_pack_loader = rule_pack_loader or RulePackLoader(
            rules_dir=rules_dir,
            rule_set_version=rule_set_version,
        )
        self.logger = logging.getLogger("hordeforge.orchestrator.engine")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _log_event(self, level: int, run_id: str, event: str, **fields: Any) -> None:
        safe_fields = redact_mapping(fields)
        correlation_id = safe_fields.pop("correlation_id", None)
        step = safe_fields.pop("step", safe_fields.pop("step_name", None))
        payload = {
            "timestamp": self._now_iso(),
            "level": logging.getLevelName(level),
            "component": "orchestrator_engine",
            "run_id": run_id,
            "correlation_id": correlation_id,
            "step": step,
            "event": event,
            **safe_fields,
        }
        self.logger.log(level, json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def _is_step_success(output: dict[str, Any]) -> bool:
        return output.get("status") in {"SUCCESS", "PARTIAL_SUCCESS"}

    @staticmethod
    def _resolve_policy_action(on_failure: str) -> str:
        return POLICY_ACTIONS.get(on_failure, "stop")

    @staticmethod
    def _resolve_path(source: dict[str, Any], dotted_path: str) -> Any:
        current: Any = source
        for part in dotted_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    @staticmethod
    def _derive_trace_id(correlation_id: str, run_id: str) -> str:
        seed = f"{correlation_id}:{run_id}"
        return sha256(seed.encode("utf-8")).hexdigest()[:32]

    def _load_rules_payload(self) -> dict[str, Any]:
        return deepcopy(self.rule_pack_loader.load())

    def _evaluate_loop_condition(self, condition: str, state: dict[str, Any]) -> bool:
        pattern = r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}\s*(==|!=|>=|<=|>|<)\s*(-?\d+)"
        match = re.fullmatch(pattern, condition.strip())
        if not match:
            return False

        path, operator, right_value_raw = match.groups()
        left = self._resolve_path(state, path)
        if left is None:
            return False
        try:
            left_value = float(left)
            right_value = float(right_value_raw)
        except (TypeError, ValueError):
            return False

        if operator == "==":
            return left_value == right_value
        if operator == "!=":
            return left_value != right_value
        if operator == ">":
            return left_value > right_value
        if operator == "<":
            return left_value < right_value
        if operator == ">=":
            return left_value >= right_value
        return left_value <= right_value

    def _execute_step_with_policy(
        self,
        step: StepDefinition,
        context: ExecutionContext,
        run_state: PipelineRunState,
    ) -> tuple[dict[str, Any], bool]:
        override_request = RUN_OVERRIDE_REGISTRY.get(context.run_id)
        if override_request is not None and override_request.action == "stop":
            run_state.set_run_status(StepStatus.BLOCKED)
            run_state.mark_step_status(
                step.name,
                StepStatus.SKIPPED,
                finished_at=self._now_iso(),
                error=f"Run stopped by override: {override_request.reason or 'no reason provided'}",
            )
            self._log_event(
                logging.WARNING,
                context.run_id,
                "step_skipped_by_override",
                step_name=step.name,
                action=override_request.action,
                reason=override_request.reason,
                correlation_id=context.metadata.get("correlation_id"),
            )
            return {
                "status": "BLOCKED",
                "artifacts": [],
                "decisions": [],
                "logs": ["Run stopped by operator override."],
                "next_actions": [],
            }, True

        retry_attempt = 0
        while True:
            output = self.step_executor.execute_step(step, context, run_state)
            if self._is_step_success(output):
                run_state.advance_index()
                return output, False

            action = self._resolve_policy_action(step.on_failure)
            if action == "retry":
                retry_attempt += 1
                if self.retry_policy.should_retry(retry_attempt, step.retry_limit):
                    backoff = self.retry_policy.backoff_duration(retry_attempt)
                    self._log_event(
                        logging.WARNING,
                        context.run_id,
                        "step_retry",
                        step_name=step.name,
                        attempt=retry_attempt,
                        backoff_seconds=backoff,
                        correlation_id=context.metadata.get("correlation_id"),
                    )
                    if backoff > 0:
                        time.sleep(backoff)
                    continue
                action = "block"

            if action == "continue":
                run_state.mark_step_status(
                    step.name,
                    StepStatus.SKIPPED,
                    finished_at=self._now_iso(),
                    error=f"Step failed but continued by policy: {step.on_failure}",
                )
                run_state.advance_index()
                return output, False

            if action == "block":
                run_state.set_run_status(StepStatus.BLOCKED)
                return output, True

            run_state.set_run_status(StepStatus.FAILED)
            return output, True

    def _execute_loop(
        self,
        loop: LoopDefinition,
        step_by_name: dict[str, StepDefinition],
        context: ExecutionContext,
        run_state: PipelineRunState,
        step_results: dict[str, dict[str, Any]],
    ) -> bool:
        iterations = 0
        while self._evaluate_loop_condition(loop.condition, context.state):
            iterations += 1
            if iterations > self.max_loop_iterations:
                raise RuntimeError(
                    f"Loop exceeded max iterations ({self.max_loop_iterations}): {loop.condition}"
                )
            for step_name in loop.steps:
                step = step_by_name.get(step_name)
                if not step:
                    raise ValueError(f"Loop references unknown step: {step_name}")
                output, should_stop = self._execute_step_with_policy(step, context, run_state)
                step_results[step_name] = output
                if should_stop:
                    return True
        return False

    def _execute_step_batch(
        self,
        steps: list[StepDefinition],
        context: ExecutionContext,
        run_state: PipelineRunState,
    ) -> tuple[dict[str, dict[str, Any]], bool]:
        if not steps:
            return {}, False
        if len(steps) == 1 or self.max_parallel_workers <= 1:
            output, should_stop = self._execute_step_with_policy(steps[0], context, run_state)
            return {steps[0].name: output}, should_stop

        outputs: dict[str, dict[str, Any]] = {}
        should_stop = False
        with ThreadPoolExecutor(max_workers=min(self.max_parallel_workers, len(steps))) as pool:
            futures = {
                pool.submit(self._execute_step_with_policy, step, context, run_state): step.name
                for step in steps
            }
            for future, step_name in futures.items():
                output, step_should_stop = future.result()
                outputs[step_name] = output
                should_stop = should_stop or step_should_stop
        return outputs, should_stop

    def _execute_with_parallelism(
        self,
        steps_to_execute: list[StepDefinition],
        context: ExecutionContext,
        run_state: PipelineRunState,
        step_results: dict[str, dict[str, Any]],
    ) -> bool:
        dependencies = build_step_dependency_graph(steps_to_execute)
        step_by_name = {step.name: step for step in steps_to_execute}
        ordered_names = [step.name for step in steps_to_execute]
        executed: set[str] = set()

        should_stop = False
        while len(executed) < len(steps_to_execute):
            ready_steps = [
                step_by_name[name]
                for name in ordered_names
                if name not in executed and dependencies[name].issubset(executed)
            ]
            if not ready_steps:
                unresolved = sorted(name for name in ordered_names if name not in executed)
                raise ValueError(
                    "Pipeline contains cyclic or unresolved dependencies: " + ", ".join(unresolved)
                )

            ready_queue = list(ready_steps)
            while ready_queue:
                batch = select_lock_aware_batch(ready_queue)
                outputs, batch_should_stop = self._execute_step_batch(batch, context, run_state)
                for step in batch:
                    step_results[step.name] = outputs[step.name]
                    executed.add(step.name)
                ready_queue = [item for item in ready_queue if item.name not in outputs]
                if batch_should_stop:
                    should_stop = True
                    break
            if should_stop:
                break
        return should_stop

    @staticmethod
    def _derive_final_status(
        run_state: PipelineRunState,
        step_results: dict[str, dict[str, Any]],
    ) -> str:
        if run_state.run_status in {StepStatus.FAILED.value, StepStatus.BLOCKED.value}:
            return run_state.run_status
        if any(output.get("status") == "PARTIAL_SUCCESS" for output in step_results.values()):
            return "PARTIAL_SUCCESS"
        return StepStatus.SUCCESS.value

    def run(
        self,
        pipeline_name: str,
        inputs: dict[str, Any] | None = None,
        *,
        run_id: str,
        metadata: dict[str, Any] | None = None,
        resume_run_state: dict[str, Any] | None = None,
        resume_step_results: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        pipeline: PipelineDefinition = self.pipeline_loader.load(pipeline_name)
        raw_metadata = dict(metadata or {})
        resumed_state_payload = resume_run_state if isinstance(resume_run_state, dict) else None
        resumed_step_results_payload = (
            resume_step_results if isinstance(resume_step_results, dict) else {}
        )
        resumed_correlation_id = (
            str(resumed_state_payload.get("correlation_id", "")).strip()
            if resumed_state_payload is not None
            else ""
        )
        resumed_trace_id = (
            str(resumed_state_payload.get("trace_id", "")).strip()
            if resumed_state_payload is not None
            else ""
        )

        correlation_id = (
            str(raw_metadata.get("correlation_id", "")).strip()
            or resumed_correlation_id
            or f"run:{run_id}"
        )
        trace_id = (
            str(raw_metadata.get("trace_id", "")).strip()
            or resumed_trace_id
            or self._derive_trace_id(
                correlation_id,
                run_id,
            )
        )
        root_span_id = str(raw_metadata.get("root_span_id", "")).strip() or uuid4().hex[:16]
        raw_metadata["correlation_id"] = correlation_id
        raw_metadata["trace_id"] = trace_id
        raw_metadata["root_span_id"] = root_span_id
        runtime_inputs = dict(inputs or {})
        runtime_inputs["rules"] = self._load_rules_payload()
        context = ExecutionContext(
            run_id=run_id,
            pipeline_name=pipeline.pipeline_name,
            inputs=runtime_inputs,
            metadata=raw_metadata,
        )
        if resumed_state_payload is None:
            run_state = PipelineRunState.from_steps(
                run_id=run_id,
                pipeline_name=pipeline.pipeline_name,
                steps=[(step.name, step.agent) for step in pipeline.steps],
                correlation_id=correlation_id,
                trace_id=trace_id,
            )
            step_results: dict[str, dict[str, Any]] = {}
            start_step_index = 0
        else:
            run_state = PipelineRunState.from_dict(resumed_state_payload)
            if run_state.run_id != run_id:
                raise ValueError(
                    f"Resume state run_id mismatch: expected '{run_id}', got '{run_state.run_id}'"
                )
            if run_state.pipeline_name != pipeline.pipeline_name:
                raise ValueError(
                    "Resume state pipeline mismatch: "
                    f"expected '{pipeline.pipeline_name}', got '{run_state.pipeline_name}'"
                )
            run_state.correlation_id = correlation_id
            run_state.trace_id = trace_id
            step_results = {
                step_name: step_output
                for step_name, step_output in resumed_step_results_payload.items()
                if isinstance(step_name, str) and isinstance(step_output, dict)
            }
            for step_name, step_output in step_results.items():
                context.record_step_result(step_name, step_output)
            try:
                raw_step_index = int(run_state.current_step_index)
            except (TypeError, ValueError):
                raw_step_index = 0
            start_step_index = max(0, min(len(pipeline.steps), raw_step_index))
            run_state.current_step_index = start_step_index

        steps_to_execute = pipeline.steps[start_step_index:]
        self._log_event(
            logging.INFO,
            run_id,
            "orchestrator_run_start",
            pipeline_name=pipeline.pipeline_name,
            step_count=len(pipeline.steps),
            resume_mode=resumed_state_payload is not None,
            start_step_index=start_step_index,
            correlation_id=correlation_id,
            trace_id=trace_id,
            root_span_id=root_span_id,
        )

        should_stop = False
        if resumed_state_payload is not None:
            for step in steps_to_execute:
                output, should_stop = self._execute_step_with_policy(step, context, run_state)
                step_results[step.name] = output
                if should_stop:
                    break
        else:
            should_stop = self._execute_with_parallelism(
                steps_to_execute,
                context,
                run_state,
                step_results,
            )

        if not should_stop and pipeline.loops:
            step_by_name = {step.name: step for step in pipeline.steps}
            for loop in pipeline.loops:
                should_stop = self._execute_loop(
                    loop, step_by_name, context, run_state, step_results
                )
                if should_stop:
                    break

        final_status = self._derive_final_status(run_state, step_results)
        run_state.run_status = final_status
        summary = self.summary_builder.build(run_state, step_results)
        self._log_event(
            logging.INFO if final_status not in {"FAILED", "BLOCKED"} else logging.ERROR,
            run_id,
            "orchestrator_run_end",
            pipeline_name=pipeline.pipeline_name,
            status=final_status,
            correlation_id=correlation_id,
            trace_id=trace_id,
            root_span_id=root_span_id,
        )

        trace_steps = [
            {
                "step": step.name,
                "trace_id": step.trace_id,
                "span_id": step.span_id,
                "parent_span_id": step.parent_span_id,
                "started_at": step.started_at,
                "finished_at": step.finished_at,
            }
            for step in run_state.steps
        ]
        return {
            "run_id": run_id,
            "pipeline_name": pipeline.pipeline_name,
            "status": final_status,
            "steps": step_results,
            "summary": summary,
            "run_state": run_state.to_dict(),
            "trace": {
                "correlation_id": correlation_id,
                "trace_id": trace_id,
                "root_span_id": root_span_id,
                "steps": trace_steps,
            },
        }
