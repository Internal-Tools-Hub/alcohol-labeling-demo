#!/bin/bash

# Alcohol Label Verification App - Docker Setup Script
# This script sets up the application for both local development and production deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check Docker
    if ! command_exists docker; then
        print_error "Docker is not installed. Please install Docker first."
        print_status "Visit: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command_exists docker-compose && ! docker compose version >/dev/null 2>&1; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        print_status "Visit: https://docs.docker.com/compose/install/"
        exit 1
    fi
    
    print_success "All prerequisites are installed"
}

# Function to setup environment file
setup_environment() {
    print_status "Setting up environment configuration..."
    
    if [ ! -f .env ]; then
        if [ -f env.example ]; then
            cp env.example .env
            print_success "Created .env file from env.example"
            print_warning "Please edit .env file with your actual configuration values"
        else
            print_error "env.example file not found. Please create a .env file manually."
            exit 1
        fi
    else
        print_warning ".env file already exists. Skipping creation."
    fi
}

# Function to create necessary directories
create_directories() {
    print_status "Creating necessary directories..."
    
    mkdir -p credentials
    mkdir -p nginx/ssl
    mkdir -p nginx/webroot
    mkdir -p uploads
    
    print_success "Created necessary directories"
}

# Function to setup Google Cloud credentials
setup_gcp_credentials() {
    print_status "Setting up Google Cloud credentials..."
    
    if [ ! -f credentials/service-account-key.json ]; then
        print_warning "Google Cloud service account key not found."
        print_status "Please place your service account key file at: credentials/service-account-key.json"
        print_status "Or set GOOGLE_APPLICATION_CREDENTIALS environment variable to point to your key file."
    else
        print_success "Google Cloud service account key found"
    fi
}

# Function to start development environment
start_development() {
    print_status "Starting development environment..."
    
    # Use docker-compose or docker compose based on what's available
    if command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    $COMPOSE_CMD up -d postgres
    print_status "Waiting for database to be ready..."
    sleep 10
    
    $COMPOSE_CMD up -d app
    print_success "Development environment started"
    print_status "Application will be available at: http://localhost:8501"
    print_status "Database will be available at: localhost:5432"
}

# Function to start production environment
start_production() {
    print_status "Starting production environment..."
    
    # Use docker-compose or docker compose based on what's available
    if command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml up -d
    print_success "Production environment started"
    print_status "Application will be available at: http://localhost (or your domain if configured)"
}

# Function to setup SSL certificates
setup_ssl() {
    print_status "Setting up SSL certificates..."
    
    if [ -z "$DOMAIN_NAME" ]; then
        print_error "DOMAIN_NAME environment variable is required for SSL setup"
        print_status "Please set DOMAIN_NAME in your .env file"
        exit 1
    fi
    
    # Use docker-compose or docker compose based on what's available
    if command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    # Start nginx first
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml up -d nginx
    
    # Get SSL certificate
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml --profile ssl-setup run --rm certbot
    
    print_success "SSL certificates obtained"
    print_status "Restarting nginx with SSL configuration..."
    $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml restart nginx
}

# Function to show logs
show_logs() {
    local service=${1:-""}
    
    # Use docker-compose or docker compose based on what's available
    if command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    if [ -n "$service" ]; then
        $COMPOSE_CMD logs -f "$service"
    else
        $COMPOSE_CMD logs -f
    fi
}

# Function to stop services
stop_services() {
    print_status "Stopping services..."
    
    # Use docker-compose or docker compose based on what's available
    if command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    $COMPOSE_CMD down
    print_success "Services stopped"
}

# Function to clean up
cleanup() {
    print_status "Cleaning up Docker resources..."
    
    # Use docker-compose or docker compose based on what's available
    if command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    $COMPOSE_CMD down -v --remove-orphans
    docker system prune -f
    print_success "Cleanup completed"
}

# Function to show help
show_help() {
    echo "Alcohol Label Verification App - Docker Setup Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  dev         Start development environment"
    echo "  prod        Start production environment"
    echo "  ssl         Setup SSL certificates (production only)"
    echo "  logs        Show logs (optionally specify service name)"
    echo "  stop        Stop all services"
    echo "  cleanup     Stop services and clean up Docker resources"
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 dev                    # Start development environment"
    echo "  $0 prod                   # Start production environment"
    echo "  $0 ssl                    # Setup SSL certificates"
    echo "  $0 logs app               # Show application logs"
    echo "  $0 logs postgres          # Show database logs"
    echo "  $0 stop                   # Stop all services"
    echo "  $0 cleanup                # Clean up everything"
}

# Main script logic
main() {
    case "${1:-help}" in
        "dev")
            check_prerequisites
            setup_environment
            create_directories
            setup_gcp_credentials
            start_development
            ;;
        "prod")
            check_prerequisites
            setup_environment
            create_directories
            setup_gcp_credentials
            start_production
            ;;
        "ssl")
            setup_ssl
            ;;
        "logs")
            show_logs "$2"
            ;;
        "stop")
            stop_services
            ;;
        "cleanup")
            cleanup
            ;;
        "help"|*)
            show_help
            ;;
    esac
}

# Run main function with all arguments
main "$@"
