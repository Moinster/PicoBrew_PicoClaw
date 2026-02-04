# Building a PicoClaw Raspberry Pi Image

This guide explains how to create a deployable Raspberry Pi image that includes the PicoBrew PicoClaw server pre-configured.

## Prerequisites

You need a **Linux machine** (Ubuntu 22.04+ recommended) or **WSL2 on Windows**.

## Quick Start

### 1. Install Dependencies

```bash
sudo apt update && sudo apt install -y \
  coreutils quilt parted qemu-user-static debootstrap zerofree zip \
  dosfstools libarchive-tools libcap2-bin grep rsync xz-utils file git curl bc dos2unix
```

### 2. Clone pi-gen

```bash
git clone https://github.com/RPi-Distro/pi-gen.git
cd pi-gen
```

### 3. Configure pi-gen

```bash
cat > config <<EOF
export IMG_NAME=picobrew-pico
export RELEASE=bookworm
export DEPLOY_ZIP=1
export LOCALE_DEFAULT=en_US.UTF-8
export TARGET_HOSTNAME=raspberrypi
export KEYBOARD_KEYMAP=us
export KEYBOARD_LAYOUT="English (US)"
export TIMEZONE_DEFAULT=America/New_York
export FIRST_USER_NAME=pi
export FIRST_USER_PASS=raspberry
export ENABLE_SSH=1
EOF
```

### 4. Configure for Lite Image (No Desktop)

```bash
touch ./stage3/SKIP ./stage4/SKIP ./stage5/SKIP
touch ./stage4/SKIP_IMAGES ./stage5/SKIP_IMAGES
rm -f stage2/EXPORT_NOOBS
```

### 5. Add PicoClaw Server Stage

```bash
# Create custom stage directory
mkdir -p stage2/99-picoclaw

# Copy the setup script
cp /path/to/PicoBrew_PicoClaw/scripts/pi/00-run-chroot.sh stage2/99-picoclaw/

# Edit the script to set your GitHub repo URL
# Change GIT_REPO="https://github.com/yourusername/PicoBrew_PicoClaw.git"
nano stage2/99-picoclaw/00-run-chroot.sh
```

### 6. Build the Image

```bash
sudo ./build.sh
```

The build takes 30-60 minutes. Output will be in `deploy/` as a `.zip` file.

## Flashing the Image

1. Extract the `.img` file from the zip
2. Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) or [Balena Etcher](https://www.balena.io/etcher/)
3. (Optional) Edit `wpa_supplicant.conf` on the boot partition for WiFi
4. Insert SD card and power on

## What the Image Does

- Creates WiFi Access Point: `PICOBREW` / password: `PICOBREW`
- Redirects `picobrew.com` to the Pi via dnsmasq
- Runs nginx as reverse proxy with SSL
- Auto-starts Flask server on boot (port 8080)
- Provides Samba network shares for recipes/sessions
- Supports auto-update from git on boot

## GitHub Actions (Automated Builds)

Push to the `master` branch and use the "Build Raspberry Pi Image" workflow to build images automatically.

## Troubleshooting

- **Build fails at stage2**: Ensure all dependencies are installed
- **Image doesn't boot**: Try a different SD card or re-flash
- **WiFi AP not appearing**: Check `/etc/hostapd/hostapd.conf` config
- **Server not starting**: Check `/var/log/syslog` for errors

## Files in This Directory

| File | Purpose |
|------|---------|
| `00-run-chroot.sh` | Main customization script run during image build |
| `picobrew.com.conf` | nginx configuration for SSL/HTTP proxy |
| `post-git-update.sh` | Script run after git updates |
| `wifi_scan.sh` | Utility for scanning WiFi networks |