#!/usr/bin/env python3
"""Boot an installed image in a VM (snapshot, writes discarded) with kernel tracing of sync calls and block requests from the first second,
log in on serial and print who synced and who issued IO during boot. Device speed does not matter for the counts.
Usage: tests/boot-trace.py IMG KERNEL INITRD ROOT_UUID [USER PASSWORD]"""
import os, re, socket, subprocess, sys, time
img, kern, initrd, uuid = sys.argv[1:5]; user = sys.argv[5] if len(sys.argv) > 5 else "tester"; pw = sys.argv[6] if len(sys.argv) > 6 else "pass1234"
sock = f"/tmp/boot-trace-{os.getpid()}.sock"
ev = "syscalls:sys_enter_fsync,syscalls:sys_enter_fdatasync,syscalls:sys_enter_sync,syscalls:sys_enter_syncfs,syscalls:sys_enter_sync_file_range,block:block_rq_issue"
q = subprocess.Popen(["qemu-system-x86_64", "-enable-kvm", "-cpu", "host", "-m", "2048", "-smp", "2", "-kernel", kern, "-initrd", initrd,
    "-append", f"root=UUID={uuid} ro console=ttyS0,115200n8",
    "-drive", f"file={img},format=raw,snapshot=on,if=virtio", "-nic", "user,model=virtio-net-pci", "-display", "none", "-serial", f"unix:{sock},server=on,wait=off"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
s = socket.socket(socket.AF_UNIX)
for _ in range(50):
    try: s.connect(sock); break
    except Exception: time.sleep(0.2)
s.settimeout(1); buf = ""; t0 = time.time()
def expect(rx, t):
    global buf; end = time.time() + t
    while time.time() < end:
        m = re.search(rx, buf)
        if m: o = buf[:m.end()]; buf = buf[m.end():]; return o
        try: buf += s.recv(65536).decode(errors="replace")
        except socket.timeout: pass
    print("TIMEOUT", rx, buf[-300:]); q.kill(); sys.exit(1)
try:
    expect(r"tetron login:", 300); print("login prompt after %.0f s" % (time.time() - t0))
    s.sendall((user + "\n").encode()); expect("Password:", 30); s.sendall((pw + "\n").encode()); expect(r"\$ ", 60)
    def run(c, t=120):
        s.sendall((c + "; echo E\"\"ND\n").encode()); return expect(r"END\r?\n", t).replace("\r", "")
    s.sendall(f"echo {pw} | sudo -S -v 2>/dev/null\n".encode()); time.sleep(2)
    TR = "sudo sh -c 'T=/sys/kernel/tracing; mount -t tracefs nodev $T 2>/dev/null; echo 0 > $T/tracing_on; echo > $T/trace; for e in fsync fdatasync sync syncfs sync_file_range; do echo 1 > $T/events/syscalls/sys_enter_$e/enable; done; echo 1 > $T/events/block/block_rq_issue/enable; echo 1 > $T/tracing_on'"
    SUM = "sudo sh -c 'T=/sys/kernel/tracing; echo 0 > $T/tracing_on; echo SYNC CALLS by process:; grep sys_enter_ $T/trace | sed -e \"s/^ *//\" -e \"s/-[0-9]* .*//\" | sort | uniq -c | sort -rn | head -12; echo BLOCK REQUESTS by process:; grep block_rq_issue $T/trace | sed -e \"s/^ *//\" -e \"s/-[0-9]* .*//\" | sort | uniq -c | sort -rn | head -10; echo write requests, flush-flagged:; grep -c -E \"block_rq_issue: [0-9,]+ [A-Z]*W\" $T/trace; grep -c -E \"block_rq_issue: [0-9,]+ [A-Z]*F\" $T/trace'"
    if os.environ.get("PRE"): print(run(os.environ["PRE"], 60))
    print(run("sudo apt-get update >/dev/null 2>&1; echo updated", 300))
    print("\n=== apt install --reinstall mc mc-data perl-modules-5.40 ===")
    print(run(TR, 30)); print(run("time sudo apt-get install -y --reinstall mc mc-data perl-modules-5.40 >/dev/null 2>&1", 900)); print(run(SUM, 60))
    s.sendall(b"sudo systemctl poweroff\n"); q.wait(timeout=300)
finally:
    if q.poll() is None: q.kill()
    os.path.exists(sock) and os.unlink(sock)
