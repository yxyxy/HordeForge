from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from typing import Any

from hordeforge_utils import resolve_path
from orchestrator.checkpointing import emit_checkpoint
from orchestrator.context import ExecutionContext
from orchestrator.executor import StepExecutor
from orchestrator.hooks import ExecutionGuardrailHook
from orchestrator.loader import LoopDefinition, StepDefinition
from orchestrator.loop_eval import evaluate_loop_condition
from orchestrator.override import RUN_OVERRIDE_REGISTRY
from orchestrator.parallel import build_step_dependency_graph, select_lock_aware_batch
from orchestrator.retry import RetryPolicy
from orchestrator.state import PipelineRunState
from orchestrator.status import StepStatus
from orchestrator.validation import RuntimeSchemaValidator

POLICY_ACTIONS: dict[str, str] = {
    "stop_pipeline": "stop",
    "log_warning": "continue",
    "continue": "continue",
    "retry_step": "retry",
    "create_issue_for_human": "block",
    "escalate_to_human": "block",
    "skip_step": "continue",
    "trigger_fix_loop": "continue",
}


class PipelineRunner:
    def __init__(
        self,
        step_executor: StepExecutor,
        retry_policy: RetryPolicy,
        execution_guardrail_hook: ExecutionGuardrailHook,
        max_loop_iterations: int,
        max_parallel_workers: int,
        checkpoint_lock: RLock,
        state_validator: RuntimeSchemaValidator,
        logger: logging.Logger,
    ) -> None:
        self.step_executor = step_executor
        self.retry_policy = retry_policy
        self.execution_guardrail_hook = execution_guardrail_hook
        self.max_loop_iterations = max_loop_iterations
        self.max_parallel_workers = max(1, int(max_parallel_workers))
        self.checkpoint_lock = checkpoint_lock
        self.state_validator = state_validator
        self.logger = logger

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _resolve_policy_action(on_failure: str) -> str:
        return POLICY_ACTIONS.get(on_failure, "stop")

    @staticmethod
    def _is_step_success(output: dict[str, Any]) -> bool:
        return output.get("status") in {"SUCCESS", "PARTIAL_SUCCESS"}

    def _log_event(self, level: int, run_id: str, event: str, **fields: Any) -> None:
        import json

        from logging_utils import redact_mapping

        safe_fields = redact_mapping(fields)
        correlation_id = safe_fields.pop("correlation_id", None)
        step = safe_fields.pop("step", safe_fields.pop("step_name", None))
        payload = {
            "timestamp": self._now_iso(),
            "level": logging.getLevelName(level),
            "component": "pipeline_runner",
            "run_id": run_id,
            "correlation_id": correlation_id,
            "step": step,
            "event": event,
            **safe_fields,
        }
        self.logger.log(level, json.dumps(payload, ensure_ascii=False))

    def execute_step_with_policy(
        self,
        step: StepDefinition,
        context: ExecutionContext,
        run_state: PipelineRunState,
        has_next_step: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        if isinstance(step.condition, str) and step.condition.strip():
            condition_matched = evaluate_loop_condition(step.condition, context.state)
            if not condition_matched:
                skipped_output = {
                    "status": "SKIPPED",
                    "artifacts": [],
                    "decisions": [
                        {
                            "reason": f"Condition not met: {step.condition}",
                            "confidence": 1.0,
                        }
                    ],
                    "logs": [f"Step skipped: condition not met ({step.condition})."],
                    "next_actions": [],
                }
                finished_at = self._now_iso()
                run_state.mark_step_status(
                    step.name,
                    StepStatus.SKIPPED,
                    finished_at=finished_at,
                    error=f"Step condition not met: {step.condition}",
                    output=skipped_output,
                )
                context.record_step_result(step.name, skipped_output)
                run_state.advance_index()
                emit_checkpoint(
                    context=context,
                    run_state=run_state,
                    checkpoint_lock=self.checkpoint_lock,
                    state_validator=self.state_validator,
                )
                self._log_event(
                    logging.INFO,
                    context.run_id,
                    "step_skipped_by_condition",
                    step_name=step.name,
                    condition=step.condition,
                    correlation_id=context.metadata.get("correlation_id"),
                )
                return skipped_output, False

        override_request = RUN_OVERRIDE_REGISTRY.get(context.run_id)
        if override_request is not None and override_request.action == "stop":
            blocked_output = {
                "status": "BLOCKED",
                "artifacts": [],
                "decisions": [],
                "logs": ["Run stopped by operator override."],
                "next_actions": [],
            }
            run_state.set_run_status(StepStatus.BLOCKED)
            run_state.mark_step_status(
                step.name,
                StepStatus.SKIPPED,
                finished_at=self._now_iso(),
                error=f"Run stopped by override: {override_request.reason or 'no reason provided'}",
                output=blocked_output,
            )
            context.record_step_result(step.name, blocked_output)
            emit_checkpoint(
                context=context,
                run_state=run_state,
                checkpoint_lock=self.checkpoint_lock,
                state_validator=self.state_validator,
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
            return blocked_output, True

        try:
            existing_step_state = run_state.get_step(step.name)
            retry_attempt = max(0, int(existing_step_state.attempts) - 1)
        except Exception as e:
            self.logger.warning("Failed to get step state for %s: %s", step.name, e)
            retry_attempt = 0
        while True:
            try:
                self.execution_guardrail_hook.before_step(
                    step_name=step.name,
                    context=context.state,
                )
            except Exception as exc:  # noqa: BLE001
                blocked_output = {
                    "status": "BLOCKED",
                    "artifacts": [],
                    "decisions": [
                        {
                            "reason": f"pre_execution_guardrail_failed:{exc}",
                            "confidence": 1.0,
                        }
                    ],
                    "logs": [f"Step blocked by pre-execution guardrail: {exc}"],
                    "next_actions": [],
                }
                run_state.set_run_status(StepStatus.BLOCKED)
                run_state.mark_step_status(
                    step.name,
                    StepStatus.BLOCKED,
                    finished_at=self._now_iso(),
                    error=str(exc),
                    output=blocked_output,
                )
                context.record_step_result(step.name, blocked_output)
                emit_checkpoint(
                    context=context,
                    run_state=run_state,
                    checkpoint_lock=self.checkpoint_lock,
                    state_validator=self.state_validator,
                )
                self._log_event(
                    logging.WARNING,
                    context.run_id,
                    "step_blocked_by_pre_execution_guardrail",
                    step_name=step.name,
                    error=str(exc),
                    correlation_id=context.metadata.get("correlation_id"),
                )
                return blocked_output, True

            output = self.step_executor.execute_step(step, context, run_state)
            try:
                self.execution_guardrail_hook.after_step(
                    step_name=step.name,
                    output=output,
                    context=context.state,
                )
            except Exception as exc:  # noqa: BLE001
                output = {
                    "status": "FAILED",
                    "artifacts": [],
                    "decisions": [
                        {
                            "reason": f"post_execution_guardrail_failed:{exc}",
                            "confidence": 1.0,
                        }
                    ],
                    "logs": [f"Step failed post-execution guardrail: {exc}"],
                    "next_actions": [],
                }

            context.record_step_result(step.name, output)
            if self._is_step_success(output):
                run_state.advance_index()
                emit_checkpoint(
                    context=context,
                    run_state=run_state,
                    checkpoint_lock=self.checkpoint_lock,
                    state_validator=self.state_validator,
                )
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
                        time.sleep(backoff)  # Blocking: sync pipeline step retry backoff
                    continue
                action = "block"

            if action == "continue":
                if run_state.run_status in {StepStatus.FAILED.value, StepStatus.BLOCKED.value}:
                    run_state.set_run_status(StepStatus.RUNNING)
                run_state.mark_step_status(
                    step.name,
                    StepStatus.SKIPPED,
                    finished_at=self._now_iso(),
                    error=f"Step failed but continued by policy: {step.on_failure}",
                )
                run_state.advance_index()
                emit_checkpoint(
                    context=context,
                    run_state=run_state,
                    checkpoint_lock=self.checkpoint_lock,
                    state_validator=self.state_validator,
                )
                return output, False

            if action == "block":
                run_state.set_run_status(StepStatus.BLOCKED)
                emit_checkpoint(
                    context=context,
                    run_state=run_state,
                    checkpoint_lock=self.checkpoint_lock,
                    state_validator=self.state_validator,
                )
                return output, True

            run_state.set_run_status(StepStatus.FAILED)
            emit_checkpoint(
                context=context,
                run_state=run_state,
                checkpoint_lock=self.checkpoint_lock,
                state_validator=self.state_validator,
            )
            return output, True

    def execute_loop(
        self,
        loop: LoopDefinition,
        step_by_name: dict[str, StepDefinition],
        context: ExecutionContext,
        run_state: PipelineRunState,
        step_results: dict[str, dict[str, Any]],
    ) -> bool:
        iterations = 0
        stagnant_iterations = 0
        previous_signature = None
        no_progress_threshold = (
            int(loop.no_progress_threshold) if loop.no_progress_threshold is not None else None
        )
        signature_path = loop.progress_signature_path or "test_results.failure_signature"

        while evaluate_loop_condition(loop.condition, context.state):
            iterations += 1
            if iterations > self.max_loop_iterations:
                loop_actions = {
                    step_by_name[step_name].on_failure
                    for step_name in loop.steps
                    if step_name in step_by_name
                }
                allow_graceful_break = any(action != "stop_pipeline" for action in loop_actions)
                if allow_graceful_break:
                    self._log_event(
                        logging.WARNING,
                        context.run_id,
                        "loop_iteration_limit_reached",
                        condition=loop.condition,
                        iterations=iterations - 1,
                        max_iterations=self.max_loop_iterations,
                        correlation_id=context.metadata.get("correlation_id"),
                    )
                    break

                raise RuntimeError(
                    f"Loop exceeded max iterations ({self.max_loop_iterations}): {loop.condition}"
                )
            retry_iteration = False
            for idx, step_name in enumerate(loop.steps):
                step = step_by_name.get(step_name)
                if not step:
                    raise ValueError(f"Loop references unknown step: {step_name}")
                has_next = idx < len(loop.steps) - 1
                output, should_stop = self.execute_step_with_policy(
                    step, context, run_state, has_next_step=has_next
                )
                step_results[step_name] = output
                if should_stop:
                    action = self._resolve_policy_action(step.on_failure)
                    is_last_loop_step = idx == len(loop.steps) - 1
                    can_retry_current_iteration = (
                        action == "stop"
                        and len(loop.steps) > 1
                        and is_last_loop_step
                        and evaluate_loop_condition(loop.condition, context.state)
                    )
                    if can_retry_current_iteration:
                        self._log_event(
                            logging.WARNING,
                            context.run_id,
                            "loop_iteration_retry",
                            step_name=step.name,
                            condition=loop.condition,
                            reason="terminal_loop_step_failed_while_condition_is_true",
                            correlation_id=context.metadata.get("correlation_id"),
                        )
                        retry_iteration = True
                        break
                    return True
            if retry_iteration:
                continue

            if no_progress_threshold is not None and no_progress_threshold > 0:
                signature_value = resolve_path(context.state, signature_path)
                signature = str(signature_value or "").strip()
                if signature:
                    if signature == previous_signature:
                        stagnant_iterations += 1
                    else:
                        stagnant_iterations = 0
                    previous_signature = signature

                if stagnant_iterations >= no_progress_threshold:
                    self._log_event(
                        logging.WARNING,
                        context.run_id,
                        "loop_no_progress_detected",
                        condition=loop.condition,
                        stagnant_iterations=stagnant_iterations,
                        signature_path=signature_path,
                        threshold=no_progress_threshold,
                        correlation_id=context.metadata.get("correlation_id"),
                    )
                    context.state.setdefault("loop_guard", {})
                    if isinstance(context.state["loop_guard"], dict):
                        context.state["loop_guard"].update(
                            {
                                "no_progress_detected": True,
                                "stagnant_iterations": stagnant_iterations,
                                "signature_path": signature_path,
                                "last_signature": previous_signature,
                            }
                        )
                    break
        return False

    def execute_step_batch(
        self,
        steps: list[StepDefinition],
        context: ExecutionContext,
        run_state: PipelineRunState,
        is_last_batch: bool = False,
    ) -> tuple[dict[str, dict[str, Any]], bool]:
        if not steps:
            return {}, False
        if len(steps) == 1 or self.max_parallel_workers <= 1:
            has_next = not is_last_batch or len(steps) > 1
            output, should_stop = self.execute_step_with_policy(
                steps[0], context, run_state, has_next_step=has_next
            )
            return {steps[0].name: output}, should_stop

        outputs: dict[str, dict[str, Any]] = {}
        should_stop = False
        last_step_index = len(steps) - 1
        with ThreadPoolExecutor(max_workers=min(self.max_parallel_workers, len(steps))) as pool:
            futures = {
                pool.submit(
                    self.execute_step_with_policy,
                    step,
                    context,
                    run_state,
                    has_next_step=(idx < last_step_index or not is_last_batch),
                ): step.name
                for idx, step in enumerate(steps)
            }
            for future, step_name in futures.items():
                output, step_should_stop = future.result()
                outputs[step_name] = output
                should_stop = should_stop or step_should_stop
        return outputs, should_stop

    def execute_with_parallelism(
        self,
        steps_to_execute: list[StepDefinition],
        context: ExecutionContext,
        run_state: PipelineRunState,
        step_results: dict[str, dict[str, Any]],
        externally_satisfied_dependencies: set[str] | None = None,
    ) -> bool:
        dependencies = build_step_dependency_graph(
            steps_to_execute,
            externally_satisfied_dependencies=externally_satisfied_dependencies,
        )
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
                remaining_after_batch = [
                    name
                    for name in ordered_names
                    if name not in executed and name not in {s.name for s in batch}
                ]
                is_last_batch = len(remaining_after_batch) == 0
                outputs, batch_should_stop = self.execute_step_batch(
                    batch, context, run_state, is_last_batch=is_last_batch
                )
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
