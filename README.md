# Alcohol Label Verification App

A Django-based web application that simulates the TTB (Alcohol and Tobacco Tax and Trade Bureau) label approval process. The app uses Google Gemini Vision API to extract text from alcohol label images and compares it against user-submitted form data.

## Features

- **Label Verification**: Upload alcohol label images and verify against form data
- **AI-Powered Text Extraction**: Uses Google Gemini Vision API for accurate text extraction
- **Fuzzy Matching**: Intelligent comparison with tolerance for minor OCR errors
- **Role-Based Access**: Django auth with login/logout and admin
- **Submission History**: Views for submissions, companies, and locations
- **Real-time Results**: Immediate verification results with detailed field-by-field comparison

## Architecture

- **Backend**: Django 5 (Python 3) with class-based views and templates
- **Frontend**: Django templates (Tailwind optional via `django-tailwind`)
- **Database**: PostgreSQL 15+
- **Storage**: Google Cloud Storage (for uploaded images)
- **AI/OCR**: Google Gemini Vision API
- **Deployment**: Docker Compose (dev/prod) and Nginx SSL termination

## Prerequisites

### Option 1: Docker (Recommended)
- Docker (version 20.10+)
- Docker Compose (version 2.0+)
- Google Cloud Platform account with:
  - Gemini API enabled
  - Cloud Storage bucket

### Option 2: Manual Installation
- Python 3.10+
- PostgreSQL 15+
- Google Cloud Platform account with:
  - Gemini API enabled
  - Cloud Storage bucket
- Google Cloud credentials (service account key)

## Quick Start with Docker

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd alcohol-labeling-demo
   ```

2. **Setup and start the application**
   ```bash
   # Initial setup
   make setup
   
   # Edit .env file with your configuration
   nano .env
   
   # Start development environment
   make dev
   ```

3. **Access the application**
   - Application: http://localhost:8000
   - Admin: http://localhost:8000/admin
   - Database: localhost:5432

For detailed Docker setup instructions, see [Docker Deployment Guide](docs/deployment/DOCKER_README.md).

## Manual Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd alcohol-labeling-demo
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   cp env.example .env
   ```
   
   Edit `.env` with your configuration:
   ```env
   # Database
   DATABASE_URL=postgresql://username:password@localhost:5432/alcohol_label_verification
   
   # Google AI & GCP
   GEMINI_API_KEY=your_gemini_api_key_here
   GCP_PROJECT_ID=your_gcp_project_id_here
   GCS_BUCKET_NAME=your_gcs_bucket_name_here
   
   # Django
   DJANGO_SECRET_KEY=change_me
   ALLOWED_HOSTS=localhost,127.0.0.1
   ```

4. **Set up Google Cloud credentials**
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="path/to/your/service-account-key.json"
   ```

5. **Initialize the database (Django)**
   ```bash
   # Create database (if not already created)
   createdb alcohol_label_verification
   
   # Run migrations
   python backend/manage.py migrate
   
   # Create a superuser (optional)
   python backend/manage.py createsuperuser
   ```

6. **Run the application**
   ```bash
   python backend/manage.py runserver 0.0.0.0:8000
   ```

## Usage

### App Navigation
- **Home**: `/`
- **Submissions**:
  - List: `/submissions/`
  - Create: `/submissions/create/`
  - Detail: `/submissions/<id>/`
- **Companies** and **Locations**: CRUD views available under `/companies/` and nested `/locations/`
- **Admin**: `/admin` (after creating a superuser)

### Submitter Flow
1. Go to `/submissions/create/` and fill out the product information form:
   - Brand Name
   - Product Type/Class
   - Alcohol Content (%)
   - Net Contents (optional)
2. Upload clear label images (front/back)
3. Submit to run verification
4. View detailed, field-by-field comparison

## API Configuration

### Google Gemini API
1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Create a new API key
3. Add the key to your `.env` file (`GEMINI_API_KEY`)

### Google Cloud Storage
1. Create a GCS bucket in your Google Cloud project
2. Set appropriate permissions for your service account
3. Update the bucket name in your `.env` file (`GCS_BUCKET_NAME`)

## Database Schema

Core models are defined in `backend/core/models.py` and migrations in `backend/core/migrations/`.

## Deployment

### Docker (Production)

Use the production compose file with Nginx SSL termination:

```bash
make prod
```

Application will be available at `http://localhost` (or your domain if configured). See `docker-compose.prod.yml` and `nginx/nginx.conf`.

### Linux VM Deployment (Without Docker)

1. **Prepare the server**
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install python3 python3-pip postgresql postgresql-contrib nginx
   ```

2. **Set up PostgreSQL**
   ```bash
   sudo -u postgres createdb alcohol_label_verification
   ```

3. **Deploy application**
   ```bash
   git clone <repository-url>
   cd alcohol-labeling-demo
   pip3 install -r requirements.txt
   cp env.example .env
   # Edit .env with production values
   python backend/manage.py migrate
   ```

4. **Set up SSL with Let's Encrypt**
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d your-domain.com
   ```

5. **Configure Nginx** (reverse proxy to Django on port 8000)
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;
       return 301 https://$server_name$request_uri;
   }
   
   server {
       listen 443 ssl;
       server_name your-domain.com;
       
       ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
       
       location / {
           proxy_pass http://localhost:8000;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

6. **Run with systemd service (gunicorn example)**
   ```ini
   [Unit]
   Description=Alcohol Label Verification (Django)
   After=network.target
   
   [Service]
   Type=simple
   User=www-data
   WorkingDirectory=/path/to/alcohol-labeling-demo
   Environment=PATH=/usr/bin:/usr/local/bin
   Environment=GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
   ExecStart=/usr/local/bin/gunicorn backend.config.wsgi:application --bind 0.0.0.0:8000 --workers 3
   Restart=always
   
   [Install]
   WantedBy=multi-user.target
   ```

## Testing

Run tests locally:

```bash
python backend/manage.py test
```

Or with Docker:

```bash
docker compose exec app python backend/manage.py test
```

You can also use the provided sample labels in `data/sample/` to validate OCR and verification flows.

## Troubleshooting

### Common Issues

1. **GCS Connection Error**
   - Verify service account credentials
   - Check bucket permissions
   - Ensure bucket exists

2. **Gemini API Error**
   - Verify API key is correct
   - Check API quotas and billing
   - Ensure API is enabled

3. **Database Connection Error**
   - Verify PostgreSQL is running
   - Check connection string format
   - Ensure database exists

4. **Image Upload Issues**
   - Check file size limits
   - Verify supported formats (JPEG, PNG, WEBP)
   - Ensure GCS bucket is accessible

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please open an issue in the repository or contact the development team.

