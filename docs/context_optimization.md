# Context Optimization

## Overview

This document describes the context optimization techniques implemented in HordeForge to reduce the size of context sent to LLMs while preserving semantic meaning and important information. The system includes deduplication, compression, and memory management to optimize token usage and reduce costs.

## Components

The context optimization system consists of several main components:

1. **Deduplicator**: Removes duplicate content from context
2. **Context Compressor**: Reduces the size of context to fit within token limits
3. **Memory Collections**: Stores historical solutions for context reuse
4. **Context Builder**: Combines memory and repository context
5. **RAG Integration**: Optimizes retrieval from documentation and codebase

## Deduplication

The deduplication process removes redundant information from the context to reduce its size without losing important information.

### Exact Match Deduplication

The system identifies and removes exact duplicates from lists of strings or chunks of content. This is particularly useful for:

- Removing duplicate code snippets retrieved from RAG
- Eliminating repeated documentation sections
- Filtering out redundant memory entries

### Semantic Deduplication

Beyond exact matches, the system also identifies semantically similar content and removes redundancies while preserving unique information.

### Implementation

The `Deduplicator` class provides methods for deduplicating different types of data:

- `deduplicate_list()`: Removes duplicates from a list of strings
- `deduplicate_chunks()`: Removes duplicates from a list of content chunks
- `remove_redundant_context()`: Removes overlapping information between different context sources

## Compression

The compression process reduces the size of context to fit within specified token limits while preserving essential information.

### Token Limit Enforcement

The `ContextCompressor` class enforces maximum token limits by:

1. Estimating the token count of the input text
2. Applying deduplication to remove redundant information
3. Truncating content if necessary while preserving structural integrity

### Semantic Compression

Rather than simple truncation, the system employs semantic compression techniques:

- Identifying and preserving key semantic elements
- Removing less important details while keeping core meaning
- Maintaining code structure and function signatures

### Structure Preservation

During compression, the system attempts to preserve the structure of the content:

- Code blocks maintain their formatting
- Function signatures remain intact
- Important semantic elements are preserved
- Hierarchical organization is maintained

## Memory Integration

The system leverages agent memory to optimize context by:

### Historical Solution Retrieval

- Retrieving similar past solutions from memory collections
- Using proven patterns and approaches
- Avoiding repetition of previous work

### Context Caching

- Storing frequently accessed context in memory
- Reducing redundant retrieval operations
- Improving response times for similar queries

### Pattern Recognition

- Identifying recurring patterns in historical solutions
- Using these patterns to optimize current context
- Applying proven strategies to new problems

## Context Building

The Context Builder component combines multiple sources of information:

### Memory and RAG Integration

The system intelligently combines:
- Historical solutions from memory collections
- Current repository context from RAG
- Real-time information from active processes

### Adaptive Context Assembly

The system adapts the context based on:
- Query requirements and intent
- Available token budget
- Relevance of different information sources
- Priority of different context types

## RAG Optimization

The system optimizes RAG (Retrieval Augmented Generation) operations:

### Intelligent Retrieval

- Semantic search to find most relevant documents
- Context-aware ranking of retrieved information
- Filtering out irrelevant or low-quality results

### Chunk Optimization

- Smart chunking to maintain semantic coherence
- Overlap management to preserve context
- Size optimization for efficient processing

### Indexing Strategies

- Multiple indexing strategies for different content types
- Keyword and vector indexing for comprehensive search
- Hierarchical indexing for efficient navigation

## Performance Benefits

### Cost Reduction

- Significant reduction in token usage
- Lower API costs for LLM operations
- More efficient resource utilization

### Performance Improvement

- Faster processing times for LLM interactions
- Reduced latency in response generation
- Better throughput for concurrent operations

### Quality Maintenance

- Preserved semantic meaning despite size reduction
- Maintained code quality and correctness
- Consistent information accuracy

## Configuration

The context optimization system can be configured through environment variables:

- `HORDEFORGE_CONTEXT_MAX_TOKENS` - Maximum tokens allowed in context
- `HORDEFORGE_CONTEXT_COMPRESSION_LEVEL` - Level of compression (0-10)
- `HORDEFORGE_CONTEXT_DEDUPE_ENABLED` - Enable/disable deduplication
- `HORDEFORGE_CONTEXT_MEMORY_ENABLED` - Enable/disable memory integration
- `HORDEFORGE_CONTEXT_RAG_ENABLED` - Enable/disable RAG integration

## API Reference

### Context Optimization
```python
from rag.context_compressor import ContextCompressor
from rag.deduplicator import Deduplicator
from rag.context_builder import ContextBuilder

# Compress context to fit within token limits
compressor = ContextCompressor(max_tokens=4000)
compressed_context = compressor.compress(original_context)

# Remove duplicates from context
deduplicator = Deduplicator()
cleaned_context = deduplicator.deduplicate_list(context_list)

# Build optimized context from multiple sources
builder = ContextBuilder(memory_retriever, rag_retriever)
optimized_context = builder.build_agent_context(query=query, max_tokens=3000)
```

### Memory Integration
```python
from rag.memory_retriever import MemoryRetriever

# Retrieve relevant historical solutions
memory_retriever = MemoryRetriever()
historical_solutions = memory_retriever.search_similar_solutions(query, limit=5)
```

## Best Practices

### Context Optimization

1. **Prioritize Information**: Place most important information first in context
2. **Use Semantic Chunks**: Organize context in semantically coherent chunks
3. **Monitor Token Usage**: Regularly check token usage to optimize appropriately
4. **Balance Compression and Quality**: Don't over-compress at the expense of meaning

### Memory Utilization

1. **Regular Updates**: Keep memory collections updated with successful solutions
2. **Quality Control**: Only store high-quality, successful solutions in memory
3. **Relevance Matching**: Use semantic similarity to find most relevant memories
4. **Retention Policies**: Implement appropriate retention policies for memory entries

### Performance Tuning

1. **Adjust Compression Levels**: Tune compression based on specific use cases
2. **Optimize Retrieval**: Fine-tune RAG retrieval parameters for best results
3. **Monitor Costs**: Track token usage and costs regularly
4. **Iterative Improvement**: Continuously refine optimization strategies

## Troubleshooting

### Common Issues

1. **Over-Compression**: If meaning is lost, reduce compression level
2. **Under-Utilization**: If token limits aren't being met, increase compression
3. **Relevance Issues**: If retrieved context isn't relevant, adjust search parameters
4. **Performance Problems**: If optimization is too slow, consider caching strategies

### Monitoring

- Track token usage before and after optimization
- Monitor response quality metrics
- Measure performance improvements
- Watch for any degradation in solution quality

## Future Enhancements

- Advanced semantic compression algorithms
- Machine learning-based context optimization
- Dynamic token allocation based on query complexity
- Enhanced memory pattern recognition
- Cross-project context optimization
- Real-time performance adaptation