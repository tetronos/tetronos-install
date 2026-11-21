#!/usr/bin/env python3
"""Boot an installed image in QEMU (snapshot, throttled disk) and time `apt-get install mc`; print dpkg.log step times and sectors written.
Usage: tests/apt-timing.py IMG [IOPS]   (IOPS limits the virtual disk; default 300 to model a slow stick)"""
import os, re, socket, subprocess, sys, time
img = sys.argv[1]; iops = sys.argv[2] if len(sys.argv) > 2 else "300"
here = os.path.dirname(os.path.abspath(__file__)); sock = f"/tmp/apt-timing-{os.getpid()}.sock"
vars_ = f"/tmp/apt-timing-{os.getpid()}.vars"; subprocess.run(["cp", "/usr/share/OVMF/OVMF_VARS_4M.fd", vars_])
q = subprocess.Popen(["qemu-system-x86_64", "-enable-kvm", "-cpu", "host", "-m", "2048", "-smp", "2",
    "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd", "-drive", f"if=pflash,format=raw,file={vars_}",
    *(["-device","qemu-xhci,id=xhci","-device",f"usb-host,bus=xhci.0,vendorid=0x{img[4:8]},productid=0x{img[9:13]}"] if img.startswith("usb:") else ["-drive", (f"file={img},format=raw" if img.startswith("/dev/") else f"file={img},format=raw,snapshot=on,throttling.iops-total={iops}")]), "-display", "none",
    "-nic", "user,model=virtio-net-pci", "-serial", f"unix:{sock},server,nowait"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
while not os.path.exists(sock): time.sleep(0.2)
s = socket.socket(socket.AF_UNIX); s.connect(sock); s.settimeout(1); buf = b""
def expect(pat, t):
    global buf; end = time.time() + t
    while time.time() < end:
        try: buf += s.recv(65536)
        except socket.timeout: pass
        m = re.search(pat.encode(), buf)
        if m: r = buf[:m.end()].decode(errors="replace"); buf = buf[m.end():]; return r
    raise SystemExit(f"timeout waiting for {pat}\n{buf[-400:].decode(errors='replace')}")
def send(x): s.send(x.encode())
try:
    expect(r"tetron login:", 600); send("tester\n"); expect("Password:", 30); send("pass1234\n"); expect(r"\$ ", 60)
    send("echo pass1234 | sudo -S -v 2>/dev/null; echo READY\n"); expect("READY\\r?\\n.*\\$ ", 20)
    def run(c, t):
        send(f"{c}; echo DONE$?\n"); return expect(r"DONE\d+", t)
    run("echo", 10)
    if os.environ.get("PRE"): print("PRE:", run(os.environ["PRE"], 120))
    print(run("cd ~ && time dd if=/dev/zero of=t bs=4k count=200 oflag=sync 2>&1 | tail -1; rm -f t", 900))
    out = run((f"INSTALL_ARGS=\"{os.environ['INSTALL_ARGS']}\"; " if os.environ.get("INSTALL_ARGS") else "") + "sectors() { awk '$3==\"vda\"||$3==\"sda\"{print $10}' /proc/diskstats; }; a=$(sectors); T=$(date +%s); sudo apt-get update >/tmp/upd.log 2>&1; echo UPDATE_S=$(( $(date +%s)-T )); echo UPDATE_MB=$(( ($(sectors)-a)/2048 )); T=$(date +%s); a=$(sectors); sudo apt-get install -y ${INSTALL_ARGS:-mc} 2>&1 | while IFS= read -r l; do echo \"$(date +%s) $l\"; done >/tmp/apt.log; echo RC=$?; echo SECONDS=$(( $(date +%s)-T )); echo WRITTEN_MB=$(( ($(sectors)-a)/2048 )); grep -E ' (install|status unpacked|status installed|trigproc) ' /var/log/dpkg.log | tail -40; awk 'NR==1{t=$1} {printf \"+%ds %s\\n\", $1-t, substr($0,index($0,$2))}' /tmp/apt.log | cut -c1-90; tail -3 /tmp/upd.log", 3000)
    print(out)
    send("sudo systemctl poweroff\n"); q.wait()  # never kill the VM: wait for the guest to power off by itself
finally:
    os.path.exists(sock) and os.unlink(sock)
