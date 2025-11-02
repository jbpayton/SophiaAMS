#!/bin/bash

###############################################################################
# Sophia AMS - Update Script
###############################################################################
#
# This script updates an existing Sophia AMS installation:
# - Pulls latest code from Git
# - Rebuilds Docker images
# - Restarts services with minimal downtime
# - Preserves data volumes and configuration
#
# Usage:
#   ./update.sh
#
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
# Pre-Update Checks
###############################################################################

check_prerequisites() {
    print_header "Checking Prerequisites"

    # Check if we're in the right directory
    if [ ! -f "docker-compose.yml" ] || [ ! -f "agent_server.py" ]; then
        print_error "This doesn't appear to be a Sophia AMS installation directory"
        print_info "Please run this script from the SophiaAMS directory"
        exit 1
    fi

    print_success "Found Sophia AMS installation"

    # Check if Git is available
    if ! command_exists git; then
        print_error "Git is not installed"
        exit 1
    fi

    print_success "Git is available"

    # Check if Docker is available
    if ! command_exists docker; then
        print_error "Docker is not installed"
        exit 1
    fi

    if ! docker info >/dev/null 2>&1; then
        print_error "Docker is not running"
        exit 1
    fi

    print_success "Docker is running"

    # Check if Docker Compose is available
    if ! command_exists docker-compose && ! docker compose version >/dev/null 2>&1; then
        print_error "Docker Compose is not installed"
        exit 1
    fi

    print_success "Docker Compose is available"
}

###############################################################################
# Backup
###############################################################################

backup_env() {
    print_header "Backing Up Configuration"

    if [ -f ".env" ]; then
        cp .env .env.backup
        print_success "Backed up .env to .env.backup"
    else
        print_warning "No .env file found to backup"
    fi
}

###############################################################################
# Update Code
###############################################################################

update_code() {
    print_header "Updating Code"

    # Save current branch
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    print_info "Current branch: $current_branch"

    # Check for uncommitted changes
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        print_warning "You have uncommitted changes"
        git status --short
        echo ""
        read -p "Do you want to stash these changes and continue? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            git stash save "Auto-stash before update at $(date)"
            print_success "Changes stashed"
        else
            print_error "Please commit or stash your changes before updating"
            exit 1
        fi
    fi

    # Pull latest changes
    print_info "Pulling latest changes..."
    git pull origin "$current_branch"
    print_success "Code updated successfully"

    # Check if .env needs updating
    if [ -f ".env.backup" ] && [ -f "env_example" ]; then
        print_info "\nChecking for new environment variables..."

        # Show differences between old and new env template
        if [ -f ".env.docker.example" ]; then
            new_vars=$(comm -13 <(grep -E "^[A-Z_]+" .env | cut -d= -f1 | sort) <(grep -E "^[A-Z_]+" env_example | cut -d= -f1 | sort) || echo "")

            if [ -n "$new_vars" ]; then
                print_warning "New environment variables found:"
                echo "$new_vars"
                print_info "Review env_example and update your .env file if needed"
            else
                print_success "No new environment variables"
            fi
        fi
    fi
}

###############################################################################
# Rebuild and Restart
###############################################################################

rebuild_services() {
    print_header "Rebuilding Docker Images"

    print_info "Pulling latest base images..."
    if command_exists docker-compose; then
        docker-compose pull || true
    else
        docker compose pull || true
    fi

    print_info "Building Sophia AMS images..."
    if command_exists docker-compose; then
        docker-compose build --no-cache
    else
        docker compose build --no-cache
    fi

    print_success "Images rebuilt successfully"
}

restart_services() {
    print_header "Restarting Services"

    print_info "Stopping services..."
    if command_exists docker-compose; then
        docker-compose down
    else
        docker compose down
    fi

    print_success "Services stopped"

    print_info "Starting updated services..."
    if command_exists docker-compose; then
        docker-compose up -d
    else
        docker compose up -d
    fi

    print_success "Services started"
}

###############################################################################
# Verification
###############################################################################

wait_for_services() {
    print_header "Waiting for Services"

    print_info "Waiting for services to become healthy..."

    local max_attempts=60
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        attempt=$((attempt + 1))

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
        print_warning "Services are taking longer than expected"
    fi
}

verify_services() {
    print_header "Verifying Services"

    local all_good=true

    # Check each service
    services=("http://localhost:5001/health:Agent" "http://localhost:3001/health:Proxy" "http://localhost:3000/health:Web" "http://localhost:6333/health:Qdrant")

    for service in "${services[@]}"; do
        IFS=':' read -r url name <<< "$service"

        if curl -f "$url" >/dev/null 2>&1; then
            print_success "$name server is healthy"
        else
            print_warning "$name server not responding"
            all_good=false
        fi
    done

    if [ "$all_good" = false ]; then
        print_warning "\nSome services may still be initializing"
        print_info "Check logs with: docker-compose logs -f"
    fi
}

###############################################################################
# Cleanup
###############################################################################

cleanup_old_images() {
    print_header "Cleaning Up"

    print_info "Removing unused Docker images..."
    docker image prune -f >/dev/null 2>&1 || true
    print_success "Cleanup complete"
}

###############################################################################
# Main Update Flow
###############################################################################

main() {
    echo -e "${BLUE}"
    cat << "EOF"
  ____             _     _          _    __  __ ____
 |  _ \ ___  _ __ | |__ (_) __ _   / \  |  \/  / ___|
 | |_) / _ \| '_ \| '_ \| |/ _` | / _ \ | |\/| \___ \
 |  __/ (_) | |_) | | | | | (_| |/ ___ \| |  | |___) |
 |_|   \___/| .__/|_| |_|_|\__,_/_/   \_\_|  |_|____/
            |_|
             Update Script
EOF
    echo -e "${NC}"

    print_info "This script will update your Sophia AMS installation"
    echo ""
    read -p "Press Enter to continue or Ctrl+C to cancel..."

    # Run update steps
    check_prerequisites
    backup_env
    update_code
    rebuild_services
    restart_services
    wait_for_services
    verify_services
    cleanup_old_images

    # Success message
    print_header "Update Complete!"

    echo -e "${GREEN}"
    cat << EOF

Sophia AMS has been updated successfully! 🎉

Services are running at:
  • Web Interface: http://localhost:3000
  • API Server:    http://localhost:3001
  • Agent Server:  http://localhost:5001
  • Qdrant Dashboard: http://localhost:6333/dashboard

Check status:
  docker-compose ps

View logs:
  docker-compose logs -f

If you stashed changes, restore them with:
  git stash pop

Configuration backup saved to: .env.backup
EOF
    echo -e "${NC}"
}

###############################################################################
# Run Update
###############################################################################

main "$@"
