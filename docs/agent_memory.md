# Agent Memory System

## Overview

The Agent Memory system is a critical component of HordeForge that enables agents to leverage historical solutions and patterns for more effective and consistent development. The system stores and retrieves information about previous tasks, patches, and architectural decisions, allowing agents to learn from past experiences and avoid repeating mistakes.

## Architecture

### System Components

1. **Memory Collections** - specialized collections in the vector database for different types of memory:
   - `memory_tasks` - information about completed tasks
   - `memory_patches` - code patches and changes
   - `memory_decisions` - architectural and design decisions

2. **Memory Store** - interface for storing and retrieving memory entries from the vector database

3. **Memory Hook** - component that automatically records successful pipeline steps to memory

4. **Memory Retriever** - component for searching relevant historical entries

5. **Context Builder** - combines memory context with repository context from RAG

### Memory Entry Types

The system supports three main types of memory entries:

#### Task Entry
Stores information about completed tasks:
- task_description: Description of the task
- pipeline: Name of the pipeline that executed the task
- agents_used: List of agents involved
- result_status: Status of the result (SUCCESS, MERGED, etc.)

#### Patch Entry
Stores information about code changes:
- task_description: Description of the task
- file: Name of the file that was modified
- diff: Text of the changes in diff format
- reason: Reason for the changes

#### Decision Entry
Stores architectural decisions:
- task_description: Description of the task
- architecture_decision: The architectural decision made
- context: Context in which the decision was made
- result: Outcome/consequences of the decision

## Implementation Details

### Automatic Memory Recording

The Memory Hook automatically records successful pipeline steps after execution. This happens only for successful steps (with status SUCCESS, MERGED, etc.) to ensure quality of stored information.

#### Integration with Orchestrator Engine

The Memory Hook is integrated into the Orchestrator Engine and is triggered after each successful step. This ensures automatic population of memory with successful solutions.

### Memory Retrieval

Agents can retrieve relevant historical information by:
1. Searching for similar tasks in memory collections
2. Using vector similarity to find relevant past solutions
3. Combining memory context with current repository context

### Context Building

The Context Builder combines:
- Historical solutions from memory (Previous solutions)
- Current repository context from RAG (Repository context)

This allows agents to use both historical experience and current codebase information.

## Usage in Agents

### Search for Similar Solutions

Agents can search memory for similar past solutions:
- Find previous implementations of similar features
- Use proven patterns and approaches
- Avoid repeating past mistakes

### Context Enhancement

Memory context is automatically included in agent prompts when available, enhancing the quality of generated code and decisions.

## Security and Privacy

- Memory entries are sanitized before storage
- Sensitive information is filtered out
- Access controls ensure proper isolation between tenants

## Performance Considerations

- Efficient vector search for fast retrieval
- Deduplication to avoid storing redundant information
- Context compression to optimize token usage
- Caching for frequently accessed memory entries

## Integration with Other Systems

### RAG Integration
Memory context is combined with RAG repository context in the Context Builder, providing agents with both historical solutions and current codebase information.

### Token Budget System
Memory operations are tracked by the Token Budget System to monitor costs associated with vector database queries.

### Pipeline Integration
Memory hooks are integrated into pipeline execution to automatically capture successful solutions.

## Best Practices

1. **Quality Control**: Only successful pipeline steps are stored in memory to maintain quality
2. **Context Relevance**: Use semantic search to find most relevant historical solutions
3. **Privacy Protection**: Sanitize sensitive information before storing in memory
4. **Performance Optimization**: Use caching and efficient indexing for fast retrieval
5. **Continuous Learning**: Regularly update memory with new successful solutions

## Troubleshooting

Common issues and solutions:

1. **Memory Not Being Recorded**: Check that pipeline steps are completing successfully
2. **Irrelevant Results**: Verify vector search parameters and indexing
3. **Performance Issues**: Check vector database configuration and indexing
4. **Security Concerns**: Verify sanitization and access controls

## Future Enhancements

- Enhanced semantic search capabilities
- Cross-project memory sharing
- Automated memory cleanup and retention policies
- Advanced analytics on memory usage patterns
- Improved context fusion algorithms

## Configuration

Memory system can be configured through environment variables:
- `HORDEFORGE_MEMORY_ENABLED` - Enable/disable memory system
- `HORDEFORGE_MEMORY_RETENTION_DAYS` - How long to retain memory entries
- `HORDEFORGE_MEMORY_SEARCH_LIMIT` - Maximum number of results to return
- `HORDEFORGE_MEMORY_SIMILARITY_THRESHOLD` - Minimum similarity threshold for results

## API Reference

### Memory Retrieval
```python
from rag.memory_retriever import MemoryRetriever

retriever = MemoryRetriever()
similar_tasks = retriever.search_similar_tasks(query, limit=5)
```

### Memory Storage
```python
from rag.memory_store import MemoryStore
from rag.memory_collections import create_memory_entry

# Create and store a memory entry
entry = create_memory_entry("task", task_description="...", result_status="SUCCESS")
store = MemoryStore()
store.save(entry)
```

### Context Building
```python
from rag.context_builder import ContextBuilder

builder = ContextBuilder(memory_retriever, rag_retriever)
agent_context = builder.build_agent_context(query=query, max_memory_entries=5, max_rag_chunks=10)