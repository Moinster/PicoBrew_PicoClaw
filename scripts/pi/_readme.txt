#Creating a custom image:

#Setup:
sudo apt update && sudo apt upgrade -y
sudo apt install -y coreutils quilt parted qemu-user-static debootstrap zerofree zip dosfstools libarchive-tools libcap2-bin grep rsync xz-utils file git curl bc dos2unix

git clone https://github.com/RPi-Distro/pi-gen.git

cd pi-gen

git checkout tags/2020-12-02-raspbian-buster -b buster-picobrew

#Update "stage0/00-configure-apt/files/sources.list" to "deb http://snapshot.raspbian.org/202012010638/raspbian/ buster main contrib non-free rpi"

#Update "stage0/00-configure-apt/files/raspi.list" to "deb http://archive.raspberrypi.org/debian/ buster main"

#Update "stage0/prerun.sh" to "bootstrap ${RELEASE} "${ROOTFS_DIR}" http://snapshot.raspbian.org/202012010638/raspbian/"




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

# Rasbian Lite (no NOOBS)
touch ./stage3/SKIP ./stage4/SKIP ./stage5/SKIP
touch ./stage4/SKIP_IMAGES ./stage5/SKIP_IMAGES
rm -f stage2/EXPORT_NOOBS

#Stage Picobrew Server area
rm -rf stage2/99-picobrewserver-setup
mkdir -p stage2/99-picobrewserver-setup
#cp <Picobrewserver Root>/picobrew_picoclaw/scripts/pi/00-run-chroot.sh stage2/99-picobrewserver-setup/