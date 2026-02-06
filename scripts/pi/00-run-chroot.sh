#!/bin/bash
# AP for Pico devices — Pi Zero W STA+AP using bridge (br0) and ap@wlan0
# SSID Must be > 8 Chars
AP_IP="192.168.72.1"
AP_SSID="PICOBREW"
AP_PASS="PICOBREW"

export IMG_NAME="PICOBREW_PICOCLAW"
export IMG_RELEASE="beta7"
export IMG_VARIANT="${IMG_VARIANT:-latest}"
export GIT_SHA='$(git rev-parse --short HEAD)'

# GitHub repository (overrideable)
GIT_REPO="${GIT_REPO:-https://github.com/Moinster/PicoBrew_PicoClaw.git}"

# === 1. Disable first-boot wizard ===
echo 'Disabling first-boot wizard...'
systemctl disable userconfig.service || true
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

# === 4. Disable apt timers ===
echo 'Disabling apt-daily timers...'
systemctl stop apt-daily.timer apt-daily-upgrade.timer
systemctl disable apt-daily.timer apt-daily-upgrade.timer

# === 5. WiFi firmware (optional stable revert) ===
if [[ "${IMG_VARIANT}" == "stable" ]]; then
    echo 'Reverting to stable WiFi firmware (rpt4)...'
    dpkg --purge firmware-brcm80211 || true
    wget -q http://archive.raspberrypi.org/debian/pool/main/f/firmware-nonfree/firmware-brcm80211_20190114-1+rpt4_all.deb
    dpkg -i firmware-brcm80211_20190114-1+rpt4_all.deb
    apt-mark hold firmware-brcm80211
    rm -f firmware-brcm80211_20190114-1+rpt4_all.deb
fi

# === 6. Update & install core packages — REMOVE dhcpcd5! ===
echo 'Updating packages...'
export DEBIAN_FRONTEND=noninteractive
echo "APT::Acquire::Retries \"5\";" > /etc/apt/apt.conf.d/80-retries
echo "samba-common samba-common/workgroup string WORKGROUP" | debconf-set-selections
echo "samba-common samba-common/dhcp boolean true" | debconf-set-selections
echo "samba-common samba-common/do_debconf boolean true" | debconf-set-selections

apt -y update
apt -y upgrade

# 🔥 CRITICAL: Remove dhcpcd5 and all conflicting net tools
echo 'Purging dhcpcd5 and legacy networking...'
apt -y --autoremove purge \
    ifupdown dhcpcd5 isc-dhcp-client isc-dhcp-common rsyslog avahi-daemon libnss-mdns
apt-mark hold \
    ifupdown dhcpcd5 isc-dhcp-client isc-dhcp-common rsyslog raspberrypi-net-mods openresolv avahi-daemon libnss-mdns

echo 'Installing required packages...'
apt -y install \
    libnss-resolve hostapd dnsmasq dnsutils samba git python3 python3-pip nginx openssh-server bluez

systemctl enable systemd-networkd systemd-resolved

# === 7. Install PicoClaw Server ===
cd /
git clone "${GIT_REPO}" picobrew_picoclaw
cd /picobrew_picoclaw

cp config.example.yaml config.yaml

# === 8. pip: FORCE piwheels as primary (ARMv6 fix) ===
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

# Optional: force-reinstall known problematic packages (if still seeing illegal instr)
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

# 9.2 wlan0 joins bridge (STA interface)
cat > /etc/systemd/network/08-wlan0.network <<EOF
[Match]
Name=wlan0
[Network]
Bridge=br0
LLMNR=no
MulticastDNS=no
IPForward=yes
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

# === 11. Instance-based accesspoint@.service ===
cat > /etc/systemd/system/accesspoint@.service <<EOF
[Unit]
Description=Access point for %I
Wants=wpa_supplicant@%i.service
After=systemd-networkd.service
Before=dnsmasq.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/sbin/iw dev %i interface add ap@%i type __ap
ExecStart=/usr/sbin/hostapd -i ap@%i /etc/hostapd/hostapd.conf
ExecStopPost=-/sbin/iw dev ap@%i del
ExecStopPost=/usr/sbin/rfkill unblock wlan

[Install]
WantedBy=sys-subsystem-net-devices-%i.device
EOF

# Disable default hostapd.service
systemctl disable hostapd.service

# Enable our instance service for wlan0
systemctl enable accesspoint@wlan0.service

# === 12. Bind wpa_supplicant@wlan0 to accesspoint@wlan0 ===
mkdir -p /etc/systemd/system/wpa_supplicant@wlan0.service.d
cat > /etc/systemd/system/wpa_supplicant@wlan0.service.d/override.conf <<EOF
[Unit]
BindsTo=accesspoint@wlan0.service
After=accesspoint@wlan0.service

[Service]
ExecStartPost=/bin/ip link set ap@wlan0 up
ExecStartPost=/usr/sbin/rfkill unblock wlan
EOF

# === 13. dnsmasq: serve DHCP/DNS on br0 ===
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

# Ensure dnsmasq starts after br0 is up
mkdir -p /etc/systemd/system/dnsmasq.service.d
cat > /etc/systemd/system/dnsmasq.service.d/override.conf <<EOF
[Unit]
After=accesspoint@wlan0.service br0.network
Requires=accesspoint@wlan0.service
EOF

systemctl enable dnsmasq

# === 14. Disable IPv6 ===
cat >> /etc/sysctl.conf <<EOF
net.ipv6.conf.all.disable_ipv6=1
net.ipv6.conf.default.disable_ipv6=1
net.ipv6.conf.lo.disable_ipv6=1
net.ipv6.conf.wlan0.disable_ipv6=1
net.ipv6.conf.eth0.disable_ipv6=1
EOF
sysctl -p >/dev/null 2>&1

# === 15. Disable resolved stub listener ===
sed -i 's/^#*DNSStubListener=.*/DNSStubListener=no/' /etc/systemd/resolved.conf
ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf

# === 16. wpa_supplicant config loader (from /boot) ===
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
systemctl enable update_wpa_supplicant.service

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
    echo " Warning: Nginx config not found at $NGINX_CONF"
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
systemctl enable smbd nmbd

# === 21. rc.local (final boot actions) ===
cat > /etc/rc.local <<'EOF'
#!/bin/bash
# rc.local — runs after all services

set -e

echo "[rc.local] Starting PicoClaw post-boot..."

# Ensure network is ready
systemctl daemon-reload
sleep 2

# Power save off (critical for stability)
iw wlan0 set power_save off 2>/dev/null || true
iw ap@wlan0 set power_save off 2>/dev/null || true

# Optional: auto-update (if enabled in config.yaml)
if [ -f "/picobrew_picoclaw/config.yaml" ] && grep -q "update_boot:\s*[tT]rue" "/picobrew_picoclaw/config.yaml"; then
    echo "[rc.local] Checking for updates..."
    cd /picobrew_picoclaw
    git fetch origin
    if ! git diff --quiet HEAD origin/HEAD; then
        echo "[rc.local] Updating code..."
        git pull origin HEAD || echo "Git pull failed — continuing with current version."
        pip3 install -r requirements.txt
        ./scripts/pi/post-git-update.sh 2>&1 | logger -t picoclaw-update
    fi
    cd /
fi

# Start server.py — log to file
export IMG_RELEASE="${IMG_RELEASE}"
export IMG_VARIANT="${IMG_VARIANT}"
export SOURCE_SHA="${GIT_SHA}"

echo "[rc.local] Starting PicoClaw Server (img: ${IMG_RELEASE}_${IMG_VARIANT}, src: ${SOURCE_SHA})..."
cd /picobrew_picoclaw
nohup python3 server.py 0.0.0.0 8080 > /var/log/picoclaw_server.log 2>&1 &
SERVER_PID=$!
echo "[rc.local] Server PID: $SERVER_PID"

# Verify it's running
sleep 3
if kill -0 "$SERVER_PID" 2>/dev/null; then
    logger -t picoclaw-boot " Server started (PID $SERVER_PID)"
else
    logger -t picoclaw-boot " Server failed to start — check /var/log/picoclaw_server.log"
    tail -n 20 /var/log/picoclaw_server.log | logger -t picoclaw-boot
fi

exit 0
EOF

chmod +x /etc/rc.local
systemctl enable rc-local.service

# === 22. Final cleanup ===
echo ' Finished custom pi setup!'