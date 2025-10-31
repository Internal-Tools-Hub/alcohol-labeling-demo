# Deploy on Linux Server (Docker Compose)

Assumptions
- Fresh Linux VM (e.g., Rocky Linux 8/9, Ubuntu 22.04) with SSH access
- You have a non-root user with sudo
- You have a GCP service account (optional) and GCS bucket ready

## 1) SSH and install Docker + Compose
```bash
# SSH into the server
ssh youruser@your-server

# setup ssh key for server: 
ssh-keygen -t ed25519 -C "masonhensley@gmail.com"
# copy public key and add as deploy key: https://github.com/Internal-Tools-Hub/alcohol-labeling-demo/settings/keys
cd .ssh
cat id_ed25519.pub #copy contents to above link as a new key

# Clone repo (or copy via scp)
sudo dnf -y install git || sudo apt-get update && sudo apt-get install -y git
git clone git@github.com:Internal-Tools-Hub/alcohol-labeling-demo.git
cd alcohol-labeling-demo

# Install Docker Engine + Compose plugin
# Rocky Linux / RHEL:
sudo bash scripts/bootstrap_linux_docker.sh
# Ubuntu (alternative): https://docs.docker.com/engine/install/ubuntu/

# Re-login to pick up docker group
exit
ssh youruser@your-server
cd alcohol-labeling-demo
```

## 2) Environment setup
```bash
# Create .env from example
cp env.example .env

# Edit .env (required)
# - POSTGRES_* (optional: defaults ok)
# - DATABASE_URL (defaults ok)
# - DJANGO_SECRET_KEY (set a strong value)
# - DEBUG=false (for production)
# - GCP_PROJECT_ID, GCS_BUCKET_NAME
# - GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account-key.json (if using a key file)
# - GEMINI_API_KEY (if calling Gemini via API key)

# Place credentials (optional if using instance metadata auth)
mkdir -p credentials
# Copy your service account key into credentials/service-account-key.json
```

### Optional: Run Python utilities outside Docker (use a virtualenv)
Ubuntu enforces PEP 668 (externally managed Python). Use a virtual environment for local Python commands (e.g., running `data/sample/seed.py`). The bootstrap script installs `python3`, `python3-venv`, and `python3-pip`.

```bash
cd ~/alcohol-labeling-demo
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

# Example: run the seeder locally (outside Docker)
python data/sample/seed.py --beer

# When done
deactivate
```

## 3) Start services
```bash
# Build and run
docker compose build app
make prod   # or: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 4) Initialize application
```bash
# Run DB migrations and create admin user
docker compose exec app python backend/manage.py migrate
docker compose exec app python backend/manage.py createsuperuser
```

## 5) Access the app
- App (production via nginx profile): http://your-server/
- App (dev without nginx): http://your-server:8000/
- Login: /accounts/login/

## 6) File uploads & GCS
- Uploaded images are stored in the container and uploaded to your GCS bucket.
- Ensure the service account has `storage.objects.create` on the bucket.

## 7) Logs & lifecycle
```bash
# Follow logs
docker compose logs -f app

# Restart
docker compose restart app

# Stop
docker compose down
```

## 8) Tailwind (optional local build)
The app ships with Tailwind CDN enabled. To use django-tailwind local build instead:
```bash
docker compose exec app python backend/manage.py tailwind init
docker compose exec app python backend/manage.py tailwind install
docker compose exec app python backend/manage.py tailwind dev
```

## 9) Security & hardening
- Set `DEBUG=false`
- Set `ALLOWED_HOSTS` in `.env`
- Rotate `DJANGO_SECRET_KEY`
- Restrict inbound security group/iptables as needed
- Ensure TLS (configure nginx with valid certs)

## 10) Troubleshooting
- Tailwind module not found → rebuild image (`docker compose build --no-cache app`)
- Django not found → ensure `requirements.txt` installed during build
- DB issues → `docker compose down -v` to reset volumes (data loss!) then `make prod`
