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

# Run specific pipeline
horde pipeline run init --repo-url https://github.com/user/repo --token YOUR_TOKEN

# LLM operations
horde llm --provider openai --model gpt-4o "Your prompt here"
horde llm list-providers
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

# Run init pipeline
horde pipeline run init --repo-url https://github.com/user/repo --token YOUR_TOKEN

# Run feature pipeline
horde pipeline run feature --inputs '{"prompt": "Add user authentication"}'
```

## Provider Selection

### Available Providers

- `openai` - OpenAI GPT models
- `anthropic` - Anthropic Claude models
- `google` - Google Gemini models
- `ollama` - Local Ollama models
- `bedrock` - AWS Bedrock models
- `vertex` - Google Cloud Vertex AI
- `groq` - Groq models
- `together` - Together AI models
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

Manage multiple configuration profiles (available in both CLIs):

```bash
# Save current settings
horde llm settings --save --profile work

# Load settings
horde llm settings --load --profile work

# List all profiles
horde llm settings --list-profiles

# Switch to profile
horde llm settings --switch-profile work

# Delete profile
horde llm settings --delete-profile old-profile

# Export profile
horde llm settings --export-profile work

# Import profile
horde llm settings --import-profile work_settings.json
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
horde llm --provider bedrock --region us-west-2 --model anthropic.claude-sonnet-4-5-20250929-v1:0 "Your prompt"

# Google Vertex AI
horde llm --provider vertex --project-id my-project --model gemini-1.5-pro-001 "Your prompt"
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
- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic API key
- `GOOGLE_API_KEY` - Google API key
- `AWS_ACCESS_KEY_ID` - AWS access key (for Bedrock)
- `AWS_SECRET_ACCESS_KEY` - AWS secret key (for Bedrock)
- `AWS_SESSION_TOKEN` - AWS session token (for Bedrock)

## Configuration Files

Settings are stored in:
- `~/.hordeforge/llm_settings.json` - Default settings
- `~/.hordeforge/profiles/` - Named profiles

## Examples

### Quick Start with New CLI
```bash
# Simple query with new interactive CLI
horde "What is Python?"

# With specific provider
horde llm --provider anthropic "Explain machine learning"

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
horde pipeline run init --repo-url https://github.com/user/repo --token YOUR_TOKEN

# Run feature pipeline
horde pipeline run feature --inputs '{"prompt": "Add user management"}'
```

### Multi-Provider Workflow
```bash
# Compare responses with new CLI
horde llm --provider openai "Write a poem" > openai_poem.txt
horde llm --provider anthropic "Write a poem" > anthropic_poem.txt
```

### Profile-Based Workflows
```bash
# Setup work profile
horde llm --provider openai --model gpt-4o --save --profile work
horde llm settings --switch-profile work

# Setup local development profile
horde llm --provider ollama --model llama2 --save --profile local
horde llm settings --switch-profile local
```

### Docker Compose Usage
```bash
# Start services
docker-compose up -d

# Run commands in container
docker exec hordeforge-gateway horde task "Implement new feature"
docker exec hordeforge-gateway horde pipeline list

# Enter container for interactive session
docker exec -it hordeforge-gateway bash
horde  # Start interactive mode
```
