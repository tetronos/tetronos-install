#!/usr/bin/env -S uv run --with pyte python3
"""Drive tetronos-install-tui in a pty with --image (no real disk), then boot-check is left to boot-image.sh.
Usage: sudo tests/test-tui.py SQUASHFS_DIR IMAGE   (engine runs with --source SQUASHFS_DIR)
Checks: screens advance, bad input is refused, the install finishes with 'Installed', the image has the user."""
import pyte, fcntl, os, pty, select, struct, subprocess, sys, termios, time

sq, img = sys.argv[1], os.path.abspath(sys.argv[2])
here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
wrapper = f"{root}/DO-NOT-COMMIT/work/engine-wrapper.sh"
os.makedirs(os.path.dirname(wrapper), exist_ok=True)
open(wrapper, "w").write(f'#!/bin/sh\nexec {root}/scripts/tetronos-install "$@" --source {sq}\n')
os.chmod(wrapper, 0o755)
if os.path.exists(img):
    sys.exit(f"{img} exists")
env = dict(os.environ, TETRONOS_INSTALL_BIN=wrapper, TERM="xterm")
pid, fd = pty.fork()
if pid == 0:
    os.execve(f"{root}/target/release/tetronos-install-tui", ["tui", "--image", img, "--size", "10G"], env)
fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))  # a pty starts 0x0: nothing would draw
buf = b""
screen = pyte.Screen(100, 30); stream = pyte.ByteStream(screen)
def text(): return "\n".join(screen.display)
def pump(t=0.3):
    global buf
    end = time.time() + t
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            try: d = os.read(fd, 65536)
            except OSError: return
            buf += d; stream.feed(d)
def send(s): os.write(fd, s.encode()); pump()
def wait(t, timeout=300):
    end = time.time() + timeout
    while time.time() < end:
        pump(0.5)
        if t in text(): return True
    return False
fails = 0
def check(name, ok):
    global fails
    if not ok: print("   screen:\n" + text())
    print(("PASS " if ok else "FAIL ") + name)
    fails += not ok
pump(1)
check("starts on You screen", "2/5 You" in text())
send("\r\r\r\r")  # empty fields: refused
check("empty username refused", "username:" in text())
send("\t")  # Hostname -> Username (wraps)
send("tester\r"); send("pw1\r"); send("pw2\r"); send("\r")
check("password mismatch refused", "passwords differ" in text())
for _ in range(3): send("\t")   # Hostname -> Password again
for _ in range(3): send("\x7f")
send("pw1"); send("\r"); send("\r")
check("options screen", wait("3/5 Options", 5))
send(" "); send("\r")
check("confirm screen", wait("4/5 Confirm", 5))
send("no\r")
check("wrong confirm refused", "to confirm" in text() and "5/5" not in text())
for _ in range(2): send("\x7f")
send("yes\r")
check("install finishes", wait("Installed.", 400))
send("q")
pump(1)
try: os.waitpid(pid, 0)
except ChildProcessError: pass
check("password file removed", not os.path.exists("/run/tetronos-install-tui.pw"))
# image: user exists, autologin drop-in written
L = subprocess.check_output(["losetup", "-f", "--show", "-P", img], text=True).strip()
os.makedirs("/run/tetronos-tui-test", exist_ok=True)
subprocess.check_call(["mount", L + "p4", "/run/tetronos-tui-test"])
try:
    check("user tester in image", "tester:" in open("/run/tetronos-tui-test/etc/passwd").read())
    check("autologin set", os.path.exists("/run/tetronos-tui-test/etc/systemd/system/kmsconvt@tty1.service.d/autologin.conf"))
finally:
    subprocess.call(["umount", "/run/tetronos-tui-test"]); subprocess.call(["losetup", "-d", L])
sys.exit(1 if fails else 0)
