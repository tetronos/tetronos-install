#!/usr/bin/env python3
"""Boot an installed disk (UEFI, snapshot, a USB mouse attached), log in as the installed user on
tty1 by typing keys through QMP, then check over the serial console that kmscon and tetron-wm run
for that login. Usage: tests/vm-session.py DISK USER PASSWORD. Screenshots: DO-NOT-COMMIT/work/vm/session-*.png"""
import os, re, socket, subprocess, sys, time, json
disk, user, pw = sys.argv[1:4]
here = os.path.dirname(os.path.abspath(__file__)); w = os.path.join(here, "..", "DO-NOT-COMMIT", "work", "vm"); os.makedirs(w, exist_ok=True)
sock, qmp, v = f"{w}/sess-ser.sock", f"{w}/sess-qmp.sock", f"{w}/sess-vars.fd"
for f in (sock, qmp):
    if os.path.exists(f): os.remove(f)
subprocess.run(["cp", "/usr/share/OVMF/OVMF_VARS_4M.fd", v], check=True)
q = subprocess.Popen(["qemu-system-x86_64", "-enable-kvm", "-cpu", "host", "-m", "2048", "-smp", "2",
    "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd", "-drive", f"if=pflash,format=raw,file={v}",
    "-drive", f"file={disk},format=raw,snapshot=on", "-device", "virtio-vga", "-device", "qemu-xhci", "-device", "usb-mouse", "-device", "usb-kbd",
    "-display", "none", "-nic", "user,model=virtio-net-pci", "-serial", f"unix:{sock},server=on,wait=off", "-qmp", f"unix:{qmp},server=on,wait=off"])
fails = []
def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok: fails.append(name)
def qcmd(c):
    s = socket.socket(socket.AF_UNIX); s.connect(qmp); f = s.makefile("rw"); f.readline()
    for x in ({"execute": "qmp_capabilities"}, c): f.write(json.dumps(x) + "\n"); f.flush(); f.readline()
def typ(t):
    for ch in t:
        qcmd({"execute": "send-key", "arguments": {"keys": [{"type": "qcode", "data": "ret" if ch == "\n" else ch}]}}); time.sleep(0.15)
try:
    s = socket.socket(socket.AF_UNIX)
    for _ in range(50):
        try: s.connect(sock); break
        except Exception: time.sleep(0.2)
    s.settimeout(1); buf = ""
    def expect(rx, t):
        global buf
        end = time.time() + t
        while time.time() < end:
            m = re.search(rx, buf)
            if m: o = buf[:m.end()]; buf = buf[m.end():]; return o
            try: buf += s.recv(65536).decode(errors="replace")
            except socket.timeout: pass
        raise SystemExit("timeout " + rx + " " + buf[-300:])
    expect(r"login:", 300)
    time.sleep(8); qcmd({"execute": "screendump", "arguments": {"filename": f"{w}/session-0-login.png", "format": "png"}})
    typ(user + "\n"); time.sleep(3); typ(pw + "\n"); time.sleep(20)
    qcmd({"execute": "screendump", "arguments": {"filename": f"{w}/session-1-after-login.png", "format": "png"}})
    s.sendall((user + "\n").encode()); expect(r"Password:", 20); s.sendall((pw + "\n").encode()); expect(r"\$ ", 60)
    def run(c, i):
        s.sendall((c + "; echo E\"\"ND" + str(i) + "\n").encode()); return expect("END" + str(i) + r"\r?\n", 30)
    out = run("ps -eo comm,user | awk '{print $1}' | sort -u | tr '\\n' ' '", 0)
    check("kmscon runs", "kmscon" in out); check("tetron-wm runs after the tty1 login", "tetron-wm" in out)
    out = run("systemctl is-enabled kmsconvt@tty1.service", 1); check("kmsconvt@tty1 enabled", "enabled" in out.split("\n", 1)[1])
finally:
    q.kill(); q.wait()
sys.exit(1 if fails else 0)
