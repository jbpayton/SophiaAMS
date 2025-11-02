# Sophia AMS - Quick Installation Guide

## One-Command Installation on Linux

The fastest way to get Sophia AMS running on a fresh Linux server:

```bash
curl -fsSL https://raw.githubusercontent.com/your-org/SophiaAMS/main/install.sh | bash
```

That's it! The script will handle everything automatically.

## What You Need

### Linux Server Requirements
- **OS**: Ubuntu 20.04+, Debian 11+, CentOS 8+, or similar
- **RAM**: 4GB minimum (8GB recommended)
- **Disk**: 10GB free space
- **CPU**: 2+ cores recommended
- **Network**: Internet access

### LLM API (Choose One)
Sophia needs an OpenAI-compatible LLM API:

**Option 1: Local LM Studio** (Recommended for development)
- Install [LM Studio](https://lmstudio.ai/)
- Load a model (e.g., OpenHermes, Mistral, Llama)
- Start the local server (default: `http://localhost:1234/v1`)

**Option 2: OpenAI API**
- Get an API key from [OpenAI](https://platform.openai.com/)
- Cost: ~$0.002 per 1K tokens

**Option 3: Other Compatible APIs**
- Ollama, Text Generation WebUI, vLLM, LocalAI, etc.
- Must support OpenAI-compatible endpoints

## Installation Methods

### Method 1: Automated Script (Easiest)

**On your Linux server:**

```bash
# Download and run installation script
curl -fsSL https://raw.githubusercontent.com/your-org/SophiaAMS/main/install.sh | bash
```

The script will:
1. Check if Docker is installed (and install it if needed)
2. Ask permission before installing anything
3. Clone the Sophia AMS repository
4. Prompt you for configuration (LLM API URL, etc.)
5. Build and start all services
6. Verify everything is working

**Time required:** 5-10 minutes

### Method 2: Manual Installation

**If you prefer manual control:**

```bash
# 1. Install Docker (if not already installed)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 2. Install Docker Compose (if needed)
sudo apt-get install docker-compose-plugin

# 3. Clone repository
git clone https://github.com/your-org/SophiaAMS.git
cd SophiaAMS

# 4. Configure environment
cp .env.docker.example .env
nano .env  # Edit with your LLM API settings

# 5. Start services
docker-compose up -d

# 6. Check status
docker-compose ps
```

**Time required:** 10-15 minutes

### Method 3: Development Setup (Windows)

**On your Windows development machine:**

This repository includes everything needed, but **the Docker deployment is designed for Linux**. On Windows, you can:

1. Develop and test code changes
2. Push to Git
3. Deploy to Linux server using the installation script

**Or use WSL2 (Windows Subsystem for Linux):**

```bash
# In WSL2 Ubuntu terminal
cd /mnt/c/Users/YourName/SophiaAMS
./install.sh
```

## After Installation

### Access Sophia

Once installed, open your browser:

- **Web Interface**: `http://your-server-ip:3000`
- **API Documentation**: `http://your-server-ip:5001/docs`
- **Qdrant Dashboard**: `http://your-server-ip:6333/dashboard`

If on the same machine: use `http://localhost:3000`

### Basic Commands

```bash
# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Start services
docker-compose up -d

# Restart a service
docker-compose restart sophia-agent

# Check status
docker-compose ps
```

### Update Sophia

```bash
cd ~/SophiaAMS
./update.sh
```

### Uninstall

```bash
cd ~/SophiaAMS
./uninstall.sh
```

## Configuration

### Environment Variables

The `.env` file contains all configuration. Key settings:

```env
# LLM API Configuration
LLM_API_BASE=http://localhost:1234/v1      # Your LLM API endpoint
LLM_API_KEY=not-needed                      # API key (or placeholder)
LLM_MODEL=openai/gpt-oss-20b                # Model name

# For Docker (use host.docker.internal to reach host)
OPENAI_API_BASE=http://host.docker.internal:1234/v1

# Optional: Web Search
SEARXNG_URL=http://localhost:8088           # SearXNG instance

# Logging
LOG_LEVEL=INFO                              # DEBUG, INFO, WARNING, ERROR
```

### Common Configurations

**Using LM Studio on the same machine:**
```env
OPENAI_API_BASE=http://host.docker.internal:1234/v1
OPENAI_API_KEY=not-needed
```

**Using LM Studio on another machine:**
```env
OPENAI_API_BASE=http://192.168.1.100:1234/v1
OPENAI_API_KEY=not-needed
```

**Using OpenAI API:**
```env
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=sk-your-actual-api-key-here
LLM_API_BASE=https://api.openai.com/v1
LLM_API_KEY=sk-your-actual-api-key-here
```

**Using Ollama:**
```env
OPENAI_API_BASE=http://host.docker.internal:11434/v1
OPENAI_API_KEY=not-needed
```

## Troubleshooting

### Services won't start

```bash
# Check logs
docker-compose logs

# Check specific service
docker-compose logs sophia-agent

# Restart everything
docker-compose restart
```

### Cannot connect to LLM API

**Test from container:**
```bash
docker exec sophia-agent curl http://host.docker.internal:1234/v1/models
```

**If that fails, use the Docker bridge IP:**
```bash
# Find Docker bridge IP
ip addr show docker0 | grep inet

# Update .env with that IP (e.g., 172.17.0.1)
OPENAI_API_BASE=http://172.17.0.1:1234/v1
```

### Port conflicts

If port 3000, 3001, or 5001 is already in use:

Edit `docker-compose.yml` and change the port mappings:
```yaml
ports:
  - "8080:3000"  # Change 8080 to any free port
```

### Out of disk space

```bash
# Clean up Docker
docker system prune -a

# Check disk usage
docker system df
```

### Permission denied errors

```bash
# Add your user to docker group
sudo usermod -aG docker $USER

# Log out and back in for changes to take effect
```

## Getting Help

### Documentation
- **Full Docker Guide**: [README-DOCKER.md](README-DOCKER.md)
- **Main README**: [README.md](README.md)
- **API Documentation**: Visit `http://localhost:5001/docs` after installation

### Check Service Health

```bash
# All services
curl http://localhost:5001/health
curl http://localhost:3001/health
curl http://localhost:3000/health
curl http://localhost:6333/health

# Or check container status
docker-compose ps
```

### Logs

```bash
# Follow all logs
docker-compose logs -f

# Just the agent
docker-compose logs -f sophia-agent

# Last 100 lines
docker-compose logs --tail=100
```

## What's Next?

After installation, Sophia can:

- **Chat with you** via the web interface
- **Remember conversations** with episodic memory
- **Build knowledge** from web pages and documents
- **Execute Python code** for analysis and computation
- **Run shell commands** for system operations
- **Search the web** (if SearXNG is configured)
- **Set and work on personal goals** in autonomous mode

Try asking Sophia:
- "What can you do?"
- "Can you search the web for recent AI news?"
- "Tell me about yourself"
- "What are your capabilities?"

## Security Notes

- The `.env` file contains API keys - never commit it to version control
- By default, services bind to `0.0.0.0` (accessible from network)
- For production, use a reverse proxy with HTTPS
- Consider firewall rules to restrict access
- Keep Docker and base images updated

## Need More Details?

See [README-DOCKER.md](README-DOCKER.md) for:
- Production deployment with resource limits
- HTTPS setup with Nginx
- Backup procedures
- Advanced configuration
- Troubleshooting guide
- Security considerations

---

**Quick Reference Card:**

```bash
# Install
curl -fsSL https://[...]/install.sh | bash

# Access
http://localhost:3000

# Update
./update.sh

# Uninstall
./uninstall.sh

# Logs
docker-compose logs -f

# Restart
docker-compose restart
```

**Happy hacking with Sophia!** 🤖✨
