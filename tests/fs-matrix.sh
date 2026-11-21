#!/bin/sh
# Same sync write test on one partition under several formats and mount options (DESTROYS the partition). Usage: tests/fs-matrix.sh /dev/sdXN
P="$1"; [ -b "$P" ] || { echo "usage: $0 PARTITION" >&2; exit 2; }
M=/mnt/fsm; sudo mkdir -p $M
run() { # label mkfs-command mount-options
	label="$1"; mk="$2"; mo="$3"
	sh -c "$mk" >/dev/null 2>&1 || { echo "== $label: mkfs failed or tool missing"; return; }
	sudo mount ${mo:+-o $mo} "$P" $M || { echo "== $label: mount failed"; return; }; sudo chown "$(id -u)" $M
	cd $M
	s=$(date +%s.%N); dd if=/dev/zero of=a.t bs=4k count=200 oflag=sync 2>/dev/null; e=$(date +%s.%N)
	s2=$(date +%s.%N); i=0; while [ $i -lt 200 ]; do echo x > f$i.t; sync f$i.t; i=$((i+1)); done; e2=$(date +%s.%N)
	rm -f *.t; cd /; sudo sync; sudo umount $M
	echo "== $label: 200 synced 4K appends $(echo "$e - $s" | bc) s; 200 files create+fsync $(echo "$e2 - $s2" | bc) s"
}
run "ext4 default"                "sudo mkfs.ext4 -q -F $P" ""
run "ext4 no journal"             "sudo mkfs.ext4 -q -F -O ^has_journal $P" ""
run "ext4 data=writeback"         "sudo mkfs.ext4 -q -F $P" "data=writeback"
run "ext4 barrier=0"              "sudo mkfs.ext4 -q -F $P" "barrier=0"
run "ext4 noatime,commit=30"      "sudo mkfs.ext4 -q -F $P" "noatime,commit=30"
run "ext2"                        "sudo mkfs.ext2 -q -F $P" ""
run "xfs"                         "sudo mkfs.xfs -q -f $P" ""
run "f2fs"                        "sudo mkfs.f2fs -q -f $P" ""
run "vfat"                        "sudo mkfs.vfat $P" "flush"
echo DONE
