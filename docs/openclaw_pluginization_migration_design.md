# HordeForge -> OpenClaw Pluginization Design

Обновлено: 2026-04-13

## 1. Стартовая позиция

Этот документ заменяет предыдущую идею, где центральным seam был `external coding runtime`.

Новая гипотеза такая:

1. HordeForge не надо "встраивать рядом" с OpenClaw.
2. HordeForge надо разложить на OpenClaw-native сущности:
   - plugins
   - model providers / harnesses
   - integrations
   - tools
   - commands
   - hooks
   - skills
   - agent profiles
   - subagents
3. Сначала это должно заработать как детерминированный набор OpenClaw-плагинов.
4. Затем это должно собраться в единый installable add-on для OpenClaw.

Главный критерий успеха не меняется:

- получить `valid PR opened` по стабильному пути `CI/issue -> patch -> tests -> PR`;
- merge остается отдельным шагом и не нужен для первой цели.

## 2. Что важно в архитектуре OpenClaw

По документации OpenClaw нужно опираться на их реальную модель, а не на нашу интерпретацию.

### 2.1 Native plugin, а не bundle

OpenClaw различает:

- `native plugin`: `openclaw.plugin.json` + runtime module, полный capability model;
- `bundle`: Codex/Claude/Cursor-совместимый content pack с ограниченным mapping.

Для HordeForge целевой формат должен быть именно `native plugin`, потому что bundle не дает полноценную регистрацию provider/harness/tool/service/runtime behavior.

Bundle можно сделать позже как совместимый слой для skills/MCP defaults, но не как основной способ интеграции.

### 2.2 Capability model

OpenClaw ожидает, что plugin регистрирует capabilities через явные API:

- `registerProvider(...)`
- `registerCliBackend(...)`
- `registerTool(...)`
- `registerCommand(...)`
- `registerHook(...)`
- `registerCli(...)`
- `registerHttpRoute(...)`
- `registerAgentHarness(...)`

Это значит, что HordeForge должен быть разложен не по нашим старым "агентам", а по OpenClaw surface area.

### 2.3 Provider != Harness != ACP

Это три разные вещи:

- `Provider plugin`: обычный model/provider routing внутри OpenClaw.
- `Agent harness`: низкоуровневый runtime, если модель или coding runtime владеют собственными thread/session semantics.
- `ACP runtime`: внешний coding harness, запускаемый через ACP backend plugin.

Следствие:

- если нужен просто Qwen API, нужен provider или bundled `qwen`;
- если нужен внешний coding runtime с его session/thread semantics, нужен ACP или harness;
- если нужен deterministic pipeline вокруг кода, это не provider и не harness, а tool/service/plugin слой.

### 2.4 Subagents не являются packaging unit

В OpenClaw `subagents` - это runtime-механизм фоновых agent runs, а не единица архитектурной декомпозиции.

Поэтому:

- нельзя проектировать HordeForge как "набор subagents" вместо deterministic pipeline;
- subagents подходят для параллельных побочных задач;
- критический путь до PR на первом этапе не должен зависеть от subagent orchestration.

## 3. Новый тезис миграции

### 3.1 Что должно стать центром системы

Центром должен стать OpenClaw control plane:

- вход пользователя;
- выбор agent profile;
- model/provider/harness selection;
- tool invocation;
- transcript;
- permissions;
- plugin configuration.

### 3.2 Что остается ценным из HordeForge

HordeForge уже имеет полезный deterministic backbone:

- `orchestrator/*`
- `pipelines/*`
- `agents/github_client.py`
- `agents/patch_workflow.py`
- `agents/patch_apply_agent.py`
- `agents/test_runner.py`
- `agents/ci_failure_analyzer.py`
- `agents/ci_incident_handoff.py`
- `agents/rag_initializer.py`
- `cli/repo_store.py`
- текущий secret/token lifecycle

Это не надо выбрасывать. Это надо завернуть в OpenClaw-compatible plugin surfaces.

### 3.3 Что должно перестать быть центром

Текущий собственный coding runtime HordeForge не должен оставаться ядром системы:

- `agents/code_generator.py`
- `agents/fix_agent.py`
- `agents/review_agent.py`
- `agents/llm_wrapper.py`
- `agents/llm_api.py`
- связанные fallback/simulation branches

Этот слой сейчас смешивает:

- prompting
- provider routing
- synthetic patch generation
- partial workflow semantics
- fallback behavior

Именно здесь самый высокий churn и самая слабая предсказуемость.

## 4. Целевая форма: multi-plugin development, single-addon distribution

Лучший компромисс между архитектурой и поставкой:

- в разработке: несколько OpenClaw-native plugin units с четкой ответственностью;
- в поставке: один installable add-on для OpenClaw.

### 4.1 Почему не один огромный plugin сразу

Если сразу собрать все в один plugin, мы получим:

- тот же монолит, только в новой упаковке;
- сложный configSchema;
- смешение GitHub, CI, RAG, coding runtime, secrets и pipeline logic;
- плохую тестируемость и сложный rollout.

### 4.2 Почему не десять независимых пакетов навсегда

Если раздробить слишком сильно, появится:

- высокая стоимость публикации и версионирования;
- сложная совместимость между пакетами;
- больше шансов не собрать end-to-end install flow.

### 4.3 Рекомендуемая топология

На уровне дизайна:

1. `hordeforge-core`
2. `hordeforge-github`
3. `hordeforge-ci`
4. `hordeforge-context`
5. `hordeforge-coding`

На уровне поставки:

- один addon package `@hordeforge/openclaw-addon`, который включает эти capability surfaces и plugin-owned runtime assets.

## 5. Целевые OpenClaw слои

## 5.1 Layer A: OpenClaw Native Shell

Реализация: TypeScript native plugin(s).

Ответственность:

- `openclaw.plugin.json`
- config schema
- plugin discovery/enablement
- OpenClaw commands
- tools registration
- hooks registration
- agent profile wiring
- optional HTTP/gateway routes
- runtime store and health checks

Это слой управления, а не слой тяжелой бизнес-логики.

## 5.2 Layer B: HordeForge Runtime Bridge

Реализация: Python sidecar/process owned by the plugin.

Ответственность:

- вызывать существующий HordeForge deterministic code;
- предоставлять OpenClaw-плагину стабильный RPC boundary;
- инкапсулировать Python-only зависимости;
- избежать полного rewrite в TypeScript на первом этапе.

Это критично. Без этого вы либо:

- перепишете слишком много на TS и застрянете;
- либо сохраните старый HordeForge как отдельный control plane и не достигнете цели.

Рекомендуемый контракт:

- локальный stdio JSON-RPC или loopback HTTP на localhost;
- строгие request/response schemas;
- детерминированные tool-level methods;
- явные health/version/capabilities endpoints.

## 5.3 Layer C: Deterministic Execution Services

Это то, что реально должно выполнять работу:

- repository preparation
- patch materialization
- test execution
- PR publication
- CI scan and handoff
- repo grounding and indexing

Именно этот слой должен остаться максимально детерминированным и проверяемым.

## 5.4 Layer D: OpenClaw Agents

Это уже не HordeForge agents в старом смысле, а OpenClaw agent profiles.

Рекомендуемые профили:

- `hf-ci-fixer`
- `hf-feature-builder`
- `hf-pr-reviewer`
- `hf-ops`

Каждый профиль должен иметь:

- ограниченный набор tools;
- понятный system/skill stack;
- свою model policy;
- жесткие правила на PR-critical path.

## 5.5 Layer E: Optional Subagents

Subagents использовать только для:

- triage длинных логов;
- parallel review;
- side research;
- background indexing.

Не использовать на первом этапе для:

- обязательной генерации патча;
- обязательного apply;
- обязательной публикации PR.

## 6. Предлагаемая упаковка по plugin units

| Plugin unit | Тип в OpenClaw | Что регистрирует | Что внутри |
| --- | --- | --- | --- |
| `hordeforge-core` | non-capability plugin | commands, hooks, shared tools, runtime bootstrap | plugin shell, config schema, health, shared runtime client |
| `hordeforge-github` | tool/hook plugin | GitHub tools, PR actions, repo init helpers | `github_client`, `patch_workflow`, PR publishing |
| `hordeforge-ci` | tool/plugin | CI scan tools, incident handoff tools, optional hooks | `ci_failure_analyzer`, `ci_incident_handoff`, scanner logic |
| `hordeforge-context` | tool/plugin or `context-engine` later | repo grounding tools, indexing refresh, retrieval helpers | `rag_initializer`, memory/repo context helpers |
| `hordeforge-coding` | provider/ACP/harness adapter + tools | coding request entrypoints, review/generate commands | bridge from OpenClaw runtime to code patch contract |

### 6.1 Что попадет в итоговый installable addon

Итоговый addon должен включать:

- native OpenClaw plugin entrypoints;
- plugin manifests;
- Python runtime bridge;
- packaged Python code or wheel assets;
- install/doctor scripts;
- config presets;
- optional skill roots.

### 6.2 Что не должно быть отдельным plugin unit

Не надо выносить в отдельные плагины:

- `test_templates.py`
- benchmark helpers
- dev stubs
- compatibility shims ради старого CLI

Это внутренности runtime, а не пользовательские capability surfaces.

### 6.3 Удачные паттерны из `openclaw-auto-pilot-pack`

Репозиторий `openclaw-auto-pilot-pack` полезен не как образец native plugin architecture, а как образец packaging/composition layer.

Что стоит заимствовать:

1. `meta-repo` как сборщик нескольких независимых компонентов.
2. Явный `install.sh` для bootstrap локальной установки.
3. Отдельные каталоги:
   - `skills/`
   - `templates/`
   - `examples/`
   - `docs/`
4. Документированный "workflow narrative", который объясняет, как компоненты сочетаются.
5. Быстрый verification path после установки.

Что не стоит копировать один-в-один:

1. `skills-only` архитектуру как замену runtime/plugin layer.
2. Установку только в `~/.openclaw/skills/...` как финальный способ поставки.
3. Ручную сборку из git submodules как единственный production delivery path.
4. Отсутствие native plugin manifests и capability registration.

Практический вывод:

- использовать этот проект как референс для `distribution shell`;
- не использовать его как референс для `execution core`.

### 6.4 Предлагаемая структура meta-repo и addon

В разработке рекомендована такая структура:

```text
hordeforge-openclaw-addon/
├── plugins/
│   ├── hordeforge-core/
│   ├── hordeforge-github/
│   ├── hordeforge-ci/
│   ├── hordeforge-context/
│   └── hordeforge-coding/
├── runtime/
│   └── python/
│       └── hordeforge_runtime/
├── skills/
│   ├── hf-ci-fixer/
│   ├── hf-feature-builder/
│   ├── hf-pr-reviewer/
│   └── hf-ops/
├── templates/
│   ├── pr-body.md
│   ├── fix-plan.md
│   └── ci-triage.md
├── examples/
│   ├── ci-fix-sandbox/
│   └── feature-request-to-pr/
├── docs/
├── install.sh
└── README.md
```

Где:

- `plugins/` содержит native OpenClaw plugin entrypoints и manifests;
- `runtime/python/` содержит детерминированный HordeForge runtime bridge;
- `skills/` содержит policy/planning/review behavior;
- `templates/` и `examples/` ускоряют adoption;
- `install.sh` делает bootstrap для dev/local install;
- финальная поставка может быть как единый addon package, даже если в репо несколько plugin units.

## 7. Разбор текущих модулей HordeForge

### 7.0 Матрица `агент -> целевая OpenClaw surface`

Ниже матрица не про "куда положить файл", а про то, чем этот агент должен стать в целевой системе.

| HordeForge агент | Целевая surface | Переходное решение | Причина |
| --- | --- | --- | --- |
| `architecture_evaluator` | `skill` | skill + optional helper command | это policy/evaluation logic, а не runtime capability |
| `architecture_planner` | `skill` | skill | planning behavior хорошо живет в skill |
| `bdd_generator` | `skill` | skill + templates | генерирует спецификационные артефакты, не требует plugin runtime |
| `ci_failure_analyzer` | `tool` в `hordeforge-ci` plugin | Python runtime bridge method | нужен typed deterministic output для CI triage |
| `ci_monitor_agent` | `hook/plugin`, позже | freeze вне critical path | мониторинг не нужен для первого valid PR |
| `code_generator` | `split: skill + tool + provider/harness boundary` | временно bridge runtime method | нельзя оставлять монолитом и нельзя сводить к одному skill |
| `dependency_checker_agent` | `tool` или optional plugin | optional after PR path | полезно, но не критично для первого маршрута |
| `dod_extractor` | `skill` | skill | extraction/spec behavior, не runtime service |
| `fix_agent` | `split: skill + tool orchestration + coding runtime` | bridge runtime method | это orchestration над patch generation, а не просто prompt |
| `issue_closer` | `tool` в `hordeforge-github` | optional admin tool | это GitHub action, должен быть explicit tool |
| `issue_scanner` | `tool` в `hordeforge-ci` | keep as side entrypoint | scanner - это intake tool, не skill |
| `memory_agent` | `plugin` или `context-engine` позже | decouple from critical path | память не должна блокировать путь до PR |
| `pipeline_initializer` | `tool/command` в `hordeforge-core` | runtime bridge method | pipeline selection должна быть deterministic service |
| `pr_merge_agent` | `tool` в `hordeforge-github` | split into publish/merge operations | `publish_pr` и `merge_pr` не должны быть одним агентом |
| `rag_initializer` | `tool` в `hordeforge-context` | runtime bridge method | индексирование и refresh - это service/tool layer |
| `repo_connector` | `tool` в `hordeforge-github` | fold into repo prep/init tool | repo prep и metadata retrieval должны быть explicit tools |
| `review_agent` | `split: skill + tool + review normalization` | bridge runtime method | review policy можно в skill, но decision/result должны быть typed |
| `specification_writer` | `skill` | skill + templates | это authoring behavior |
| `stub_agent` | `remove` | удалить из целевой архитектуры | заглушки не должны пережить migration |
| `task_decomposer` | `skill` | skill | decomposition - чистый behavioral layer |
| `test_analyzer` | `skill` или optional tool | skill first | анализ test failures может жить как prompt-level helper, пока без runtime сервиса |
| `test_generator` | `skill` + templates | skill first | генерирует тестовые заготовки, не требует своего capability |
| `ci_incident_handoff` | `tool` в `hordeforge-ci` | runtime bridge method | handoff должен быть typed artifact, а не prose-only skill |
| `test_runner` | `tool` в `hordeforge-core` или `hordeforge-github` | runtime bridge method | это ключевой deterministic executor |

Дополнительные runtime-модули, которые не надо считать skills:

| Модуль | Целевая surface | Решение |
| --- | --- | --- |
| `patch_apply_agent` | `tool` | сохранить как deterministic executor |
| `patch_workflow.py` | `tool/service` | сохранить и завернуть в GitHub plugin |
| `github_client.py` | `plugin-owned runtime service` | не выносить в skill |
| `llm_wrapper.py` | `provider/harness bridge` | постепенно вытеснять из центра системы |
| `qwen_oauth_token_manager.py` | `plugin-owned auth/runtime helper` | оставить как bridge-only compatibility слой |
| `orchestrator/*` | `plugin-owned runtime engine` | сохранить как детерминированное ядро |

## 7.1 Orchestrator и pipelines

Состав:

- `orchestrator/*`
- `agents/pipeline_initializer.py`
- `agents/pipeline_runner.py`
- `pipelines/*.yaml`

Решение:

- оставить как Python deterministic engine;
- не переносить в OpenClaw subagent model;
- завернуть как `hf_pipeline_run`, `hf_pipeline_resume`, `hf_pipeline_status` tools/commands.

Статус:

- `Keep`

Оценка:

- effort `M`
- риск `Low`

Причина:

- это ваш наиболее ценный и уже понятный control logic;
- его надо не переписать, а сделать plugin-owned runtime service.

## 7.2 GitHub и PR workflow

Состав:

- `agents/github_client.py`
- `agents/patch_workflow.py`
- `agents/pr_merge_agent.py`
- `agents/live_merge.py`
- `agents/issue_closer.py`

Решение:

- `github_client.py` и `patch_workflow.py` сохранить почти как есть;
- `pr_merge_agent.py` разделить на `publish_pr` и `merge_pr`;
- `live_merge.py` убрать из critical path;
- зарегистрировать OpenClaw tools:
  - `hf_repo_init`
  - `hf_publish_pr`
  - `hf_pr_status`
  - `hf_merge_pr` как optional/admin-only.

Статус:

- `Keep + Adapt`

Оценка:

- effort `M`
- риск `Low-Medium`

Обязательная правка:

- `PR opened` должен считаться `SUCCESS`, а не `PARTIAL_SUCCESS`.

## 7.3 Patch apply и test execution

Состав:

- `agents/patch_apply_agent.py`
- `agents/patch_workflow_orchestrator.py`
- `agents/test_runner.py`
- `agents/test_executor.py`

Решение:

- сохранить isolated workspace apply как deterministic service;
- вынести simulation branches из runtime-path;
- оставить mock/fake behavior только в test fixtures;
- зарегистрировать tools:
  - `hf_apply_patch`
  - `hf_run_tests`
  - `hf_collect_test_failures`

Статус:

- `Keep + Refactor`

Оценка:

- effort `M`
- риск `Medium`

Обязательная правка:

- simulated apply path не должен жить в production-модуле;
- если patch не materialized, сервис должен fail fast.

## 7.4 CI triage и issue intake

Состав:

- `agents/ci_failure_analyzer.py`
- `agents/ci_incident_handoff.py`
- `agents/issue_scanner.py`
- `agents/issue_pipeline_dispatcher.py`
- `agents/ci_monitor_agent/*`

Решение:

- `ci_failure_analyzer.py` и `ci_incident_handoff.py` нужны сразу;
- `issue_scanner.py` нужен как secondary entrypoint;
- `ci_monitor_agent/*` не нужен для первого маршрута до valid PR;
- оформить как `hordeforge-ci` plugin tools плюс optional hooks/automation later.

Статус:

- analyzer/handoff: `Keep`
- monitor: `Freeze for now`

Оценка:

- effort `S-M`
- риск `Low`

## 7.5 RAG, memory, repo grounding

Состав:

- `agents/rag_initializer.py`
- `agents/memory_agent.py`
- связанные `rag/*` пакеты

Решение:

- не встраивать в critical path PR generation на первом этапе;
- оформить как `hordeforge-context`;
- сначала дать tools:
  - `hf_index_repo`
  - `hf_search_repo_context`
  - `hf_refresh_context`
- позже, если понадобится, превратить в `context-engine` plugin slot.

Статус:

- `Keep, but decouple from critical path`

Оценка:

- effort `M`
- риск `Medium`

Причина:

- RAG полезен, но это не то место, где вы выигрываете первый valid PR.

## 7.6 LLM, codegen, fix, review

Состав:

- `agents/code_generator.py`
- `agents/fix_agent.py`
- `agents/review_agent.py`
- `agents/llm_wrapper.py`
- `agents/llm_api.py`
- `agents/llm_providers.py`
- `agents/qwen_dashscope.py`
- `agents/qwen_oauth_token_manager.py`
- `agents/token_budget_system.py`

Решение по частям:

1. Prompting/instruction stack:
   - вынести в OpenClaw skills/system fragments where possible.
2. Provider routing:
   - целевой владелец OpenClaw provider/ACP/harness layer.
3. Patch contract normalization:
   - оставить в HordeForge runtime.
4. Synthetic fallback generation:
   - удалить из runtime critical path.
5. Review decision:
   - сделать deterministic schema normalization, а не "свободный review loop".

Статус:

- `Split aggressively`

Оценка:

- effort `L`
- риск `High`

Это главный сложный блок всей миграции.

### 7.6.1 Что оставить временно

- `qwen_oauth_token_manager.py` можно оставить как bridge-only compatibility слой;
- `token_budget_system.py` можно оставить как runtime metrics helper;
- `qwen_dashscope.py` можно использовать до тех пор, пока не завершен переход на OpenClaw-managed provider path.

### 7.6.2 Что убрать из runtime-path

- synthetic file targets вроде `src/feature_impl.py`;
- fallback patch generation без grounded targets;
- implicit success через demo/simulation behavior.

## 7.7 CLI и secret management

Состав:

- `cli/horde_cli.py`
- `cli/repo_store.py`
- `cli/infra.py`
- `cli/llm_cli.py`

Решение:

- внешний пользовательский CLI должен постепенно уйти в OpenClaw commands;
- `repo_store.py` и token refs временно оставить как bridge storage;
- целевой конфиг должен жить в:
  - `plugins.entries.<id>.config`
  - OpenClaw SecretRef semantics
  - plugin-owned onboarding/doctor flows

Статус:

- CLI UX: `Replace gradually`
- storage helpers: `Keep temporarily`

Оценка:

- effort `M`
- риск `Medium`

## 8. Модели и runtime: что делать с Qwen

Здесь есть три реальных варианта.

## 8.1 Вариант A: использовать bundled OpenClaw `qwen` provider

Плюсы:

- максимально native для OpenClaw;
- меньше собственного routing code;
- меньше долгосрочной поддержки.

Минусы:

- не сохраняет автоматически ваш текущий `qwen-code`/OAuth compatibility path;
- может потребовать переход на API-key based flow.

Когда подходит:

- если вы готовы уйти от собственного Qwen OAuth lifecycle.

Оценка:

- effort `M`
- риск `Medium`

## 8.2 Вариант B: использовать ACP runtime для Qwen Code

Плюсы:

- ближе к идее "coding harness inside OpenClaw";
- лучше, если вам нужна session/runtime semantics внешнего coding engine;
- меньше соблазна снова держать логику в Python LLM wrapper.

Минусы:

- выше интеграционная сложность;
- нужен зрелый ACP adapter path;
- требует хорошего контроля workdir, sandbox, patch contract.

Когда подходит:

- если Qwen Code для вас именно coding runtime, а не просто API provider.

Оценка:

- effort `L`
- риск `Medium-High`

## 8.3 Вариант C: собственный native harness plugin

Плюсы:

- полный контроль;
- можно сделать поведение строго под ваши patch/test/PR semantics.

Минусы:

- самый дорогой путь;
- легко повторить ошибку "строим платформу вместо результата";
- требует глубокого понимания OpenClaw harness contract.

Когда подходит:

- только если bundled provider и ACP path не покрывают обязательные требования.

Оценка:

- effort `XL`
- риск `High`

## 8.4 Рекомендация по порядку

Рекомендую такой порядок:

1. bridge phase: сохранить текущий Python Qwen path как временный backend внутри plugin-owned runtime;
2. parallel evaluation: проверить bundled `qwen` provider как целевую native модель;
3. если нужен именно coding harness behavior, пробовать ACP раньше, чем писать свой harness;
4. собственный harness делать только как третий вариант.

### 8.5 Namespace strategy для credentials и моделей

Для migration path не нужно плодить provider ids по числу credential sets.

Нужно сделать один compatibility provider:

- `horde-provider`

А внутри него:

- много auth profiles;
- внутренняя маршрутизация на нужный backend;
- общая публикация model refs в namespace `horde-provider/...`.

Почему так:

1. provider id должен описывать transport/runtime family, а не отдельный аккаунт;
2. разные наборы credentials должны жить как auth profiles;
3. fallback/rotation между credentials логичнее делать внутри одного provider;
4. это не конфликтует с canonical `qwen/...` namespace OpenClaw.

Пример:

- `horde-provider/qwen3-coder-plus`
- auth profiles:
  - `horde-provider:profile1`
  - `horde-provider:profile2`
  - `horde-provider:team-shared`

Внутри этого provider мы сами решаем, используем ли:

- Qwen OAuth compatibility path;
- другой backend;
- дополнительную routing logic.

## 9. Agent profiles и subagents в новой модели

## 9.1 Обязательные agent profiles

### `hf-ci-fixer`

Назначение:

- путь от CI failure до PR.

Разрешенные tools:

- `hf_ci_scan`
- `hf_prepare_repo`
- `hf_apply_patch`
- `hf_run_tests`
- `hf_publish_pr`

Запрещено:

- merge
- background fan-out по умолчанию

### `hf-feature-builder`

Назначение:

- feature request -> patch -> tests -> PR

Разрешенные tools:

- те же плюс optional context tools

### `hf-pr-reviewer`

Назначение:

- review and critique

Разрешенные tools:

- `hf_search_repo_context`
- `hf_collect_test_failures`
- `hf_pr_status`

### `hf-ops`

Назначение:

- doctor, plugin status, health, config.

## 9.2 Subagents

Разрешенные роли на later stage:

- `hf-log-triager`
- `hf-test-investigator`
- `hf-diff-review-worker`
- `hf-context-indexer`

Правило:

- subagents не получают publish/merge права;
- subagents не являются обязательным шагом для `valid PR`.

## 10. Целевой пользовательский поток внутри OpenClaw

```text
User -> OpenClaw agent profile (`hf-ci-fixer`)
  -> hf_ci_scan
  -> hf_prepare_repo
  -> hf_generate_or_request_patch
  -> hf_apply_patch
  -> hf_run_tests
  -> hf_publish_pr
  -> SUCCESS (PR opened)
```

Позже можно добавить:

- optional `hf-reviewer` subagent;
- optional context refresh;
- optional artifact summarization.

## 11. Фазы миграции

## 11.1 Phase 0: Prerequisite cleanup in HordeForge

Нужно сделать до pluginization:

1. `PR opened => SUCCESS`
2. удалить synthetic fallback targets из runtime-path
3. вынести simulated apply path в test fixtures/fakes
4. зафиксировать один success route: `ci_fix_pipeline -> valid PR`

Оценка:

- effort `S`
- риск `Low`

## 11.2 Phase 1: OpenClaw plugin shell + Python runtime bridge

Deliverables:

- `hordeforge-core` plugin shell
- plugin manifest/config schema
- health/doctor commands
- stable RPC bridge to Python runtime

Оценка:

- effort `M`
- риск `Medium`

Exit criteria:

- OpenClaw может вызвать HordeForge runtime deterministically;
- runtime health и versioning видны из OpenClaw.

## 11.3 Phase 2: GitHub / patch / test surfaces

Deliverables:

- `hf_prepare_repo`
- `hf_apply_patch`
- `hf_run_tests`
- `hf_publish_pr`

Оценка:

- effort `M`
- риск `Medium`

Exit criteria:

- полный deterministic path до PR управляется из OpenClaw.

## 11.4 Phase 3: CI and context plugins

Deliverables:

- `hordeforge-ci`
- `hordeforge-context`
- optional commands and health surfaces

Оценка:

- effort `M`
- риск `Medium`

## 11.5 Phase 4: coding runtime transition

Deliverables:

- decision between:
  - bundled `qwen`
  - ACP runtime
  - custom harness
- migration of `code_generator/fix_agent/review_agent` responsibility into OpenClaw-native layers

Оценка:

- effort `L`
- риск `High`

## 11.6 Phase 5: single-addon packaging

Deliverables:

- one installable OpenClaw add-on package
- install scripts
- doctor checks
- config presets

Оценка:

- effort `S-M`
- риск `Medium`

## 12. Критические риски

## 12.1 Самый опасный риск

Самый опасный риск - снова начать строить платформу, а не рабочий путь до PR.

Признаки:

- слишком рано уходим в custom harness;
- слишком рано делаем богатую automation/subagent graph;
- слишком рано переносим RAG/memory/monitoring вместо PR path.

## 12.2 Технические риски

- TS/Python boundary может стать хрупким, если контракт не будет строгим.
- Secret migration может дублировать старый secret store и OpenClaw SecretRef одновременно.
- ACP/harness path может оказаться сложнее, чем кажется, если нужен строгий patch contract.
- Windows/Docker/path handling легко ломают apply/test workflows.

## 12.3 Архитектурные риски

- если GitHub/test/apply останутся вне OpenClaw transcript/control plane, цель будет достигнута только частично;
- если весь Python код просто "обернуть" без decomposition по plugin surfaces, получится старый HordeForge внутри новой оболочки.

## 13. Практический вывод

Правильный путь сейчас:

1. не переписывать HordeForge целиком;
2. не тащить весь control plane отдельно от OpenClaw;
3. не делать ставку сразу на custom harness;
4. разложить HordeForge на OpenClaw-native plugin surfaces;
5. держать Python как plugin-owned deterministic runtime до тех пор, пока не будет доказан рабочий маршрут до PR;
6. только потом переносить coding runtime глубже в provider/ACP/harness model.

Ключевая формула:

- OpenClaw должен стать внешней операционной системой;
- HordeForge должен стать plugin pack + deterministic execution runtime;
- `valid PR opened` должен быть первой завершенной вертикалью, а не побочным эффектом общей платформы.

## 14. Рекомендуемое решение

Если выбирать один путь, который лучше всего соответствует вашим целям:

- **целевая архитектура**: `OpenClaw-native addon`
- **первый этап реализации**: `native plugin shell + Python runtime bridge`
- **критический маршрут**: `hf-ci-fixer -> valid PR`
- **стратегия по моделям**: сначала bridge, затем bundled `qwen` или ACP, custom harness только при доказанной необходимости

Это самый реалистичный способ не потерять уже сделанное и при этом действительно перейти под управление OpenClaw.

### 14.1 Рекомендованный packaging pattern

С учетом удачных внешних референсов, итоговый паттерн должен быть таким:

1. `meta-repo of plugins + skills + templates + examples`
2. `install.sh` для локального bootstrap и dev-install
3. `native OpenClaw plugins` как execution/control layer
4. `skills` как behavior/policy layer
5. `Python runtime bridge` как переходный слой для существующего HordeForge кода
6. `single addon package` как финальная форма поставки

В одной строке:

- брать у `openclaw-auto-pilot-pack` способ собирать и доставлять набор компонентов;
- не брать у него `skills-only` модель как замену HordeForge runtime.
