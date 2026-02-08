#!/bin/bash
# AP for Pico devices - Pi Zero W STA+AP using bridge (br0) and ap@wlan0
# Target: Raspberry Pi OS Bookworm (Debian 12, 32-bit)
# SSID Must be > 8 Chars
AP_IP="192.168.72.1"
AP_SSID="PICOBREW"
AP_PASS="PICOBREW"

export IMG_NAME="PICOBREW_PICOCLAW"
export IMG_RELEASE="beta7"
export IMG_VARIANT="${IMG_VARIANT:-latest}" # Default to 'latest' if not set by YAML
export GIT_SHA="image-build-${IMG_RELEASE}"

# GitHub repository (overrideable)
GIT_REPO="${GIT_REPO:-https://github.com/Moinster/PicoBrew_PicoClaw.git}"

# === 1. Disable first-boot wizard (if present in Bookworm image) ===
echo 'Disabling first-boot wizard (if applicable)...'
systemctl disable userconfig.service || true
systemctl disable networking.service || true
systemctl mask networking.service || true
systemctl enable systemd-networkd systemd-resolved
systemctl mask userconfig.service || true
rm -f /etc/xdg/autostart/piwiz.desktop || true
rm -f /etc/systemd/system/getty@tty1.service.d/autologin.conf || true

# Ensure pi user exists (pi-gen usually creates it, but safe to ensure)
if ! id -u pi >/dev/null 2>&1; then
    useradd -m -G sudo,video,audio,bluetooth,netdev,gpio,i2c,spi -s /bin/bash pi
    echo "pi:raspberry" | chpasswd
fi

# === 2. Bluetooth & UART ===
echo 'Making bluetooth accessible without being root...'
if command -v setcap >/dev/null 2>&1; then
    # Attempt setcap (may fail in chroot, which is okay)
    setcap cap_net_raw+eip /usr/bin/python3 || true
fi
usermod -a -G bluetooth pi || true
systemctl restart dbus || true

cat >> /boot/config.txt <<EOF
enable_uart=1
EOF

# === 3. wpa_supplicant example config (for /boot & /etc) ===
cat > /boot/wpa_supplicant.conf <<EOF
country=US
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
p2p_disabled=1

network={
    ssid="YOUR_WIFI_NAME"
    psk="YOUR_WIFI_PASSWORD"
    key_mgmt=WPA-PSK
}
EOF

# Copy to /etc as fallback (will be replaced by update_wpa_supplicant.service if /boot exists)
cp /boot/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant-wlan0.conf.example

# === 4. Disable apt timers (optional, good practice) ===
echo 'Disabling apt-daily timers...'
systemctl stop apt-daily.timer apt-daily-upgrade.timer
systemctl disable apt-daily.timer apt-daily-upgrade.timer

# === 5. (Removed) WiFi firmware (Bookworm ships modern firmware) ===
# The old stable/latest logic for firmware-brcm80211 is removed.
# Bookworm's default firmware should be sufficient for Pi Zero W AP mode.

# === 6. Update & install core packages — REMOVE dhcpcd5! ===
echo 'Updating packages...'
export DEBIAN_FRONTEND=noninteractive
echo "APT::Acquire::Retries \"5\";" > /etc/apt/apt.conf.d/80-retries
echo "samba-common samba-common/workgroup string WORKGROUP" | debconf-set-selections
echo "samba-common samba-common/dhcp boolean true" | debconf-set-selections
echo "samba-common samba-common/do_debconf boolean true" | debconf-set-selections

apt -y update
# Consider using --no-install-recommends for some packages to reduce deps if needed
apt -y upgrade

# CRITICAL: Remove dhcpcd5 and all conflicting net tools (same as Bullseye)
echo 'Purging dhcpcd5 and legacy networking...'
apt -y --autoremove purge \
    ifupdown dhcpcd5 isc-dhcp-client isc-dhcp-common rsyslog avahi-daemon libnss-mdns
apt-mark hold \
    ifupdown dhcpcd5 isc-dhcp-client isc-dhcp-common rsyslog raspberrypi-net-mods openresolv avahi-daemon libnss-mdns

echo 'Installing required packages...'
# Use --no-install-recommends for network-related packages to avoid potential faulty deps like crda
apt -y install --no-install-recommends \
    libnss-resolve hostapd dnsmasq dnsutils samba git python3 python3-pip nginx openssh-server bluez

systemctl enable systemd-networkd systemd-resolved

# === 7. Install PicoClaw Server ===
# PicoClaw files are copied later by pi-gen (stage files/)
# Do not access /picobrew_picoclaw during chroot





# === 8. pip: FORCE piwheels as primary (ARMv6/v7 fix for Bookworm) ===
mkdir -p /etc/pip.conf.d
cat > /etc/pip.conf <<EOF
[global]
index-url=https://www.piwheels.org/simple
extra-index-url=https://pypi.org/simple
trusted-host = www.piwheels.org pypi.org
EOF

pip3 install --upgrade pip
pip3 cache purge
pip3 install -r requirements.txt

# Optional: force-reinstall known problematic packages (if still seeing illegal instr later)
# pip3 uninstall -y eventlet flask-socketio requests
# pip3 install --no-cache-dir --force-reinstall eventlet flask-socketio requests

cd /

# === 9. Networking: Bridge + Virtual Interface (ap@wlan0) ===

# 9.1 NetDev: bridge br0
cat > /etc/systemd/network/02-br0.netdev <<EOF
[NetDev]
Name=br0
Kind=bridge
EOF

cat > /etc/systemd/network/03-br0.network <<EOF
[Match]
Name=br0

[Network]
Address=${AP_IP}/24
IPForward=yes
IPMasquerade=yes
DHCPServer=no
EOF


# 9.2 wlan0 joins bridge (STA interface)
cat > /etc/systemd/network/08-wlan0.network <<EOF
[Match]
Name=wlan0

[Network]
Bridge=br0
DHCP=yes
IPv6AcceptRA=no
LLMNR=no
MulticastDNS=no
EOF

# 9.3 eth0 (optional wired client) joins bridge
cat > /etc/systemd/network/04-eth0.network <<EOF
[Match]
Name=eth0
[Network]
Bridge=br0
ConfigureWithoutCarrier=yes
EOF

# 9.4 br0 gets AP IP
cat > /etc/systemd/network/16-br0_up.network <<EOF
[Match]
Name=br0
[Network]
Address=${AP_IP}/24
IPMasquerade=yes
EOF

# === 10. hostapd config (binds to ap@wlan0, bridges to br0) ===
cat > /etc/hostapd/hostapd.conf <<EOF
driver=nl80211
ssid=${AP_SSID}
country_code=US
hw_mode=g
channel=6
auth_algs=1
wpa=2
wpa_passphrase=${AP_PASS}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
bridge=br0
EOF
chmod 600 /etc/hostapd/hostapd.conf

# Bookworm requires /etc/default/hostapd to exist
cat > /etc/default/hostapd <<EOF
DAEMON_CONF="/etc/hostapd/hostapd.conf"
EOF

# === 11. Instance-based accesspoint@.service (runs on target) ===
cat > /etc/systemd/system/accesspoint@.service <<EOF
[Unit]
Description=Access point for %I
After=sys-subsystem-net-devices-%i.device systemd-networkd.service
Requires=sys-subsystem-net-devices-%i.device
Wants=br0.network

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/bin/ip link set %i up
ExecStartPre=/usr/sbin/iw dev %i interface add ap@%i type __ap
ExecStart=/usr/sbin/hostapd -i ap@%i /etc/hostapd/hostapd.conf
ExecStopPost=-/usr/sbin/iw dev ap@%i del

[Install]
WantedBy=multi-user.target
EOF

# Mask the default hostapd.service to prevent conflicts
systemctl mask hostapd.service 2>/dev/null || true
# Do NOT enable accesspoint@wlan0.service here in chroot

# === 12. Bind wpa_supplicant@wlan0 to accesspoint@wlan0 (runs on target) ===
mkdir -p /etc/systemd/system/wpa_supplicant@wlan0.service.d
cat > /etc/systemd/system/wpa_supplicant@wlan0.service.d/override.conf <<EOF
[Unit]
Before=accesspoint@wlan0.service
BindsTo=accesspoint@wlan0.service

[Service]
ExecStartPost=/usr/bin/rfkill unblock wlan
EOF
# Do NOT enable wpa_supplicant@wlan0.service here in chroot

# === 13. dnsmasq: serve DHCP/DNS on br0 (runs on target) ===
cat > /etc/dnsmasq.conf <<EOF
interface=br0
bind-interfaces
domain=picobrew.local
address=/picobrew.com/${AP_IP}
address=/www.picobrew.com/${AP_IP}
server=8.8.8.8
server=8.8.4.4
server=1.1.1.1
dhcp-range=192.168.72.100,192.168.72.200,255.255.255.0,24h
dhcp-option=option:router,${AP_IP}
dhcp-option=option:dns-server,${AP_IP}
EOF

# Ensure dnsmasq starts after br0 is up and accesspoint is running
mkdir -p /etc/systemd/system/dnsmasq.service.d
cat > /etc/systemd/system/dnsmasq.service.d/override.conf <<EOF
[Unit]
After=br0.network accesspoint@wlan0.service
Requires=br0.network accesspoint@wlan0.service
EOF

# Enable dnsmasq for SysV compatibility in the final image using update-rc.d (safe in chroot)
update-rc.d dnsmasq defaults

# === 14. Disable IPv6 ===
cat >> /etc/sysctl.conf <<EOF
net.ipv6.conf.all.disable_ipv6=1
net.ipv6.conf.default.disable_ipv6=1
net.ipv6.conf.lo.disable_ipv6=1
net.ipv6.conf.wlan0.disable_ipv6=1
net.ipv6.conf.eth0.disable_ipv6=1
EOF
sysctl -p >/dev/null 2>&1

# === 15. systemd-resolved (Bookworm-safe) ===
sed -i 's/^#*DNSStubListener=.*/DNSStubListener=no/' /etc/systemd/resolved.conf

# Use resolved-managed resolv.conf (NOT stub, not runtime)
ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf

systemctl enable systemd-resolved


# === 16. wpa_supplicant config loader (runs on target) ===
cat > /etc/systemd/system/update_wpa_supplicant.service <<EOF
[Unit]
Description=Copy wpa_supplicant.conf from /boot if present
ConditionPathExists=/boot/wpa_supplicant.conf
After=systemd-fsck@boot.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/mv /boot/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
ExecStartPost=/bin/chmod 600 /etc/wpa_supplicant/wpa_supplicant-wlan0.conf

[Install]
WantedBy=multi-user.target
EOF
# Enable update_wpa_supplicant.service for the target system.
# Simulate systemctl enable using symlinks in chroot.
ln -sf /etc/systemd/system/update_wpa_supplicant.service /etc/systemd/system/multi-user.target.wants/update_wpa_supplicant.service

# === 16.5 Enable networking services for target boot ===
systemctl enable wpa_supplicant@wlan0
systemctl enable accesspoint@wlan0
systemctl enable dnsmasq

# === 17. Hosts file ===
cat >> /etc/hosts <<EOF
${AP_IP}       picobrew.com
${AP_IP}       www.picobrew.com
EOF

# === 18. SSL Certificates ===
mkdir -p /etc/nginx/ssl
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

openssl req -x509 -sha256 -newkey rsa:2048 -nodes \
  -keyout /etc/nginx/ssl/domain.key -days 1825 \
  -out /etc/nginx/ssl/domain.crt \
  -subj "/CN=PicobrewPicoClaw_CA" < /dev/null

openssl req -newkey rsa:2048 -nodes \
  -subj "/CN=picobrew.com" \
  -keyout /etc/nginx/ssl/server.key \
  -out /tmp/server.csr < /dev/null

openssl x509 -req -in /tmp/server.csr \
  -CA /etc/nginx/ssl/domain.crt -CAkey /etc/nginx/ssl/domain.key -CAcreateserial \
  -out /etc/nginx/ssl/server.crt -days 1825 -extfile /tmp/req.cnf -extensions v3_req

cat /etc/nginx/ssl/server.crt /etc/nginx/ssl/domain.crt > /etc/nginx/ssl/bundle.crt
rm -f /tmp/req.cnf /tmp/server.csr

# === 19. Nginx ===
NGINX_CONF="/picobrew_picoclaw/scripts/pi/picobrew.com.conf"
if [ -f "$NGINX_CONF" ]; then
    ln -sf "$NGINX_CONF" /etc/nginx/sites-available/picobrew.com.conf
    ln -sf /etc/nginx/sites-available/picobrew.com.conf /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    systemctl enable nginx
else
    echo "⚠️ Warning: Nginx config not found at $NGINX_CONF"
fi

# === 20. Samba ===
cat > /etc/samba/smb.conf <<EOF
[global]
workgroup = WORKGROUP
server string = Samba Server %v
netbios name = PICOCALW_SRV
security = user
map to guest = bad user
guest account = nobody
dns proxy = no
log file = /var/log/samba/log.%m
max log size = 1000
logging = file

[App]
path = /picobrew_picoclaw
guest ok = yes
browseable = yes
public = yes
writable = yes
write list = @users

[Recipes]
path = /picobrew_picoclaw/app/recipes
guest ok = yes
browseable = yes
public = yes
writable = yes
write list = @users

[History]
path = /picobrew_picoclaw/app/sessions
guest ok = yes
browseable = yes
public = yes
writable = yes
write list = @users
EOF
# Enable samba services for the target system using update-rc.d
update-rc.d smbd defaults
update-rc.d nmbd defaults

# === 21. rc.local (final boot actions) ===
cat > /etc/rc.local <<'EOF'
#!/bin/bash
# rc.local — runs after all services

set -e # Exit on any error

echo "[rc.local] Starting PicoClaw post-boot sequence..."

# Ensure config.yaml exists
if [ ! -f /picobrew_picoclaw/config.yaml ]; then
    if [ -f /picobrew_picoclaw/config.example.yaml ]; then
        cp /picobrew_picoclaw/config.example.yaml /picobrew_picoclaw/config.yaml
        chown pi:pi /picobrew_picoclaw/config.yaml
        echo "[rc.local] Created config.yaml from example"
    else
        echo "[rc.local] ❌ config.example.yaml missing!"
    fi
fi

VENV_DIR="/opt/picoclaw-venv"
FIRST_BOOT_VENV="/var/lib/picoclaw_venv_ready"

if [ ! -f "$FIRST_BOOT_VENV" ]; then
    echo "[rc.local] Creating Python virtualenv..."
    python3 -m venv "$VENV_DIR"

    echo "[rc.local] Upgrading pip..."
    "$VENV_DIR/bin/pip" install --upgrade pip

    echo "[rc.local] Installing Python requirements..."
    "$VENV_DIR/bin/pip" install --no-cache-dir -r /picobrew_picoclaw/requirements.txt

    touch "$FIRST_BOOT_VENV"
    echo "[rc.local] Virtualenv ready."
fi


# Ensure systemd manager configuration is up-to-date (optional, might help in rare cases)
systemctl daemon-reload 2>/dev/null || true # Ignore errors in rc.local if systemctl unavailable momentarily

# Power save off (critical for stability)
iw wlan0 set power_save off 2>/dev/null || true
# Check if ap@wlan0 exists before trying to set power_save
if ip link show ap@wlan0 >/dev/null 2>&1; then
    iw ap@wlan0 set power_save off 2>/dev/null || true
fi

# Optional: On first boot, force reinstall Python packages from piwheels to ensure ARMv6 compatibility
# This helps mitigate "Illegal instruction" errors if packages were installed incorrectly during build.
FIRST_BOOT_MARKER="/var/lib/picoclaw_first_boot_done"
if [ ! -f "$FIRST_BOOT_MARKER" ]; then
    echo "[rc.local] First boot detected. Verifying Python packages..."
    cd /picobrew_picoclaw
    # Purge pip cache and force reinstall requirements from piwheels
    sudo -u pi pip3 cache purge
    sudo -u pi pip3 install --no-cache-dir --force-reinstall -r requirements.txt
    # Create marker file to prevent reinstall on subsequent boots
    touch "$FIRST_BOOT_MARKER"
    echo "[rc.local] Python packages verified/reinstalled."
fi

# Optional: auto-update (if enabled in config.yaml) - ensure internet access first
if [ -f "/picobrew_picoclaw/config.yaml" ] && grep -q "update_boot:\s*[tT]rue" "/picobrew_picoclaw/config.yaml"; then
    echo "[rc.local] Checking for updates (requires internet access)..."
    # Simple connectivity check (adjust host if needed)
    if ping -c 1 8.8.8.8 -W 10; then
        cd /picobrew_picoclaw
        git fetch origin
        if ! git diff --quiet HEAD origin/HEAD; then
            echo "[rc.local] Updating code..."
            git pull origin HEAD || echo "[rc.local] Git pull failed — continuing with current version."
            # Reinstall Python deps if code changed significantly (optional)
            # sudo -u pi pip3 install -r requirements.txt
            ./scripts/pi/post-git-update.sh 2>&1 | logger -t picoclaw-update
        else
            echo "[rc.local] No updates found."
        fi
        cd /
    else
        echo "[rc.local] No internet connectivity detected, skipping update check."
    fi
fi

# Start server.py — log to file
export IMG_RELEASE="${IMG_RELEASE:-beta7}" # Provide default if not set during build
export IMG_VARIANT="${IMG_VARIANT:-latest}" # Provide default if not set during build
export SOURCE_SHA="${GIT_SHA:-unknown}"    # Provide default if not set during build

echo "[rc.local] Starting PicoClaw Server (img: ${IMG_RELEASE}_${IMG_VARIANT}, src: ${SOURCE_SHA})..."
cd /picobrew_picoclaw
# Use nohup and redirect output to a log file
#nohup python3 server.py 0.0.0.0 8080 > /var/log/picoclaw_server.log 2>&1 &
"$VENV_DIR/bin/python" /picobrew_picoclaw/server.py 0.0.0.0 8080 \
  > /var/log/picoclaw_server.log 2>&1 &
SERVER_PID=$!
echo "[rc.local] Server started with PID $SERVER_PID."

# Log the outcome
if kill -0 "$SERVER_PID" 2>/dev/null; then
    logger -t picoclaw-boot "✅ Server started successfully (PID $SERVER_PID). Check /var/log/picoclaw_server.log if needed."
    echo "[rc.local] Server confirmed running."
else
    logger -t picoclaw-boot "❌ Server failed to start (PID $SERVER_PID died quickly). Check /var/log/picoclaw_server.log."
    echo "[rc.local] ERROR: Server may have failed to start. Check /var/log/picoclaw_server.log"
    # Optionally, tail the last few lines of the log here for immediate feedback in rc.local output
    tail -n 10 /var/log/picoclaw_server.log 2>/dev/null | logger -t picoclaw-boot-log-tail
fi

exit 0
EOF

chmod +x /etc/rc.local

# Enable rc-local.service for the TARGET system using update-rc.d (safe in chroot)
update-rc.d rc.local defaults

# === 22. Final cleanup ===
echo '✅ Finished custom pi setup! (Bookworm version)'