# Building a PicoClaw Raspberry Pi Image

This guide explains how to create a deployable Raspberry Pi image that includes the PicoBrew PicoClaw server pre-configured.

> **Important**: This build process uses **Raspbian Buster** (dated 2020-12-02). Newer versions (Bullseye, Bookworm) have compatibility issues with PicoBrew devices and WiFi AP configuration.

## Prerequisites

You need a **Linux machine** (Ubuntu 20.04/22.04 recommended) or **WSL2 on Windows**.

## Quick Start

### 1. Install Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y coreutils quilt parted qemu-user-static debootstrap zerofree zip \
  dosfstools libarchive-tools libcap2-bin grep rsync xz-utils file git curl bc dos2unix
```

### 2. Clone pi-gen (Buster Release)

```bash
git clone https://github.com/RPi-Distro/pi-gen.git
cd pi-gen

# Checkout the Buster release tag
git checkout tags/2020-12-02-raspbian-buster -b buster-picobrew
```

### 3. Configure Package Sources for Buster Snapshots

Since Buster is archived, you must use snapshot repositories:

```bash
# Update stage0/00-configure-apt/files/sources.list
echo "deb http://snapshot.raspbian.org/202012010638/raspbian/ buster main contrib non-free rpi" > stage0/00-configure-apt/files/sources.list

# Update stage0/00-configure-apt/files/raspi.list
echo "deb http://archive.raspberrypi.org/debian/ buster main" > stage0/00-configure-apt/files/raspi.list

# Update stage0/prerun.sh bootstrap URL
sed -i 's|bootstrap ${RELEASE} "${ROOTFS_DIR}" .*|bootstrap ${RELEASE} "${ROOTFS_DIR}" http://snapshot.raspbian.org/202012010638/raspbian/|' stage0/prerun.sh
```

### 4. Configure pi-gen

```bash
cat > config <<EOF
export IMG_NAME=picobrew-pico
export RELEASE=buster
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

### 5. Configure for Lite Image (No Desktop)

```bash
# Skip desktop stages (Lite image only - smaller footprint for Pi Zero W)
touch ./stage3/SKIP ./stage4/SKIP ./stage5/SKIP
touch ./stage4/SKIP_IMAGES ./stage5/SKIP_IMAGES
rm -f stage2/EXPORT_NOOBS
```

### 6. Add PicoClaw Server Stage

```bash
# Create custom stage directory
rm -rf stage2/99-picobrewserver-setup
mkdir -p stage2/99-picobrewserver-setup

# Copy the setup script from your PicoClaw repo
cp /path/to/PicoBrew_PicoClaw/scripts/pi/00-run-chroot.sh stage2/99-picobrewserver-setup/
chmod +x stage2/99-picobrewserver-setup/00-run-chroot.sh
```

### 7. Build the Image

```bash
sudo ./build.sh
```

The build takes 30-60 minutes depending on your machine. Output will be in `deploy/` as a `.zip` file.

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

## Why Buster?

Newer Raspberry Pi OS versions (Bullseye, Bookworm) have issues:
- **WiFi AP + Client mode**: The simultaneous AP/client WiFi configuration works reliably on Buster but has issues on newer releases
- **Package compatibility**: Some required packages have different names or behaviors
- **WiFi firmware**: Buster's WiFi firmware is more stable for the concurrent AP+STA mode required

## GitHub Actions (Automated Builds)

Push a tag (e.g., `v1.0.0`) to trigger the "Build Raspberry Pi Image" workflow, or run it manually from the Actions tab.

## Troubleshooting

- **Build fails at stage0**: Ensure snapshot URLs are correct and accessible
- **Build fails at stage2**: Ensure all dependencies are installed
- **Image doesn't boot**: Try a different SD card or re-flash
- **WiFi AP not appearing**: Check `/etc/hostapd/hostapd.conf` config
- **Server not starting**: Check `/var/log/syslog` for errors

## Files in This Directory

| File | Purpose |
|------|---------|
| `_readme.txt` | Original manual build notes |
| `00-run-chroot.sh` | Main customization script run during image build |
| `picobrew.com.conf` | nginx configuration for SSL/HTTP proxy |
| `post-git-update.sh` | Script run after git updates |
| `wifi_scan.sh` | Utility for scanning WiFi networks |