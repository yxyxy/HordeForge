# Migration Guide

## Overview

This guide provides instructions for migrating from previous versions of HordeForge to the current version. The guide covers breaking changes, deprecated features, and steps required for a smooth transition.

## Version History

### Current Version: 2.0.0
Major changes include:
- Agent Memory system with automatic recording of successful solutions
- Context optimization with compression and deduplication
- Token Budget System with comprehensive cost tracking
- Enhanced RAG with memory integration
- New CLI interface with interactive features
- Improved pipeline orchestration with memory hooks

### Previous Version: 1.x.x
Legacy version with basic pipeline orchestration and limited memory features.

## Breaking Changes

### 1. Agent Contract Changes

#### Old Agent Interface
```python
class OldAgent:
    def run(self, context):
        # Old interface
        return result
```

#### New Agent Interface
```python
from agents.base import BaseAgent
from agents.token_budget_system import TokenUsage

class NewAgent(BaseAgent):
    name = "new_agent"
    description = "Description of agent"
    
    def run(self, context: dict) -> dict:
        # New standardized interface
        return {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": []
        }
```

### 2. Configuration Changes

#### Environment Variables
Old variables в†’ New variables:
- `HORDE_GATEWAY_URL` в†’ `HORDEFORGE_GATEWAY_URL`
- `HORDE_STORAGE_DIR` в†’ `HORDEFORGE_STORAGE_DIR`
- `HORDE_OPERATOR_API_KEY` в†’ `HORDEFORGE_OPERATOR_API_KEY`
- `HORDE_MAX_PARALLEL_WORKERS` в†’ `HORDEFORGE_MAX_PARALLEL_WORKERS`

#### New Required Variables
```bash
# Memory system configuration
HORDEFORGE_MEMORY_ENABLED=true
HORDEFORGE_MEMORY_RETENTION_DAYS=90

# Token budget system
HORDEFORGE_TOKEN_BUDGET_DAILY_LIMIT=10.0
HORDEFORGE_TOKEN_BUDGET_MONTHLY_LIMIT=100.0

# Context optimization
HORDEFORGE_CONTEXT_COMPRESSION_ENABLED=true
HORDEFORGE_CONTEXT_MAX_TOKENS=4000
```

### 3. Pipeline Configuration Changes

#### Old Pipeline Format
```yaml
name: old_pipeline
steps:
  - agent: old_agent
    inputs: ["field1", "field2"]
    retry: 3
    timeout: 300
```

#### New Pipeline Format
```yaml
name: new_pipeline
description: Updated pipeline with memory support
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

## Migration Steps

### Step 1: Backup Current Data

Before starting migration, backup all data:

```bash
# Backup storage directory
cp -r .hordeforge_data .hordeforge_data_backup

# Backup database (if using PostgreSQL)
pg_dump hordeforge > hordeforge_backup.sql

# Backup token usage data
cp ~/.hordeforge/token_usage.json ~/.hordeforge/token_usage_backup.json
```

### Step 2: Update Dependencies

Update to the new version:

```bash
# Update the package
pip install hordeforge==2.0.0

# Or install from source
pip install -e .
```

### Step 3: Update Configuration

Update your `.env` file with new variables:

```bash
# Copy new example
cp .env.example .env

# Edit .env with your settings
# Add new memory and token budget settings
```

### Step 4: Update Agent Implementations

For each custom agent, update to the new interface:

```python
# Old agent
class CustomAgent:
    def run(self, context):
        # Old implementation
        pass

# New agent
from agents.base import BaseAgent
from agents.token_budget_system import TokenBudgetSystem

class CustomAgent(BaseAgent):
    name = "custom_agent"
    description = "Custom agent description"
    
    def run(self, context: dict) -> dict:
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
            "decisions": [{"reason": "Decision made", "confidence": 0.9}],
            "logs": ["Operation completed successfully"],
            "next_actions": []
        }
```

### Step 5: Update Pipeline Definitions

Convert old pipeline formats to new format:

```yaml
# pipelines/updated_pipeline.yaml
name: updated_feature_pipeline
description: Feature pipeline with memory integration
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
    memory_enabled: true
  
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
    memory_enabled: true
```

### Step 6: Migrate Data (if needed)

If you have custom data that needs migration:

```python
# Example migration script
from storage.repositories.run_repository import RunRepository
from rag.memory_store import MemoryStore

def migrate_old_data():
    """Migrate data from old format to new format."""
    run_repo = RunRepository()
    memory_store = MemoryStore()
    
    # Convert old run records to new format
    old_runs = run_repo.get_all_runs()
    for old_run in old_runs:
        # Convert to new format if needed
        new_format = convert_run_format(old_run)
        run_repo.update_run(old_run.id, new_format)
    
    # Migrate memory entries if they exist
    migrate_memory_entries()

def convert_run_format(old_run):
    """Convert old run format to new format."""
    # Implementation depends on specific changes needed
    pass
```

### Step 7: Test the Migration

Run comprehensive tests to ensure everything works:

```bash
# Run all tests
make test

# Test specific components
pytest tests/unit/test_agents.py
pytest tests/integration/test_memory.py
pytest tests/integration/test_token_budget.py

# Test pipeline execution
horde repo add test/repo --url https://github.com/test/repo --token TEST_TOKEN --set-default
horde init test/repo
```

## Feature-Specific Migrations

### Memory System Migration

#### Enable Memory Recording

Update your pipeline steps to enable memory recording:

```python
# In your agents, ensure successful results are stored
def run(self, context: dict) -> dict:
    # Execute main logic
    result = self._execute_logic(context)
    
    # Store successful results in memory
    if result["status"] == "SUCCESS":
        from rag.memory_store import MemoryStore
        from rag.memory_collections import create_memory_entry
        
        memory_store = MemoryStore()
        memory_entry = create_memory_entry(
            entry_type="task",
            task_description=context.get("task"),
            result_status="SUCCESS",
            agents_used=[self.name],
            pipeline="feature_pipeline",
            artifacts=result.get("artifacts", [])
        )
        memory_store.save(memory_entry)
    
    return result
```

#### Context Building Updates

Update context building to use new memory integration:

```python
from rag.context_builder import ContextBuilder

def build_context(self, query: str) -> str:
    # Use new context builder with memory integration
    context_builder = ContextBuilder(
        memory_retriever=self.memory_retriever,
        rag_retriever=self.rag_retriever
    )
    
    return context_builder.build_agent_context(
        query=query,
        max_memory_entries=5,
        max_rag_chunks=10,
        max_tokens=4000
    )
```

### Token Budget System Migration

#### Update Token Tracking

Ensure all LLM interactions track tokens properly:

```python
from agents.token_budget_system import TokenBudgetSystem, TokenUsage

class UpdatedAgent(BaseAgent):
    def run(self, context: dict) -> dict:
        # Initialize budget system
        budget_system = TokenBudgetSystem()
        
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
        
        # Record usage
        cost_breakdown = budget_system.track_usage(
            provider="openai",
            model_info=self.model_info,
            usage=usage
        )
        
        return {
            "status": "SUCCESS",
            "usage": usage,
            "cost": cost_breakdown.totalCost,
            "result": response.content
        }
```

### Context Optimization Migration

#### Enable Context Compression

Update agents to use context optimization:

```python
from rag.context_compressor import ContextCompressor
from rag.deduplicator import Deduplicator

def prepare_context(self, context: str) -> str:
    # Compress context to fit within limits
    compressor = ContextCompressor(max_tokens=4000)
    compressed_context = compressor.compress(context)
    
    # Remove duplicates
    deduplicator = Deduplicator()
    optimized_context = deduplicator.deduplicate_text(compressed_context)
    
    return optimized_context
```

## CLI Interface Migration

### Old CLI Usage
```bash
# Old commands
horde run-pipeline --name feature --inputs "{}"
horde get-runs
horde get-run --id RUN_ID
```

### New CLI Usage
```bash
# New commands with enhanced features
horde pipeline run feature --inputs "{}"
horde runs list
horde runs show RUN_ID

# New interactive features
horde task "Implement feature"
horde --plan "How should I refactor this?"
horde --act "Write the implementation"
```

## Provider Integration Migration

### Update Provider Configuration

The system now supports 18+ providers with unified interface:

```python
# Old provider selection
if provider == "openai":
    # OpenAI specific code
elif provider == "anthropic":
    # Anthropic specific code

# New unified interface
from agents.llm_api import ApiConfiguration, ApiProvider, LlmApi

config = ApiConfiguration(
    provider=ApiProvider.OPENAI,
    model="gpt-4o",
    api_key="your-key"
)

api = LlmApi(config)
```

### Token Tracking for All Providers

All providers now automatically track tokens:

```python
# Token usage is automatically tracked for all providers
async for chunk in api.create_message(system_prompt, messages):
    if isinstance(chunk, ApiStreamUsageChunk):
        print(f"Input tokens: {chunk.inputTokens}")
        print(f"Output tokens: {chunk.outputTokens}")
        print(f"Cost: ${chunk.cost}")
```

## Database Migration

### Alembic Migrations

Run database migrations if using PostgreSQL:

```bash
# Run migrations
alembic upgrade head

# Check current version
alembic current
```

### Schema Changes

The new version includes schema changes for:
- Memory collections in vector store
- Enhanced run storage with memory links
- Token usage tracking tables
- Budget limit configurations

## Configuration Migration

### Environment Variables

Update your `.env` file with new variables:

```bash
# Core settings
HORDEFORGE_GATEWAY_URL=http://localhost:8000
HORDEFORGE_STORAGE_DIR=.hordeforge_data
HORDEFORGE_OPERATOR_API_KEY=your-operator-key

# Memory system
HORDEFORGE_MEMORY_ENABLED=true
HORDEFORGE_MEMORY_RETENTION_DAYS=90
HORDEFORGE_MEMORY_SIMILARITY_THRESHOLD=0.7

# Token budget system
HORDEFORGE_TOKEN_BUDGET_DAILY_LIMIT=10.0
HORDEFORGE_TOKEN_BUDGET_MONTHLY_LIMIT=100.0
HORDEFORGE_TOKEN_BUDGET_SESSION_LIMIT=5.0

# Context optimization
HORDEFORGE_CONTEXT_COMPRESSION_ENABLED=true
HORDEFORGE_CONTEXT_MAX_TOKENS=4000
HORDEFORGE_CONTEXT_DEDUPLICATION_ENABLED=true

# RAG settings
HORDEFORGE_RAG_ENABLED=true
HORDEFORGE_VECTOR_STORE_MODE=auto
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# Queue settings
HORDEFORGE_QUEUE_BACKEND=redis
HORDEFORGE_IDEMPOTENCY_TTL_SECONDS=3600

# LLM profiles (recommended)
horde llm profile add openai-main --provider openai --model gpt-4o --api-key YOUR_OPENAI_KEY --set-default
horde llm profile add anthropic-main --provider anthropic --model claude-sonnet-4-20250514 --api-key YOUR_ANTHROPIC_KEY
```

## Testing the Migration

### Pre-Migration Tests

Before migration, verify current system works:

```bash
# Test current functionality
make test
horde runs list
horde llm test --provider openai
```

### Post-Migration Tests

After migration, verify new functionality:

```bash
# Run comprehensive tests
make test

# Test new features
horde llm tokens  # Should show token tracking
horde llm cost    # Should show cost information
horde memory status  # Should show memory system status
horde rag status   # Should show RAG status

# Test pipeline execution
horde repo add test/repo --url https://github.com/test/repo --token TEST_TOKEN --set-default
horde init test/repo
```

### Integration Tests

Run integration tests to verify all components work together:

```bash
# Run integration tests
pytest tests/integration/

# Test memory integration
pytest tests/integration/test_memory_integration.py

# Test token budget integration
pytest tests/integration/test_token_budget.py

# Test context optimization
pytest tests/integration/test_context_optimization.py
```

## Rollback Procedure

If migration fails, you can rollback using backups:

```bash
# Stop the system
docker-compose down

# Restore data from backup
rm -rf .hordeforge_data
cp -r .hordeforge_data_backup .hordeforge_data

# Restore database (if using PostgreSQL)
psql hordeforge < hordeforge_backup.sql

# Restore token usage data
cp ~/.hordeforge/token_usage_backup.json ~/.hordeforge/token_usage.json

# Downgrade package
pip install hordeforge==1.x.x

# Restart system
docker-compose up -d
```

## Common Migration Issues

### Issue 1: Missing Environment Variables

**Problem**: System fails to start due to missing configuration
**Solution**: Check that all required environment variables are set

```bash
# Verify required variables are set
env | grep HORDEFORGE
```

### Issue 2: Token Budget Exceeded

**Problem**: New token budget system blocks operations
**Solution**: Adjust budget limits or reset usage

```bash
# Check current usage
horde llm tokens

# Increase budget limits
horde llm budget --set-daily 20.0

# Reset session usage
horde llm budget --reset-session
```

### Issue 3: Memory System Not Working

**Problem**: Memory collections are empty or not being populated
**Solution**: Verify pipeline steps are completing successfully

```bash
# Check memory status
horde memory status

# Test memory functionality
python -c "from rag.memory_store import MemoryStore; ms = MemoryStore(); print('Memory OK')"
```

### Issue 4: Context Too Large

**Problem**: Context exceeds new token limits
**Solution**: Enable compression and optimize context size

```bash
# Enable context compression
export HORDEFORGE_CONTEXT_COMPRESSION_ENABLED=true
export HORDEFORGE_CONTEXT_MAX_TOKENS=4000
```

## Performance Considerations

### Memory Usage

The new memory system may use more memory. Monitor resource usage:

```bash
# Monitor memory usage
docker stats hordeforge-gateway
docker stats hordeforge-qdrant
```

### Token Usage

The new token tracking system provides detailed usage information:

```bash
# Monitor token usage
horde llm tokens --history
horde llm cost --monthly
```

### Performance Testing

Run performance tests after migration:

```bash
# Run performance tests
pytest tests/performance/

# Test concurrent operations
horde pipeline run feature --inputs '{"prompt": "Test 1"}' &
horde pipeline run feature --inputs '{"prompt": "Test 2"}' &
wait
```

## Security Updates

### Token Redaction

The new version includes enhanced token redaction:

```bash
# Verify token redaction is enabled
export HORDEFORGE_SECURITY_TOKEN_REDACTION=true
```

### Authentication Updates

Update authentication settings if needed:

```bash
# New RBAC settings
HORDEFORGE_RBAC_ENABLED=true
HORDEFORGE_OPERATOR_ALLOWED_ROLES=admin,operator
HORDEFORGE_MANUAL_COMMAND_ALLOWED_SOURCES=api,cli
```

## Monitoring and Observables

### New Metrics

The new version includes additional metrics:

```bash
# Check new metrics
curl http://localhost:8000/metrics | grep -E "(memory|token|budget)"
```

### Alerting Updates

Update alerting rules for new metrics:

```yaml
# alerts.yml
- name: token_budget_exceeded
  expression: hordeforge_token_budget_usage_percent > 90
  message: "Token budget usage is above 90%"
```

## Support and Troubleshooting

### Getting Help

If you encounter issues during migration:

1. Check the logs for error details
2. Verify configuration settings
3. Test individual components
4. Consult the updated documentation
5. Reach out to the community for support

### Useful Commands for Support

```bash
# Collect system information
horde system info

# Generate diagnostic report
horde system diagnose

# Export configuration
horde config export

# Test all components
horde health check --all
```

## Post-Migration Verification

### Verify Migration Success

After migration, verify all components work:

```bash
# Check system status
horde status

# Verify token tracking
horde llm tokens

# Verify memory system
horde memory status

# Verify RAG system
horde rag status

# Test pipeline execution
horde repo add test/repo --url https://github.com/test/repo --token TEST_TOKEN --set-default
horde init test/repo
```

### Performance Verification

Verify performance is acceptable:

```bash
# Run performance tests
make benchmark

# Check response times
time horde llm --provider openai "Hello" > /dev/null

# Monitor resource usage
docker stats --no-stream
```

### Data Integrity Check

Verify data integrity after migration:

```bash
# Check run history
horde runs list --limit 10

# Verify token usage history
horde llm tokens --history --limit 5

# Check memory entries
python -c "
from rag.memory_store import MemoryStore
store = MemoryStore()
entries = store.search('test', limit=5)
print(f'Found {len(entries)} memory entries')
"
```

## Next Steps

After successful migration:

1. **Update Documentation**: Update any internal documentation to reflect new features
2. **Train Team**: Train team members on new features and changes
3. **Monitor Performance**: Monitor system performance and usage patterns
4. **Optimize Configuration**: Fine-tune configuration based on usage patterns
5. **Plan Enhancements**: Plan additional enhancements using new capabilities

## Additional Resources

- [Updated Architecture Documentation](ARCHITECTURE.md)
- [New Agent Specifications](AGENT_SPEC.md)
- [CLI Interface Documentation](cli_interface.md)
- [LLM Integration Guide](llm_integration.md)
- [Memory System Documentation](agent_memory.md)
- [Context Optimization Guide](context_optimization.md)
- [Token Budget System Documentation](token_budget_system.md)

This migration guide covers the main changes needed to upgrade from previous versions. If you encounter specific issues not covered here, please consult the detailed documentation or reach out to the community for assistance.
