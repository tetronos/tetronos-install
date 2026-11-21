#!/usr/bin/env python3
"""Boot an installed USB stick in a VM (real device passed through), log in on serial, run the slowness diagnostics, power off cleanly.
Usage: tests/stick-diag.py VENDORID PRODUCTID [USER PASSWORD]   (hex ids from lsusb, e.g. 154b 00ee). Output: DO-NOT-COMMIT/stick-diag-DATE.txt
Never kills the VM on success; a timeout leaves it running and says so (a kill during writes can hurt a cheap stick)."""
import os, re, socket, subprocess, sys, time
vid, pid = sys.argv[1], sys.argv[2]; user = sys.argv[3] if len(sys.argv) > 3 else "tester"; pw = sys.argv[4] if len(sys.argv) > 4 else "pass1234"
here = os.path.dirname(os.path.abspath(__file__)); out = f"{here}/../DO-NOT-COMMIT/stick-diag-{time.strftime('%Y%m%d-%H%M%S')}.txt"
sock = f"/tmp/stick-diag-{os.getpid()}.sock"; v = f"/tmp/stick-diag-{os.getpid()}.vars"
subprocess.run(["cp", "/usr/share/OVMF/OVMF_VARS_4M.fd", v], check=True); t0 = time.time(); log = open(out, "w")
def say(x): print(x, flush=True); log.write(x + "\n"); log.flush()
q = subprocess.Popen(["qemu-system-x86_64", "-enable-kvm", "-cpu", "host", "-m", "4096", "-smp", "4",
    "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd", "-drive", f"if=pflash,format=raw,file={v}",
    "-device", "qemu-xhci,id=xhci", "-device", f"usb-host,bus=xhci.0,vendorid=0x{vid},productid=0x{pid}",
    "-device", "virtio-vga", "-nic", "user,model=virtio-net-pci", "-display", "none", "-serial", f"unix:{sock},server=on,wait=off"])
s = socket.socket(socket.AF_UNIX)
for _ in range(50):
    try: s.connect(sock); break
    except Exception: time.sleep(0.2)
s.settimeout(1); buf = ""
def expect(rx, t):
    global buf; end = time.time() + t
    while time.time() < end:
        m = re.search(rx, buf)
        if m: o = buf[:m.end()]; buf = buf[m.end():]; return o
        try: buf += s.recv(65536).decode(errors="replace")
        except socket.timeout: pass
    say("TIMEOUT waiting for %r after %.0f s; VM left running (pid %d); tail: %r" % (rx, time.time() - t0, q.pid, buf[-300:])); sys.exit(1)
expect(r"login:", 2400); say("login prompt on serial after %.0f s (wall clock, includes OVMF and grub)" % (time.time() - t0))
s.sendall((user + "\n").encode()); expect(r"Password:", 120); s.sendall((pw + "\n").encode()); expect(r"\$ ", 900)
say("shell after %.0f s" % (time.time() - t0))
SUDO = f"echo {pw} | sudo -S -v 2>/dev/null; "
cmds = [
 ("analyze", "systemd-analyze 2>&1"),
 ("blame", "systemd-analyze blame --no-pager 2>&1 | head -25"),
 ("critical-chain", "systemd-analyze critical-chain --no-pager 2>&1 | head -30"),
 ("jobs", "systemctl list-jobs --no-pager 2>&1 | head"),
 ("failed", "systemctl --failed --no-pager 2>&1 | head -15"),
 ("io-pressure", "cat /proc/pressure/io /proc/pressure/cpu /proc/pressure/memory"),
 ("D-state and lazyinit", "ps -eo pid,stat,wchan:22,comm | awk '$2 ~ /^D/ || /ext4lazyinit/'"),
 ("id and input", "id; ls -l /dev/input | head -12; ls -l /dev/dri | head"),
 ("mounts", "findmnt -no SOURCE,TARGET,OPTIONS / /boot; cat /sys/block/sda/queue/scheduler"),
 ("write sample 30 s (sectors by disk, bytes by process)", "a=$(awk '$3==\"sda\"{print $10}' /proc/diskstats); for p in /proc/[0-9]*; do echo $(cat $p/comm 2>/dev/null) $(awk '/^write_bytes/{print $2}' $p/io 2>/dev/null); done > /tmp/io1 2>/dev/null; sleep 30; b=$(awk '$3==\"sda\"{print $10}' /proc/diskstats); echo sda_written_KB_in_30s=$(( (b-a)/2 )); for p in /proc/[0-9]*; do echo $(cat $p/comm 2>/dev/null) $(awk '/^write_bytes/{print $2}' $p/io 2>/dev/null); done > /tmp/io2 2>/dev/null; echo top writers, KB total since boot:; sort -k2 -n -r /tmp/io2 | head -8"),
 ("journal", "journalctl -b -p warning --no-pager 2>&1 | tail -25; journalctl --disk-usage"),
 ("ssh unit", "systemctl status ssh --no-pager 2>&1 | head -12; journalctl -u ssh -b --no-pager 2>&1 | tail -8"),
 ("dmesg usb and errors", "dmesg 2>&1 | grep -i -E 'usb|sda|reset|error|timeout|ext4' | tail -25"),
 ("sync write test", "cd ~ && time dd if=/dev/zero of=t bs=4k count=200 oflag=sync 2>&1 | tail -1; rm -f t"),
]

if os.environ.get("CMDSET") == "trace":
    TR = "T=/sys/kernel/tracing; sudo mount -t tracefs nodev $T 2>/dev/null; "
    cmds = [
     ("uptime and load", "uptime; cat /proc/pressure/io | head -1"),
     ("who syncs and who issues IO, 60 s idle after login (fsync counts per process; block requests by process; flush requests)",
      "sudo sh -c 'T=/sys/kernel/tracing; mount -t tracefs nodev $T 2>/dev/null; echo 0 > $T/tracing_on; echo > $T/trace; "
      "for e in fsync fdatasync sync syncfs sync_file_range; do echo 1 > $T/events/syscalls/sys_enter_$e/enable; done; "
      "echo 1 > $T/events/block/block_rq_issue/enable; echo 1 > $T/tracing_on; sleep 60; echo 0 > $T/tracing_on; "
      "echo SYNC CALLS by process:; grep sys_enter_ $T/trace | sed -e \"s/^ *//\" -e \"s/-[0-9]* .*//\" | sort | uniq -c | sort -rn | head -12; "
      "echo BLOCK REQUESTS by process:; grep block_rq_issue $T/trace | sed -e \"s/^ *//\" -e \"s/-[0-9]* .*//\" | sort | uniq -c | sort -rn | head -12; "
      "echo FLUSH-flagged requests:; grep -c -E \"block_rq_issue: [0-9,]+ [A-Z]*F\" $T/trace; echo write requests:; grep -c -E \"block_rq_issue: [0-9,]+ [A-Z]*W\" $T/trace'"),
     ("per-process written bytes since boot (root)", "sudo sh -c 'for p in /proc/[0-9]*; do echo $(awk \"/^write_bytes/{print \\$2/1024}\" $p/io 2>/dev/null) KB $(cat $p/comm 2>/dev/null); done | sort -n -r | head -12'"),
     ("journal and logging", "journalctl --disk-usage; sudo ls -la /var/log/journal 2>&1 | head -4; grep -rhs -E '^(Storage|Sync|Forward)' /etc/systemd/journald.conf /etc/systemd/journald.conf.d/ 2>&1 | head"),
     ("timers and services running now", "systemctl list-timers --no-pager | head -12; systemctl list-units --type=service --state=running --no-pager | head -30"),
    ]
for i, (name, c) in enumerate(cmds):
    say("\n=== " + name + " ===")
    s.sendall((SUDO + c + "; echo E\"\"ND" + str(i) + "\n").encode())
    say(expect("END" + str(i) + r"\r?\n", 600).replace("\r", ""))
say("\npoweroff (clean)"); s.sendall((SUDO + "sudo systemctl poweroff\n").encode()); q.wait(timeout=300); say("VM exited; safe to unplug the stick")
