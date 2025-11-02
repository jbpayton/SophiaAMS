# Sophia AMS - Python Agent Server Dockerfile
# Multi-stage build for optimized image size

FROM python:3.12-slim as base

# Set working directory
WORKDIR /app

# Install system dependencies and useful shell utilities
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    wget \
    git \
    vim \
    nano \
    jq \
    tree \
    htop \
    procps \
    net-tools \
    iputils-ping \
    dnsutils \
    unzip \
    zip \
    tar \
    gzip \
    findutils \
    grep \
    sed \
    gawk \
    less \
    file \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY agent_server.py .
COPY AssociativeSemanticMemory.py .
COPY VectorKnowledgeGraph.py .
COPY EpisodicMemory.py .
COPY PersistentConversationMemory.py .
COPY autonomous_agent.py .
COPY MemoryExplorer.py .
COPY message_queue.py .
COPY searxng_tool.py .

# Create directories for persistent data
RUN mkdir -p /app/data/episodic_memory \
    && mkdir -p /app/VectorKnowledgeGraphData/qdrant_data \
    && mkdir -p /app/logs

# Expose the agent server port
EXPOSE 5001

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5001/health || exit 1

# Run the agent server
CMD ["python", "agent_server.py"]
