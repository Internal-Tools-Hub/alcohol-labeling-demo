# Alcohol Label Verification App - Makefile
# Provides convenient commands for Docker management

.PHONY: help dev prod stop logs clean ssl setup migrate makemigrations superuser manage tailwind-init tailwind-install tailwind-dev seed-all seed-beer seed-wine seed-liquor seed-one

# Default target
help:
	@echo "Alcohol Label Verification App - Docker Commands"
	@echo ""
	@echo "Available commands:"
	@echo "  make dev      Start development environment"
	@echo "  make prod     Start production environment"
	@echo "  make stop     Stop all services"
	@echo "  make logs     Show logs (use LOGS=service for specific service)"
	@echo "  make clean    Stop and clean up all resources"
	@echo "  make ssl      Setup SSL certificates (production only)"
	@echo "  make setup    Initial setup and configuration"
	@echo "  make migrate  Run Django migrations"
	@echo "  make makemigrations Create Django migrations"
	@echo "  make superuser Create Django superuser"
	@echo "  make manage CMD='shell' Run arbitrary manage.py command"
	@echo "  make tailwind-init     Initialize django-tailwind theme app"
	@echo "  make tailwind-install  Install Tailwind NPM deps in the theme"
	@echo "  make tailwind-dev      Run Tailwind dev (hot reload)"
	@echo "  make seed-all          Seed all categories (beer, wine, liquor)"
	@echo "  make seed-beer         Seed beer category only"
	@echo "  make seed-wine         Seed wine category only"
	@echo "  make seed-liquor       Seed liquor category only"
	@echo "  make seed-one ID=beer_pass_001  Seed a single item by ID"
	@echo "  make help     Show this help message"
	@echo ""
	@echo "Examples:"
	@echo "  make dev"
	@echo "  make logs LOGS=app"
	@echo "  make clean"

# Check if Docker and Docker Compose are available
check-docker:
	@command -v docker >/dev/null 2>&1 || { echo "Docker is required but not installed. Aborting." >&2; exit 1; }
	@command -v docker-compose >/dev/null 2>&1 || docker compose version >/dev/null 2>&1 || { echo "Docker Compose is required but not installed. Aborting." >&2; exit 1; }

# Get Docker Compose command
DOCKER_COMPOSE := $(shell command -v docker-compose >/dev/null 2>&1 && echo "docker-compose" || echo "docker compose")

# Initial setup
setup: check-docker
	@echo "Setting up Alcohol Label Verification App..."
	@if [ ! -f .env ]; then \
		if [ -f env.example ]; then \
			cp env.example .env; \
			echo "Created .env file from env.example"; \
			echo "Please edit .env file with your configuration"; \
		else \
			echo "Error: env.example file not found"; \
			exit 1; \
		fi; \
	else \
		echo ".env file already exists"; \
	fi
	@mkdir -p credentials nginx/ssl nginx/webroot uploads
	@echo "Setup complete! Please edit .env file and run 'make dev' or 'make prod'"

# Development environment
dev: check-docker
	@echo "Starting development environment..."
	@$(DOCKER_COMPOSE) up -d postgres
	@echo "Waiting for database to be ready..."
	@sleep 10
	@$(DOCKER_COMPOSE) up -d app
	@echo "Development environment started!"
	@echo "Application: http://localhost:8000"
	@echo "Database: localhost:5432"

# Django management helpers
migrate: check-docker
	@$(DOCKER_COMPOSE) exec app python backend/manage.py migrate

makemigrations: check-docker
	@$(DOCKER_COMPOSE) exec app python backend/manage.py makemigrations

superuser: check-docker
	@$(DOCKER_COMPOSE) exec app python backend/manage.py createsuperuser

manage: check-docker
	@if [ -z "$(CMD)" ]; then \
		echo "Usage: make manage CMD='shell'"; \
		exit 1; \
	fi
	@$(DOCKER_COMPOSE) exec app python backend/manage.py $(CMD)

tailwind-init: check-docker
	@$(DOCKER_COMPOSE) exec app python backend/manage.py tailwind init

tailwind-install: check-docker
	@$(DOCKER_COMPOSE) exec app python backend/manage.py tailwind install

tailwind-dev: check-docker
	@$(DOCKER_COMPOSE) exec app python backend/manage.py tailwind dev

# Production environment
prod: check-docker
	@echo "Starting production environment..."
	@$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml up -d
	@echo "Production environment started!"
	@echo "Application: http://localhost (or your domain if configured)"

# Stop services
stop: check-docker
	@echo "Stopping services..."
	@$(DOCKER_COMPOSE) down
	@echo "Services stopped"

# Show logs
logs: check-docker
	@if [ -n "$(LOGS)" ]; then \
		$(DOCKER_COMPOSE) logs -f $(LOGS); \
	else \
		$(DOCKER_COMPOSE) logs -f; \
	fi

# Setup SSL certificates
ssl: check-docker
	@echo "Setting up SSL certificates..."
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found"; \
		exit 1; \
	fi
	@DOMAIN_NAME=$$(grep -E '^DOMAIN_NAME=' .env | cut -d '=' -f2- | xargs); \
	if [ -z "$$DOMAIN_NAME" ]; then \
		echo "Error: DOMAIN_NAME not found in .env file"; \
		echo "Please set DOMAIN_NAME=your-domain.com in your .env file"; \
		exit 1; \
	fi; \
	echo "Using domain: $$DOMAIN_NAME"
	@$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml up -d nginx
	@$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml --profile ssl-setup run --rm certbot
	@echo "SSL certificates obtained"
	@$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml restart nginx
	@echo "SSL setup complete!"

# Clean up
clean: check-docker
	@echo "Cleaning up Docker resources..."
	@$(DOCKER_COMPOSE) down -v --remove-orphans
	@docker system prune -f
	@echo "Cleanup complete"

# Show status
status: check-docker
	@echo "Service Status:"
	@$(DOCKER_COMPOSE) ps

# Show resource usage
stats: check-docker
	@echo "Resource Usage:"
	@docker stats --no-stream

# Restart services
restart: check-docker
	@echo "Restarting services..."
	@$(DOCKER_COMPOSE) restart
	@echo "Services restarted"

# Update and restart
update: check-docker
	@echo "Updating services..."
	@$(DOCKER_COMPOSE) pull
	@$(DOCKER_COMPOSE) up -d
	@echo "Services updated and restarted"

# Database backup
backup: check-docker
	@echo "Creating database backup..."
	@$(DOCKER_COMPOSE) exec postgres pg_dump -U postgres alcohol_label_verification > backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "Database backup created"

# Database restore
restore: check-docker
	@if [ -z "$(FILE)" ]; then \
		echo "Error: FILE variable is required for restore"; \
		echo "Usage: make restore FILE=backup_file.sql"; \
		exit 1; \
	fi
	@echo "Restoring database from $(FILE)..."
	@$(DOCKER_COMPOSE) exec -T postgres psql -U postgres alcohol_label_verification < $(FILE)
	@echo "Database restored"

# Data seeding
seed-all: check-docker
	@$(DOCKER_COMPOSE) exec app python data/sample/seed.py --all

seed-beer: check-docker
	@$(DOCKER_COMPOSE) exec app python data/sample/seed.py --beer

seed-wine: check-docker
	@$(DOCKER_COMPOSE) exec app python data/sample/seed.py --wine

seed-liquor: check-docker
	@$(DOCKER_COMPOSE) exec app python data/sample/seed.py --liquor

seed-one: check-docker
	@if [ -z "$(ID)" ]; then \
		echo "Usage: make seed-one ID=beer_pass_004"; \
		exit 1; \
	fi
	@$(DOCKER_COMPOSE) exec app python data/sample/seed.py --all --only-id $(ID)
