# External Coding Runtime Integration Design

Обновлено: 2026-04-12

## 1. Цель

Спроектировать интеграцию внешнего coding runtime в HordeForge так, чтобы:

1. получить стабильный путь `CI incident / issue -> patch -> tests -> valid PR`;
2. не переписывать HordeForge целиком;
3. сохранить уже работающие deterministic-компоненты;
4. снизить стоимость и сложность собственного execution core;
5. подготовить основу для подключения OpenClaw и/или Qwen Code ACP без разрыва текущей архитектуры.

Ключевая практическая цель на первом этапе:

- `valid PR opened` должен стать основным критерием успеха для repair/feature pipeline;
- merge остаётся отдельным, отключённым или операторским шагом.

---

## 2. Контекст и ограничения

### 2.1 Что уже работает и представляет ценность

В HordeForge уже есть сильный deterministic backbone:

- pipeline orchestration и loop control;
- structured contracts и schema validation;
- GitHub client и PR publish path;
- patch materialization и isolated workspace apply;
- test execution;
- CI incident triage / issue handoff;
- secret store и Qwen OAuth/token-refresh;
- RAG/repository grounding.

Это не нужно переносить в OpenClaw. Это и есть основной актив проекта.

### 2.2 Что вызывает наибольшие проблемы

Наиболее проблемная часть текущей системы — собственный execution/runtime слой для coding turns:

- `agents/code_generator.py`
- `agents/fix_agent.py`
- `agents/review_agent.py`
- `agents/llm_wrapper.py`
- связанные fallback-ветки и runtime-эвристики

Именно этот слой сейчас совмещает:

- prompt assembly;
- provider routing;
- tool calling;
- patch synthesis;
- schema repair;
- fallback generation;
- частично GitHub apply/publish.

Это делает слой слишком большим и слишком дорогим в поддержке.

### 2.3 Жёсткие ограничения

- Нельзя делать ставку на дорогой closed runtime как единственный путь.
- Нужно сохранить работу в Docker-контуре.
- Qwen Code остаётся важным базовым провайдером.
- E2E live-сценарии можно отложить до стабилизации основного pipeline, но архитектура должна их предусматривать.

---

## 3. Архитектурный вывод

### 3.1 Что не нужно делать

Не рекомендуется:

1. Переписывать HordeForge целиком в OpenClaw.
2. Переносить pipeline orchestration внутрь OpenClaw.
3. Дублировать GitHub / patch apply / test runner в двух системах.
4. Строить ещё один собственный mini-Cline/mini-Codex поверх `llm_wrapper.py`.

### 3.2 Что рекомендуется делать

Рекомендуется:

1. Оставить HordeForge как deterministic control plane.
2. Выделить внешний `coding runtime` как заменяемый execution слой.
3. Подключить runtime через адаптеры:
   - `Qwen ACP` как первый практический backend;
   - `OpenClaw Gateway Runtime` как следующий backend для multi-provider/fallback.
4. Оставить apply/test/PR строго внутри HordeForge.

Итоговая граница ответственности:

- HordeForge: orchestration, grounding, apply, tests, PR, CI triage, secrets.
- External runtime: planning/reasoning/tool-driven code synthesis/review.

---

## 4. Варианты интеграции

### 4.1 Вариант A — Qwen Code ACP backend

Схема:

- HordeForge -> adapter -> Qwen Code process / ACP transport -> patch result

Плюсы:

- минимальный migration cost;
- напрямую использует текущий основной движок;
- лучше всего подходит для быстрого получения первого рабочего PR path;
- не требует принятия всей экосистемы OpenClaw.

Минусы:

- слабее по model routing и fallback orchestration;
- меньше зрелых runtime-паттернов вокруг gateway/plugin/runtime isolation;
- может потребовать больше glue-кода со стороны HordeForge.

Оценка:

- effort: `M`
- риск: `Medium`
- time-to-first-valid-PR: лучший

### 4.2 Вариант B — OpenClaw runtime/gateway adapter

Схема:

- HordeForge -> adapter -> OpenClaw gateway/runtime -> selected model backend -> patch/review result

Плюсы:

- зрелый provider/model routing;
- сильный fallback/failover слой;
- гибкий runtime/tool/plugin контур;
- удобная база для дальнейшего multi-model evolution.

Минусы:

- выше интеграционная сложность;
- есть риск утянуть в систему слишком много OpenClaw-слоёв, не относящихся к основной цели;
- потребуется чётко ограничить роль OpenClaw только coding runtime-ом.

Оценка:

- effort: `L`
- риск: `Medium-High`
- time-to-first-valid-PR: хуже, чем у Qwen ACP, но лучше в долгую

### 4.3 Вариант C — Полный переход в OpenClaw

Не рекомендуется.

Причины:

- потеря deterministic pipeline-first модели;
- дублирование уже написанных модулей HordeForge;
- высокий migration cost;
- размывание основной цели `получить валидный PR`.

Оценка:

- effort: `XL`
- риск: `High`
- бизнес-ценность на текущем этапе: низкая

### 4.4 Рекомендация

Рекомендуемый порядок:

1. ввести абстракцию `CodingRuntime`;
2. первым backend сделать `Qwen ACP`;
3. вторым backend добавить `OpenClawRuntime`;
4. переключение backend сделать конфигурационным.

Это даёт быстрый путь к результату без тупика по архитектуре.

---

## 5. Целевая архитектура

### 5.1 Логическая схема

```text
HordeForge Pipeline / Orchestrator
  -> CI / Issue grounding
  -> Context packaging
  -> CodingRuntime adapter
      -> Qwen ACP backend OR OpenClaw backend
  -> Patch normalization + gates
  -> Patch apply to isolated workspace
  -> Test runner
  -> Review decision normalization
  -> GitHub PR publish
```

### 5.2 Новые слои

#### Layer 1. Deterministic Control Plane

Остаётся в HordeForge:

- `orchestrator/*`
- `pipelines/*`
- `registry/*`
- `contracts/*`

#### Layer 2. Grounding & Context Packaging

Остаётся в HordeForge:

- `ci_failure_analyzer`
- `rag_initializer`
- `context_utils`
- selected memory/repo context assembly

#### Layer 3. External Coding Runtime

Новый слой-граница:

- `runtime/contracts.py`
- `runtime/base.py`
- `runtime/selector.py`
- `runtime/request_builder.py`
- `runtime/patch_normalizer.py`
- `runtime/adapters/qwen_acp.py`
- `runtime/adapters/openclaw_gateway.py`
- `runtime/adapters/local_legacy.py`

#### Layer 4. Patch Validation and Materialization

Остаётся в HordeForge:

- `patch_apply_agent`
- `patch_workflow.py`
- `patch_workflow_orchestrator.resolve_code_patch_files()`
- semantic/quality gates

#### Layer 5. Verification and Delivery

Остаётся в HordeForge:

- `test_runner`
- `review_agent` decision normalization
- `github_client`
- `pr_merge_agent`

---

## 6. Предлагаемый интерфейс интеграции

### 6.1 Базовый контракт

```python
from dataclasses import dataclass, field
from typing import Any, Literal

RuntimeMode = Literal["plan", "code", "review"]


@dataclass
class RuntimeRequest:
    mode: RuntimeMode
    task_id: str
    repository_path: str
    issue_context: str
    failure_context: dict[str, Any]
    target_files: list[str]
    snippets: list[dict[str, Any]]
    constraints: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimePatchCandidate:
    patch_text: str | None = None
    operations: list[dict[str, Any]] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    raw_response: str | None = None
    backend: str = ""
    model: str | None = None


@dataclass
class RuntimeReviewResult:
    decision: str
    summary: str
    findings: list[dict[str, Any]]
    recommendations: list[str]
    backend: str = ""
    model: str | None = None
```

### 6.2 Базовый runtime интерфейс

```python
class CodingRuntime(Protocol):
    def plan(self, request: RuntimeRequest) -> dict[str, Any]: ...
    def generate_patch(self, request: RuntimeRequest) -> RuntimePatchCandidate: ...
    def review_patch(
        self,
        request: RuntimeRequest,
        patch: dict[str, Any],
    ) -> RuntimeReviewResult: ...
```

### 6.3 Важный принцип

Runtime не должен:

- публиковать PR;
- применять патчи к repo напрямую внутри HordeForge runtime path;
- запускать тесты как источник истины для pipeline;
- читать секреты GitHub напрямую;
- владеть loop-логикой.

Runtime только:

- получает grounding;
- строит candidate output;
- возвращает результат в нормализованном контракте.

---

## 7. Детализация backend-адаптеров

### 7.1 `LocalLegacyRuntime`

Назначение:

- переходный адаптер поверх текущего `llm_wrapper.py` и существующих prompt paths.

Нужен для:

- безопасного выделения seam без немедленного переписывания всей системы;
- сравнения output нового runtime и текущего legacy behavior.

Оценка:

- effort: `S`
- обязательность: `High`

### 7.2 `QwenAcpRuntime`

Назначение:

- первый целевой backend.

Режим:

- HordeForge запускает/подключается к Qwen Code ACP runtime;
- передаёт подготовленный request;
- получает tool-driven result;
- нормализует в `RuntimePatchCandidate`.

Что особенно важно:

- не требовать от Qwen владения GitHub/PR flow;
- использовать ACP/transport только для coding turns;
- не дублировать sandbox HordeForge.

Оценка:

- effort: `M`
- обязательность: `High`

### 7.3 `OpenClawRuntime`

Назначение:

- второй backend для multi-provider routing, fallback chain и более зрелого runtime surface.

Режим:

- OpenClaw запускается как sidecar/gateway;
- HordeForge обращается к нему как к coding-runtime service;
- OpenClaw сам выбирает backend/model/fallback;
- HordeForge получает уже нормализованный coding output.

Предпочтительный способ интеграции:

- sidecar/gateway adapter;
- не plugin-перенос всего HordeForge в OpenClaw.

Оценка:

- effort: `L`
- обязательность: `Medium`

---

## 8. Разбор текущих модулей HordeForge

### 8.1 Оставить без смены ответственности

| Модуль | Роль | Решение | Причина | Оценка |
|---|---|---|---|---|
| `orchestrator/engine.py` | основной pipeline engine | оставить | это control plane | `Keep` |
| `orchestrator/executor.py` | step execution + contracts | оставить | нужен независимо от runtime | `Keep` |
| `orchestrator/context.py` | execution context | оставить | core state model | `Keep` |
| `pipelines/ci_scanner_pipeline.yaml` | CI handoff pipeline | оставить | deterministic triage | `Keep` |
| `pipelines/ci_fix_pipeline.yaml` | repair pipeline | оставить | основной путь к PR | `Keep` |
| `agents/ci_failure_analyzer.py` | извлечение structured CI context | оставить | сильный grounded input | `Keep` |
| `agents/patch_apply_agent.py` | isolated workspace prep | оставить | важный deterministic execution seam | `Keep` |
| `agents/test_runner.py` | verification source of truth | оставить | не должен жить во внешнем runtime | `Keep` |
| `agents/github_client.py` | GitHub API | оставить | продуктовая интеграция HordeForge | `Keep` |
| `agents/patch_workflow.py` | publish patch to branch/PR | оставить | реальный PR path | `Keep` |
| `agents/rag_initializer.py` | repository indexing / retrieval bootstrap | оставить | grounded coding context | `Keep` |
| `cli/repo_store.py` | secret/token refs | оставить | локальный operational asset | `Keep` |
| `cli/horde_cli.py` | operator/CLI surface | оставить | внешний control surface | `Keep` |

### 8.2 Оставить, но адаптировать под новый seam

| Модуль | Текущее состояние | Решение | Что менять | Оценка |
|---|---|---|---|---|
| `agents/code_generator.py` | слишком большой runtime + grounding + publish | адаптировать | вынести runtime call в adapter; убрать synthetic runtime fallback | `L` |
| `agents/fix_agent.py` | завязан на `EnhancedCodeGenerator` как внутренний runtime | адаптировать | перевести на `CodingRuntime.generate_patch()` | `M` |
| `agents/review_agent.py` | локальный review runtime + normalization | адаптировать | вынести LLM-review во внешний runtime, оставить policy normalization | `M` |
| `agents/llm_wrapper.py` | provider routing + profile fallback + vendor logic | адаптировать/сжать | оставить как legacy adapter или service for local mode only | `L` |
| `agents/llm_api.py` | router abstraction | адаптировать | либо использовать только в `LocalLegacyRuntime`, либо заморозить | `M` |
| `agents/llm_providers.py` | provider-specific wrappers | адаптировать | сохранить как legacy compatibility layer | `M` |
| `agents/pr_merge_agent.py` | смешивает PR-opened и merge-success semantics | адаптировать | `PR opened => SUCCESS`, merge flag отдельно | `S` |

### 8.3 Оставить только как внутренний utility / legacy support

| Модуль | Решение | Причина | Оценка |
|---|---|---|---|
| `agents/patch_workflow_orchestrator.py` | сократить до materialization utilities | runtime-simulation path не должен выглядеть как production logic | `M` |
| `agents/pipeline_runner.py` | оставить как dev/minimal runner | не основной orchestration path | `S` |
| `agents/memory_agent.py` | оставить вне critical PR path | не нужен для первого валидного PR | `S` |

### 8.4 Убрать из runtime critical path

| Элемент | Где | Решение | Причина | Оценка |
|---|---|---|---|---|
| synthetic fallback file `src/feature_impl.py` | `code_generator.py`, `fix_agent.py` | убрать из runtime | создаёт ложный прогресс | `S` |
| simulated apply logic | `patch_workflow_orchestrator.py` | вынести в test fakes | production/module boundary размыта | `M` |
| analysis-only / placeholder fallback branches | `code_generator.py` | жёстко fail в runtime | pipeline должен получать честный failure | `M` |

### 8.5 Не переносить в OpenClaw

Не переносить во внешний runtime:

- `ci_failure_analyzer`
- `patch_apply_agent`
- `test_runner`
- `github_client`
- `patch_workflow`
- `pr_merge_agent`
- `rag_initializer`
- секреты GitHub / repo mapping

Причина:

- это deterministic infrastructure HordeForge, а не model runtime.

---

## 9. Детализация по функциональности

### 9.1 Repository sandbox / workspace init

Статус:

- уже есть хорошая база в `patch_apply_agent`.

Решение:

- оставить в HordeForge;
- внешний runtime получает только repo path и curated snippets;
- внешний runtime не должен владеть isolated workspace lifecycle.

### 9.2 RAG / grounding

Статус:

- already useful and differentiating.

Решение:

- оставить в HordeForge;
- перед runtime отправлять только selected snippets / target files / failure context;
- не пытаться заставить OpenClaw переиндексировать весь repo для каждого run.

### 9.3 CI scanning / incident triage

Статус:

- сильный preprocessing layer.

Решение:

- полностью оставить в HordeForge;
- runtime должен получать уже нормализованный `ci_failure_context`.

### 9.4 Model/provider auth and token rotation

Статус:

- в HordeForge уже есть secret refs и Qwen OAuth handling.

Решение:

- на первом этапе оставить auth management в HordeForge;
- runtime adapter получает уже разрешённые credentials/config;
- при OpenClaw integration можно позже вынести часть auth к runtime-gateway, но не в первом этапе.

### 9.5 Patch generation

Статус:

- главный кандидат на вынос.

Решение:

- внешнему runtime отдать только reasoning + tool-driven patch synthesis;
- materialization и validation оставить в HordeForge.

### 9.6 Review

Статус:

- review сейчас наполовину runtime, наполовину policy normalizer.

Решение:

- review synthesis можно вынести в runtime;
- policy checks, verification validity, CI grounding mismatch оставить в HordeForge.

### 9.7 PR publishing

Статус:

- нужно сохранить локально.

Решение:

- publish branch/PR только через HordeForge;
- runtime не должен создавать PR напрямую.

---

## 10. Предлагаемая структура новых модулей

```text
src_or_agents_runtime/
  contracts.py
  base.py
  selector.py
  request_builder.py
  patch_normalizer.py
  review_normalizer.py
  adapters/
    legacy_local.py
    qwen_acp.py
    openclaw_gateway.py
  testing/
    fake_runtime.py
```

### Назначение

- `contracts.py`: dataclasses / pydantic schemas
- `base.py`: `CodingRuntime` protocol
- `selector.py`: runtime selection by config/profile
- `request_builder.py`: перевод HordeForge context -> runtime request
- `patch_normalizer.py`: runtime output -> HordeForge patch schema
- `review_normalizer.py`: runtime review -> HordeForge review_result schema
- `legacy_local.py`: bridge to existing `llm_wrapper`
- `qwen_acp.py`: direct Qwen ACP backend
- `openclaw_gateway.py`: OpenClaw sidecar/gateway backend
- `fake_runtime.py`: test fixture backend

---

## 11. Контур миграции pipeline

### Phase 0 — Cleanup before integration

Обязательно сделать до подключения внешнего runtime:

1. `PR opened => SUCCESS`
2. убрать `src/feature_impl.py` fallback из runtime path
3. вынести simulated apply из production-looking модуля
4. оставить legacy runtime как baseline adapter

Оценка:

- effort: `S-M`

### Phase 1 — Introduce `CodingRuntime` seam

Шаги:

1. добавить runtime contracts + interface
2. обернуть текущий `llm_wrapper` в `LocalLegacyRuntime`
3. перевести `code_generator` на runtime adapter
4. перевести `fix_agent` на runtime adapter
5. минимально перевести `review_agent`

Оценка:

- effort: `M-L`

### Phase 2 — Add `QwenAcpRuntime`

Шаги:

1. реализовать ACP adapter
2. добавить config selection
3. нормализовать patch output
4. сравнить с legacy runtime на replay dataset

Оценка:

- effort: `M`

### Phase 3 — Add `OpenClawRuntime`

Шаги:

1. поднять sidecar/gateway integration contract
2. подключить runtime auth/config
3. добавить model/fallback policy
4. использовать для selected runs / shadow mode

Оценка:

- effort: `L`

### Phase 4 — Runtime selection policy

Пример:

- default: `qwen_acp`
- fallback: `openclaw`
- emergency fallback: `legacy_local`

---

## 12. Тестовая стратегия после рефакторинга

### 12.1 Что мокать

Нужно мокать через фикстуры/adapter fakes, а не через simulated ветки внутри production-классов:

- внешний runtime (`fake_runtime.py`)
- GitHub network
- ACP transport / gateway transport

### 12.2 Что не мокать

Не нужно мокать:

- patch normalization
- `resolve_code_patch_files`
- `patch_apply_agent`
- quality/semantic gates
- pipeline loop decisions

### 12.3 Рекомендуемые уровни тестов

1. Unit:
   - runtime adapter output normalization
   - request builder
   - review normalization
2. Integration:
   - pipeline + fake runtime + real patch materialization
   - pipeline + fake runtime + real isolated workspace
3. Optional live:
   - sandbox repo + real runtime + valid PR opened

---

## 13. Оценка стоимости и приоритетов

| Направление | Value | Cost | Priority |
|---|---|---|---|
| `PR opened => SUCCESS` semantics | very high | low | `P0` |
| убрать runtime synthetic fallbacks | very high | low | `P0` |
| runtime seam (`CodingRuntime`) | very high | medium | `P0` |
| `QwenAcpRuntime` | very high | medium | `P1` |
| `OpenClawRuntime` | high | high | `P2` |
| перенос memory/RAG в OpenClaw | low | high | `No` |
| перенос GitHub/test/apply в OpenClaw | low | high | `No` |

---

## 14. Итоговая рекомендация

### Короткий вывод

Лучший дизайн для текущего этапа:

- HordeForge остаётся orchestrator/control plane.
- Внешний runtime вводится как заменяемый слой.
- Первый backend: `Qwen ACP`.
- Второй backend: `OpenClaw gateway runtime`.
- GitHub/apply/tests/RAG/CI triage остаются внутри HordeForge.

### Почему это лучше полного перехода в OpenClaw

Потому что проекту сейчас нужен не новый assistant platform, а:

- предсказуемый grounded patch path;
- стабильный valid PR;
- дешёвая и контролируемая миграция.

### Что считать успешным завершением Phase 1

1. `code_generator` больше не знает о provider-specific runtime internals.
2. `fix_agent` не импортирует `EnhancedCodeGenerator` как внутренний runtime.
3. synthetic fallback patch generation убран из production path.
4. pipeline получает `SUCCESS` при создании валидного PR.
5. backend переключается конфигурацией, а не переписыванием агентов.

---

## 15. Решение к принятию

### Recommended decision

Принять architecture decision:

`HordeForge keeps deterministic orchestration; external coding runtime becomes a pluggable execution backend.`

### Immediate next implementation step

Начать не с OpenClaw, а с runtime seam + `LocalLegacyRuntime`, затем добавить `QwenAcpRuntime`.

Это минимизирует риск и создаёт правильную архитектурную границу для последующего подключения OpenClaw.
