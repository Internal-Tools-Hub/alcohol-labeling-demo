#!/usr/bin/env bash

set -euo pipefail

# Bootstrap an Ubuntu server with Docker Engine and Docker Compose (plugin)
# Usage: sudo ./bootstrap_linux_docker.sh

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (use sudo)." >&2
  exit 1
fi

echo "[1/10] Updating APT package index and upgrading packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y || true

echo "[2/10] Installing prerequisites (ca-certificates, curl, gnupg, software-properties-common, ufw, fail2ban, unattended-upgrades)..."
apt-get install -y \
  ca-certificates \
  curl \
  gnupg \
  software-properties-common \
  apt-transport-https \
  ufw \
  fail2ban \
  unattended-upgrades || true

echo "[3/10] Adding Docker's official GPG key and APT repository..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
UBUNTU_CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
apt-get update -y

echo "[4/10] Installing Docker Engine, CLI, containerd, Buildx, and Compose plugin..."
apt-get install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

echo "[5/10] Enabling and starting Docker service..."
systemctl enable docker
systemctl start docker

echo "[6/10] Adding non-root user to docker group (if available)..."
TARGET_USER=${SUDO_USER:-${USER}}
if id -u "${TARGET_USER}" >/dev/null 2>&1; then
  usermod -aG docker "${TARGET_USER}" || true
  echo " - Added ${TARGET_USER} to docker group. You'll need to log out and back in for this to take effect."
fi

echo "[7/10] Configuring UFW firewall (deny incoming, allow outgoing, allow OpenSSH)..."
ufw --force reset >/dev/null 2>&1 || true
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
yes | ufw enable

echo "[8/10] Enabling fail2ban..."
systemctl enable --now fail2ban || true

echo "[9/10] Enabling unattended security upgrades..."
printf "APT::Periodic::Update-Package-Lists \"1\";\nAPT::Periodic::Unattended-Upgrade \"1\";\n" > /etc/apt/apt.conf.d/20auto-upgrades
systemctl enable --now unattended-upgrades || true

echo "[10/10] SSH hardening..."
# Safe default: disable root login. Password auth can be disabled by setting SSH_DISABLE_PASSWORDS=true
SSH_HARDEN_DIR=/etc/ssh/sshd_config.d
install -m 0755 -d "$SSH_HARDEN_DIR"
HARDEN_FILE="$SSH_HARDEN_DIR/99-hardening.conf"
{
  echo "PermitRootLogin no"
  echo "Protocol 2"
  echo "X11Forwarding no"
  echo "ClientAliveInterval 300"
  echo "ClientAliveCountMax 2"
  echo "MaxAuthTries 3"
  echo "ChallengeResponseAuthentication no"
  echo "UsePAM yes"
} > "$HARDEN_FILE"

if [[ "${SSH_DISABLE_PASSWORDS:-false}" == "true" ]]; then
  echo "PasswordAuthentication no" >> "$HARDEN_FILE"
  echo " - SSH password authentication DISABLED. Ensure you have working SSH keys."
else
  echo " - SSH password authentication left as-is. To disable, re-run with SSH_DISABLE_PASSWORDS=true."
fi

if sshd -t 2>/dev/null; then
  systemctl reload ssh || systemctl restart ssh || true
else
  echo " - Warning: sshd config test failed; not reloading sshd." >&2
fi

echo "Verifying installation..."
docker --version || { echo "Docker not found in PATH" >&2; exit 1; }
docker compose version || { echo "Docker Compose plugin not found" >&2; exit 1; }
ufw status verbose || true
systemctl status fail2ban --no-pager -l | sed -n '1,10p' || true
systemctl status unattended-upgrades --no-pager -l | sed -n '1,10p' || true

echo "\nSuccess! Ubuntu server is bootstrapped with Docker and basic hardening."
echo "Next steps:"
echo "  1) Log out and back in (or run: newgrp docker) to use docker without sudo."
echo "  2) Test Docker: docker run --rm hello-world"
echo "  3) SSH passwords are $( [[ "${SSH_DISABLE_PASSWORDS:-false}" == "true" ]] && echo DISABLED || echo ENABLED ). To disable: SSH_DISABLE_PASSWORDS=true sudo $0"
echo "  4) Firewall: only OpenSSH allowed inbound by default (UFW). Adjust as needed."
echo "  5) Use 'docker compose' in this repo with: make dev"


