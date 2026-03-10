# 34. Documentation Alignment & Remaining Tasks

**Created:** 2026-03-10

## Цель

Актуализировать документацию и закрыть оставшиеся нереализованные пункты.

## Статус: DONE ✅ (2026-03-10)

---

## Незавершённые пункты из документации

### 1. GitHub Pagination (P0)

**Описание:** GitHub client не поддерживает пагинацию для больших репозиториев.

**Где указано:** `docs/features.md` - "GitHub integration" -> "pagination"

**Текущее состояние:** `agents/github_client.py` - базовая реализация без пагинации

**Что нужно сделать:**
- Добавить пагинацию в `GitHubClient.get_issues()`
- Добавить пагинацию в `GitHubClient.get_pulls()`
- Добавить пагинацию в `GitHubClient.get_commits()`
- Обрабатывать `Link` header для next/prev страниц

**Критерии приёмки:**
- Методы `get_issues()`, `get_pulls()`, `get_commits()` поддерживают `page` и `per_page` параметры
- Автоматическое следование за next link при наличии
- Логирование информации о пагинации

**Priority:** P0

---

### 2. Enhanced DoD Extraction (P1)

**Описание:** `dod_extractor.py` использует deterministic fallback вместо LLM- enhanced извлечения.

**Где указано:** `docs/features.md` - "DoD extraction" -> "richer extraction semantics"

**Текущее состояние:** `agents/dod_extractor.py` - возвращает базовые критерии

**Что нужно сделать:**
- Интегрировать `llm_wrapper.py` для извлечения DoD из issue body
- Использовать prompt engineering для анализа issue
- Извлекать acceptance criteria, BDD сценарии, тестовые критерии

**Критерии приёмки:**
- LLM-based extraction с fallback на deterministic
- Извлечение acceptance criteria из markdown
- Извлечение BDD сценариев (Given/When/Then)
- Confidence score в результатах

**Priority:** P1

---

### 3. Enhanced CI Failure Parser (P1)

**Описание:** `ci_failure_analyzer` имеет базовый MVP парсер, нужно улучшить.

**Где указано:** `docs/features.md` - "CI failure analysis" -> "richer parser"

**Текущее состояние:** `agents/ci_failure_analyzer.py` - базовый анализ

**Что нужно сделать:**
- Парсить больше типов ошибок (syntax, runtime, test, lint, type check)
- Извлекать stack traces и определять местоположение ошибки
- Классифицировать по severity (critical, major, minor)
- Предлагать конкретные исправления на основе типа ошибки

**Критерии приёмки:**
- Поддержка Python, JavaScript/TypeScript, Go, Java ошибок
- Извлечение file:line из stack traces
- Categorization: syntax, runtime, test, lint, type, security

**Priority:** P1

---

## Subtasks

```markdown
- [x] 34.1 GitHub pagination support in GitHubClient ✅
- [x] 34.2 LLM-enhanced DoD extraction ✅
- [x] 34.3 Enhanced CI failure parser ✅
```

## Notes

- Документация обновлена 2026-03-10: ARCHITECTURE.md, use_cases.md, scheduler_integration.md, REPO_STRUCTURE.md, FR_NFR.md
- Features.md уже отражает актуальное состояние
- Большинство P0-P2 фич уже реализованы

### Implementation Complete 2026-03-10

**34.1 GitHub Pagination (P0):**
- Added `page`/`per_page` params to `get_issues()`, `get_commits()`, `list_pull_requests_paginated()`
- Implemented `_parse_link_header()`, `_extract_page_info()`, `_log_pagination()`
- Added `_request_with_pagination()` for auto-pagination
- Added convenience methods: `get_all_issues()`, `get_all_commits()`, `get_all_pull_requests()`
- Tests: 16 tests pass

**34.2 LLM-enhanced DoD Extraction (P1):**
- Integrated `llm_wrapper` in `DodExtractor`
- Added `build_dod_prompt()` with structured prompt for DoD extraction
- Added `extract_acceptance_criteria_from_markdown()` - parses checklists, AC headers, bullet points
- Added `extract_bdd_scenarios_from_markdown()` - parses Given/When/Then
- Added `parse_llm_dod_response()` - parses LLM JSON response
- Added confidence scoring
- Tests: 8 tests pass

**34.3 Enhanced CI Failure Parser (P1):**
- Added language-specific error patterns: Python, JavaScript/TypeScript, Go, Java
- Added `classify_failure_text()` for detailed error classification
- Added `extract_file_line_from_trace()` for Python, JS, Go, Java stack traces
- Added `determine_severity()` mapping (critical/major/minor)
- Enhanced `CiFailureAnalyzer.run()` to include severity and locations
- Tests: 19 tests pass
