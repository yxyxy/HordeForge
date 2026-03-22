# Подзадача P16.5: Интеграция провайдеров из Cline

## Описание
Добавить поддержку всех провайдеров из Cline в LLM wrapper HordeForge с полной совместимостью

## Приоритет
HIGH

## Технические детали

### 1. Подготовка архитектуры
- [ ] Обновить интерфейс ApiHandler для совместимости с Cline
- [ ] Добавить типы для обработки сообщений и стриминга
- [ ] Реализовать систему retry с обратными вызовами
- [ ] Добавить поддержку инструментов (tools) как в Cline

### 2. Интеграция провайдеров
Источник: https://github.com/cline/cline/tree/71e312e92a526488e3fb002c8771d4577cd31779/src/core/api/providers

- [ ] Ollama - https://github.com/cline/cline/blob/main/src/core/api/providers/ollama.ts
- [ ] Gemini - https://github.com/cline/cline/blob/main/src/core/api/providers/gemini.ts  
- [ ] OpenRouter - https://github.com/cline/cline/blob/main/src/core/api/providers/openrouter.ts
- [ ] AWS Bedrock - https://github.com/cline/cline/blob/main/src/core/api/providers/bedrock.ts
- [ ] Vertex AI - https://github.com/cline/cline/blob/main/src/core/api/providers/vertex.ts
- [ ] LM Studio - https://github.com/cline/cline/blob/main/src/core/api/providers/lmstudio.ts
- [ ] DeepSeek - https://github.com/cline/cline/blob/main/src/core/api/providers/deepseek.ts
- [ ] Fireworks - https://github.com/cline/cline/blob/main/src/core/api/providers/fireworks.ts
- [ ] Together AI - https://github.com/cline/cline/blob/main/src/core/api/providers/together.ts
- [ ] Qwen - https://github.com/cline/cline/blob/main/src/core/api/providers/qwen.ts
- [ ] Mistral - https://github.com/cline/cline/blob/main/src/core/api/providers/mistral.ts
- [ ] Hugging Face - https://github.com/cline/cline/blob/main/src/core/api/providers/huggingface.ts
- [ ] LiteLLM - https://github.com/cline/cline/blob/main/src/core/api/providers/litellm.ts
- [ ] Moonshot - https://github.com/cline/cline/blob/main/src/core/api/providers/moonshot.ts
- [ ] Groq - https://github.com/cline/cline/blob/main/src/core/api/providers/groq.ts
- [ ] Claude Code - https://github.com/cline/cline/blob/main/src/core/api/providers/claude-code.ts
- [ ] и другие провайдеры из Cline

### 3. Тестирование
- [ ] Написать тесты для каждого нового провайдера
- [ ] Проверить стриминг для каждого провайдера
- [ ] Проверить поддержку инструментов
- [ ] Проверить обработку ошибок

## Критерии готовности (DoD)
- [ ] Все провайдеры из Cline интегрированы
- [ ] Каждый провайдер поддерживает стриминг
- [ ] Каждый провайдер поддерживает инструменты
- [ ] Тесты проходят для всех провайдеров
- [ ] Обработка ошибок работает корректно

## Риски
- Сложность интеграции большого количества провайдеров
- Совместимость с существующей архитектурой
- Различия в API между версиями библиотек

## Комментарии
Важно обеспечить полную совместимость с Cline для возможности легкого импорта обновлений провайдеров в будущем.