# HordeForge Practical Architecture Task Plan (No Extra Layers)

Этот план обновлен под принцип: без внешних адаптеров и без новых абстракций поверх текущего runtime.
Работаем внутри существующих модулей `orchestrator`, `storage`, `scheduler`, `agents`, `rag`.

## Task 1: Checkpointed Step Execution and Resume
### 1. Название
Checkpointed execution на уровне step

### 2. Цель
После каждого шага сохранять `context snapshot + step cursor + retry metadata`.
При падении/рестарте продолжать run с последнего успешного шага, а не стартовать с нуля.

### 3. BDD
```gherkin
Feature: Resume pipeline from last successful step
  Scenario: Process restart during step N
    Given pipeline run has completed steps 1..N-1
    And step N failed because process crashed
    When orchestrator restarts the same run
    Then orchestrator resumes from step N
    And steps 1..N-1 are not re-executed

  Scenario: Retry metadata is preserved
    Given step failed twice before restart
    When run is resumed
    Then retry counter for this step equals 2
    And retry policy continues from preserved state
```

### 4. TDD
- Добавить unit-тесты сериализации/десериализации checkpoint state.
- Добавить интеграционный тест: kill/restart процесса и resume без повторного прогона уже успешных шагов.
- Добавить тест на корректное восстановление retry metadata.

### 5. Изменяемые файлы
- `orchestrator/state.py`
- `orchestrator/engine.py`
- `storage/repositories/run_repository.py`
- `storage/repositories/step_log_repository.py`
- `tests/unit/orchestrator/test_orchestrator_state.py`
- `tests/unit/orchestrator/test_orchestrator_engine.py`

### 6. Новые файлы (если требуется)
- `tests/integration/test_pipeline_resume_from_checkpoint.py`


## Task 2: Explicit Typed PipelineState
### 1. Название
Explicit state model вместо свободного `context dict`

### 2. Цель
Ввести typed `PipelineState` (pydantic/dataclass) с полями:
`run_id`, `current_step`, `artifacts`, `pending_steps`, `failed_steps`, `locks`, `retry_state`.
Снизить скрытые зависимости и упростить resume/replay.

### 3. BDD
```gherkin
Feature: Typed pipeline state boundaries
  Scenario: Step receives valid state
    Given orchestrator loads PipelineState
    When step execution starts
    Then state is validated against schema
    And step receives only declared fields

  Scenario: Corrupted state payload
    Given persisted state misses required field current_step
    When orchestrator loads state
    Then run is marked FAILED with validation reason
    And no step execution is started
```

### 4. TDD
- Написать unit-тесты валидации `PipelineState` (valid/invalid/partial payload).
- Обновить тесты orchestrator на работу через typed state вместо произвольного dict.
- Добавить test на обратную совместимость (legacy context -> typed state adapter внутри orchestrator/context).

### 5. Изменяемые файлы
- `orchestrator/context.py`
- `orchestrator/validation.py`
- `orchestrator/engine.py`
- `tests/unit/orchestrator/test_orchestrator_context.py`
- `tests/unit/orchestrator/test_orchestrator_executor.py`

### 6. Новые файлы (если требуется)
- `contracts/schemas/pipeline_state.v1.schema.json`
- `orchestrator/pipeline_state.py`
- `tests/unit/orchestrator/test_pipeline_state_schema.py`


## Task 3: Durable Memory Tiers in Runtime
### 1. Название
Durable memory tiers (short-term/long-term) как часть runtime

### 2. Цель
Явно разделить:
- short-term memory: память текущего run в state snapshot;
- long-term memory: persist между run (через текущий memory/RAG слой).
Добавить bridge policy: что и когда переносится из short-term в long-term.

### 3. BDD
```gherkin
Feature: Runtime memory promotion policy
  Scenario: Successful run promotes memory
    Given run completed with SUCCESS
    And promotion policy allows this artifact type
    When finalize hook runs
    Then selected short-term artifacts are persisted to long-term memory

  Scenario: Failed run does not pollute long-term memory
    Given run completed with FAILED
    When finalize hook runs
    Then no unstable artifacts are promoted
    And long-term memory remains unchanged
```

### 4. TDD
- Добавить unit-тесты policy: promote/skip по status и artifact type.
- Добавить тесты на hooks: short-term snapshot используется в run, long-term запись только по policy.
- Добавить regression-test: fallback/ошибочные патчи не пишутся в long-term.

### 5. Изменяемые файлы
- `agents/memory_agent.py`
- `rag/memory_store.py`
- `orchestrator/hooks.py`
- `tests/unit/rag/test_memory_collections.py`
- `tests/unit/agents/test_memory_agent.py`
- `tests/unit/orchestrator/test_memory_hooks.py`

### 6. Новые файлы (если требуется)
- `orchestrator/memory_policy.py`
- `tests/unit/orchestrator/test_memory_policy.py`


## Task 4: Idempotent Step Replay
### 1. Название
Idempotent step replay с `step_input_hash`

### 2. Цель
Сделать шаги переигрываемыми: одинаковый step input должен давать тот же artifact identity.
При resume пропускать шаги, которые уже успешно выполнены для того же `step_input_hash`.

### 3. BDD
```gherkin
Feature: Deterministic step replay
  Scenario: Resume with unchanged step input
    Given step X already succeeded with input hash H
    When run resumes and step X input hash is H
    Then executor skips step X
    And reuses persisted artifacts from previous successful execution

  Scenario: Resume with changed step input
    Given step X succeeded with hash H1
    When run resumes and step X input hash is H2
    Then step X is executed again
    And new artifacts are persisted with hash H2
```

### 4. TDD
- Добавить unit-тесты расчета и сравнения `step_input_hash`.
- Добавить unit-тесты executor на skip/replay поведение.
- Добавить integration test через gateway: duplicate run с тем же input не переисполняет уже подтвержденные шаги.

### 5. Изменяемые файлы
- `orchestrator/executor.py`
- `scheduler/idempotency.py`
- `storage/models.py`
- `storage/repositories/step_log_repository.py`
- `tests/unit/orchestrator/test_orchestrator_executor.py`
- `tests/unit/scheduler/test_idempotency.py`
- `tests/unit/storage/test_storage_repositories.py`

### 6. Новые файлы (если требуется)
- `tests/integration/test_step_replay_idempotency.py`


## Execution Order (Recommended)
1. Task 2 (typed state)
2. Task 1 (checkpoint/resume)
3. Task 4 (idempotent replay)
4. Task 3 (memory tiers + promotion policy)

Причина порядка:
- Сначала фиксируем модель состояния.
- Затем строим checkpoint/resume на стабильной модели.
- Потом добавляем skip/replay механику по hash.
- В конце включаем memory promotion policy, уже опираясь на устойчивый runtime state.
