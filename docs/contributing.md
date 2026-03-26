# Contributing to HordeForge

## Overview

This document explains how to contribute to the HordeForge project. We welcome contributions from the community and appreciate your interest in improving the system.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Setup](#development-setup)
3. [Coding Standards](#coding-standards)
4. [Testing Guidelines](#testing-guidelines)
5. [Pull Request Process](#pull-request-process)
6. [Issue Reporting](#issue-reporting)
7. [Documentation](#documentation)
8. [Community Guidelines](#community-guidelines)

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Docker and Docker Compose
- Git
- A GitHub account

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/HordeForge.git
   cd HordeForge
   ```
3. Add upstream remote:
   ```bash
   git remote add upstream https://github.com/yourusername/HordeForge.git
   ```

## Development Setup

### Environment Setup

1. Create virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install in development mode:
   ```bash
   pip install -e .
   pip install -r requirements-dev.txt
   ```

3. Set up pre-commit hooks:
   ```bash
   pre-commit install
   ```

### Configuration

Copy and customize the environment file:
```bash
cp .env.example .env
# Edit .env with your settings
```

## Coding Standards

### Python Standards

Follow PEP 8 with these project-specific rules:

- Line length: 100 characters
- Use type hints for all functions
- Write docstrings for all public methods
- Use meaningful variable names
- Keep functions under 50 lines when possible

### Code Structure

#### Agent Development
```python
from agents.base import BaseAgent
from agents.token_budget_system import TokenUsage, TokenBudgetSystem

class NewAgent(BaseAgent):
    """Agent for specific task."""
    
    name = "new_agent"
    description = "Description of what this agent does"
    
    def run(self, context: dict) -> dict:
        """Execute the agent's main function.
        
        Args:
            context: Input context with required fields
            
        Returns:
            Dictionary with standardized result format
        """
        # Validate inputs
        self.validate_inputs(context, ["required_field"])
        
        # Initialize token budget system
        budget_system = TokenBudgetSystem()
        
        # Main implementation
        result = self._process_logic(context)
        
        # Return standardized result
        return {
            "status": "SUCCESS",
            "artifacts": [result],
            "decisions": [],
            "logs": ["Operation completed"],
            "next_actions": []
        }
    
    def _process_logic(self, context: dict) -> str:
        """Private method for main processing logic."""
        # Implementation here
        pass
```

#### Pipeline Development
```yaml
# pipelines/new_feature_pipeline.yaml
name: new_feature_pipeline
description: Pipeline for new feature implementation
version: 1.0
steps:
  - name: task_analyzer
    agent: task_analyzer
    inputs:
      - task_description
    outputs:
      - analysis_result
    retry_policy:
      max_attempts: 3
      backoff_factor: 2.0
    timeout: 300
    memory_enabled: true  # Enable memory recording for successful steps
```

### Memory System Integration

When developing agents that should store results in memory:

```python
from rag.memory_store import MemoryStore
from rag.memory_collections import create_memory_entry, MemoryType

def run(self, context: dict) -> dict:
    # Execute main logic
    result = self._execute_main_logic(context)
    
    # Store successful results in memory
    if result.get("status") == "SUCCESS":
        memory_store = MemoryStore()
        memory_entry = create_memory_entry(
            entry_type=MemoryType.TASK,
            task_description=context.get("task"),
            result_status="SUCCESS",
            agents_used=[self.name],
            pipeline="feature_pipeline",
            artifacts=result.get("artifacts", [])
        )
        memory_store.save(memory_entry)
    
    return result
```

### Context Optimization

Use context optimization features when building agents:

```python
from rag.context_compressor import ContextCompressor
from rag.deduplicator import Deduplicator
from rag.context_builder import ContextBuilder

def build_optimized_context(self, query: str) -> str:
    # Retrieve context from RAG and memory
    rag_context = self.rag_retriever.retrieve(query)
    memory_context = self.memory_retriever.retrieve(query)
    
    # Combine contexts
    full_context = f"""
    Previous solutions:
    {memory_context}
    
    Repository context:
    {rag_context}
    """
    
    # Optimize context size
    compressor = ContextCompressor(max_tokens=4000)
    optimized_context = compressor.compress(full_context)
    
    # Remove duplicates
    deduplicator = Deduplicator()
    final_context = deduplicator.deduplicate_text(optimized_context)
    
    return final_context
```

### Token Budget Management

All LLM interactions should track token usage:

```python
from agents.token_budget_system import TokenBudgetSystem, TokenUsage, ModelInfo

class MyAgent(BaseAgent):
    def run(self, context: dict) -> dict:
        # Initialize budget system
        budget_system = TokenBudgetSystem()
        
        # Define model information
        model_info = ModelInfo(
            name="gpt-4o",
            inputPrice=2.5,
            outputPrice=10.0,
            cacheWritesPrice=3.75,
            cacheReadsPrice=0.3,
            reasoningPrice=20.0
        )
        
        # Track usage for each LLM call
        usage = TokenUsage(
            inputTokens=0,
            outputTokens=0,
            cacheWriteTokens=0,
            cacheReadTokens=0,
            reasoningTokens=0
        )
        
        # Make LLM call and update usage
        response = self.llm_client.generate(prompt)
        usage.inputTokens = response.usage.input_tokens
        usage.outputTokens = response.usage.output_tokens
        
        # Record usage and calculate cost
        cost_breakdown = budget_system.track_usage(
            provider="openai",
            model_info=model_info,
            usage=usage
        )
        
        return {
            "status": "SUCCESS",
            "usage": usage,
            "cost": cost_breakdown.totalCost,
            "result": response.content
        }
```

## Testing Guidelines

### Test Structure

Tests are organized in the `tests/` directory:

```
tests/
├── unit/              # Unit tests for individual components
├── integration/       # Integration tests for component interactions
├── e2e/              # End-to-end tests for complete workflows
└── test_rag/         # RAG-specific tests (renamed to avoid conflicts)
```

### Writing Tests

#### Unit Tests
```python
import pytest
from agents.new_agent import NewAgent

def test_new_agent_success():
    """Test successful execution of new agent."""
    agent = NewAgent()
    context = {"required_field": "test_value"}
    
    result = agent.run(context)
    
    assert result["status"] == "SUCCESS"
    assert len(result["artifacts"]) > 0

def test_new_agent_invalid_input():
    """Test agent with invalid input."""
    agent = NewAgent()
    context = {}  # Missing required field
    
    with pytest.raises(ValueError):
        agent.run(context)
```

#### Integration Tests
```python
import pytest
from agents.token_budget_system import TokenBudgetSystem
from agents.token_budget_system import TokenUsage

def test_token_tracking_integration():
    """Test token tracking with actual provider."""
    budget_system = TokenBudgetSystem()
    
    usage = TokenUsage(
        inputTokens=1000,
        outputTokens=500
    )
    
    cost_breakdown = budget_system.track_usage(
        provider="openai",
        model_info=MockModelInfo(),
        usage=usage
    )
    
    assert cost_breakdown.totalCost > 0
    assert cost_breakdown.inputCost > 0
    assert cost_breakdown.outputCost > 0
```

### Running Tests

```bash
# Run all tests
make test

# Run specific test suites
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/unit/test_new_agent.py

# Run tests with specific marker
pytest -m "slow"  # Run slow tests only
```

### Test Requirements

- All new features must include unit tests
- Bug fixes must include regression tests
- Test coverage should not decrease
- Tests must pass in CI environment
- Integration tests should mock external dependencies

## Pull Request Process

### Before Submitting

1. **Sync with upstream**:
   ```bash
   git checkout main
   git pull upstream main
   git checkout your-feature-branch
   git rebase main
   ```

2. **Run all tests**:
   ```bash
   make test
   make lint
   make format
   ```

3. **Update documentation**: Ensure all relevant documentation is updated

### Creating Pull Request

1. **Push your changes**:
   ```bash
   git push origin your-feature-branch
   ```

2. **Create PR on GitHub**: Fill in the PR template with:
   - Clear description of changes
   - Related issues (if any)
   - Testing performed
   - Breaking changes (if any)

3. **Link related issues**: Use keywords like "Closes #123" or "Fixes #456"

### Code Review Process

1. **Initial Review**: Maintainers check for basic requirements
2. **Detailed Review**: Technical review of implementation
3. **Feedback**: Reviewers provide feedback and suggestions
4. **Address Feedback**: Author makes requested changes
5. **Approval**: PR approved when all reviewers are satisfied
6. **Merge**: Maintainer merges the PR

## Issue Reporting

### Good Issue Reports

Include the following information:

- **Clear title**: Descriptive and specific
- **Environment**: OS, Python version, Docker version
- **Steps to reproduce**: Clear, numbered steps
- **Expected behavior**: What should happen
- **Actual behavior**: What actually happens
- **Error messages**: Full error messages and stack traces
- **Screenshots**: If applicable

### Bug Report Template

```markdown
## Environment
- OS: [e.g., Ubuntu 20.04]
- Python: [e.g., 3.10.6]
- Docker: [e.g., 20.10.12]

## Steps to Reproduce
1. Step 1
2. Step 2
3. Step 3

## Expected Behavior
Description of what should happen

## Actual Behavior
Description of what actually happened

## Error Message
Full error message and stack trace
```

## Documentation

### Updating Documentation

When making changes, update relevant documentation:

- **API changes**: Update API documentation
- **New features**: Add usage examples
- **Breaking changes**: Update migration guides
- **Configuration**: Update config documentation

### Documentation Standards

- Use clear, concise language
- Include code examples where appropriate
- Follow existing documentation style
- Use proper formatting (code blocks, lists, etc.)

### Documentation Files

Key documentation files to update:

- `README.md` - Main project overview
- `docs/development_setup.md` - Setup instructions
- `docs/AGENT_SPEC.md` - Agent specifications
- `docs/ARCHITECTURE.md` - Architecture documentation
- `docs/cli_interface.md` - CLI documentation
- `docs/llm_integration.md` - LLM integration
- `docs/agent_memory.md` - Memory system
- `docs/context_optimization.md` - Context optimization
- `docs/token_budget_system.md` - Token budget system

## Community Guidelines

### Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on the code, not the person
- Be patient with newcomers
- Collaborate openly and transparently

### Getting Help

- **Discussions**: Use GitHub Discussions for questions
- **Issues**: Use Issues for bug reports and feature requests
- **Pull Requests**: Use PRs for code contributions
- **Chat**: Join our community chat (if available)

## Development Tips

### Working with Memory System

When developing features that interact with the memory system:

1. **Test memory recording**: Verify successful pipeline steps are stored
2. **Check context building**: Ensure memory context is properly combined with RAG context
3. **Validate search**: Test that similar solutions can be retrieved
4. **Monitor performance**: Check that memory operations don't impact performance

### Working with Token Budget System

When developing features that use LLMs:

1. **Track usage**: Ensure all LLM calls track token usage
2. **Test budget limits**: Verify budget limits are enforced
3. **Verify costs**: Check that cost calculations are accurate
4. **Handle overages**: Test behavior when budgets are exceeded

### Working with Context Optimization

When developing features that handle context:

1. **Test compression**: Verify context compression works properly
2. **Check deduplication**: Ensure duplicate removal works
3. **Monitor token usage**: Verify context stays within limits
4. **Validate quality**: Ensure compression doesn't degrade quality

## Advanced Topics

### Adding New LLM Providers

To add support for a new LLM provider:

1. **Create provider handler**:
   ```python
   from agents.llm_api import ApiHandler
   
   class NewProviderHandler(ApiHandler):
       async def create_message(self, ...):
           # Implementation for new provider
           pass
       
       def get_model_info(self):
           # Return model information
           pass
   ```

2. **Register provider** in `llm_api.py` factory function

3. **Add configuration** options for the provider

4. **Implement token tracking** for the provider

5. **Add tests** for the new provider

6. **Update documentation** with provider information

### Extending Memory System

To add new memory entry types:

1. **Define entry type** in `rag/memory_collections.py`

2. **Update memory store** to handle new type

3. **Add retrieval methods** for the new type

4. **Update context builder** to include new type in context

5. **Add tests** for the new functionality

6. **Update documentation** with new capabilities

### Performance Optimization

When optimizing performance:

1. **Profile first**: Identify actual bottlenecks
2. **Measure impact**: Quantify performance improvements
3. **Consider trade-offs**: Balance performance with maintainability
4. **Test thoroughly**: Ensure optimizations don't break functionality
5. **Monitor in production**: Verify improvements in real environment

## Security Considerations

### Security Best Practices

- Never log sensitive information (API keys, tokens, etc.)
- Validate all inputs to prevent injection attacks
- Use parameterized queries for database operations
- Implement proper access controls
- Keep dependencies up to date

### Reporting Security Issues

Report security issues privately through GitHub's security advisory feature or contact the maintainers directly. Do not create public issues for security vulnerabilities.

## Questions?

If you have questions about contributing:

- Check existing documentation
- Search through existing issues and discussions
- Ask in the community chat (if available)
- Create a discussion topic for questions

Thank you for your interest in contributing to HordeForge! Your contributions help make the project better for everyone.