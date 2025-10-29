#!/bin/bash

# Alcohol Label Verification App Setup Script
# This script sets up the application on a Linux VM

set -e

echo "🍷 Setting up Alcohol Label Verification App..."

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
echo "🐍 Installing Python and dependencies..."
sudo apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib nginx

# Install Node.js (for some Python packages that need it)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Create application directory
APP_DIR="/opt/alcohol-label-verification"
echo "📁 Creating application directory at $APP_DIR..."
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

# Copy application files
echo "📋 Copying application files..."
cp -r . $APP_DIR/
cd $APP_DIR

# Create virtual environment
echo "🔧 Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Set up PostgreSQL
echo "🗄️ Setting up PostgreSQL database..."
sudo -u postgres createdb alcohol_label_verification || echo "Database may already exist"
sudo -u postgres psql -d alcohol_label_verification -f scripts/init_db.sql

# Create systemd service
echo "⚙️ Creating systemd service..."
sudo tee /etc/systemd/system/alcohol-label-verification.service > /dev/null <<EOF
[Unit]
Description=Alcohol Label Verification App
After=network.target postgresql.service

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin:/usr/bin:/usr/local/bin
Environment=GOOGLE_APPLICATION_CREDENTIALS=$APP_DIR/service-account-key.json
ExecStart=$APP_DIR/venv/bin/streamlit run app.py --server.port=8501 --server.address=0.0.0.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create Nginx configuration
echo "🌐 Setting up Nginx configuration..."
sudo tee /etc/nginx/sites-available/alcohol-label-verification > /dev/null <<EOF
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }
}
EOF

# Enable Nginx site
sudo ln -sf /etc/nginx/sites-available/alcohol-label-verification /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

# Enable and start services
echo "🚀 Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable alcohol-label-verification
sudo systemctl start alcohol-label-verification

# Set up SSL with Let's Encrypt (optional)
echo "🔒 SSL Setup (Optional)"
echo "To set up SSL with Let's Encrypt, run:"
echo "sudo apt install certbot python3-certbot-nginx"
echo "sudo certbot --nginx -d your-domain.com"

echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Copy your .env file to $APP_DIR"
echo "2. Copy your Google Cloud service account key to $APP_DIR/service-account-key.json"
echo "3. Restart the service: sudo systemctl restart alcohol-label-verification"
echo "4. Check status: sudo systemctl status alcohol-label-verification"
echo "5. View logs: sudo journalctl -u alcohol-label-verification -f"
echo ""
echo "🌐 Application will be available at: http://your-server-ip"

