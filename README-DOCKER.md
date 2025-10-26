# Sophia AMS - Docker Deployment Guide

This guide explains how to deploy Sophia AMS using Docker and Docker Compose on Linux systems.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Development Mode](#development-mode)
- [Production Deployment](#production-deployment)
- [Service Architecture](#service-architecture)
- [Data Persistence](#data-persistence)
- [Troubleshooting](#troubleshooting)

## Overview

The Sophia AMS Docker setup consists of four containerized services:

1. **sophia-agent** - Python FastAPI agent server (Port 5001)
2. **sophia-server** - Node.js proxy/WebSocket server (Port 3001)
3. **sophia-web** - React frontend served by Nginx (Port 3000)
4. **qdrant** - Vector database for knowledge graph (Ports 6333, 6334)

All services communicate via an isolated Docker network and persist data through named volumes.

## Prerequisites

### Required Software

- **Docker Engine** 20.10+ ([Install Docker](https://docs.docker.com/engine/install/))
- **Docker Compose** 2.0+ (included with Docker Desktop)
- **Git** (to clone the repository)

### System Requirements

- **OS**: Linux (Ubuntu 20.04+, Debian 11+, CentOS 8+, etc.)
- **RAM**: Minimum 4GB, recommended 8GB+
- **Disk**: 10GB free space for images and data
- **CPU**: 2+ cores recommended

### External Services (Optional)

- **LLM API**: OpenAI-compatible endpoint (e.g., LM Studio, OpenAI API, local ollama)
- **SearXNG**: Search engine for web queries (optional)

## Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd SophiaAMS
```

### 2. Configure Environment

```bash
# Copy the example environment file
cp .env.docker.example .env

# Edit the .env file with your settings
nano .env
```

**Minimum required configuration:**

```env
# If using LM Studio on the Docker host machine
OPENAI_API_BASE=http://host.docker.internal:1234/v1
OPENAI_API_KEY=lm-studio

# Or if using OpenAI API
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=sk-your-actual-api-key-here
```

### 3. Build and Start Services

```bash
# Build all images and start services
docker-compose up -d

# View logs
docker-compose logs -f

# Check service status
docker-compose ps
```

### 4. Access the Application

Once all services are healthy (check with `docker-compose ps`):

- **Web Interface**: http://localhost:3000
- **API Server**: http://localhost:3001
- **Agent Server**: http://localhost:5001
- **Qdrant Dashboard**: http://localhost:6333/dashboard

### 5. Verify Installation

```bash
# Check agent health
curl http://localhost:5001/health

# Check server health
curl http://localhost:3001/health

# Check web health
curl http://localhost:3000/health
```

## Agent Capabilities

### Command-Line and Code Execution

The Sophia agent running in the container has powerful execution capabilities:

#### Shell Tool
The agent can execute Linux shell commands via the **shell** tool:
- File operations: `ls`, `cat`, `find`, `grep`, `mkdir`, `rm`, etc.
- Text processing: `grep`, `sed`, `awk`, `jq`
- Network utilities: `curl`, `wget`, `ping`
- Package management: `pip install`, `apt-get` (for system packages)
- Git operations: `git clone`, `git status`, `git log`
- System monitoring: `df`, `du`, `ps`, `htop`

**Example conversation:**
```
User: "Can you check what files are in the data directory?"
Sophia: *uses shell(command="ls -lah /app/data")*
```

#### Python REPL
The agent can write and execute Python code for:
- Data analysis and transformations
- Complex memory queries and filtering
- Scientific computing
- Testing ideas and concepts
- Access to `memory_system`, `json`, and standard libraries

**Example conversation:**
```
User: "Can you analyze the topic distribution in my knowledge graph?"
Sophia: *uses python_repl to query memory_system and analyze topics*
```

### Installed Utilities

The container comes with useful command-line tools:
- **Editors**: vim, nano
- **JSON processing**: jq
- **Archiving**: tar, zip, unzip, gzip
- **Network**: curl, wget, ping, netstat, dig
- **Monitoring**: htop, ps, top
- **Development**: git, build-essential
- **File utilities**: find, tree, grep, sed, awk, less

This means Sophia can autonomously:
- Download and process web data
- Analyze files and logs
- Install Python packages as needed
- Run scripts and utilities
- Monitor system resources
- Manage data files

## Configuration

### Environment Variables

Edit the `.env` file to customize your deployment:

#### LLM Configuration

```env
# OpenAI-compatible API endpoint
OPENAI_API_BASE=http://host.docker.internal:1234/v1

# API key
OPENAI_API_KEY=lm-studio
```

**Options:**
- **Local LM Studio**: `http://host.docker.internal:1234/v1`
- **OpenAI API**: `https://api.openai.com/v1`
- **Local Ollama**: `http://host.docker.internal:11434/v1`
- **Custom endpoint**: Any OpenAI-compatible API

#### Vector Database

```env
# Use containerized Qdrant (default)
QDRANT_URL=http://qdrant:6333

# Or use external Qdrant instance
QDRANT_URL=http://your-qdrant-server:6333
```

#### Search Engine

```env
# Enable web search with SearXNG
SEARXNG_URL=http://host.docker.internal:8088

# Disable web search
SEARXNG_URL=
```

#### Logging

```env
# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO
```

### Port Mapping

To change exposed ports, edit `docker-compose.yml`:

```yaml
services:
  sophia-web:
    ports:
      - "8080:3000"  # Change 8080 to your desired port
```

## Development Mode

For active development with hot-reload:

```bash
# Start in development mode
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Rebuild after dependency changes
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

**Development features:**
- Hot module replacement for React (Vite dev server)
- Nodemon for Node.js server auto-restart
- Source code mounted as volumes
- Debug logging enabled
- No optimization/minification

## Production Deployment

### 1. Build Production Images

```bash
# Build optimized images
docker-compose build --no-cache

# Or pull pre-built images if available
docker-compose pull
```

### 2. Configure for Production

```env
# Use production LLM endpoint
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=sk-your-production-key

# Set production log level
LOG_LEVEL=WARNING

# Production mode
NODE_ENV=production
```

### 3. Start with Resource Limits

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  sophia-agent:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
    restart: always

  sophia-server:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
    restart: always

  sophia-web:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 256M
    restart: always

  qdrant:
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 2G
    restart: always
```

Start with resource limits:

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 4. Enable HTTPS (Recommended)

Use a reverse proxy like Nginx or Traefik:

**Example Nginx configuration:**

```nginx
server {
    listen 443 ssl http2;
    server_name sophia.yourdomain.com;

    ssl_certificate /etc/ssl/certs/sophia.crt;
    ssl_certificate_key /etc/ssl/private/sophia.key;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://localhost:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 5. Set Up Automatic Backups

```bash
# Create backup script
cat > backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backup/sophia"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup volumes
docker run --rm \
  -v sophia_episodic_memory:/data/episodic \
  -v sophia_vector_data:/data/vector \
  -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/sophia_data_$DATE.tar.gz /data

# Keep only last 7 days of backups
find $BACKUP_DIR -name "sophia_data_*.tar.gz" -mtime +7 -delete
EOF

chmod +x backup.sh

# Add to crontab (daily at 2 AM)
echo "0 2 * * * /path/to/backup.sh" | crontab -
```

## Service Architecture

### Network Topology

```
External User
    ↓
[sophia-web:3000] ← Nginx serving React SPA
    ↓
[sophia-server:3001] ← Node.js proxy + WebSocket
    ↓
[sophia-agent:5001] ← Python FastAPI agent
    ↓
[qdrant:6333] ← Vector database
```

### Data Flow

1. **User Request** → React frontend (sophia-web)
2. **API Call** → Node.js server (sophia-server) via HTTP/WebSocket
3. **Agent Processing** → Python agent (sophia-agent) executes tools
4. **Knowledge Retrieval** → Qdrant vector database queries
5. **LLM Inference** → External LLM API (OpenAI/LM Studio)
6. **Response** → Back through the chain to user

### Internal Communication

All services communicate via the `sophia-network` Docker bridge network:

- Services use container names as hostnames
- External access via mapped ports
- Isolated from host network

## Data Persistence

### Named Volumes

The following Docker volumes persist data across container restarts:

| Volume | Purpose | Typical Size |
|--------|---------|--------------|
| `episodic_memory` | Conversation history (TinyDB) | 10-100 MB |
| `vector_data` | Vector embeddings (Qdrant) | 100 MB - 10 GB |
| `qdrant_storage` | Qdrant database files | Same as vector_data |
| `agent_logs` | Application logs | 10-500 MB |

### Volume Management

```bash
# List volumes
docker volume ls

# Inspect a volume
docker volume inspect sophia_episodic_memory

# Backup a volume
docker run --rm \
  -v sophia_episodic_memory:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/episodic_backup.tar.gz /data

# Restore a volume
docker run --rm \
  -v sophia_episodic_memory:/data \
  -v $(pwd):/backup \
  alpine sh -c "cd /data && tar xzf /backup/episodic_backup.tar.gz --strip 1"

# Remove all volumes (WARNING: deletes all data)
docker-compose down -v
```

### Data Location on Host

To find where volumes are stored:

```bash
docker volume inspect sophia_episodic_memory | grep Mountpoint
```

Typical location: `/var/lib/docker/volumes/<volume_name>/_data`

## Troubleshooting

### Service Won't Start

**Check logs:**
```bash
docker-compose logs sophia-agent
docker-compose logs sophia-server
docker-compose logs sophia-web
docker-compose logs qdrant
```

**Common issues:**

1. **Port already in use**
   ```bash
   # Find process using port 5001
   sudo lsof -i :5001
   # Kill or change port in docker-compose.yml
   ```

2. **Permission denied**
   ```bash
   # Fix volume permissions
   sudo chown -R 1000:1000 /var/lib/docker/volumes/sophia_*
   ```

3. **Out of memory**
   ```bash
   # Check Docker resources
   docker system df
   # Prune unused resources
   docker system prune -a
   ```

### Cannot Connect to LLM API

**If using `host.docker.internal`:**

```bash
# Test connectivity from container
docker exec sophia-agent curl http://host.docker.internal:1234/v1/models

# If it fails, use host IP instead:
ip addr show docker0 | grep inet
# Use the IP in .env: OPENAI_API_BASE=http://172.17.0.1:1234/v1
```

### Qdrant Connection Failed

```bash
# Check Qdrant health
curl http://localhost:6333/health

# View Qdrant logs
docker-compose logs qdrant

# Restart Qdrant
docker-compose restart qdrant
```

### Frontend Not Loading

**Check Nginx logs:**
```bash
docker exec sophia-web cat /var/log/nginx/error.log
```

**Rebuild frontend:**
```bash
docker-compose build --no-cache sophia-web
docker-compose up -d sophia-web
```

### Health Check Failing

```bash
# Check service health status
docker-compose ps

# Manual health check
curl -v http://localhost:5001/health
curl -v http://localhost:3001/health
curl -v http://localhost:3000/health
```

### Reset Everything

```bash
# Stop and remove all containers, networks, and volumes
docker-compose down -v

# Remove all images
docker-compose down --rmi all

# Start fresh
docker-compose up --build -d
```

### View Resource Usage

```bash
# Real-time stats
docker stats

# Specific container
docker stats sophia-agent
```

### Debug Mode

Enable verbose logging:

```env
LOG_LEVEL=DEBUG
PYTHONUNBUFFERED=1
```

```bash
# Restart with debug logging
docker-compose restart sophia-agent
docker-compose logs -f sophia-agent
```

## Advanced Usage

### Scale Services

```bash
# Run multiple agent instances (requires load balancer)
docker-compose up -d --scale sophia-agent=3
```

### Use External Qdrant

```env
# In .env
QDRANT_URL=http://your-qdrant-cluster:6333
```

```yaml
# In docker-compose.yml, comment out qdrant service
services:
  # qdrant:
  #   image: qdrant/qdrant:latest
  #   ...
```

### Custom Network

```yaml
networks:
  sophia-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16
```

### Environment-Specific Configs

```bash
# Development
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Production
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up

# Testing
docker-compose -f docker-compose.yml -f docker-compose.test.yml up
```

## Maintenance

### Update Images

```bash
# Pull latest changes
git pull

# Rebuild images
docker-compose build --pull

# Restart with new images
docker-compose up -d
```

### Clean Up

```bash
# Remove stopped containers
docker-compose rm

# Remove unused images
docker image prune -a

# Remove unused volumes (careful!)
docker volume prune

# Full cleanup
docker system prune -a --volumes
```

### Monitor Logs

```bash
# Follow all logs
docker-compose logs -f

# Specific service
docker-compose logs -f sophia-agent

# Last 100 lines
docker-compose logs --tail=100

# Since timestamp
docker-compose logs --since 2024-01-01T00:00:00
```

## Security Considerations

1. **API Keys**: Never commit `.env` to version control
2. **Network Isolation**: Use custom networks for multi-tier security
3. **Resource Limits**: Set memory/CPU limits to prevent DoS
4. **HTTPS**: Always use TLS in production
5. **Firewall**: Only expose necessary ports (3000, 3001 behind reverse proxy)
6. **Updates**: Regularly update base images for security patches

```bash
# Update base images
docker-compose pull
docker-compose up -d
```

## Support

For issues or questions:

- Check logs: `docker-compose logs`
- Review this documentation
- Open an issue on the repository
- Check Docker documentation: https://docs.docker.com

## License

[Your License Here]

---

**Last Updated**: 2024-01-25
**Docker Compose Version**: 3.8
**Tested On**: Ubuntu 22.04, Debian 12, CentOS 8
