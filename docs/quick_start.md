# Quick Start Guide

## Overview

This guide provides a quick introduction to getting started with HordeForge, an autonomous AI software development orchestrator. The system automates the full development lifecycle from GitHub issues to merged pull requests using AI agents, memory systems, and context optimization.

## Requirements

- **Python**: 3.10 or higher
- **Docker**: 20.10 or higher (for containerized deployment)
- **Docker Compose**: v2.0 or higher (for multi-container deployment)
- **Git**: 2.0 or higher
- **Make**: GNU Make (for convenience commands)
- **(Optional)** PostgreSQL and Redis for production deployment

## 1. Installation

### Local Installation (Recommended for Development)

```bash
# Clone the repository
git clone https://github.com/yourusername/HordeForge.git
cd HordeForge

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e .
pip install -r requirements-dev.txt
```

After installation, both CLI commands will be available:
- `hordeforge` - Original CLI for gateway operations
- `horde` - New interactive CLI for development workflows

### Docker Compose Installation (Recommended for Production Simulation)

```bash
# Clone the repository
git clone https://github.com/yourusername/HordeForge.git
cd HordeForge

# Build and start services
docker-compose up --build -d
```

## 2. Configuration

### Environment Setup

```bash
# Copy example configuration
cp .env.example .env

# Edit .env with your settings
# Minimum configuration already in .env.example
# Add your LLM API keys and other settings
```

#### Required Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HORDEFORGE_GATEWAY_URL` | http://localhost:8000 | Gateway URL |
| `HORDEFORGE_STORAGE_DIR` | .hordeforge_data | Data directory |
| `HORDEFORGE_OPERATOR_API_KEY` | local-operator-key | Key for manual control |
| `HORDEFORGE_PIPELINES_DIR` | pipelines | Pipelines directory |
| `HORDEFORGE_LLM_PROVIDER` | openai | Default LLM provider |

#### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HORDEFORGE_TOKEN_BUDGET_DAILY_LIMIT` | 10.0 | Daily token budget limit |
| `HORDEFORGE_TOKEN_BUDGET_MONTHLY_LIMIT` | 100.0 | Monthly token budget limit |
| `HORDEFORGE_CONTEXT_COMPRESSION_ENABLED` | true | Enable context compression |
| `HORDEFORGE_CONTEXT_MAX_TOKENS` | 4000 | Maximum context tokens |
| `HORDEFORGE_MEMORY_ENABLED` | true | Enable agent memory system |
| `HORDEFORGE_VECTOR_STORE_MODE` | auto | Vector store mode (local/host/auto) |

## 3. Running

### Local Development Mode (Recommended)

```bash
# Run gateway with auto-reload
uvicorn scheduler.gateway:app --host 0.0.0.0 --port 8000 --reload

# Or use make command
make run
```

### Docker Compose Mode

```bash
# Start all services
docker-compose up --build -d

# View logs
docker-compose logs -f gateway

# Check services status
docker-compose ps
```

## 4. Health and Status Checks

```bash
# Check health endpoint
curl http://localhost:8000/health

# Check readiness
curl http://localhost:8000/ready

# Check metrics
curl http://localhost:8000/metrics

# Check system status
horde status
hordeforge status
```

## 5. Running Pipelines

### Using Interactive CLI (`horde`) - Recommended

```bash
# Run init pipeline to set up repository
horde pipeline run init --repo-url https://github.com/user/repo --token YOUR_TOKEN

# Run feature pipeline
horde pipeline run feature --inputs '{"prompt": "Add user authentication"}'

# Run development task
horde task "Implement user authentication system"

# Interactive mode
horde
```

### Using Original CLI (`hordeforge`)

```bash
# Run init pipeline
hordeforge run --pipeline init_pipeline --inputs '{"repo_url": "https://github.com/user/repo", "token": "YOUR_TOKEN"}'

# Run with specific provider
hordeforge llm --provider anthropic --model claude-3-5-sonnet "Hello, world!"

# Interactive chat mode
hordeforge llm chat
```

### Using API

```bash
curl -X POST http://localhost:8000/run-pipeline \
  -H "Content-Type: application/json" \
  -H "X-Operator-Key: local-operator-key" \
  -d '{
    "pipeline_name": "init_pipeline",
    "inputs": {"repo_url": "https://github.com/user/repo", "github_token": "YOUR_TOKEN"}
  }'
```

### Check Pipeline Status

```bash
# Get list of runs
curl http://localhost:8000/runs

# Get specific run
curl http://localhost:8000/runs/<run_id>

# Using CLI
horde runs list
horde runs show <run_id>
hordeforge runs list
hordeforge runs show <run_id>
```

## 6. Memory System Usage

The Agent Memory system is enabled by default and automatically records successful solutions:

```bash
# Check memory status
horde memory status

# Search for similar solutions
horde memory search "user authentication"

# View memory collections
horde memory collections
```

## 7. Context Optimization

The system automatically optimizes context through compression and deduplication:

```bash
# Check current context size
horde llm tokens --context-size

# View context optimization settings
horde config | grep CONTEXT
```

## 8. Token Budget Management

Monitor and control your LLM costs:

```bash
# Show current token usage
horde llm tokens
hordeforge llm tokens

# Show usage history
horde llm tokens --history
hordeforge llm tokens --history

# Show cost information
horde llm cost
hordeforge llm cost

# Show budget status
horde llm budget
hordeforge llm budget

# Set budget limits
horde llm budget --set-daily 20.0
horde llm budget --set-monthly 200.0
horde llm budget --set-session 10.0
```

## 9. RAG Configuration

Configure Retrieval-Augmented Generation:

```bash
# Set vector store mode
export HORDEFORGE_VECTOR_STORE_MODE=auto  # local, host, or auto

# For external Qdrant (host mode)
export QDRANT_HOST=qdrant
export QDRANT_PORT=6333

# Check RAG status
horde rag status
horde rag rebuild  # Rebuild indexes if needed
```

## 10. Manual Control

```bash
# Stop running pipeline
curl -X POST http://localhost:8000/runs/<run_id>/override \
  -H "Content-Type: application/json" \
  -H "X-Operator-Key: local-operator-key" \
  -H "X-Operator-Role: operator" \
  -H "X-Command-Source: api" \
  -d '{"action": "stop", "reason": "Manual stop"}'

# Retry failed run
curl -X POST http://localhost:8000/runs/<run_id>/override \
  -H "Content-Type: application/json" \
  -H "X-Operator-Key: local-operator-key" \
  -H "X-Operator-Role: operator" \
  -H "X-Command-Source: api" \
  -d '{"action": "retry"}'

# Using CLI
horde runs override <run_id> --action stop --reason "Manual stop"
horde runs override <run_id> --action retry
```

## 11. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/ready` | Ready check |
| POST | `/run-pipeline` | Trigger pipeline |
| GET | `/runs` | List runs with filtering/pagination |
| GET | `/runs/{run_id}` | Get run status and details |
| POST | `/runs/{run_id}/override` | Manual control (stop/retry/resume/explain) |
| GET | `/queue/tasks/{task_id}` | Queue task status |
| POST | `/queue/drain` | Drain async queue |
| GET | `/cron/jobs` | List cron jobs |
| POST | `/cron/run-due` | Run due jobs |
| POST | `/cron/jobs/{job_name}/trigger` | Trigger specific job |
| GET | `/metrics` | Prometheus metrics |
| POST | `/metrics/export` | Export metrics to external systems |
| POST | `/webhooks/github` | GitHub webhook with HMAC validation |
| GET | `/llm/providers` | List available LLM providers |
| GET | `/llm/models/{provider}` | List available models for provider |
| POST | `/llm/chat` | Interactive chat with LLM |
| GET | `/memory/search` | Search memory collections |
| POST | `/rag/query` | Query RAG system |

## 12. What to Do Next

1. **Set up your first repository**: Run the init pipeline with your GitHub repository
2. **Configure LLM provider**: Add your API keys for OpenAI, Anthropic, or other providers
3. **Run a feature pipeline**: Process a GitHub issue through the full development cycle
4. **Explore the memory system**: Check how successful solutions are stored and reused
5. **Monitor token usage**: Keep track of costs with the Token Budget System
6. **Try context optimization**: Experience how the system optimizes token usage
7. **Add tests**: Extend the test coverage for your custom components

## 13. Troubleshooting

### Common Issues

#### Import Error
```bash
# Make sure all dependencies are installed
pip install -r requirements-dev.txt
```

#### Gateway Won't Start
```bash
# Check .env file
cat .env

# Check port availability
lsof -i :8000

# Check logs (for Docker)
docker-compose logs gateway
```

#### Pipeline Won't Run
```bash
# Check run status
curl http://localhost:8000/runs/<run_id>

# Check system status
hordeforge status
```

#### LLM Provider Issues
```bash
# Check provider settings
horde llm test --provider all
hordeforge llm test --provider openai

# Check token usage
horde llm tokens
hordeforge llm tokens

# Check budget status
horde llm budget
hordeforge llm budget
```

#### Memory System Issues
```bash
# Check memory status
horde memory status
python -c "from rag.memory_store import MemoryStore; ms = MemoryStore(); print('Memory OK')"
```

#### RAG System Issues
```bash
# Check RAG status
horde rag status
python -c "from rag.retriever import Retriever; r = Retriever(); print('RAG OK')"
```

### Debugging Commands
```bash
# Enable debug mode
export HORDEFORGE_DEBUG=true
export LOG_LEVEL=DEBUG

# Check configuration
horde config
hordeforge config

# View detailed logs
docker-compose logs gateway | grep -E "(ERROR|CRITICAL)"
```

## 14. CLI Commands

### Pipeline Management
```bash
# List available pipelines
horde pipeline list
hordeforge pipeline list

# Run specific pipeline
horde pipeline run init --repo-url https://github.com/user/repo --token YOUR_TOKEN
horde pipeline run feature --inputs '{"prompt": "Add user management"}'
```

### LLM Operations
```bash
# Interactive chat
horde llm chat
hordeforge llm chat

# Plan/act modes
horde --plan "How should I refactor this codebase?"
horde --act "Write a Python function to sort an array"
hordeforge llm --plan "How should I refactor this codebase?"
hordeforge llm --act "Write a Python function to sort an array"
```

### Memory and Context
```bash
# Memory operations
horde memory status
horde memory search "query"
horde memory collections

# Context operations
horde llm tokens
horde llm cost
horde llm budget
```

## 15. Security Considerations

- Store API keys securely in environment variables
- Use strong operator keys for manual control
- Enable authentication for production deployments
- Monitor token usage to prevent cost overruns
- Regularly rotate API keys and operator keys

## 16. Performance Tips

- Use local models (Ollama) for faster response times during development
- Enable context compression to reduce token usage
- Set appropriate budget limits to control costs
- Use the memory system to leverage historical solutions
- Configure parallel workers appropriately for your hardware

This quick start guide provides the essential information to get HordeForge running and start using its AI-powered development automation capabilities. The system includes advanced features like agent memory, context optimization, and token budget management that enhance the development experience while controlling costs.