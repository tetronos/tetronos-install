// State and logic of the installer TUI. No rendering, no terminal: unit testable.
use std::io::{BufRead, BufReader, Write};
use std::os::unix::fs::OpenOptionsExt;
use std::process::{Command, Stdio};
use std::sync::mpsc::{Receiver, channel};

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Screen {
    Disk,
    User,
    Options,
    Confirm,
    Install,
    Done,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Disk {
    pub path: String,
    pub size: u64,
    pub model: String,
    pub bus: String,
}

pub const MIN_DISK: u64 = 8 * 1024 * 1024 * 1024;

pub const FIELDS: [&str; 4] = ["Username", "Password", "Password again", "Hostname"];

pub struct App {
    pub screen: Screen,
    pub disks: Vec<Disk>,
    pub disk_sel: usize,
    pub image: Option<(String, String)>, // (file, size): test mode, skips the Disk screen
    pub fields: [String; 4],
    pub field_sel: usize,
    pub autologin: bool,
    pub invite: String,
    pub opt_sel: usize, // 0 autologin, 1 invite
    pub confirm: String,
    pub error: String,
    pub steps: Vec<String>,
    pub log: Vec<String>,
    pub rx: Option<Receiver<Msg>>,
    pub status: Option<i32>,
    pub quit: bool,
    pub reboot: bool,
}

pub enum Msg {
    Line(String),
    Exit(i32),
}

impl App {
    pub fn new(image: Option<(String, String)>) -> Self {
        let disks = if image.is_some() { vec![] } else { list_disks() };
        App {
            screen: if image.is_some() { Screen::User } else { Screen::Disk },
            disks,
            disk_sel: 0,
            image,
            fields: [String::new(), String::new(), String::new(), "tetron".into()],
            field_sel: 0,
            autologin: false,
            invite: String::new(),
            opt_sel: 0,
            confirm: String::new(),
            error: String::new(),
            steps: vec![],
            log: vec![],
            rx: None,
            status: None,
            quit: false,
            reboot: false,
        }
    }

    /// What the user must type on the Confirm screen.
    pub fn confirm_word(&self) -> String {
        match (&self.image, self.disks.get(self.disk_sel)) {
            (Some(_), _) => "yes".into(),
            (None, Some(d)) => d.path.trim_start_matches("/dev/").to_string(),
            _ => String::new(),
        }
    }

    pub fn validate_user(&self) -> Result<(), String> {
        valid_username(&self.fields[0])?;
        if self.fields[1].is_empty() {
            return Err("password must not be empty".into());
        }
        if self.fields[1] != self.fields[2] {
            return Err("passwords differ".into());
        }
        valid_hostname(&self.fields[3])
    }

    pub fn validate_options(&self) -> Result<(), String> {
        if !self.invite.is_empty() && !std::path::Path::new(&self.invite).is_file() {
            return Err(format!("invite file not found: {}", self.invite));
        }
        Ok(())
    }

    pub fn next(&mut self) {
        self.error.clear();
        match self.screen {
            Screen::Disk => {
                if self.disks.is_empty() {
                    self.error = "no usable disk (whole disks of 8 GiB or more, other than the live medium)".into();
                } else {
                    self.screen = Screen::User;
                }
            }
            Screen::User => match self.validate_user() {
                Ok(()) => self.screen = Screen::Options,
                Err(e) => self.error = e,
            },
            Screen::Options => match self.validate_options() {
                Ok(()) => self.screen = Screen::Confirm,
                Err(e) => self.error = e,
            },
            Screen::Confirm => {
                if self.confirm == self.confirm_word() {
                    if let Err(e) = self.start() {
                        self.error = e;
                    }
                } else {
                    self.error = format!("type {} to confirm", self.confirm_word());
                }
            }
            _ => {}
        }
    }

    pub fn back(&mut self) {
        self.error.clear();
        self.screen = match self.screen {
            Screen::User if self.image.is_none() => Screen::Disk,
            Screen::Options => Screen::User,
            Screen::Confirm => Screen::Options,
            s => s,
        };
    }

    /// Engine arguments. The password is never here (password file).
    pub fn engine_args(&self, pwfile: &str) -> Vec<String> {
        let mut a: Vec<String> = vec![
            "--yes".into(),
            "--user".into(),
            self.fields[0].clone(),
            "--hostname".into(),
            self.fields[3].clone(),
            "--password-file".into(),
            pwfile.into(),
        ];
        if self.autologin {
            a.push("--autologin".into());
        }
        if !self.invite.is_empty() {
            a.push("--invite-file".into());
            a.push(self.invite.clone());
        }
        match &self.image {
            Some((f, s)) => {
                a.push("--target-image".into());
                a.push(f.clone());
                a.push("--size".into());
                a.push(s.clone());
            }
            None => a.push(self.disks[self.disk_sel].path.clone()),
        }
        a
    }

    fn start(&mut self) -> Result<(), String> {
        let pwfile = "/run/tetronos-install-tui.pw".to_string();
        let _ = std::fs::remove_file(&pwfile);
        let mut f = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&pwfile)
            .map_err(|e| format!("password file: {e}"))?;
        writeln!(f, "{}", self.fields[1]).map_err(|e| e.to_string())?;
        drop(f);
        let bin = std::env::var("TETRONOS_INSTALL_BIN").unwrap_or_else(|_| "tetronos-install".into());
        let mut child = Command::new(bin)
            .args(self.engine_args(&pwfile))
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| {
                let _ = std::fs::remove_file(&pwfile);
                format!("cannot start the installer: {e}")
            })?;
        let (tx, rx) = channel();
        let out = child.stdout.take().unwrap();
        let err = child.stderr.take().unwrap();
        let t1 = tx.clone();
        let h1 = std::thread::spawn(move || {
            for l in BufReader::new(out).lines().map_while(Result::ok) {
                let _ = t1.send(Msg::Line(l));
            }
        });
        let t2 = tx.clone();
        let h2 = std::thread::spawn(move || {
            for l in BufReader::new(err).lines().map_while(Result::ok) {
                let _ = t2.send(Msg::Line(l));
            }
        });
        std::thread::spawn(move || {
            let _ = h1.join();
            let _ = h2.join();
            let code = child.wait().ok().and_then(|s| s.code()).unwrap_or(-1);
            let _ = std::fs::remove_file("/run/tetronos-install-tui.pw");
            let _ = tx.send(Msg::Exit(code));
        });
        self.rx = Some(rx);
        self.screen = Screen::Install;
        Ok(())
    }

    /// Drain engine messages. Called every tick.
    pub fn poll(&mut self) {
        let Some(rx) = &self.rx else { return };
        while let Ok(m) = rx.try_recv() {
            match m {
                Msg::Line(l) => {
                    if let Some(s) = l.strip_prefix("== ") {
                        self.steps.push(s.to_string());
                    }
                    self.log.push(l);
                    if self.log.len() > 500 {
                        self.log.remove(0);
                    }
                }
                Msg::Exit(c) => {
                    self.status = Some(c);
                    self.screen = Screen::Done;
                }
            }
        }
    }
}

pub fn valid_username(u: &str) -> Result<(), String> {
    let ok = !u.is_empty()
        && u.len() <= 32
        && u.chars().next().is_some_and(|c| c.is_ascii_lowercase() || c == '_')
        && u.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_' || c == '-');
    if ok { Ok(()) } else { Err("username: lowercase letters, digits, _ and -, starting with a letter".into()) }
}

pub fn valid_hostname(h: &str) -> Result<(), String> {
    let ok = !h.is_empty() && h.len() <= 63 && h.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '.');
    if ok { Ok(()) } else { Err("hostname: letters, digits, - and .".into()) }
}

/// Whole disks of at least MIN_DISK, except the one holding the live medium or the running root, from `lsblk -J -b` output.
pub fn parse_disks(json: &str) -> Vec<Disk> {
    fn is_live(m: &str) -> bool {
        m == "/" || m.starts_with("/run/live") || m.starts_with("/usr/lib/live") || m.starts_with("/lib/live")
    }
    fn mounted(n: &serde_json::Value) -> bool {
        let own = n["mountpoints"].as_array().is_some_and(|a| a.iter().any(|m| m.as_str().is_some_and(is_live)));
        own || n["children"].as_array().is_some_and(|c| c.iter().any(mounted))
    }
    let Ok(v) = serde_json::from_str::<serde_json::Value>(json) else { return vec![] };
    let mut out = vec![];
    for n in v["blockdevices"].as_array().cloned().unwrap_or_default() {
        if n["type"] != "disk" || mounted(&n) {
            continue;
        }
        let size = n["size"].as_u64().or_else(|| n["size"].as_str().and_then(|s| s.parse().ok())).unwrap_or(0);
        if size < MIN_DISK {
            continue;
        }
        out.push(Disk {
            path: format!("/dev/{}", n["name"].as_str().unwrap_or("?")),
            size,
            model: n["model"].as_str().unwrap_or("").trim().to_string(),
            bus: n["tran"].as_str().unwrap_or("").to_string(),
        });
    }
    out
}

pub fn list_disks() -> Vec<Disk> {
    Command::new("lsblk")
        .args(["-J", "-b", "-o", "NAME,SIZE,MODEL,TRAN,TYPE,MOUNTPOINTS"])
        .output()
        .map(|o| parse_disks(&String::from_utf8_lossy(&o.stdout)))
        .unwrap_or_default()
}

pub fn human(b: u64) -> String {
    let g = b as f64 / 1e9;
    if g >= 1000.0 { format!("{:.1} TB", g / 1000.0) } else { format!("{g:.0} GB") }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn disks_skip_live_small_and_partitions() {
        let j = r#"{"blockdevices":[
          {"name":"sda","size":500107862016,"model":"SSD ","tran":"sata","type":"disk","mountpoints":[null],
           "children":[{"name":"sda1","size":1,"type":"part","mountpoints":["/run/live/medium"]}]},
          {"name":"nvme0n1","size":1000204886016,"model":"Micron","tran":"nvme","type":"disk","mountpoints":[null]},
          {"name":"sdc","size":64000000000,"model":"USB stick","tran":"usb","type":"disk","mountpoints":[null],
           "children":[{"name":"sdc1","size":1,"type":"part","mountpoints":["/media/erik/DATA"]}]},
          {"name":"sdb","size":4000000000,"model":"small","tran":"usb","type":"disk","mountpoints":[null]},
          {"name":"loop0","size":900000000000,"type":"loop","mountpoints":[null]}]}"#;
        let d = parse_disks(j);
        assert_eq!(d.len(), 2);
        assert_eq!(d[0].path, "/dev/nvme0n1");
        assert_eq!(d[1].path, "/dev/sdc");
    }

    #[test]
    fn validation() {
        assert!(valid_username("erik").is_ok());
        assert!(valid_username("Erik").is_err());
        assert!(valid_username("1erik").is_err());
        assert!(valid_username("").is_err());
        assert!(valid_hostname("thinkpad-p1").is_ok());
        assert!(valid_hostname("bad host").is_err());
    }

    #[test]
    fn password_not_in_args_and_flow() {
        let mut a = App::new(Some(("/x/i.img".into(), "10G".into())));
        a.fields = ["tester".into(), "secret".into(), "secret".into(), "h1".into()];
        a.autologin = true;
        let args = a.engine_args("/run/pw");
        assert!(!args.iter().any(|s| s == "secret"));
        assert!(args.contains(&"--autologin".to_string()));
        assert!(args.windows(2).any(|w| w == ["--target-image", "/x/i.img"]));
        a.fields[2] = "other".into();
        assert!(a.validate_user().is_err());
        assert_eq!(a.confirm_word(), "yes");
    }
}
