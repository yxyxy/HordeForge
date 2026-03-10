# Migrations

Актуальные миграции Alembic хранятся в `migrations/`.

## Настройка

Задайте переменную окружения:

```bash
HORDEFORGE_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/hordeforge
```

## Команды

```bash
alembic upgrade head
alembic downgrade -1
alembic current
```

## Seed миграции

Seed выполняется в ревизии `20260310_02` и сохраняет содержимое файлов из `pipelines/` и `rules/`
в таблицу `artifacts` с `run_id=seed:default`.
