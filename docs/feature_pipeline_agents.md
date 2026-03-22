# Feature Pipeline Агенты

Данный документ описывает агенты, реализующие полный цикл разработки функциональности от анализа задачи до объединения pull request. Эти агенты составляют основу feature pipeline в системе HordeForge.

## Обзор

Feature pipeline представляет собой последовательность агентов, которая преобразует GitHub issue в законченный функционал, реализованный в виде кода, тестов и документации. Каждый агент выполняет свою часть работы, передавая результат следующему агенту в цепочке.

## Архитектура Pipeline

```
GitHub Issue → DoD Extractor → Specification Writer → Test Generator → Code Generator → Test Runner → Fix Agent → Review Agent → PR Merge Agent
```

## Агенты

### 1. DoD Extractor (`dod_extractor`)

**Назначение**: Извлекает Definition of Done (DoD) из GitHub issue, включая acceptance criteria и BDD сценарии.

**Входной контракт**: `context.issue.v1` (GitHub issue данные)

**Выходной контракт**: `context.dod.v1` (DoD спецификация)

**Функциональность**:
- Анализ текста issue для извлечения требований
- Генерация acceptance criteria
- Генерация BDD сценариев (Given/When/Then)
- Использование LLM для расширения спецификации
- Поддержка детерминированного извлечения (без LLM)

**Пример использования**:
```python
context = {
    "issue": {
        "title": "Add user login functionality",
        "body": "As a user, I want to login to the system so that I can access my account.\n\n## Acceptance Criteria\n- User can enter username and password\n- System validates credentials\n- User is redirected to dashboard after login"
    }
}

result = DodExtractor().run(context)
```

### 2. Specification Writer (`specification_writer`)

**Назначение**: Генерирует техническую спецификацию на основе DoD, включая user stories, технические требования и план изменений файлов.

**Входной контракт**: `context.dod.v1` (DoD спецификация)

**Выходной контракт**: `context.spec.v1` (Техническая спецификация)

**Функциональность**:
- Генерация user stories в формате "As a ..., I want ..., So that ..."
- Создание acceptance criteria
- Генерация технической спецификации (компоненты, эндпоинты, схемы)
- План изменений файлов (создание, модификация, удаление)
- Использование LLM для расширения спецификации
- Поддержка детерминированной генерации (без LLM)

**Пример использования**:
```python
context = {
    "issue": {
        "title": "Implement user registration API",
        "body": "Add API endpoint for user registration with email verification"
    },
    "project_structure": {
        "files": ["api/v1/users.py", "models/user.py", "services/auth.py"]
    }
}

result = SpecificationWriter().run(context)
```

### 3. Test Generator (`test_generator`)

**Назначение**: Генерирует unit и integration тесты на основе спецификации и сгенерированного кода.

**Входной контракт**: `context.spec.v1` (Техническая спецификация)

**Выходной контракт**: `context.tests.v1` (Тесты)

**Функциональность**:
- Генерация unit тестов для функций и методов
- Генерация integration тестов для API эндпоинтов
- Генерация edge case тестов
- Анализ существующих тестов для определения паттернов
- Адаптация сгенерированных тестов к проектным паттернам
- Использование LLM для генерации комплексных тестов
- Поддержка детерминированной генерации (без LLM)

**Пример использования**:
```python
context = {
    "spec": {
        "summary": "User login functionality",
        "requirements": [{"description": "Validate user credentials"}]
    },
    "code_patch": {
        "files": [{"path": "auth/service.py", "content": "..."}]
    },
    "existing_test_files": [
        {"path": "tests/test_auth.py", "content": "..."}
    ],
    "existing_files": ["auth/service.py", "models/user.py"],
    "repo_config": {
        "config_files": ["pytest.ini"],
        "package_json": {"devDependencies": {"pytest": "^7.0.0"}}
    }
}

result = TestGenerator().run(context)
```

### 4. Code Generator (`code_generator`)

**Назначение**: Генерирует код на основе спецификации, тестов и подзадач.

**Входной контракт**: `context.spec.v1` (Техническая спецификация)

**Выходной контракт**: `context.code_patch.v1` (Патч кода)

**Функциональность**:
- Генерация кода на основе спецификации
- Интеграция с RAG для получения контекста из существующего кода
- Использование LLM для генерации качественного кода
- Поддержка детерминированной генерации (без LLM)
- Создание патча с изменениями файлов
- Интеграция с GitHub для создания pull request

**Пример использования**:
```python
context = {
    "spec": {
        "summary": "User registration API",
        "file_changes": [{"path": "api/v1/users.py", "description": "Add register endpoint"}]
    },
    "tests": {
        "test_cases": [{"name": "test_register_user", "content": "..."}]
    },
    "subtasks": {
        "items": [{"title": "Create user model", "description": "..."}]
    },
    "rag_context": {
        "sources": ["existing_user_code.py", "auth_patterns.py"]
    },
    "use_llm": True
}

result = CodeGenerator().run(context)
```

### 5. Test Runner (`test_runner`)

**Назначение**: Запускает тесты и анализирует результаты в изолированном окружении.

**Входной контракт**: `context.code_patch.v1` (Патч кода)

**Выходной контракт**: `context.test_results.v1` (Результаты тестов)

**Функциональность**:
- Определение используемого фреймворка тестирования (pytest, jest, go test)
- Создание изолированного окружения для запуска тестов
- Запуск тестов с изоляцией
- Сбор информации о покрытии кода
- Анализ результатов тестов
- Обработка таймаутов и исключений

**Пример использования**:
```python
context = {
    "project_path": "./my_project",
    "project_metadata": {
        "language": "python",
        "test_framework": "pytest"
    },
    "coverage_enabled": True,
    "pytest_args": ["--verbose", "--tb=short"]
}

result = TestRunner().run(context)
```

### 6. Fix Agent (`fix_agent`)

**Назначение**: Исправляет код на основе результатов тестов и анализа ошибок.

**Входной контракт**: `context.test_results.v1` (Результаты тестов)

**Выходной контракт**: `context.code_patch.v1` (Патч кода с исправлениями)

**Функциональность**:
- Анализ stacktrace ошибок
- Определение типа ошибки (assertion, exception, syntax)
- Генерация исправлений на основе типа ошибки
- Поддержка итеративных исправлений
- Отслеживание количества итераций исправлений

**Пример использования**:
```python
context = {
    "test_runner": {
        "test_results": {
            "failed": 2,
            "stdout": "AssertionError: expected 3 got 2",
            "stderr": ""
        }
    }
}

result = FixAgent().run(context)
```

### 7. Review Agent (`review_agent`)

**Назначение**: Проводит автоматический ревью кода с проверкой на соответствие стандартам и безопасности.

**Входной контракт**: `context.code_patch.v1` (Патч кода)

**Выходной контракт**: `context.review_result.v1` (Результат ревью)

**Функциональность**:
- Запуск линтеров (ruff для Python)
- Запуск сканеров безопасности (bandit для Python)
- Проверка архитектурных правил
- Анализ содержимого файлов на предмет уязвимостей
- Интеграция с GitHub для комментирования PR
- Использование LLM для глубокого анализа кода
- Поддержка детерминированного анализа (без LLM)

**Пример использования**:
```python
context = {
    "code_patch": {
        "files": [{"path": "auth/service.py", "content": "..."}]
    },
    "spec": {
        "summary": "Authentication service implementation"
    },
    "github_client": github_client_instance,
    "pr_number": 123,
    "use_llm": True
}

result = ReviewAgent().run(context)
```

## Интеграции

### RAG (Retrieval Augmented Generation)

Агенты используют RAG для получения контекста из существующей кодовой базы, документации и истории изменений. Это позволяет генерировать более точный и соответствующий проекту код и тесты.

### LLM (Large Language Model)

Агенты могут использовать LLM для расширенной генерации и анализа. Поддерживаются различные провайдеры LLM, включая OpenAI, Anthropic и локальные модели. Использование LLM может быть включено или выключено в зависимости от требований безопасности и доступности.

### GitHub API

Агенты интегрированы с GitHub API для:
- Чтения issue и pull request
- Комментирования pull request
- Создания и объединения pull request
- Работы с ветками и коммитами

## Контракты

Каждый агент работает с определёнными контрактами данных, которые обеспечивают согласованность и совместимость между агентами. Контракты определяют структуру входных и выходных данных, что позволяет легко заменять и расширять агенты без нарушения целостности pipeline.

## Безопасность и надёжность

- Все агенты работают в изолированных окружениях
- Код проверяется на безопасность перед выполнением
- Используются ограничения по времени выполнения
- Поддерживается полная история изменений и решений
- Все действия логируются для аудита

## Расширяемость

Архитектура агентов позволяет легко добавлять новые агенты и модифицировать существующие. Каждый агент имеет чётко определённую ответственность и интерфейс взаимодействия, что упрощает разработку и тестирование новых функций.