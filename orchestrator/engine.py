from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from threading import RLock
from typing import Any
from uuid import uuid4

from hordeforge_utils import resolve_path
from logging_utils import redact_mapping
from orchestrator import checkpointing
from orchestrator.context import ExecutionContext
from orchestrator.executor import StepExecutor
from orchestrator.hooks import (
    BasicExecutionGuardrailHook,
    ExecutionGuardrailHook,
    MemoryHook,
    trigger_memory_hook,
    trigger_memory_promotion,
)
from orchestrator.loader import PipelineDefinition, PipelineLoader, StepDefinition
from orchestrator.loop_eval import evaluate_loop_condition
from orchestrator.pipeline_runner import (
    POLICY_ACTIONS,  # noqa: F401
    PipelineRunner,
)
from orchestrator.pipeline_state import PipelineState
from orchestrator.pipeline_status import PipelineStatus
from orchestrator.pipeline_validator import PipelineValidationError, PipelineValidator
from orchestrator.retry import RetryPolicy
from orchestrator.state import PipelineRunState
from orchestrator.status import StepStatus
from orchestrator.summary import RunSummaryBuilder
from orchestrator.validation import RuntimeSchemaValidator, SchemaValidationError
from registry.bootstrap import init_registries
from registry.runtime_adapter import RuntimeRegistryAdapter
from rules.loader import DEFAULT_RULE_SET_VERSION, RulePackLoader


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
        validate_pipeline_schema: bool = False,
        contracts_dir: str = "contracts/schemas",
        use_registry_bootstrap: bool = True,
        allow_pipeline_fallback: bool = True,
        execution_guardrail_hook: ExecutionGuardrailHook | None = None,
        deps: Any = None,
    ):
        if deps is not None:
            from orchestrator.container import OrchestratorDependencies

            if not isinstance(deps, OrchestratorDependencies):
                raise TypeError(f"deps must be OrchestratorDependencies, got {type(deps).__name__}")
            self.pipeline_loader = deps.pipeline_loader or PipelineLoader(
                pipelines_dir=pipelines_dir
            )
            self.step_executor = deps.step_executor or StepExecutor()
            self.retry_policy = deps.retry_policy or RetryPolicy(retry_limit=0, backoff_seconds=0.0)
            self.execution_guardrail_hook = (
                deps.execution_guardrail_hook or BasicExecutionGuardrailHook()
            )
            self.summary_builder = deps.summary_builder or RunSummaryBuilder()
            self.rule_pack_loader = deps.rule_pack_loader
            self.validate_pipeline_schema = deps.pipeline_validator is not None
            self._pipeline_validator = deps.pipeline_validator
            self._state_validator = deps.state_validator or RuntimeSchemaValidator()
            self.logger = deps.logger or logging.getLogger("hordeforge.orchestrator.engine")
            self._checkpoint_lock = deps.checkpoint_lock
            self.max_loop_iterations = max_loop_iterations
            self.max_parallel_workers = max(1, int(max_parallel_workers))
        else:
            registry_bundle: dict[str, Any] | None = None
            runtime_registry: RuntimeRegistryAdapter | None = None
            if use_registry_bootstrap:
                registry_bundle = init_registries(
                    contracts_dir=contracts_dir,
                    pipelines_dir=pipelines_dir,
                )
                runtime_registry = RuntimeRegistryAdapter(registry_bundle["agent_registry"])

            if pipeline_loader is None:
                if registry_bundle is not None:
                    self.pipeline_loader = PipelineLoader(
                        pipelines_dir=pipelines_dir,
                        pipeline_registry=registry_bundle["pipeline_registry"],
                        allow_fallback=allow_pipeline_fallback,
                    )
                else:
                    self.pipeline_loader = PipelineLoader(pipelines_dir=pipelines_dir)
            else:
                self.pipeline_loader = pipeline_loader

            if step_executor is None:
                if runtime_registry is not None:
                    self.step_executor = StepExecutor(
                        agent_registry=runtime_registry,
                        strict_schema_validation=strict_schema_validation,
                    )
                else:
                    self.step_executor = StepExecutor(
                        strict_schema_validation=strict_schema_validation,
                    )
            else:
                self.step_executor = step_executor
            self.retry_policy = retry_policy or RetryPolicy(retry_limit=0, backoff_seconds=0.0)
            self.execution_guardrail_hook = (
                execution_guardrail_hook or BasicExecutionGuardrailHook()
            )
            self.summary_builder = summary_builder or RunSummaryBuilder()
            self.max_loop_iterations = max_loop_iterations
            self.max_parallel_workers = max(1, int(max_parallel_workers))
            self.rule_pack_loader = rule_pack_loader or RulePackLoader(
                rules_dir=rules_dir,
                rule_set_version=rule_set_version,
            )
            self.validate_pipeline_schema = validate_pipeline_schema
            if validate_pipeline_schema:
                if runtime_registry is not None:
                    self._pipeline_validator = PipelineValidator(agent_registry=runtime_registry)
                else:
                    self._pipeline_validator = PipelineValidator()
            else:
                self._pipeline_validator = None
            self._state_validator = RuntimeSchemaValidator(
                strict_mode=strict_schema_validation,
            )
            self.logger = logging.getLogger("hordeforge.orchestrator.engine")
            self._checkpoint_lock = RLock()

        self._runner = PipelineRunner(
            step_executor=self.step_executor,
            retry_policy=self.retry_policy,
            execution_guardrail_hook=self.execution_guardrail_hook,
            max_loop_iterations=self.max_loop_iterations,
            max_parallel_workers=self.max_parallel_workers,
            checkpoint_lock=self._checkpoint_lock,
            state_validator=self._state_validator,
            logger=self.logger,
        )

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name == "step_executor" and hasattr(self, "_runner"):
            self._runner.step_executor = value

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
    def _resolve_path(source: dict[str, Any], dotted_path: str) -> Any:
        return resolve_path(source, dotted_path)

    @staticmethod
    def _evaluate_loop_condition(condition: str, state: dict[str, Any]) -> bool:
        return evaluate_loop_condition(condition, state)

    @staticmethod
    def _derive_trace_id(correlation_id: str, run_id: str) -> str:
        seed = f"{correlation_id}:{run_id}"
        return sha256(seed.encode("utf-8")).hexdigest()[:32]

    def _load_rules_payload(self) -> dict[str, Any]:
        return deepcopy(self.rule_pack_loader.load())

    @staticmethod
    def _derive_final_status(
        run_state: PipelineRunState,
        step_results: dict[str, dict[str, Any]],
    ) -> str:
        if run_state.run_status in {StepStatus.FAILED.value, StepStatus.BLOCKED.value}:
            return run_state.run_status
        has_pr_merge_step = any(step.name == "pr_merge_agent" for step in run_state.steps)
        if has_pr_merge_step:
            pr_merge_output = step_results.get("pr_merge_agent")
            pr_merge_status = (
                str(pr_merge_output.get("status") or "").strip().upper()
                if isinstance(pr_merge_output, dict)
                else ""
            )
            if pr_merge_status not in {"SUCCESS", "PARTIAL_SUCCESS"}:
                return StepStatus.PARTIAL_SUCCESS.value
        if any(output.get("status") == "PARTIAL_SUCCESS" for output in step_results.values()):
            return "PARTIAL_SUCCESS"
        return StepStatus.SUCCESS.value

    def _setup_run_context(
        self,
        run_id: str,
        pipeline: PipelineDefinition,
        inputs: dict[str, Any] | None,
        metadata: dict[str, Any] | None,
        resumed_state_payload: dict[str, Any] | None,
    ) -> tuple[ExecutionContext, str, str, str]:
        raw_metadata = dict(metadata or {})
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
            or self._derive_trace_id(correlation_id, run_id)
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
        context.set_state_value(MemoryHook.PROMOTION_MODE_KEY, "deferred")
        return context, correlation_id, trace_id, root_span_id

    def _setup_resume_state(
        self,
        run_id: str,
        pipeline: PipelineDefinition,
        context: ExecutionContext,
        resumed_state_payload: dict[str, Any] | None,
        resumed_step_results_payload: dict[str, dict[str, Any]],
        correlation_id: str,
        trace_id: str,
    ) -> tuple[PipelineRunState, dict[str, dict[str, Any]], int]:
        resume_pipeline_state_payload = (
            resumed_state_payload.get("pipeline_state")
            if isinstance(resumed_state_payload, dict)
            else None
        )
        if resume_pipeline_state_payload is not None:
            if not isinstance(resume_pipeline_state_payload, dict):
                raise ValueError("Resume pipeline_state payload must be an object")
            try:
                errors = self._state_validator.validate_pipeline_state(
                    resume_pipeline_state_payload
                )
            except SchemaValidationError as exc:
                raise ValueError(f"Invalid resume pipeline_state payload: {exc}") from exc
            if errors:
                raise ValueError("Invalid resume pipeline_state payload: " + "; ".join(errors))
            context.pipeline_state = PipelineState.model_validate(resume_pipeline_state_payload)

        if resumed_state_payload is None:
            run_state = PipelineRunState.from_steps(
                run_id=run_id,
                pipeline_name=pipeline.pipeline_name,
                steps=[(step.name, step.agent) for step in pipeline.steps],
                correlation_id=correlation_id,
                trace_id=trace_id,
            )
            run_state.transition_pipeline(PipelineStatus.VALIDATING)
            return run_state, {}, 0

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
        return run_state, step_results, start_step_index

    def _execute_resumed_steps(
        self,
        run_id: str,
        pipeline: PipelineDefinition,
        steps_to_execute: list[StepDefinition],
        start_step_index: int,
        context: ExecutionContext,
        run_state: PipelineRunState,
        step_results: dict[str, dict[str, Any]],
        correlation_id: str,
    ) -> bool:
        should_stop = False
        for idx, step in enumerate(steps_to_execute):
            has_next = idx < len(steps_to_execute) - 1
            absolute_step_index = start_step_index + idx
            try:
                step_state = run_state.get_step(step.name)
            except KeyError:
                step_state = None

            replay_state = dict(context.state)
            for future_step in pipeline.steps[absolute_step_index:]:
                replay_state.pop(future_step.name, None)
            step_input_hash = self.step_executor.calculate_step_input_hash(step, replay_state)
            if (
                step_state is not None
                and step_state.status
                in {
                    StepStatus.SUCCESS,
                    StepStatus.PARTIAL_SUCCESS,
                    StepStatus.SKIPPED,
                }
                and isinstance(step_state.input_hash, str)
                and step_state.input_hash == step_input_hash
                and step.name in context.step_results
            ):
                run_state.current_step_index = max(
                    run_state.current_step_index,
                    absolute_step_index + 1,
                )
                checkpointing.emit_checkpoint(
                    context=context,
                    run_state=run_state,
                    checkpoint_lock=self._checkpoint_lock,
                    state_validator=self._state_validator,
                )
                self._log_event(
                    logging.INFO,
                    run_id,
                    "step_replay_skipped",
                    step_name=step.name,
                    input_hash=step_input_hash,
                    correlation_id=correlation_id,
                )
                continue

            output, should_stop = self._runner.execute_step_with_policy(
                step, context, run_state, has_next_step=has_next
            )
            step_results[step.name] = output
            if should_stop:
                break
            trigger_memory_hook(step.name, output, context.state)
        return should_stop

    def _execute_fresh_steps(
        self,
        pipeline: PipelineDefinition,
        steps_to_execute: list[StepDefinition],
        context: ExecutionContext,
        run_state: PipelineRunState,
        step_results: dict[str, dict[str, Any]],
    ) -> bool:
        executed_step_names: set[str] = set()

        def _trigger_hooks_for_new_steps(step_scope: list[StepDefinition]) -> None:
            nonlocal executed_step_names
            for step in step_scope:
                if step.name in step_results and step.name not in executed_step_names:
                    trigger_memory_hook(step.name, step_results[step.name], context.state)
                    executed_step_names.add(step.name)

        if pipeline.loops:
            loop_step_names = {step_name for loop in pipeline.loops for step_name in loop.steps}
            loop_anchor_names = {
                loop.steps[0]
                for loop in pipeline.loops
                if isinstance(loop.steps, list) and loop.steps
            }
            indexed_steps = list(enumerate(steps_to_execute))
            indexed_loop_anchors = [
                index for index, step in indexed_steps if step.name in loop_anchor_names
            ]

            if indexed_loop_anchors:
                first_loop_index = min(indexed_loop_anchors)
                pre_loop_steps = [step for index, step in indexed_steps if index < first_loop_index]
                post_loop_steps = [
                    step
                    for index, step in indexed_steps
                    if index >= first_loop_index and step.name not in loop_step_names
                ]
            else:
                pre_loop_steps = steps_to_execute
                post_loop_steps = []

            should_stop = self._runner.execute_with_parallelism(
                pre_loop_steps, context, run_state, step_results
            )
            _trigger_hooks_for_new_steps(pre_loop_steps)

            if not should_stop:
                step_by_name = {step.name: step for step in pipeline.steps}
                for loop in pipeline.loops:
                    should_stop = self._runner.execute_loop(
                        loop, step_by_name, context, run_state, step_results
                    )
                    if should_stop:
                        break

            if not should_stop and post_loop_steps:
                should_stop = self._runner.execute_with_parallelism(
                    post_loop_steps,
                    context,
                    run_state,
                    step_results,
                    externally_satisfied_dependencies=set(step_results.keys()),
                )
                _trigger_hooks_for_new_steps(post_loop_steps)
            return should_stop

        should_stop = self._runner.execute_with_parallelism(
            steps_to_execute, context, run_state, step_results
        )
        _trigger_hooks_for_new_steps(steps_to_execute)
        return should_stop

    def _finalize_run(
        self,
        run_id: str,
        pipeline: PipelineDefinition,
        context: ExecutionContext,
        run_state: PipelineRunState,
        step_results: dict[str, dict[str, Any]],
        correlation_id: str,
        trace_id: str,
        root_span_id: str,
    ) -> dict[str, Any]:
        final_status = self._derive_final_status(run_state, step_results)
        run_state.set_run_status(StepStatus(final_status))
        if final_status == StepStatus.SUCCESS.value:
            run_state.transition_pipeline(PipelineStatus.COMPLETED)
        elif final_status == StepStatus.FAILED.value:
            run_state.transition_pipeline(PipelineStatus.FAILED)
        elif final_status == StepStatus.BLOCKED.value:
            run_state.transition_pipeline(PipelineStatus.BLOCKED)
        elif final_status == StepStatus.PARTIAL_SUCCESS.value:
            run_state.transition_pipeline(PipelineStatus.COMPLETED)

        promoted_entries = trigger_memory_promotion(context.state, run_status=final_status)
        if promoted_entries:
            self._log_event(
                logging.INFO,
                run_id,
                "memory_promotion_completed",
                promoted_entries=promoted_entries,
                correlation_id=correlation_id,
            )

        checkpointing.emit_checkpoint(
            context=context,
            run_state=run_state,
            checkpoint_lock=self._checkpoint_lock,
            state_validator=self._state_validator,
            status=final_status,
        )
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
            "state": context.snapshot_state(),
            "summary": summary,
            "run_state": run_state.to_dict(),
            "trace": {
                "correlation_id": correlation_id,
                "trace_id": trace_id,
                "root_span_id": root_span_id,
                "steps": trace_steps,
            },
        }

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

        if self._pipeline_validator is not None:
            try:
                self._pipeline_validator.validate(pipeline)
            except PipelineValidationError as e:
                self.logger.error(f"Pipeline validation failed for '{pipeline_name}': {e}")
                raise

        resumed_state_payload = resume_run_state if isinstance(resume_run_state, dict) else None
        resumed_step_results_payload = (
            resume_step_results if isinstance(resume_step_results, dict) else {}
        )

        context, correlation_id, trace_id, root_span_id = self._setup_run_context(
            run_id, pipeline, inputs, metadata, resumed_state_payload
        )

        run_state, step_results, start_step_index = self._setup_resume_state(
            run_id,
            pipeline,
            context,
            resumed_state_payload,
            resumed_step_results_payload,
            correlation_id,
            trace_id,
        )

        run_state.transition_pipeline(PipelineStatus.RUNNING)
        checkpointing.sync_and_validate_pipeline_state(
            context=context,
            run_state=run_state,
            state_validator=self._state_validator,
        )
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

        if resumed_state_payload is not None:
            should_stop = self._execute_resumed_steps(
                run_id,
                pipeline,
                steps_to_execute,
                start_step_index,
                context,
                run_state,
                step_results,
                correlation_id,
            )
        else:
            should_stop = self._execute_fresh_steps(
                pipeline,
                steps_to_execute,
                context,
                run_state,
                step_results,
            )

        if resumed_state_payload is not None and not should_stop and pipeline.loops:
            step_by_name = {step.name: step for step in pipeline.steps}
            for loop in pipeline.loops:
                should_stop = self._runner.execute_loop(
                    loop, step_by_name, context, run_state, step_results
                )
                if should_stop:
                    break

        return self._finalize_run(
            run_id,
            pipeline,
            context,
            run_state,
            step_results,
            correlation_id,
            trace_id,
            root_span_id,
        )
