# Quick Start

## Требования

- Python 3.10+
- (Опционально) Docker для PostgreSQL и Redis

## 1. Установка

```bash
# Клонировать репозиторий
git clone <repo-url>
cd HordeForge

# Установить зависимости
pip install -r requirements-dev.txt
```

## 2. Конфигурация

```bash
# Скопировать пример конфигурации
cp .env.example .env

# Отредактировать .env при необходимости
# Минимальная конфигурация уже есть в .env.example
```

### Основные переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `HORDEFORGE_GATEWAY_URL` | http://localhost:8000 | URL gateway |
| `HORDEFORGE_STORAGE_DIR` | .hordeforge_data | Директория для данных |
| `HORDEFORGE_OPERATOR_API_KEY` | local-operator-key | Ключ для ручного управления |
| `HORDEFORGE_PIPELINES_DIR` | pipelines | Директория с pipeline |
| `HORDEFORGE_RULES_DIR` | rules | Директория с правилами |

## 3. Запуск

### Локальный запуск (рекомендуется для разработки)

```bash
uvicorn scheduler.gateway:app --host 0.0.0.0 --port 8000 --reload
```

### Docker запуск

```bash
docker compose up --build
```

## 4. Проверка работоспособности

```bash
# Проверить health endpoint
curl http://localhost:8000/health

# Проверить метрики
curl http://localhost:8000/metrics
```

## 5. Запуск pipeline

### Через CLI

```bash
python cli.py init --repo-url <GITHUB_URL> --token <GITHUB_TOKEN>
```

### Через API

```bash
curl -X POST http://localhost:8000/run-pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_name": "init_pipeline",
    "inputs": {"repo_url": "<GITHUB_URL>", "github_token": "<TOKEN>"}
  }'
```

### Проверка статуса

```bash
# Получить список запусков
curl http://localhost:8000/runs

# Получить конкретный запуск
curl http://localhost:8000/runs/<run_id>
```

## 6. Ручное управление

```bash
# Остановить запущенный pipeline
curl -X POST http://localhost:8000/runs/<run_id>/override \
  -H "Content-Type: application/json" \
  -H "X-Operator-Key: local-operator-key" \
  -H "X-Operator-Role: operator" \
  -H "X-Command-Source: api" \
  -d '{"action": "stop", "reason": "Manual stop"}'

# Повторить неудачный запуск
curl -X POST http://localhost:8000/runs/<run_id>/override \
  -H "Content-Type: application/json" \
  -H "X-Operator-Key: local-operator-key" \
  -H "X-Operator-Role: operator" \
  -H "X-Command-Source: api" \
  -d '{"action": "retry"}'
```

## 7. Опциональные компоненты

### LLM агенты (для AI-функциональности)

```bash
# OpenAI
HORDEFORGE_LLM_PROVIDER=openai
HORDEFORGE_OPENAI_API_KEY=sk-...

# Anthropic
HORDEFORGE_LLM_PROVIDER=anthropic
HORDEFORGE_ANTHROPIC_API_KEY=sk-ant-...

# Google GenAI
HORDEFORGE_LLM_PROVIDER=google
HORDEFORGE_GOOGLE_API_KEY=your-key
```

### Базы данных (production)

```bash
# PostgreSQL для storage
HORDEFORGE_STORAGE_BACKEND=postgres
HORDEFORGE_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/hordeforge

# Redis для queue
HORDEFORGE_QUEUE_BACKEND=redis
HORDEFORGE_REDIS_URL=redis://localhost:6379/0
```

### RAG (векторное хранилище)

```bash
# Режим работы векторного хранилища: local, host или auto (по умолчанию)
HORDEFORGE_VECTOR_STORE_MODE=auto

# Хост и порт для внешнего Qdrant (используется в режимах host и auto)
QDRANT_HOST=qdrant
QDRANT_PORT=6333
```

### Метрики

```bash
# Prometheus Pushgateway
HORDEFORGE_METRICS_EXPORTER=prometheus_pushgateway
HORDEFORGE_PROMETHEUS_PUSHGATEWAY_URL=http://localhost:9091
HORDEFORGE_METRICS_EXPORT_INTERVAL_SECONDS=60

# Datadog
HORDEFORGE_METRICS_EXPORTER=datadog
HORDEFORGE_DATADOG_API_KEY=your-api-key
HORDEFORGE_DATADOG_SITE=datadoghq.com
```

### Аутентификация (JWT)

```bash
HORDEFORGE_AUTH_ENABLED=true
HORDEFORGE_JWT_SECRET_KEY=your-secret-key
HORDEFORGE_JWT_ALGORITHM=HS256
```

## 8. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check |
| POST | `/run-pipeline` | Запуск pipeline |
| GET | `/runs` | Список запусков |
| GET | `/runs/{run_id}` | Статус запуска |
| POST | `/runs/{run_id}/override` | Ручное управление |
| GET | `/queue/tasks/{task_id}` | Статус задачи в очереди |
| POST | `/queue/drain` | Обработка очереди |
| GET | `/cron/jobs` | Список cron задач |
| POST | `/cron/run-due` | Запуск due задач |
| POST | `/cron/jobs/{job_name}/trigger` | Триггер задачи |
| GET | `/metrics` | Prometheus метрики |
| POST | `/metrics/export` | Экспорт метрик |
| POST | `/webhooks/github` | GitHub webhook |

## 9. Что делать дальше

1. Выбрать scaffold-агента из `agents/` и заменить его production-реализацией
2. Настроить LLM провайдер для AI-агентов
3. Запустить полноценный feature pipeline
4. Добавить тесты

## Troubleshooting

### Ошибка импорта

```bash
# Убедитесь, что все зависимости установлены
pip install -r requirements-dev.txt
```

### Gateway не запускается

```bash
# Проверьте .env файл
cat .env

# Проверьте порт
lsof -i :8000
```

### Pipeline не выполняется

```bash
# Проверьте логи
curl http://localhost:8000/runs/<run_id>
```
