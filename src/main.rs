// tetronos-install-tui: full screen front end of tetronos-install (spec InstallTui).
mod app;
mod ui;

use app::{App, Screen};
use crossterm::{
    event::{self, Event, KeyCode, KeyEventKind, KeyModifiers},
    execute,
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode},
};
use ratatui::{Terminal, backend::CrosstermBackend};
use std::time::Duration;

fn main() -> anyhow::Result<()> {
    let mut image = None;
    let mut it = std::env::args().skip(1);
    let (mut file, mut size) = (None, None);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--image" => file = it.next(),
            "--size" => size = it.next(),
            "--version" => {
                println!("tetronos-install-tui {}", env!("CARGO_PKG_VERSION"));
                return Ok(());
            }
            _ => anyhow::bail!("usage: tetronos-install-tui [--image FILE --size SIZE] | --version"),
        }
    }
    if let (Some(f), Some(s)) = (file, size) {
        image = Some((f, s));
    }
    if unsafe { libc_geteuid() } != 0 {
        anyhow::bail!("must run as root");
    }
    let mut app = App::new(image);
    enable_raw_mode()?;
    execute!(std::io::stdout(), EnterAlternateScreen)?;
    let mut term = Terminal::new(CrosstermBackend::new(std::io::stdout()))?;
    let res = run(&mut term, &mut app);
    disable_raw_mode()?;
    execute!(std::io::stdout(), LeaveAlternateScreen)?;
    if res.is_ok() && app.reboot {
        let _ = std::process::Command::new("systemctl").arg("reboot").status();
    }
    res
}

unsafe extern "C" {
    #[link_name = "geteuid"]
    fn libc_geteuid() -> u32;
}

fn run(term: &mut Terminal<CrosstermBackend<std::io::Stdout>>, app: &mut App) -> anyhow::Result<()> {
    while !app.quit {
        app.poll();
        term.draw(|f| ui::draw(f, app))?;
        if !event::poll(Duration::from_millis(100))? {
            continue;
        }
        let Event::Key(k) = event::read()? else { continue };
        if k.kind != KeyEventKind::Press {
            continue;
        }
        if k.code == KeyCode::Char('c') && k.modifiers.contains(KeyModifiers::CONTROL) && app.screen != Screen::Install {
            break;
        }
        key(app, k.code);
    }
    Ok(())
}

fn key(app: &mut App, code: KeyCode) {
    match app.screen {
        Screen::Disk => match code {
            KeyCode::Up if app.disk_sel > 0 => app.disk_sel -= 1,
            KeyCode::Down if app.disk_sel + 1 < app.disks.len() => app.disk_sel += 1,
            KeyCode::Enter => app.next(),
            KeyCode::Esc => app.quit = true,
            _ => {}
        },
        Screen::User => match code {
            KeyCode::Tab | KeyCode::Down => app.field_sel = (app.field_sel + 1) % 4,
            KeyCode::Up => app.field_sel = (app.field_sel + 3) % 4,
            KeyCode::Enter => {
                if app.field_sel < 3 {
                    app.field_sel += 1;
                } else {
                    app.next();
                }
            }
            KeyCode::Esc => app.back(),
            KeyCode::Backspace => {
                app.fields[app.field_sel].pop();
            }
            KeyCode::Char(c) => app.fields[app.field_sel].push(c),
            _ => {}
        },
        Screen::Options => match code {
            KeyCode::Tab | KeyCode::Up | KeyCode::Down => app.opt_sel = 1 - app.opt_sel,
            KeyCode::Char(' ') if app.opt_sel == 0 => app.autologin = !app.autologin,
            KeyCode::Char(c) if app.opt_sel == 1 => app.invite.push(c),
            KeyCode::Backspace if app.opt_sel == 1 => {
                app.invite.pop();
            }
            KeyCode::Enter => app.next(),
            KeyCode::Esc => app.back(),
            _ => {}
        },
        Screen::Confirm => match code {
            KeyCode::Enter => app.next(),
            KeyCode::Esc => app.back(),
            KeyCode::Backspace => {
                app.confirm.pop();
            }
            KeyCode::Char(c) => app.confirm.push(c),
            _ => {}
        },
        Screen::Install => {}
        Screen::Done => match code {
            KeyCode::Char('r') if app.status == Some(0) => {
                app.reboot = true;
                app.quit = true;
            }
            KeyCode::Char('q') | KeyCode::Esc | KeyCode::Enter => app.quit = true,
            _ => {}
        },
    }
}
