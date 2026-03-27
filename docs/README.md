# HordeForge Documentation

Welcome to the comprehensive documentation for HordeForge, an autonomous AI software development orchestrator.

## Table of Contents

### Architecture and Design
- [Architecture Overview](ARCHITECTURE.md) - System architecture and component relationships
- [Agent Specification](AGENT_SPEC.md) - Standardized agent contracts and interfaces
- [Repository Structure](REPO_STRUCTURE.md) - Project organization and file layout
- [FR/NFR Requirements](FR_NFR.md) - Functional and non-functional requirements

### Getting Started
- [Quick Start](quick_start.md) - Rapid setup and first run
- [Development Setup](development_setup.md) - Local development environment
- [CLI Interface](cli_interface.md) - Command-line tools and usage

### Core Features
- [LLM Integration](llm_integration.md) - Multi-provider LLM support and configuration
- [Agent Memory System](agent_memory.md) - Historical solution storage and retrieval
- [Context Optimization](context_optimization.md) - Context compression and deduplication
- [Token Budget System](token_budget_system.md) - Cost tracking and budget management
- [Features Matrix](features.md) - Comprehensive feature list and status

### Operations
- [Operations Runbook](operations_runbook.md) - Operational procedures and runbooks
- [Launch Readiness Plan](launch_readiness_plan.md) - Production hardening and launch gates
- [Troubleshooting Guide](troubleshooting_guide.md) - Common issues and solutions
- [System Requirements](system_requirements.md) - Hardware and software requirements
- [Security Notes](security_notes.md) - Security practices and considerations

### Development
- [Development Workflow](development_workflow.md) - Development processes and practices
- [Quality Assurance](quality_assurance.md) - Testing and quality standards
- [Contributing Guide](contributing.md) - Contribution guidelines and standards
- [Migration Guide](migration_guide.md) - Migration procedures from previous versions

### Pipelines and Scheduling
- [Pipelines Documentation](pipelines.md) - Complete pipeline definitions and usage
- [Scheduler Integration](scheduler_integration.md) - Scheduling and webhook integration
- [Pipeline Memory Flow](pipeline_memory_flow.md) - Memory integration in pipelines
- [Use Cases](use_cases.md) - Detailed use cases and scenarios

### Monitoring and Performance
- [Metrics and Monitoring](metrics_and_monitoring.md) - Performance metrics and monitoring
- [Benchmark Results](benchmark_results.md) - Performance benchmarks and results
- [Performance Optimization](context_optimization.md) - Performance tuning and optimization

## Key Features

### AI Integration
- **Multi-Provider Support**: 18+ LLM providers including OpenAI, Anthropic, Google, Ollama, and more
- **Unified Interface**: Consistent API across all providers with streaming support
- **Token Budget System**: Comprehensive cost tracking and budget enforcement
- **Context Optimization**: Advanced compression and deduplication for efficient token usage

### Memory System
- **Historical Solutions**: Store and retrieve successful past solutions
- **Semantic Search**: Find relevant historical solutions using vector similarity
- **Automatic Recording**: Successful pipeline steps automatically stored in memory
- **Context Enhancement**: Combine historical and current repository context

### Pipeline Orchestration
- **Declarative Pipelines**: YAML-based pipeline definitions
- **Parallel Execution**: DAG-based dependency management with parallel processing
- **Retry and Loops**: Robust error handling with configurable retry policies
- **Human Override**: Manual control for intervention and debugging

### Security and Reliability
- **Token Redaction**: Automatic filtering of sensitive information
- **RBAC**: Role-based access control for operations
- **Tenant Isolation**: Multi-tenant security boundaries
- **Circuit Breakers**: Fault tolerance and resilience patterns

## Quick Navigation

### For Developers
1. Start with [Development Setup](development_setup.md) for local environment
2. Review [Agent Specification](AGENT_SPEC.md) for creating new agents
3. Check [CLI Interface](cli_interface.md) for development workflows
4. Follow [Development Workflow](development_workflow.md) for best practices

### For Operators
1. Begin with [System Requirements](system_requirements.md) for deployment
2. Review [Operations Runbook](operations_runbook.md) for operational procedures
3. Check [Security Notes](security_notes.md) for security practices
4. Use [Troubleshooting Guide](troubleshooting_guide.md) for issue resolution

### For Architects
1. Study [Architecture Overview](ARCHITECTURE.md) for system design
2. Review [FR/NFR Requirements](FR_NFR.md) for system capabilities
3. Examine [Pipelines Documentation](pipelines.md) for workflow design
4. Check [Metrics and Monitoring](metrics_and_monitoring.md) for observability

## Support and Community

- **Issue Tracking**: Use GitHub Issues for bug reports and feature requests
- **Discussions**: Use GitHub Discussions for questions and community support
- **Pull Requests**: Contributions are welcome through PRs
- **Documentation**: This documentation is continuously updated

## Version Information

Current version: 2.0.0
Last updated: March 27, 2026
Documentation status: Synced with codebase for MVP/P2; launch hardening items remain

## Contributing to Documentation

Documentation is maintained alongside code changes. See [Contributing Guide](contributing.md) for contribution guidelines and [Development Workflow](development_workflow.md) for documentation standards.

## Next Steps

1. **New to HordeForge?** Start with the [Quick Start](quick_start.md) guide
2. **Developing agents?** Review the [Agent Specification](AGENT_SPEC.md)
3. **Setting up production?** Check [System Requirements](system_requirements.md) and [Operations Runbook](operations_runbook.md)
4. **Integrating with LLMs?** Read [LLM Integration](llm_integration.md)

The documentation is organized to provide both high-level overviews and detailed technical information. Use the table of contents above to navigate to specific topics of interest.
