# Pipeline Memory Flow

## Overview

This document describes the flow of memory integration in the HordeForge pipelines. With the introduction of Agent Memory, the system now leverages historical solutions to improve code generation quality and consistency.

## Architecture

The memory system consists of three main components:

1. **Memory Collections**: Separate collections for different types of memory
2. **Memory Store**: Interface for storing and retrieving memory entries
3. **Context Builder**: Merges memory context with repository context

### Memory Collections

The system maintains three distinct memory collections:

- `memory_tasks`: Historical task descriptions and outcomes
- `memory_patches`: Previous code patches and their contexts
- `memory_decisions`: Architectural decisions and their rationales

### Memory Flow in Pipeline

```
task
 │
 ▼
memory retrieval
 │
 ├─ similar tasks
 ├─ previous patches
 └─ architecture decisions
 │
 ▼
context builder
 │
 ▼
LLM
```

## Pipeline Integration

### Code Generation Pipeline

The `code_generation.yaml` pipeline includes the following memory-related steps:

1. `memory_retrieval` - searches for similar tasks in memory
2. `memory_writer` - saves successful results to memory

### Feature Pipeline Updates

The `feature_pipeline.yaml` was updated to include:

1. `memory_retrieval` step after `rag_initializer`
2. Memory context passed to `architecture_planner` and `code_generator`
3. `memory_writer` step after `review_agent`

## Implementation Details

### Memory Retrieval

The memory retrieval step uses vector similarity to find relevant past solutions:

```python
def search_memory(query, limit=3):
    vector = embedder.embed_query(query)
    return client.search(
        collection_name="agent_memory",
        query_vector=vector,
        limit=limit
    )
```

### Context Building

The context builder merges memory context with repository context:

```python
def build_agent_context(query):
    memory = memory_retriever.retrieve(query)
    code_context = rag_retriever.retrieve(query)
    return f"""
Previous solutions:

{memory}

Repository context:

{code_context}
"""
```

## Benefits

- **Reusability**: Leverages successful past solutions
- **Consistency**: Maintains architectural consistency across tasks
- **Efficiency**: Reduces redundant work by referencing prior implementations
- **Learning**: Improves over time as more solutions are stored