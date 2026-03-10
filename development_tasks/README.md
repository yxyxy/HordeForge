# Development Tasks Catalog

Каталог содержит детальный план разработки HordeForge, синхронизированный с:

- `docs/ARCHITECTURE.md`
- `docs/FR_NFR.md`
- `docs/AGENT_SPEC.md`
- `docs/features.md`
- `docs/scheduler_integration.md`

## Файлы каталога

1. `00_master_roadmap.md` — общий план и контрольные точки.
31. `subtasks/INDEX.md` — индекс всех подзадач с BDD/TDD постановкой.

## Формат задач

Каждая задача имеет:

- `Task ID`
- `Priority`
- `Estimate`
- `Dependencies`
- `Подзадачи`
- `Критерии приемки`

## Формат подзадач

Для каждой подзадачи создан отдельный файл в `development_tasks/subtasks/<phase>/<task_id>/`.

Каждый файл подзадачи содержит:

- BDD блок (`Feature`, `Scenario`, `Given/When/Then`)
- TDD блок (`Red`, `Green`, `Refactor`)
- тест-дизайн и `Definition of Done`

## Правило исполнения

1. Не начинать задачу, пока не закрыты все `Dependencies`.
2. Любая задача считается завершенной только при выполнении всех критериев приемки.
3. После закрытия задачи обновлять статус в соответствующем phase-файле.
