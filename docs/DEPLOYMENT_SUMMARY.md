# Sophia AMS - Docker Deployment Summary

## What Was Created

This document summarizes the complete Docker containerization and automated deployment system created for Sophia AMS.

### Files Created/Modified

#### Core Docker Configuration
1. **Dockerfile** - Python agent server container with shell utilities
   - Base: Python 3.12 slim
   - Includes: curl, wget, git, vim, nano, jq, htop, and more
   - Healthcheck: Agent server `/health` endpoint
   - Volumes: Episodic memory, vector data, logs

2. **sophia-web/server/Dockerfile** - Node.js proxy server container
   - Base: Node 18 alpine
   - Express.js + WebSocket server
   - Healthcheck: Server `/health` endpoint

3. **sophia-web/client/Dockerfile** - React frontend (multi-stage build)
   - Stage 1: Node 18 for building React app
   - Stage 2: Nginx alpine for serving static files
   - Production-optimized bundle

4. **sophia-web/client/nginx.conf** - Nginx configuration
   - Gzip compression
   - Security headers
   - React Router support (SPA)
   - Static asset caching

5. **docker-compose.yml** - Service orchestration
   - 4 services: sophia-agent, sophia-server, sophia-web, qdrant
   - Named volumes for data persistence
   - Health checks and dependencies
   - Internal Docker networking

6. **docker-compose.dev.yml** - Development overrides
   - Hot module replacement for React
   - Source code volume mounting
   - Nodemon for Node.js auto-restart
   - Debug logging

#### Automation Scripts

7. **install.sh** - Automated installation script (755 lines)
   - Detects OS and installs Docker if needed
   - Clones repository (or uses current directory)
   - Interactive environment configuration
   - Builds and starts all services
   - Verifies installation with health checks
   - Usage: `curl -fsSL [...]/install.sh | bash`

8. **update.sh** - Update script (323 lines)
   - Backs up `.env` configuration
   - Pulls latest Git changes
   - Rebuilds Docker images
   - Restarts services with minimal downtime
   - Preserves data volumes
   - Usage: `./update.sh`

9. **uninstall.sh** - Uninstallation script (368 lines)
   - Options to keep data/images/directory
   - Safe removal with confirmations
   - Cleans up containers and volumes
   - Usage: `./uninstall.sh [--keep-data] [--keep-images]`

#### Configuration Files

10. **.env.docker.example** - Environment template
    - Updated with all variables from `env_example`
    - Both legacy and Docker-specific variables
    - LLM API, Qdrant, SearXNG configuration
    - Model-specific settings
    - Embedding configuration

11. **.dockerignore** - Docker build optimization
    - Excludes Python cache, node_modules
    - Excludes data directories (mounted as volumes)
    - Excludes Git, IDEs, documentation

#### Documentation

12. **README-DOCKER.md** - Comprehensive deployment guide (667 lines)
    - Quick start with automated installation
    - Manual installation instructions
    - Configuration examples
    - Development and production modes
    - Architecture diagrams
    - Data persistence explanation
    - Troubleshooting guide
    - Maintenance procedures
    - Security considerations

13. **INSTALLATION.md** - Quick installation guide (334 lines)
    - One-command installation
    - Prerequisites and requirements
    - Common configurations
    - Troubleshooting quick reference
    - Getting started with Sophia

#### Code Changes

14. **agent_server.py** - Added ShellTool integration
    - Imported `ShellTool` from `langchain_community.tools`
    - Added shell tool to agent tools list (~80 lines)
    - Comprehensive documentation in tool description
    - Updated system prompts to mention shell capabilities
    - Updated autonomous mode prompt

## Key Features

### Complete Container Stack
- **Python Agent Server** (Port 5001) - FastAPI with LangChain
- **Node.js Proxy** (Port 3001) - WebSocket + HTTP proxy
- **React Frontend** (Port 3000) - Nginx-served SPA
- **Qdrant Vector DB** (Ports 6333, 6334) - Knowledge graph storage

### Agent Capabilities in Container
- **Shell Tool**: Execute Linux commands (ls, grep, curl, git, etc.)
- **Python REPL**: Run Python code with memory system access
- **Internet Access**: Web search, page reading, API calls
- **Package Management**: Install packages as needed (pip, apt-get)
- **File Operations**: Create, read, modify files
- **Network Operations**: Download data, make API calls

### Deployment Features
- ✅ One-command installation on fresh Linux systems
- ✅ Automatic dependency installation (Docker, Git, etc.)
- ✅ Interactive configuration prompts
- ✅ Health checks and service verification
- ✅ Data persistence across restarts
- ✅ Hot-reload for development
- ✅ Production-optimized builds
- ✅ Easy updates with `./update.sh`
- ✅ Safe uninstall with data preservation options

### Data Persistence
All important data persists in Docker volumes:
- **episodic_memory** - Conversation history (TinyDB)
- **vector_data** - Vector embeddings (Qdrant)
- **qdrant_storage** - Qdrant database files
- **agent_logs** - Application logs

## Installation Methods

### Method 1: Automated (Recommended)
```bash
curl -fsSL https://raw.githubusercontent.com/jbpayton/SophiaAMS/main/install.sh | bash
```

### Method 2: Manual
```bash
git clone https://github.com/jbpayton/SophiaAMS.git
cd SophiaAMS
cp .env.docker.example .env
# Edit .env with your settings
docker-compose up -d
```

### Method 3: Development
```bash
git clone https://github.com/jbpayton/SophiaAMS.git
cd SophiaAMS
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

## Network Architecture

```
Internet
   ↓
User Browser
   ↓
[sophia-web:3000] ← Nginx + React
   ↓
[sophia-server:3001] ← Node.js Proxy + WebSocket
   ↓
[sophia-agent:5001] ← Python FastAPI + LangChain
   ↓
[qdrant:6333] ← Vector Database
   ↓
External LLM API (OpenAI/LM Studio/etc.)
```

### Internal Docker Network
All services communicate via `sophia-network` bridge network:
- Containers use service names as hostnames
- Qdrant accessible at `http://qdrant:6333`
- Agent accessible at `http://sophia-agent:5001`
- Isolated from host network

### External Access
- Host machine accessible via `host.docker.internal`
- Internet access enabled by default
- Port mapping for external access

## Environment Variables

### Required
```env
LLM_API_BASE=http://localhost:1234/v1
OPENAI_API_BASE=http://host.docker.internal:1234/v1
LLM_API_KEY=not-needed
OPENAI_API_KEY=not-needed
```

### Optional
```env
LLM_MODEL=zai-org/glm-4.7-flash
SEARXNG_URL=http://localhost:8088
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
LOG_LEVEL=INFO
```

### Docker-Specific
```env
QDRANT_URL=http://qdrant:6333
AGENT_PORT=5001
VITE_API_URL=http://localhost:3001
```

## Testing the Installation

Once deployed, test with:

```bash
# Check health endpoints
curl http://localhost:5001/health  # Agent
curl http://localhost:3001/health  # Proxy
curl http://localhost:3000/health  # Web
curl http://localhost:6333/health  # Qdrant

# Check container status
docker-compose ps

# View logs
docker-compose logs -f

# Access web interface
open http://localhost:3000
```

## Shell Tool Examples

Sophia can now execute Linux commands:

```python
# File operations
shell(command="ls -lah /app/data")
shell(command="find /app -name '*.py' -type f")

# Data processing
shell(command="cat data.json | jq '.results'")

# Network operations
shell(command="curl -s https://api.github.com/repos/user/repo")

# Package management
shell(command="pip install beautifulsoup4 requests")

# System monitoring
shell(command="df -h && free -m")

# Git operations
shell(command="git clone https://github.com/user/repo")
```

## Maintenance Commands

```bash
# Update Sophia
cd ~/SophiaAMS
./update.sh

# Restart services
docker-compose restart

# View logs
docker-compose logs -f sophia-agent

# Stop services
docker-compose down

# Start services
docker-compose up -d

# Rebuild from scratch
docker-compose build --no-cache
docker-compose up -d

# Backup data
docker run --rm \
  -v sophia_episodic_memory:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/sophia-backup.tar.gz /data

# Uninstall
./uninstall.sh
```

## Security Considerations

1. **API Keys**: The `.env` file contains sensitive keys - never commit to Git
2. **Network Exposure**: By default, services bind to `0.0.0.0` (accessible from network)
3. **Shell Access**: Agent has shell command execution - runs as non-root in isolated container
4. **Data Volumes**: Persistent volumes stored in `/var/lib/docker/volumes/`
5. **HTTPS**: Production deployments should use reverse proxy with TLS

### Recommended for Production
- Use HTTPS with Nginx/Traefik reverse proxy
- Set resource limits (CPU/memory)
- Enable firewall rules
- Regular backups
- Keep base images updated
- Use secrets management for API keys

## What's Next?

### On Your Linux Server
1. Run the installation script
2. Configure LLM API endpoint
3. Access web interface at `http://your-server:3000`
4. Start chatting with Sophia!

### Development Workflow
1. Make code changes on Windows
2. Test locally (or in WSL2)
3. Commit and push to Git
4. Run `./update.sh` on Linux server
5. Services auto-rebuild and restart

### Sophia Can Now
- Execute shell commands in Linux container
- Run Python code with memory system access
- Search the web and read pages
- Manage files and data
- Install packages as needed
- Work on personal goals autonomously
- Learn from web content
- Remember conversations

## Files Staged for Commit

The following files are ready to commit:

```
modified:   .env.docker.example
modified:   README-DOCKER.md
modified:   agent_server.py
modified:   Dockerfile
new file:   docker-compose.dev.yml
new file:   docker-compose.yml
new file:   install.sh
new file:   uninstall.sh
new file:   update.sh
new file:   INSTALLATION.md
new file:   sophia-web/client/Dockerfile
new file:   sophia-web/client/nginx.conf
new file:   sophia-web/server/Dockerfile
new file:   .dockerignore
```

## Summary

You now have a **complete, production-ready Docker deployment system** for Sophia AMS that:

1. **Installs automatically** on any Linux system with a single command
2. **Packages everything** in isolated, reproducible containers
3. **Persists data** across restarts and updates
4. **Scales easily** for production deployment
5. **Provides full shell access** for the agent in a safe Linux environment
6. **Updates safely** with automated scripts
7. **Uninstalls cleanly** with data preservation options

**Next step**: Push these changes to Git, then run `install.sh` on your Linux target machine! 🚀
