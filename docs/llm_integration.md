# LLM Integration System

## Overview

The LLM integration system in HordeForge provides a unified interface for working with multiple LLM providers, supporting both streaming and non-streaming operations with comprehensive cost tracking and budget management.

## Supported Providers

The system supports 18 different LLM providers:

- **OpenAI**: GPT models (gpt-4o, gpt-3.5-turbo, etc.)
- **Anthropic**: Claude models (sonnet, opus, haiku)
- **Google**: Gemini models (pro, flash, etc.)
- **Ollama**: Local open-source models
- **OpenRouter**: Access to 100+ models from various providers
- **AWS Bedrock**: Managed foundation models
- **Google Vertex AI**: Enterprise ML platform
- **LM Studio**: Local model serving
- **DeepSeek**: DeepSeek models
- **Fireworks AI**: Llama and other open models
- **Together AI**: Open-source model hosting
- **Qwen**: Alibaba Qwen models
- **Mistral**: Mistral AI models
- **Hugging Face**: Access to HF model hub
- **LiteLLM**: Proxy for multiple providers
- **Moonshot**: Moonshot AI models
- **Groq**: High-speed inference
- **Other providers**: Extensible architecture

## Architecture

### Core Components

```python
# Main API interface
class LlmApi:
    def create_message(...) -> AsyncGenerator[ApiStreamChunk, None]
    def get_model_info() -> tuple[str, ModelInfo]
    def get_usage() -> ApiStreamUsageChunk
    def abort() -> None

# Unified provider enum
class ApiProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    # ... all other providers

# Configuration class
class ApiConfiguration:
    provider: ApiProvider
    model: str
    api_key: Optional[str]
    # provider-specific settings
```

### Streaming Interface

The system uses a unified streaming interface with different chunk types:

- `ApiStreamTextChunk`: Text content from the model
- `ApiStreamUsageChunk`: Token usage and cost information
- `ApiStreamToolCallsChunk`: Function/tool call requests
- `ApiStreamThinkingChunk`: Reasoning/thought process

### Token Budget System

Comprehensive cost tracking and budget management:

```python
class TokenBudgetSystem:
    # Track usage by provider, date, and session
    daily_usage: Dict[str, TokenUsage]
    monthly_usage: Dict[str, TokenUsage]
    session_usage: Dict[str, TokenUsage]
    
    # Budget limits
    budget_limits: BudgetLimits
    # daily_limit, monthly_limit, session_limit
```

## Usage Examples

### Basic Usage

```python
from agents.llm_api import ApiConfiguration, ApiProvider, LlmApi

# Configure API
config = ApiConfiguration(
    provider=ApiProvider.OPENAI,
    model="gpt-4o",
    api_key="your-api-key"
)

api = LlmApi(config)

# Stream response
messages = [
    {"role": "user", "content": "Hello, world!"}
]

async for chunk in api.create_message("system prompt", messages):
    if isinstance(chunk, ApiStreamTextChunk):
        print(chunk.text, end="")
    elif isinstance(chunk, ApiStreamUsageChunk):
        print(f"Tokens: {chunk.input_tokens} input, {chunk.output_tokens} output")
```

### CLI Interface

The system includes a comprehensive CLI:

```bash
# Interactive chat
hordeforge llm chat --provider openai --model gpt-4o

# Plan mode
hordeforge llm plan "analyze this codebase"

# Act mode  
hordeforge llm act "implement feature X"

# Test connectivity
hordeforge llm test --provider anthropic

# View token usage
hordeforge llm tokens

# Set budget limits
hordeforge llm budget --set-daily 10.00
```

### Router Usage

Automatic provider selection based on task type:

```python
from agents.llm_api import LlmRouter

router = LlmRouter()

# Optimal provider for different tasks
code_llm = router.route_for_task("code")        # Uses OpenAI/GPT
analysis_llm = router.route_for_task("analysis") # Uses Anthropic/Claude
spec_llm = router.route_for_task("spec")        # Uses Google/Gemini
```

## Cost Management

### Pricing Models

Support for multiple pricing structures:

- **Flat pricing**: Simple input/output token rates
- **Tiered pricing**: Different rates based on usage volume
- **Cache pricing**: Separate pricing for prompt cache operations
- **Reasoning pricing**: Special pricing for thinking/thought tokens

### Budget Limits

Configure spending controls:

```python
from agents.token_budget_system import BudgetLimits, set_budget_limits

limits = BudgetLimits(
    daily_limit=10.00,      # $10 per day
    monthly_limit=100.00,   # $100 per month  
    session_limit=5.00      # $5 per session
)

set_budget_limits(limits)
```

## Environment Variables

Required environment variables by provider:

```bash
# OpenAI
HORDEFORGE_OPENAI_API_KEY=sk-...

# Anthropic
HORDEFORGE_ANTHROPIC_API_KEY=...

# Google
HORDEFORGE_GOOGLE_API_KEY=...

# Other providers
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
DEEPSEEK_API_KEY=...
# etc.
```

## Local Providers

### Ollama Setup

```bash
# Start Ollama server
ollama serve

# Pull required models
ollama pull llama2
ollama pull codellama

# Use in HordeForge
hordeforge llm chat --provider ollama --model llama2
```

### LM Studio Setup

```bash
# Start LM Studio with local model
# Configure base URL in settings
hordeforge llm chat --provider lmstudio --base-url http://localhost:1234
```

## Error Handling

The system includes robust error handling:

- Automatic retry with exponential backoff
- Fallback provider selection
- Graceful degradation
- Detailed error reporting

## Security

- API keys stored securely in environment variables
- No hardcoded credentials
- Secure connection handling
- Rate limiting protection

## Testing

Comprehensive testing framework:

```bash
# Run integration tests
python -m test_llm_integration

# Test specific providers
python -c "from agents.llm_api import create_openai_api; print('OpenAI OK')"
```

## Extending Support

New providers can be added by implementing the `ApiHandler` interface:

```python
class NewProviderHandler(ApiHandler):
    async def create_message(...):
        # Implementation
        pass
    
    def get_model(self):
        # Return model info
        pass
```

Then register in the factory system in `llm_api.py`.

## Best Practices

1. **Budget Management**: Always set appropriate budget limits
2. **Provider Fallback**: Configure multiple providers for reliability
3. **Local Models**: Use local providers (Ollama, LM Studio) for sensitive data
4. **Streaming**: Use streaming for large responses to manage memory
5. **Error Handling**: Implement proper error handling in production code
6. **Environment**: Use environment variables for API keys and configuration

## Advanced Features

### Context Optimization
The system includes context optimization features:
- Deduplication to remove redundant information
- Compression to reduce context size
- Memory management to store and retrieve historical solutions

### Agent Memory Integration
LLM calls can leverage agent memory to:
- Retrieve similar past solutions
- Learn from historical patterns
- Avoid repeating previous mistakes

### RAG Integration
The system seamlessly integrates with RAG (Retrieval Augmented Generation):
- Context retrieval from documentation
- Code snippet extraction
- Historical solution lookup
- Knowledge base integration

### Multi-modal Support
Some providers support multi-modal inputs:
- Image processing (OpenAI GPT-4o, Anthropic Claude)
- Audio processing (where supported)
- Video processing (where supported)

## Performance Considerations

- Streaming responses to manage memory usage
- Connection pooling for better performance
- Caching for frequently requested information
- Parallel processing where appropriate
- Efficient token usage to minimize costs

## Troubleshooting

Common issues and solutions:

1. **Rate Limits**: Implement exponential backoff and retry logic
2. **Authentication**: Verify API keys are correctly set in environment variables
3. **Network Issues**: Check connectivity to provider endpoints
4. **Token Limits**: Implement context window management
5. **Cost Overruns**: Monitor usage with the Token Budget System
6. **Provider Unavailability**: Use fallback providers and graceful degradation

## Monitoring and Observability

The system provides comprehensive monitoring:
- Token usage tracking
- Cost monitoring
- Response time metrics
- Error rate tracking
- Provider availability monitoring
- Budget compliance checking