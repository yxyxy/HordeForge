# Troubleshooting Guide

## Overview

This guide provides solutions for common issues encountered when running HordeForge. The guide covers problems related to LLM providers, token budgets, memory systems, RAG, pipelines, and general system operations.

## Common Issues and Solutions

### LLM Provider Issues

#### Provider Connectivity Problems
**Problem**: Unable to connect to LLM provider
**Symptoms**: 
- Connection timeout errors
- API key validation failures
- Provider not responding

**Solutions**:
1. Verify API key is correct:
   ```bash
   # Test provider connectivity
   horde llm test --provider openai
   horde llm test --provider anthropic
   ```

2. Check network connectivity:
   ```bash
   # Verify internet connectivity
   curl -I https://api.openai.com/v1/models
   curl -I https://api.anthropic.com/v1/messages
   ```

3. Validate environment variables:
   ```bash
   # Check if API keys are set
   echo $OPENAI_API_KEY
   echo $ANTHROPIC_API_KEY
   ```

#### Token Budget Exceeded
**Problem**: Token budget limit exceeded
**Symptoms**:
- RuntimeError: "Session budget limit exceeded"
- Pipeline stops with budget error
- Cost tracking shows limit reached

**Solutions**:
1. Check current usage:
   ```bash
   # View current token usage
   horde llm tokens
   horde llm cost
   horde llm budget
   ```

2. Increase budget limits:
   ```bash
   # Set new budget limits
   horde llm budget --set-daily 20.0
   horde llm budget --set-monthly 200.0
   horde llm budget --set-session 10.0
   ```

3. Reset session usage:
   ```bash
   # Reset current session
   horde llm budget --reset-session
   ```

#### Model Not Found
**Problem**: Requested model is not available
**Symptoms**:
- ModelNotFoundError
- Provider returns 404 for model
- Invalid model name error

**Solutions**:
1. List available models:
   ```bash
   # List models for provider
   horde llm list-models --provider openai
   horde llm list-models --provider anthropic
   ```

2. Use correct model name:
   ```bash
   # Use exact model name from provider
   horde llm --provider openai --model gpt-4o "Your prompt"
   horde llm --provider anthropic --model claude-3-5-sonnet-20250929 "Your prompt"
   ```

### Memory System Issues

#### Memory Not Being Recorded
**Problem**: Successful pipeline steps are not stored in memory
**Symptoms**:
- Memory collections remain empty
- No historical solutions available
- Context building fails to include memory

**Solutions**:
1. Verify pipeline completion:
   ```bash
   # Check if pipeline steps completed successfully
   horde runs list
   horde runs show RUN_ID
   ```

2. Check memory configuration:
   ```bash
   # Verify memory system is enabled
   grep -i memory .env
   ```

3. Test memory functionality:
   ```bash
   # Test memory retrieval
   python -c "from rag.memory_retriever import MemoryRetriever; r = MemoryRetriever(); print('Memory OK')"
   ```

#### Memory Search Returns Irrelevant Results
**Problem**: Memory retrieval returns unrelated solutions
**Symptoms**:
- Irrelevant historical solutions
- Poor semantic matching
- Low similarity scores

**Solutions**:
1. Adjust similarity threshold:
   ```bash
   # Configure similarity settings
   export HORDEFORGE_MEMORY_SIMILARITY_THRESHOLD=0.7
   ```

2. Verify vector database:
   ```bash
   # Check Qdrant connection
   curl http://qdrant:6333/collections
   ```

3. Rebuild memory indexes:
   ```bash
   # Clear and rebuild memory collections
   horde memory rebuild
   ```

### RAG System Issues

#### RAG Context Not Retrieved
**Problem**: RAG system fails to retrieve relevant context
**Symptoms**:
- Empty context in agent prompts
- Repository context not available
- RAG retriever returns no results

**Solutions**:
1. Check RAG configuration:
   ```bash
   # Verify RAG settings
   grep -i rag .env
   ```

2. Test RAG functionality:
   ```bash
   # Test RAG retrieval
   python -c "from rag.retriever import Retriever; r = Retriever(); print('RAG OK')"
   ```

3. Verify repository indexing:
   ```bash
   # Check if repository is properly indexed
   horde rag status
   horde rag rebuild
   ```

#### Vector Store Connection Issues
**Problem**: Cannot connect to vector store
**Symptoms**:
- Qdrant connection errors
- Vector search failures
- Indexing operations fail

**Solutions**:
1. Check Qdrant service:
   ```bash
   # Verify Qdrant is running
   docker ps | grep qdrant
   curl http://localhost:6333/health
   ```

2. Verify connection settings:
   ```bash
   # Check Qdrant configuration
   export QDRANT_HOST=qdrant
   export QDRANT_PORT=6333
   ```

3. Restart vector store:
   ```bash
   # Restart Qdrant service
   docker restart hordeforge-qdrant
   ```

### Pipeline Issues

#### Pipeline Fails to Start
**Problem**: Pipeline fails to initiate
**Symptoms**:
- Pipeline returns error immediately
- Gateway returns 500 error
- Run ID not created

**Solutions**:
1. Check gateway health:
   ```bash
   # Verify gateway is healthy
   curl http://localhost:8000/health
   curl http://localhost:8000/ready
   ```

2. Verify pipeline configuration:
   ```bash
   # Check pipeline file exists
   ls pipelines/feature_pipeline.yaml
   ```

3. Check logs:
   ```bash
   # View gateway logs
   docker logs hordeforge-gateway
   ```

#### Pipeline Gets Stuck
**Problem**: Pipeline hangs or stops progressing
**Symptoms**:
- Pipeline remains in RUNNING state indefinitely
- No progress updates
- Agent appears unresponsive

**Solutions**:
1. Check pipeline status:
   ```bash
   # Get detailed pipeline status
   horde runs show RUN_ID
   ```

2. Override stuck pipeline:
   ```bash
   # Stop or retry stuck pipeline
   horde runs override RUN_ID --action retry --reason "stuck pipeline"
   ```

3. Check resource usage:
   ```bash
   # Monitor system resources
   docker stats hordeforge-gateway
   ```

### Agent Issues

#### Agent Returns Error
**Problem**: Individual agent fails with error
**Symptoms**:
- Agent returns FAILED status
- Error message in logs
- Pipeline stops at specific step

**Solutions**:
1. Check agent logs:
   ```bash
   # View agent-specific logs
   horde runs show RUN_ID --step STEP_NAME
   ```

2. Test agent independently:
   ```bash
   # Test agent with simple input
   python -c "from agents.code_generator import CodeGenerator; agent = CodeGenerator(); print('Agent OK')"
   ```

3. Verify agent configuration:
   ```bash
   # Check agent settings
   grep -i agent .env
   ```

#### Agent Memory Not Working
**Problem**: Agent fails to use memory context
**Symptoms**:
- No memory context in prompts
- Agents don't leverage historical solutions
- Memory collections not being queried

**Solutions**:
1. Verify memory hook registration:
   ```python
   # Check if memory hook is registered
   from orchestrator.hooks import MemoryHook
   # MemoryHook should be registered in orchestrator
   ```

2. Test memory retrieval:
   ```bash
   # Test memory functionality
   python -c "from rag.memory_retriever import MemoryRetriever; r = MemoryRetriever(); r.search_similar_tasks('test', limit=1)"
   ```

### Token Budget System Issues

#### Incorrect Cost Calculations
**Problem**: Token costs are calculated incorrectly
**Symptoms**:
- Unexpected high costs
- Cost calculations don't match provider rates
- Budget limits triggered unexpectedly

**Solutions**:
1. Verify provider pricing:
   ```bash
   # Check current pricing information
   horde llm cost --provider openai --model gpt-4o
   ```

2. Update pricing data:
   ```bash
   # Refresh pricing information
   horde llm settings --update-pricing
   ```

3. Check token counting:
   ```bash
   # Verify token usage tracking
   horde llm tokens --detailed
   ```

#### Token Counting Not Working
**Problem**: Token usage not being tracked
**Symptoms**:
- Token counts show 0
- Cost calculations return 0
- No usage history available

**Solutions**:
1. Check provider token support:
   ```bash
   # Test token tracking
   horde llm --provider openai "count tokens" --track-tokens
   ```

2. Verify token budget system:
   ```python
   # Test token budget system directly
   from agents.token_budget_system import TokenBudgetSystem
   budget_system = TokenBudgetSystem()
   print("Token budget system OK")
   ```

3. Check environment configuration:
   ```bash
   # Verify token budget settings
   grep -i token .env
   ```

### Context Optimization Issues

#### Context Too Large
**Problem**: Context exceeds token limits
**Symptoms**:
- Token limit exceeded errors
- Context compression not working
- LLM refuses to process request

**Solutions**:
1. Check context size:
   ```bash
   # View current context size
   horde llm tokens --context-size
   ```

2. Enable compression:
   ```bash
   # Use context compression
   export HORDEFORGE_CONTEXT_COMPRESSION_ENABLED=true
   ```

3. Reduce context:
   ```bash
   # Limit context size
   export HORDEFORGE_CONTEXT_MAX_TOKENS=4000
   ```

#### Context Deduplication Not Working
**Problem**: Duplicate content not being removed
**Symptoms**:
- Context contains redundant information
- Token usage higher than expected
- Performance degradation

**Solutions**:
1. Test deduplication:
   ```bash
   # Test deduplication functionality
   python -c "from rag.deduplicator import Deduplicator; d = Deduplicator(); print('Deduplication OK')"
   ```

2. Enable deduplication:
   ```bash
   # Enable context deduplication
   export HORDEFORGE_CONTEXT_DEDUPLICATION_ENABLED=true
   ```

### CLI Interface Issues

#### CLI Commands Not Working
**Problem**: CLI commands fail or return errors
**Symptoms**:
- Command not found errors
- Permission denied errors
- Unexpected command behavior

**Solutions**:
1. Verify CLI installation:
   ```bash
   # Check if CLI is installed
   horde --help
   hordeforge --help
   ```

2. Check Python environment:
   ```bash
   # Verify Python installation
   python -c "import hordeforge; print('CLI OK')"
   ```

3. Reinstall CLI:
   ```bash
   # Reinstall in development mode
   pip install -e .
   ```

#### Interactive Mode Issues
**Problem**: Interactive CLI mode not working properly
**Symptoms**:
- Interactive session crashes
- Commands not recognized
- Poor user experience

**Solutions**:
1. Check interactive dependencies:
   ```bash
   # Verify readline support
   python -c "import readline; print('Readline OK')"
   ```

2. Test interactive mode:
   ```bash
   # Start interactive session
   horde
   ```

### Docker/Container Issues

#### Container Won't Start
**Problem**: Docker containers fail to start
**Symptoms**:
- Container exits immediately
- Port binding errors
- Dependency startup failures

**Solutions**:
1. Check container logs:
   ```bash
   # View container logs
   docker logs hordeforge-gateway
   docker logs hordeforge-qdrant
   ```

2. Verify port availability:
   ```bash
   # Check if ports are free
   netstat -tulpn | grep :8000
   netstat -tulpn | grep :6333
   ```

3. Restart services:
   ```bash
   # Restart all services
   docker-compose down
   docker-compose up -d
   ```

#### Container Resource Issues
**Problem**: Containers running out of resources
**Symptoms**:
- Out of memory errors
- High CPU usage
- Slow response times

**Solutions**:
1. Check resource allocation:
   ```bash
   # Monitor container resources
   docker stats hordeforge-gateway
   ```

2. Increase container resources:
   ```yaml
   # In docker-compose.yml
   services:
     gateway:
       deploy:
         resources:
           limits:
             memory: 4G
             cpus: '2.0'
   ```

### Database Issues

#### PostgreSQL Connection Problems
**Problem**: Cannot connect to PostgreSQL database
**Symptoms**:
- Database connection errors
- Storage operations fail
- Run history not saved

**Solutions**:
1. Check database status:
   ```bash
   # Verify PostgreSQL is running
   docker ps | grep postgres
   ```

2. Test database connection:
   ```bash
   # Test connection
   docker exec hordeforge-db psql -U hordeforge -c "SELECT 1;"
   ```

3. Check connection settings:
   ```bash
   # Verify database URL
   echo $HORDEFORGE_DATABASE_URL
   ```

#### Redis Connection Problems
**Problem**: Cannot connect to Redis cache
**Symptoms**:
- Cache operations fail
- Queue operations fail
- Session data not available

**Solutions**:
1. Check Redis status:
   ```bash
   # Verify Redis is running
   docker ps | grep redis
   ```

2. Test Redis connection:
   ```bash
   # Test connection
   docker exec hordeforge-redis redis-cli ping
   ```

3. Check Redis settings:
   ```bash
   # Verify Redis URL
   echo $HORDEFORGE_REDIS_URL
   ```

## Performance Issues

### Slow Response Times
**Problem**: System responds slowly
**Symptoms**:
- High latency responses
- Long pipeline execution times
- Poor user experience

**Solutions**:
1. Monitor performance:
   ```bash
   # Check system metrics
   curl http://localhost:8000/metrics
   ```

2. Optimize context size:
   ```bash
   # Reduce context size
   export HORDEFORGE_CONTEXT_MAX_TOKENS=2000
   ```

3. Check resource usage:
   ```bash
   # Monitor system resources
   htop
   docker stats
   ```

### High Memory Usage
**Problem**: System uses excessive memory
**Symptoms**:
- High RAM consumption
- Memory leaks
- Out of memory errors

**Solutions**:
1. Monitor memory usage:
   ```bash
   # Check memory usage
   docker stats --format "table {{.Container}}\t{{.MemUsage}}"
   ```

2. Optimize caching:
   ```bash
   # Reduce cache size
   export HORDEFORGE_CACHE_SIZE_LIMIT=100MB
   ```

3. Check for memory leaks:
   ```python
   # Use memory profiler
   python -m memory_profiler your_script.py
   ```

## Security Issues

### Authentication Failures
**Problem**: Authentication fails
**Symptoms**:
- 401/403 errors
- Unauthorized access attempts
- API key validation failures

**Solutions**:
1. Verify API keys:
   ```bash
   # Check API key format
   echo $HORDEFORGE_OPERATOR_API_KEY
   ```

2. Test authentication:
   ```bash
   # Test with valid headers
   curl -H "X-Operator-Key: $HORDEFORGE_OPERATOR_API_KEY" http://localhost:8000/health
   ```

3. Check RBAC settings:
   ```bash
   # Verify role permissions
   grep -i rbac .env
   ```

### Token Leakage
**Problem**: Sensitive tokens appear in logs
**Symptoms**:
- API keys in log files
- Token values in error messages
- Security vulnerabilities

**Solutions**:
1. Verify token redaction:
   ```bash
   # Check if redaction is enabled
   grep -i redact .env
   ```

2. Test logging:
   ```bash
   # Look for tokens in logs
   grep -i "token\|key\|secret" logs/
   ```

3. Enable security features:
   ```bash
   # Enable token redaction
   export HORDEFORGE_SECURITY_TOKEN_REDACTION=true
   ```

## Debugging Tools

### System Diagnostics
```bash
# Check system status
horde status

# View configuration
horde config

# Test all providers
horde llm test --all

# Check memory status
horde memory status

# Check RAG status
horde rag status
```

### Log Analysis
```bash
# View recent logs
docker logs hordeforge-gateway --tail 100

# Follow logs in real-time
docker logs -f hordeforge-gateway

# Filter logs by level
docker logs hordeforge-gateway 2>&1 | grep ERROR
```

### Performance Profiling
```bash
# Profile Python code
python -m cProfile -o profile.stats your_script.py
py-spy record -o profile.svg --pid CONTAINER_PID
```

## Environment Variables

### Common Configuration Issues
```bash
# Verify required environment variables
env | grep -E "(API_KEY|SECRET|TOKEN|URL)"

# Check for missing variables
python -c "
import os
required = ['HORDEFORGE_GATEWAY_URL', 'HORDEFORGE_OPERATOR_API_KEY']
missing = [var for var in required if not os.getenv(var)]
if missing:
    print(f'Missing required variables: {missing}')
else:
    print('All required variables present')
"
```

### Debug Mode
```bash
# Enable debug logging
export HORDEFORGE_DEBUG=true
export LOG_LEVEL=DEBUG

# Enable verbose token tracking
export HORDEFORGE_TOKEN_DEBUG=true
```

## Recovery Procedures

### Service Recovery
```bash
# Restart all services
docker-compose down && docker-compose up -d

# Restart specific service
docker-compose restart gateway

# Clear and rebuild data
docker-compose down -v && docker-compose up -d
```

### Data Recovery
```bash
# Backup current data
docker exec hordeforge-db pg_dump -U hordeforge hordeforge > backup.sql

# Restore from backup
docker exec -i hordeforge-db psql -U hordeforge hordeforge < backup.sql
```

## Support Information

### Getting Help
- Check the logs for error details
- Verify configuration settings
- Test individual components
- Consult the documentation
- Reach out to the community

### Useful Commands for Support
```bash
# Collect system information
horde system info

# Generate diagnostic report
horde system diagnose

# Export configuration
horde config export
```

This troubleshooting guide covers the most common issues encountered with HordeForge. If problems persist, please provide detailed error messages, system configuration, and steps to reproduce when seeking additional support.