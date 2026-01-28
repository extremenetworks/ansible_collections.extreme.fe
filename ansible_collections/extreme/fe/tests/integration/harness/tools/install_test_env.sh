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

if prompt_install_gns3 ; then
  INSTALL_GNS3=true
  echo " Installing with GNS3 environment"
  
  #install_subnet_route

  # add "add-ub-route" to the sudoers file if not already present
  echo "bjorn ALL=(root) NOPASSWD: $TOOLS_DIR/add-ub-route" | sudo tee /etc/sudoers.d/add-ub-route 
  sudo chmod 440 /etc/sudoers.d/add-ub-route

  # Ask the user for the project name, default is Ansible   
  project_prompt=" Enter the GNS3 project name [Ansible]: "
  read -r -p "$project_prompt" project_response
  project_response=${project_response:-Ansible} 

  # Ask the user for the subnet of the GNS3 Network  
  subnet_prompt=" Enter subnet n for the GNS3 internal network (e.g., 192.168.n.0) [5]: "
  read -r -p "$subnet_prompt" subnet_response
  subnet_response=${subnet_response:-5}
  
  # Ask if the Subnet router public IP should use a DHCP client or static IP
  dhcp_prompt=" Should the Subnet Router use DHCP for its public IP? [Y/n]: "
  read -r -p "$dhcp_prompt" dhcp_response
  dhcp_response=${dhcp_response:-Y}
  case "$dhcp_response" in
    [Yy]*)
      UB_SERVER_ETH0_DHCP="true"
      UB_SERVER_ETH0_IP=""
      ;;
    [Nn]*)
      UB_SERVER_ETH0_DHCP="false"
      static_ip_prompt=" Enter the static IP for the Subnet Router public interface (e.g., 192.168.1.252, or 10.10.10.15) [192.168.1.252]: "
      read -r -p "$static_ip_prompt" static_ip_response
      UB_SERVER_ETH0_IP=${static_ip_response:-192.168.1.252}

      # Ask for the netmask and gateway if static IP is chosen
      netmask_prompt=" Enter the netmask for the Subnet Router public interface (e.g., 255.255.255.0) [255.255.255.0]: "
      read -r -p "$netmask_prompt" netmask_response
      netmask_response=${netmask_response:-255.255.255.0}
      gateway_prompt=" Enter the gateway for the Subnet Router public interface (e.g., 192.168.1.1) [192.168.1.1]: "
      read -r -p "$gateway_prompt" gateway_response
      gateway_response=${gateway_response:-192.168.1.1}
      ;;
    *)
      UB_SERVER_ETH0_DHCP="true"
      UB_SERVER_ETH0_IP=""
      ;;
  esac

  # Determine our own IP, so we can set it for the GNS3_SERVER_HOST
  my_ip=$(ip addr show | grep 'inet ' | grep -v '127.0.0.1' | grep -v docker | grep -v virbr| awk '{print $2}' | cut -d'/' -f1 | head -n1)
  if [ -z "$my_ip" ] ; then
    echo " Unable to determine my own IP address"
    # Ask formy own IP
    ip_prompt=" Enter the IP address of this host (GNS3 server) []: "
    read -r -p "$ip_prompt" my_ip
  fi
  if [ -z "$my_ip" ] ; then
    echo " No IP address provided, cannot continue"
    exit 1
  fi

  # Create the gns3.cfg file from scratch
  echo " Creating GNS3 configuration file $GNS3_CFG_PATH"
  echo "GNS3_PROJECT_NAME=$project_response" > "$GNS3_CFG_PATH"
  echo "GNS3_SERVER_HOST=$my_ip" >> "$GNS3_CFG_PATH"
  echo "GNS3_SERVER_PORT=3080" >> "$GNS3_CFG_PATH"
  echo "GNS3_SERVER_NETWORK_ADAPTER=1" >> "$GNS3_CFG_PATH"
  echo "GNS3_LAN_PORT=\"br0\"" >> "$GNS3_CFG_PATH"
  echo "GNS3_LAN_PORT_NR=\"0\"" >> "$GNS3_CFG_PATH"
  echo "GNS3_LAN_ADAPTER=\"0\"" >> "$GNS3_CFG_PATH"
  echo "GNS3_SERVER_DT_IMAGE_PATH=\$ANSIBLE/tests/integration/harness/gns3_images" >> "$GNS3_CFG_PATH"
  echo "SUBNET_ROUTER_GATEWAY=$UB_SERVER_ETH0_IP" >> "$GNS3_CFG_PATH"
  echo "SUBNET_ROUTER_NETWORK=$subnet_response" >> "$GNS3_CFG_PATH"
  echo "source \${ANSIBLE}/tests/integration/harness/tools/gns3_func" >> "$GNS3_CFG_PATH"
  echo "DT_IMAGE_PATH=\$GNS3_SERVER_DT_IMAGE_PATH" >> "$GNS3_CFG_PATH"

  # Update the subnet router docker interface file
  IFile="$HARNESS_DIR/docker/ubserver/interfaces"
  echo " Updating subnet router interface file $IFile"

  # eth0 can be DHCP or static
  if [ "$UB_SERVER_ETH0_DHCP" = "false" ] ; then
    echo "iface eth0 inet static" > "$IFile"
    echo "	address $UB_SERVER_ETH0_IP" >> "$IFile"
    echo "	netmask $netmask_response" >> "$IFile"
    echo "	gateway $gateway_response" >> "$IFile"
  else
    echo "auto eth0" > "$IFile"
    echo "iface eth0 inet dhcp" >> "$IFile"
    echo "	hostname br0_vm-1" >> "$IFile"
  fi

  # eth1 is always static, only the subnet n can be chosen, within the 192.168.x.0/24 range
  echo "iface eth1 inet static" >> "$IFile"
  echo "	address 192.168.$subnet_response.1" >> "$IFile"
  echo "	netmask 255.255.255.0" >> "$IFile"

  # Write the host IP to the dashboard-server-ip file
  DASHBOARD_IP_FILE="$HARNESS_DIR/docker/ubserver/dashboard-server-ip"
  echo " Writing dashboard server IP to $DASHBOARD_IP_FILE"
  echo "$my_ip" > "$DASHBOARD_IP_FILE"

  # Create the ansible inventory file
  INV_FILE="$HARNESS_DIR/cfg/inventory.ini"
  echo " Creating Ansible inventory file $INV_FILE"

  # Copy the template-inventory.ini to inventory.ini, replacing SUBNET with the chosen subnet n 
  sed -E "s/SUBNET/$subnet_response/g" "$HARNESS_DIR/cfg/template-inventory.ini" > "$INV_FILE"
    
  # Create the DHCPd.conf file from the template, make sure to replace $SUBNET with the chosen subnet n
  DHCPD_TEMPLATE="$HARNESS_DIR/docker/ubserver/template-dhcpd.conf"
  DHCPD_CONF="$HARNESS_DIR/docker/ubserver/dhcpd.conf"
  echo " Creating DHCPd configuration file $DHCPD_CONF from template $DHCPD_TEMPLATE"
  sed -E "s/SUBNET/$subnet_response/g" "$DHCPD_TEMPLATE" > "$DHCPD_CONF"

  # Create a new interfaces file in the pc directory, based upon the teomplate-interfaces file, be sure to substitute $SUBNET
  PC_TEMPLATE="$HARNESS_DIR/docker/pc/template-interfaces"
  PC_INTERFACES="$HARNESS_DIR/docker/pc/interfaces"
  echo " Creating PC interfaces file $PC_INTERFACES from template $PC_TEMPLATE"
  sed -E "s/SUBNET/$subnet_response/g" "$PC_TEMPLATE" > "$PC_INTERFACES"
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

# Copy the template-test.yml to test.yml if it does not already exist
TEST_YML_TEMPLATE="$HARNESS_DIR/cfg/template-test.yml"
TEST_YML_FILE="$HARNESS_DIR/cfg/test.yml"
if [ ! -f "$TEST_YML_FILE" ] ; then
  echo " Creating test.yml from template"
  cp "$TEST_YML_TEMPLATE" "$TEST_YML_FILE"
else
  echo " test.yml already exists, not overwriting"
fi

# Update packages and install build dependencies
sudo apt update 
sudo apt upgrade -y

# Install packages
echo "*** Installing packages ***"

echo "Installing Vmware tools"
sudo apt install -y open-vm-tools

sudo apt install -y git python3 python3-pip python3-venv expect fping 

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

  echo "*** Installing gns3 ***"
  sudo add-apt-repository -y ppa:gns3/ppa

  sudo apt install -y python3 python3-pip python3-venv \
    qemu-kvm qemu-utils libvirt-daemon-system libvirt-clients \
    bridge-utils virt-manager docker.io dynamips vpcs ubridge

  sudo systemctl enable --now libvirtd
  sudo systemctl enable --now docker

  python3 -m venv ~/gns3-venv
  source ~/gns3-venv/bin/activate

  pip install --upgrade pip

  pip install gns3-server==2.2.54 gns3-gui==2.2.54

  sudo ln -s ~/gns3-venv/bin/gns3server /usr/local/bin/gns3server

  sudo ufw allow 3080/tcp

  # Update privilege level for kvm, libvirt, ubridge, docker
  sudo usermod -aG kvm,libvirt,ubridge,docker $(whoami)

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
        network=${network:-5}
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
        - to: 192.168.$network.0/24
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
 
  
  echo " =================================================="
  echo " You must reboot for all the changes to take effect"
  echo " =================================================="

fi
