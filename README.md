# tetronos-install

The installer of [TetronOS](https://github.com/tetronos/tetron-os): copies the running live system to a disk. GPT with bios_boot, ESP, /boot and root (ext4), the user, GRUB for BIOS and UEFI (the TetronOS logo menu, white on black when the logo can not draw), the ssh policy of the live ISO. USB and removable targets get a flash profile (noatime, fewer syncs). No network needed.

- `scripts/tetronos-install`: the engine (POSIX sh). `tetronos-install --help`.
- `tetronos-install-tui`: the full screen front end (Rust, ratatui), static musl. The boot menu entry "Install TetronOS" starts it on tty1 (`packaging/files/tetronos-install-tui.service`).

## Install

TetronOS live ISOs carry it. The `.deb` (amd64) is attached to each release and is in the [tetronos apt repository](https://tetronos.github.io/apt/) as `tetronos-install`.

## Build and test

```sh
cargo build --release --target x86_64-unknown-linux-musl
cargo test
tests/vm-install.py ISO bios|uefi     # install from a live ISO in a VM onto a second disk, then boot it
```

A release is a version bump in `Cargo.toml` merged to main (or a `v*` tag): the workflow builds the static binary and the `.deb` with [tetron-packaging](https://github.com/tetronos/tetron-packaging).

## License

MPL-2.0, see `LICENSE`.
