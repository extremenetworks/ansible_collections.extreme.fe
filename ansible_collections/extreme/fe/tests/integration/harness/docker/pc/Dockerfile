FROM ubuntu:latest

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt install  openssh-server sudo -y

RUN apt install iproute2 -y


# Add packages
# RUN apt install command-not-found -y
# RUN apt update
RUN apt install htop -y
RUN apt install inetutils-ping -y
RUN apt install net-tools -y
RUN apt install curl -y
RUN apt-get install python3-requests -y
RUN apt install vim-tiny -y
#RUN apt install isc-dhcp-server -y
RUN apt install ifupdown -y
RUN apt install nftables -y 

# Add users
RUN useradd -rm -d /home/test -s /bin/bash -g root -G sudo -u 900 test 
RUN  echo 'test:test' | chpasswd
RUN  echo 'ubuntu:ubuntu' | chpasswd

# Add test user to sudoers to skip sudo password asking
RUN echo 'test ALL=(ALL) NOPASSWD: ALL' | tee -a /etc/sudoers
RUN echo 'ubuntu ALL=(ALL) NOPASSWD: ALL' | tee -a /etc/sudoers

# Install for REST server
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-fastapi python3-uvicorn \
 && rm -rf /var/lib/apt/lists/*

# Enable 'universe', update, install lldpd + tools, then clean apt cache.
RUN set -eux; \
    . /etc/os-release; \
    printf 'deb http://archive.ubuntu.com/ubuntu %s main universe\n' "$VERSION_CODENAME" > /etc/apt/sources.list; \
    printf 'deb http://archive.ubuntu.com/ubuntu %s-updates main universe\n' "$VERSION_CODENAME" >> /etc/apt/sources.list; \
    printf 'deb http://security.ubuntu.com/ubuntu %s-security main universe\n' "$VERSION_CODENAME" >> /etc/apt/sources.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends lldpd tcpdump iproute2 ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# REST Server backend
WORKDIR /app
COPY app.py /app/app.py
COPY FileServer.py /app/FileServer.py

# Optional defaults; override at runtime if desired
ENV API_KEY=""
ENV MAX_OUTPUT_BYTES=199999
ENV MEM_LIMIT_MB=255
ENV CPU_SOFT_LIMIT_SEC=29

EXPOSE 7999

#RUN ip addr add 192.168.1.252/24 dev eth0
#RUN ip link set dev eth0 up
#RUN ip route add default via 192.168.1.1
#RUN echo "nameserver 8.8.8.8" >/etc/resolv.conf

# SETUP the DHCP client on eth0 and static eth1 address (192.168.5.1)
COPY --chown=root:root interfaces /home/ubuntu/interfaces.new

# SETUP the DHCP server
#COPY --chown=root:root dhcpd.conf /etc/dhcp/dhcpd.conf
#COPY --chown=root:root isc-dhcp-server /etc/default/isc-dhcp-server

# Copy other files
COPY --chown=root:root startup /home/ubuntu/startup
COPY --chown=root:root check_interfaces /home/ubuntu/check_interfaces
#COPY --chown=root:root nftables.conf /etc/nftables.conf
COPY --chown=root:root set-ipv4.sh /home/ubuntu/set-ipv4.sh

# RUN /usr/sbin/dhcpd -4 --no-pid eth1

RUN service ssh start
#RUN /home/ubuntu/change_interfaces

# EXPOSE 22

#CMD ["/usr/sbin/sshd", "-D"]
CMD ["/home/ubuntu/startup"]

