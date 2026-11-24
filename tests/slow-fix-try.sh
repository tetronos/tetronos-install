#!/bin/sh
# Fresh copy of the installed image under a write delay, apply PRE in the guest, time dd + apt install mc. Usage: tests/slow-fix-try.sh LABEL DELAY_MS 'PRE command'
set -e
H="$(cd "$(dirname "$0")/.." && pwd)"; W="$H/DO-NOT-COMMIT/work"; L="$1"; D="$2"; export PRE="$3"
sudo "$H/tests/slow-disk.sh" down 2>/dev/null || true
rm -f "$W/slow.img"; cp --sparse=always "$W/test/i1.img" "$W/slow.img"
sudo "$H/tests/slow-disk.sh" up "$W/slow.img" "$D" >/dev/null; sudo setfacl -m u:$(id -un):rw "$(readlink -f /dev/mapper/slowdisk)"
"$H/tests/apt-timing.py" /dev/mapper/slowdisk > "$H/DO-NOT-COMMIT/apt-timing-$L.out" 2>&1 || true
sudo "$H/tests/slow-disk.sh" down
