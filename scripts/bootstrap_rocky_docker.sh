#!/usr/bin/env bash

set -euo pipefail

# Bootstrap a Rocky Linux 8/9 server with Docker Engine and Docker Compose (plugin)
# Usage: sudo ./bootstrap_rocky_docker.sh

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (use sudo)." >&2
  exit 1
fi

echo "[1/7] Updating system packages..."
dnf -y update || true

echo "[2/7] Installing required tools (dnf-plugins-core, curl, ca-certificates)..."
dnf -y install dnf-plugins-core curl ca-certificates gnupg || true

echo "[3/7] Adding Docker CE repository..."
curl -fsSL https://download.docker.com/linux/centos/docker-ce.repo -o /etc/yum.repos.d/docker-ce.repo

echo "[4/7] Installing Docker Engine, CLI, containerd, Buildx, and Compose plugin..."
dnf -y install \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

echo "[5/7] Enabling and starting Docker service..."
systemctl enable docker
systemctl start docker

echo "[6/7] Adding non-root user to docker group (if available)..."
TARGET_USER=${SUDO_USER:-${USER}}
if id -u "${TARGET_USER}" >/dev/null 2>&1; then
  usermod -aG docker "${TARGET_USER}" || true
  echo " - Added ${TARGET_USER} to docker group. You'll need to log out and back in for this to take effect."
fi

echo "[7/7] Verifying installation..."
docker --version || { echo "Docker not found in PATH" >&2; exit 1; }
docker compose version || { echo "Docker Compose plugin not found" >&2; exit 1; }

echo "\nSuccess! Docker and Docker Compose are installed."
echo "Next steps:"
echo "  1) Log out and back in (or run: newgrp docker) to use docker without sudo."
echo "  2) Test: docker run --rm hello-world"
echo "  3) Use 'docker compose' in this repo with: make dev"


