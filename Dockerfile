# Multi-stage build for Horde CLI
FROM python:3.11-slim as builder

WORKDIR /app
COPY . .

# Install dependencies required for building CLI
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Build the CLI application
RUN python setup.py install

FROM python:3.11-slim

WORKDIR /app

# Copy only the built CLI from the builder stage
COPY --from=builder /usr/local/bin/horde /usr/local/bin/horde

# Create necessary directories for configuration
RUN mkdir -p /etc/horde /root/.horde

# Set proper permissions
RUN chmod +x /usr/local/bin/horde

# Copy any necessary runtime dependencies
COPY --from=builder /usr/local/lib/python*/site-packages /usr/local/lib/python*/site-packages

CMD ["bash"]