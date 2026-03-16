# Context Optimization

## Overview

This document describes the context optimization techniques implemented in HordeForge to reduce the size of context sent to LLMs while preserving semantic meaning and important information.

## Components

The context optimization system consists of two main components:

1. **Deduplicator**: Removes duplicate content from context
2. **Context Compressor**: Reduces the size of context to fit within token limits

## Deduplication

The deduplication process removes redundant information from the context to reduce its size without losing important information.

### Exact Match Deduplication

The system identifies and removes exact duplicates from lists of strings or chunks of content. This is particularly useful for:

- Removing duplicate code snippets retrieved from RAG
- Eliminating repeated documentation sections
- Filtering out redundant memory entries

### Implementation

The `Deduplicator` class provides methods for deduplicating different types of data:

- `deduplicate_list()`: Removes duplicates from a list of strings
- `deduplicate_chunks()`: Removes duplicates from a list of content chunks

## Compression

The compression process reduces the size of context to fit within specified token limits while preserving essential information.

### Token Limit Enforcement

The `ContextCompressor` class enforces maximum token limits by:

1. Estimating the token count of the input text
2. Applying deduplication to remove redundant information
3. Truncating content if necessary while preserving structural integrity

### Structure Preservation

During compression, the system attempts to preserve the structure of the content:

- Code blocks maintain their formatting
- Function signatures remain intact
- Important semantic elements are preserved

## Usage in Pipelines

The context optimization components are integrated into the pipeline flow:

1. Before sending context to the LLM, the system applies deduplication
2. The compressed context is then validated against token limits
3. If needed, additional compression is applied to meet requirements

## Benefits

- **Reduced Costs**: Smaller contexts mean lower token usage and costs
- **Improved Performance**: Faster processing times for LLM interactions
- **Maintained Quality**: Semantic meaning preserved despite size reduction
- **Scalability**: Enables handling of larger codebases and knowledge bases