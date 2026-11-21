#!/bin/sh
# Same measurements every time, so sticks and before/after runs compare.
# Usage: sudo tests/stick-bench.sh /dev/sdX LABEL [--write]
# Read tests are non-destructive. --write overwrites ~140 MB at 1 GiB before the end of the
# disk (the caller decides the disk is erasable) and refuses a mounted disk.
# Output: one block to stdout and DO-NOT-COMMIT/stick-bench-LABEL-DATE.txt
set -eu
DEV="$1"; LABEL="$2"; WRITE="${3:-}"
[ -b "$DEV" ] || { echo "not a block device: $DEV" >&2; exit 2; }
OUT="$(cd "$(dirname "$0")/.." && pwd)/DO-NOT-COMMIT/stick-bench-$LABEL-$(date +%Y%m%d-%H%M%S).txt"
mkdir -p "$(dirname "$OUT")"
rate() { awk '/copied/ {print $(NF-1), $NF}'; }
{
echo "== $LABEL $DEV $(date)"
lsblk -d -o NAME,SIZE,VENDOR,MODEL,TRAN,SERIAL "$DEV"
d=$(readlink -f "/sys/block/${DEV##*/}/device"); while [ "$d" != / ]; do [ -f "$d/speed" ] && { echo "usb link: $(cat "$d/speed") Mb/s"; break; }; d=$(dirname "$d"); done
B=$(blockdev --getsize64 "$DEV"); echo "bytes: $B"
echo "-- read, 64 MB direct, 5 places"
for p in 0 25 50 75 95; do printf '%3s%%: ' "$p"; dd if="$DEV" of=/dev/null bs=1M count=64 skip=$(( B / 100 * p / 1048576 )) iflag=direct 2>&1 | rate; done
echo "-- read, 4 KB direct x2000"; dd if="$DEV" of=/dev/null bs=4k count=2000 skip=$(( B / 2 / 4096 )) iflag=direct 2>&1 | rate
if [ "$WRITE" = --write ]; then
	if lsblk -n -o MOUNTPOINTS "$DEV" | grep -q .; then echo "REFUSED: $DEV has mounted partitions" >&2; exit 3; fi
	S=$(( (B - 1073741824) / 4096 )); M=$(( (B - 536870912) / 1048576 ))
	echo "-- write 4 KB synchronous x200"; dd if=/dev/zero of="$DEV" bs=4k count=200 seek="$S" oflag=direct,dsync 2>&1 | rate
	echo "-- write 4 KB direct x2000"; dd if=/dev/zero of="$DEV" bs=4k count=2000 seek="$S" oflag=direct 2>&1 | rate
	echo "-- write 64 MB sequential, 2 runs"
	dd if=/dev/zero of="$DEV" bs=1M count=64 seek="$M" oflag=direct 2>&1 | rate
	dd if=/dev/zero of="$DEV" bs=1M count=64 seek=$((M + 64)) oflag=direct 2>&1 | rate
fi
echo "-- kernel log errors since boot"; dmesg | grep -i "${DEV##*/}" | grep -i -c "error\|reset" || true
} | tee "$OUT"
echo "saved: $OUT"
