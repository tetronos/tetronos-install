#!/bin/sh
# Install the squashfs of an ISO into an image file twice, boot it (BIOS and UEFI), check the result.
# Usage: sudo tests/test-install.sh ISO  (prototype uses --fetch-deps: needs network)
set -e
ISO="$1"; [ -f "$ISO" ] || { echo "usage: $0 ISO" >&2; exit 2; }
H="$(cd "$(dirname "$0")/.." && pwd)"; W="$H/DO-NOT-COMMIT/work/test"; mkdir -p "$W/iso" "$W/sq"
fail=0; ok() { echo "PASS $1"; }; bad() { echo "FAIL $1"; fail=1; }
cleanup() { umount "$W/sq" 2>/dev/null; umount "$W/iso" 2>/dev/null; umount "$W/m" 2>/dev/null; true; }
trap cleanup EXIT
mount -o loop,ro "$ISO" "$W/iso"; mount -o loop,ro "$W/iso/live/filesystem.squashfs" "$W/sq"
echo pass1234 > "$W/pw"; chmod 600 "$W/pw"
for n in 1 2; do rm -f "$W/i$n.img"; "$H/scripts/tetronos-install" --user tester --password-file "$W/pw" --source "$W/sq" --target-image "$W/i$n.img" --size 10G --yes --fetch-deps >"$W/i$n.log" 2>&1 && ok "install $n" || bad "install $n"; done
mkdir -p "$W/m"; L=$(losetup -f --show -P "$W/i1.img"); mount "${L}p4" "$W/m"
[ ! -s "$W/m/etc/machine-id" ] && ok "machine-id empty" || bad "machine-id"
grep -q '^tester:' "$W/m/etc/passwd" && ok "user exists" || bad "user"
! grep -q '^tetronos:' "$W/m/etc/passwd" && ok "no live user" || bad "live user"
[ -z "$(chroot "$W/m" dpkg -l 'live-*' tetronos-live-config 2>/dev/null | grep '^ii')" ] && ok "no live packages" || bad "live packages"
[ ! -e "$W/m/etc/tetron/secret_key" ] && ok "no tetron identity" || bad "identity"
[ ! -e "$W/m/etc/systemd/system/kmsconvt@tty1.service.d/autologin.conf" ] && ok "autologin off" || bad "autologin"
[ -z "$(chroot "$W/m" find /etc/systemd/system -xtype l)" ] && ok "no dangling unit links" || bad "dangling links"
umount "$W/m"; losetup -d "$L"
L2=$(losetup -f --show -P "$W/i2.img"); mount "${L2}p4" "$W/m"
k2=$(cat "$W/m/etc/ssh/ssh_host_ed25519_key.pub"); umount "$W/m"; losetup -d "$L2"
L=$(losetup -f --show -P "$W/i1.img"); mount "${L}p4" "$W/m"; k1=$(cat "$W/m/etc/ssh/ssh_host_ed25519_key.pub"); umount "$W/m"; losetup -d "$L"
[ "$k1" != "$k2" ] && ok "ssh host keys differ" || bad "ssh host keys"
for fw in bios uefi; do "$H/tests/boot-image.sh" "$W/i1.img" "$fw" 120 && ok "boot $fw" || bad "boot $fw"; done
exit $fail
