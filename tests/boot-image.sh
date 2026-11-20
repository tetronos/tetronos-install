#!/bin/sh
# Boot an installed image in QEMU/KVM (bios|uefi), read-only (snapshot), wait for the serial login prompt.
# Usage: tests/boot-image.sh IMG bios|uefi [timeout]. Exit 0 when "login:" appears. Log: IMG.<fw>.log
set -e
IMG="$1"; FW="${2:-bios}"; T="${3:-120}"
LOG="$IMG.$FW.log"; rm -f "$LOG"; A=""
if [ "$FW" = uefi ]; then
	V=$(mktemp); cp /usr/share/OVMF/OVMF_VARS_4M.fd "$V"
	A="-drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd -drive if=pflash,format=raw,file=$V"
fi
# shellcheck disable=SC2086
qemu-system-x86_64 -enable-kvm -cpu host -m 2048 -smp 2 $A -drive file="$IMG",format=raw,snapshot=on \
	-display none -nic user,model=virtio-net-pci -serial file:"$LOG" >/dev/null 2>&1 &
Q=$!
i=0; while [ $i -lt "$T" ]; do grep -aq "login:" "$LOG" 2>/dev/null && break; sleep 2; i=$((i+2)); done
kill $Q 2>/dev/null || true
grep -aq "login:" "$LOG" && { echo "PASS $FW"; exit 0; } || { echo "FAIL $FW"; tail -c 300 "$LOG"; exit 1; }
