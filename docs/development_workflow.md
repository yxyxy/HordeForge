# Development Workflow

## Overview

This document describes the development workflow for HordeForge, covering the process from issue identification to production deployment. The workflow emphasizes automated testing, code review, continuous integration, and the use of advanced features like agent memory, context optimization, and token budget management.

## Development Process

### Issue Triage and Assignment

Issues are managed through GitHub and follow this process:

1. **Issue Creation**: Issues are created with clear descriptions and acceptance criteria
2. **Triage**: Issues are categorized and prioritized
3. **Assignment**: Issues are assigned to team members
4. **Estimation**: Complexity and time estimates are added
5. **Implementation**: Development begins with proper planning

### Branch Strategy

The project uses a GitFlow-inspired branching model:

```
main ← release branches ← feature branches
 ↑
hotfix branches
```

#### Branch Naming Convention
- **Feature branches**: `feature/issue-number-short-description`
- **Bug fix branches**: `fix/issue-number-short-description`
- **Hotfix branches**: `hotfix/issue-number-short-description`
- **Release branches**: `release/version-number`

### Code Development

#### Setting Up Development Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/HordeForge.git
   cd HordeForge
   ```

2. Create virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install in development mode:
   ```bash
   pip install -e .
   pip install -r requirements-dev.txt
   ```

4. Set up pre-commit hooks:
   ```bash
   pre-commit install
   ```

#### Development Cycle

1. **Plan**: Analyze requirements and design solution
2. **Code**: Implement the solution following coding standards
3. **Test**: Write and run tests to verify functionality
4. **Review**: Submit for code review and address feedback
5. **Merge**: Integrate changes after approval

### Testing Strategy

#### Test Pyramid

The project follows a test pyramid approach:

- **Unit Tests** (70%): Test individual functions and classes in isolation
- **Integration Tests** (20%): Test component interactions and integrations
- **End-to-End Tests** (10%): Test complete workflows and user journeys

#### Running Tests

```bash
# Run all tests
make test

# Run specific test suites
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/
pytest tests/test_rag/  # RAG-specific tests (renamed to avoid conflicts)

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test
pytest tests/unit/test_agent_memory.py
```

#### Test Requirements

- All new features must include unit tests
- Bug fixes must include regression tests
- Test coverage should not decrease
- Tests must pass in CI environment
- Integration tests should mock external dependencies where appropriate

## Implementation Guidelines

### Agent Development

#### Creating New Agents

When creating new agents, follow this pattern:

```python
from agents.base import BaseAgent
from agents.token_budget_system import TokenUsage, TokenBudgetSystem

class NewAgent(BaseAgent):
    name = "new_agent"
    description = "Description of what the agent does"
    
    def run(self, context: dict) -> dict:
        # Validate inputs
        required_inputs = ["input1", "input2"]
        self.validate_inputs(context, required_inputs)
        
        # Initialize token budget system
        budget_system = TokenBudgetSystem()
        
        # Track token usage
        usage = TokenUsage(
            inputTokens=0,
            outputTokens=0,
            cacheWriteTokens=0,
            cacheReadTokens=0,
            reasoningTokens=0
        )
        
        # Main implementation logic
        result = self._process_logic(context)
        
        # Return standardized result
        return {
            "status": "SUCCESS",
            "artifacts": [result],
            "decisions": [{"reason": "Decision made", "confidence": 0.9}],
            "logs": ["Operation completed successfully"],
            "next_actions": [],
            "usage": usage,
            "cost": 0.0  # Will be calculated by budget system
        }
    
    def _process_logic(self, context: dict) -> str:
        """Private method for main processing logic."""
        # Implementation here
        pass
```

#### Agent Contract Compliance

All agents must comply with the agent contract:
- Implement `run(context)` method
- Return standardized result format
- Handle errors gracefully
- Track token usage when applicable
- Follow naming conventions
- Integrate with memory system when appropriate
- Use context optimization features

### Pipeline Development

#### Creating New Pipelines

New pipelines should be defined in YAML format with memory and context optimization:

```yaml
name: new_feature_pipeline
description: Pipeline for new feature implementation with memory integration
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
    context_optimization:
      compression_enabled: true
      deduplication_enabled: true
      max_tokens: 4000
  - name: code_generator
    agent: code_generator
    inputs:
      - analysis_result
    outputs:
      - code_artifact
    depends_on:
      - task_analyzer
    retry_policy:
      max_attempts: 5
      backoff_factor: 1.5
    timeout: 600
    memory_enabled: true  # Enable memory recording for successful steps
    context_optimization:
      compression_enabled: true
      deduplication_enabled: true
      max_tokens: 4000
```

#### Pipeline Best Practices

- Define clear input/output contracts
- Include appropriate retry policies
- Set reasonable timeouts
- Use dependency relationships
- Document purpose and usage
- Enable memory recording for successful steps
- Use context optimization to reduce token usage
- Include proper error handling and fallback mechanisms

### Memory System Integration

#### Adding Memory Capabilities

When agents should store results in memory:

```python
from rag.memory_store import MemoryStore
from rag.memory_collections import create_memory_entry, MemoryType

def run(self, context: dict) -> dict:
    # Execute main logic
    result = self._execute_main_logic(context)
    
    # Store successful results in memory
    if result["status"] == "SUCCESS":
        memory_store = MemoryStore()
        memory_entry = create_memory_entry(
            entry_type=MemoryType.TASK,
            task_description=context.get("task"),
            result_status="SUCCESS",
            agents_used=[self.name],
            pipeline="feature_pipeline",
            artifacts=result.get("artifacts", []),
            metadata={
                "repository": context.get("repository"),
                "branch": context.get("branch", "main"),
                "timestamp": context.get("timestamp")
            }
        )
        memory_store.save(memory_entry)
    
    return result
```

#### Context Optimization

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

def run(self, context: dict) -> dict:
    # Build optimized context
    query = context.get("task_description", "")
    optimized_context = self.build_optimized_context(query)
    
    # Use optimized context for LLM calls
    response = self.llm_client.generate(optimized_context)
    
    # Continue with normal processing...
    return {
        "status": "SUCCESS",
        "artifacts": [response],
        "usage": response.usage,
        "cost": response.cost
    }
```

### Token Budget Management

#### Implementing Token Tracking

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
        response = self.llm_client.generate(context["prompt"])
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

## Quality Assurance

### Code Quality Standards

#### Python Standards
- Follow PEP 8 style guide
- Use type hints for all functions
- Write docstrings for public methods
- Keep functions under 50 lines when possible
- Use meaningful variable names
- Implement proper error handling

#### Testing Standards
- Achieve 80%+ test coverage
- Test both happy path and error cases
- Use parametrized tests for multiple inputs
- Mock external dependencies in unit tests
- Include integration tests for critical paths
- Test memory system integration
- Test context optimization features
- Test token budget enforcement

### Security Considerations

#### Input Validation
- Validate all external inputs
- Sanitize user-provided content
- Prevent injection attacks
- Use parameterized queries for databases
- Implement proper authentication and authorization

#### Token Security
- Never log API keys or tokens
- Use environment variables for secrets
- Implement token redaction in logs
- Validate token permissions
- Use secure connection handling

### Performance Optimization

#### Context Management
- Optimize context size with compression
- Remove duplicate information
- Use semantic search for relevance
- Implement efficient caching
- Leverage memory system for historical solutions

#### Resource Management
- Close resources properly
- Use connection pooling
- Implement lazy loading where appropriate
- Monitor memory usage
- Optimize token usage through context optimization

## Documentation Requirements

### Code Documentation

#### Docstring Standards
```python
def process_request(self, request: dict) -> dict:
    """
    Process incoming request and return response.
    
    Args:
        request (dict): Input request with required fields
        
    Returns:
        dict: Response with status and results
        
    Raises:
        ValueError: If request is invalid
        RuntimeError: If processing fails
        BudgetExceededError: If token budget is exceeded
    """
    pass
```

#### Inline Comments
- Explain complex logic
- Document assumptions
- Note limitations and workarounds
- Use TODO/FIXME for future work
- Document security considerations
- Note performance implications

### Architecture Documentation

Update architecture documents when making significant changes:
- `docs/ARCHITECTURE.md` - System architecture
- `docs/AGENT_SPEC.md` - Agent specifications
- `docs/development_setup.md` - Development setup
- `docs/security_notes.md` - Security considerations
- `docs/llm_integration.md` - LLM integration
- `docs/agent_memory.md` - Memory system
- `docs/context_optimization.md` - Context optimization
- `docs/token_budget_system.md` - Token budget system

## Deployment Process

### Pre-deployment Checklist

Before deploying changes:

- [ ] All tests pass
- [ ] Code review approved
- [ ] Documentation updated
- [ ] Security scan passed
- [ ] Performance tests completed
- [ ] Token budget verified
- [ ] Memory system tested
- [ ] Context optimization verified
- [ ] Integration tests passed

### Deployment Steps

1. **Prepare Release**:
   - Update version numbers
   - Update changelog
   - Create release notes

2. **Test in Staging**:
   - Deploy to staging environment
   - Run smoke tests
   - Verify functionality
   - Test memory and context optimization
   - Verify token budget enforcement

3. **Deploy to Production**:
   - Deploy changes
   - Monitor system health
   - Verify metrics
   - Monitor token usage and costs

4. **Post-deployment**:
   - Monitor for issues
   - Update documentation
   - Notify stakeholders
   - Verify memory system continues to work
   - Check context optimization performance

## Monitoring and Observability

### Metrics Collection

The system collects various metrics:

- **Performance**: Response times, throughput
- **Usage**: Token usage, API calls
- **Errors**: Error rates, failure types
- **Cost**: Provider costs, budget usage
- **Memory**: Memory system performance and effectiveness
- **Context**: Context optimization metrics and token savings

### Logging Standards

#### Log Format
Use structured logging with JSON format:
```json
{
  "timestamp": "2026-03-26T22:30:00Z",
  "level": "INFO",
  "message": "Pipeline started",
  "run_id": "abc123",
  "pipeline": "feature_pipeline",
  "step": "task_analyzer",
  "correlation_id": "xyz789",
  "tokens_used": 1500,
  "cost_usd": 0.0025
}
```

#### Log Levels
- **DEBUG**: Detailed diagnostic information
- **INFO**: General operational information
- **WARNING**: Potential issues
- **ERROR**: Recoverable errors
- **CRITICAL**: Unrecoverable errors

## Troubleshooting

### Common Development Issues

#### Token Budget Exceeded
- Check current usage: `horde llm tokens`
- Increase budget: `horde llm budget --set-daily 20.0`
- Optimize context size: Use compression and deduplication
- Review token usage: `horde llm tokens --detailed`

#### Memory Not Being Recorded
- Verify pipeline steps complete successfully
- Check memory configuration in `.env`
- Test memory functionality independently
- Verify successful steps are being stored
- Check memory system logs

#### Context Too Large
- Enable compression: `HORDEFORGE_CONTEXT_COMPRESSION_ENABLED=true`
- Set token limits: `HORDEFORGE_CONTEXT_MAX_TOKENS=4000`
- Use deduplication: `HORDEFORGE_CONTEXT_DEDUPLICATION_ENABLED=true`
- Optimize context building with memory and RAG

#### RAG Context Not Retrieved
- Verify repository indexing: `horde rag status`
- Check vector store connection
- Rebuild indexes if necessary: `horde rag rebuild`
- Test memory retrieval: `horde memory status`

### Debugging Techniques

#### Enable Debug Mode
```bash
export HORDEFORGE_DEBUG=true
export LOG_LEVEL=DEBUG
export HORDEFORGE_TOKEN_DEBUG=true  # Enable token debugging
```

#### Test Components Individually
```bash
# Test LLM connectivity
horde llm test --provider all

# Test memory system
python -c "from rag.memory_store import MemoryStore; ms = MemoryStore(); print('Memory OK')"

# Test RAG functionality
python -c "from rag.retriever import Retriever; r = Retriever(); print('RAG OK')"

# Test context optimization
python -c "from rag.context_compressor import ContextCompressor; cc = ContextCompressor(); print('Context compression OK')"

# Test token budget system
python -c "from agents.token_budget_system import TokenBudgetSystem; tbs = TokenBudgetSystem(); print('Token budget OK')"
```

## Best Practices

### Development Best Practices

1. **Small, Focused Commits**: Keep commits small and focused on single changes
2. **Descriptive Commit Messages**: Use clear, descriptive commit messages
3. **Regular Syncing**: Sync with main branch regularly to avoid conflicts
4. **Incremental Development**: Develop features incrementally with working intermediate states
5. **Automated Testing**: Run tests frequently during development
6. **Token Awareness**: Be mindful of token usage and costs
7. **Memory Utilization**: Leverage historical solutions when appropriate
8. **Context Optimization**: Use compression and deduplication features

### Collaboration Best Practices

1. **Clear Communication**: Communicate blockers and progress regularly
2. **Code Reviews**: Participate actively in code reviews
3. **Knowledge Sharing**: Share knowledge and discoveries with the team
4. **Documentation**: Keep documentation up to date
5. **Issue Tracking**: Use issues to track work and decisions
6. **Memory Sharing**: Contribute to and leverage shared memory collections

### Performance Best Practices

1. **Efficient Algorithms**: Choose efficient algorithms and data structures
2. **Resource Management**: Properly manage resources and connections
3. **Caching**: Use caching appropriately for expensive operations
4. **Parallel Processing**: Use parallel processing where beneficial
5. **Memory Management**: Monitor and optimize memory usage
6. **Token Optimization**: Minimize token usage through context optimization
7. **Context Efficiency**: Use memory and RAG efficiently to reduce redundant processing

## Tools and Utilities

### Development Tools

#### CLI Interface
The system provides comprehensive CLI tools:
- `horde` - Interactive development CLI with memory and context optimization
- `hordeforge` - Original gateway CLI with full feature support
- Both support LLM operations, pipeline management, monitoring, and token budget management

#### Configuration Management
- Environment variable management
- Profile-based configurations
- Settings validation and testing
- Multi-provider configuration support

#### Token Budget Management
- Usage tracking and monitoring
- Budget limit enforcement
- Cost calculation and reporting
- CLI interface for budget management

#### Memory System Tools
- Memory search and retrieval
- Memory collection management
- Historical solution lookup
- Context optimization utilities

### Testing Tools

#### Unit Testing
- pytest for test framework
- Coverage analysis with pytest-cov
- Mocking with unittest.mock
- Property-based testing with hypothesis

#### Integration Testing
- Docker-based test environments
- API testing with test clients
- Database testing with fixtures
- Memory system integration tests
- Context optimization tests

#### Performance Testing
- Load testing with custom tools
- Token usage monitoring
- Response time measurement
- Memory system performance testing
- Context optimization efficiency testing

## Continuous Integration

### CI Pipeline

The CI pipeline includes:
- Code quality checks (linting, formatting)
- Unit and integration tests
- Security scanning
- Performance testing
- Documentation generation
- Memory system tests
- Context optimization tests
- Token budget system tests

### Automated Checks

#### Pre-commit Hooks
- Code formatting (black, ruff)
- Security scanning (bandit)
- License header checks
- Spell checking
- Encoding verification (UTF-8)

#### Code Quality Gates
- Test coverage minimums (80%+)
- Code complexity limits
- Security vulnerability scans
- Performance regression checks
- Token usage verification
- Memory system validation

## Release Management

### Versioning Strategy

The project follows semantic versioning:
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Process

1. **Feature Complete**: All planned features implemented
2. **Testing Complete**: All tests pass, performance verified
3. **Documentation Updated**: All docs reflect changes
4. **Security Review**: Security scan completed
5. **Memory System Review**: Verify memory functionality
6. **Context Optimization Review**: Verify optimization features
7. **Token Budget Review**: Verify cost tracking and limits
8. **Release Candidate**: RC testing period
9. **Final Release**: Production deployment

## Advanced Features Integration

### Agent Memory Integration
When developing new features, consider how they can leverage the memory system:
- Store successful results in memory collections
- Retrieve similar historical solutions
- Use memory context to improve quality
- Implement proper memory cleanup

### Context Optimization Integration
Optimize token usage through context optimization:
- Use compression for large contexts
- Implement deduplication to remove redundancy
- Combine memory and RAG context efficiently
- Monitor token usage and costs

### Token Budget Integration
Ensure all LLM interactions are properly tracked:
- Track all token types (input, output, cache, reasoning)
- Calculate costs based on provider pricing
- Enforce budget limits appropriately
- Provide clear cost information to users

## Security and Compliance

### Security Best Practices
- Regular security scanning
- Token redaction in logs
- Secure credential handling
- Input validation and sanitization
- Memory data sanitization
- Context optimization security checks

### Compliance Considerations
- Data retention policies
- Audit logging requirements
- Token usage tracking for billing
- Memory data privacy
- Context optimization privacy

## Performance Monitoring

### Key Metrics to Monitor
- Token usage and costs
- Memory system performance
- Context optimization efficiency
- Pipeline execution times
- Agent response times
- Memory retrieval effectiveness

### Performance Optimization
- Regular performance testing
- Token usage optimization
- Memory system tuning
- Context optimization improvements
- Pipeline parallelization

This development workflow ensures high-quality code, proper testing, and smooth collaboration among team members while maintaining the system's reliability, performance, and cost-effectiveness. The workflow incorporates advanced features like agent memory, context optimization, and token budget management to create an efficient and cost-effective AI development system.
