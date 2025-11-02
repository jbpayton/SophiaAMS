#!/bin/bash

###############################################################################
# Sophia AMS - Uninstall Script
###############################################################################
#
# This script removes a Sophia AMS installation:
# - Stops and removes all containers
# - Optionally removes data volumes
# - Optionally removes Docker images
# - Optionally removes installation directory
#
# Usage:
#   ./uninstall.sh [--keep-data] [--keep-images] [--keep-directory]
#
# Options:
#   --keep-data       Don't delete data volumes (conversations, knowledge)
#   --keep-images     Don't delete Docker images
#   --keep-directory  Don't delete installation directory
#   --all             Delete everything (no prompts)
#
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse command-line options
KEEP_DATA=false
KEEP_IMAGES=false
KEEP_DIRECTORY=false
DELETE_ALL=false

for arg in "$@"; do
    case $arg in
        --keep-data)
            KEEP_DATA=true
            shift
            ;;
        --keep-images)
            KEEP_IMAGES=true
            shift
            ;;
        --keep-directory)
            KEEP_DIRECTORY=true
            shift
            ;;
        --all)
            DELETE_ALL=true
            shift
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Usage: $0 [--keep-data] [--keep-images] [--keep-directory] [--all]"
            exit 1
            ;;
    esac
done

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

confirm() {
    local prompt="$1"
    local default="${2:-N}"

    if [ "$DELETE_ALL" = true ]; then
        return 0
    fi

    if [ "$default" = "Y" ]; then
        read -p "$prompt [Y/n]: " -n 1 -r
    else
        read -p "$prompt [y/N]: " -n 1 -r
    fi
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        return 0
    else
        return 1
    fi
}

###############################################################################
# Uninstall Steps
###############################################################################

check_installation() {
    print_header "Checking Installation"

    if [ ! -f "docker-compose.yml" ]; then
        print_error "No docker-compose.yml found"
        print_info "This doesn't appear to be a Sophia AMS installation"
        exit 1
    fi

    print_success "Found Sophia AMS installation"

    # Check Docker availability
    if ! command_exists docker; then
        print_error "Docker is not available"
        exit 1
    fi

    if ! command_exists docker-compose && ! docker compose version >/dev/null 2>&1; then
        print_error "Docker Compose is not available"
        exit 1
    fi
}

stop_services() {
    print_header "Stopping Services"

    print_info "Stopping all containers..."

    if command_exists docker-compose; then
        docker-compose down 2>/dev/null || true
    else
        docker compose down 2>/dev/null || true
    fi

    print_success "Services stopped"
}

remove_volumes() {
    if [ "$KEEP_DATA" = true ]; then
        print_info "Keeping data volumes (--keep-data specified)"
        return 0
    fi

    print_header "Data Volumes"

    echo -e "${YELLOW}WARNING: This will permanently delete all data!${NC}"
    echo "This includes:"
    echo "  • All conversations and episodic memory"
    echo "  • Knowledge graph and learned information"
    echo "  • Vector embeddings"
    echo "  • All logs"
    echo ""

    if confirm "Do you want to DELETE all data volumes?" "N"; then
        print_info "Removing data volumes..."

        if command_exists docker-compose; then
            docker-compose down -v 2>/dev/null || true
        else
            docker compose down -v 2>/dev/null || true
        fi

        # Also remove named volumes explicitly
        docker volume rm sophia_episodic_memory 2>/dev/null || true
        docker volume rm sophia_vector_data 2>/dev/null || true
        docker volume rm sophia_qdrant_storage 2>/dev/null || true
        docker volume rm sophia_agent_logs 2>/dev/null || true

        print_success "Data volumes removed"
    else
        print_info "Keeping data volumes"
        KEEP_DATA=true
    fi
}

remove_images() {
    if [ "$KEEP_IMAGES" = true ]; then
        print_info "Keeping Docker images (--keep-images specified)"
        return 0
    fi

    print_header "Docker Images"

    if confirm "Do you want to remove Sophia AMS Docker images?" "N"; then
        print_info "Removing images..."

        # Get project name (usually the directory name)
        local project_name=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]')

        # Remove images
        docker rmi ${project_name}-sophia-agent 2>/dev/null || true
        docker rmi ${project_name}-sophia-server 2>/dev/null || true
        docker rmi ${project_name}-sophia-web 2>/dev/null || true

        print_success "Images removed"
    else
        print_info "Keeping Docker images"
        KEEP_IMAGES=true
    fi
}

remove_directory() {
    if [ "$KEEP_DIRECTORY" = true ]; then
        print_info "Keeping installation directory (--keep-directory specified)"
        return 0
    fi

    print_header "Installation Directory"

    local current_dir=$(pwd)

    echo -e "${YELLOW}WARNING: This will delete the entire installation directory!${NC}"
    echo "Directory: $current_dir"
    echo ""

    if confirm "Do you want to DELETE the installation directory?" "N"; then
        print_info "Removing installation directory..."

        # Move up one level before deleting
        cd ..
        rm -rf "$current_dir"

        print_success "Installation directory removed"
        print_info "Uninstall complete. You are now in: $(pwd)"
        exit 0
    else
        print_info "Keeping installation directory"
        KEEP_DIRECTORY=true
    fi
}

show_cleanup_commands() {
    print_header "Additional Cleanup (Optional)"

    echo "If you want to free up more Docker resources, run:"
    echo ""
    echo "  # Remove all unused Docker images"
    echo "  docker image prune -a"
    echo ""
    echo "  # Remove all unused volumes"
    echo "  docker volume prune"
    echo ""
    echo "  # Remove all unused containers, networks, and images"
    echo "  docker system prune -a"
    echo ""
}

###############################################################################
# Main Uninstall Flow
###############################################################################

main() {
    echo -e "${RED}"
    cat << "EOF"
  ____             _     _          _    __  __ ____
 / ___|  ___  _ __| |__ (_) __ _   / \  |  \/  / ___|
 \___ \ / _ \| '_ \| '_ \| |/ _` | / _ \ | |\/| \___ \
  ___) | (_) | |_) | | | | | (_| |/ ___ \| |  | |___) |
 |____/ \___/| .__/|_| |_|_|\__,_/_/   \_\_|  |_|____/
             |_|
            Uninstall Script
EOF
    echo -e "${NC}"

    print_warning "This script will uninstall Sophia AMS"
    echo ""

    if [ "$DELETE_ALL" = true ]; then
        print_warning "Running in --all mode: Everything will be deleted!"
    fi

    echo ""
    read -p "Press Enter to continue or Ctrl+C to cancel..."

    # Run uninstall steps
    check_installation
    stop_services
    remove_volumes
    remove_images
    remove_directory

    # Final message
    print_header "Uninstall Summary"

    echo "Sophia AMS has been uninstalled with the following settings:"
    echo ""

    if [ "$KEEP_DATA" = true ]; then
        print_info "Data volumes: KEPT"
        echo "  To remove data later, run: docker volume prune"
    else
        print_success "Data volumes: REMOVED"
    fi

    if [ "$KEEP_IMAGES" = true ]; then
        print_info "Docker images: KEPT"
    else
        print_success "Docker images: REMOVED"
    fi

    if [ "$KEEP_DIRECTORY" = true ]; then
        print_info "Installation directory: KEPT"
        print_info "You can manually remove it with: rm -rf $(pwd)"
    else
        print_success "Installation directory: REMOVED"
    fi

    echo ""
    show_cleanup_commands

    print_success "Uninstall complete!"
}

###############################################################################
# Run Uninstall
###############################################################################

main "$@"
