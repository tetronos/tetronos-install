from libspec import Requirement


class InstallEngine(Requirement):
    """tetronos-install copies the running live system to a disk. The
    source is the pristine live squashfs (/run/live/rootfs/filesystem.squashfs,
    or --source DIR), never the live overlay, so no live session state
    (identity, host keys, logs, the live user) reaches the installed
    system. It needs no network. The target is a block device or, with
    --target-image FILE --size SIZE, a sparse image file (loop device),
    which gives installed-system images for VM and CI tests without
    booting an ISO. The installer is POSIX sh, root only, and refuses to
    run on a non live system unless --source is given."""


class InstallLayout(Requirement):
    """The target gets a GPT with four partitions: bios_boot 1 MiB, ESP
    512 MiB (vfat), /boot 1 GiB (ext4), root (ext4, rest of the disk).
    The same layout boots under BIOS and UEFI, so a disk moves between
    machines. /boot is a separate unencrypted partition so encryption
    (v2) only adds a step between partitioning and formatting. fstab uses
    UUIDs. The installer refuses a target that is mounted, holds the live
    medium, or is smaller than 8 GiB, and never touches another disk. It
    prints the target and asks for the word yes before it writes, unless
    --yes is given."""


class InstallNoLiveLeftovers(Requirement):
    """After the copy the installer removes the live packages from the
    target (live-boot, live-boot-initramfs-tools, live-config,
    live-config-systemd, tetronos-live-config) with apt-get purge in a
    chroot, then deletes any remaining live drop-in
    (kmsconvt@tty1 tetronos-autologin.conf, /etc/live) and rebuilds the
    initramfs for every kernel, so the installed system does not boot as a
    live system and does not create the live user."""


class InstallIdentityFresh(Requirement):
    """The installed system gets its own identity: /etc/machine-id is
    emptied (systemd creates it on first boot), /etc/ssh/ssh_host_* are
    regenerated with ssh-keygen -A when openssh-server is installed, and
    no /etc/tetron/secret_key exists (the tetron daemon creates it on
    first start). Hostname is --hostname (default tetron). The installer
    writes /etc/hosts for it."""


class InstallUser(Requirement):
    """The installer creates --user (required, no default) with
    useradd -m and the supplementary groups of the live user, and sets
    the password from --password-file (one line, plain text, read once and
    never in argv) or an interactive prompt. The live user does not exist
    on the target. An empty password is refused. Root login stays locked.
    Skeleton files come from /etc/skel (the Files app directories)."""


class InstallSshPolicy(Requirement):
    """SSH policy equals the live ISO (USER 2026-11-19): the service state
    of the edition is kept (sshd enabled on the Server edition, off on the
    Desktop edition) and password login is allowed because the installed
    user has a password that is not the public live password. The
    installer adds no ssh key and no ssh option, and removes the live
    drop-in 40-tetronos-live-password.conf together with the live-config
    package."""


class InstallAutologinOption(Requirement):
    """--autologin makes kmscon on tty1 log in --user without a password
    (a drop-in /etc/systemd/system/kmsconvt@tty1.service.d/autologin.conf
    like the live one, with the installed user). Default off. The option
    is the only place autologin is configured."""


class InstallBootloader(Requirement):
    """GRUB goes on the target for both firmwares: grub-install
    --target=i386-pc on the disk (bios_boot partition) and
    --target=x86_64-efi --removable --no-nvram on the ESP (mounted at
    /boot/efi), so the disk boots on any machine without touching the NVRAM
    of the build host. grub.cfg is made with update-grub in the target
    chroot when grub-mkconfig exists there, else a static grub.cfg is
    written from the kernels in /boot (root=UUID=...). The kernel command
    line is the quiet default plus console=tty0 console=ttyS0,115200n8."""


class InstallToolsInImage( Requirement):
    """The installer ships as the deb tetronos-install, in tetronos-core or
    tetronos-suite (decided with the ISO manifest). Depends: grub-pc-bin,
    grub-efi-amd64-bin, grub-common, dosfstools, e2fsprogs, util-linux
    (sfdisk, losetup), rsync, coreutils. The installed system keeps
    grub-common so update-grub works after kernel updates."""


class InstallFirstBoot(Requirement):
    """The installer enables tetronos-firstboot.service on the target (the
    package never enables itself) and, with --invite-file FILE, copies the
    invite to /etc/tetron/pending-invite (root, 0600). The invite never
    appears in argv or in the installer log."""


class InstallTest(Requirement):
    """tests/test-install.sh ISO builds an installed image with
    --target-image from the ISO squashfs, then checks in a chroot and in
    QEMU: BIOS boot and UEFI boot of the image reach the login prompt;
    the user exists, the live user and live packages do not; the machine
    id is empty before first boot and set after; no tetron secret_key;
    ssh host keys differ between two installs; autologin off by default.
    Nothing writes to a real disk. Results go to out/."""


class InstallEncryptionLater(Requirement):
    """v1 has no encryption. The steps partition, format, mount, copy,
    chroot setup and bootloader are separate functions so a v2 encryption
    step (/home or full disk, LUKS2, cryptsetup-initramfs) is added
    between partition and format without restructuring."""


class InstallTui(Requirement):
    """tetronos-install-tui is the front end of M7: a ratatui full screen
    program (keyboard only, 16 colors, so it works on a serial console and
    under kmscon) that collects the answers and runs the engine
    (/usr/sbin/tetronos-install) as a child process. It contains no install
    logic. Screens: Disk, You (username, password twice, hostname),
    Options (autologin, optional invite file), Confirm (the user types the
    disk name), Install (step list and log), Done (r reboots, q quits).
    Disk lists only whole disks of at least 8 GiB with no mounted
    partition, so the live medium is never offered. The password reaches
    the engine only through a 0600 file in /run that is removed when the
    engine exits, never through argv. --image FILE --size SIZE skips the
    Disk screen and installs to an image file (tests). The engine path is
    TETRONOS_INSTALL_BIN or tetronos-install from PATH."""
