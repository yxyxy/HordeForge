# API Reference

## Overview

This document provides comprehensive reference for the HordeForge API endpoints, including gateway endpoints, webhook endpoints, and internal service APIs. The API follows REST principles with JSON responses and standardized error handling.

## Authentication

Most endpoints require authentication using the operator key system:

```bash
# Include operator key in requests
curl -H "X-Operator-Key: $HORDEFORGE_OPERATOR_API_KEY" \
     -H "X-Operator-Role: operator" \
     -H "X-Command-Source: api" \
     http://localhost:8000/runs
```

### Required Headers for Manual Commands

For override and manual cron commands, the following headers are required:
- `X-Operator-Key`: Operator authentication key
- `X-Operator-Role`: Operator role (admin, operator, viewer)
- `X-Command-Source`: Source of command (api, cli, webhook)

## Gateway Endpoints

### Pipeline Operations

#### `POST /run-pipeline`
Trigger a pipeline execution.

**Request Body:**
```json
{
  "pipeline_name": "feature_pipeline",
  "inputs": {
    "issue_id": 123,
    "repository": "org/repo"
  },
  "source": "webhook",
  "correlation_id": "unique-correlation-id",
  "tenant_id": "tenant-123"
}
```

**Response:**
```json
{
  "run_id": "run-123",
  "status": "QUEUED",
  "created_at": "2026-03-26T22:30:00Z",
  "estimated_completion": "2026-03-26T22:35:00Z"
}
```

#### `GET /runs`
List pipeline runs with filtering and pagination.

**Query Parameters:**
- `pipeline_name`: Filter by pipeline name
- `status`: Filter by status (PENDING, RUNNING, COMPLETED, FAILED, BLOCKED)
- `tenant_id`: Filter by tenant
- `limit`: Number of results (default: 20)
- `offset`: Offset for pagination (default: 0)
- `start_date`: Filter from date (ISO format)
- `end_date`: Filter to date (ISO format)

**Response:**
```json
{
  "runs": [
    {
      "run_id": "run-123",
      "pipeline_name": "feature_pipeline",
      "status": "COMPLETED",
      "created_at": "2026-03-26T22:30:00Z",
      "completed_at": "2026-03-26T22:35:00Z",
      "duration_seconds": 300,
      "cost_usd": 0.45,
      "tenant_id": "tenant-123"
    }
  ],
  "total": 150,
  "limit": 20,
  "offset": 0
}
```

#### `GET /runs/{run_id}`
Get detailed information about a specific run.

**Response:**
```json
{
  "run_id": "run-123",
  "pipeline_name": "feature_pipeline",
  "status": "COMPLETED",
  "inputs": {
    "issue_id": 123,
    "repository": "org/repo"
  },
  "outputs": {
    "pr_url": "https://github.com/org/repo/pull/456"
  },
  "steps": [
    {
      "step_name": "task_analyzer",
      "agent": "task_analyzer",
      "status": "SUCCESS",
      "started_at": "2026-03-26T22:30:00Z",
      "completed_at": "2026-03-26T22:31:00Z",
      "duration_seconds": 60,
      "cost_usd": 0.05,
      "artifacts": ["analysis_result.json"]
    }
  ],
  "created_at": "2026-03-26T22:30:00Z",
  "completed_at": "2026-03-26T22:35:00Z",
  "duration_seconds": 300,
  "total_cost_usd": 0.45,
  "error": null,
  "override_state": null,
  "correlation_id": "unique-correlation-id",
  "tenant_id": "tenant-123"
}
```

#### `POST /runs/{run_id}/override`
Manually control a running pipeline.

**Request Body:**
```json
{
  "action": "stop",
  "reason": "Manual intervention required",
  "details": "Additional context for the override"
}
```

**Actions:**
- `stop`: Stop a RUNNING pipeline
- `retry`: Retry a FAILED/BLOCKED pipeline
- `resume`: Resume a BLOCKED pipeline
- `explain`: Get explanation for current state

**Response:**
```json
{
  "status": "SUCCESS",
  "action": "stop",
  "previous_state": "RUNNING",
  "new_state": "STOPPED",
  "reason": "Manual intervention required",
  "timestamp": "2026-03-26T22:32:00Z"
}
```

### Queue Operations

#### `GET /queue/tasks/{task_id}`
Get status of a queued task.

**Response:**
```json
{
  "task_id": "task-123",
  "status": "PROCESSING",
  "queue_name": "default",
  "priority": "normal",
  "created_at": "2026-03-26T22:30:00Z",
  "started_at": "2026-03-26T22:31:00Z",
  "progress": 0.65,
  "estimated_completion": "2026-03-26T22:35:00Z",
  "tenant_id": "tenant-123"
}
```

#### `POST /queue/drain`
Process all pending tasks in the queue.

**Response:**
```json
{
  "status": "STARTED",
  "tasks_processed": 0,
  "tasks_remaining": 5,
  "queue_name": "default",
  "timestamp": "2026-03-26T22:30:00Z"
}
```

### Cron Operations

#### `GET /cron/jobs`
List available cron jobs.

**Response:**
```json
{
  "jobs": [
    {
      "job_name": "issue_scanner",
      "schedule": "*/15 * * * *",
      "enabled": true,
      "last_run": "2026-03-26T22:15:00Z",
      "next_run": "2026-03-26T22:30:00Z",
      "status": "ACTIVE",
      "tenant_id": "global"
    }
  ]
}
```

#### `POST /cron/run-due`
Run all due cron jobs manually.

**Response:**
```json
{
  "status": "STARTED",
  "jobs_triggered": 2,
  "jobs_skipped": 0,
  "timestamp": "2026-03-26T22:30:00Z",
  "triggered_jobs": ["issue_scanner", "ci_monitor"]
}
```

#### `POST /cron/jobs/{job_name}/trigger`
Trigger a specific cron job manually.

**Request Body:**
```json
{
  "payload": {
    "force": true,
    "parameters": {}
  }
}
```

**Response:**
```json
{
  "status": "TRIGGERED",
  "job_name": "issue_scanner",
  "execution_id": "exec-123",
  "scheduled_at": "2026-03-26T22:30:00Z",
  "expected_duration": 120
}
```

### Metrics and Monitoring

#### `GET /metrics`
Get Prometheus-compatible metrics.

**Response:**
```
# HELP hordeforge_pipeline_runs_total Total number of pipeline runs
# TYPE hordeforge_pipeline_runs_total counter
hordeforge_pipeline_runs_total{pipeline="feature_pipeline",status="success"} 42
hordeforge_pipeline_runs_total{pipeline="feature_pipeline",status="failed"} 3

# HELP hordeforge_pipeline_duration_seconds Pipeline execution duration
# TYPE hordeforge_pipeline_duration_seconds histogram
hordeforge_pipeline_duration_seconds_bucket{pipeline="feature_pipeline",le="60.0"} 25
hordeforge_pipeline_duration_seconds_bucket{pipeline="feature_pipeline",le="300.0"} 42
hordeforge_pipeline_duration_seconds_bucket{pipeline="feature_pipeline",le="+Inf"} 45

# HELP hordeforge_token_usage_total Token usage by provider
# TYPE hordeforge_token_usage_total counter
hordeforge_token_usage_total{provider="openai",type="input"} 125000
hordeforge_token_usage_total{provider="openai",type="output"} 50000
```

#### `POST /metrics/export`
Export metrics to external systems.

**Request Body:**
```json
{
  "exporter": "prometheus_pushgateway",
  "url": "http://pushgateway:9091",
  "job_name": "hordeforge"
}
```

**Response:**
```json
{
  "status": "EXPORTED",
  "exporter": "prometheus_pushgateway",
  "metrics_exported": 150,
  "timestamp": "2026-03-26T22:30:00Z"
}
```

### Health Checks

#### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-03-26T22:30:00Z",
  "components": {
    "database": "healthy",
    "queue": "healthy",
    "vector_store": "healthy",
    "llm_providers": "healthy"
  },
  "version": "2.0.0"
}
```

#### `GET /ready`
Readiness check endpoint.

**Response:**
```json
{
  "status": "ready",
  "timestamp": "2026-03-26T22:30:00Z",
  "ready": true,
  "reason": "All systems operational"
}
```

## Webhook Endpoints

### `POST /webhooks/github`
GitHub webhook endpoint with HMAC validation.

**Required Headers:**
- `X-GitHub-Delivery`: Delivery ID
- `X-GitHub-Event`: Event type
- `X-Hub-Signature-256`: HMAC signature

**Request Body:**
```json
{
  "action": "opened",
  "issue": {
    "number": 123,
    "title": "Add user authentication",
    "body": "Implement user authentication system",
    "labels": [
      {
        "name": "feature"
      }
    ]
  },
  "repository": {
    "full_name": "org/repo"
  },
  "sender": {
    "login": "user"
  }
}
```

**Response:**
```json
{
  "status": "ACCEPTED",
  "triggered_pipeline": "feature_pipeline",
  "run_id": "run-123",
  "processed_at": "2026-03-26T22:30:00Z"
}
```

## LLM Provider Endpoints

### `POST /llm/chat`
Interactive chat with LLM providers.

**Request Body:**
```json
{
  "provider": "openai",
  "model": "gpt-4o",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful coding assistant"
    },
    {
      "role": "user",
      "content": "Explain how to implement user authentication"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": true
}
```

**Streaming Response:**
```json
event: text_chunk
data: {"text": "User authentication can be implemented"}

event: usage_chunk
data: {"input_tokens": 15, "output_tokens": 8, "cost": 0.00025}

event: done
data: {"final_cost": 0.00125, "total_tokens": 23}
```

### `POST /llm/providers/{provider}/models`
List available models for a provider.

**Response:**
```json
{
  "provider": "openai",
  "models": [
    {
      "name": "gpt-4o",
      "max_tokens": 128000,
      "context_window": 128000,
      "input_price": 2.5,
      "output_price": 10.0,
      "supports_images": true,
      "supports_tools": true
    }
  ]
}
```

## Memory System Endpoints

### `GET /memory/search`
Search memory collections for similar solutions.

**Query Parameters:**
- `query`: Search query
- `limit`: Number of results (default: 5)
- `collection`: Memory collection type (tasks, patches, decisions)
- `min_similarity`: Minimum similarity threshold (default: 0.7)

**Response:**
```json
{
  "results": [
    {
      "id": "memory-123",
      "type": "task",
      "task_description": "Implement user authentication",
      "result_status": "SUCCESS",
      "agents_used": ["code_generator", "test_runner"],
      "pipeline": "feature_pipeline",
      "similarity_score": 0.85,
      "created_at": "2026-03-20T10:00:00Z"
    }
  ],
  "total_results": 1,
  "query": "user authentication",
  "search_time_ms": 45
}
```

### `POST /memory/store`
Store a successful solution in memory.

**Request Body:**
```json
{
  "type": "task",
  "task_description": "Implement user authentication",
  "result_status": "SUCCESS",
  "agents_used": ["code_generator", "test_runner"],
  "pipeline": "feature_pipeline",
  "artifacts": [
    {
      "type": "code_patch",
      "content": "diff content here",
      "file": "auth.py"
    }
  ],
  "metadata": {
    "repository": "org/repo",
    "branch": "main"
  }
}
```

**Response:**
```json
{
  "status": "STORED",
  "memory_id": "memory-123",
  "stored_at": "2026-03-26T22:30:00Z",
  "processing_time_ms": 120
}
```

## Token Budget System Endpoints

### `GET /budget/usage`
Get current token usage and costs.

**Response:**
```json
{
  "usage": {
    "today": {
      "input_tokens": 15000,
      "output_tokens": 8000,
      "total_cost": 0.45
    },
    "this_month": {
      "input_tokens": 250000,
      "output_tokens": 120000,
      "total_cost": 8.75
    },
    "session": {
      "input_tokens": 2500,
      "output_tokens": 1200,
      "total_cost": 0.12
    }
  },
  "budget_limits": {
    "daily_limit": 10.0,
    "monthly_limit": 100.0,
    "session_limit": 5.0
  },
  "remaining_budget": {
    "daily_remaining": 9.55,
    "monthly_remaining": 91.25,
    "session_remaining": 4.88
  },
  "usage_percent": {
    "daily_percent": 4.5,
    "monthly_percent": 8.75,
    "session_percent": 2.4
  }
}
```

### `POST /budget/reset-session`
Reset session token usage.

**Response:**
```json
{
  "status": "RESET",
  "previous_session_cost": 0.12,
  "reset_at": "2026-03-26T22:30:00Z",
  "new_session_cost": 0.0
}
```

## RAG System Endpoints

### `POST /rag/query`
Query the RAG system for repository context.

**Request Body:**
```json
{
  "query": "Find user authentication implementation",
  "repository": "org/repo",
  "limit": 10,
  "min_similarity": 0.6
}
```

**Response:**
```json
{
  "results": [
    {
      "id": "chunk-123",
      "content": "class AuthManager:\n    def authenticate(self, user, password):\n        # Implementation here",
      "file_path": "src/auth.py",
      "line_numbers": [15, 25],
      "similarity_score": 0.82,
      "metadata": {
        "repository": "org/repo",
        "branch": "main",
        "commit_hash": "abc123"
      }
    }
  ],
  "query": "Find user authentication implementation",
  "retrieval_time_ms": 67,
  "total_chunks": 1
}
```

### `POST /rag/index`
Index repository content for RAG.

**Request Body:**
```json
{
  "repository": "org/repo",
  "branch": "main",
  "force_reindex": false,
  "include_tests": true,
  "include_docs": true
}
```

**Response:**
```json
{
  "status": "INDEXING_STARTED",
  "repository": "org/repo",
  "branch": "main",
  "estimated_duration": 300,
  "indexing_job_id": "index-job-123",
  "files_to_index": 150
}
```

## Error Handling

### Standard Error Response

All error responses follow this format:

```json
{
  "error": {
    "type": "ValidationError",
    "message": "Invalid pipeline name provided",
    "details": {
      "field": "pipeline_name",
      "value": "invalid_pipeline",
      "allowed_values": ["feature_pipeline", "init_pipeline", "ci_scanner_pipeline"]
    },
    "timestamp": "2026-03-26T22:30:00Z",
    "request_id": "req-123"
  }
}
```

### Common Error Types

- `ValidationError`: Input validation failed
- `AuthenticationError`: Authentication required or failed
- `AuthorizationError`: Insufficient permissions
- `NotFoundError`: Requested resource not found
- `RateLimitError`: Rate limit exceeded
- `BudgetExceededError`: Token budget limit exceeded
- `ProviderError`: LLM provider error
- `TimeoutError`: Operation timed out
- `InternalServerError`: Server-side error

### HTTP Status Codes

- `200 OK`: Successful request
- `201 Created`: Resource created successfully
- `202 Accepted`: Request accepted for processing
- `400 Bad Request`: Invalid request format
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `409 Conflict`: Resource conflict
- `422 Unprocessable Entity`: Validation error
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error
- `502 Bad Gateway`: Upstream provider error
- `503 Service Unavailable`: Service temporarily unavailable
- `504 Gateway Timeout`: Upstream provider timeout

## Rate Limiting

The API implements rate limiting with the following headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 1648320000
Retry-After: 60
```

Rate limits can be configured per tenant and per endpoint type.

## Tenant Isolation

All endpoints support tenant isolation through:
- Tenant-specific headers
- Isolated storage backends
- Resource quotas per tenant
- Access control enforcement

## Security Headers

The API includes security headers:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security: max-age=31536000`

## CORS Configuration

The API supports CORS with configurable origins:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, X-Operator-Key
Access-Control-Allow-Credentials: true
```

## Request/Response Size Limits

- Maximum request body size: 10MB
- Maximum response size: 10MB
- Maximum file upload size: 50MB
- Maximum streaming response: 100MB

## Pagination

Collection endpoints support pagination:
- Default page size: 20 items
- Maximum page size: 100 items
- Offset-based pagination
- Cursor-based pagination available for some endpoints

## Filtering and Sorting

Endpoints support various filtering options:
- Status filters
- Date range filters
- Text search
- Field-based sorting
- Custom query parameters

## Webhook Delivery

GitHub webhooks include delivery guarantees:
- Idempotency support
- Duplicate suppression
- Retry mechanism with exponential backoff
- Delivery status tracking
- HMAC signature validation

## Audit Logging

All API requests are logged with:
- Request/response details
- Authentication information
- Timestamps
- IP addresses
- User agents
- Correlation IDs

## Monitoring and Observability

The API provides monitoring endpoints:
- Health check with component status
- Metrics in Prometheus format
- Request/response logging
- Performance timing
- Error rate tracking
- Token usage monitoring

## Versioning

The API uses header-based versioning:
- Default version: 1.0
- Version header: `X-API-Version: 1.0`
- Backward compatibility maintained
- Deprecation notices provided

## Client Libraries

Official client libraries are available for:
- Python
- JavaScript/TypeScript
- Go
- Java
- C#

## SDK Examples

### Python SDK
```python
from hordeforge.client import HordeForgeClient

client = HordeForgeClient(
    base_url="http://localhost:8000",
    api_key="your-api-key"
)

# Run a pipeline
run = client.run_pipeline("feature_pipeline", {
    "issue_id": 123,
    "repository": "org/repo"
})

# Get run status
status = client.get_run(run.run_id)
print(f"Status: {status.status}")

# Search memory
results = client.search_memory("user authentication", limit=5)
for result in results:
    print(f"Found: {result.task_description}")
```

### JavaScript SDK
```javascript
import { HordeForgeClient } from '@hordeforge/client';

const client = new HordeForgeClient({
    baseUrl: 'http://localhost:8000',
    apiKey: 'your-api-key'
});

// Run a pipeline
const run = await client.runPipeline('feature_pipeline', {
    issue_id: 123,
    repository: 'org/repo'
});

// Get run status
const status = await client.getRun(run.runId);
console.log(`Status: ${status.status}`);

// Search memory
const results = await client.searchMemory('user authentication', { limit: 5 });
for (const result of results) {
    console.log(`Found: ${result.taskDescription}`);
}
```

## Testing the API

### Health Check
```bash
curl -I http://localhost:8000/health
```

### Simple Pipeline Run
```bash
curl -X POST http://localhost:8000/run-pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_name": "init_pipeline",
    "inputs": {"repo_url": "https://github.com/user/repo", "token": "YOUR_TOKEN"}
  }'
```

### Check Token Usage
```bash
curl -H "X-Operator-Key: $HORDEFORGE_OPERATOR_API_KEY" \
     http://localhost:8000/budget/usage
```

### Search Memory
```bash
curl -X POST http://localhost:8000/memory/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "user authentication",
    "limit": 5
  }'
```

## Troubleshooting

### Common Issues

1. **Authentication Required**: Ensure `X-Operator-Key` header is included
2. **Rate Limited**: Check rate limit headers and implement backoff
3. **Budget Exceeded**: Check token budget status and increase limits if needed
4. **Provider Errors**: Verify LLM provider configuration and API keys
5. **Memory Not Found**: Ensure successful pipeline steps are being recorded

### Debug Headers

Include these headers for debugging:
- `X-Correlation-ID`: Trace request across services
- `X-Debug`: Enable debug logging (development only)
- `X-Tenant-ID`: Specify tenant for multi-tenant setups

### Logging

The API logs include:
- Request/response details
- Performance metrics
- Error information
- Token usage tracking
- Audit trail information

## Performance Considerations

### Response Times

Target response times:
- Simple queries: < 100ms
- Pipeline triggers: < 500ms
- Memory searches: < 200ms
- RAG queries: < 500ms
- Complex operations: < 2s

### Concurrency

The API supports:
- 100+ concurrent requests
- Connection pooling
- Asynchronous processing
- Queue-based operations

### Caching

Built-in caching for:
- Model information
- Memory search results
- RAG context
- Token prices
- Configuration data

## Security Best Practices

### API Key Management

- Use strong, unique API keys
- Rotate keys regularly
- Store keys securely
- Use environment variables
- Implement key revocation

### Input Validation

- Validate all inputs
- Sanitize user-provided content
- Prevent injection attacks
- Use parameterized queries
- Implement proper escaping

### Rate Limiting

- Configure appropriate limits
- Implement client-side backoff
- Monitor usage patterns
- Set up alerts for unusual activity
- Use distributed rate limiting

## Monitoring and Alerting

### Key Metrics

Monitor these metrics:
- Request rate and response times
- Error rates and types
- Token usage and costs
- Memory system performance
- RAG retrieval quality
- Queue depth and processing times

### Alerting Rules

Set up alerts for:
- High error rates (>5%)
- Slow response times (>5s)
- Budget limit approaching (80%)
- Service unavailability
- Unusual token usage patterns
- Memory system failures

## API Evolution

### Deprecation Policy

- 6 months notice for deprecated features
- Backward compatibility maintained
- Migration guides provided
- Alternative implementations suggested
- Removal announced in advance

### Versioning Strategy

- Header-based versioning
- Backward compatibility priority
- Forward compatibility where possible
- Clear deprecation notices
- Migration tooling provided

This API reference provides comprehensive documentation for all HordeForge API endpoints, including request/response formats, authentication requirements, error handling, and best practices for integration.