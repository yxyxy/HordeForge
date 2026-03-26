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

### Memory Hook

The memory hook automatically records successful pipeline steps:

```python
from orchestrator.hooks import MemoryHook

# Register the hook in the orchestrator
hook = MemoryHook()
orchestrator.register_hook(hook)
```

The hook automatically captures successful step results and stores them in the appropriate memory collection.

## Benefits

- **Reusability**: Leverages successful past solutions
- **Consistency**: Maintains architectural consistency across tasks
- **Efficiency**: Reduces redundant work by referencing prior implementations
- **Learning**: Improves over time as more solutions are stored

## Memory Entry Types

### Task Entries

Store information about completed tasks:
- task_description: Description of the task
- pipeline: Name of the pipeline that executed the task
- agents_used: List of agents involved
- result_status: Status of the result (SUCCESS, MERGED, etc.)

### Patch Entries

Store information about code changes:
- task_description: Description of the task
- file: Name of the file that was modified
- diff: Text of the changes in diff format
- reason: Reason for the changes

### Decision Entries

Store architectural decisions:
- task_description: Description of the task
- architecture_decision: The architectural decision made
- context: Context in which the decision was made
- result: Outcome/consequences of the decision

## Configuration

Memory system can be configured through environment variables:

- `HORDEFORGE_MEMORY_ENABLED` - Enable/disable memory system
- `HORDEFORGE_MEMORY_RETENTION_DAYS` - How long to retain memory entries
- `HORDEFORGE_MEMORY_SEARCH_LIMIT` - Maximum number of results to return
- `HORDEFORGE_MEMORY_SIMILARITY_THRESHOLD` - Minimum similarity threshold for results

## Security and Privacy

- Memory entries are sanitized before storage
- Sensitive information is filtered out
- Access controls ensure proper isolation between tenants
- Token redaction applied to all stored content

## Performance Considerations

- Efficient vector search for fast retrieval
- Deduplication to avoid storing redundant information
- Context compression to optimize token usage
- Caching for frequently accessed memory entries

## Troubleshooting

Common issues and solutions:

1. **Memory Not Being Recorded**: Check that pipeline steps are completing successfully
2. **Irrelevant Results**: Verify vector search parameters and indexing
3. **Performance Issues**: Check vector database configuration and indexing
4. **Security Concerns**: Verify sanitization and access controls

## Integration with Other Systems

### RAG Integration
Memory context is combined with RAG repository context in the Context Builder, providing agents with both historical solutions and current codebase information.

### Token Budget System
Memory operations are tracked by the Token Budget System to monitor costs associated with vector database queries.

### LLM Integration
Memory context is automatically included in LLM prompts when available, enhancing the quality of generated code and decisions.

## Best Practices

1. **Quality Control**: Only successful pipeline steps are stored in memory to maintain quality
2. **Context Relevance**: Use semantic search to find most relevant historical solutions
3. **Privacy Protection**: Sanitize sensitive information before storing in memory
4. **Performance Optimization**: Use caching and efficient indexing for fast retrieval
5. **Continuous Learning**: Regularly update memory with new successful solutions

## Future Enhancements

- Enhanced semantic search capabilities
- Cross-project memory sharing
- Automated memory cleanup and retention policies
- Advanced analytics on memory usage patterns
- Improved context fusion algorithms
- Memory-based testing and validation
- Enhanced memory categorization and tagging