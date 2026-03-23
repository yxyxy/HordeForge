# RAG Configuration

## Overview

HordeForge includes a Retrieval-Augmented Generation (RAG) system that provides intelligent document indexing and search capabilities. The RAG system supports three different operational modes to accommodate various deployment scenarios.

## Vector Store Modes

The RAG system can operate in three different modes:

### Local Mode
- Uses in-memory Qdrant storage
- All data is stored in memory and is ephemeral
- Ideal for development, testing, or isolated environments
- No external dependencies required

### Host Mode
- Connects to an external Qdrant server
- Requires a running Qdrant instance accessible via network
- Suitable for production environments with dedicated vector storage
- Provides persistent storage capabilities

### Auto Mode (Default)
- Attempts to connect to an external Qdrant server first
- Automatically falls back to local in-memory storage if the host is unavailable
- Provides maximum reliability and flexibility
- Recommended for most deployments

## Configuration

### Environment Variables

The RAG system is configured through the following environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `HORDEFORGE_VECTOR_STORE_MODE` | `auto` | Vector store mode: `local`, `host`, or `auto` |
| `QDRANT_HOST` | `qdrant` | Qdrant server host (used in `host` and `auto` modes) |
| `QDRANT_PORT` | `6333` | Qdrant server port (used in `host` and `auto` modes) |

### Example Configuration

```bash
# Use auto mode (recommended)
HORDEFORGE_VECTOR_STORE_MODE=auto
QDRANT_HOST=qdrant
QDRANT_PORT=6333
```

```bash
# Force local mode for development
HORDEFORGE_VECTOR_STORE_MODE=local
```

```bash
# Use external Qdrant server
HORDEFORGE_VECTOR_STORE_MODE=host
QDRANT_HOST=my-qdrant-server.com
QDRANT_PORT=6333
```

## Implementation Details

The vector store configuration is managed through the `rag.config` module:

- `get_vector_store_mode()` - Returns the current vector store mode
- `get_qdrant_host()` - Returns the configured Qdrant host
- `get_qdrant_port()` - Returns the configured Qdrant port
- `get_embedding_model()` - Returns the configured embedding model

The `QdrantStore` class in `rag.vector_store` handles the connection logic and automatically applies the selected mode based on configuration.

## Best Practices

1. **Development**: Use `local` mode for isolated development environments
2. **Testing**: Use `auto` mode to simulate production behavior
3. **Production**: Use `host` mode with a dedicated Qdrant instance for optimal performance and persistence
4. **Deployment**: `auto` mode provides the most resilient setup with automatic fallback capability

## Troubleshooting

If the RAG system fails to initialize:

1. Check that the configured Qdrant host is accessible (when using `host` or `auto` mode)
2. Verify that the Qdrant service is running and accepting connections
3. Ensure that the required ports are not blocked by firewalls
4. Review the application logs for specific error messages related to vector store initialization

The system will automatically log mode transitions and connection attempts to assist with debugging.