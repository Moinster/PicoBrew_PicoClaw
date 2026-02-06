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

# Enable root login
#sed -i 's/.*PermitRootLogin.*/PermitRootLogin yes/g' /etc/ssh/sshd_config

# echo 'Enabling serial console support...'
cat >> /boot/config.txt <<EOF
enable_uart=1
EOF

echo 'Making bluetooth accessible without being root...'
# Attempt to set capability but don't fail the build if not permitted (CI chroot may be unprivileged)
if command -v setcap >/dev/null 2>&1; then
  # try best-effort; some CI runners disallow CAP_SETFCAP and will return non-zero
  # Use python3 (Bullseye has Python 3.9, not 3.7)
  setcap cap_net_raw+eip /usr/bin/python3 || true
fi
usermod -a -G bluetooth pi || true
systemctl restart dbus || true

echo 'Load default wpa_supplicant.conf...'
cat > /boot/wpa_supplicant.conf <<EOF
country=US
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
p2p_disabled=1

network={
    ssid="YOUR_WIFI_NAME"
    psk="YOUR_WIFI_PASSWORD"
    key_mgmt=WPA-PSK
    freq_list=2412 2417 2422 2427 2432 2437 2442 2447 2452 2457 2462
}
EOF

echo 'Disabling apt-daily timers...'
systemctl stop apt-daily.timer
systemctl stop apt-daily-upgrade.timer
systemctl disable apt-daily.timer
systemctl disable apt-daily-upgrade.timer

# revert 'stable' image to have rpt4 wireless firmware
# build 'latest' image with the following lines commented out (required for Pi 400 - see https://github.com/chiefwigms/picobrew_pico/issues/182)
if [[ ${IMG_VARIANT} == "stable" ]];
then
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

# https://raspberrypi.stackexchange.com/questions/89803/access-point-as-wifi-router-repeater-optional-with-bridge
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

# Configure pip to use piwheels.org for Raspberry Pi compatible wheels (ARMv6/v7/v8)
# This is critical for Pi Zero W (ARMv6) compatibility
mkdir -p /etc/pip.conf.d
cat > /etc/pip.conf <<EOF
[global]
extra-index-url=https://www.piwheels.org/simple
EOF

# Install Python packages - piwheels provides pre-built ARMv6 wheels
pip3 install --upgrade pip
pip3 install -r requirements.txt
# Force reinstall packages known to cause 'Illegal instruction' from piwheels
pip3 uninstall -y eventlet flask-socketio requests
pip3 install --no-cache-dir --force-reinstall eventlet flask-socketio requests
cd /

echo 'Setting up WiFi AP + Client...'
rm -rf /etc/dhcp

systemctl enable systemd-networkd.service systemd-resolved.service

# Setup hostapd for dedicated AP interface (uap0)
cat > /etc/hostapd/hostapd.conf <<EOF
interface=uap0
driver=nl80211
ssid=${AP_SSID}
hw_mode=g
channel=6
wpa=2
wpa_passphrase=${AP_PASS}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF
chmod 600 /etc/hostapd/hostapd.conf

cat > /etc/systemd/system/picobrew-accesspoint.service <<EOF
[Unit]
Description=PICOBREW access point
After=network.target dhcpcd.service sys-subsystem-net-devices-wlan0.device
Wants=network.target dhcpcd.service

[Service]
Type=simple
ExecStartPre=/bin/sleep 3
ExecStartPre=/sbin/ip link set wlan0 up
ExecStartPre=/sbin/iw dev wlan0 interface add uap0 type __ap
ExecStart=/usr/sbin/hostapd /etc/hostapd/hostapd.conf
ExecStartPost=/usr/sbin/rfkill unblock wlan
ExecStopPost=-/sbin/iw dev uap0 del
ExecStopPost=/usr/sbin/rfkill unblock wlan
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable picobrew-accesspoint.service

# Enable wpa_supplicant for the STA interface
systemctl enable wpa_supplicant@wlan0.service
rm -f /etc/wpa_supplicant/wpa_supplicant.conf

cat > /etc/systemd/system/update_wpa_supplicant.service <<EOF
[Unit]
Description=Setup wpa_supplicant config for wlan0
Before=wpa_supplicant@wlan0.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash -c 'if [ -f /boot/wpa_supplicant.conf ]; then mv /boot/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant-wlan0.conf; else cp /etc/wpa_supplicant/wpa_supplicant-wlan0.conf.example /etc/wpa_supplicant/wpa_supplicant-wlan0.conf 2>/dev/null || echo "Place your wpa_supplicant.conf on /boot before first boot"; fi'
ExecStartPost=/bin/chmod 600 /etc/wpa_supplicant/wpa_supplicant-wlan0.conf || true

[Install]
WantedBy=multi-user.target
EOF

# Create a fallback example config in /etc so users can copy it to /boot if needed
cp /boot/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant-wlan0.conf.example

systemctl enable update_wpa_supplicant.service

# Setup systemd-networkd for wlan0 (client) and uap0 (AP)
cat > /etc/systemd/network/08-wlan0.network <<EOF
[Match]
Name=wlan0
[Network]
DHCP=yes
LLMNR=no
MulticastDNS=no
EOF

cat >> /etc/dhcpcd.conf <<EOF

# dhcpcd should ONLY manage the AP interface
denyinterfaces wlan0
denyinterfaces eth0

interface uap0
static ip_address=${AP_IP}/24
nohook wpa_supplicant
EOF



# eth0 gets DHCP if connected (for debugging/updates)
cat > /etc/systemd/network/04-eth0.network <<EOF
[Match]
Name=eth0
[Network]
DHCP=yes
EOF

echo 'Disable resolved DNS stub listener & point to localhost (dnsmasq)...'
sed -i 's/.*DNSStubListener=.*/DNSStubListener=no/g' /etc/systemd/resolved.conf
sed -i 's/.*IGNORE_RESOLVCONF.*/IGNORE_RESOLVCONF=yes/g' /etc/default/dnsmasq

echo 'Disabling ipv6...'
cat >> /etc/sysctl.conf <<EOF
net.ipv6.conf.all.disable_ipv6=1
net.ipv6.conf.default.disable_ipv6=1
net.ipv6.conf.lo.disable_ipv6=1
net.ipv6.conf.eth0.disable_ipv6 = 1
EOF

echo 'Setting up dnsmasq...'
cat >> /etc/dnsmasq.conf <<EOF
domain=picobrew.local
address=/picobrew.com/${AP_IP}
address=/www.picobrew.com/${AP_IP}
server=8.8.8.8
server=8.8.4.4
server=1.1.1.1
interface=uap0
bind-interfaces
dhcp-range=192.168.72.100,192.168.72.200,255.255.255.0,24h
EOF

mkdir -p /etc/systemd/system/dnsmasq.service.d
cat > /etc/systemd/system/dnsmasq.service.d/override.conf <<EOF
[Unit]
After=picobrew-accesspoint.service
Requires=picobrew-accesspoint.service

[Service]
ExecStartPre=/bin/sleep 2
EOF


systemctl enable dnsmasq.service

echo 'Setting up /etc/hosts...'
cat >> /etc/hosts <<EOF
${AP_IP}       picobrew.com
${AP_IP}       www.picobrew.com
EOF

echo 'Generating self-signed SSL certs...'
mkdir /certs
cat > /certs/req.cnf <<EOF
[v3_req]
keyUsage = critical, digitalSignature, keyAgreement
extendedKeyUsage = serverAuth
subjectAltName = @alt_names
subjectAltName = @alt_names
[alt_names]
DNS.1 = picobrew.com
DNS.2 = www.picobrew.com
EOF

openssl req -x509 -sha256 -newkey rsa:2048 -nodes -keyout /certs/domain.key -days 1825  -out  /certs/domain.crt  -subj "/CN=chiefwigms_Picobrew_Pico CA"

openssl req -newkey rsa:2048 -nodes -subj "/CN=picobrew.com" \
    -keyout  /certs/server.key -out  /certs/server.csr

openssl x509 \
    -CA /certs/domain.crt -CAkey /certs/domain.key -CAcreateserial \
    -in /certs/server.csr \
    -req -days 1825 -out /certs/server.crt -extfile /certs/req.cnf -extensions v3_req

cat /certs/server.crt /certs/domain.crt > /certs/bundle.crt

echo 'Setting up nginx for http and https...'
ln -s /picobrew_picoclaw/scripts/pi/picobrew.com.conf /etc/nginx/sites-available/picobrew.com.conf
ln -s /etc/nginx/sites-available/picobrew.com.conf /etc/nginx/sites-enabled/picobrew.com.conf
rm /etc/nginx/sites-enabled/default

echo 'Setup samba config...'
cat > /etc/samba/smb.conf <<EOF
[global]
workgroup = WORKGROUP
server string = Samba Server
netbios name = PICOBREW_SERVER
security = user
map to guest = Bad User
guest account = root
dns proxy = no

[App]
guest ok = yes
path = /picobrew_picoclaw
available = yes
browsable = yes
public = yes
writable = yes
read only = no

[Recipes]
guest ok = yes
path = /picobrew_picoclaw/app/recipes
available = yes
browsable = yes
public = yes
writable = yes
read only = no

[History]
guest ok = yes
path = /picobrew_picoclaw/app/sessions
available = yes
browsable = yes
public = yes
writable = yes
read only = no
EOF

# Have Name Service Switch use DNS
# After resolve install:
# hosts:          files resolve [!UNAVAIL=return] dns
sed -i 's/\(.*hosts:.*\) \[.*\]\(.*\)/\1\2/' /etc/nsswitch.conf

echo 'Setting up rc.local...'
sed -i 's/exit 0//g' /etc/rc.local
cat >> /etc/rc.local <<EOF

# reload systemd manager configuration to recreate entire dependency tree
systemctl daemon-reload

# toggle off WiFi power management
iw wlan0 set power_save off || true
sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true
iptables -t nat -C POSTROUTING -o wlan0 -j MASQUERADE 2>/dev/null || \
    iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
iptables -C FORWARD -i wlan0 -o uap0 -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || \
    iptables -A FORWARD -i wlan0 -o uap0 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -C FORWARD -i uap0 -o wlan0 -j ACCEPT 2>/dev/null || \
    iptables -A FORWARD -i uap0 -o wlan0 -j ACCEPT

cd /picobrew_picoclaw

if grep -q "update_boot:\s*[tT]rue" config.yaml
then
  echo 'Updating PicoClaw Server...'
  git pull || true
  # install dependencies and start server
  pip3 install -r requirements.txt
  ./scripts/pi/post-git-update.sh || true
fi

source_sha=${GIT_SHA}
rpi_image_version=${IMG_RELEASE}_${IMG_VARIANT}
export IMG_RELEASE=${IMG_RELEASE}
export IMG_VARIANT=${IMG_VARIANT}

echo "Starting PicoClaw Server (image: \${rpi_image_version}; source: \${source_sha}) ..."
python3 server.py 0.0.0.0 8080 &

exit 0
EOF

# Ensure rc-local.service is enabled so rc.local runs on boot
systemctl enable rc-local.service || true

echo 'Finished custom pi setup!'