#!/bin/bash
# AP for Pico devices
# SSID Must be > 8 Chars
AP_IP="192.168.72.1"
AP_SSID="PICOBREW"
AP_PASS="PICOBREW"

export IMG_NAME="PICOBREW_PICOCLAW"
export IMG_RELEASE="beta7"
# export IMG_VARIANT="stable"
export IMG_VARIANT="latest"
export GIT_SHA='$(git rev-parse --short HEAD)'

# GitHub repository to clone (override for forks)
GIT_REPO="${GIT_REPO:-https://github.com/Moinster/PicoBrew_PicoClaw.git}"

# Disable the first-boot wizard (piwiz) so Pi boots directly without user interaction
echo 'Disabling first-boot wizard...'
systemctl disable userconfig.service || true
systemctl mask userconfig.service || true
rm -f /etc/xdg/autostart/piwiz.desktop || true
rm -f /etc/systemd/system/getty@tty1.service.d/autologin.conf || true

# Create the pi user if it doesn't exist (pi-gen should create it, but ensure it)
if ! id -u pi > /dev/null 2>&1; then
    useradd -m -G sudo,video,audio,bluetooth,netdev,gpio,i2c,spi -s /bin/bash pi
    echo "pi:raspberry" | chpasswd
fi

# Enable root login (Consider removing if not strictly necessary for debugging)
#sed -i 's/.*PermitRootLogin.*/PermitRootLogin yes/g' /etc/ssh/sshd_config

echo 'Making bluetooth accessible without being root...'
# Attempt to set capability but don't fail the build if not permitted (CI chroot may be unprivileged)
if command -v setcap >/dev/null 2>&1; then
  setcap cap_net_raw+eip /usr/bin/python3 || true
fi
usermod -a -G bluetooth pi || true
systemctl restart dbus || true

echo 'Load default wpa_supplicant.conf...'
cat > /etc/wpa_supplicant/wpa_supplicant-wlan0.conf.example <<EOF
country=US
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
p2p_disabled=1

network={
    ssid="YOUR_WIFI_NAME"
    psk="YOUR_WIFI_PASSWORD"
    key_mgmt=WPA-PSK
    # freq_list=2412 2417 2422 2427 2432 2437 2442 2447 2452 2457 2462 # Consider removing freq_list for auto-selection
}
EOF

# Also write to /boot so user can edit before first boot
cat > /boot/wpa_supplicant.conf <<EOF
country=US
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
p2p_disabled=1

network={
    ssid="YOUR_WIFI_NAME"
    psk="YOUR_WIFI_PASSWORD"
    key_mgmt=WPA-PSK
    # freq_list=2412 2417 2422 2427 2432 2437 2442 2447 2452 2457 2462 # Consider removing freq_list for auto-selection
}
EOF

echo 'Disabling apt-daily timers...'
systemctl stop apt-daily.timer
systemctl stop apt-daily-upgrade.timer
systemctl disable apt-daily.timer
systemctl disable apt-daily-upgrade.timer

# revert 'stable' image to have rpt4 wireless firmware
# build 'latest' image with the following lines commented out (required for Pi 400 - see https://github.com/chiefwigms/picobrew_pico/issues/182)
if [[ ${IMG_VARIANT} == "stable" ]]; then
    echo 'Revert to stable WiFi firmware...'
    dpkg --purge firmware-brcm80211
    wget http://archive.raspberrypi.org/debian/pool/main/f/firmware-nonfree/firmware-brcm80211_20190114-1+rpt4_all.deb
    dpkg -i firmware-brcm80211_20190114-1+rpt4_all.deb
    apt-mark hold firmware-brcm80211
    rm firmware-brcm80211_20190114-1+rpt4_all.deb
fi

echo 'Updating packages...'
export DEBIAN_FRONTEND=noninteractive
echo "APT::Acquire::Retries \"5\";" > /etc/apt/apt.conf.d/80-retries
echo "samba-common samba-common/workgroup string WORKGROUP" | debconf-set-selections
echo "samba-common samba-common/dhcp boolean true" | debconf-set-selections
echo "samba-common samba-common/do_debconf boolean true" | debconf-set-selections

apt -y update
apt -y upgrade

# Remove potentially conflicting networking packages (keeping dhcpcd for client management)
echo 'Removing conflicting networking packages (keeping dhcpcd)...'
apt -y --autoremove purge ifupdown isc-dhcp-client isc-dhcp-common rsyslog avahi-daemon
apt-mark hold ifupdown isc-dhcp-client isc-dhcp-common rsyslog raspberrypi-net-mods openresolv avahi-daemon

echo 'Installing required packages...'
# python3-venv removed - not needed for single-purpose device
apt -y install dhcpcd5 libnss-resolve hostapd dnsmasq dnsutils samba git python3 python3-pip nginx openssh-server bluez
systemctl enable dhcpcd

echo 'Installing PicoClaw Server...'
cd /
git clone ${GIT_REPO} picobrew_picoclaw
cd /picobrew_picoclaw

# Create config.yaml from example (config.yaml is gitignored)
cp config.example.yaml config.yaml

# --- CRITICAL FIX FOR ILLEGAL INSTRUCTION ---
# Configure pip to use piwheels.org as PRIMARY source BEFORE installing anything
# This is critical for Pi Zero W (ARMv6) - piwheels MUST be primary, not fallback
mkdir -p /etc/pip.conf.d
cat > /etc/pip.conf <<EOF
[global]
index-url=https://www.piwheels.org/simple
extra-index-url=https://pypi.org/simple
trusted-host = www.piwheels.org
               pypi.org
EOF

# Update pip using the new config
pip3 install --upgrade pip

# Clear pip cache to ensure fresh downloads from piwheels
pip3 cache purge

# Now install requirements - they should come from piwheels
pip3 install -r requirements.txt

# Optionally, force reinstall packages known to cause 'Illegal instruction' if needed
# pip3 uninstall -y eventlet flask-socketio requests
# pip3 install --no-cache-dir --force-reinstall eventlet flask-socketio requests
cd /

echo 'Setting up WiFi AP + Client...'
# Remove any conflicting dhcp config directory
rm -rf /etc/dhcp

# Enable systemd-networkd and systemd-resolved (for managing interfaces and DNS resolution)
systemctl enable systemd-networkd.service systemd-resolved.service

# Setup hostapd for dedicated AP interface (uap0)
cat > /etc/hostapd/hostapd.conf <<EOF
interface=uap0
driver=nl80211
ssid=${AP_SSID}
hw_mode=g
channel=6
ieee80211n=1
wmm_enabled=1
ht_capab=[HT40][SHORT-GI-20][DSSS_CCK-40]
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=${AP_PASS}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF
chmod 600 /etc/hostapd/hostapd.conf

# --- IMPROVED SERVICE FOR HOSTAPD ---
# Define the service more robustly
cat > /etc/systemd/system/picobrew-accesspoint.service <<EOF
[Unit]
Description=PICOBREW access point
After=network-pre.target
Before=hostapd.service
Requires=sys-subsystem-net-devices-wlan0.device
After=sys-subsystem-net-devices-wlan0.device
Wants=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
Environment=IFACE=uap0
ExecStart=/bin/bash -c '/sbin/ip link set wlan0 up && sleep 2 && /sbin/iw dev wlan0 interface add $${IFACE} type __ap && sleep 2 && /sbin/ip addr add ${AP_IP}/24 dev $${IFACE} && /sbin/ip link set $${IFACE} up && /usr/sbin/hostapd -B /etc/hostapd/hostapd.conf && sleep 3 && /usr/sbin/rfkill unblock wlan'
ExecStop=/bin/bash -c 'pkill -f "hostapd" 2>/dev/null || true; /sbin/iw dev $${IFACE} del 2>/dev/null || true; /sbin/ip addr flush dev $${IFACE} 2>/dev/null || true; /sbin/ip link delete $${IFACE} 2>/dev/null || true; /usr/sbin/rfkill unblock wlan 2>/dev/null || true'
TimeoutStartSec=30
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF


# --- CORRECTED DHCP/DNS SETUP ---
# Setup dnsmasq for the AP interface (uap0)
cat > /etc/dnsmasq.conf <<EOF
# Basic Configuration
interface=uap0
bind-interfaces
domain-needed
bogus-priv

# DHCP Configuration for AP Network
dhcp-range=192.168.72.100,192.168.72.200,255.255.255.0,24h
dhcp-option=option:router,${AP_IP}
dhcp-option=option:dns-server,${AP_IP}

# DNS Redirection for PicoBrew
address=/picobrew.com/${AP_IP}
address=/www.picobrew.com/${AP_IP}

# Upstream DNS Servers (fallback if needed, but AP serves its own)
server=8.8.8.8
server=8.8.4.4
server=1.1.1.1

# Local DNS
local=/${AP_SSID}.local/
domain=${AP_SSID}.local
EOF

# Ensure dnsmasq service waits for the AP interface
mkdir -p /etc/systemd/system/dnsmasq.service.d
cat > /etc/systemd/system/dnsmasq.service.d/override.conf <<EOF
[Unit]
After=picobrew-accesspoint.service
Requires=picobrew-accesspoint.service
PartOf=picobrew-accesspoint.service
EOF

# --- CLIENT NETWORK CONFIGURATION ---
# Setup systemd-networkd for wlan0 (client) - Let systemd-networkd manage it
cat > /etc/systemd/network/08-wlan0.network <<EOF
[Match]
Name=wlan0

[Network]
DHCP=yes
# Ensure LLMNR/MulticastDNS don't interfere with dnsmasq if needed on AP side
LLMNR=no
MulticastDNS=no
IPForward=yes # Allow forwarding if needed for AP internet access later
EOF

# Setup systemd-networkd for eth0 (client) - Let systemd-networkd manage it
cat > /etc/systemd/network/04-eth0.network <<EOF
[Match]
Name=eth0

[Network]
DHCP=yes
LLMNR=no
MulticastDNS=no
IPForward=yes # Allow forwarding if needed for AP internet access later
EOF

# --- DHCPDC CONFIGURATION ---
# DO NOT deny wlan0/eth0 in dhcpcd.conf if systemd-networkd manages them.
# dhcpcd should generally handle interfaces *not* managed by systemd-networkd,
# but we've explicitly told systemd-networkd to manage wlan0 and eth0.
# Let systemd-networkd be the primary for these, but ensure dhcpcd doesn't conflict.
# Removing the 'denyinterfaces' lines for wlan0/eth0 from dhcpcd.conf is key.
# We keep the uap0 static config in dhcpcd.conf *if* dhcpcd needs to manage it,
# but since hostapd sets its IP, maybe dhcpcd shouldn't manage uap0 at all.
# Let's remove the uap0 config from dhcpcd.conf entirely, and let hostapd/dnsmasq handle it.
# This simplifies things.

# Add specific configuration for uap0 to tell dhcpcd to ignore it (if necessary, but probably not)
# cat >> /etc/dhcpcd.conf <<EOF
# interface uap0
# static ip_address=${AP_IP}/24
# nohook wpa_supplicant
# EOF

# Instead, ensure dhcpcd doesn't interfere globally less aggressively.
# The default dhcpcd.conf usually works fine alongside systemd-networkd
# if .network files are explicit enough.
# We will not add denyinterfaces lines for wlan0/eth0 here.

# --- RESOLVED CONFIG ---
# Disable resolved's stub listener to free up port 53 if dnsmasq binds to it
# dnsmasq will act as the primary resolver on the AP interface
# This line should already be sufficient
sed -i 's/.*DNSStubListener=.*/DNSStubListener=no/g' /etc/systemd/resolved.conf

# --- WPA_SUPPLICANT CONFIGURATION ---
# Enable wpa_supplicant for the STA interface (wlan0)
# The service file provided by the system should handle the @wlan0 part
systemctl enable wpa_supplicant@wlan0.service

# Update wpa_supplicant config placement service
cat > /etc/systemd/system/update_wpa_supplicant.service <<EOF
[Unit]
Description=Setup wpa_supplicant config for wlan0
Before=wpa_supplicant@wlan0.service
After=systemd-fsck@boot.service # Ensure /boot is mounted

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash -c 'if [ -f /boot/wpa_supplicant.conf ]; then mv /boot/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant-wlan0.conf; else cp /etc/wpa_supplicant/wpa_supplicant-wlan0.conf.example /etc/wpa_supplicant/wpa_supplicant-wlan0.conf 2>/dev/null || echo "Using example wpa_supplicant config, edit /etc/wpa_supplicant/wpa_supplicant-wlan0.conf if needed"; fi'
ExecStartPost=/bin/chmod 600 /etc/wpa_supplicant/wpa_supplicant-wlan0.conf || true

[Install]
WantedBy=multi-user.target
EOF

systemctl enable update_wpa_supplicant.service

echo 'Disabling ipv6...'
cat >> /etc/sysctl.conf <<EOF
net.ipv6.conf.all.disable_ipv6=1
net.ipv6.conf.default.disable_ipv6=1
net.ipv6.conf.lo.disable_ipv6=1
net.ipv6.conf.eth0.disable_ipv6=1
net.ipv6.conf.wlan0.disable_ipv6=1
EOF

# Ensure services are enabled
systemctl enable picobrew-accesspoint.service
systemctl enable dnsmasq.service

echo 'Setting up /etc/hosts...'
cat >> /etc/hosts <<EOF
${AP_IP}       picobrew.com
${AP_IP}       www.picobrew.com
EOF

echo 'Generating self-signed SSL certs...'
mkdir -p /etc/nginx/ssl # Use a more standard location
cat > /tmp/req.cnf <<EOF
[v3_req]
keyUsage = critical, digitalSignature, keyAgreement
extendedKeyUsage = serverAuth
subjectAltName = @alt_names
[alt_names]
DNS.1 = picobrew.com
DNS.2 = www.picobrew.com
DNS.3 = localhost
IP.1 = 127.0.0.1
IP.2 = ${AP_IP}
EOF

openssl req -x509 -sha256 -newkey rsa:2048 -nodes -keyout /etc/nginx/ssl/domain.key -days 1825 -out /etc/nginx/ssl/domain.crt -subj "/CN=PicobrewPicoClaw_CA" < /dev/null
openssl req -newkey rsa:2048 -nodes -subj "/CN=picobrew.com" -keyout /etc/nginx/ssl/server.key -out /tmp/server.csr < /dev/null
openssl x509 -req -in /tmp/server.csr -CA /etc/nginx/ssl/domain.crt -CAkey /etc/nginx/ssl/domain.key -CAcreateserial -out /etc/nginx/ssl/server.crt -days 1825 -extfile /tmp/req.cnf -extensions v3_req
cat /etc/nginx/ssl/server.crt /etc/nginx/ssl/domain.crt > /etc/nginx/ssl/bundle.crt
rm /tmp/req.cnf /tmp/server.csr # Clean up temporary files

echo 'Setting up nginx for http and https...'
# Assuming the picobrew.com.conf file exists in the cloned repo
NGINX_CONF_PATH="/picobrew_picoclaw/scripts/pi/picobrew.com.conf"
if [ -f "$NGINX_CONF_PATH" ]; then
    ln -sf "$NGINX_CONF_PATH" /etc/nginx/sites-available/picobrew.com.conf
    ln -sf /etc/nginx/sites-available/picobrew.com.conf /etc/nginx/sites-enabled/picobrew.com.conf
    rm -f /etc/nginx/sites-enabled/default # Remove default site
    systemctl enable nginx # Ensure nginx is enabled
else
    echo "Warning: Nginx configuration file $NGINX_CONF_PATH not found!"
fi

echo 'Setup samba config...'
cat > /etc/samba/smb.conf <<EOF
[global]
workgroup = WORKGROUP
server string = Samba Server %v
netbios name = PICOCALW_SRV
security = user
map to guest = bad user
guest account = nobody
dns proxy = no
# Logging
log file = /var/log/samba/log.%m
max log size = 1000
logging = file

[App]
path = /picobrew_picoclaw
valid users = @users
guest ok = yes
browseable = yes
public = yes
writable = yes
write list = @users

[Recipes]
path = /picobrew_picoclaw/app/recipes
valid users = @users
guest ok = yes
browseable = yes
public = yes
writable = yes
write list = @users

[History]
path = /picobrew_picoclaw/app/sessions
valid users = @users
guest ok = yes
browseable = yes
public = yes
writable = yes
write list = @users
EOF

# Restart samba services
systemctl enable smbd nmbd

# --- RC.LOCAL MODIFICATIONS ---
# Simplified rc.local, focusing on server startup and post-git-update logic
# Networking setup is handled by systemd services now
cat > /etc/rc.local <<EOF
#!/bin/bash
# /etc/rc.local - Executed after all multi-user services are started

echo "Starting PicoClaw post-boot sequence..."

# Load environment variables (example values, adjust if needed)
export IMG_RELEASE="${IMG_RELEASE}"
export IMG_VARIANT="${IMG_VARIANT}"

# Toggle off WiFi power management (helpful for AP stability)
iw wlan0 set power_save off 2>/dev/null || true

# Enable IP forwarding (might be needed depending on desired AP internet access)
sysctl -w net.ipv4.ip_forward=1 2>/dev/null || true

# Post-git-update logic (if enabled in config)
if [ -f "/picobrew_picoclaw/config.yaml" ] && grep -q "update_boot:\s*[tT]rue" "/picobrew_picoclaw/config.yaml"; then
  echo 'Checking for PicoClaw Server updates...'
  cd /picobrew_picoclaw
  git fetch origin
  LOCAL=$(git rev-parse HEAD)
  REMOTE=$(git rev-parse origin/HEAD)
  if [ $LOCAL != $REMOTE ]; then
      echo "Updates found, pulling..."
      git pull origin HEAD || echo "Git pull failed, continuing with current version."
      # Reinstall Python deps if needed after update (optional, depends on changes)
      # pip3 install -r requirements.txt
      # Run post-update script if it exists
      ./scripts/pi/post-git-update.sh 2>&1 | logger -t picoclaw-update
  else
      echo "No updates found."
  fi
  cd /
fi

# Start the main Python server
echo "Starting PicoClaw Server (image: \${IMG_RELEASE}_\${IMG_VARIANT})..."
cd /picobrew_picoclaw
# Log server output
nohup python3 server.py 0.0.0.0 8080 > /var/log/picoclaw_server.log 2>&1 &
SERVER_PID=$!
echo "PicoClaw Server started with PID: \$SERVER_PID"

# Wait a moment to check if the server started successfully
sleep 5
if kill -0 \$SERVER_PID 2>/dev/null; then
    echo "PicoClaw Server confirmed running (PID: \$SERVER_PID)."
    logger -t picoclaw-boot "PicoClaw Server started successfully (PID: \$SERVER_PID)"
else
    echo "Warning: PicoClaw Server may have failed to start. Check /var/log/picoclaw_server.log"
    logger -t picoclaw-boot "PicoClaw Server failed to start. Check /var/log/picoclaw_server.log"
    # Optionally, tail the last few lines of the log here
    tail -n 20 /var/log/picoclaw_server.log
fi

# End of rc.local
exit 0
EOF

chmod +x /etc/rc.local

# Ensure rc-local.service is enabled so rc.local runs on boot
systemctl enable rc-local.service || true

echo 'Finished custom pi setup!'