PS> cd D:\Projects\HordeForge; python -c "from scheduler.gateway import app; print('Gateway OK')"# Get Started

Документ для первичного запуска текущего скелета HordeForge.

## 1. Что важно понимать заранее

Репозиторий находится в стадии skeleton/MVP bootstrap:

- часть компонентов работает только как каркас
- pipeline-файлы описаны шире, чем текущая реализация агентов

Этот onboarding предназначен для разработки платформы, а не для production использования.

## 2. Предварительные требования

1. Python 3.10+
2. Docker Desktop (для docker-ready запуска)
3. Доступ к GitHub token (для ручных тестов интеграции)
4. Установленные зависимости из `requirements-dev.txt`

## 3. Установка

```bash
pip install -r requirements-dev.txt
```

## 4. Запуск gateway

```bash
uvicorn scheduler.gateway:app --host 0.0.0.0 --port 8000
```

Проверка health:

```bash
curl http://localhost:8000/health
```

## 5. Docker-ready запуск

```bash
cp .env.example .env
docker compose up --build
```

`.env.example` содержит базовый policy переменных окружения для `RunConfig`:

- `HORDEFORGE_GATEWAY_URL`
- `HORDEFORGE_PIPELINES_DIR`
- `HORDEFORGE_RULES_DIR`
- `HORDEFORGE_RULE_SET_VERSION`
- `HORDEFORGE_REQUEST_TIMEOUT_SECONDS`
- `HORDEFORGE_STATUS_TIMEOUT_SECONDS`
- `HORDEFORGE_HEALTH_TIMEOUT_SECONDS`
- `HORDEFORGE_MAX_PARALLEL_WORKERS`

## 6. Запуск CLI

```bash
python cli.py init --repo-url <GITHUB_URL> --token <GITHUB_TOKEN>
```

## 7. Проверка результата

Ожидаемое поведение:

- gateway принимает запрос
- orchestrator выполняет pipeline с полным lifecycle
- агенты возвращают результаты с валидацией
- результаты записываются в storage и доступны через API

Все MVP агенты реализованы:
- `dod_extractor`, `specification_writer`, `task_decomposer`
- `test_generator`, `code_generator`, `fix_agent`
- `review_agent`, `pr_merge_agent`, `ci_failure_analyzer`
- И многие другие

## 8. Рекомендуемый workflow разработки

1. Реализовать агентный модуль.
2. Подключить его в pipeline.
3. Проверить локальный запуск pipeline.
4. Добавить тесты и обновить документацию.

## 9. Типовые проблемы

- `ImportError` на агенте: нет файла `agents/<agent_name>.py` (для новых шагов).
- `AttributeError` на классе: имя класса не совпадает с `snake_case -> CamelCase` правилом.
- `docker compose build` падает: Docker Engine не запущен.
- невалидный output агента: нет обязательных полей `AgentResult`.

## 10. Что читать дальше

- `docs/ARCHITECTURE.md`
- `docs/AGENT_SPEC.md`
- `docs/FR_NFR.md`
- `docs/quick_start.md`
- `docs/development_setup.md`
