# Docker Networking for Sophia AMS

## Understanding Docker Container Networking

When running Sophia in Docker containers, network connectivity works differently than running directly on the host machine.

### The Key Concept: `localhost` vs `host.docker.internal`

**Problem:**
- Your LLM server runs on `localhost:1234` on the host machine
- Your SearXNG runs on `localhost:8088` on the host machine
- But from inside a Docker container, `localhost` refers to the **container itself**, not the host!

**Solution:**
- Docker provides a special hostname: `host.docker.internal`
- This hostname always points to the host machine
- On Linux, we add this with `extra_hosts: - "host.docker.internal:host-gateway"`

## Your Setup

On your Linux target machine, you have:
- **LLM Server**: Running on host at `localhost:1234`
- **SearXNG**: Running on host at `localhost:8088`
- **Sophia Docker Containers**: Need to access these services

## Configuration

### In `.env` file:

```env
# These are the REAL addresses on your host machine
LLM_API_BASE=http://localhost:1234/v1
SEARXNG_URL=http://localhost:8088

# These are what Docker containers will use
OPENAI_API_BASE=http://host.docker.internal:1234/v1
# (SEARXNG_URL also uses host.docker.internal in docker-compose.yml)
```

### How It Works:

1. **Your LLM server** listens on `0.0.0.0:1234` (or `127.0.0.1:1234`)
2. **Docker container** needs to reach it
3. **Docker translates** `host.docker.internal` → host machine's IP
4. **Connection succeeds**: Container reaches `host.docker.internal:1234` → Your LLM

## Network Topology

```
┌─────────────────────────────────────────────────────────────┐
│ Host Machine (Linux)                                        │
│                                                             │
│  ┌──────────────────┐        ┌──────────────────┐          │
│  │ LLM Server       │        │ SearXNG          │          │
│  │ localhost:1234   │        │ localhost:8088   │          │
│  └──────────────────┘        └──────────────────┘          │
│           ▲                           ▲                     │
│           │                           │                     │
│           │ host.docker.internal      │                     │
│           │                           │                     │
│  ┌────────┴───────────────────────────┴──────────────────┐ │
│  │ Docker Network (sophia-network)                       │ │
│  │                                                        │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │ │
│  │  │ sophia-agent │  │ sophia-server│  │ sophia-web  │ │ │
│  │  │   :5001      │  │   :3001      │  │   :3000     │ │ │
│  │  └──────────────┘  └──────────────┘  └─────────────┘ │ │
│  │         │                  │                 │        │ │
│  │         └──────────────────┴─────────────────┘        │ │
│  │                            │                           │ │
│  │                   ┌────────┴────────┐                  │ │
│  │                   │ qdrant:6333     │                  │ │
│  │                   └─────────────────┘                  │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         │                      │
         │                      │
    Port 3000              Exposed Ports
    (Web UI)               (3000, 3001, 5001, 6333)
```

## Docker Compose Configuration

In `docker-compose.yml`, the key configuration is:

```yaml
sophia-agent:
  environment:
    - OPENAI_API_BASE=${OPENAI_API_BASE:-http://host.docker.internal:1234/v1}
    - SEARXNG_URL=${SEARXNG_URL:-http://host.docker.internal:8088}

  # This makes host.docker.internal work on Linux
  extra_hosts:
    - "host.docker.internal:host-gateway"
```

The `extra_hosts` entry tells Docker to add `host.docker.internal` to the container's `/etc/hosts` file, pointing to the host's gateway IP.

## Verification

### From Host Machine:

Test that your services are accessible:

```bash
# Test LLM API
curl http://localhost:1234/v1/models

# Test SearXNG
curl http://localhost:8088/health
```

### From Inside Container:

Once deployed, verify the container can reach the host:

```bash
# Enter the agent container
docker exec -it sophia-agent bash

# Test connection to host LLM
curl http://host.docker.internal:1234/v1/models

# Test connection to host SearXNG
curl http://host.docker.internal:8088/health

# Check /etc/hosts
cat /etc/hosts | grep host.docker.internal
```

You should see something like:
```
172.17.0.1    host.docker.internal
```

## Troubleshooting

### Problem: Container can't reach host services

**Check 1: Is the service binding to the right interface?**

Many servers bind to `127.0.0.1` (localhost only) by default, which won't accept connections from Docker containers.

For LM Studio or similar, ensure it's listening on `0.0.0.0` (all interfaces):
```bash
# Check what your LLM is listening on
netstat -tlnp | grep 1234

# Should show:
# 0.0.0.0:1234  (good - accepts from anywhere)
# NOT 127.0.0.1:1234 (bad - only local connections)
```

**Check 2: Firewall blocking connections?**

```bash
# Temporarily disable firewall for testing
sudo ufw disable

# Or allow specific ports
sudo ufw allow 1234
sudo ufw allow 8088
```

**Check 3: Test from container**

```bash
# Get host gateway IP
docker network inspect sophia_sophia-network | grep Gateway

# Test direct IP connection
docker exec sophia-agent curl http://172.17.0.1:1234/v1/models
```

**Check 4: Use direct IP instead of host.docker.internal**

If `host.docker.internal` doesn't work, find your host's IP and use it directly:

```bash
# Get your host's IP
ip addr show docker0 | grep inet

# Update .env:
OPENAI_API_BASE=http://172.17.0.1:1234/v1
```

## Alternative: Network Mode Host

If you can't get container networking working, you can use host networking mode (Linux only):

```yaml
sophia-agent:
  network_mode: "host"
  environment:
    - OPENAI_API_BASE=http://localhost:1234/v1  # Now localhost works!
```

**Caveat:** This removes network isolation and may cause port conflicts.

## Summary

✅ **Your LLM and SearXNG run on `localhost` on the host**
✅ **Docker containers use `host.docker.internal` to reach them**
✅ **docker-compose.yml is already configured with `extra_hosts`**
✅ **.env.docker.example has the correct defaults**
✅ **Just run `./install.sh` and it should work!**

The install script will copy `.env.docker.example` to `.env`, which already has the correct `host.docker.internal` configuration for your setup.
