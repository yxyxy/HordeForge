# 00. Master Roadmap

## Цель

Собрать реалистичный план перевода HordeForge в `OpenClaw-native addon` на основе
[openclaw_pluginization_migration_design.md](/d:/Projects/HordeForge/docs/openclaw_pluginization_migration_design.md),
не теряя детерминированный путь:

`CI / issue -> patch -> tests -> valid PR`

## Принципы

1. OpenClaw становится внешним control plane.
2. HordeForge раскладывается на `plugins / tools / hooks / skills / runtime bridge`.
3. Критический путь сначала доводится до `valid PR`, а не до полной платформенной зрелости.
4. `skills` используются для policy/planning/review behavior.
5. Детерминированная логика `apply / test / publish PR / CI triage` остается runtime/service слоем.

## Фазы

| Phase | Основной результат | Gate |
|---|---|---|
| P0 Discovery & Contracts | зафиксированы provider, runtime и packaging contracts | roadmap согласован, первая задача оформлена |
| P1 Auth & Model Bootstrap | `horde-provider` описан как native compatibility provider | импорт credentials и refresh lifecycle спроектированы |
| P2 Runtime Shell | `hordeforge-core` plugin shell + Python runtime bridge | OpenClaw вызывает HordeForge runtime детерминированно |
| P3 Valid PR Vertical Slice | `hf-ci-fixer -> valid PR` работает в OpenClaw control plane | PR created = SUCCESS |
| P4 Context & CI Expansion | CI/context capabilities вынесены в plugin surfaces | side capabilities не ломают critical path |
| P5 Packaging & Install | единый addon + bootstrap install flow | установка и bootstrap документированы и воспроизводимы |

## Критический путь

1. `HF-OC-001` — спроектировать `horde-provider` и native Qwen OAuth compatibility path.
2. `HF-OC-002` — определить OpenClaw plugin shell и Python runtime bridge contract.
3. `HF-OC-003` — вынести deterministic tools: repo prep, patch apply, test run, PR publish.
4. `HF-OC-004` — собрать `hf-ci-fixer` vertical slice до `valid PR`.
5. `HF-OC-005` — оформить meta-repo/addon packaging и install flow.

## Задачи

## P0 Discovery & Contracts

### HF-OC-001 — `horde-provider` Qwen OAuth compatibility provider

- Priority: P0
- Estimate: 3d
- Dependencies: none

Objective:
- зафиксировать, как текущий `qwen_oauth_token_manager.py` становится native-compatible provider слоем внутри OpenClaw;
- не ломать bundled `qwen`, а ввести единый provider namespace `horde-provider`;
- описать auth profiles, model namespace, import flow и refresh lifecycle.

Подзадачи:
- `development_tasks/subtasks/p0/HF-OC-001/01_provider_contract.md`
- `development_tasks/subtasks/p0/HF-OC-001/02_credentials_storage_and_refresh.md`
- `development_tasks/subtasks/p0/HF-OC-001/03_model_namespace_and_failover.md`

Критерии приемки:
1. Зафиксировано, что provider id = `horde-provider`.
2. Зафиксировано, что разные credential sets живут как auth profiles, а не отдельные providers.
3. Описан import flow `oauth_creds.json -> OpenClaw auth profile`.
4. Описан refresh lifecycle и persisted write-back.
5. Зафиксирован model namespace `horde-provider/...`.

### HF-OC-002 — Plugin Shell and Runtime Bridge Contract

- Priority: P0
- Estimate: 3d
- Dependencies: HF-OC-001

Objective:
- описать `hordeforge-core` plugin shell;
- определить TS/Python boundary и typed RPC contract;
- определить health/version/capabilities surface.

Подзадачи:
- будут созданы после закрытия `HF-OC-001`

Критерии приемки:
1. Определён plugin manifest/config schema baseline.
2. Определён runtime bridge protocol.
3. Определён ownership между OpenClaw plugin shell и HordeForge Python runtime.

## P1 Auth & Model Bootstrap

### HF-OC-003 — Secret Migration and Auth Profile Bootstrap

- Priority: P0
- Estimate: 2d
- Dependencies: HF-OC-001

Objective:
- определить migration path от старого `repo_store`/`api_key_ref` к OpenClaw-native secret/auth surfaces.

Критерии приемки:
1. Описан temporary compatibility bridge.
2. Описан target storage model.
3. Определён пользовательский bootstrap flow.

### HF-OC-004 — Model Catalog and Fallback Policy

- Priority: P1
- Estimate: 2d
- Dependencies: HF-OC-001

Objective:
- зафиксировать model catalog для `horde-provider` и поведение fallback/rotation.

Критерии приемки:
1. Есть список стартовых моделей.
2. Определён порядок auth profile rotation.
3. Определено поведение при auth/model failure.

## P2 Runtime Shell

### HF-OC-005 — `hordeforge-core` Native Plugin Shell

- Priority: P1
- Estimate: 4d
- Dependencies: HF-OC-002, HF-OC-003

Objective:
- создать базовый native plugin shell для HordeForge surfaces.

Критерии приемки:
1. Есть plugin manifest.
2. Есть config schema baseline.
3. Есть commands/health surface.

### HF-OC-006 — Python Runtime Bridge

- Priority: P1
- Estimate: 4d
- Dependencies: HF-OC-002

Objective:
- обернуть текущий deterministic runtime в plugin-owned bridge.

Критерии приемки:
1. OpenClaw вызывает runtime по typed contract.
2. Есть health/version/capabilities ответы.
3. Ошибки и failure states нормализованы.

## P3 Valid PR Vertical Slice

### HF-OC-007 — Deterministic GitHub and Patch Tools

- Priority: P1
- Estimate: 5d
- Dependencies: HF-OC-005, HF-OC-006

Objective:
- вынести `prepare_repo / apply_patch / run_tests / publish_pr` в tool surfaces.

Критерии приемки:
1. Tools зарегистрированы и имеют typed outputs.
2. Runtime simulation не живёт в critical path.
3. `PR opened => SUCCESS`.

### HF-OC-008 — `hf-ci-fixer` Vertical Slice

- Priority: P1
- Estimate: 5d
- Dependencies: HF-OC-007

Objective:
- собрать рабочий маршрут `CI failure -> patch -> tests -> PR`.

Критерии приемки:
1. Маршрут выполняется из OpenClaw control plane.
2. Успехом считается открытый валидный PR.
3. Merge не требуется.

## P4 Context & CI Expansion

### HF-OC-009 — `hordeforge-ci` Plugin Surface

- Priority: P2
- Estimate: 3d
- Dependencies: HF-OC-008

Objective:
- оформить CI triage/intake как отдельный plugin surface.

### HF-OC-010 — `hordeforge-context` Plugin Surface

- Priority: P2
- Estimate: 3d
- Dependencies: HF-OC-008

Objective:
- вынести grounding/indexing/retrieval в отдельный context layer вне critical path.

## P5 Packaging & Install

### HF-OC-011 — Meta-Repo Packaging Pattern

- Priority: P2
- Estimate: 2d
- Dependencies: HF-OC-005, HF-OC-009, HF-OC-010

Objective:
- собрать структуру `plugins/ + runtime/ + skills/ + templates/ + examples/`.

### HF-OC-012 — Install Flow and Bootstrap

- Priority: P2
- Estimate: 2d
- Dependencies: HF-OC-011

Objective:
- сделать install/bootstrap path по образцу удачных внешних паттернов, включая `install.sh`.

Критерии приемки:
1. Есть documented bootstrap path.
2. Есть verification steps после установки.
3. Поставка соответствует модели addon, а не skills-only pack.

## Глобальные критерии успеха

1. `horde-provider` описан как единый provider namespace для compatibility path.
2. Детерминированный runtime HordeForge вызывается из OpenClaw plugin surfaces.
3. Путь `hf-ci-fixer -> valid PR` реализован в OpenClaw control plane.
4. Skills используются как behavior layer, а не как замена runtime.
5. Итоговая поставка оформлена как addon с воспроизводимой установкой.
