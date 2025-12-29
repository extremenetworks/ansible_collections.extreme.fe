#!/usr/bin/env bash
set -e

echo "Updating package list..."
sudo apt update -y
sudo apt upgrade -y

echo "Installing basic packages..."
sudo apt install -y \
    curl \
    wget \
    git \
    htop \
    python3-pip \
    python3-venv \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release \
    software-properties-common \
    python3-setuptools \
    python3-wheel \
    python3-dev \
    python3-pyqt5 \
    python3-pyqt5.qtsvg \
    python3-pyqt5.qtwebsockets \
    python3-pyqt5.qtwebengine \
    expect \
    jq

# Upgrade pip
echo "Upgrading pip..."
python3 -m pip install --user --upgrade pip

# Install Ansible system-wide using sudo
echo "Installing ansible-core 2.17.14 system-wide..."
sudo python3 -m pip install ansible-core==2.17.14
echo "Ansible installation complete:"
ansible --version || true

# -------------------------------
# Docker installation
# -------------------------------
echo "Installing Docker 26.1.0..."

# Remove old versions (if any)
sudo apt remove -y docker docker-engine docker.io containerd runc || true

# Install prerequisites for Docker repository (redundant runs are harmless)
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt update

# Pin specific Docker release (26.1.0) and compatible dependencies
DOCKER_VERSION="5:26.1.0-1~ubuntu.22.04~jammy"
CONTAINERD_VERSION="1.6.33-1"
BUILDX_VERSION="0.29.0-0~ubuntu.22.04~jammy"
COMPOSE_VERSION="2.40.0-1~ubuntu.22.04~jammy"

sudo apt install -y --allow-downgrades \
    docker-ce=${DOCKER_VERSION} \
    docker-ce-cli=${DOCKER_VERSION} \
    containerd.io=${CONTAINERD_VERSION} \
    docker-buildx-plugin=${BUILDX_VERSION} \
    docker-compose-plugin=${COMPOSE_VERSION}

# Enable and start Docker service
sudo systemctl enable docker
sudo systemctl start docker

echo "Adding $USER to docker group..."
sudo usermod -aG docker $USER

echo "Docker installation complete:"
docker --version

# -------------------------------
# GNS3 server + Web UI
# -------------------------------
echo "Installing GNS3 server 2.2.54 + Web UI only..."

sudo python3 -m pip install --upgrade pip

# Install GNS3 server + Web UI system-wide
sudo python3 -m pip install gns3-server==2.2.54

# sudo apt install -y  qemu-utils libvirt-daemon-system libvirt-clients bridge-utils virtinst virt-manager dynamips vpcs ubridge

sudo add-apt-repository -y ppa:gns3/ppa
sudo apt update
# Install GNS3 dependencies and ubridge
sudo apt install -y gns3-server dynamips ubridge vpcs

# Verify installation
echo "GNS3 installation complete. Checking version..."
gns3server --version


sudo python3 -m pip install fastapi pydantic uvicorn
sudo python3 -m pip install coverage