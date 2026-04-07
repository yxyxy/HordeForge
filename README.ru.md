# HordeForge

[English](README.md) | [Русский](README.ru.md)

Автономный оркестратор разработки ПО на базе ИИ. Читает GitHub-задачи и автоматически выполняет полный цикл разработки ПО: Issue → DoD → Spec → Tasks → Tests → Code → Fix loop → Review → PR → Merge

## Текущее состояние

Система находится на стадии позднего MVP / предварительной подготовки к производству:

- Основные возможности ядра реализованы (оркестратор, шлюз планировщика, реестр, хранилище, наблюдаемость).
- Подходит для внутреннего пилотного использования и контролируемого использования на staging.
- Широкий релиз в производство требует финального аудита (E2E тестирование staging, проверка безопасности, нагрузочное тестирование).

## Ключевые возможности

### Интеграция с ИИ
- **18+ LLM-провайдеров**: OpenAI, Anthropic, Google, Ollama, OpenRouter, AWS Bedrock, Google Vertex AI и другие
- **Унифицированный интерфейс**: Согласованный API со всеми провайдерами с поддержкой потоковой передачи
- **Система бюджетов токенов**: Комплексное отслеживание затрат и контроль бюджетов
- **Оптимизация контекста**: Продвинутое сжатие и дедупликация для эффективного использования токенов

### Система памяти
- **Память агентов**: Хранение и извлечение исторических решений для повторного использования знаний
- **Автоматическая запись**: Успешные шаги конвейера автоматически сохраняются в памяти
- **Семантический поиск**: Поиск релевантных исторических решений с помощью векторного сходства
- **Улучшение контекста**: Комбинирование исторического и текущего контекста репозитория

### Оркестрация конвейеров
- **Декларативные конвейеры**: YAML-определения конвейеров
- **Параллельное выполнение**: Управление зависимостями на основе DAG с параллельной обработкой
- **Повторы и циклы**: Надежная обработка ошибок с настраиваемой политикой повторов
- **Ручное управление**: Возможность вмешательства и отладки

### Архитектура

Основные слои: агенты → оркестратор → планировщик → интеграции → хранилище

- **Агенты**: `agents/` - извлечение DoD, генерация спецификаций, генерация тестов, генерация кода, цикл исправлений, ревью, слияние
- **Оркестратор**: `orchestrator/` - движок конвейера, жизненный цикл шагов, повторы/таймауты/циклы, сводка запусков
- **Планировщик**: `scheduler/` - шлюз (FastAPI), cron-задачи, ручное управление, идемпотентность, ограничение частоты, изоляция арендаторов
- **Интеграции**: GitHub issues/PR/actions, git branch workflow, адаптеры триггеров планировщика
- **Хранилище**: `storage/` - состояние запусков, артефакты агентов, журналы решений, история повторов (JSON и PostgreSQL бэкенды)
- **RAG**: `rag/` - Retrieval-Augmented Generation с векторным хранилищем и коллекциями памяти
- **Реестр**: `registry/` - метаданные контрактов, агентов и конвейеров с валидацией


## Быстрый старт

### Локальная разработка

1. Установите зависимости: `pip install -r requirements-dev.txt`
2. Запустите шлюз: `uvicorn scheduler.gateway:app --host 0.0.0.0 --port 8000 --reload`
3. Запустите конвейер: `horde pipeline run init_pipeline`

### Docker Compose

1. Создайте файл окружения: `cp .env.example .env` (отредактируйте настройки)
2. Соберите и запустите в локальном режиме: `docker compose up --build`
3. Опционально командный режим: `docker compose --profile team up --build -d`
4. Опционально локальная инфраструктура из CLI:
   - `horde infra mode show`
   - `horde infra qdrant up`
   - `horde infra mcp up`
5. Проверьте работоспособность: `curl http://localhost:8000/health`

## Конфигурация окружения

Унифицированная конфигурация времени выполнения загружается из переменных окружения через `RunConfig` (полный список см. в `.env.example`):

- `HORDEFORGE_GATEWAY_URL` (по умолчанию: `http://localhost:8000`)
- `HORDEFORGE_PIPELINES_DIR` (по умолчанию: `pipelines`)
- `HORDEFORGE_RULES_DIR` (по умолчанию: `rules`)
- `HORDEFORGE_EMBEDDING_MODEL` (по умолчанию: `sentence-transformers/all-MiniLM-L6-v2`)
- `HORDEFORGE_STORAGE_DIR` (по умолчанию: `.hordeforge_data`)
- `HORDEFORGE_MAX_PARALLEL_WORKERS` (по умолчанию: `4`)
- `HORDEFORGE_VECTOR_STORE_MODE` (по умолчанию: `auto`)
- `HORDEFORGE_DATABASE_URL` (PostgreSQL бэкенд)
- `HORDEFORGE_LOG_LEVEL` (по умолчанию: `INFO`)
- `HORDEFORGE_AUTH_ENABLED` (по умолчанию: `false`)
- `HORDEFORGE_METRICS_EXPORTER` (экспорт метрик)
- `HORDEFORGE_RETENTION_RUNS_DAYS` (по умолчанию: `90`)

## Настройка LLM

Настройте LLM по умолчанию через profile-store (рекомендуется):

```bash
horde llm profile add openai-main --provider openai --model gpt-4o --api-key YOUR_OPENAI_KEY --set-default
horde llm profile list
horde llm --profile openai-main test
```

## Интерфейс CLI

HordeForge предоставляет два интерфейса CLI:

### Основной CLI (`hordeforge`)
```bash
# Запуск конвейера
hordeforge run --pipeline init_pipeline --inputs "{}"

# Проверка статуса
hordeforge status

# Запуск с конкретным провайдером
hordeforge llm --provider openai --model gpt-4o "Hello, world!"

# Интерактивный чат
hordeforge llm chat

# Просмотр использования токенов
hordeforge llm tokens

# Просмотр информации о затратах
hordeforge llm cost

# Просмотр статуса бюджета
hordeforge llm budget
```

### Интерактивный CLI (`horde`)
```bash
# Одноразовая настройка профиля репозитория (id репозитория определяется из URL)
horde repo add --url https://github.com/yxyxy/HordeForge --token YOUR_GITHUB_TOKEN --set-default

# Опциональное управление секретами
horde secret set github.main YOUR_GITHUB_TOKEN
horde secret list

# Запуск инициализации по id профиля репозитория (не нужно передавать --repo-url/--token каждый раз)
horde init yxyxy/HordeForge
horde pipeline run init yxyxy/HordeForge

# Интерактивная разработка
horde task "Implement user authentication"

# Режимы планирования/действия
horde --plan "How should I refactor this codebase?"
horde --act "Write a Python function to sort an array"

# Управление конвейерами
horde pipeline run feature --inputs '{"prompt": "Add user management"}'

# Управление инфраструктурой
horde infra mode show
horde infra mode set local --save
horde infra mode set team --save
horde infra qdrant up
horde infra mcp up
horde infra stack up                # безопасный режим по умолчанию: --no-recreate
horde infra stack up --build        # пересобрать образ(ы)
horde infra stack up --recreate     # принудительно пересоздать контейнеры
horde infra stack status

# Просмотр истории
horde history

# Просмотр использования токенов и затрат
horde llm tokens
horde llm cost
horde llm budget

# Профили LLM с поддержкой локального JSON-хранилища + ссылки на секреты
horde llm profile add openai-main --provider openai --model gpt-4o --api-key YOUR_OPENAI_KEY --set-default
horde llm profile list
horde llm --profile openai-main test
```

## Система памяти

Система памяти агентов автоматически записывает успешные шаги конвейера и обеспечивает повторное использование знаний:

```python
# Память автоматически используется агентами при наличии
# Не требуется специальной настройки - просто запускайте конвейеры как обычно
horde pipeline run feature --inputs '{"prompt": "Add user authentication"}'

# Контекст памяти автоматически включается в запросы агентов
# Исторические решения помогают улучшить качество текущих задач
```

## Оптимизация контекста

Система включает продвинутую оптимизацию контекста:

- **Дедупликация**: Удаляет избыточную информацию из контекста
- **Сжатие**: Уменьшает размер контекста для соответствия лимитам токенов
- **Интеграция памяти**: Комбинирует исторический и текущий контекст
- **Интеграция RAG**: Объединяет контекст репозитория и памяти

## Система бюджетов токенов

Мониторинг и контроль затрат на LLM:

```bash
# Показать текущее использование токенов
horde llm tokens
hordeforge llm tokens

# Показать историю использования
horde llm tokens --history
hordeforge llm tokens --history

# Показать информацию о затратах
horde llm cost
hordeforge llm cost

# Установить лимиты бюджета
horde llm budget --set-daily 10.0
horde llm budget --set-monthly 100.0
horde llm budget --set-session 5.0

# Просмотр статуса бюджета
horde llm budget
```

## Компоненты архитектуры

### Слой агентов
- `agents/` - Специализированные агенты для различных задач разработки
- `agents/base.py` - Базовый контракт агента
- `agents/registry/` - Реестр агентов времени выполнения
- `agents/token_budget_system.py` - Отслеживание токенов и управление бюджетом
- `agents/llm_api.py` - Унифицированный интерфейс LLM с 18+ провайдерами
- `agents/llm_providers.py` - Реализации для конкретных провайдеров

### Слой оркестратора
- `orchestrator/` - Движок выполнения конвейеров
- `orchestrator/engine.py` - Основной движок конвейера
- `orchestrator/hooks.py` - Хуки конвейера (включая хук памяти)
- `orchestrator/parallel.py` - DAG-выполнение с параллельной обработкой

### Слой RAG и памяти
- `rag/` - Система Retrieval-Augmented Generation
- `rag/memory_store.py` - Интерфейс хранилища памяти
- `rag/memory_collections.py` - Типы записей памяти и коллекции
- `rag/memory_retriever.py` - Интерфейс извлечения памяти
- `rag/context_builder.py` - Построение контекста с интеграцией памяти
- `rag/context_compressor.py` - Сжатие и оптимизация контекста
- `rag/deduplicator.py` - Дедупликация контекста

### Слой хранилища
- `storage/` - Слой persistence данных
- `storage/repositories/` - Репозитории запусков, журналов шагов и артефактов
- `storage/backends.py` - Бэкенды JSON и PostgreSQL

### Слой планировщика
- `scheduler/` - API-шлюз и планирование
- `scheduler/gateway.py` - Шлюз FastAPI
- `scheduler/cron_dispatcher.py` - Диспетчер cron-задач
- `scheduler/task_queue.py` - Система очереди задач

## Конвейеры

### Конвейер функций (Feature Pipeline)
Конвейер выполнения для подготовленных задач:
```
rag_initializer -> memory_retrieval -> specification_passthrough -> subtasks_passthrough ->
bdd_passthrough -> tests_passthrough -> code_generator -> test_runner ->
fix_agent (loop) -> review_agent -> memory_writer -> pr_merge_agent
```

Защитные механизмы в `pr_merge_agent`:
- решение ревью должно быть `approve`
- тесты должны проходить
- PR должен существовать
- в режиме dry-run/no-live `merged=false`

### Конвейер сканера CI (CI Scanner Pipeline)
Анализ сбоев CI и передача:
```
ci_failure_analyzer -> ci_incident_handoff
```
Результат: создает/обновляет задачу инцидента с метками `agent:opened`, `source:ci_scanner_pipeline`, `kind:ci-incident`.

### Конвейер исправления CI (CI Fix Pipeline)
Безопасный для производства конвейер выполнения для инцидентов CI и задач исправления:
```
rag_initializer -> memory_retrieval -> ci_failure_analysis -> specification_passthrough ->
subtasks_passthrough -> bdd_passthrough -> code_generator -> test_runner ->
fix_agent (loop) -> review_agent -> memory_writer -> pr_merge_agent
```

### Конвейер сканера задач (Issue Scanner Pipeline)
Сканирует подготовленные задачи (`agent:opened`, `agent:planning`, `agent:ready`, `agent:fixed`) и отправляет на реализацию:
```
repo_connector -> issue_classification -> issue_dispatch -> feature_pipeline
```
Поведение `issue_dispatch` по меткам:
- `agent:opened` -> установить `agent:planning`, запустить планирование (DoD/BDD/TDD + комментарий планирования), отправить в `feature_pipeline`, установить `agent:ready`.
- `agent:planning` -> запустить планирование снова, затем отправить в `feature_pipeline`.
- `agent:ready` -> отправить в `feature_pipeline` без планирования.
- `agent:fixed` -> проверить связанный объединенный PR и закрыть задачу при корректной связи.

### Конвейер инициализации (Init Pipeline)
Инициализация и настройка репозитория:
```
repo_connector -> rag_initializer -> memory_agent -> architecture_evaluator ->
test_analyzer -> pipeline_initializer
```

### Конвейер генерации кода (Code Generation Pipeline)
Конвейер генерации кода:
```
rag_initializer -> memory_retrieval -> planner -> code_generator -> review -> memory_writer
```

### Конвейер проверки зависимостей (Dependency Check Pipeline)
Конвейер анализа зависимостей:
```
architecture_evaluator -> test_analyzer
```
## Разработка

### Требования
- Python 3.11+
- Docker и docker-compose
- Git

### Настройка
```bash
# Клонировать репозиторий
git clone https://github.com/yxyxy/HordeForge.git
cd HordeForge

# Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # В Windows: .venv\Scripts\activate

# Установить в режиме разработки
pip install -e .
pip install -r requirements-dev.txt

# Настроить окружение
cp .env.example .env
# Отредактировать .env с вашими настройками

# Запустить тесты
make test
make lint
make format
```

### Тестирование
```bash
# Все тесты
make test

# Только unit-тесты
pytest tests/unit/

# Только integration-тесты
pytest tests/integration/

# С покрытием
pytest --cov=. --cov-report=html
```

## Документация

Полная документация доступна в директории `docs/`:
- [Начало работы](docs/get_started.md) - Быстрый старт работы с проектом
- [Архитектура](docs/ARCHITECTURE.md) - Архитектура системы и дизайн
- [Структура репозитория](docs/REPO_STRUCTURE.md) - Организация проекта
- [Спецификация агентов](docs/AGENT_SPEC.md) - Контракты и интерфейсы агентов
- [Агенты](docs/agents.md) - Описание агентов
- [Агенты конвейера функций](docs/feature_pipeline_agents.md) - Агенты feature pipeline
- [Настройка разработки](docs/development_setup.md) - Локальная конфигурация разработки
- [Интерфейс CLI](docs/cli_interface.md) - Инструменты командной строки
- [Интеграция LLM](docs/llm_integration.md) - Поддержка мульти-провайдеров LLM
- [Память агентов](docs/memory_collections.md) - Система памяти и коллекции
- [Построение контекста](docs/context_builder.md) - Построение и управление контекстом
- [Конфигурация RAG](docs/rag_configuration.md) - Настройка RAG-системы
- [Граф конвейера](docs/pipeline_graph.md) - Структура графа конвейеров
- [Память конвейера](docs/pipeline_memory_flow.md) - Поток памяти в конвейерах
- [Конвейеры](docs/pipelines.md) - Описание конвейеров
- [Интеграция планировщика](docs/scheduler_integration.md) - Интеграция планировщика
- [Система бюджетов токенов](docs/token_budget_system.md) - Отслеживание затрат и бюджет
- [Метрики и мониторинг](docs/metrics_and_monitoring.md) - Наблюдаемость и метрики
- [Операционный справочник](docs/operations_runbook.md) - Операционные процедуры
- [Руководство по устранению неполадок](docs/troubleshooting_guide.md) - Разрешение проблем
- [Обеспечение качества](docs/quality_assurance.md) - Стандарты тестирования и качества
- [Справочник API](docs/api_reference.md) - Полная документация API
- [Результаты бенчмарков](docs/benchmark_results.md) - Результаты тестирования производительности
- [Функциональные и нефункциональные требования](docs/FR_NFR.md) - Требования к системе
- [План готовности к запуску](docs/launch_readiness_plan.md) - План подготовки к production
- [Безопасность](docs/security_notes.md) - Заметки по безопасности
- [Варианты использования](docs/use_cases.md) - Сценарии использования
- [Руководство по участию](docs/contributing.md) - Правила участия в проекте

## Участие в проекте

См. [Руководство по участию](docs/contributing.md) для получения инструкций по участию.

## Лицензия

MIT License
