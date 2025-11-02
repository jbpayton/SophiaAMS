#!/bin/bash

###############################################################################
# Sophia AMS - Automated Installation Script for Linux
###############################################################################
#
# This script automates the complete installation of Sophia AMS:
# - Checks and installs system dependencies (Docker, Docker Compose, Git)
# - Clones the repository (or uses current directory if already cloned)
# - Sets up environment configuration
# - Builds and starts Docker containers
#
# Usage:
#   wget -O - https://raw.githubusercontent.com/jbpayton/SophiaAMS/main/install.sh | bash
#
#   OR
#
#   curl -fsSL https://raw.githubusercontent.com/jbpayton/SophiaAMS/main/install.sh | bash
#
#   OR (manual):
#
#   chmod +x install.sh
#   ./install.sh
#
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO_URL="${REPO_URL:-https://github.com/jbpayton/SophiaAMS.git}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/SophiaAMS}"
BRANCH="${BRANCH:-main}"

###############################################################################
# Helper Functions
###############################################################################

print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

###############################################################################
# Dependency Checks and Installation
###############################################################################

check_dependencies() {
    print_header "Checking System Dependencies"

    local missing_deps=()

    # Check for essential commands
    if ! command_exists curl; then
        missing_deps+=("curl")
    else
        print_success "curl is installed"
    fi

    if ! command_exists git; then
        missing_deps+=("git")
    else
        print_success "git is installed"
    fi

    # Check Docker
    if ! command_exists docker; then
        print_warning "Docker is not installed"
        missing_deps+=("docker")
    else
        print_success "Docker is installed ($(docker --version))"

        # Check if Docker daemon is running
        if ! docker info >/dev/null 2>&1; then
            print_error "Docker is installed but not running"
            print_info "Please start Docker and run this script again"
            exit 1
        fi
    fi

    # Check Docker Compose
    if ! command_exists docker-compose && ! docker compose version >/dev/null 2>&1; then
        print_warning "Docker Compose is not installed"
        missing_deps+=("docker-compose")
    else
        print_success "Docker Compose is installed"
    fi

    return ${#missing_deps[@]}
}

install_docker() {
    print_header "Installing Docker"

    # Detect OS
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        VERSION=$VERSION_ID
    else
        print_error "Cannot detect operating system"
        exit 1
    fi

    print_info "Detected OS: $OS $VERSION"

    case "$OS" in
        ubuntu|debian)
            print_info "Installing Docker on Ubuntu/Debian..."
            sudo apt-get update
            sudo apt-get install -y ca-certificates curl gnupg lsb-release

            # Add Docker's official GPG key
            sudo install -m 0755 -d /etc/apt/keyrings
            curl -fsSL https://download.docker.com/linux/$OS/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
            sudo chmod a+r /etc/apt/keyrings/docker.gpg

            # Set up the repository
            echo \
              "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$OS \
              $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

            # Install Docker
            sudo apt-get update
            sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

            # Add current user to docker group
            sudo usermod -aG docker $USER

            print_success "Docker installed successfully"
            print_warning "You may need to log out and back in for group membership to take effect"
            ;;

        centos|rhel|fedora)
            print_info "Installing Docker on CentOS/RHEL/Fedora..."
            sudo yum install -y yum-utils
            sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
            sudo yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            sudo systemctl start docker
            sudo systemctl enable docker
            sudo usermod -aG docker $USER
            print_success "Docker installed successfully"
            ;;

        *)
            print_error "Unsupported operating system: $OS"
            print_info "Please install Docker manually: https://docs.docker.com/engine/install/"
            exit 1
            ;;
    esac
}

install_dependencies() {
    print_header "Installing Missing Dependencies"

    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
    fi

    case "$OS" in
        ubuntu|debian)
            sudo apt-get update
            sudo apt-get install -y curl git
            install_docker
            ;;
        centos|rhel|fedora)
            sudo yum install -y curl git
            install_docker
            ;;
        *)
            print_error "Cannot automatically install dependencies for $OS"
            print_info "Please install: docker, docker-compose, git, curl"
            exit 1
            ;;
    esac
}

###############################################################################
# Repository Setup
###############################################################################

setup_repository() {
    print_header "Setting Up Repository"

    # Check if we're already in the SophiaAMS directory
    if [ -f "docker-compose.yml" ] && [ -f "agent_server.py" ]; then
        print_info "Already in SophiaAMS directory, using current location"
        INSTALL_DIR=$(pwd)
        print_success "Using directory: $INSTALL_DIR"
        return 0
    fi

    # Clone repository
    if [ -d "$INSTALL_DIR" ]; then
        print_warning "Directory $INSTALL_DIR already exists"
        read -p "Do you want to remove it and clone fresh? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$INSTALL_DIR"
        else
            print_info "Using existing directory"
            cd "$INSTALL_DIR"
            git pull origin "$BRANCH" || true
            return 0
        fi
    fi

    print_info "Cloning repository from $REPO_URL..."
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    print_success "Repository cloned successfully"
}

###############################################################################
# Environment Configuration
###############################################################################

configure_environment() {
    print_header "Configuring Environment"

    if [ -f ".env" ]; then
        print_warning ".env file already exists"
        read -p "Do you want to overwrite it? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Keeping existing .env file"
            return 0
        fi
    fi

    # Use env_example as the template
    if [ -f "env_example" ]; then
        print_info "Using env_example as template..."
        cp env_example .env
    elif [ -f ".env.docker.example" ]; then
        print_info "Using .env.docker.example as template..."
        cp .env.docker.example .env
    else
        print_error "No environment template found!"
        exit 1
    fi

    print_success "Created .env file"

    # Prompt for key configuration values
    print_info "\nLet's configure your environment:"

    # LLM API Configuration
    echo -e "\n${YELLOW}LLM API Configuration:${NC}"
    read -p "LLM API Base URL [http://localhost:1234/v1]: " llm_api_base
    llm_api_base=${llm_api_base:-http://localhost:1234/v1}

    read -p "LLM API Key [not-needed]: " llm_api_key
    llm_api_key=${llm_api_key:-not-needed}

    read -p "LLM Model [openai/gpt-oss-20b]: " llm_model
    llm_model=${llm_model:-openai/gpt-oss-20b}

    # SearXNG Configuration
    echo -e "\n${YELLOW}Search Configuration:${NC}"
    read -p "SearXNG URL [http://localhost:8088]: " searxng_url
    searxng_url=${searxng_url:-http://localhost:8088}

    # Update .env file with user inputs
    sed -i "s|LLM_API_BASE=.*|LLM_API_BASE=$llm_api_base|g" .env
    sed -i "s|LLM_API_KEY=.*|LLM_API_KEY=$llm_api_key|g" .env
    sed -i "s|LLM_MODEL=.*|LLM_MODEL=$llm_model|g" .env
    sed -i "s|SEARXNG_URL=.*|SEARXNG_URL=$searxng_url|g" .env

    # For Docker Compose, we need to set OPENAI_API_BASE as well
    if ! grep -q "OPENAI_API_BASE" .env; then
        echo "OPENAI_API_BASE=$llm_api_base" >> .env
    else
        sed -i "s|OPENAI_API_BASE=.*|OPENAI_API_BASE=$llm_api_base|g" .env
    fi

    if ! grep -q "OPENAI_API_KEY" .env; then
        echo "OPENAI_API_KEY=$llm_api_key" >> .env
    else
        sed -i "s|OPENAI_API_KEY=.*|OPENAI_API_KEY=$llm_api_key|g" .env
    fi

    print_success "Environment configured"
    print_info "You can edit .env later to adjust settings"
}

###############################################################################
# Docker Setup and Deployment
###############################################################################

build_and_deploy() {
    print_header "Building and Deploying Sophia AMS"

    print_info "Pulling base images..."
    docker-compose pull || docker compose pull || true

    print_info "Building Sophia AMS containers (this may take several minutes)..."
    if command_exists docker-compose; then
        docker-compose build
    else
        docker compose build
    fi

    print_success "Build completed"

    print_info "Starting services..."
    if command_exists docker-compose; then
        docker-compose up -d
    else
        docker compose up -d
    fi

    print_success "Services started"
}

wait_for_services() {
    print_header "Waiting for Services to Start"

    print_info "This may take 1-2 minutes as services initialize..."

    local max_attempts=60
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        attempt=$((attempt + 1))

        # Check if all services are healthy
        if command_exists docker-compose; then
            status=$(docker-compose ps --format json 2>/dev/null || echo "[]")
        else
            status=$(docker compose ps --format json 2>/dev/null || echo "[]")
        fi

        # Simple check: are containers running?
        local running_count=0
        if command_exists docker-compose; then
            running_count=$(docker-compose ps | grep -c "Up" || echo "0")
        else
            running_count=$(docker compose ps | grep -c "Up" || echo "0")
        fi

        if [ "$running_count" -ge 4 ]; then
            print_success "All services are running"
            break
        fi

        echo -n "."
        sleep 2
    done

    echo ""

    if [ $attempt -eq $max_attempts ]; then
        print_warning "Services are taking longer than expected to start"
        print_info "Check status with: docker-compose ps"
        print_info "Check logs with: docker-compose logs"
    fi
}

verify_installation() {
    print_header "Verifying Installation"

    local all_good=true

    # Check agent health
    print_info "Checking agent server..."
    if curl -f http://localhost:5001/health >/dev/null 2>&1; then
        print_success "Agent server is healthy"
    else
        print_warning "Agent server not responding yet (may need more time)"
        all_good=false
    fi

    # Check proxy server
    print_info "Checking proxy server..."
    if curl -f http://localhost:3001/health >/dev/null 2>&1; then
        print_success "Proxy server is healthy"
    else
        print_warning "Proxy server not responding yet"
        all_good=false
    fi

    # Check web frontend
    print_info "Checking web frontend..."
    if curl -f http://localhost:3000/health >/dev/null 2>&1; then
        print_success "Web frontend is healthy"
    else
        print_warning "Web frontend not responding yet"
        all_good=false
    fi

    # Check Qdrant
    print_info "Checking Qdrant database..."
    if curl -f http://localhost:6333/health >/dev/null 2>&1; then
        print_success "Qdrant database is healthy"
    else
        print_warning "Qdrant database not responding yet"
        all_good=false
    fi

    if [ "$all_good" = false ]; then
        print_warning "\nSome services are not ready yet. They may still be initializing."
        print_info "Wait a minute and check again with: curl http://localhost:5001/health"
    fi
}

###############################################################################
# Main Installation Flow
###############################################################################

main() {
    clear
    echo -e "${BLUE}"
    cat << "EOF"
  ____             _     _          _    __  __ ____
 / ___|  ___  _ __| |__ (_) __ _   / \  |  \/  / ___|
 \___ \ / _ \| '__| '_ \| |/ _` | / _ \ | |\/| \___ \
  ___) | (_) | |  | | | | | (_| |/ ___ \| |  | |___) |
 |____/ \___/|_|  |_| |_|_|\__,_/_/   \_\_|  |_|____/

        Automated Installation Script for Linux
EOF
    echo -e "${NC}"

    print_info "This script will install Sophia AMS and all dependencies"
    print_info "Installation directory: $INSTALL_DIR"
    echo ""
    read -p "Press Enter to continue or Ctrl+C to cancel..."

    # Step 1: Check and install dependencies
    if ! check_dependencies; then
        print_warning "Some dependencies are missing"
        read -p "Do you want to install them automatically? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            install_dependencies
        else
            print_error "Cannot proceed without dependencies"
            exit 1
        fi
    fi

    # Step 2: Setup repository
    setup_repository
    cd "$INSTALL_DIR"

    # Step 3: Configure environment
    configure_environment

    # Step 4: Build and deploy
    build_and_deploy

    # Step 5: Wait for services
    wait_for_services

    # Step 6: Verify installation
    verify_installation

    # Final success message
    print_header "Installation Complete!"

    echo -e "${GREEN}"
    cat << EOF

Sophia AMS is now running! 🎉

Access the application:
  • Web Interface: http://localhost:3000
  • API Server:    http://localhost:3001
  • Agent Server:  http://localhost:5001
  • Qdrant Dashboard: http://localhost:6333/dashboard

Useful commands:
  • View logs:     docker-compose logs -f
  • Stop services: docker-compose down
  • Start services: docker-compose up -d
  • Restart:       docker-compose restart
  • Update:        ./update.sh

Configuration:
  • Edit .env to change settings
  • Restart services after changing .env

Installation directory: $INSTALL_DIR

For more information, see README-DOCKER.md
EOF
    echo -e "${NC}"
}

###############################################################################
# Run Installation
###############################################################################

main "$@"
