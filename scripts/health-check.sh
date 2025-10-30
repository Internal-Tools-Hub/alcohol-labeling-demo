#!/bin/bash

# Health Check Script for Alcohol Label Verification App
# This script checks the health of all services

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

# Function to check Docker service
check_docker_service() {
    local service_name=$1
    local port=$2
    local endpoint=${3:-"/"}
    
    print_status "Checking $service_name service..."
    
    if command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    # Check if container is running
    if ! $COMPOSE_CMD ps | grep -q "$service_name.*Up"; then
        print_error "$service_name container is not running"
        return 1
    fi
    
    # Check if port is accessible
    if [ -n "$port" ]; then
        if ! $COMPOSE_CMD exec $service_name nc -z localhost $port 2>/dev/null; then
            print_error "$service_name is not responding on port $port"
            return 1
        fi
    fi
    
    # Check health endpoint if provided
    if [ -n "$endpoint" ] && [ "$endpoint" != "/" ]; then
        if ! $COMPOSE_CMD exec $service_name curl -f "http://localhost$endpoint" >/dev/null 2>&1; then
            print_error "$service_name health endpoint is not responding"
            return 1
        fi
    fi
    
    print_success "$service_name is healthy"
    return 0
}

# Function to check database connectivity
check_database() {
    print_status "Checking database connectivity..."
    
    if command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    # Test database connection
    if $COMPOSE_CMD exec postgres psql -U postgres -d alcohol_label_verification -c "SELECT 1;" >/dev/null 2>&1; then
        print_success "Database connection is healthy"
        return 0
    else
        print_error "Database connection failed"
        return 1
    fi
}

# Function to check application health
check_application() {
    print_status "Checking application health..."
    
    if command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    # Test application health endpoint
    if $COMPOSE_CMD exec app curl -f "http://localhost:8501/_stcore/health" >/dev/null 2>&1; then
        print_success "Application is healthy"
        return 0
    else
        print_error "Application health check failed"
        return 1
    fi
}

# Function to check external services
check_external_services() {
    print_status "Checking external services..."
    
    if command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    # Test GCS connection
    if $COMPOSE_CMD exec app python -c "from src.services.gcs_service import gcs_service; print('GCS:', gcs_service.test_connection())" 2>/dev/null | grep -q "True"; then
        print_success "Google Cloud Storage connection is healthy"
    else
        print_warning "Google Cloud Storage connection failed"
    fi
    
    # Test Gemini API connection
    if $COMPOSE_CMD exec app python -c "from src.services.gemini_service import gemini_service; print('Gemini:', gemini_service.test_connection())" 2>/dev/null | grep -q "True"; then
        print_success "Gemini API connection is healthy"
    else
        print_warning "Gemini API connection failed"
    fi
}

# Function to show service status
show_status() {
    print_status "Service Status:"
    
    if command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    $COMPOSE_CMD ps
}

# Function to show resource usage
show_resources() {
    print_status "Resource Usage:"
    docker stats --no-stream
}

# Function to show logs
show_logs() {
    local service=${1:-""}
    local lines=${2:-50}
    
    print_status "Recent logs (last $lines lines):"
    
    if command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    if [ -n "$service" ]; then
        $COMPOSE_CMD logs --tail=$lines $service
    else
        $COMPOSE_CMD logs --tail=$lines
    fi
}

# Function to run full health check
run_health_check() {
    print_status "Running comprehensive health check..."
    echo ""
    
    local exit_code=0
    
    # Check Docker services
    check_docker_service "postgres" "5432" || exit_code=1
    check_docker_service "app" "8501" "/_stcore/health" || exit_code=1
    
    echo ""
    
    # Check database connectivity
    check_database || exit_code=1
    
    echo ""
    
    # Check application health
    check_application || exit_code=1
    
    echo ""
    
    # Check external services
    check_external_services
    
    echo ""
    
    # Show status
    show_status
    
    echo ""
    
    if [ $exit_code -eq 0 ]; then
        print_success "All health checks passed!"
    else
        print_error "Some health checks failed!"
    fi
    
    return $exit_code
}

# Function to show help
show_help() {
    echo "Alcohol Label Verification App - Health Check Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  check       Run comprehensive health check (default)"
    echo "  status      Show service status"
    echo "  resources   Show resource usage"
    echo "  logs        Show recent logs (optionally specify service and lines)"
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 check                    # Run full health check"
    echo "  $0 status                   # Show service status"
    echo "  $0 logs app 100             # Show last 100 lines of app logs"
    echo "  $0 logs postgres 50         # Show last 50 lines of postgres logs"
}

# Main script logic
main() {
    case "${1:-check}" in
        "check")
            run_health_check
            ;;
        "status")
            show_status
            ;;
        "resources")
            show_resources
            ;;
        "logs")
            show_logs "$2" "$3"
            ;;
        "help"|*)
            show_help
            ;;
    esac
}

# Run main function with all arguments
main "$@"
