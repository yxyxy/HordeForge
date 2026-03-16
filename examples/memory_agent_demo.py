#!/usr/bin/env python3
"""
Демонстрация функциональности Memory Agent
"""

from agents.memory_agent import retrieve_context, setup_memory, store_context


def main():
    print("=== Демонстрация Memory Agent ===\n")

    # 1. Инициализация хранилища памяти
    print("1. Инициализация хранилища памяти...")
    config = {"type": "json", "file_path": ".hordeforge_data/demo_memory.json"}
    result = setup_memory(config)
    print(f"   Результат: {result}\n")

    # 2. Сохранение контекста
    print("2. Сохранение контекста...")
    context_data = {
        "session_id": "sess_001",
        "user_id": "user_123",
        "conversation_history": [
            {"role": "user", "message": "Привет!"},
            {"role": "agent", "message": "Здравствуйте! Чем могу помочь?"},
        ],
        "timestamp": "2026-03-12T09:0:00Z",
        "metadata": {"source": "chat", "priority": "normal"},
    }

    store_result = store_context(context_data)
    print(f"   Контекст сохранен: {store_result}\n")

    # 3. Извлечение контекста
    print("3. Извлечение контекста...")
    context_id = store_result["context_id"]
    retrieve_result = retrieve_context(context_id)
    print(f"   Результат извлечения: {retrieve_result['status']}")
    if retrieve_result["status"] == "success":
        print(f"   Извлеченный контекст: {retrieve_result['context']}\n")

    # 4. Попытка извлечения несуществующего контекста
    print("4. Попытка извлечения несуществующего контекста...")
    nonexistent_result = retrieve_context("nonexistent_id")
    print(f"   Результат: {nonexistent_result}\n")

    # 5. Сохранение еще одного контекста
    print("5. Сохранение дополнительного контекста...")
    context_data2 = {
        "session_id": "sess_002",
        "user_id": "user_456",
        "task_info": "Решение задачи по оптимизации кода",
        "progress": 0.75,
        "deadline": "2026-03-15T18:00:00Z",
    }

    store_result2 = store_context(context_data2)
    print(f"   Второй контекст сохранен: {store_result2}\n")

    # 6. Извлечение второго контекста
    print("6. Извлечение второго контекста...")
    context_id2 = store_result2["context_id"]
    retrieve_result2 = retrieve_context(context_id2)
    print(f"   Результат извлечения: {retrieve_result2['status']}")
    if retrieve_result2["status"] == "success":
        print(f"   Извлеченный контекст: {retrieve_result2['context']}\n")

    print("=== Демонстрация завершена ===")


if __name__ == "__main__":
    main()
