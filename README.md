# Alcohol Label Verification App

A Streamlit-based web application that simulates the TTB (Alcohol and Tobacco Tax and Trade Bureau) label approval process. The app uses Google Gemini Vision API to extract text from alcohol label images and compares it against user-submitted form data.

## Features

- **Label Verification**: Upload alcohol label images and verify against form data
- **AI-Powered Text Extraction**: Uses Google Gemini Vision API for accurate text extraction
- **Fuzzy Matching**: Intelligent comparison with tolerance for minor OCR errors
- **Role-Based Access**: Switch between submitter and admin roles
- **Submission History**: Admin view of all submissions with filtering
- **Real-time Results**: Immediate verification results with detailed field-by-field comparison

## Architecture

- **Frontend/Backend**: Streamlit (Python 3)
- **Database**: PostgreSQL 17+
- **Storage**: Google Cloud Storage (for uploaded images)
- **AI/OCR**: Google Gemini Vision API
- **Deployment**: Linux VM with SSL

## Prerequisites

### Option 1: Docker (Recommended)
- Docker (version 20.10+)
- Docker Compose (version 2.0+)
- Google Cloud Platform account with:
  - Gemini API enabled
  - Cloud Storage bucket

### Option 2: Manual Installation
- Python 3.8+
- PostgreSQL 17+
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
   - Application: http://localhost:8501
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
   GEMINI_API_KEY=your_gemini_api_key_here
   GCP_PROJECT_ID=your_gcp_project_id_here
   GCS_BUCKET_NAME=your_gcs_bucket_name_here
   DATABASE_URL=postgresql://username:password@localhost:5432/alcohol_label_verification
   DEFAULT_ROLE=admin
   ```

4. **Set up Google Cloud credentials**
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="path/to/your/service-account-key.json"
   ```

5. **Initialize the database**
   ```bash
   # Create database
   createdb alcohol_label_verification
   
   # Run initialization script
   psql -d alcohol_label_verification -f scripts/init_db.sql
   ```

6. **Run the application**
   ```bash
   streamlit run app.py
   ```

## Usage

### Submitter Role
1. Fill out the product information form:
   - Brand Name
   - Product Type/Class
   - Alcohol Content (%)
   - Net Contents (optional)

2. Upload a clear image of the alcohol label

3. Click "Verify Label" to process the verification

4. View detailed results showing field-by-field comparison

### Admin Role
1. Switch to admin role using the toggle button
2. View all submissions in the admin history page
3. Filter submissions by status, date, or other criteria
4. Click on individual submissions for detailed view

## API Configuration

### Google Gemini API
1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Create a new API key
3. Add the key to your `.env` file

### Google Cloud Storage
1. Create a GCS bucket in your Google Cloud project
2. Set appropriate permissions for your service account
3. Update the bucket name in your `.env` file

## Database Schema

The application uses three main tables:

- **users**: User accounts and roles
- **submissions**: Label verification submissions
- **verification_results**: Detailed field-by-field comparison results

## Deployment

### Linux VM Deployment

1. **Prepare the server**
   ```bash
   # Update system
   sudo apt update && sudo apt upgrade -y
   
   # Install Python 3.8+
   sudo apt install python3 python3-pip postgresql postgresql-contrib
   
   # Install Nginx (for SSL termination)
   sudo apt install nginx
   ```

2. **Set up PostgreSQL**
   ```bash
   sudo -u postgres createdb alcohol_label_verification
   sudo -u postgres psql -d alcohol_label_verification -f scripts/init_db.sql
   ```

3. **Deploy application**
   ```bash
   # Clone repository
   git clone <repository-url>
   cd alcohol-labeling-demo
   
   # Install dependencies
   pip3 install -r requirements.txt
   
   # Set up environment
   cp .env.example .env
   # Edit .env with production values
   ```

4. **Set up SSL with Let's Encrypt**
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d your-domain.com
   ```

5. **Configure Nginx**
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
           proxy_pass http://localhost:8501;
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

6. **Run with systemd service**
   ```bash
   # Create service file
   sudo nano /etc/systemd/system/alcohol-label-verification.service
   ```
   
   ```ini
   [Unit]
   Description=Alcohol Label Verification App
   After=network.target
   
   [Service]
   Type=simple
   User=www-data
   WorkingDirectory=/path/to/alcohol-labeling-demo
   Environment=PATH=/usr/bin:/usr/local/bin
   Environment=GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
   ExecStart=/usr/local/bin/streamlit run app.py --server.port=8501 --server.address=0.0.0.0
   Restart=always
   
   [Install]
   WantedBy=multi-user.target
   ```
   
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable alcohol-label-verification
   sudo systemctl start alcohol-label-verification
   ```

## Testing

The application includes test functionality for:
- GCS connection
- Gemini API connection
- Database connectivity

Test with sample alcohol labels (bourbon, wine, beer) to verify functionality.

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

