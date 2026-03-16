# Agent Specification

Этот документ определяет обязательный контракт для всех агентов HordeForge.

## 1. Цель контракта

Контракт нужен для:

- единообразного вызова агентов orchestrator-ом
- предсказуемых результатов
- schema-валидации и retry политики

## 2. Обязательный интерфейс

```python
from agents.base import BaseAgent

class Agent(BaseAgent):
    name: str
    description: str

    def run(self, context: dict) -> dict:
        ...
```

Минимально допустимый вход: `context: dict`.
Базовый контракт реализован в `agents/base.py::BaseAgent`.

## 3. AgentResult (обязательная структура)

```json
{
  "schema_version": "1.0",
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
- `schema_version` — опционально, если указан, должен быть `"1.0"` (см. `contracts/schemas/agent_result.v1.schema.json`)
- `validation_errors` — опционально, список ошибок валидации (для non-strict режима)
- `test_results` — опционально, агрегированные результаты тестов

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

### Привязка к схемам контрактов

Runtime валидирует `artifacts[*].content` по JSON-схемам из `contracts/schemas/`.
Текущая карта типов артефактов:

- `dod` → `context.dod.v1.schema.json`
- `spec` → `context.spec.v1.schema.json`
- `tests` → `context.tests.v1.schema.json`
- `code_patch` → `context.code_patch.v1.schema.json`

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

Текущий раннер разрешает агенты через реестр (`agents/registry/`), а не через dynamic import.

Ожидания:

1. `agent` в YAML должен быть зарегистрирован в `agents/registry`.
2. класс агента наследует `BaseAgent` и реализует `run(...)`.

Пример:

- `agent: test_generator`
- файл: `agents/test_generator.py`
- класс: `TestGenerator` (имя класса свободно, но единообразие желательно)

## 9. Регистрация агентов (целевая)

В проекте есть два уровня реестров:

### Runtime-реестр (используется orchestrator)

```python
from agents.registry import AGENT_REGISTRY, register_default_agents

register_default_agents()  # заполняет runtime mapping
```

### Metadata-реестр (контракты, категории, валидация)

```python
from registry.agents import AgentRegistry, AgentMetadata
from registry.contracts import ContractRegistry
from registry.agent_category import AgentCategory

contract_registry = ContractRegistry()
contract_registry.autoload_schemas()

agent_registry = AgentRegistry(contract_registry=contract_registry)
agent_registry.register(
    AgentMetadata(
        name="dod_extractor",
        agent_class=DodExtractor,
        input_contract="context.dod.v1",
        output_contract="context.dod.v1",
        category=AgentCategory.PLANNING,
    )
)
```

Metadata-реестр используется для валидации контрактов и генерации документации.

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
