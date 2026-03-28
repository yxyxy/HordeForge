# Token Budget System Documentation

## Overview

The Token Budget System provides comprehensive tracking and monitoring of LLM token usage and costs across all supported providers. The system is designed to be fully compatible with Cline's architecture while maintaining backward compatibility with existing HordeForge components.

## Features

### Core Functionality
- **Token Tracking**: Monitor input, output, cache read/write, and reasoning tokens
- **Cost Calculation**: Automatic cost calculation based on provider pricing
- **Budget Limits**: Daily, monthly, and session budget controls
- **Tiered Pricing**: Support for context window-based pricing tiers
- **Usage History**: Persistent storage of usage data
- **CLI Integration**: Command-line tools for monitoring and management

### Cline Compatibility
- Full compatibility with Cline's `ModelInfo` structure
- Support for Cline's naming conventions (`maxTokens`, `contextWindow`, etc.)
- Compatible with Cline's pricing model and tiered pricing
- Backward compatibility maintained through property aliases

## Architecture

### Main Components

#### TokenBudgetSystem
The core system that manages all token tracking and budget enforcement:

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

#### ModelInfo Integration
Compatible with Cline's `ModelInfo` structure:

```python
from agents.llm_wrapper import ModelInfo

model_info = ModelInfo(
    name="gpt-4o",
    maxTokens=4096,
    contextWindow=128000,
    supportsImages=True,
    inputPrice=2.5,         # $2.5 per million tokens
    outputPrice=10.0,       # $10.0 per million tokens
    cacheWritesPrice=3.75,  # $3.75 per million tokens
    cacheReadsPrice=0.3,    # $0.3 per million tokens
    tiers=[                 # Tiered pricing support
        {
            "contextWindow": 128000,
            "inputPrice": 2.5,
            "outputPrice": 10.0
        }
    ]
)
```

#### TokenUsage Tracking
Comprehensive token usage tracking:

```python
from agents.token_budget_system import TokenUsage

usage = TokenUsage(
    inputTokens=1000,
    outputTokens=500,
    cacheWriteTokens=100,
    cacheReadTokens=200,
    thoughtsTokenCount=50,
    reasoningTokens=25
)
```

## Usage Examples

### Basic Token Tracking

```python
from agents.token_budget_system import TokenBudgetSystem
from agents.llm_wrapper import ModelInfo

budget_system = TokenBudgetSystem()

model_info = ModelInfo(
    name="test-model",
    inputPrice=2.5,
    outputPrice=10.0
)

usage = TokenUsage(
    inputTokens=1000,
    outputTokens=500
)

# Track usage and get cost breakdown
cost_breakdown = budget_system.track_usage("openai", model_info, usage)

print(f"Input cost: ${cost_breakdown.inputCost:.4f}")
print(f"Output cost: ${cost_breakdown.outputCost:.4f}")
print(f"Total cost: ${cost_breakdown.totalCost:.4f}")
```

### Tiered Pricing

```python
model_info = ModelInfo(
    name="gpt-4o",
    tiers=[
        {
            "contextWindow": 128000,
            "inputPrice": 2.5,
            "outputPrice": 10.0
        },
        {
            "contextWindow": 200000,
            "inputPrice": 1.5,
            "outputPrice": 7.5
        }
    ]
)

# Usage will be priced according to appropriate tier
usage = TokenUsage(inputTokens=150000, outputTokens=75000)
cost_breakdown = budget_system.track_usage("openai", model_info, usage)
```

### Budget Limit Enforcement

```python
from agents.token_budget_system import BudgetLimits

budget_system = TokenBudgetSystem(
    budget_limits=BudgetLimits(
        sessionLimit=1.0  # $1.00 limit
    )
)

# This will raise RuntimeError if budget is exceeded
try:
    cost_breakdown = budget_system.track_usage("provider", model_info, usage)
except RuntimeError as e:
    print(f"Budget exceeded: {e}")
```

## CLI Commands

### View Token Usage
```bash
# Show current token usage
horde llm tokens

# Show usage history
horde llm tokens --history
```

### View Cost Information
```bash
# Show total cost
horde llm cost
```

### Manage Budget Limits
```bash
# Show current budget status
horde llm budget

# Set daily budget limit
horde llm budget --set-daily 10.0

# Set monthly budget limit
horde llm budget --set-monthly 100.0

# Set session budget limit
horde llm budget --set-session 5.0
```

## Provider Integration

The system integrates with all supported providers and tracks token usage automatically:

### Supported Providers
- OpenAI
- Anthropic
- Google Gemini
- Ollama
- OpenRouter
- AWS Bedrock
- Google Vertex AI
- LM Studio
- DeepSeek
- Fireworks AI
- Together AI
- Qwen
- Mistral
- Hugging Face
- LiteLLM
- Moonshot
- Groq
- Claude Code

### Provider-Specific Features
Each provider supports:
- Accurate token counting
- Cost calculation based on provider rates
- Cache token tracking (where supported)
- Reasoning/thinking token tracking (where supported)

## Global Functions

### Access Global Instance
```python
from agents.token_budget_system import get_budget_system, get_cost_tracker

budget_system = get_budget_system()
cost_tracker = get_cost_tracker()
```

### Usage Summary
```python
from agents.token_budget_system import get_usage_summary

summary = get_usage_summary()
print(f"Today's cost: ${summary['total_cost']:.4f}")
```

### Budget Management
```python
from agents.token_budget_system import set_budget_limits, reset_session
from agents.token_budget_system import BudgetLimits

# Set new budget limits
new_limits = BudgetLimits(
    dailyLimit=15.0,
    monthlyLimit=150.0
)
set_budget_limits(new_limits)

# Reset session usage
reset_session()
```

## Data Persistence

Usage data is automatically persisted to:
- `~/.hordeforge/token_usage.json`

The system maintains:
- Daily usage history
- Monthly usage history
- Session usage tracking
- Total cost accumulation

## Error Handling

### Budget Limit Errors
When budget limits are exceeded, the system raises:
```python
RuntimeError("Session budget limit exceeded: $X.XXXX")
```

### Common Error Scenarios
- Session budget exceeded
- Daily budget exceeded
- Invalid token counts
- Missing pricing information

## Performance Considerations

- Thread-safe operation with internal locking
- Efficient memory usage for large usage histories
- Asynchronous-friendly design
- Minimal performance overhead

## Testing

The system includes comprehensive test coverage:
- Unit tests for all core components
- Integration tests with providers
- Budget limit enforcement tests
- Cost calculation accuracy tests

Run tests with:
```bash
pytest tests/unit/llm/test_token_budget_system.py
```

## Migration Guide

### From Previous Versions
- All existing `ModelInfo` fields remain compatible
- New Cline-compatible fields added as alternatives
- Backward compatibility maintained through properties
- No breaking changes to existing functionality

### Naming Convention Changes
Old naming → New Cline-compatible naming:
- `max_tokens` → `maxTokens`
- `context_window` → `contextWindow`
- `supports_images` → `supportsImages`
- `input_price` → `inputPrice`
- And so on for all fields

## Troubleshooting

### Common Issues
1. **Budget limits not enforced**: Ensure `BudgetLimits` are properly configured
2. **Incorrect costs**: Verify provider pricing information is current
3. **Missing token counts**: Check provider API responses for token information
4. **Performance issues**: Review usage tracking frequency

### Debugging
Enable logging to see detailed tracking information:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Security Considerations

- Token usage data stored locally
- No sensitive information in persisted data
- Budget limits help control API costs
- Rate limiting handled by individual providers

## Configuration

The Token Budget System can be configured through environment variables:

- `HORDEFORGE_TOKEN_BUDGET_DAILY_LIMIT` - Daily token budget limit
- `HORDEFORGE_TOKEN_BUDGET_MONTHLY_LIMIT` - Monthly token budget limit
- `HORDEFORGE_TOKEN_BUDGET_SESSION_LIMIT` - Session token budget limit
- `HORDEFORGE_TOKEN_BUDGET_ENABLED` - Enable/disable token budget tracking
- `HORDEFORGE_TOKEN_BUDGET_ALERT_THRESHOLD` - Threshold for budget alerts

## Integration with Other Systems

### CLI Integration
The system integrates with both CLI interfaces:
- `hordeforge llm tokens` - View token usage
- `horde llm tokens` - View token usage
- `hordeforge llm cost` - View cost information
- `horde llm cost` - View cost information

### Pipeline Integration
Token usage is tracked automatically during pipeline execution, with costs aggregated per pipeline run.

### Monitoring Integration
The system exports metrics to the monitoring system for cost tracking and alerting.
