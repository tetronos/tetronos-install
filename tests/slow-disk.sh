#!/bin/sh
# Put a write delay under a COPY of an installed image (dm-delay) to model a stick with slow cache flushes.
# Usage: sudo tests/slow-disk.sh up IMG DELAY_MS   -> prints /dev/mapper/slowdisk ;   sudo tests/slow-disk.sh down
set -e
case "$1" in
up) L=$(losetup -f --show "$2"); S=$(blockdev --getsz "$L"); dmsetup create slowdisk --table "0 $S delay $L 0 0 $L 0 $3"; chmod a+rw /dev/mapper/slowdisk 2>/dev/null; echo /dev/mapper/slowdisk ;;
down) L=$(dmsetup deps -o devname slowdisk | sed 's/.*(\(loop[0-9]*\)).*/\1/'); dmsetup remove slowdisk; [ -n "$L" ] && losetup -d "/dev/$L" ;;
esac
