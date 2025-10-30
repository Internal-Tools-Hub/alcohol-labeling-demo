# Docker Setup for Alcohol Label Verification App

This document provides comprehensive instructions for running the Alcohol Label Verification App using Docker and Docker Compose, both locally and on a Linux VM.

## Quick Start

### Prerequisites

- Docker (version 20.10+)
- Docker Compose (version 2.0+)
- Google Cloud Platform account with:
  - Gemini API enabled
  - Cloud Storage bucket
  - Service account key (optional)

### 1. Clone and Setup

```bash
git clone <repository-url>
cd alcohol-labeling-demo
```

### 2. Configure Environment

```bash
# Copy environment template
cp env.example .env

# Edit with your actual values
nano .env
```

**Required Environment Variables:**
- `GEMINI_API_KEY`: Your Google Gemini API key
- `GCP_PROJECT_ID`: Your Google Cloud Project ID
- `GCS_BUCKET_NAME`: Your Google Cloud Storage bucket name
- `POSTGRES_PASSWORD`: Database password (change from default)

### 3. Start the Application

**For Development:**
```bash
./scripts/docker-setup.sh dev
```

**For Production:**
```bash
./scripts/docker-setup.sh prod
```

## Detailed Setup Instructions

### Local Development

1. **Start Development Environment:**
   ```bash
   ./scripts/docker-setup.sh dev
   ```

2. **Access the Application:**
   - Application: http://localhost:8501
   - Database: localhost:5432

3. **View Logs:**
   ```bash
   ./scripts/docker-setup.sh logs
   ./scripts/docker-setup.sh logs app
   ./scripts/docker-setup.sh logs postgres
   ```

4. **Stop Services:**
   ```bash
   ./scripts/docker-setup.sh stop
   ```

### Production Deployment (Linux VM)

1. **Prepare the VM:**
   ```bash
   # Update system
   sudo apt update && sudo apt upgrade -y
   
   # Install Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker $USER
   
   # Install Docker Compose
   sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   ```

2. **Deploy the Application:**
   ```bash
   # Clone repository
   git clone <repository-url>
   cd alcohol-labeling-demo
   
   # Configure environment
   cp env.example .env
   nano .env  # Edit with production values
   
   # Start production environment
   ./scripts/docker-setup.sh prod
   ```

3. **Setup SSL (Optional):**
   ```bash
   # Set domain name in .env file
   echo "DOMAIN_NAME=your-domain.com" >> .env
   echo "LETSENCRYPT_EMAIL=your-email@example.com" >> .env
   
   # Get SSL certificates
   ./scripts/docker-setup.sh ssl
   ```

4. **Setup SSL Certificate Renewal:**
   ```bash
   # Add to crontab for automatic renewal
   (crontab -l 2>/dev/null; echo "0 12 * * * cd /path/to/alcohol-labeling-demo && ./scripts/docker-setup.sh ssl") | crontab -
   ```

## Docker Compose Files

### Main Files

- `docker-compose.yml`: Base configuration with all services
- `docker-compose.override.yml`: Local development overrides (auto-loaded)
- `docker-compose.prod.yml`: Production-specific configuration

### Services

1. **app**: Streamlit application
   - Port: 8501 (development), internal only (production)
   - Health check: HTTP endpoint
   - Restart policy: unless-stopped

2. **postgres**: PostgreSQL database
   - Port: 5432 (development), internal only (production)
   - Health check: pg_isready
   - Data persistence: Docker volume

3. **nginx**: Reverse proxy (production only)
   - Ports: 80, 443
   - SSL termination
   - Rate limiting
   - Security headers

## Environment Configuration

### Required Variables

```env
# Database
POSTGRES_DB=alcohol_label_verification
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password

# Google Cloud
GEMINI_API_KEY=your_gemini_api_key
GCP_PROJECT_ID=your_project_id
GCS_BUCKET_NAME=your_bucket_name

# Application
DEFAULT_ROLE=admin
```

### Optional Variables

```env
# Production SSL
DOMAIN_NAME=your-domain.com
LETSENCRYPT_EMAIL=your-email@example.com

# Development
ENVIRONMENT=development
DEBUG=true
```

## Google Cloud Setup

### 1. Enable APIs

```bash
# Enable Gemini API
gcloud services enable generativelanguage.googleapis.com

# Enable Cloud Storage API
gcloud services enable storage.googleapis.com
```

### 2. Create Storage Bucket

```bash
# ----------------------------------------------------------------------------
# Configure variables (edit these to your values)
# ----------------------------------------------------------------------------
export PROJECT_ID="your-project-id"
export BUCKET_NAME="your-bucket-name"           # e.g., alcohol-labeling-demo
export SERVICE_ACCOUNT_NAME="alcohol-labeling-app"
export SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Create bucket
gsutil mb gs://$BUCKET_NAME

# SKIP, but FYI. Set permissions (optional - for public access)
gsutil iam ch allUsers:objectViewer gs://$BUCKET_NAME
```

### 3. Service Account (Optional)

```bash

# Set default project for gcloud (optional but recommended)
gcloud config set project "$PROJECT_ID"

# ----------------------------------------------------------------------------
# Create service account
# ----------------------------------------------------------------------------
gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
  --display-name="Alcohol Labeling App"

# ----------------------------------------------------------------------------
# Grant bucket-level permissions (Object Admin is sufficient; no list required)
# ----------------------------------------------------------------------------
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET_NAME" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/storage.objectAdmin"

# If you prefer project-level permissions instead (broader scope):
# gcloud projects add-iam-policy-binding "$PROJECT_ID" \
#   --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
#   --role="roles/storage.objectAdmin"

# ----------------------------------------------------------------------------
# Create and download key (store in mounted credentials/ path)
# ----------------------------------------------------------------------------
gcloud iam service-accounts keys create credentials/service-account-key.json \
  --iam-account="$SERVICE_ACCOUNT_EMAIL"
```

## Troubleshooting

### Common Issues

1. **Database Connection Error:**
   ```bash
   # Check if database is running
   docker-compose ps postgres
   
   # Check database logs
   docker-compose logs postgres
   
   # Restart database
   docker-compose restart postgres
   ```

2. **GCS Connection Error:**
   ```bash
   # Verify credentials
   docker-compose exec app python -c "from src.services.gcs_service import gcs_service; print(gcs_service.test_connection())"
   
   # Check environment variables
   docker-compose exec app env | grep GCP
   ```

3. **Gemini API Error:**
   ```bash
   # Test API connection
   docker-compose exec app python -c "from src.services.gemini_service import gemini_service; print(gemini_service.test_connection())"
   
   # Check API key
   docker-compose exec app env | grep GEMINI
   ```

4. **Port Already in Use:**
   ```bash
   # Check what's using the port
   sudo netstat -tulpn | grep :8501
   
   # Stop conflicting services
   sudo systemctl stop nginx  # if nginx is running
   ```

### Logs and Debugging

```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f app
docker-compose logs -f postgres
docker-compose logs -f nginx

# View logs with timestamps
docker-compose logs -f -t

# View last 100 lines
docker-compose logs --tail=100 app
```

### Performance Monitoring

```bash
# Check resource usage
docker stats

# Check container health
docker-compose ps

# Check disk usage
docker system df
```

## Security Considerations

### Production Security

1. **Change Default Passwords:**
   - Update `POSTGRES_PASSWORD` in `.env`
   - Use strong, unique passwords

2. **SSL/TLS:**
   - Always use HTTPS in production
   - Set up SSL certificates with Let's Encrypt
   - Configure security headers in nginx

3. **Network Security:**
   - Use Docker networks for service isolation
   - Don't expose database ports in production
   - Configure firewall rules

4. **Secrets Management:**
   - Use Docker secrets for sensitive data
   - Rotate API keys regularly
   - Don't commit `.env` files to version control

### Environment Isolation

```bash
# Development
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d

# Production
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Backup and Recovery

### Database Backup

```bash
# Create backup
docker-compose exec postgres pg_dump -U postgres alcohol_label_verification > backup.sql

# Restore backup
docker-compose exec -T postgres psql -U postgres alcohol_label_verification < backup.sql
```

### Volume Backup

```bash
# Backup volumes
docker run --rm -v alcohol-labeling-demo_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz -C /data .
```

## Scaling and Performance

### Resource Limits

The production configuration includes resource limits:
- App: 1GB RAM, 0.5 CPU
- PostgreSQL: 512MB RAM, 0.25 CPU
- Nginx: 128MB RAM, 0.1 CPU

### Horizontal Scaling

For high-traffic deployments, consider:
- Load balancer in front of multiple app instances
- Database read replicas
- Redis for session storage
- CDN for static assets

## Maintenance

### Regular Tasks

1. **Update Dependencies:**
   ```bash
   docker-compose pull
   docker-compose up -d
   ```

2. **Clean Up:**
   ```bash
   ./scripts/docker-setup.sh cleanup
   ```

3. **Monitor Logs:**
   ```bash
   ./scripts/docker-setup.sh logs
   ```

4. **SSL Certificate Renewal:**
   ```bash
   ./scripts/docker-setup.sh ssl
   ```

5. **Rebuild**
   ```
   docker compose build app && docker compose up -d app
   docker compose logs -f app
   ```
   
## Support

For issues and questions:
1. Check the logs: `./scripts/docker-setup.sh logs`
2. Verify configuration: Check `.env` file
3. Test connections: Use the built-in health checks
4. Review this documentation
5. Open an issue in the repository
