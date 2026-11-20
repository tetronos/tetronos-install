#!/usr/bin/env python3
"""Install from inside the booted live ISO onto a second virtio disk, then boot that disk.
Usage: [TARGET_DEV=/dev/sdX] tests/vm-install.py ISO bios|uefi   (needs kvm, qemu, OVMF for uefi; no sudo)
The live system is driven over its serial console (tetronos/live). A partition on the
target is mounted first, so the engine's unmount path runs. Work dir: DO-NOT-COMMIT/work/vm."""
import os, re, socket, subprocess, sys, time

iso, fw = os.path.abspath(sys.argv[1]), sys.argv[2]
here = os.path.dirname(os.path.abspath(__file__))
w = os.path.join(here, "..", "DO-NOT-COMMIT", "work", "vm"); os.makedirs(w, exist_ok=True)
# TARGET_DEV=/dev/sdX: a real device (USB stick) instead of a 12G image; the caller grants access
# (setfacl) and the device is ERASED. Never overwrite an existing image file.
dev = os.environ.get("TARGET_DEV")
disk, sock = dev or f"{w}/target-{fw}.raw", f"{w}/ser-{fw}.sock"
for f in ((sock,) if dev else (disk, sock)):
    if os.path.exists(f): os.rename(f, f"{f}.{int(time.time())}")
if not dev: subprocess.run(["truncate", "-s", "12G", disk], check=True)
fwargs = []
if fw == "uefi":
    v = f"{w}/vars-{fw}.fd"; subprocess.run(["cp", "/usr/share/OVMF/OVMF_VARS_4M.fd", v], check=True)
    fwargs = ["-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd",
              "-drive", f"if=pflash,format=raw,file={v}"]
q = subprocess.Popen(["qemu-system-x86_64", "-enable-kvm", "-cpu", "host", "-m", "2048", "-smp", "2", *fwargs,
    "-drive", f"file={iso},media=cdrom,readonly=on", "-boot", "d", "-drive", f"file={disk},format=raw,if=virtio",
    "-display", "none", "-nic", "user,model=virtio-net-pci", "-serial", f"unix:{sock},server=on,wait=off"])
fails = []
def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok: fails.append(name)
try:
    for _ in range(50):
        if os.path.exists(sock): break
        time.sleep(0.2)
    s = socket.socket(socket.AF_UNIX); s.connect(sock); s.settimeout(1)
    buf = ""
    def expect(rx, timeout):
        global buf
        end = time.time() + timeout
        while time.time() < end:
            m = re.search(rx, buf)
            if m:
                out, buf = buf[:m.end()], buf[m.end():]; return out
            try: buf += s.recv(65536).decode(errors="replace")
            except socket.timeout: pass
        raise SystemExit(f"timeout waiting for {rx!r}; tail: {buf[-400:]!r}")
    def send(t): s.sendall(t.encode())
    expect(r"tetron login:", 240); send("tetronos\n"); expect(r"Password:", 20); send("live\n"); expect(r"\$ ", 60)
    n = [0]
    def run(cmd, timeout=60):
        n[0] += 1; tag = f"M{n[0]}X"
        send(f"{cmd}; echo {tag}$?\n")
        out = expect(tag + r"\d+", timeout)
        rc = int(re.search(tag + r"(\d+)", out).group(1)); expect(r"\$ ", 10)
        if os.environ.get("V"): print("---", cmd[:60], "\n", out[-500:], flush=True)
        return rc, out
    run("echo pass1234 | sudo tee /run/pw >/dev/null; sudo chmod 600 /run/pw")
    run("printf 'label: gpt\\n,\\n' | sudo sfdisk -q /dev/vda; sudo mkfs.ext4 -q /dev/vda1; sudo mount /dev/vda1 /mnt", 600)
    rc, out = run("findmnt -n /mnt"); check("target partition mounted before install", rc == 0)
    rc, out = run("sudo tetronos-install --user tester --password-file /run/pw --yes /dev/vda 2>&1 | tail -4", 2400)
    rc, out = run("findmnt -n /mnt; echo; test -b /dev/vda4 && echo ha""s4"); check("engine unmounted /mnt and repartitioned", "has4" in out.split("\n",1)[1])
    rc, out = run("sudo mount /dev/vda4 /mnt && grep -c '^tester:' /mnt/etc/passwd; ls /mnt/boot/grub/grub.cfg; sudo umount /mnt", 60)
    check("installed system has user and grub.cfg", "grub.cfg" in out and "\n1\r" in out or "\r\n1\r" in out)
    # the live medium must be refused (cdrom is not a disk; use the root overlay device name check via a loop of the squashfs)
    send("sudo systemctl poweroff\n")
    try: q.wait(timeout=120)
    except subprocess.TimeoutExpired: q.kill(); q.wait()
finally:
    if q.poll() is None: q.kill(); q.wait()
r = subprocess.run([f"{here}/boot-image.sh", disk, fw, os.environ.get("BOOT_T", "180")], env={**os.environ, "LOG": f"{w}/boot-{fw}.log"})
check(f"installed disk boots ({fw})", r.returncode == 0)
sys.exit(1 if fails else 0)
