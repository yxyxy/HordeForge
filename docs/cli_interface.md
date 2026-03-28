# CLI Interface Documentation

## Overview

The HordeForge CLI provides command-line access to the full AI development orchestrator with support for multiple providers, interactive development, pipeline management, and advanced configuration management. The CLI includes two main commands: `hordeforge` (original) and `horde` (new interactive command).

## Installation

### Local Installation

Install the CLI as part of the HordeForge package for local development and direct usage:

```bash
# Clone the repository
git clone https://github.com/yourusername/HordeForge.git
cd HordeForge

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e .
```

After installation, both commands will be available:
- `hordeforge` - Original CLI for gateway operations
- `horde` - New interactive CLI for development workflows

### Docker Compose Installation

When running HordeForge through Docker Compose, the CLI is available inside the gateway container. Access it using docker exec commands or enter the container interactively:

```bash
# Start the services
docker-compose up -d

# Run CLI commands directly
docker exec hordeforge-gateway horde --help

# Enter the container interactively
docker exec -it hordeforge-gateway bash

# Inside the container, run CLI commands
horde --help
horde task "Implement user authentication"
```

## Basic Usage

### Main Commands

#### New Interactive CLI (`horde`)

```bash
# Show help
horde --help

# Run a task
horde task "Implement user authentication"

# Interactive mode (starts interactive session)
horde

# Run with plan/act modes
horde --plan "Design the database schema"
horde --act "Deploy the application"

# Check system status
horde status
horde health

# List available pipelines
horde pipeline list

# One-time repository profile setup
horde repo add yxyxy/HordeForge --url https://github.com/yxyxy/HordeForge --token YOUR_GITHUB_TOKEN --set-default

# Run init by repository profile id
horde init yxyxy/HordeForge
horde pipeline run init yxyxy/HordeForge

# Infra operations
horde infra mode show
horde infra mode set team --save
horde infra stack up
horde infra stack up --build
horde infra stack up --recreate
horde infra mcp up

# LLM operations
horde llm --provider openai --model gpt-4o "Your prompt here"
horde llm list-providers

# LLM profile management
horde llm profile add openai-main --provider openai --model gpt-4o --api-key YOUR_OPENAI_KEY --set-default
horde llm --profile openai-main test
```

#### Original CLI (`hordeforge`)

```bash
# Show help
hordeforge --help

# Run with specific provider and model
hordeforge llm --provider openai --model gpt-4o "Your prompt here"

# Interactive chat mode
hordeforge llm chat
```

## Interactive Development Features

### Task Management

The new `horde` command provides Cline-like interactive development experience:

```bash
# Start interactive development session
horde

# Run specific tasks
horde task "Fix the authentication bug"
horde task --plan "Refactor the user management system"
horde task --act "Deploy the new feature to staging"

# View task history
horde history
horde history --limit 20
```

### Pipeline Operations

Manage development pipelines directly from CLI:

```bash
# List available pipelines
horde pipeline list

# Run init pipeline by profile id
horde init yxyxy/HordeForge
horde pipeline run init yxyxy/HordeForge

# Run feature pipeline
horde pipeline run feature --inputs '{"prompt": "Add user authentication"}'
```

## Provider Selection

### Available Providers

- `openai` - OpenAI GPT models
- `anthropic` - Anthropic Claude models
- `google` - Google Gemini models
- `ollama` - Local Ollama models
- `openrouter` - OpenRouter models
- `aws_bedrock` - AWS Bedrock models
- `google_vertex` - Google Cloud Vertex AI
- `lm_studio` - LM Studio models
- `deepseek` - DeepSeek models
- `fireworks` - Fireworks AI models
- `together` - Together AI models
- `qwen` - Alibaba Qwen models
- `mistral` - Mistral AI models
- `huggingface` - Hugging Face models
- `litellm` - LiteLLM proxy
- `moonshot` - Moonshot AI models
- `groq` - Groq models
- `other` - Other OpenAI-compatible providers
- And many more...

### Selecting a Provider

```bash
# Using command line argument with new CLI
horde llm --provider openai --model gpt-4o "Hello, world!"

# Using original CLI
hordeforge llm --provider openai --model gpt-4o "Hello, world!"

# Using environment variables
export OPENAI_API_KEY="your-key-here"
horde llm --provider openai "Hello, world!"
```

## Plan/Act Modes

Both CLIs support Cline-like plan/act modes for different types of interactions:

### Plan Mode

Analyze and create detailed plans (available in both CLIs):

```bash
# New CLI - with interactive features
horde --plan "How should I refactor this codebase?"
horde task --plan "Design the API architecture"

# Original CLI
hordeforge llm --plan "How should I refactor this codebase?"
hordeforge llm plan "How should I refactor this codebase?"
```

### Act Mode

Execute actions and perform tasks (available in both CLIs):

```bash
# New CLI - with interactive features
horde --act "Write a Python function to sort an array"
horde task --act "Deploy the application to production"

# Original CLI
hordeforge llm --act "Write a Python function to sort an array"
hordeforge llm act "Write a Python function to sort an array"
```

## Interactive Chat

Start an interactive chat session (available in both CLIs):

```bash
# New CLI
horde llm chat

# Original CLI
hordeforge llm chat

# Chat with system prompt
horde llm chat --system "You are a helpful coding assistant"

# Chat with file as system prompt
horde llm chat --file system_prompt.txt
```

## Settings Management

### Profile Management

Manage repository and LLM profiles from local JSON store (`~/.hordeforge/config.json`) and secrets store (`~/.hordeforge/secrets.json`):

```bash
# Repository profiles
horde repo add yxyxy/HordeForge --url https://github.com/yxyxy/HordeForge --token YOUR_GITHUB_TOKEN --set-default
horde repo list
horde repo use yxyxy/HordeForge
horde repo show yxyxy/HordeForge

# Secrets
horde secret set llm.openai YOUR_OPENAI_KEY
horde secret list
horde secret remove llm.openai

# LLM profiles
horde llm profile add openai-main --provider openai --model gpt-4o --secret-ref llm.openai --set-default
horde llm profile list
horde llm profile use openai-main
horde llm profile show openai-main
horde llm profile remove openai-main
horde llm --profile openai-main test
```

### Legacy LLM Settings

Legacy `horde llm settings` subcommands are still available for compatibility:

```bash
horde llm settings --list-profiles
horde llm settings --save --profile work
horde llm settings --load --profile work
```

### Global Settings Mode

Access settings interface directly (available in both CLIs):

```bash
# Enter settings mode
horde llm --settings
hordeforge llm --settings
```

### API Key Validation

Validate your API keys (available in both CLIs):

```bash
# Test provider connectivity
horde llm settings --validate --provider openai
hordeforge llm settings --validate --provider openai
```

## Advanced Options

### Model Selection

```bash
# Specify model explicitly with new CLI
horde llm --provider openai --model gpt-4o "Your prompt"

# For local providers, specify base URL
horde llm --provider ollama --base-url http://localhost:11434 --model llama2 "Your prompt"
```

### Cloud Provider Specific Options

```bash
# AWS Bedrock
horde llm --provider aws_bedrock --region us-west-2 --model anthropic.claude-sonnet-4-5-20250929-v1:0 "Your prompt"

# Google Vertex AI
horde llm --provider google_vertex --project-id my-project --model gemini-1.5-pro-001 "Your prompt"
```

## Token and Cost Tracking

Monitor your usage (available in both CLIs):

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

# Set budget limits
horde llm budget --set-daily 10.0
horde llm budget --set-monthly 100.0
horde llm budget --set-session 5.0

# View budget information
horde llm budget
```

## Available Subcommands for `horde`

### `task` - Run Development Tasks
```bash
horde task [PROMPT] [OPTIONS]
```
Options:
- `-a, --act`: Run in act mode
- `-p, --plan`: Run in plan mode
- `--model`: Model to use for the task
- `--timeout`: Timeout in seconds

### `history` - Show Task History
```bash
horde history [OPTIONS]
```
Options:
- `-n, --limit`: Number of tasks to show (default: 10)
- `--page`: Page number (default: 1)

### `config` - Show Configuration
```bash
horde config
```

### `status` - Check System Status
```bash
horde status
```

### `health` - Check Gateway Health
```bash
horde health
```

### `pipeline` - Manage Pipelines
```bash
horde pipeline [SUBCOMMAND]
```
Subcommands:
- `list`: List available pipelines
- `run [NAME]`: Run a specific pipeline

### `infra` - Manage Infrastructure
```bash
horde infra [SUBCOMMAND]
```
Subcommands:
- `mode show`: Show effective mode and resolved backends
- `mode set local|team [--save] [--profile NAME]`: Set mode defaults
- `qdrant up|down|status`: Manage Qdrant service
- `mcp up|down|status`: Manage MCP bridge service
- `stack up|down|status`: Manage full stack

`stack up` behavior:
- default is safe (`--no-recreate`)
- use `--build` to rebuild images
- use `--recreate` to force container recreation
- example: `horde infra stack up --build --recreate`

`mode set` behavior:
- without `--save`, values apply only to the current CLI process call
- use `--save` (or `--save --profile ...`) to persist mode defaults

### `llm` - LLM Operations
```bash
horde llm [OPTIONS] [SUBCOMMANDS]
```
Same subcommands as original CLI (chat, plan, act, test, list-providers, etc.)

## Available Subcommands for `hordeforge`

### `llm` - LLM Operations
```bash
hordeforge llm [OPTIONS] [SUBCOMMANDS]
```
Options:
- `--provider`: LLM provider to use
- `--model`: Model name to use
- `--api-key`: API key for the provider
- `--base-url`: Base URL for local providers
- `--plan`: Plan mode - analyze and plan
- `--act`: Act mode - execute actions
- `--settings`: Open settings configuration

Subcommands:
- `chat` - Interactive chat with LLM
- `plan` - Plan mode - analyze and plan
- `act` - Act mode - execute actions
- `test` - Test provider connectivity
- `list-providers` - List available providers
- `settings` - Manage provider settings
- `tokens` - Show token usage
- `cost` - Show cost information
- `budget` - Show budget information

## Environment Variables

Both CLIs respect the following environment variables:

- `HORDEFORGE_GATEWAY_URL` - Gateway URL (default: http://localhost:8000)
- `HORDEFORGE_PIPELINES_DIR` - Pipelines directory (default: pipelines)
- `HORDEFORGE_STORAGE_DIR` - Storage directory (default: .hordeforge_data)
- `HORDEFORGE_QUEUE_BACKEND` - Queue backend (default: memory)
- `HORDEFORGE_LLM_PROVIDER` - Default LLM provider (default: openai)
- `HORDEFORGE_OPENAI_API_KEY` - OpenAI API key
- `HORDEFORGE_ANTHROPIC_API_KEY` - Anthropic API key
- `HORDEFORGE_GOOGLE_API_KEY` - Google API key
- `HORDEFORGE_AWS_ACCESS_KEY_ID` - AWS access key (for Bedrock)
- `HORDEFORGE_AWS_SECRET_ACCESS_KEY` - AWS secret key (for Bedrock)
- `HORDEFORGE_AWS_SESSION_TOKEN` - AWS session token (for Bedrock)
- `HORDEFORGE_OLLAMA_BASE_URL` - Ollama base URL (default: http://localhost:11434)
- `HORDEFORGE_VERTEX_PROJECT_ID` - Google Vertex project ID
- `HORDEFORGE_VERTEX_LOCATION` - Google Vertex location
- `HORDEFORGE_BEDROCK_REGION` - AWS Bedrock region (default: us-east-1)
- `HORDEFORGE_TOKEN_BUDGET_DAILY_LIMIT` - Daily token budget limit
- `HORDEFORGE_TOKEN_BUDGET_MONTHLY_LIMIT` - Monthly token budget limit
- `HORDEFORGE_TOKEN_BUDGET_SESSION_LIMIT` - Session token budget limit

## Configuration Files

Settings are stored in:
- `~/.hordeforge/config.json` - Repository and LLM profiles (including default selections)
- `~/.hordeforge/secrets.json` - Secret values referenced by profiles
- `~/.hordeforge/llm_settings.json` - Legacy LLM settings storage (compatibility mode)
- `~/.hordeforge/profiles/` - Legacy named profile files used by `llm settings`

## Examples

### Quick Start with New CLI
```bash
# Simple LLM query
horde llm --provider anthropic llm "Explain machine learning"

# Run a development task
horde task "Implement user authentication system"
```

### Interactive Development
```bash
# Start interactive session
horde

# Or run specific commands
horde task --plan "Add user authentication to my Flask app"
horde task --act "Write the login endpoint for Flask"

# Check system status
horde status
horde config
```

### Pipeline Management
```bash
# List and run pipelines
horde pipeline list
horde repo add yxyxy/HordeForge --url https://github.com/yxyxy/HordeForge --token YOUR_GITHUB_TOKEN --set-default
horde init yxyxy/HordeForge

# Run feature pipeline
horde pipeline run feature --inputs '{"prompt": "Add user management"}'
```

### Multi-Provider Workflow
```bash
# Compare responses with new CLI
horde llm --provider openai llm "Write a poem" > openai_poem.txt
horde llm --provider anthropic llm "Write a poem" > anthropic_poem.txt
```

### Profile-Based Workflows
```bash
# Setup OpenAI profile with stored secret
horde secret set llm.openai YOUR_OPENAI_KEY
horde llm profile add work --provider openai --model gpt-4o --secret-ref llm.openai --set-default
horde llm --profile work test

# Setup local development profile
horde llm profile add local --provider ollama --model llama2 --base-url http://localhost:11434
horde llm --profile local test
```

### Docker Compose Usage
```bash
# Start services
docker compose up -d

# Run commands in container
docker exec hordeforge-gateway horde task "Implement new feature"
docker exec hordeforge-gateway horde pipeline list

# Safe infra stack up (no recreate)
docker exec hordeforge-gateway horde infra stack up

# Explicit rebuild/recreate when needed
docker exec hordeforge-gateway horde infra stack up --build --recreate

# Enter container for interactive session
docker exec -it hordeforge-gateway bash
horde  # Start interactive mode
```

### Token Budget Management
```bash
# Check current token usage
horde llm tokens

# Check cost information
horde llm cost

# Set daily budget limit
horde llm budget --set-daily 10.0

# View current budget status
horde llm budget
```

### Advanced LLM Operations
```bash
# Run with specific model and temperature
horde llm --provider openai --model gpt-4o --temperature 0.7 "Generate code for..."

# Use streaming mode
horde llm --stream --provider anthropic "Explain this concept..."

# Run with custom system prompt
horde llm --system "You are a Python expert" --provider openai "Write a function..."

# Test provider connectivity
horde llm test --provider google

# List all available models for a provider
horde llm list-models --provider openai
```

### Memory and Context Management
```bash
# The CLI automatically uses Agent Memory and RAG context when available
# No special commands needed - context is automatically included in requests
horde task "Implement feature based on previous solutions"
```

### Agent and Pipeline Management
```bash
# List all available agents
horde agents list

# Get detailed information about an agent
horde agents show code_generator

# List pipeline runs
horde runs list

# Get details of a specific run
horde runs show RUN_ID

# Override a running pipeline
horde runs override RUN_ID --action retry --reason "manual retry"
```

