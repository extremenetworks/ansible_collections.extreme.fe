#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GNS3_CFG_PATH="$HARNESS_DIR/cfg/gns3.cfg"
TOOLS_DIR="$HARNESS_DIR/tools"

prompt_install_gns3() {
  local prompt="Do you want to install the GNS3 environment? [Y/n]: "
  local response
  read -r -p "$prompt" response
  response=${response:-Y}
  case "$response" in
    [Yy]*) return 0 ;;
    [Nn]*) return 1 ;;
    *) return 0 ;;
  esac
}

read_cfg_value() {
  local key="$1"
  local cfg="$GNS3_CFG_PATH"
  if [ ! -f "$cfg" ]; then
    echo ""
    return
  fi
  sed -n -E "s/^${key}=\"?([^\"]*)\"?/\1/p" "$cfg" | head -n1
}

update_subnet_router_gateway() {
  local cfg="$GNS3_CFG_PATH"
  if [ ! -f "$cfg" ]; then
    echo " Unable to update SUBNET_ROUTER_GATEWAY: $cfg not found"
    return
  fi
  local current_gateway
  current_gateway=$(read_cfg_value "SUBNET_ROUTER_GATEWAY")
  local display_gateway="${current_gateway:-unset}"
  echo -n " Enter subnet router gateway IP [$display_gateway]: "
  read -r gateway_input
  if [ -z "$gateway_input" ]; then
    gateway_input="$current_gateway"
  fi
  if [ -z "$gateway_input" ]; then
    echo " No gateway provided; keeping existing value"
    return
  fi
  sed -i -E "s|^SUBNET_ROUTER_GATEWAY=.*|SUBNET_ROUTER_GATEWAY=\"$gateway_input\"|" "$cfg"
  echo " Updated SUBNET_ROUTER_GATEWAY to $gateway_input in $cfg"
}

install_subnet_route() {
  local gateway network
  gateway=$(read_cfg_value "SUBNET_ROUTER_GATEWAY")
  network=$(read_cfg_value "SUBNET_ROUTER_NETWORK")
  if [ -n "$gateway" ] && [ -n "$network" ]; then
    local existing
    existing=$(ip route | grep -F "$gateway" | wc -l)
    if [ "$existing" = "0" ]; then
      echo "Installing route to $network through gateway $gateway"
      sudo ip route add "$network" via "$gateway"
    fi
  fi
}

modify_gns3_server_ip() {
  # retrieve my own IP from command "ip addr"
  local my_ip
  my_ip=$(ip addr show | grep 'inet ' | grep -v '127.0.0.1' | grep -v docker | grep -v virbr| awk '{print $2}' | cut -d'/' -f1 | head -n1)
  if [ -z "$my_ip" ] ; then
    echo " Unable to determine my own IP address"
    return
  fi
  echo " Modifying GNS3 server IP to $my_ip in cfg/gns3.cfg"
  local cfg="$GNS3_CFG_PATH"
  if [ ! -f "$cfg" ]; then
    echo " Unable to update GNS3_SERVER_HOST: $cfg not found"
    return
  fi
  sed -i -E "s|^GNS3_SERVER_HOST=.*|GNS3_SERVER_HOST=$my_ip|" "$cfg"  
}
if prompt_install_gns3 ; then
  INSTALL_GNS3=true
  echo " Installing with GNS3 environment"
  update_subnet_router_gateway
  #install_subnet_route
  modify_gns3_server_ip
else
  INSTALL_GNS3=false
fi

# Set the correct timezone
# First check if the timezone is set to UTC
current_tz=$(timedatectl | grep "Time zone" | awk '{print $3}')
if [ "$current_tz" = "Etc/UTC" ]; then
  # Ask the user which timezone is desired
  read -p "Enter desired timezone (e.g., America/Chicago, America/New_York, America/Los_Angeles): " desired_tz
  if [ -n "$desired_tz" ]; then
    sudo timedatectl set-timezone "$desired_tz"
    echo " Timezone set to $desired_tz"
  else
    echo " No timezone entered; keeping current timezone"
  fi
else
  echo " Timezone is already set to $current_tz; no changes made"
fi

# Update packages and install build dependencies
sudo apt update 
sudo apt upgrade -y

# Install packages
echo "*** Installing packages ***"

echo "Installing Vmware tools"
sudo apt install -y open-vm-tools

sudo apt install -y git python3 python3-pip python3-venv expect

#################################
# Install ssh
#################################
echo "*** Installing sshd ***"
sudo apt-get install openssh-server

# Create a virtual python environment. We need this in a specific directory!
cd $TOOLS_DIR/..
echo "*** Creating python virtual environment ***"
python3 -m venv venv
source venv/bin/activate

# Install extra python packages
pip install --upgrade pip
pip install fastapi pydantic uvicorn websockets
echo " ---------------------------------------------------------------"
pip install coverage PyYAML yamllint ansible ansible-lint
echo " ---------------------------------------------------------------"

if [ "$INSTALL_GNS3" = true ] ; then
  echo "*** Installing docker ***"

  ###################################
  # Install docker
  ###################################

  # 1. Install docker packages
  sudo apt install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

  # 2. Add Docker GPG key and repository
  sudo rm -rf /etc/apt/keyrings
  sudo mkdir -p /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

  # 3. Fix permissions
  sudo chmod a+r /etc/apt/keyrings/docker.gpg

  # 4. Add the Docker repository
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

  # 5. Install the Docker Engine
  sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  # 5. Add your user to docker group (to run without sudo)
  sudo usermod -aG docker $USER

  echo "*** Installing gns3 ***"
  sudo add-apt-repository -y ppa:gns3/ppa

  sudo apt install -y python3 python3-pip python3-venv \
    qemu-kvm qemu-utils libvirt-daemon-system libvirt-clients \
    bridge-utils virt-manager docker.io

  sudo systemctl enable --now libvirtd
  sudo systemctl enable --now docker

  python3 -m venv ~/gns3-venv
  source ~/gns3-venv/bin/activate

  sudo apt install -y ubridge

  pip install --upgrade pip

  pip install gns3-server==2.2.54 gns3-gui==2.2.54

  sudo ln -s ~/gns3-venv/bin/gns3server /usr/local/bin/gns3server

  sudo ufw allow 3080/tcp

  # Update privilege level
  sudo usermod -aG kvm,libvirt,ubridge $(whoami)

  echo "Determining network changes"
  NETPLAN_FILE="/etc/netplan/00-installer-config.yaml"
  if sudo test -f "$NETPLAN_FILE"; then
    if sudo grep -qE '^[[:space:]]*br0:' "$NETPLAN_FILE"; then
      echo " br0 already defined in $NETPLAN_FILE; skipping bridge configuration"
    else
      mac_address=$(ip link show ens33 2>/dev/null | awk '/link\/ether/ {print $2; exit}')
      if [ -z "$mac_address" ]; then
        echo " Unable to determine MAC address for ens33; skipping netplan bridge configuration"
      else
        gateway=$(read_cfg_value "SUBNET_ROUTER_GATEWAY")
        network=$(read_cfg_value "SUBNET_ROUTER_NETWORK")
        gateway=${gateway:-192.168.1.252}
        network=${network:-192.168.5.0/24}
        backup_path="${NETPLAN_FILE}.$(date +%Y%m%d%H%M%S).bak"
        sudo cp "$NETPLAN_FILE" "$backup_path"
        sudo tee "$NETPLAN_FILE" > /dev/null <<EOF
network:
  version: 2
  ethernets:
    ens33:
      dhcp4: no
      dhcp6: no
      match:
        macaddress: $mac_address
      set-name: ens33
  bridges:
    br0:
      interfaces: [ens33]
      macaddress: $mac_address
      dhcp4: true
      dhcp6: true
      parameters:
        stp: false
        forward-delay: 0
      routes:
        - to: $network
          via: $gateway
EOF
        sudo netplan apply
        echo " Configured br0 bridge in $NETPLAN_FILE (backup saved to $backup_path)"
        #echo " Network settings have changed; please reboot for the changes to take effect."
      fi
    fi
  else
    echo " Netplan file $NETPLAN_FILE not found; skipping bridge configuration"
  fi

  #Install gns3 2.2.54 version
  #sudo add-apt-repository -y ppa:gns3/ppa

  #sudo apt install -y python3-pip python3-pyqt5 python3-pyqt5.qtwebsockets python3-pyqt5.qtsvg qemu-kvm qemu-utils libvirt-daemon-system libvirt-clients bridge-utils virtinst virt-manager dynamips vpcs ubridge

  #pip3 install gns3-server==2.2.54 gns3-gui==2.2.54

  # Export PATH
  #echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc

  # Update privilege level
  #sudo usermod -aG kvm,libvirt,ubridge $(whoami)


  
  
  echo
  echo " You must logout and log back in for the updates to take effect"
  echo

fi
