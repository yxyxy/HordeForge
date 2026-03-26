# Metrics and Monitoring System

## Overview

The Metrics and Monitoring system in HordeForge provides comprehensive observability for the AI development orchestrator. The system tracks performance metrics, costs, token usage, and system health across all components including agents, pipelines, and LLM providers.

## Architecture

### Core Components

The monitoring system consists of several interconnected components:

1. **Metrics Collection**: Runtime metrics from all system components
2. **Token Tracking**: Comprehensive token usage and cost tracking
3. **Health Checks**: System and service health monitoring
4. **Alerting System**: Proactive notification system
5. **Dashboard Export**: Metrics export for visualization tools

### Token Budget System Integration

The system includes a sophisticated Token Budget System that tracks usage across all providers:

```python
from agents.token_budget_system import TokenBudgetSystem, BudgetLimits

# Initialize with budget limits
budget_system = TokenBudgetSystem(
    budget_limits=BudgetLimits(
        dailyLimit=10.0,      # $10 per day
        monthlyLimit=100.0,   # $100 per month
        sessionLimit=5.0      # $5 per session
    )
)
```

## Metrics Categories

### Performance Metrics

#### Pipeline Metrics
- `pipeline_execution_time` - Time taken for pipeline execution
- `step_execution_time` - Time taken for individual steps
- `concurrent_pipelines` - Number of currently running pipelines
- `pipeline_success_rate` - Success rate percentage
- `pipeline_failure_reasons` - Distribution of failure reasons

#### Agent Metrics
- `agent_response_time` - Response time for individual agents
- `agent_success_rate` - Success rate per agent type
- `agent_token_usage` - Tokens consumed per agent
- `agent_error_rate` - Error rate per agent

#### LLM Provider Metrics
- `provider_response_time` - Response time per provider
- `provider_success_rate` - Success rate per provider
- `provider_token_usage` - Token usage per provider
- `provider_cost` - Cost incurred per provider

### Cost Metrics

#### Token Usage Tracking
The system tracks multiple types of tokens:

- **Input Tokens**: Tokens sent to the model
- **Output Tokens**: Tokens received from the model
- **Cache Write Tokens**: Tokens written to cache (where supported)
- **Cache Read Tokens**: Tokens read from cache (where supported)
- **Reasoning Tokens**: Tokens used for reasoning/thinking (where supported)

#### Cost Calculation
Automatic cost calculation based on provider pricing:

```python
from agents.token_budget_system import TokenUsage, ModelInfo

usage = TokenUsage(
    inputTokens=1000,
    outputTokens=500,
    cacheWriteTokens=100,
    cacheReadTokens=200,
    reasoningTokens=50
)

model_info = ModelInfo(
    name="gpt-4o",
    inputPrice=2.5,      # $2.5 per million tokens
    outputPrice=10.0,    # $10.0 per million tokens
    cacheWritesPrice=3.75,  # $3.75 per million tokens
    cacheReadsPrice=0.3,    # $0.3 per million tokens
    reasoningPrice=20.0     # $20.0 per million tokens
)

cost = budget_system.calculate_cost(model_info, usage)
```

### System Health Metrics

#### Resource Utilization
- `cpu_usage_percent` - CPU utilization percentage
- `memory_usage_bytes` - Memory usage in bytes
- `disk_usage_bytes` - Disk space usage
- `network_io_bytes` - Network I/O statistics

#### Queue Metrics
- `queue_size` - Number of items in task queue
- `queue_processing_rate` - Items processed per second
- `queue_error_rate` - Error rate in queue processing

#### Database Metrics
- `db_connection_count` - Active database connections
- `db_query_time` - Database query execution time
- `db_error_rate` - Database operation error rate

## Monitoring Endpoints

### Health Checks

The system provides multiple health check endpoints:

```bash
# Overall system health
GET /health

# Ready status (system ready to accept requests)
GET /ready

# Detailed health information
GET /health/details
```

### Metrics Endpoint

Prometheus-compatible metrics endpoint:

```bash
# Get all metrics
GET /metrics

# Metrics with specific labels
GET /metrics?labels=provider,agent
```

### Token Usage

View current token usage and costs:

```bash
# Current token usage
GET /metrics/tokens

# Usage history
GET /metrics/tokens/history

# Cost information
GET /metrics/cost

# Budget status
GET /metrics/budget
```

## Alerting System

### Built-in Alerts

The system includes predefined alerts for common issues:

#### Budget Alerts
- Daily budget exceeded
- Monthly budget exceeded
- Session budget exceeded
- Cost threshold exceeded

#### Performance Alerts
- High error rates (>5%)
- Slow response times (>30s)
- Low success rates (<80%)
- Resource exhaustion

#### System Alerts
- Service unavailability
- Database connection failures
- Queue backlogs
- Token limit exceeded

### Alert Configuration

Alerts can be configured through environment variables:

```bash
# Budget alert thresholds
HORDEFORGE_ALERT_BUDGET_DAILY_THRESHOLD=80.0
HORDEFORGE_ALERT_BUDGET_MONTHLY_THRESHOLD=90.0
HORDEFORGE_ALERT_BUDGET_SESSION_THRESHOLD=75.0

# Performance alert thresholds
HORDEFORGE_ALERT_ERROR_RATE_THRESHOLD=0.05
HORDEFORGE_ALERT_RESPONSE_TIME_THRESHOLD=30.0
HORDEFORGE_ALERT_SUCCESS_RATE_THRESHOLD=0.80

# Alert destinations
HORDEFORGE_ALERT_SLACK_WEBHOOK=https://hooks.slack.com/...
HORDEFORGE_ALERT_EMAIL_RECIPIENTS=admin@example.com,user@example.com
```

## CLI Integration

### Token Monitoring Commands

```bash
# View current token usage
horde llm tokens
hordeforge llm tokens

# View usage history
horde llm tokens --history
hordeforge llm tokens --history

# View cost information
horde llm cost
hordeforge llm cost

# View budget status
horde llm budget
hordeforge llm budget

# Set budget limits
horde llm budget --set-daily 10.0
horde llm budget --set-monthly 100.0
horde llm budget --set-session 5.0
```

### System Monitoring Commands

```bash
# View system status
hordeforge status

# View pipeline runs
horde runs list
hordeforge runs list

# View agent statistics
horde agents stats
hordeforge agents stats

# View provider statistics
horde providers stats
hordeforge providers stats
```

## Provider-Specific Monitoring

### Multi-Provider Tracking

The system tracks metrics separately for each provider:

```python
# Provider-specific metrics
providers = [
    "openai",      # OpenAI models
    "anthropic",   # Anthropic Claude models
    "google",      # Google Gemini models
    "ollama",      # Local Ollama models
    "openrouter",  # OpenRouter models
    "bedrock",     # AWS Bedrock models
    "vertex",      # Google Vertex AI
    "groq",        # Groq models
    "together",    # Together AI models
    # ... and many more
]

# Each provider has separate metrics tracking
for provider in providers:
    metrics = get_provider_metrics(provider)
    print(f"{provider}: {metrics['success_rate']:.2%} success rate")
```

### Cache Token Monitoring

For providers that support caching (like OpenAI's recent models):

```python
# Cache token tracking
cache_metrics = {
    'cache_creation_input_tokens': 0,  # Tokens used for cache creation
    'cache_hit_output_tokens': 0,      # Tokens saved through cache hits
    'cache_miss_rate': 0.0,           # Percentage of cache misses
    'cache_efficiency_ratio': 0.0     # Efficiency of cache usage
}
```

### Reasoning Token Monitoring

For models that support reasoning tokens (like some newer models):

```python
# Reasoning token tracking
reasoning_metrics = {
    'reasoning_tokens': 0,           # Tokens used for reasoning
    'reasoning_time': 0.0,           # Time spent in reasoning
    'reasoning_efficiency': 0.0      # Efficiency of reasoning
}
```

## Dashboard Integration

### Prometheus Integration

The system exports metrics in Prometheus format:

```yaml
# prometheus.yml configuration
scrape_configs:
  - job_name: 'hordeforge'
    static_configs:
      - targets: ['localhost:8000']
    scrape_interval: 15s
    metrics_path: '/metrics'
```

### Grafana Dashboards

Pre-built Grafana dashboards are available for:
- Token usage and costs
- Pipeline performance
- Agent statistics
- Provider comparison
- System health
- Error rates and trends

### Custom Exporters

The system supports custom metric exporters:

```python
from observability.exporters import MetricsExporter, PrometheusExporter, DatadogExporter

# Prometheus exporter
prometheus_exporter = PrometheusExporter(
    push_gateway_url="http://pushgateway:9091",
    job_name="hordeforge"
)

# Datadog exporter
datadog_exporter = DatadogExporter(
    api_key="your-datadog-api-key",
    site="datadoghq.com"
)

# Register exporters
budget_system.register_exporter(prometheus_exporter)
budget_system.register_exporter(datadog_exporter)
```

## Performance Benchmarks

### Baseline Performance

The system maintains performance benchmarks:

- **Pipeline Init Time**: < 3 seconds
- **Orchestrator Overhead**: < 500ms (excluding LLM work)
- **Token Tracking Overhead**: < 50ms per request
- **Memory Retrieval Time**: < 200ms
- **Context Building Time**: < 300ms

### Load Testing Results

Under load testing conditions:
- Sustained throughput: 100+ requests/minute
- 95th percentile response time: < 5 seconds
- Error rate: < 1%
- Resource utilization: < 80% CPU, < 70% memory

## Data Retention

### Usage History

The system maintains usage history with configurable retention:

```python
from observability.cost_tracker import DataRetentionPolicy

retention_policy = DataRetentionPolicy(
    usage_history_days=90,      # Keep usage data for 90 days
    metrics_history_days=30,    # Keep metrics for 30 days
    logs_history_days=14,       # Keep logs for 14 days
    audit_history_days=90       # Keep audit logs for 90 days
)
```

### Historical Analysis

Historical data enables trend analysis:

```python
# Get historical usage patterns
historical_data = budget_system.get_historical_usage(
    start_date="2026-01-01",
    end_date="2026-03-26",
    granularity="daily"
)

# Analyze trends
trends = analyze_usage_trends(historical_data)
forecast = forecast_usage(trends)
```

## Security and Privacy

### Token Redaction

All sensitive information is redacted from logs and metrics:

- API keys are never logged
- Token values are masked in logs
- Personal information is filtered
- Audit trails maintain privacy

### Access Controls

Metric endpoints have appropriate access controls:
- Health endpoints: public access
- Metrics endpoints: authenticated access
- Admin metrics: admin-only access

## Troubleshooting

### Common Issues

1. **High Token Usage**: Check for inefficient prompts or infinite loops
2. **Slow Performance**: Monitor context sizes and optimize compression
3. **Budget Exceeded**: Review usage patterns and adjust limits
4. **Provider Errors**: Check API keys and provider availability

### Diagnostic Commands

```bash
# Check current usage
horde llm tokens --detailed

# Check provider status
horde llm test --provider all

# View system metrics
horde metrics system

# Check memory usage
horde metrics memory
```

## Configuration

### Environment Variables

```bash
# Metrics configuration
HORDEFORGE_METRICS_ENABLED=true
HORDEFORGE_METRICS_COLLECTION_INTERVAL=60
HORDEFORGE_METRICS_RETENTION_DAYS=30

# Token budget configuration
HORDEFORGE_TOKEN_BUDGET_DAILY_LIMIT=10.0
HORDEFORGE_TOKEN_BUDGET_MONTHLY_LIMIT=100.0
HORDEFORGE_TOKEN_BUDGET_SESSION_LIMIT=5.0

# Alerting configuration
HORDEFORGE_ALERT_ENABLED=true
HORDEFORGE_ALERT_THRESHOLD_HIGH=80.0
HORDEFORGE_ALERT_THRESHOLD_CRITICAL=95.0
```

### Programmatic Configuration

```python
from agents.token_budget_system import TokenBudgetSystem, BudgetLimits
from observability.metrics import MetricsConfig

# Configure metrics system
config = MetricsConfig(
    enabled=True,
    collection_interval=60,
    retention_days=30,
    export_interval=300
)

budget_system = TokenBudgetSystem(
    budget_limits=BudgetLimits(
        dailyLimit=10.0,
        monthlyLimit=100.0,
        sessionLimit=5.0
    ),
    metrics_config=config
)
```

## Best Practices

### Monitoring Best Practices

1. **Set Appropriate Budgets**: Configure realistic budget limits based on usage patterns
2. **Monitor Trends**: Regularly review usage trends and adjust accordingly
3. **Alert Responsibly**: Set meaningful alert thresholds to avoid noise
4. **Secure Access**: Protect metric endpoints with appropriate authentication
5. **Retention Planning**: Configure data retention based on compliance needs

### Performance Optimization

1. **Context Optimization**: Use compression and deduplication to reduce token usage
2. **Provider Selection**: Choose appropriate providers based on task requirements
3. **Batch Operations**: Where possible, batch operations to reduce overhead
4. **Caching**: Leverage cache tokens where supported by providers
5. **Efficient Prompts**: Optimize prompts to reduce token consumption

## Integration with External Systems

### CI/CD Integration

The system can integrate with CI/CD pipelines for automated monitoring:

```yaml
# Example GitHub Actions workflow
name: Monitor Token Usage
on:
  schedule:
    - cron: '0 9 * * *'  # Daily at 9 AM
jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - name: Check token usage
        run: |
          curl -s http://hordeforge:8000/metrics/tokens
```

### Alerting Integration

Integrates with popular alerting systems:
- Slack notifications
- Email alerts
- PagerDuty
- Opsgenie
- Custom webhooks

## Future Enhancements

### Planned Features

1. **Advanced Analytics**: Machine learning-based anomaly detection
2. **Predictive Budgeting**: AI-powered budget forecasting
3. **Multi-dimensional Analysis**: Advanced drill-down capabilities
4. **Real-time Dashboards**: Live updating visualization
5. **Automated Optimization**: AI-powered cost optimization suggestions

### Performance Improvements

1. **Efficient Storage**: Optimized storage for large-scale usage data
2. **Faster Queries**: Improved query performance for historical data
3. **Better Compression**: Enhanced data compression algorithms
4. **Edge Computing**: Local processing for sensitive data
5. **Scalable Architecture**: Horizontal scaling support

The Metrics and Monitoring system provides comprehensive visibility into the performance, costs, and health of the HordeForge AI development orchestrator, enabling teams to optimize usage, control costs, and maintain high performance.