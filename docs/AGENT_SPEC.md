# Agent Specification

Этот документ определяет обязательный контракт для всех агентов HordeForge.

## 1. Цель контракта

Контракт нужен для:

- единообразного вызова агентов orchestrator-ом
- предсказуемых результатов
- schema-валидации и retry политики

## 2. Обязательный интерфейс

```python
class Agent:
    name: str
    description: str

    def run(self, context: dict) -> dict:
        ...
```

Минимально допустимый вход: `context: dict`.

## 3. AgentResult (обязательная структура)

```json
{
  "status": "SUCCESS",
  "artifacts": [],
  "decisions": [],
  "logs": [],
  "next_actions": []
}
```

### Поля

- `status` — одно из: `SUCCESS`, `PARTIAL_SUCCESS`, `FAILED`, `BLOCKED`
- `artifacts` — список артефактов шага
- `decisions` — ключевые инженерные решения
- `logs` — диагностические сообщения
- `next_actions` — рекомендуемые следующие шаги

## 4. Artifact format

```json
{
  "type": "specification",
  "path": "artifacts/specification/feature_x.md",
  "content": "...",
  "metadata": {
    "source": "issue#123"
  }
}
```

## 5. Decision format

```json
{
  "reason": "Выбран подход X, потому что...",
  "confidence": 0.82
}
```

## 6. Ошибки и блокировки

Если агент не может продолжать выполнение:

```json
{
  "status": "BLOCKED",
  "artifacts": [],
  "decisions": [
    {
      "reason": "Missing repository context",
      "confidence": 1.0
    }
  ],
  "logs": ["Required file not found: ..."],
  "next_actions": ["request_human_input"]
}
```

## 7. Правила детерминизма

- фиксированный output schema
- запрет скрытых полей в результате
- ограниченный уровень случайности в LLM-вызовах

## 8. Совместимость с pipeline runner

Текущий раннер ожидает:

1. module name == `agent` в pipeline yaml
2. класс по имени из `snake_case -> CamelCase`
3. метод `run(...)`

Пример:

- `agent: test_generator`
- файл: `agents/test_generator.py`
- класс: `TestGenerator`

## 9. Регистрация агентов (целевая)

Вместо неявного dynamic import рекомендуется registry:

```python
AGENT_REGISTRY = {
    "dod_extractor": DoDExtractor,
    "test_generator": TestGenerator,
}
```

До внедрения registry надо соблюдать naming conventions из раздела 8.

## 10. Тестирование агентов

Минимум для каждого MVP-агента:

1. valid input -> `SUCCESS`
2. missing required context -> `BLOCKED`
3. invalid output format -> `FAILED`

## 11. Безопасность

Агенты не должны:

- логировать секреты
- пушить изменения напрямую в protected branch
- исполнять произвольные shell-команды без policy контроля

## 12. Definition of Done для нового агента

Новый агент считается готовым, если:

1. есть модуль агента и класс с `run(...)`
2. есть schema (при необходимости)
3. подключен в pipeline
4. добавлены тесты
5. обновлена документация (`features.md`, `use_cases.md` при необходимости)
